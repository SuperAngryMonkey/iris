#!/usr/bin/env python3
"""
iris — a draft-only Microsoft 365 mail MCP.

The other messenger of the gods. Composes mail into your Outlook Drafts
folder and stops there. A human opens Outlook, reads it, and presses Send.

Containment (heimdall doctrine applied to mail):
  - NO SEND CAPABILITY  the app requests Mail.ReadWrite ONLY, never Mail.Send.
                        This is structural: the token cannot send mail, so no
                        bug, loop, or bad instruction can put mail in flight.
  - DELEGATED AUTH      public client + device code. No client secret on disk,
                        no admin consent, blast radius = this mailbox only.
  - RECIPIENT ALLOWLIST if recipients.allow is present and non-empty, drafts to
                        anything outside it are refused.
  - AUDIT LOG           every draft written appended to audit.log.
  - KILL SWITCH         a DISABLED file (or IRIS_DISABLED=1) blocks everything.
  - CONFIRM GATE        deleting a draft requires confirm=true, which the
                        assistant must only set after explicit human ok.

Setup (one time, in Entra ID):
  1. Register an application. Single tenant is fine.
  2. Authentication -> Add platform -> Mobile and desktop -> check the
     "https://login.microsoftonline.com/common/oauth2/nativeclient" redirect,
     and set "Allow public client flows" = Yes.
  3. API permissions -> Microsoft Graph -> Delegated -> Mail.ReadWrite.
     Do NOT add Mail.Send. That omission is the safety property.
  4. Export IRIS_CLIENT_ID and IRIS_TENANT_ID, then call iris_login().
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import msal
import requests
from mcp.server.fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ALLOWLIST_FILE = Path(os.environ.get("IRIS_ALLOWLIST", HERE / "recipients.allow"))
AUDIT_LOG = Path(os.environ.get("IRIS_AUDIT_LOG", HERE / "audit.log"))
CACHE_FILE = Path(os.environ.get("IRIS_TOKEN_CACHE", HERE / ".token_cache.json"))
DISABLED_FILE = HERE / "DISABLED"
# Drafts are staged here instead of the Drafts folder. Blank = use Drafts.
DRAFT_FOLDER = os.environ.get("IRIS_DRAFT_FOLDER", "Cyrano")

CLIENT_ID = os.environ.get("IRIS_CLIENT_ID", "")
TENANT_ID = os.environ.get("IRIS_TENANT_ID", "organizations")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Mail.ReadWrite ONLY. Adding Mail.Send here would defeat the entire design.
SCOPES = ["Mail.ReadWrite"]

GRAPH = "https://graph.microsoft.com/v1.0"
HTTP_TIMEOUT = 30
MAX_BODY = 500_000

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

mcp = FastMCP("iris")


# ----------------------------------------------------------------- plumbing

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _disabled() -> bool:
    return DISABLED_FILE.exists() or os.environ.get("IRIS_DISABLED") == "1"


def _audit(action: str, detail: str) -> None:
    try:
        with AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{_now()}\t{action}\t{detail}\n")
    except OSError:
        pass


def _load_allowlist() -> list[str]:
    if not ALLOWLIST_FILE.exists():
        return []
    entries = []
    for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            entries.append(line)
    return entries


def _check_recipients(addrs: list[str]) -> str | None:
    """Return an error string if any address is outside the allowlist."""
    allow = _load_allowlist()
    if not allow:
        return None
    bad = []
    for a in addrs:
        a = a.strip().lower()
        domain = a.rsplit("@", 1)[-1]
        if a not in allow and domain not in allow and f"@{domain}" not in allow:
            bad.append(a)
    if bad:
        return (
            f"recipients not in {ALLOWLIST_FILE.name}: {', '.join(bad)}. "
            "Add them to the allowlist or clear the file to allow all."
        )
    return None


def _cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text(encoding="utf-8"))
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")
        try:
            CACHE_FILE.chmod(0o600)
        except OSError:
            pass


def _app(cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=cache
    )


def _token() -> tuple[str | None, str | None]:
    """Return (access_token, error)."""
    if not CLIENT_ID:
        return None, "IRIS_CLIENT_ID is not set. See the setup notes in server.py."
    cache = _cache()
    app = _app(cache)
    accounts = app.get_accounts()
    if not accounts:
        return None, "not signed in — run iris_login() first"
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache)
    if not result or "access_token" not in result:
        return None, "token expired or revoked — run iris_login() again"
    return result["access_token"], None


def _graph(method: str, path: str, token: str, **kw) -> tuple[dict, int]:
    url = path if path.startswith("http") else f"{GRAPH}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers.update(kw.pop("headers", {}))
    resp = requests.request(method, url, headers=headers, timeout=HTTP_TIMEOUT, **kw)
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        body = {"raw": resp.text[:2000]}
    return body, resp.status_code


def _recips(addrs: list[str] | None) -> list[dict]:
    return [{"emailAddress": {"address": a.strip()}} for a in (addrs or []) if a.strip()]


def _flatten(*groups) -> list[str]:
    out = []
    for g in groups:
        for a in (g or []):
            if a and a.strip():
                out.append(a.strip())
    return out


def _ensure_folder(token: str) -> tuple[str | None, str | None]:
    """Find or create the staging mail folder. Returns (folder_id, error)."""
    if not DRAFT_FOLDER:
        return "drafts", None
    body, code = _graph(
        "GET", "/me/mailFolders?$top=100&$select=id,displayName", token
    )
    if code != 200:
        return None, f"folder lookup failed {code}: {json.dumps(body)[:300]}"
    want = DRAFT_FOLDER.strip().lower()
    for f in body.get("value", []):
        if (f.get("displayName") or "").strip().lower() == want:
            return f.get("id"), None
    made, code = _graph(
        "POST", "/me/mailFolders", token, json={"displayName": DRAFT_FOLDER}
    )
    if code not in (200, 201):
        return None, f"folder creation failed {code}: {json.dumps(made)[:300]}"
    _audit("folder", f"created {DRAFT_FOLDER} id={made.get('id')}")
    return made.get("id"), None


# -------------------------------------------------------------------- tools

@mcp.tool()
def iris_login() -> str:
    """Start a device-code sign-in for the mailbox. Returns a URL and a code
    for the human to enter in a browser. Only needed once, or after the
    refresh token lapses."""
    if _disabled():
        return "iris is DISABLED (kill switch engaged)"
    if not CLIENT_ID:
        return "IRIS_CLIENT_ID is not set. See the setup notes in server.py."
    cache = _cache()
    app = _app(cache)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        return f"failed to start device flow: {json.dumps(flow)[:500]}"
    msg = flow.get("message", "")
    result = app.acquire_token_by_device_flow(flow)  # blocks until done or expires
    _save_cache(cache)
    if "access_token" in result:
        who = result.get("id_token_claims", {}).get("preferred_username", "unknown")
        _audit("login", who)
        return f"signed in as {who} (scopes: {' '.join(SCOPES)} — no send capability)"
    return f"sign-in failed: {result.get('error_description', json.dumps(result))[:500]}\n\n{msg}"


@mcp.tool()
def iris_auth_status() -> str:
    """Report whether iris is signed in, as whom, and with what scopes."""
    if _disabled():
        return "iris is DISABLED (kill switch engaged)"
    token, err = _token()
    if err:
        return err
    body, code = _graph("GET", "/me?$select=displayName,userPrincipalName", token)
    if code != 200:
        return f"graph error {code}: {json.dumps(body)[:400]}"
    allow = _load_allowlist()
    return json.dumps({
        "signed_in_as": body.get("userPrincipalName"),
        "display_name": body.get("displayName"),
        "scopes": SCOPES,
        "can_send": False,
        "draft_folder": DRAFT_FOLDER or "Drafts",
        "recipient_allowlist": allow or "(empty — all recipients permitted)",
    }, indent=2)


@mcp.tool()
def iris_create_draft(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html: bool = False,
    reply_to_message_id: str | None = None,
) -> str:
    """Compose a message into the staging mail folder (IRIS_DRAFT_FOLDER,
    default "Cyrano"; created on first use). It is NOT sent — a human opens
    Outlook and presses Send. Set reply_to_message_id to draft a threaded
    reply to an existing message."""
    if _disabled():
        return "iris is DISABLED (kill switch engaged)"
    if not to:
        return "at least one 'to' recipient is required"
    if len(body) > MAX_BODY:
        return f"body too large ({len(body)} chars, max {MAX_BODY})"

    everyone = _flatten(to, cc, bcc)
    malformed = [a for a in everyone if not EMAIL_RE.match(a)]
    if malformed:
        return f"malformed addresses: {', '.join(malformed)}"
    problem = _check_recipients(everyone)
    if problem:
        return problem

    token, err = _token()
    if err:
        return err

    content_type = "HTML" if html else "Text"

    if reply_to_message_id:
        draft, code = _graph("POST", f"/me/messages/{reply_to_message_id}/createReply", token)
        if code not in (200, 201):
            return f"createReply failed {code}: {json.dumps(draft)[:400]}"
        draft_id = draft.get("id")
        patch = {
            "body": {"contentType": content_type, "content": body},
            "toRecipients": _recips(to),
        }
        if subject:
            patch["subject"] = subject
        if cc:
            patch["ccRecipients"] = _recips(cc)
        if bcc:
            patch["bccRecipients"] = _recips(bcc)
        out, code = _graph("PATCH", f"/me/messages/{draft_id}", token, json=patch)
        if code != 200:
            return f"draft created but patch failed {code}: {json.dumps(out)[:400]}"
        # createReply lands it in Drafts; relocate to the staging folder.
        # NOTE: a move returns a NEW message id, so rebind out.
        folder_id, ferr = _ensure_folder(token)
        if ferr:
            return ferr
        if folder_id != "drafts":
            moved, code = _graph(
                "POST", f"/me/messages/{draft_id}/move", token,
                json={"destinationId": folder_id},
            )
            if code not in (200, 201):
                return f"drafted but move failed {code}: {json.dumps(moved)[:400]}"
            out = moved
    else:
        payload = {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": _recips(to),
        }
        if cc:
            payload["ccRecipients"] = _recips(cc)
        if bcc:
            payload["bccRecipients"] = _recips(bcc)
        folder_id, ferr = _ensure_folder(token)
        if ferr:
            return ferr
        out, code = _graph(
            "POST", f"/me/mailFolders/{folder_id}/messages", token, json=payload
        )
        if code not in (200, 201):
            return f"draft creation failed {code}: {json.dumps(out)[:400]}"

    _audit("draft", f"to={','.join(to)} subject={subject!r} id={out.get('id')}")
    return json.dumps({
        "status": "draft created — NOT sent",
        "folder": DRAFT_FOLDER or "Drafts",
        "id": out.get("id"),
        "subject": out.get("subject"),
        "to": [r["emailAddress"]["address"] for r in out.get("toRecipients", [])],
        "webLink": out.get("webLink"),
        "next": f"open the {DRAFT_FOLDER or 'Drafts'} folder in Outlook, read it, press Send",
    }, indent=2)


@mcp.tool()
def iris_list_drafts(limit: int = 10) -> str:
    """List recent messages sitting in the staging mail folder."""
    if _disabled():
        return "iris is DISABLED (kill switch engaged)"
    limit = max(1, min(int(limit), 50))
    token, err = _token()
    if err:
        return err
    folder_id, ferr = _ensure_folder(token)
    if ferr:
        return ferr
    q = (f"/me/mailFolders/{folder_id}/messages?$top={limit}"
         "&$select=id,subject,toRecipients,createdDateTime,webLink"
         "&$orderby=createdDateTime desc")
    body, code = _graph("GET", q, token)
    if code != 200:
        return f"graph error {code}: {json.dumps(body)[:400]}"
    items = [{
        "id": m.get("id"),
        "subject": m.get("subject"),
        "to": [r["emailAddress"]["address"] for r in m.get("toRecipients", [])],
        "created": m.get("createdDateTime"),
        "webLink": m.get("webLink"),
    } for m in body.get("value", [])]
    return json.dumps(items, indent=2)


@mcp.tool()
def iris_update_draft(
    draft_id: str,
    subject: str | None = None,
    body: str | None = None,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html: bool = False,
) -> str:
    """Revise an existing draft in place. Only the fields you pass are changed."""
    if _disabled():
        return "iris is DISABLED (kill switch engaged)"
    patch: dict = {}
    if subject is not None:
        patch["subject"] = subject
    if body is not None:
        if len(body) > MAX_BODY:
            return f"body too large ({len(body)} chars, max {MAX_BODY})"
        patch["body"] = {"contentType": "HTML" if html else "Text", "content": body}
    for field, val in (("toRecipients", to), ("ccRecipients", cc), ("bccRecipients", bcc)):
        if val is not None:
            patch[field] = _recips(val)
    if not patch:
        return "nothing to update — pass at least one field"

    everyone = _flatten(to, cc, bcc)
    if everyone:
        malformed = [a for a in everyone if not EMAIL_RE.match(a)]
        if malformed:
            return f"malformed addresses: {', '.join(malformed)}"
        problem = _check_recipients(everyone)
        if problem:
            return problem

    token, err = _token()
    if err:
        return err
    out, code = _graph("PATCH", f"/me/messages/{draft_id}", token, json=patch)
    if code != 200:
        return f"update failed {code}: {json.dumps(out)[:400]}"
    _audit("update", f"id={draft_id} fields={','.join(patch)}")
    return json.dumps({
        "status": "draft updated — still NOT sent",
        "id": out.get("id"),
        "subject": out.get("subject"),
        "webLink": out.get("webLink"),
    }, indent=2)


@mcp.tool()
def iris_delete_draft(draft_id: str, confirm: bool = False) -> str:
    """Delete a draft. Destructive, so confirm=true is required — set it only
    after the human has explicitly approved deleting this specific draft."""
    if _disabled():
        return "iris is DISABLED (kill switch engaged)"
    if not confirm:
        return ("refusing to delete without confirm=true. Ask the human first, "
                "then retry with confirm=true.")
    token, err = _token()
    if err:
        return err
    out, code = _graph("DELETE", f"/me/messages/{draft_id}", token)
    if code not in (200, 204):
        return f"delete failed {code}: {json.dumps(out)[:400]}"
    _audit("delete", f"id={draft_id}")
    return f"draft {draft_id} deleted"


if __name__ == "__main__":
    mcp.run()
