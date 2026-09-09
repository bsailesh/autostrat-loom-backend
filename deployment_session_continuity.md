# AutoStrat Loom — Session Continuity Doc

Written to hand off context to a new chat. Supersedes the 4 Sept version.
Everything below is confirmed true as of the end of the 8 Sept session, not
aspirational.

## Current status: LIVE AND WORKING

- **Backend**: `https://api.autostrat.net` — healthy. `/health` returns
  `{"status":"ok"}`. Note that `/` returns `{"detail":"Not Found"}` — that is
  FastAPI's 404 for an undefined root route and is **healthy**, not an error.
- **Frontend**: `https://app.autostrat.net` — the product surface (React).
  Signup, login, scope configuration, running Market Insights, reading
  reports, and exporting the full report pack to Word all confirmed working.
- **Marketing site**: `https://autostrat.net` — "Log in" links point to
  `app.autostrat.net`. Favicon added 8 Sept.
- **Signup is invite-only** via allowlist. `saileshathreya@autostrat.net` is on
  it.

## Infrastructure reference

| Component | Detail |
|---|---|
| GitHub repo | `github.com/bsailesh/autostrat-loom-backend` |
| Backend server | Lightsail instance named **"Ubuntu-1"** (default name, never renamed) |
| Backend static IP | `44.253.87.35` (`StaticIp-1`) |
| Backend process | `loom-api` systemd service, port 8000, reverse-proxied by Caddy |
| Backend HTTPS | Caddy, automatic via Let's Encrypt |
| Instance size | 512MB plan — **414Mi usable, 2GB swap added 8 Sept** |
| Database | SQLite, `/home/ubuntu/autostrat-loom-backend/loom.db` — deliberate, Postgres deferred |
| Frontend S3 bucket | `autostrat-app` (private, CloudFront-only) |
| Frontend CloudFront | `E2YF1Y0LAQQTFV`, `d33ugba59hfe7o.cloudfront.net` |
| Frontend SSL | Wildcard `*.autostrat.net` (ACM, **us-east-1**) |
| Marketing S3 bucket | `autostrat-temp-site` |
| Marketing CloudFront | `E2ZCVTWM9KA4M8` (has a custom error response sending unmatched paths to the homepage) |
| DNS provider | **Cloudflare** (not Route 53) |
| AWS account | `905846953972` |

## Access — how to connect (set up 8 Sept)

**Do not use the Lightsail browser SSH terminal.** It froze repeatedly across
two sessions. Key-based SSH from PowerShell is set up and reliable:

```
ssh -i C:\Users\saile\.ssh\lightsail.pem ubuntu@44.253.87.35
```

**AWS CLI** is installed on the Windows machine and configured with IAM user
`sailesh-cli` (S3 + CloudFront access). **Root access keys were deliberately
not created.** Verify with `aws sts get-caller-identity`.

Local repo: `C:\Users\saile\OneDrive\Documents\AutoStrat\GitHub\autostrat-loom-backend`

## What happened in the 8 Sept session

### 1. Production outage — diagnosed and fixed

The instance became completely unreachable: no SSH, no HTTPS, while CPU sat
idle. Root cause was **chronic out-of-memory**. `journalctl` showed the OOM
killer firing roughly hourly for days, killing `fwupd` at only ~110MB
resident, with memory pressure severe enough to wedge the network stack
(`systemd-networkd-wait-online` timeouts).

State before the fix: 414Mi RAM, **0B swap**, ~122Mi available at idle.

Fix applied on the instance:
- 2GB swap file at `/swapfile`, persisted in `/etc/fstab`
- `vm.swappiness=20` in `/etc/sysctl.conf`
- `fwupd.service` **masked** (it is a static unit — `disable` does not work),
  `fwupd-refresh.service` and `.timer` disabled

Stable since. A stop/start from the Lightsail console was what recovered the
box initially.

### 2. Word export — shipped

`GET /agents/market-insights/runs/{run_id}/export.docx` generates a single
Word document from all 9 reports in a run. Tenant-scoped, streamed from
memory, cursor-iterated. Frontend Export button in the Workspace header.

Modules: `app/export/{markdown_parser,exhibits,docx_builder,build_template}.py`
plus a committed `template.docx` and `scripts/render_export.py` for QA
rendering.

Verified by rendering all 33 pages and inspecting each. Six defects found and
fixed. TOC is a Word field — Word prompts "update fields" on first open, which
is expected and required to populate page numbers.

**Memory during a live export was negligible** — available held at 116Mi, swap
steady at 30Mi. The export does not stress the box.

### 3. Test-suite isolation bug — fixed

Every test file assigned the global `app.dependency_overrides[get_db]` at
import time, so the last-imported file's database won for the whole session.
Reversing file order produced **22 failures out of 60** — including the
tenant-isolation and cross-tenant access tests. Those security guarantees were
only being verified by alphabetical accident.

Fixed with `tests/conftest.py`: an autouse fixture pinning each module's
override per test, plus a collection-time guard that fails loudly if a module
builds a `TestClient` without defining `override_get_db`. Verified 60/60 across
four orderings.

### 4. Deployment docs corrected

`DEPLOY-LIGHTSAIL.md` and `PRODUCTION-READINESS.md` now match reality —
Cloudflare not Route 53, the `app.` subdomain in `CORS_ORIGINS`, swap as a
required step, the real frontend hosting build-out, key-based SSH, and the
fact that backend deploy does not deploy the frontend.

### 5. Cleanup

- Old `/login` and `/login.html` deleted from the marketing bucket
- Favicon added to both sites — AL monogram in Florida Gators colours
  (`#0021A5` / `#FA4616`), built from scratch since no source logo file exists

## Deploying changes

**Backend** (SSH to the instance):
```
cd /home/ubuntu/autostrat-loom-backend
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart loom-api
systemctl status loom-api --no-pager
```

**Frontend — a separate step. Merging code does NOT deploy the frontend.**
This was hit on 8 Sept.
```
cd frontend
npm run build
aws s3 sync dist/ s3://autostrat-app/ --delete
aws cloudfront create-invalidation --distribution-id E2YF1Y0LAQQTFV --paths "/*"
```
Hard-refresh (Ctrl+Shift+R) to confirm.

**Marketing site** — no repo, no version control. Files live only in S3. Edit
by `aws s3 cp` down, change, `aws s3 cp` back. Use individual `cp` commands,
**never `sync --delete`**, which would wipe the site.

## Known bugs and gotchas (hit for real, will recur)

- `CORS_ORIGINS` must list every origin explicitly including subdomains — the
  bare domain does not cover `app.<domain>`. Verify with `grep` after editing;
  a `nano` edit silently failed to save once. Read once at startup, so restart
  after changing.
- ACM certificates for CloudFront must be in **us-east-1** regardless of where
  anything else lives.
- CloudFront needs **Default root object** = `index.html` for a single-page app.
- Caddy ships a placeholder config; copying the project Caddyfile over it is a
  required step.
- Instance names can silently default during creation.
- Check Cloudflare for stale/duplicate records pointing at an old instance
  during any redeploy.
- Pasting multi-line command blocks into PowerShell sometimes runs only the
  last line. Run consequential commands one at a time and check each result.

## Report markdown format (learned 8 Sept, needed for any parser work)

Verified across two production runs. The frontend parses this at render time;
the export parses it again in Python. **Two parsers, one contract — they will
drift.** Golden fixtures live in `tests/fixtures/reports/` as the drift alarm.

- **Subject line** — first line, bold, pipe-delimited. **Format drifts between
  runs**: whole-line bold vs per-label bold; `Window:` vs `Date window:`;
  `Compiled <date>` present in one run, absent in the other.
- **Governing Insight** — Report 1 only. SCQA: bold **Situation. /
  Complication. / Question. / Answer.**
- **Key Insights** — all other reports. Bullets with trailing
  `(Confidence: High)`.
- **Three confidence-tag conventions**: leading `**FACT (High).**`, trailing
  `(Confidence: High)`, and em-dash `**FACT — High confidence**`.
- `*So what:*` italic closers end most evidence paragraphs.
- `**Staleness flag:**` marks evidence outside or old within the research
  window. Currently only visible if you read the paragraph it sits in.
- `## Exhibit N — <title>` — exhibits are headings, not special blocks.
- **Fenced blocks appear in only 5 of 18 reports, three distinct structures**:
  TAM/SAM/SOM nested boxes (Report 2, both runs — has a dedicated handler), a
  design-authority/brand arrow map (Report 3 — preformatted fallback), and one
  uninspected block in Report 9.
- **Harvey Ball grid** (Report 4) — 6 columns, 20 rows, Unicode `● ◕ ◑ ◔ ○`.
  Needs landscape orientation and an explicit symbol font or it renders
  incoherently.

## Follow-up items

**Worth doing before building agent #2:**
- **TAM/SAM/SOM renders as ASCII in the frontend.** The Word export now renders
  it as proper nested tables, so the export looks better than the app. Fix
  before the report workspace gets reused by another agent.
- **Marketing site has no version control.** Live production HTML edited by
  hand with no history.

**Not urgent:**
- Three untracked files at the repo root — `autostrat-loom-dashboard.jsx`,
  `index.html`, `index-backup Sept 7..html`. Probably legacy, unconfirmed.
- Report 9's fenced block is uninspected; it hits the preformatted fallback.
- Harvey Ball `◕` vs `●` are hard to distinguish at body text size.
- Instance sizing — **unmeasured, not a known problem.** An agent run has never
  been observed under memory monitoring. Do that before deciding to resize;
  the export barely touched the box.
- Staleness flags are easy to miss in a 90-page pack — surfacing a count on the
  cover would help.
- The app's AL mark (orange on navy) and the logo (blue/purple gradient) are
  different. No source logo file exists in any form.
- Postgres migration, Stripe billing.

## Product/spec context

- Full agent specification (Evidence & Confidence Standard, Consulting-Grade
  Output Standard, Market Insights agent spec) is in
  `market_insights_agent_spec.md`, **now committed to the repo** (it was
  untracked until 8 Sept).
- All session briefings are now committed too.
- **Only Market Insights has a backend.** Voice of Customer, Tech & Regulation,
  Product Sustainment, and Strategy Synthesis and Decision exist as spec and as
  inert "Not subscribed" cards.
- The report workspace design pattern (report list sidebar, Governing Insight
  on Report 1 only, Key Insights elsewhere, named exhibits per report type) is
  documented in the Phase 5 frontend briefing and is the reference for any
  additional agent's frontend — not something to redesign.
- Two production runs exist: `1f843fe9` (aerospace actuation, 4 Sept) and
  `df344207` (flight recorders, 7 Sept). Both succeeded, 9 reports each.
