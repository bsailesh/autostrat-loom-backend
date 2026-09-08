# Claude Code Briefing — Pre-Phase 6 Addendum: Signup Allowlist

## Context

Phase 5 (frontend) is built and merged. Before Phase 6 (deployment), we need a
simple gate on new signups — there's no billing yet, and deploying without any
access control means anyone who finds the signup page can create an account and
trigger real, paid API usage with no limit. This is deliberately the simplest
possible version, not a real invite-token system — that can come later alongside
billing.

This is small and additive. Do not modify anything else in the existing signup,
login, or tenant-creation logic beyond what's described below.

## Important: don't affect existing accounts

Any users/tenants already created (including whatever test account was used to
verify Phase 5) must keep working exactly as before. This allowlist check only
applies to NEW signup attempts going forward — it is not a retroactive filter on
who's already in the database.

## What to build

### 1. New table: `signup_allowlist`
- email (unique, store lowercased for case-insensitive matching), added_at.

### 2. Modify the signup endpoint
- Before creating a tenant and user, check whether the submitted email exists in
  `signup_allowlist` (case-insensitive).
- If not present: reject with 403 and a clear message, e.g. "Signups are
  currently invite-only." Do not create a tenant or user.
- If present: proceed exactly as signup already works today.

### 3. A way for me to add emails to the allowlist
- This does not need an admin UI or an authenticated API endpoint — a simple
  command-line script (e.g. `python manage.py add_to_allowlist someone@email.com`)
  is enough. I'm the only person who needs to manage this, and building a full
  admin interface for a stopgap measure isn't worth it. Use your judgment on the
  exact mechanism, but it must be something I can run myself without needing to
  write code or redeploy.

### 4. Small frontend update
- On the signup page, if the API returns the allowlist rejection, show a clear,
  friendly message — something like "Signups are currently invite-only. Contact
  us for access." — not a raw error or a generic failure message.

## Explicit non-goals

- No invite tokens, no expiring links — plain allowlist only.
- No admin UI for managing the list.
- No changes to the existing per-tenant invite flow (adding a second user to an
  *existing* tenant) — that already works and is untouched by this. This
  addendum is specifically about gating brand-new signups/tenant creation.
- No deployment — this still runs locally until Phase 6.

## Success criteria

1. An email NOT on the allowlist attempting signup is rejected with a clear
   message, and no tenant or user is created.
2. An email on the allowlist can sign up exactly as before.
3. I have a working way to add an email to the allowlist myself, without writing
   code.
4. The signup page shows the friendly rejection message, not a raw error.
5. Existing accounts created before this change still log in and work normally.
