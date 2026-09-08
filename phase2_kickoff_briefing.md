# Claude Code Kickoff Briefing — Phase 2: Database, Multi-User Auth, Agent API

## Goal

Turn the Phase 1 standalone script into something a real logged-in user can trigger
and read results from — with real multi-user authentication, not the current
hardcoded single-password demo login. This is Phase 2 of the deployment roadmap.
No frontend work and no deployment happen in this phase — see Non-goals below.

## Important context to read first

- Read `tenant_scope.py` and whatever currently handles login/sessions in this repo
  before writing anything new. This backend already does tenant isolation and already
  has some bearer-token session mechanism for the existing single-password-per-tenant
  login. Extend and adapt that existing mechanism — do not rebuild session handling
  from scratch if something usable already exists.
- Architectural decision already made for this product (do not re-litigate it):
  **every account is a tenant, even a single person.** There is no separate "individual"
  vs "organization" signup path. Signing up always creates a tenant behind the scenes,
  with the signing-up user as its owner. If they later invite someone, the tenant they
  already have just gains a second member — no migration, no different code path.

## What to build

### 1. Database schema
- `users` table: id, tenant_id (foreign key), email, password_hash, role
  (owner / admin / member), created_at. Use bcrypt or argon2 for password hashing —
  do not roll your own hashing.
- `agent_runs` table: id, tenant_id, agent_type, subject, status, created_at.
- `agent_reports` table: id, run_id, report_number, title, content, confidence_summary,
  created_at.
- Everything must be scoped by tenant_id and enforced through the existing
  `tenant_scope.py` pattern — a user from one tenant must never be able to read
  another tenant's runs or reports, at the database query level, not just in the UI.

### 2. Auth endpoints
- Signup: creates a new tenant and a new user (role = owner) in one transaction.
- Login: authenticates a user by email/password, returns a session token scoped to
  that user and their tenant.
- Invite: an owner/admin generates an invite tied to their tenant_id and an email
  address. Accepting an invite creates a new user attached to the *existing* tenant,
  not a new one.
- Session verification middleware/dependency that resolves the current user and
  their tenant_id from the bearer token, for use by the agent endpoints below.

### 3. Agent endpoints
- `POST /agents/market-insights/run` — triggers a Market Insights agent run for the
  authenticated user's tenant. This should call the Phase 1 agent script/module —
  do not reimplement the agent logic, wire up what already exists.
- `GET /agents/market-insights/runs` — list past runs for the authenticated tenant.
- `GET /agents/market-insights/runs/{run_id}/reports` — list reports from a specific
  run.
- `GET /agents/market-insights/reports/{report_id}` — fetch one report's full content.
- All of these must only return data belonging to the authenticated user's own tenant.

## Explicit non-goals for this phase

Do not build any of the following yet:

- No frontend/UI changes of any kind
- No deployment to Lightsail or anywhere else
- No changes to the Phase 1 agent's internal logic (research/synthesis) — only wire
  it up so the new run endpoint can call it
- No password reset / forgot-password flow yet — login and signup only
- No billing/Stripe integration

## Success criteria

I should be able to, entirely through API calls (e.g. via curl or a REST client, no
UI needed yet):

1. Sign up as a new tenant/owner.
2. Invite a second user by email, and have that second user accept and log in
   independently.
3. Trigger a Market Insights agent run as either user, and see it appear in that
   tenant's run list.
4. Confirm — this is the most important check — that a user from a *different* tenant
   cannot see the first tenant's runs or reports under any circumstance, even by
   guessing IDs.

If step 4 fails in any way, that is a stop-everything bug, not a minor issue — flag
it to me immediately rather than moving on.
