# Changelog

All notable changes to iris-worker (the Cloudflare Python Worker port of iris).

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
