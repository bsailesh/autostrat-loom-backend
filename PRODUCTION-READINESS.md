# Production Readiness — Phase 6

What this phase produced: locked-down (env-driven) CORS, a confirmed SQLite
storage plan, the exact backend env-var list to set on the server, a working
production frontend build with a configurable API URL, and the status of the
old demo login. **No AWS resources are created here** — the bucket, CloudFront
distribution, DNS, and Lightsail instance are done manually in the console.
Follow `DEPLOY-LIGHTSAIL.md` for that click-through; this file is the checklist
and the decisions behind it.

Target shape (unchanged from `DEPLOY-LIGHTSAIL.md`):

```
Browser → CloudFront + S3 (autostrat.net)        [frontend: the Phase 5 React app in frontend/]
                 ↓ fetch()
          Lightsail instance (api.autostrat.net)  [backend: uvicorn + Caddy for HTTPS]
            └─ SQLite file on the instance disk
```

---

## 1. CORS — locked down, env-var driven ✅

- Controlled entirely by **`CORS_ORIGINS`** (`app/config.py` → `app/main.py`).
  Comma-separated list of allowed browser origins. Nothing is hardcoded.
- The default is `*`, which is **local-dev only**. Production **must** set an
  explicit list.
- Verified: with `CORS_ORIGINS="https://autostrat.net,https://www.autostrat.net"`,
  a request from an allowed `Origin` gets that origin echoed in
  `Access-Control-Allow-Origin`; any other origin gets **no** CORS header, so
  the browser blocks the call.
- `CORS_ORIGINS` is read **once at startup**. Changing it requires
  `sudo systemctl restart loom-api`.
- Set it to the final frontend domain(s) once DNS is decided — expected:
  `https://autostrat.net,https://www.autostrat.net`.

## 2. Database — staying on SQLite (deliberate) ✅

Per the briefing: SQLite is a deliberate choice for the small, invite-only
user base, not an oversight. Postgres migration is a real future task, not part
of this phase. All DB access already goes through one `DATABASE_URL` setting
(`app/database.py`), so that migration is later a config change, not a rewrite.

Storage plan for the Lightsail box:

- Default `DATABASE_URL=sqlite:///./loom.db` resolves relative to the service's
  working directory. The systemd unit sets
  `WorkingDirectory=/home/ubuntu/autostrat-loom-backend`, so the file lands at
  `/home/ubuntu/autostrat-loom-backend/loom.db` — on the instance's persistent
  SSD.
- **Recommended:** set an absolute path explicitly so it never depends on CWD:
  `DATABASE_URL=sqlite:////home/ubuntu/autostrat-loom-backend/loom.db`
  (four slashes after `sqlite:` = absolute path).
- Survives `systemctl restart` and instance reboots. **Not** touched by the
  documented deploy step (`git pull`) — `loom.db` is gitignored/untracked, so
  git leaves it alone. It would only be lost if the instance itself is deleted.
- Backup = periodic **Lightsail snapshots** (see "Keeping it backed up" in
  `DEPLOY-LIGHTSAIL.md`). Turn on automatic daily snapshots.
- On first start against a fresh file, the app creates all tables
  automatically (`Base.metadata.create_all` in `app/main.py`), including
  `signup_allowlist`.

## 3. Backend environment variables (set these on the Lightsail server)

Set in `/home/ubuntu/autostrat-loom-backend/.env` (loaded by the systemd unit).
Start from `.env.example`.

| Variable | Required | Value to set | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | a **separate production key** | See note below — set a spending limit in the Anthropic console. |
| `CORS_ORIGINS` | **yes** | `https://autostrat.net,https://www.autostrat.net` | Exact frontend origin(s). No `*`. Restart on change. |
| `DATABASE_URL` | recommended | `sqlite:////home/ubuntu/autostrat-loom-backend/loom.db` | Absolute path (item 2). Omit to accept the relative default. |
| `LOOM_ADMIN_KEYS` | **yes** | a long random string | Gates `POST /admin/tenants`. Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SESSION_TTL_HOURS` | no | `24` (default) | Login session lifetime. |
| `LOOM_MODEL` | no | `claude-sonnet-5` (default) | Model used by the agent. |
| `CONTACT_EMAIL_TO` | no | already defaulted | Where contact-form submissions are emailed. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_TLS` | no | blank for now | If `SMTP_HOST` is blank, contact submissions are still saved to the DB; only the email send is skipped. Fill in once SES is set up. |

**There is no session signing secret to set.** Session tokens are random
opaque strings (`secrets.token_urlsafe`) stored as rows in the `api_keys`
table — not signed JWTs — so there is no `SECRET_KEY`-style value in play.

**Production `ANTHROPIC_API_KEY` (your task, in the Anthropic console — not code):**
create a **new key** dedicated to production, distinct from the local-dev key
in this repo's `.env`, and set a **monthly spending limit** on it. A real
Market Insights run does live web research and is not cheap; the limit is the
backstop if something loops or is abused.

## 4. Frontend production build ✅

- `npm run build` in `frontend/` produces a working `dist/` — `index.html`
  plus a single hashed JS chunk (no CSS file; the app uses inline styles from
  `src/theme.js`). Verified: `1788 modules transformed`, build clean.
- The API URL is a **build-time** value: `VITE_API_BASE`. `src/api.js` falls
  back to `http://127.0.0.1:8000` if it is unset, so a production build **must**
  provide it.
- Added **`frontend/.env.production.example`**. Copy it to
  `frontend/.env.production` and set `VITE_API_BASE` to the real API domain
  (`https://api.autostrat.net`). Vite auto-loads `.env.production` for
  `npm run build` and it overrides `.env`, so `npm run dev` still uses the
  localhost `.env` — same codebase, no code change.
- Verified the built bundle contains `https://api.autostrat.net` and **no**
  `localhost` / `127.0.0.1` API references when built with that value.
- `dist/` is gitignored — build during deploy, upload to S3, invalidate
  CloudFront (`/*`). Don't commit it.

## 5. Product surface and the old dashboard

**The product surface is the React app in `frontend/`.** That is what gets
built and uploaded to S3/CloudFront (item 4). There is no competing frontend
in the deploy path.

- The old single-file dashboard (`index.html`) — marketing site plus an
  embedded UI for the original five agents (Prioritize / Discover / Align /
  Sustain / Brief) — has been **archived to `legacy/`**. It is not built,
  served, or uploaded by any deploy step. See `legacy/README.md`.
- The hardcoded client-side demo login the briefing referred to
  (`demo@autostrat.net` / a static password check) never existed in the
  archived file either — its `handleLogin()` already calls the real
  `POST /auth/login` (replaced in commit `3abd1e3`). Nothing to disable.
- `seed_data.py` (which populated the old dashboard) is archived alongside it
  in `legacy/`. Production accounts are created via self-serve signup
  (`POST /auth/signup`, gated by `manage_allowlist.py`), not that script.
- The admin endpoints `POST /admin/tenants` and
  `POST /admin/tenants/{tenant_id}/users` stay in the active backend — the
  test suite uses them, not just the archived script — so `LOOM_ADMIN_KEYS`
  is still a required production variable (item 3).

## 6. HTTPS — required (infra, not code)

- The API **must** be served over HTTPS in production. The frontend is HTTPS
  (CloudFront), and browsers block mixed content — an HTTPS page cannot call a
  plain-HTTP API.
- On the Lightsail path this is handled by **Caddy**
  (`deploy/lightsail/Caddyfile`), which gets and renews a free Let's Encrypt
  certificate automatically once `api.<domain>` DNS points at the instance's
  static IP. Nothing to change in application code.
- The frontend's `VITE_API_BASE` must therefore be an `https://` URL (item 4).

---

## Deployment checklist

Backend and infra — full click-through in `DEPLOY-LIGHTSAIL.md`:

- [ ] Anthropic console: create a **production** API key, set a monthly spending limit.
- [ ] Lightsail: create instance, attach a **static IP**, open firewall for TCP 80 + 443.
- [ ] `deploy/lightsail/setup.sh` on the instance (clones repo, makes venv, `.env` from example).
- [ ] Edit `.env`: `ANTHROPIC_API_KEY` (prod key), `CORS_ORIGINS` (explicit domains), `DATABASE_URL` (absolute path), `LOOM_ADMIN_KEYS` (random).
- [ ] Install + start the systemd service; `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.
- [ ] Install Caddy + `deploy/lightsail/Caddyfile`; add `api.<domain>` A record → static IP; `curl https://api.<domain>/health`.
- [ ] On the server: `python3 manage_allowlist.py add <your-email>` — signup returns 403 until an email is on the allowlist.
- [ ] Sign up through the app (or via `POST /auth/signup`) to create your production account.

Frontend:

- [ ] `cd frontend && cp .env.production.example .env.production`; set `VITE_API_BASE=https://api.<domain>`.
- [ ] `npm ci && npm run build`.
- [ ] Upload `frontend/dist/` to the S3 bucket; CloudFront invalidation `/*`.
- [ ] Confirm nothing from `legacy/` is in the upload (item 5) — only `frontend/dist/` goes to S3.

Verify:

- [ ] Load `https://autostrat.net`, sign up / log in, configure the Market Insights scope, start a run, confirm it moves out of the gate and polls.
- [ ] Turn on automatic daily **Lightsail snapshots** (SQLite backup).
