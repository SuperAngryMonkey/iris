# iris-worker

**iris** as a Cloudflare Python Worker — a draft-and-send Microsoft 365 agent for a single **bot mailbox**, reachable over MCP (streamable HTTP).

Sibling of the stdio [`iris`](https://github.com/SuperAngryMonkey/iris) package (PyPI `iris-mcp`). Same intent — an AI agent operating one mailbox safely — but this runtime lives 100% in Cloudflare and speaks MCP over HTTP, so a sandboxed agent (e.g. a hosted chatbot) can reach it with only a URL + bearer.

## One-click deploy

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/SuperAngryMonkey/iris/tree/main/worker)

Forks the repo, provisions a KV namespace, and prompts for the four values in
`.dev.vars.example` (`IRIS_CLIENT_ID`, `IRIS_TENANT_ID`, `IRIS_HTTP_TOKEN`,
`IRIS_ENC_KEY`). You still need an Entra app and a licensed bot mailbox first
(Setup steps 1-2) and a one-time sign-in after (step 7).

> This is a **Python** Worker whose dependencies are vendored by `pywrangler`. If
> the one-click build fails, set the deploy command to `uv run pywrangler deploy`
> in the deploy form, or use the manual **Setup** steps below — those always work.

## Architecture

```
Agent (MCP client)
  |  Authorization: Bearer <IRIS_HTTP_TOKEN>
  v
your worker  (Cloudflare Python Worker, e.g. iris.example.com/mcp)
  - bearer gate (fail-closed, constant-time)
  - device-code + refresh OAuth via httpx (Worker-native, no MSAL)
  - refresh token encrypted AES-GCM in Workers KV
  - /me only, one mailbox
  v
Microsoft Graph  ->  the bot mailbox
```

- **No Microsoft credential ever reaches the agent.** The agent holds only the worker bearer. The mailbox refresh token is sealed (AES-GCM) in KV; the key is a Worker secret.
- **One mailbox, `/me` only.** No mailbox switching, no access to other users.

## Tools (10)

- `iris_auth_status` — who is signed in, scopes, Graph reachability
- `iris_login` / `iris_login_finish` — one-time device-code sign-in for the bot mailbox
- `iris_list_folders` — list mail folders
- `iris_create_draft` — compose an UNSENT draft (optionally a threaded reply) into a folder
- `iris_list_drafts` — list drafts in a folder
- `iris_update_draft` — revise a draft in place
- `iris_delete_draft` — move a draft to Deleted Items (confirm=true)
- `iris_send_draft` — send an existing draft as the bot (confirm=true)
- `iris_audit_tail` — recent send-audit entries

## Send safety model

No human is on the Send button in a sandbox, so the rails are programmatic:

- `confirm=true` required on every send and delete
- recipient allowlist — `IRIS_ALLOWLIST` (comma-separated addresses/domains); empty = unrestricted
- audit log in KV — every send recorded; read with `iris_audit_tail`
- kill switch — set `IRIS_DISABLED` to any value and all sends refuse (no redeploy)
- send is two-step: `iris_create_draft` -> inspect -> `iris_send_draft` (drafts are real, reviewable objects)

## Setup

### 1. Entra app registration
- Azure Portal -> Microsoft Entra ID -> App registrations -> New registration (single tenant is fine).
- Authentication -> Advanced settings -> **Allow public client flows: Yes**.
- API permissions -> add **delegated** Microsoft Graph permissions `Mail.ReadWrite`, `Mail.Send`, `User.Read` -> **Grant admin consent**.
- Record the **Application (client) ID** and **Directory (tenant) ID**.

### 2. Bot mailbox
Create or designate a **licensed** Exchange Online mailbox for the bot. iris is `/me` only — it operates whatever account signs in. An unlicensed / shared mailbox will not work.

### 3. KV namespace
```
npx wrangler kv namespace create iris-token-cache
```
Copy the returned namespace id.

### 4. Config
```
cp wrangler.jsonc.example wrangler.jsonc
```
Fill in `IRIS_CLIENT_ID`, `IRIS_TENANT_ID`, and the KV `id`. `wrangler.jsonc` is git-ignored so your IDs never enter the repo. (Optional: add a `routes` entry for a custom domain, e.g. `"routes": [{ "pattern": "iris.example.com", "custom_domain": true }]`.)

### 5. Secrets
```
# bearer the agent presents
printf '%s' "$(openssl rand -base64 32)" | npx wrangler secret put IRIS_HTTP_TOKEN
# 32-byte AES-GCM key for the KV token cache
printf '%s' "$(openssl rand -base64 32)" | npx wrangler secret put IRIS_ENC_KEY
```
Keep copies in a password manager. Losing `IRIS_ENC_KEY` just means re-running the sign-in.

### 6. Deploy
```
CI=1 uv run pywrangler deploy
```

### 7. First-run sign-in (one-time)
Point an MCP client at the worker (see `client.py`) and:
1. `iris_login` -> returns a URL + device code
2. open the URL, enter the code, sign in **as the bot mailbox** (approve Send mail)
3. `iris_login_finish` -> refresh token stored encrypted in KV
4. `iris_auth_status` -> confirms `can_send: true`

Re-run only if the refresh token lapses or scopes change.

## Config reference

Vars (`wrangler.jsonc`, not secret): `IRIS_CLIENT_ID`, `IRIS_TENANT_ID`, optional `IRIS_DRAFT_FOLDER` (default `AI Drafts`), `IRIS_ALLOWLIST`, `IRIS_DISABLED`.

Secrets (`wrangler secret put`, never committed): `IRIS_HTTP_TOKEN`, `IRIS_ENC_KEY`.

KV: binding `IRIS_KV` — stores `refresh_token` (encrypted), `pending_device_code`, `audit_log`.

## Register with an agent

```json
{
  "mcpServers": {
    "iris": {
      "url": "https://YOUR-WORKER/mcp",
      "headers": { "Authorization": "Bearer <IRIS_HTTP_TOKEN>" }
    }
  }
}
```

## Rotating the bearer

```
printf '%s' "<new token>" | npx wrangler secret put IRIS_HTTP_TOKEN
```
Update the agent header; the old token dies immediately.

## Local test client

```
IRIS_URL=https://YOUR-WORKER/mcp IRIS_BEARER=<token> python client.py __list__
IRIS_URL=https://YOUR-WORKER/mcp IRIS_BEARER=<token> python client.py iris_login
```

---
800 Pound Gorilla Inc. - MIT
