from workers import WorkerEntrypoint, Response, asgi
import json, base64, os, hmac, traceback

_ENV = None


def cfg(name, default=None):
    v = getattr(_ENV, name, None)
    return v if v is not None else default


GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE_STR = "offline_access User.Read Mail.ReadWrite Mail.Send"


def _token_url():
    return f"https://login.microsoftonline.com/{cfg('IRIS_TENANT_ID')}/oauth2/v2.0/token"


def _devicecode_url():
    return f"https://login.microsoftonline.com/{cfg('IRIS_TENANT_ID')}/oauth2/v2.0/devicecode"


def _key():
    k = cfg("IRIS_ENC_KEY")
    return base64.b64decode(k) if k else None


def _encrypt(s):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    n = os.urandom(12)
    ct = AESGCM(_key()).encrypt(n, s.encode(), None)
    return base64.b64encode(n + ct).decode()


def _decrypt(b):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(b)
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode()


async def _kv_get(k):
    return await _ENV.IRIS_KV.get(k)


async def _kv_put(k, v):
    await _ENV.IRIS_KV.put(k, v)


async def _access_token():
    blob = await _kv_get("refresh_token")
    if not blob:
        return None, "not signed in — run iris_login"
    import httpx
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(_token_url(), data={
            "grant_type": "refresh_token", "client_id": cfg("IRIS_CLIENT_ID"),
            "refresh_token": _decrypt(blob), "scope": SCOPE_STR})
    t = r.json()
    if "access_token" not in t:
        return None, "refresh failed: " + str(t.get("error_description", ""))[:200]
    if t.get("refresh_token"):
        await _kv_put("refresh_token", _encrypt(t["refresh_token"]))
    return t["access_token"], None


async def _graph(method, path, token, body=None):
    import httpx
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, GRAPH + path,
                            headers={"Authorization": f"Bearer {token}"}, json=body)
    try:
        j = r.json()
    except Exception:
        j = {}
    return j, r.status_code


def _recips(addrs):
    return [{"emailAddress": {"address": a}} for a in addrs]


def _check_recipients(addrs):
    raw = cfg("IRIS_ALLOWLIST", "") or ""
    allow = [x.strip().lower() for x in raw.split(",") if x.strip()]
    if not allow:
        return None
    for a in addrs:
        al = a.lower()
        if al not in allow and al.split("@")[-1] not in allow:
            return f"recipient {a} not in allowlist ({raw})"
    return None


async def _ensure_folder(token, name=None):
    target = (cfg("IRIS_DRAFT_FOLDER", "AI Drafts") if name is None else (name or "")).strip()
    if not target or target.lower() == "drafts":
        return "drafts", None
    body, code = await _graph("GET", "/me/mailFolders?$top=100&$select=id,displayName", token)
    if code != 200:
        return None, f"folder lookup failed {code}: {json.dumps(body)[:200]}"
    want = target.lower()
    for f in body.get("value", []):
        if (f.get("displayName") or "").strip().lower() == want:
            return f.get("id"), None
    made, code = await _graph("POST", "/me/mailFolders", token, {"displayName": target})
    if code not in (200, 201):
        return None, f"folder creation failed {code}: {json.dumps(made)[:200]}"
    return made.get("id"), None


async def _audit(action, detail):
    import datetime
    entry = {"ts": datetime.datetime.utcnow().isoformat() + "Z", "action": action}
    entry.update(detail)
    try:
        raw = await _kv_get("audit_log") or ""
        lines = raw.split("\n") if raw else []
        lines.append(json.dumps(entry))
        await _kv_put("audit_log", "\n".join(lines[-500:]))
    except Exception:
        pass


def _build_mcp():
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    m = FastMCP("iris", stateless_http=True)
    m.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    @m.tool()
    async def iris_auth_status() -> str:
        """Who is signed in, scopes, whether Graph is reachable. Send is OFF."""
        if not await _kv_get("refresh_token"):
            return json.dumps({"signed_in": False, "hint": "run iris_login"}, indent=2)
        token, err = await _access_token()
        if err:
            return json.dumps({"signed_in": True, "graph_ok": False, "error": err}, indent=2)
        me, code = await _graph("GET", "/me?$select=userPrincipalName", token)
        return json.dumps({"signed_in": True,
                           "signed_in_as": me.get("userPrincipalName") if code == 200 else None,
                           "scopes": ["Mail.ReadWrite", "Mail.Send"], "graph_ok": code == 200,
                           "can_send": True}, indent=2)

    @m.tool()
    async def iris_login() -> str:
        """Start device-code sign-in for the bot mailbox. Returns a URL and a code."""
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(_devicecode_url(),
                             data={"client_id": cfg("IRIS_CLIENT_ID"), "scope": SCOPE_STR})
        f = r.json()
        if "user_code" not in f:
            return "failed to start sign-in: " + json.dumps(f)[:300]
        await _kv_put("pending_device_code", f["device_code"])
        return json.dumps({"verification_uri": f.get("verification_uri"),
                           "user_code": f["user_code"],
                           "next": "open the URL, enter the code, then call iris_login_finish"}, indent=2)

    @m.tool()
    async def iris_login_finish() -> str:
        """Complete sign-in after entering the code. If pending, finish the browser step and call again."""
        dc = await _kv_get("pending_device_code")
        if not dc:
            return "no pending sign-in — call iris_login first"
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(_token_url(), data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": cfg("IRIS_CLIENT_ID"), "device_code": dc})
        t = r.json()
        if "error" in t:
            if t["error"] == "authorization_pending":
                return "not authorized yet — finish the browser step, then call iris_login_finish again"
            return "sign-in failed: " + str(t.get("error_description", t["error"]))[:200]
        await _kv_put("refresh_token", _encrypt(t["refresh_token"]))
        await _kv_put("pending_device_code", "")
        me, code = await _graph("GET", "/me?$select=userPrincipalName", t["access_token"])
        return json.dumps({"status": "signed in — refresh token stored encrypted",
                           "signed_in_as": me.get("userPrincipalName") if code == 200 else None}, indent=2)

    @m.tool()
    async def iris_list_folders() -> str:
        """List the bot mailbox's top-level mail folders."""
        token, err = await _access_token()
        if err:
            return err
        body, code = await _graph("GET",
            "/me/mailFolders?$top=100&$select=id,displayName,unreadItemCount,totalItemCount", token)
        if code != 200:
            return f"graph error {code}: {json.dumps(body)[:300]}"
        return json.dumps([{"name": f.get("displayName"), "id": f.get("id"),
                            "unread": f.get("unreadItemCount"), "total": f.get("totalItemCount")}
                           for f in body.get("value", [])], indent=2)

    @m.tool()
    async def iris_create_draft(to: list[str] | None = None, subject: str = "", body: str = "",
                                cc: list[str] | None = None, bcc: list[str] | None = None,
                                html: bool = False, reply_to_message_id: str | None = None,
                                folder: str | None = None) -> str:
        """Compose an UNSENT draft into a mail folder (default from IRIS_DRAFT_FOLDER).
        Never sends — a human opens Outlook and presses Send. Set reply_to_message_id
        to draft a threaded reply. folder picks/creates the destination folder by name."""
        token, err = await _access_token()
        if err:
            return err
        if not to and not reply_to_message_id:
            return "need at least one recipient (or reply_to_message_id)"
        prob = _check_recipients((to or []) + (cc or []) + (bcc or []))
        if prob:
            return prob
        btype = "HTML" if html else "Text"
        if reply_to_message_id:
            rep, code = await _graph("POST", f"/me/messages/{reply_to_message_id}/createReply", token)
            if code not in (200, 201):
                return f"createReply failed {code}: {json.dumps(rep)[:300]}"
            draft_id = rep.get("id")
            patch = {"body": {"contentType": btype, "content": body}}
            if subject:
                patch["subject"] = subject
            if to:
                patch["toRecipients"] = _recips(to)
            if cc:
                patch["ccRecipients"] = _recips(cc)
            if bcc:
                patch["bccRecipients"] = _recips(bcc)
            out, code = await _graph("PATCH", f"/me/messages/{draft_id}", token, patch)
            if code != 200:
                return f"draft created but patch failed {code}: {json.dumps(out)[:300]}"
            folder_id, ferr = await _ensure_folder(token, folder)
            if ferr:
                return ferr
            if folder_id != "drafts":
                moved, code = await _graph("POST", f"/me/messages/{draft_id}/move", token,
                                           {"destinationId": folder_id})
                if code not in (200, 201):
                    return f"created but move failed {code}: {json.dumps(moved)[:200]}"
                out = moved
        else:
            payload = {"subject": subject or "",
                       "body": {"contentType": btype, "content": body},
                       "toRecipients": _recips(to)}
            if cc:
                payload["ccRecipients"] = _recips(cc)
            if bcc:
                payload["bccRecipients"] = _recips(bcc)
            folder_id, ferr = await _ensure_folder(token, folder)
            if ferr:
                return ferr
            path = "/me/messages" if folder_id == "drafts" else f"/me/mailFolders/{folder_id}/messages"
            out, code = await _graph("POST", path, token, payload)
            if code not in (200, 201):
                return f"draft creation failed {code}: {json.dumps(out)[:300]}"
        return json.dumps({"status": "draft created — NOT sent", "id": out.get("id"),
                           "subject": out.get("subject"),
                           "to": [r["emailAddress"]["address"] for r in out.get("toRecipients", [])],
                           "webLink": out.get("webLink")}, indent=2)

    @m.tool()
    async def iris_list_drafts(limit: int = 10, folder: str | None = None) -> str:
        """List recent messages in a draft folder (default IRIS_DRAFT_FOLDER)."""
        token, err = await _access_token()
        if err:
            return err
        limit = max(1, min(int(limit), 50))
        folder_id, ferr = await _ensure_folder(token, folder)
        if ferr:
            return ferr
        q = (f"/me/mailFolders/{folder_id}/messages?$top={limit}"
             "&$select=id,subject,toRecipients,isDraft,createdDateTime,webLink"
             "&$orderby=createdDateTime desc")
        body, code = await _graph("GET", q, token)
        if code != 200:
            return f"graph error {code}: {json.dumps(body)[:300]}"
        return json.dumps([{"id": mm.get("id"), "subject": mm.get("subject"),
                            "to": [r["emailAddress"]["address"] for r in mm.get("toRecipients", [])],
                            "isDraft": mm.get("isDraft"), "created": mm.get("createdDateTime"),
                            "webLink": mm.get("webLink")} for mm in body.get("value", [])], indent=2)

    @m.tool()
    async def iris_update_draft(draft_id: str, to: list[str] | None = None, subject: str | None = None,
                                body: str | None = None, cc: list[str] | None = None,
                                bcc: list[str] | None = None, html: bool = False) -> str:
        """Revise a draft in place. Only supplied fields change."""
        token, err = await _access_token()
        if err:
            return err
        patch = {}
        if subject is not None:
            patch["subject"] = subject
        if body is not None:
            patch["body"] = {"contentType": "HTML" if html else "Text", "content": body}
        if to:
            prob = _check_recipients(to)
            if prob:
                return prob
            patch["toRecipients"] = _recips(to)
        if cc:
            patch["ccRecipients"] = _recips(cc)
        if bcc:
            patch["bccRecipients"] = _recips(bcc)
        if not patch:
            return "nothing to update"
        out, code = await _graph("PATCH", f"/me/messages/{draft_id}", token, patch)
        if code != 200:
            return f"update failed {code}: {json.dumps(out)[:300]}"
        return json.dumps({"status": "draft updated", "id": out.get("id"),
                           "subject": out.get("subject")}, indent=2)

    @m.tool()
    async def iris_delete_draft(draft_id: str, confirm: bool = False) -> str:
        """Move a draft to Deleted Items (recoverable). Requires confirm=true."""
        token, err = await _access_token()
        if err:
            return err
        if not confirm:
            return "refusing to delete without confirm=true"
        out, code = await _graph("POST", f"/me/messages/{draft_id}/move", token,
                                 {"destinationId": "deleteditems"})
        if code not in (200, 201):
            return f"delete failed {code}: {json.dumps(out)[:300]}"
        return f"draft {draft_id} moved to Deleted Items"

    @m.tool()
    async def iris_send_draft(draft_id: str, confirm: bool = False) -> str:
        """Send an existing draft AS the bot mailbox. Requires confirm=true.
        Honors the IRIS_ALLOWLIST recipient allowlist and the IRIS_DISABLED kill switch."""
        if (cfg("IRIS_DISABLED", "") or "").strip():
            return "sending disabled (IRIS_DISABLED is set) — refusing"
        token, err = await _access_token()
        if err:
            return err
        if not confirm:
            return "refusing to send without confirm=true"
        msg, code = await _graph("GET",
            f"/me/messages/{draft_id}?$select=subject,toRecipients,ccRecipients,bccRecipients,isDraft", token)
        if code != 200:
            return f"could not load draft {code}: {json.dumps(msg)[:200]}"
        if not msg.get("isDraft", True):
            return "that message is not a draft (already sent?) — refusing"
        addrs = [r["emailAddress"]["address"]
                 for k in ("toRecipients", "ccRecipients", "bccRecipients")
                 for r in msg.get(k, [])]
        if not addrs:
            return "draft has no recipients — refusing"
        prob = _check_recipients(addrs)
        if prob:
            return prob
        out, code = await _graph("POST", f"/me/messages/{draft_id}/send", token)
        if code not in (200, 202):
            return f"send failed {code}: {json.dumps(out)[:200]}"
        await _audit("send", {"draft_id": draft_id, "subject": msg.get("subject"), "to": addrs})
        return json.dumps({"status": "SENT", "subject": msg.get("subject"), "to": addrs}, indent=2)

    @m.tool()
    async def iris_audit_tail(limit: int = 20) -> str:
        """Show the most recent send-audit entries recorded by the worker."""
        raw = await _kv_get("audit_log") or ""
        lines = [x for x in raw.split("\n") if x.strip()]
        return json.dumps(lines[-max(1, min(int(limit), 200)):], indent=2)

    return m.streamable_http_app()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global _ENV
        _ENV = self.env
        try:
            want = cfg("IRIS_HTTP_TOKEN")
            if not want:
                return Response(json.dumps({"error": "server not configured: no bearer"}),
                                status=503, headers={"content-type": "application/json"})
            auth = request.headers.get("Authorization") or ""
            presented = auth[7:] if auth.startswith("Bearer ") else ""
            if not hmac.compare_digest(presented, want):
                return Response(json.dumps({"error": "unauthorized"}), status=401,
                                headers={"content-type": "application/json", "WWW-Authenticate": "Bearer"})
            app = _build_mcp()
            return await asgi.fetch(app, request, self.env)
        except Exception:
            return Response(traceback.format_exc(), status=500, headers={"content-type": "text/plain"})
