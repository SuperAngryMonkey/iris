# iris — Handoff

> **Read this first.** Single pickup point for the draft-only M365 mail MCP.
> Just continue the work — no re-introduction needed.

---

## TL;DR — state in five lines
1. iris is **built, registered, signed in, and working end to end.**
2. It composes into the **Cyrano** mail folder. It **cannot send** — no Mail.Send scope.
3. A real draft to dean@iothings.ai was created and read back on 2026-07-23. Ghost sent it.
4. **Two bugs are live in the public repo.** `iris_login()` can never succeed.
5. Fix those first. Everything else is polish.

---

## What / where
- **iris = draft-only Microsoft 365 mail MCP.** Writes into Outlook, stops there.
  A human reads the draft and presses Send.
- Local: `~/Projects/iris` on Mac-studio. Public: github.com/SuperAngryMonkey/iris (MIT).
- Registered in Claude Desktop as `iris`, alongside christian / ferryman / tupperware.
- Named for Iris, the other messenger of the gods — sibling to [hermes], ferryman, obol, minos.

## Status: WORKING
Verified on 2026-07-23 by an actual draft appearing in the mailbox, not by the
server starting cleanly:
- `iris_create_draft(...)` -> created in **Cyrano** (folder auto-created on first use)
- `iris_list_drafts()` -> read it back
- Token carries `Mail.ReadWrite openid profile email`. **No Mail.Send.**

## Entra registration — DONE, do not redo
| item | value |
|------|-------|
| App name | `iris`, single tenant, 800 Pound Gorilla Inc. |
| Client ID | `cf1473d7-9c86-4833-9d88-d9f91c120546` |
| Tenant ID | `cc06d355-c099-4a61-8aae-61973e4eb27e` |
| Client secret | **none, deliberately** — public client, device code |
| Allow public client flows | Enabled |
| Graph permissions | `Mail.ReadWrite` (Delegated) + default `User.Read` |

Neither ID is a secret. The absence of a secret, and of `Mail.Send`, is the design.

## Claude Desktop config — DONE
Already patched into `claude_desktop_config.json` (backup at
`claude_desktop_config.json.bak-iris`):

    "iris": {
      "command": "/Users/<you>/Projects/iris/.venv/bin/python",
      "args": ["/Users/<you>/Projects/iris/server.py"],
      "env": {
        "IRIS_CLIENT_ID": "cf1473d7-9c86-4833-9d88-d9f91c120546",
        "IRIS_TENANT_ID": "cc06d355-c099-4a61-8aae-61973e4eb27e",
        "IRIS_DRAFT_FOLDER": "Cyrano"
      }
    }

Token cache lives at `.token_cache.json` (mode 600, gitignored) and renews
silently until it lapses — roughly 90 days idle, or on a password change or
Conditional Access shift.

---

## KNOWN BUGS — start here

### 1. `iris_login()` cannot work
It calls `initiate_device_flow()` and then immediately
`acquire_token_by_device_flow()`, which **blocks until the user authenticates**.
The `user_code` is captured but never returned until after that call finishes —
so the human never sees the code they are supposed to enter, and the flow times
out after ~15 minutes.

This is public. The README tells people to call `iris_login()` as setup step 4.
Anyone who clones the repo hits a dead end at the first step.

**Fix:** split into two tools sharing a module-level flow variable —
`iris_login_start()` initiates and returns the verification URL + code
immediately; `iris_login_finish()` performs the blocking exchange and writes
the cache.

**Workaround used to sign in the first time:** a two-step script run through
christian that writes to the same `.token_cache.json` the server reads. See
`docs/AS-BUILT.md`.

### 2. `iris_auth_status()` returns 403
It calls Graph `/me`, which requires `User.Read`. The token only requests
`Mail.ReadWrite`, so Graph replies `Authorization_RequestDenied`. Sign-in is
fine; the status tool is wrong.

**Fix:** drop the `/me` call and read the username from the MSAL account object
(`app.get_accounts()[0]["username"]`). Preferable to adding `User.Read` to
SCOPES — keeping the grant minimal is the entire point of this project.

Until fixed, use `iris_list_drafts()` as the health check.

---

## Tools
| tool | what it does |
|------|--------------|
| `iris_login()` | **BROKEN** — see above |
| `iris_auth_status()` | **BROKEN (403)** — see above |
| `iris_create_draft(to, subject, body, cc, bcc, html, reply_to_message_id)` | works; writes to Cyrano, does not send |
| `iris_list_drafts(limit)` | works |
| `iris_update_draft(draft_id, ...)` | untested against Graph |
| `iris_delete_draft(draft_id, confirm)` | untested; needs confirm=true |

## Where drafts land
Top-level folder named by `IRIS_DRAFT_FOLDER` (currently `Cyrano`), created on
first use. Empty string falls back to Drafts.

They are genuine drafts and Outlook sends them normally, but they **do not
appear in the Drafts view** — look in the folder.

Replies are special: Graph `createReply` always creates in Drafts, so iris moves
the message afterwards, and **a move assigns a new message id**. The returned id
will not match the one createReply produced.

## Containment
- **No send capability** — `Mail.ReadWrite` only. Structural, not a rule.
- `recipients.allow` — address/domain allowlist; empty or absent permits all.
- `audit.log` — every draft, update, delete, login.
- Kill switch — `touch DISABLED`, or `IRIS_DISABLED=1`.
- Confirm gate — deletion requires `confirm=true`, set only on explicit human ok.

## Next actions, in order
1. **Fix `iris_login()`** (split start/finish). Public repo, first-step blocker.
2. **Fix `iris_auth_status()`** (MSAL account, not Graph `/me`).
3. Update README with a Known Issues section — currently it documents a broken
   setup path with no warning.
4. Test `iris_update_draft` and `iris_delete_draft` against Graph. Never run.
5. Decide the LICENSE copyright holder: it currently reads James B Smith III
   personally, but the Entra app sits under 800 Pound Gorilla Inc.
6. Optional: attachments, shared/delegated mailboxes, folder nesting via
   `parentFolderId`.

## Repo map
    HANDOFF.md            <- you are here
    README.md             public-facing; needs a Known Issues section
    LICENSE               MIT, 2026 James B Smith III
    server.py             the whole server, ~441 lines
    requirements.txt      mcp, msal, requests
    recipients.allow      allowlist, currently permissive
    docs/AS-BUILT.md      what actually ran, and the traps hit on the way
    patch_iris.py         one-shot folder migration, applied, gitignored
    server.py.orig        pre-folder snapshot, gitignored

## Gotchas
- macOS system `python3` is **3.9.6** and cannot install `mcp` (needs 3.10+).
  Use `/opt/homebrew/bin/python3.14`, same interpreter christian runs on.
  Rebuild with `python3.14 -m venv --clear .venv` — `--clear` wipes in place and
  avoids a recursive force-delete, which christian's gate refuses without
  explicit human approval.
- christian matches dangerous-command patterns against the **whole command
  string, heredoc body included** — a document that merely quotes a destructive
  command trips the gate even though nothing executes.
- Entra's new permission picker: clicking a permission group's expand chevron
  silently closes the whole panel and loses the selection. Filter, click
  "expand all", then tick the exact child row.
- Verify by checking a **draft actually arrived**, never by checking the server
  started. "It loaded" is not "it works" — that is how both bugs above survived
  to first real use.
