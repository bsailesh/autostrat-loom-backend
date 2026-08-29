# legacy/ — archived, not part of the deploy

These files belong to an earlier iteration of the product and are kept only
for reference and git history. **Nothing here is built, served, or uploaded
by the Phase 6 deployment.** The live product surface is the React app in
`../frontend/` (see `../PRODUCTION-READINESS.md`).

Do not wire these back into a deploy path. If you need something from here,
lift the specific piece into the active codebase deliberately.

## Contents

| File | What it was |
|---|---|
| `index.html` | A single-file marketing site **plus** an embedded dashboard for the original five agents — Prioritize / Discover / Align / Sustain / Brief (later renamed Voice of Customer / Market Insights / Tech & Regulation / Product Sustainment / Strategy Synthesis and Decision). Its login already calls the real `POST /auth/login`; there is no hardcoded demo credential. Superseded by `../frontend/`. |
| `seed_data.py` | A script that stood up a demo tenant + login user + sample initiatives/assets by calling the running API (`POST /admin/tenants`, `/admin/tenants/{id}/users`, `/initiatives`, `/assets`). Used to populate the old dashboard. The current product creates accounts through self-serve signup (`POST /auth/signup`, gated by `manage_allowlist.py`), not this script. |

## What was intentionally left in the active codebase

- **`POST /admin/tenants`** (`app/routers/tenants.py`) and
  **`POST /admin/tenants/{tenant_id}/users`** (`app/routers/auth.py`) —
  `seed_data.py` calls these, but so does the test suite
  (`tests/test_agents_and_isolation.py`, `tests/test_auth_and_contact.py`),
  so per the archive addendum they stay where they are.
- The five original agent routers (`initiatives`, `signals`, `assets`,
  `roadmaps`, `briefs`) and their tests — working, tested backend from
  Phases 1–2, out of scope for this archive.
