# Claude Code Kickoff Briefing — Phase 6: Production Readiness

## Goal

Get the backend and frontend ready to actually deploy to the live infrastructure
(Lightsail for the backend, S3/CloudFront for the frontend, matching the existing
pattern used for autostrat.net). This briefing covers preparing the *artifacts and
configuration* for deployment. The actual AWS resource creation (new S3 bucket,
new CloudFront distribution, DNS) happens separately, walked through manually in
the AWS Console — that part is not something to attempt here, since prior
infrastructure work on this project has always gone through manual console steps,
not automated cloud provisioning.

## What to fix and prepare

### 1. Lock down CORS
- The backend currently allows all origins (`CORS_ORIGINS=*`), which is fine for
  local development only. Before deployment, this must be restricted to the real
  frontend domain (the exact production URL will be decided alongside DNS setup —
  for now, make this a configurable environment variable, not a hardcoded value,
  so it can be set correctly at deploy time without a code change).

### 2. Confirm the database approach for this deployment
- Decision: **stay on SQLite for this initial deployment.** This is a deliberate
  choice given the small, invite-only user base right now — not an oversight.
  Migrating to Postgres is a real future task once usage grows, not part of this
  phase. Just confirm the SQLite database file path and location are appropriate
  for the Lightsail server (persistent storage, included in backups if any exist),
  not something that would be wiped on a routine deploy or restart.

### 3. Production environment variables
- Document exactly which environment variables the backend needs in production
  (ANTHROPIC_API_KEY, CORS origin, database path, session secret, anything else)
  in a clear checklist or `.env.example` — I'll be setting these directly on the
  Lightsail server myself, not through Claude Code, so this needs to be something
  I can follow without guessing.
- Flag clearly: the production ANTHROPIC_API_KEY should be a separate key from
  the one used in local development, ideally with a spending limit set on it —
  note this as something for me to do in the Anthropic console, not something
  to build in code.

### 4. Frontend production build
- Confirm `npm run build` in `frontend/` produces a working `dist/` folder.
- The frontend's API base URL must point to the real production API domain when
  built for production, not `localhost:8000` — make this configurable via a
  build-time environment variable, not hardcoded, so the same codebase can build
  correctly for both local dev and production without code changes.

### 5. Remove the old demo login
- The current live site has a client-side-only demo login (hardcoded
  `demo@autostrat.net` / password check, no real backend). Once this real
  frontend is deployed, that demo login should be removed or clearly disabled —
  flag exactly which files that is (this may be outside this repo, in the
  separate marketing site's static files — note if so, since that's a different
  deploy process, not something in this repo).

### 6. Confirm HTTPS assumptions
- Note whether the backend API is expected to be served over HTTPS in production
  (it needs to be, since the frontend will be served over HTTPS and browsers
  block mixed-content API calls from an HTTPS page to a plain HTTP API). Flag
  this as a requirement for the Lightsail/DNS setup, not something to solve in
  code.

## Explicit non-goals

- Do not attempt to create AWS resources, modify DNS, or actually deploy
  anything — this phase produces ready-to-deploy artifacts and a clear
  checklist, not a live deployment.
- No changes to any application logic, database schema, or features — this is
  entirely about configuration and packaging for deployment.
- No Postgres migration — explicitly deferred, see above.

## Success criteria

I should end this phase with: a locked-down CORS configuration (env-var driven),
a confirmed SQLite storage plan, a clear list of environment variables I need to
set on the production server, a working production frontend build with a
configurable API URL, and a clear note on what needs to happen to the old demo
login. From there, I'll walk through the actual AWS deployment steps separately.
