# iris — Handoff

> Draft-only Microsoft 365 mail MCP. Composes into a dedicated mail folder
> (default **Cyrano**). A human reads it and presses Send. iris cannot send.
> By design.

## Why draft-only
The app requests **`Mail.ReadWrite` and nothing else**. `Mail.Send` is
deliberately absent, so the token is *structurally incapable* of putting mail
in flight. This is not a guardrail that can be argued around or bypassed by a
bug, a loop, or a bad instruction — the capability simply is not in the grant.

## Status
- Code written, deps installed, imports clean. **Never yet run against Graph.**
- Blocked on: Entra app registration (needs a CLIENT_ID), then `iris_login()`.

## One-time setup in Entra ID
1. Entra ID -> App registrations -> New registration. Single tenant is fine.
   Name it `iris`. Copy the **Application (client) ID** and **Directory
   (tenant) ID**.
2. Authentication -> Add a platform -> Mobile and desktop applications ->
   tick `https://login.microsoftonline.com/common/oauth2/nativeclient`.
   Then set **Allow public client flows = Yes**. (Device code needs this.)
3. API permissions -> Add -> Microsoft Graph -> **Delegated** -> `Mail.ReadWrite`.
   **Do NOT add Mail.Send.** That omission is the safety property.
   No admin consent needed for a delegated Mail.ReadWrite on your own mailbox.
4. No client secret. Public client, device code flow, nothing sensitive on disk
   except the token cache.

## Wire into Claude Desktop
`~/Library/Application Support/Claude/claude_desktop_config.json`:

    "iris": {
      "command": "/Users/jamessmith/Projects/iris/.venv/bin/python",
      "args": ["/Users/jamessmith/Projects/iris/server.py"],
      "env": {
        "IRIS_CLIENT_ID": "<application client id>",
        "IRIS_TENANT_ID": "<directory tenant id>",
        "IRIS_DRAFT_FOLDER": "Cyrano"
      }
    }

Restart Claude Desktop, then call `iris_login()`. It returns a URL and a code;
enter them in a browser once. The refresh token is cached at
`.token_cache.json` (mode 600, gitignored) and renews silently until it lapses
(~90 days idle, or on password change / CA policy shift).

## Where drafts land
Drafts are staged in a top-level mail folder named by `IRIS_DRAFT_FOLDER`
(default `Cyrano`), created automatically on first use. Set it to an empty
string to fall back to the normal Drafts folder.

They are still real drafts and Outlook opens and sends them normally, but
they will **not** appear in the Drafts view — look in the Cyrano folder.

For replies, Graph `createReply` always lands the draft in Drafts first, so
iris moves it afterwards. A move assigns a **new message id**, which is why
the returned id differs from the one createReply produced.

## Tools
| tool | what it does |
|------|--------------|
| `iris_login()` | device-code sign-in, one time |
| `iris_auth_status()` | who we are, what scopes, allowlist state |
| `iris_create_draft(to, subject, body, cc, bcc, html, reply_to_message_id)` | writes to Drafts, does not send |
| `iris_list_drafts(limit)` | what is sitting in Drafts |
| `iris_update_draft(draft_id, ...)` | revise in place, only fields passed |
| `iris_delete_draft(draft_id, confirm)` | destructive, needs confirm=true |

`reply_to_message_id` uses Graph `createReply`, so replies thread properly.

## Containment
- **No send capability** — `Mail.ReadWrite` only.
- **`recipients.allow`** — one address or domain per line. If the file is empty
  or absent, all recipients are permitted. Populate it to restrict.
- **`audit.log`** — every draft, update, delete, and login appended.
- **Kill switch** — `touch DISABLED` (or `IRIS_DISABLED=1`) blocks every tool.
- **Confirm gate** — deletion requires `confirm=true`, set only after a human
  explicitly approves that specific deletion.

## Environment gotchas
macOS system `python3` is **3.9.6** and cannot install `mcp` (needs 3.10+).
Use `/opt/homebrew/bin/python3.14`, the same interpreter christian runs on.
Rebuild the venv with `python3.14 -m venv --clear .venv` — the `--clear` flag
wipes it in place and avoids a recursive force-delete, which christian's
dangerous-pattern gate refuses without explicit human approval.

Note also that christian matches those patterns against the **whole command
string**, heredoc body included — so writing a document that merely quotes a
destructive command will trip the gate even though nothing is executed.

## Not done
- Attachments (Graph supports <3MB inline, upload session beyond).
- Shared / delegated mailboxes — this is `/me` only.
- `git init` + commit. Repo is uncommitted.
