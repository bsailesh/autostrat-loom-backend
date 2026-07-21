# AutoStrat Loom — Backend

This is the backend for the five Loom agents shown on the marketing site:
**Prioritize**, **Discover**, **Align**, **Sustain**, and **Brief**. It's a
multi-tenant API — every piece of data belongs to one "tenant" (one
customer organization), and the code is structured so a tenant can never
read or act on another tenant's data.

You don't need to understand Python to run this. Follow the steps below in
order.

## 1. Install Python

You need Python 3.11 or newer. Check if you already have it:

```
python3 --version
```

If that fails or shows an older version, install Python from
https://www.python.org/downloads/ (grab the latest 3.x installer for your
OS) before continuing.

## 2. Set up the project

Open a terminal in this folder (`autostrat-loom-backend/`) and run:

```
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The `venv` step creates an isolated Python environment just for this
project, so it doesn't conflict with anything else on your machine. You'll
need to run the `source venv/bin/activate` line every time you open a new
terminal to work on this project.

## 3. Add your Anthropic API key

```
cp .env.example .env
```

Open the new `.env` file in any text editor and replace
`sk-ant-your-key-here` with a real API key from
https://console.anthropic.com/. This file is where all secrets live — keep
it out of version control (add it to `.gitignore` before you set up git)
so it never gets committed or shared by accident.

## 4. Run the server

```
uvicorn app.main:app --reload
```

Leave this running. You should see something like `Uvicorn running on
http://127.0.0.1:8000`. Open http://127.0.0.1:8000/docs in a browser — that's
an interactive page (auto-generated from the code) where you can see and
try every endpoint without writing any code.

## 5. Create a demo tenant and sample data

In a **second terminal** (leave the server running in the first one):

```
source venv/bin/activate
python seed_data.py
```

This creates a demo company ("Acme Industrial Co.") with a few sample
initiatives and one tracked asset, and prints an **API key** — save it,
it's the only time it's shown. That key is what stands in for a logged-in
user of that tenant on every request.

## 6. Try an agent for real

Using the API key printed in step 5:

```
curl -X POST http://127.0.0.1:8000/initiatives/<initiative_id>/prioritize \
  -H "Authorization: Bearer <api_key>"
```

(The exact command with real IDs filled in is also printed at the end of
the seed script.) This makes a real call to Claude and stores a score. You
can see the result either in that response, or by refreshing
http://127.0.0.1:8000/docs and trying `GET /initiatives/{id}/scores`.

## 7. Run the automated tests

```
pytest -v
```

These run offline against an in-memory database with the Claude calls
mocked out, so they don't need your API key or an internet connection.
They specifically check that one tenant can never read or trigger an agent
on another tenant's data — that's the property that matters most before
you'd put real customer data anywhere near this.

---

## How this maps to the marketing site

| Site agent card | Endpoint(s) |
|---|---|
| Loom Prioritize | `POST /initiatives/{id}/prioritize` |
| Loom Discover | `POST /signals/discover` |
| Loom Align | `POST /roadmaps` |
| Loom Sustain | `POST /assets/{id}/assess` |
| Loom Brief | `POST /briefs` |

Every other endpoint (`GET /initiatives`, `GET /assets`, `GET /audit-log`,
etc.) supports reading back what the agents have produced.

## How tenant isolation actually works here

- Every business table has a `tenant_id` column.
- Every query goes through helper functions in `app/tenant_scope.py` that
  filter by tenant automatically — there's no code path where a router
  queries a table without that filter.
- The tenant is never taken from the request body or URL — it's derived
  server-side from the caller's API key (`app/auth.py`). A caller can't ask
  for another tenant's data by changing a parameter, because there's no
  parameter for that.
- Requesting another tenant's record by ID returns 404, not 403 — so a
  caller can't even confirm that a given ID exists outside their own
  tenant.
- Every agent action writes an append-only row to `audit_log`
  (`app/agents/base.py`), scoped to the tenant, with no delete route
  exposed anywhere in the API.

This is a solid foundation, but it is not the same thing as an enterprise
security review. Before this touches real customer data:
- Replace the simple bearer-API-key auth with SSO (SAML/OIDC) — the rest of
  the app only depends on "give me the current tenant and role," so this
  swap doesn't ripple through the agents or routers.
- Move from SQLite to Postgres (`database.py` is the only file that needs
  to change — set `DATABASE_URL` in `.env` to a Postgres connection string).
- Add rate limiting, request size limits, and structured logging/monitoring.
- Get a real penetration test / security review before onboarding paying
  enterprise customers. No stack or architecture choice substitutes for
  that step.

## Project layout

```
app/
  main.py            FastAPI app, wires up all routers
  config.py           environment/config loading
  database.py          DB engine + session setup
  models.py             SQLAlchemy tables (the actual data model)
  schemas.py              Pydantic request/response + agent output contracts
  auth.py                   API key -> tenant resolution
  tenant_scope.py            centralized tenant-scoped query helpers
  agents/
    base.py                    shared Claude-calling + audit logging logic
    prioritize.py                Loom Prioritize
    discover.py                    Loom Discover
    align.py                         Loom Align
    sustain.py                         Loom Sustain
    brief.py                             Loom Brief
  routers/            one file per API resource (initiatives, signals, assets, roadmaps, briefs, audit, tenants)
tests/
  test_agents_and_isolation.py    tenant isolation + agent tests, mocked Claude calls
seed_data.py           creates a demo tenant + sample data
```

## Connecting the front end

The `index.html` front end you already have is currently a static demo (the
login form and contact form don't call anything real). To connect it:
- The contact form (`handleContact`) would POST to a new `/contact` endpoint
  you'd add here, which emails or stores the message.
- The login form (`handleLogin`) is a placeholder for real authentication —
  once you add SSO or a proper login flow, that's what wires in here.
- Anything showing live agent output (a dashboard, a scored backlog view)
  would call the endpoints in the table above with `fetch()`, using the
  tenant's API key or session token.

That front-end wiring is a separate, smaller task once you're ready for it
— happy to help with that next.
