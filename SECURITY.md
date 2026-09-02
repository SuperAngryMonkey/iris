# Security

## The property this project claims

**By default**, iris requests one delegated Microsoft Graph scope:
`Mail.ReadWrite`. It does not request `Mail.Send`. The access token it holds
therefore has no capability to transmit a message, and Graph rejects any attempt
to do so.

By default this is not a check in the code. There is no `if` statement to bypass,
no confirmation prompt to talk past, and no prompt injection that reaches it. The
boundary is enforced by Microsoft against the consent you granted, and it holds
even if this program is wrong or compromised.

## When you enable sending

Setting `IRIS_ENABLE_SEND=1` — together with adding `Mail.Send` to the app
registration and re-consenting — deliberately gives up the property above. The
token then carries `Mail.Send`, so Microsoft will no longer reject a send. What
stands between an agent and an outgoing message becomes a **guardrail in this
code**: `iris_send_draft` refuses without a per-call `confirm=true` and re-checks
the recipient allowlist. That is a real line of defence, but it is code — it can
have bugs and be talked past, unlike the default, which cannot. Enable sending
only where that weaker guarantee is acceptable, and keep a human on `confirm`.

## Verify it yourself

Do not take the README's word for it.

1. On the Entra app registration you created, open **API permissions**. For the
   default draft-only posture the list should show `Mail.ReadWrite` (Delegated)
   and nothing else beyond the default `User.Read`. If `Mail.Send` appears and
   you did **not** intend to enable sending, the no-send property is void —
   remove it and re-consent.
2. Call `iris_auth_status`. It reports the scopes actually granted to the live
   token and whether `can_send` is true.
3. Read the source: with send disabled, `SCOPES` is `["Mail.ReadWrite"]` and the
   `iris_send_draft` tool is not even registered — it lives behind
   `if ENABLE_SEND:`. `Mail.Send` is added to `SCOPES`, and the tool defined,
   only when `IRIS_ENABLE_SEND=1`.

## What iris CAN do, which matters just as much

`Mail.ReadWrite` is a broad scope. Within your mailbox, iris can:

- **read every message you have**, including anything an agent asks it to look at
- create, modify and delete drafts
- delete mail

"Cannot send" is a narrower promise than "safe". An agent driving iris can read
your entire mailbox, and anything it reads can end up in the context of a model
you do not control. If that is unacceptable for your mail, iris is not the right
tool, and no configuration of it will make it so.

There is no scope narrower than `Mail.ReadWrite` that still permits creating a
draft. That is a Graph limitation, not a design choice.

## Blast radius

- Delegated **public client** auth via MSAL device code. No client secret exists
  anywhere in this project.
- No admin consent, so iris cannot reach any mailbox but the signed-in user's.
  There is no `/users/{id}` access, no application permissions, no shared or
  delegated mailbox support.
- The token cache is written beside the server at mode 600. Anyone with read
  access to that file or to the machine has your mailbox until the token
  expires. Treat it as a credential.
- The audit log records every tool call. It contains recipient addresses and
  subjects.

## Controls

- **Recipient allowlist** — `recipients.allow`. If absent or empty, all
  recipients are permitted. This is a convenience, not a security boundary: it
  is enforced in this code, so it is exactly the kind of check that can be
  bypassed by a bug.
- **Kill switch** — a `DISABLED` file beside the server, or `IRIS_DISABLED=1`,
  makes every tool refuse.

## Reporting

Open an issue at https://github.com/SuperAngryMonkey/iris/issues. If the finding
would let iris send mail, reach a mailbox other than the signed-in user's, or
leak the token cache, please mark it clearly so it is handled first.
