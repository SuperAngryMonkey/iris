# Changelog

All notable changes to iris-worker (the Cloudflare Python Worker port of iris).

## 0.5.0

- Read tools, matching iris 0.3.0 (stdio): `iris_list_messages`,
  `iris_search_messages`, `iris_get_message`, `iris_get_thread`. Read-only (a GET
  never flips `isRead`; the read folder resolver never creates folders); message
  content is flagged to the agent as untrusted data.
- `IRIS_DISABLE_READ=1` unregisters them. Reads are not written to the KV audit
  log (it stays a send log, and KV write quotas are small).
- 14 tools total.

## 0.4.1

- Added a Deploy to Cloudflare one-click template: a public `wrangler.jsonc`
  (KV auto-provisioned per deployer, no instance IDs), `.dev.vars.example` for the
  four prompted secrets, and a deploy button in the README. Packaging and docs
  only — `src/entry.py` is byte-for-byte unchanged from 0.4.0.

## 0.4.0
- Add `Mail.Send` scope and `iris_send_draft` — send an existing draft **as the bot mailbox**; `confirm=true` required per send.
- Add `iris_audit_tail` and a KV audit log recording every send.
- Add `IRIS_DISABLED` kill switch; honor `IRIS_ALLOWLIST` recipient allowlist on send.
- `iris_auth_status` now reports `can_send`.
- 10 tools total.

## 0.3.0
- Initial Cloudflare Python Worker port of iris — **draft-only** (8 tools).
- Worker-native device-code + refresh OAuth via httpx (no MSAL); refresh token AES-GCM encrypted in Workers KV.
- Bearer-gated MCP over streamable HTTP; fresh app per request (works around StreamableHTTPSessionManager single-run).
- Optional custom domain support.
