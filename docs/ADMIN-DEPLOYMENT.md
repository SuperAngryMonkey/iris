# iris — Administrator Deployment Guide

How a Microsoft 365 administrator authorizes iris for other people in a tenant —
for example, rolling it out to staff in an organization whose mailboxes live in a
different tenant from the one where you first set up iris.

---

## Read this first: what you are and are NOT authorizing

iris uses **delegated** Microsoft Graph permissions with **device-code sign-in**.
That means:

- **Every user signs in as themselves.** Each person's iris gets a token for
  *their own* mailbox and can only ever touch *their own* mail. There is no
  service account and no shared mailbox access.
- **Admin authorization here does two things only:** (1) it *pre-consents* the
  delegated permission for the tenant so individual users are not each shown a
  consent prompt, and (2) it lets you *restrict* which users are allowed to use
  the app at all.
- **It does NOT create one instance that can read everyone's mail.** That would
  require *application* permissions (e.g. `Mail.ReadWrite` as an application
  role) plus admin consent — a far more powerful and dangerous design that iris
  deliberately does not use. If anyone proposes granting iris application
  permissions, stop: that is not how iris is meant to run.

So the blast radius of this deployment is exactly "each authorized user, their
own mailbox" — no more.

---

## Prerequisites

- You are a **Global Administrator** (or **Application Administrator** +
  **Cloud Application Administrator**) in the target tenant — the one that owns
  the mailboxes you are deploying to.
- Decide up front: **draft-only**, or **draft + send**? Draft-only is the safe
  default and needs one permission. Send needs a second permission and changes
  the security posture (see the send note at the end).
- **Register iris in the tenant that owns the mailboxes.** If you already run
  iris in another tenant, register a *separate* app in the new tenant rather than
  reusing the existing one — keep each tenant's access independent and separately
  revocable.

---

## Step 1 — Register the application (target tenant)

1. Sign in to the **Microsoft Entra admin center** (entra.microsoft.com) in the
   target tenant.
2. **App registrations → New registration.**
3. Name: `iris` (or `iris — <your organization>`).
4. **Supported account types:** *Accounts in this organizational directory only*
   (single tenant).
5. **Redirect URI:** leave blank — device-code flow needs none.
6. **Register.** On the overview page, copy the **Application (client) ID** and
   the **Directory (tenant) ID**. Neither is a secret, but keep them handy —
   users will need them.

## Step 2 — Turn on public client flows (required for device-code sign-in)

1. In the app → **Authentication**.
2. Under **Advanced settings**, set **Allow public client flows** to **Yes**.
3. **Save.** (No client secret is created. iris is a public client — it has no
   secret to store or leak.)

## Step 3 — Add the delegated Graph permission

1. In the app → **API permissions → Add a permission → Microsoft Graph →
   Delegated permissions.**
2. Add **`Mail.ReadWrite`**.
3. For **draft-only** (recommended), add nothing else. Add **`Mail.Send`** *only*
   if you intend to let users send from iris (see the send note).
4. Confirm the list shows `Mail.ReadWrite` (Delegated) — and `User.Read` may be
   present by default, which is harmless.

## Step 4 — Grant admin consent (this is the "on behalf of others" part)

1. Still on **API permissions**, click **Grant admin consent for
   \<organization\>** and confirm.
2. The **Status** column should turn to **Granted for \<organization\>**.

That single click pre-consents the delegated scope for the whole tenant, so no
user gets an individual consent prompt when they sign in. It does **not** grant
iris standalone access to anything — a user still has to sign in as themselves
for iris to do anything on their behalf.

## Step 5 (recommended) — Restrict who can use iris

By default any user in the tenant could sign in to the app. To limit it to
specific people:

1. **Entra admin center → Enterprise applications →** find **iris** (it appears
   here automatically after admin consent) → **Properties**.
2. Set **Assignment required?** to **Yes** → **Save.**
3. Go to **Users and groups → Add user/group** and assign the specific people
   (or a security group, e.g. "iris users") who are allowed to use it.

With assignment required, only assigned users can sign in to iris. This is how
you authorize *specific* people rather than the entire tenant. Remove a person
here to cut off just that person.

## Step 6 — Hand the two IDs to each authorized user

Give each authorized user the **Application (client) ID** and **Directory
(tenant) ID** (again, neither is secret). They put them in their MCP client
config:

```json
"iris": {
  "command": "uvx",
  "args": ["iris-mcp"],
  "env": {
    "IRIS_CLIENT_ID": "<the app's application (client) id>",
    "IRIS_TENANT_ID": "<the tenant's directory (tenant) id>"
  }
}
```

Then each user signs in once: run `iris_login`, open the URL, enter the code,
run `iris_login_finish`. Because you granted admin consent in Step 4, they will
**not** see a consent screen — they just authenticate as themselves.

(Each user also needs Python 3.10+ / `uv`. See the project README.)

---

## Enabling send tenant-wide (optional — understand the trade)

Send is off by default, and keeping it off is the safe choice. If the
organization wants users to be able to send from iris:

1. In Step 3, also add **`Mail.Send`** (Delegated), and re-run **Grant admin
   consent** in Step 4.
2. Each user must **also** set `IRIS_ENABLE_SEND=1` in their own config **and**
   re-run `iris_login` to re-consent. Send stays off for anyone who does not opt
   in locally — the tenant permission alone does not turn it on.

Security note: with send off, "iris cannot send" is enforced by Microsoft itself.
With `Mail.Send` granted, that structural guarantee is gone; the only thing left
between an agent and an outgoing message is iris's per-call confirmation prompt —
a guardrail in code, which is weaker. Prefer leaving `Mail.Send` off the app
registration unless you specifically want sending, so it isn't even available
tenant-wide.

---

## Hardening (optional but recommended)

- **Block or scope device-code flow.** Device-code sign-in can be phished
  (an attacker tricks a user into entering a code for the attacker's session).
  Consider a **Conditional Access** policy that blocks the device-code
  authentication flow except for the assigned iris users/group, or requires
  compliant/managed devices.
- **Watch the sign-in logs** for the iris enterprise application periodically
  (Entra → Enterprise applications → iris → Sign-in logs).

## Revoking access

- **Cut off one person:** Enterprise applications → iris → **Users and groups** →
  remove them.
- **Cut off everyone / turn it off:** Enterprise applications → iris →
  **Properties → Enabled for users to sign in? = No**, or delete the app
  registration entirely. Either immediately stops new sign-ins; existing cached
  tokens expire on their normal schedule.

---

## Quick checklist

- [ ] App registered in the **target** tenant, single-tenant
- [ ] **Allow public client flows = Yes**
- [ ] Delegated **`Mail.ReadWrite`** added (+ `Mail.Send` only if sending)
- [ ] **Grant admin consent** clicked — status "Granted"
- [ ] **Assignment required = Yes**, specific users/group assigned
- [ ] Client ID + Tenant ID distributed to those users
- [ ] (If sending) users set `IRIS_ENABLE_SEND=1` and re-ran `iris_login`
- [ ] (Recommended) Conditional Access policy scoping device-code flow
