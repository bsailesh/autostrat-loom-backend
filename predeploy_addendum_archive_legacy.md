# Claude Code Briefing — Pre-Deploy Addendum: Archive the Old Dashboard

## Context

This repo contains an older `index.html` with an embedded dashboard for the
original five agents (Prioritize / Discover / Align / Sustain / Brief) —
names retired earlier in this project in favor of Voice of Customer / Market
Insights / Tech & Regulation / Product Sustainment / Strategy Synthesis and
Decision. This old dashboard is not live anywhere today, but it must not be
part of the Phase 6 deploy path — the real product surface is the React app
in `frontend/`.

This is a small, low-risk cleanup task. Move things, don't delete them.

## What to do

1. Move the old `index.html` (and any files that exist *only* to support it —
   for example `seed_data.py`, and the admin-tenant-creation endpoint if it
   has no other caller) into a clearly-named folder such as `legacy/`, out of
   the root of the repo and out of anything Step 10 of the deploy would
   upload.
2. Do not delete anything — this is an archive/move, not a cleanup that
   destroys history. It's still in git history either way, but keep the
   working tree tidy and unambiguous about what's active.
3. Before moving the admin-tenant endpoint (if it's used only by
   `seed_data.py`), check whether anything else in the app calls it. If it's
   only used by the legacy seeding script, it can move with it. If it's used
   elsewhere, leave the endpoint in place and just move the frontend files
   and `seed_data.py`.
4. Update `DEPLOY-LIGHTSAIL.md` and `PRODUCTION-READINESS.md` (item 5 in the
   latter) to remove the "open decision" framing — state plainly that
   `frontend/` (the React app) is the product surface, and the old dashboard
   is archived in `legacy/`, not part of the deploy.

## Non-goals

- No deletion of the old dashboard or its supporting files.
- No changes to the React app (`frontend/`) itself.
- No deployment — this is still local repo cleanup, same as every phase
  before actual deployment.

## Success criteria

1. The repo root no longer has an active `index.html` competing with
   `frontend/` as an apparent deploy target.
2. `seed_data.py` and any dashboard-only endpoint are either moved alongside
   it or confirmed still needed elsewhere and left in place, with a clear
   note on which.
3. `DEPLOY-LIGHTSAIL.md` and `PRODUCTION-READINESS.md` no longer describe
   this as an open decision — they state the React app is the product
   surface.
4. Nothing about the working, tested backend or frontend from Phases 1, 2,
   and 5 is touched.
