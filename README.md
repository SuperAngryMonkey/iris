# iris

**A Microsoft 365 mail server for AI agents that does not send email — until you decide it should.**

By default iris requests the delegated Graph scope `Mail.ReadWrite` and never
`Mail.Send`. The access token it holds has no capability to transmit a message,
so no prompt, no jailbreak and no bug in this code can make one go out. It writes
drafts into a folder in your mailbox; you open Outlook and press Send.

Sending is an explicit opt-in (`IRIS_ENABLE_SEND=1`) that requires granting the
`Mail.Send` scope and re-consenting — and even then every send is human-confirmed
and allowlist-checked. Leave it off (the default) and the no-send property is
structural, as above. See [Enabling send](#enabling-send).

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

**Python 3.10 or newer.** macOS ships Python 3.9, which is too old — `mcp`
requires 3.10+. Use [`uv`](https://docs.astral.sh/uv/) (it comes with `uvx` and
manages its own Python), or install a current Python with Homebrew
(`brew install python@3.12`). The system `python3` on macOS will not work.

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
   **`Mail.ReadWrite`**. For draft-only use (the default), add nothing else and
   leave `Mail.Send` off — that omission is what makes the no-send property
   structural. Add `Mail.Send` only if you intend to enable sending (see
   [Enabling send](#enabling-send)).
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
        "IRIS_CLIENT_ID": "<application (client) id>",
        "IRIS_TENANT_ID": "<directory (tenant) id>"
      }
    }
  }
}
```

Sign in once: call `iris_login`, open the URL, enter the code, then call
`iris_login_finish`. The token cache is written next to the server, mode 600.

**Deploying to a whole team?** See the [Administrator Deployment
Guide](docs/ADMIN-DEPLOYMENT.md) — authorizing iris across a Microsoft 365 tenant:
admin consent, per-user assignment, and why it stays the delegated model rather
than application permissions.

## Clients

iris is a local **stdio** MCP server: your MCP client launches it as a child
process on the same machine. It works with any client that supports local stdio
servers — Claude Desktop, Cursor, and the **Grok CLI**
(`grok mcp add iris -- uvx iris-mcp`) among them.

It does **not** work with clients that only accept remote MCP connectors over
HTTP. The **Grok app / Grok Bot** is in that category — it takes hosted HTTP
servers, not local stdio ones — so iris cannot attach to it as-is. Bridging iris
to an HTTP transport is possible, but out of scope for this project.

## Tools

| Tool | What it does |
|---|---|
| `iris_login` | Starts device-code sign-in, returns a URL and a code |
| `iris_login_finish` | Completes sign-in; safe to call repeatedly while you type the code |
| `iris_auth_status` | Who is signed in, which scopes, and whether Graph is reachable |
| `iris_list_folders` | Lists your top-level mail folders, so you can pick one for a draft |
| `iris_create_draft` | Writes a draft (to/cc/bcc, subject, body or HTML, optional reply-to, optional `folder`) |
| `iris_list_drafts` | Lists what is waiting in a draft folder (optional `folder`) |
| `iris_update_draft` | Revises a draft in place |
| `iris_delete_draft` | Deletes a draft; requires `confirm=true` |
| `iris_send_draft` | **Only present when `IRIS_ENABLE_SEND=1`.** Sends an existing draft; requires `confirm=true`, re-checks the allowlist |

## Where drafts go

Into a dedicated top-level mail folder, `AI Drafts` by default
(`IRIS_DRAFT_FOLDER`), created on first use. Set the variable to an empty string
to use the normal Drafts folder instead.

You can also choose the folder per draft: pass `folder` to `iris_create_draft`
(and `iris_list_drafts`) to target any folder by name, created on first use if it
does not exist. Pass `""` or `"Drafts"` for the normal Outlook Drafts folder, or
call `iris_list_folders` first to pick from what already exists. Omitting
`folder` uses the `IRIS_DRAFT_FOLDER` default, so nothing changes for existing
setups.

These are real drafts and Outlook sends them normally — but because they live in
their own folder, they do **not** appear in the Drafts view. That is the point:
agent-written mail sits somewhere you have to go and look, rather than mixed in
with your own half-finished messages.

One wrinkle worth knowing: Graph's `createReply` always lands a reply in Drafts
first, so iris moves it afterwards, and a move assigns a new message id.

## Enabling send

Sending is off by default and, by design, takes three deliberate steps — miss any
one and iris still cannot send:

1. In your Entra app registration, add **`Mail.Send`** (Delegated) alongside
   `Mail.ReadWrite`.
2. Set `IRIS_ENABLE_SEND=1` in the server's environment. Only then is `Mail.Send`
   requested and the `iris_send_draft` tool registered at all.
3. Run `iris_login` again to re-consent — the cached token predates the new scope
   and will not carry it until you do.

Then `iris_send_draft(draft_id, confirm=true)` sends an existing draft. It refuses
without `confirm`, re-verifies the message is still an unsent draft, and re-runs
the recipient allowlist before sending. The flow stays compose → review → send;
iris never composes and sends in one shot.

Understand the trade. With send off, "cannot send" is enforced by Microsoft
against your consent and holds even if this code is wrong. With send on, the last
line of defence is a per-call confirmation — a guardrail *in this code*, which is
exactly the kind of check a bug or a cleverly-worded prompt can talk past. Enable
it only where that weaker guarantee is acceptable.

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
