# Changelog

## 0.2.1 — 2026-09-02

- Optional sending, off by default and still structural. `IRIS_ENABLE_SEND=1` —
  together with granting `Mail.Send` on your app registration and re-consenting —
  registers an `iris_send_draft` tool. Without all three the tool isn't registered
  and the token can't transmit, so the absent-capability guarantee is unchanged for
  anyone who doesn't opt in. Enabling it trades that structural guarantee for in-code
  guardrails: `confirm=true`, an allowlist re-check, and a check that the message is
  still an unsent draft. `SECURITY.md` describes the trade honestly.
- User-selectable draft folder. `iris_create_draft` and `iris_list_drafts` take an
  optional `folder`, and a new `iris_list_folders` lists your top-level folders. The
  default stays `AI Drafts`.
- Added `docs/ADMIN-DEPLOYMENT.md` — authorizing iris across a Microsoft 365 tenant
  (admin consent, per-user assignment, the delegated model), linked from the README.
- Documented that iris needs Python 3.10+ (the macOS system 3.9 is too old), and that
  the Grok CLI runs iris locally while the Grok app/Bot is remote-only.
- Scrubbed personal Entra IDs and a third-party address from the tracked docs.

## 0.1.0 — 2026-08-21

First published release.

- Packaged for PyPI as `iris-mcp` with an `iris-mcp` console script, and
  registered with the MCP registry as `io.github.SuperAngryMonkey/iris`.
- Default draft folder is now `AI Drafts`. It was previously a name meaningful
  only to the author's own setup, which would have created an oddly-named
  folder in a stranger's mailbox.
- README rewritten around the actual design claim: the token carries
  `Mail.ReadWrite` and never `Mail.Send`, so sending is absent rather than
  merely disallowed. Setup now leads with registering your own Entra app,
  because there is no shared app registration.

### Earlier, unreleased

- Split sign-in into `iris_login` / `iris_login_finish` so the device-code flow
  returns its URL immediately instead of blocking.
- `iris_auth_status` reads identity from the MSAL account and probes Graph
  in-scope, rather than calling `/me`.
- Fixed bare strings passed as `to`/`cc`/`bcc` being iterated character by
  character. MCP clients were unaffected — the schema forces arrays — but
  direct callers were not.
- `iris_update_draft` and `iris_delete_draft` exercised against Graph for the
  first time; full create/update/list/delete cycle verified.
