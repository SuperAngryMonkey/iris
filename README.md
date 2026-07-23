# iris

A **draft-only** Microsoft 365 mail MCP server. It composes email into a
dedicated folder in your Outlook mailbox and stops. A human opens it, reads
it, and presses Send.

Named for Iris, messenger of the gods — she carries the message; she does not
decide to deliver it.

## Why draft-only

Letting a language model send email on your behalf means a bug, a runaway
loop, or a badly-worded instruction can put mail in front of a client before
anyone notices. The usual mitigation is a confirmation prompt, which is a rule
the model is asked to follow.

iris does not rely on a rule. It requests the delegated Graph scope
**`Mail.ReadWrite` and nothing else**. `Mail.Send` is never granted, so the
access token is *structurally incapable* of sending mail. There is no code
path, no flag, and no prompt that changes that — the capability simply is not
in the grant.

Review stays where it belongs: in your mail client, on your screen, under your
thumb.

## Requirements

- Python 3.10+ (the `mcp` package will not install on older interpreters;
  macOS system Python is 3.9 and will not work)
- A Microsoft 365 mailbox
- An Entra ID app registration (below) — no client secret, no admin consent

## Setup

### 1. Register the application

In **Entra ID → App registrations → New registration**:

- Name it `iris`. Single tenant is fine.
- Copy the **Application (client) ID** and **Directory (tenant) ID**.

Under **Authentication**:

- Add a platform → *Mobile and desktop applications*
- Tick `https://login.microsoftonline.com/common/oauth2/nativeclient`
- Set **Allow public client flows = Yes** (device code requires this)

Under **API permissions**:

- Add → Microsoft Graph → **Delegated** → `Mail.ReadWrite`
- **Do not add `Mail.Send`.** Its absence is the entire security model.

No client secret is needed. This is a public client using the device code
flow, so nothing sensitive is stored on disk except the cached refresh token.

### 2. Install

```sh
git clone git@github.com:SuperAngryMonkey/iris.git
cd iris
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Register with your MCP client

For Claude Desktop, in `claude_desktop_config.json`:

```json
"iris": {
  "command": "/absolute/path/to/iris/.venv/bin/python",
  "args": ["/absolute/path/to/iris/server.py"],
  "env": {
    "IRIS_CLIENT_ID": "<application client id>",
    "IRIS_TENANT_ID": "<directory tenant id>",
    "IRIS_DRAFT_FOLDER": "Cyrano"
  }
}
```

Paths must be absolute — `~` is not expanded.

### 4. Sign in

Restart the client and call `iris_login()`. It returns a URL and a short code
to enter in a browser, once. The refresh token is cached at `.token_cache.json`
(mode 600, gitignored) and renews silently until it lapses — roughly 90 days
idle, or on a password change or Conditional Access policy shift.

## Tools

| Tool | Description |
|------|-------------|
| `iris_login()` | Device-code sign-in. One time. |
| `iris_auth_status()` | Signed-in identity, granted scopes, allowlist state |
| `iris_create_draft(to, subject, body, cc, bcc, html, reply_to_message_id)` | Compose into the staging folder. Does not send. |
| `iris_list_drafts(limit)` | What is waiting in the staging folder |
| `iris_update_draft(draft_id, ...)` | Revise in place; only fields passed are changed |
| `iris_delete_draft(draft_id, confirm)` | Destructive; requires `confirm=true` |

Passing `reply_to_message_id` uses Graph's `createReply`, so replies thread
correctly rather than arriving as orphaned messages.

## Where drafts land

Drafts are staged in a top-level mail folder named by `IRIS_DRAFT_FOLDER`,
created automatically on first use. Set it to an empty string to use the
normal Drafts folder instead.

Messages in a custom folder are still genuine drafts and Outlook opens and
sends them normally — but they do **not** appear in the Drafts view. Look in
the folder.

Replies are a special case: Graph's `createReply` always creates the draft in
Drafts, so iris moves it afterwards. A move assigns a **new message id**, so
the id returned will not match the one `createReply` produced.

## Containment

Beyond the missing send scope:

- **`recipients.allow`** — one address or domain per line. Drafts addressed
  outside the list are refused. An empty or absent file permits all.
- **`audit.log`** — every draft, update, deletion, and sign-in is recorded.
- **Kill switch** — `touch DISABLED`, or set `IRIS_DISABLED=1`, to block every
  tool without unregistering the server.
- **Confirm gate** — deletion requires an explicit `confirm=true`, intended to
  be set only after a human approves that specific deletion.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `IRIS_CLIENT_ID` | — | Entra application (client) ID. Required. |
| `IRIS_TENANT_ID` | `organizations` | Directory (tenant) ID |
| `IRIS_DRAFT_FOLDER` | `Cyrano` | Staging folder; empty string uses Drafts |
| `IRIS_ALLOWLIST` | `./recipients.allow` | Recipient allowlist path |
| `IRIS_AUDIT_LOG` | `./audit.log` | Audit log path |
| `IRIS_TOKEN_CACHE` | `./.token_cache.json` | MSAL token cache path |
| `IRIS_DISABLED` | unset | Set to `1` to disable every tool |

## Not implemented

- Attachments (Graph supports inline under 3MB, upload sessions beyond)
- Shared and delegated mailboxes — this operates on `/me` only
- Retention or cleanup of the staging folder

## License

MIT. See [LICENSE](LICENSE). Use it, fork it, ship it.

## Status

Working, and deliberately small. Treat the first successful draft appearing in
your mailbox as the real test — a server that starts cleanly has proven
nothing.
