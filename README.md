# iris

**A Microsoft 365 mail server for AI agents that cannot send email.**

Not "will not". Cannot. iris requests the delegated Graph scope `Mail.ReadWrite`
and never `Mail.Send`. The access token it holds has no capability to transmit a
message, so no prompt, no jailbreak and no bug in this code can make one go out.
It writes drafts into a folder in your mailbox. You open Outlook and press Send.

That is the whole design. Everything else is detail.

---

## Why this shape

The usual worry about giving an agent your mailbox is that it will send
something you did not sanction — to the wrong person, with the wrong tone, or
because someone talked it into doing so. The common answer is a confirmation
prompt, which is a guardrail: code that asks permission, and code can be
bypassed.

iris removes the capability instead. Microsoft Graph will reject a send attempt
made with this token, because the consent screen you approved never included
that permission. The security boundary is Microsoft's, not this program's, and
it holds even if this program is wrong.

The trade is real: a human is in the loop on every message, by construction. If
you want autonomous sending, iris is the wrong tool.

## Install

```bash
uvx iris-mcp        # run without installing
pip install iris-mcp
```

Python 3.10+.

## Setup

**You must register your own Entra application.** There is no shared app
registration and no hosted service — iris talks directly from your machine to
your tenant. This is deliberate: a shared app would mean trusting someone
else's client ID with access to your mail.

1. Entra admin centre → **App registrations** → **New registration**. Single
   tenant is fine. No redirect URI needed.
2. **Authentication** → Settings → enable **Allow public client flows**. Device
   code sign-in needs this. No client secret is used anywhere.
3. **API permissions** → Microsoft Graph → **Delegated** → add
   **`Mail.ReadWrite`**. Add nothing else. Do not add `Mail.Send` — if it is
   present, the guarantee above is void.
4. Copy the **Application (client) ID** and **Directory (tenant) ID**. Neither
   is a secret.

Then add iris to your MCP client:

```json
{
  "mcpServers": {
    "iris": {
      "command": "uvx",
      "args": ["iris-mcp"],
      "env": {
        "IRIS_CLIENT_ID": "<application client id>",
        "IRIS_TENANT_ID": "<directory tenant id>"
      }
    }
  }
}
```

Sign in once: call `iris_login`, open the URL, enter the code, then call
`iris_login_finish`. The token cache is written next to the server, mode 600.

## Tools

| Tool | What it does |
|---|---|
| `iris_login` | Starts device-code sign-in, returns a URL and a code |
| `iris_login_finish` | Completes sign-in; safe to call repeatedly while you type the code |
| `iris_auth_status` | Who is signed in, which scopes, and whether Graph is reachable |
| `iris_create_draft` | Writes a draft (to/cc/bcc, subject, body or HTML, optional reply-to) |
| `iris_list_drafts` | Lists what is waiting in the draft folder |
| `iris_update_draft` | Revises a draft in place |
| `iris_delete_draft` | Deletes a draft; requires `confirm=true` |

## Where drafts go

Into a dedicated top-level mail folder, `AI Drafts` by default
(`IRIS_DRAFT_FOLDER`). It is created on first use. Set the variable to an empty
string to use the normal Drafts folder instead.

These are real drafts and Outlook sends them normally — but because they live in
their own folder, they do **not** appear in the Drafts view. That is the point:
agent-written mail sits somewhere you have to go and look, rather than mixed in
with your own half-finished messages.

One wrinkle worth knowing: Graph's `createReply` always lands a reply in Drafts
first, so iris moves it afterwards, and a move assigns a new message id.

## Other controls

- **Recipient allowlist** — `recipients.allow`, one address or domain per line.
  Absent or empty means all recipients are permitted. Point `IRIS_ALLOWLIST`
  elsewhere if you prefer.
- **Kill switch** — create a `DISABLED` file beside the server, or set
  `IRIS_DISABLED=1`, and every tool refuses.
- **Audit log** — every call is appended to `audit.log` (`IRIS_AUDIT_LOG`).

## Limits

No attachments. No shared or delegated mailboxes — `/me` only. No folder nesting
via `parentFolderId`. Sign-in is delegated device-code as a public client, so
the blast radius is exactly one mailbox: yours.

## Security

The no-send guarantee, how to verify it yourself, and — just as important — what
iris *can* reach with `Mail.ReadWrite`: see [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).

<!-- mcp-name: io.github.SuperAngryMonkey/iris -->
