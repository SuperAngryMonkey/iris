# Changelog

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
