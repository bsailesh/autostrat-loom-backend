# AutoStrat Loom — Session Continuity Doc

Written to hand off context to a new chat. **Supersedes the 8 September
version**, which predated four of the five agents. Everything below is
confirmed true as of 7 October 2026.

## Current status: ALL FIVE AGENTS LIVE

| Agent | Reports | Status |
|---|---|---|
| Market Insights (2) | 9 | Live since Sept |
| Voice of Customer (1) | 9 | Live 5 Oct |
| Technology & Regulation (3) | 9 | Live 4 Oct |
| Product Sustainment (4) | 9 | Live 7 Oct |
| Strategy Synthesis & Decision (5) | 7 | Live 17 Sept |

- **Backend**: `https://api.autostrat.net` — `/health` returns
  `{"status":"ok"}`. `/` returns `{"detail":"Not Found"}`, which is FastAPI's
  404 for an undefined root route and is **healthy**, not an error.
- **Frontend**: `https://app.autostrat.net`. Bundle ~575KB (165KB gzipped);
  Vite warns about chunk size, not yet split.
- **Marketing**: `https://autostrat.net`.
- **Signup is invite-only** via allowlist (`manage_allowlist.py`).

## Infrastructure

| Component | Detail |
|---|---|
| GitHub repo | `github.com/bsailesh/autostrat-loom-backend` |
| Backend server | Lightsail instance **"Ubuntu-1"** (default name, never renamed) |
| Static IP | `44.253.87.35` |
| Backend process | `loom-api` systemd service, port 8000, behind Caddy |
| Instance size | 512MB plan — **414Mi usable, 2GB swap added 8 Sept** |
| Database | SQLite, `/home/ubuntu/autostrat-loom-backend/loom.db` |
| Frontend bucket | `autostrat-app` (private, CloudFront-only) |
| Frontend CloudFront | `E2YF1Y0LAQQTFV` |
| Marketing bucket | `autostrat-temp-site` |
| Marketing CloudFront | `E2ZCVTWM9KA4M8` |
| SSL | Wildcard `*.autostrat.net` (ACM, **us-east-1**) |
| DNS | **Cloudflare** (not Route 53) |
| AWS account | `905846953972` |

**Memory is a solved question.** Full Agent 5 synthesis across two upstream
agents peaked at 75Mi swap. Tech & Regulation and Voice of Customer runs barely
moved it. The instance handles the workload; no resize needed.

## Access

**Do not use the Lightsail browser SSH terminal** — it froze repeatedly.

```
ssh -i C:\Users\saile\.ssh\lightsail.pem ubuntu@44.253.87.35
```

**AWS CLI** configured with IAM user `sailesh-cli` (S3 + CloudFront). **Root
access keys were deliberately not created.**

Local repo:
`C:\Users\saile\OneDrive\Documents\AutoStrat\GitHub\autostrat-loom-backend`

## Tenants

| Tenant | Contents |
|---|---|
| Original | Market Insights runs for aerospace actuation (`1f843fe9`, 4 Sept), flight recorders (`df344207`, 7 Sept), liquid piston compressors; Agent 5 runs against the Meridian recorder brief |
| **Arden Actuation Systems** (`demo@autostrat.net`) | The demo tenant. EMA actuation Market Insights run, Tech & Regulation envelope, Agent 5 decision brief, Voice of Customer context |

**Arden Actuation Systems is fictional** — a mid-tier EMA supplier built to
resemble Curtiss-Wright's position without claiming to be them. Strong in
defence and space actuation, absent from commercial flight control.

---

## The platform thesis, now working

Verified end to end on 5 October:

**Technology & Regulation** found an Infineon GaN discontinuation and 19 other
candidate work items → **Agent 5** read all 20 as structured rows, not parsed
prose → they joined 9 Market Insights candidates and 3 user proposals in a
32-candidate universe, scored against Arden's capacity and objectives.

**Product Sustainment** completes the chain: it calculates what that
discontinuation costs and when, since GaN-650 is single-sourced in the Arden
envelope and committed project P-03 is the redesign. **All three agents meet on
one component.**

### How each agent contributes to Agent 5

| Agent | Contribution | Mechanism |
|---|---|---|
| Market Insights | Market evidence, competitor positions | Report markdown, read by Pass 1 |
| Voice of Customer | `customer_value` scoring (0.25 weight, currently substituted) + a **"Findings for synthesis"** section | Named section in Report 1, textual |
| Technology & Regulation | Dated regulatory and supplier obligations | **Structured** `tr_candidate_work` rows |
| Product Sustainment | Runout dates, quantities, blast radius | **Structured** `ps_candidate_work` rows |

**The distinction matters.** Tech & Reg and Sustainment emit *candidate work* —
a defined piece of work with a date. VoC emits *findings* — facts about the
business where whether they warrant a project is a human judgement. Neither
emits effort estimates or priority; those are computed in Agent 5 against
capacity it alone can see.

---

## Architecture decisions worth not relitigating

**The model judges, code computes.** Agent 5 runs two passes: Pass 1 emits
dimension scores as validated JSON, `compute.py` does every calculation,
Pass 2 narrates from the results. Product Sustainment has the same split for
its runout calculation. This made the bottleneck finding — a bucket at 115%
behind a comfortable 51% aggregate — reliable rather than emergent.

**Two populations, never merged.** Agent 5 ranks committed projects with
validated effort. Candidates discovered from evidence have no effort and are
never ranked against them. The transition is a human act: someone scopes a
candidate and adds it to the roadmap.

**The BOM is a matrix, not a tree.** Product Sustainment's structure is
LRU → Level 1 → Level 2 with many-to-many at both joins. A component's
depletion comes from every LRU that consumes it through every path; examining
one LRU alone shows a position that does not exist.

**Agents are independent.** Each has its own package (`market_insights/`,
`tech_regulation/`, `voice_of_customer/`, `product_sustainment/`,
`strategy_synthesis/`) and its own frontend module with its own exhibit
registry. Shared: the report workspace shell, markdown rendering, governing
insight and key insight blocks. Harvey Ball renderers are duplicated
deliberately.

**Every agent degrades, none blocks.** Missing input produces a stated
consequence, never a refusal to run. Each states its operating state in the
first line — scoped/partial/unscoped for Tech & Reg, Tier 1/Tier 2 for VoC.

---

## Shared output standards

Both copies live in `market_insights/standards.py` (imported by Agent 5) and
`tech_regulation/standards.py`. **Two files to touch, not three.**

- **Key insights capped at three**, one sentence each, consequence stated
- **`Validity:` line is exempt from the cap** — a caveat qualifying the whole
  report competes with findings and loses under a flat cap
- **One confidence tag per insight**, never two
- **The governing insight opens each agent's principal decision report** —
  Report 1 for most, **Report 7** for Agent 5

---

## Bugs found and fixed, worth knowing

**The four-competitor cap** (10 Sept). Market Insights truncated discovery at
four, silently dropping Parker Hannifin and Liebherr despite naming them as
top-five players in its own text. Discovery is now uncapped; the grid selects
6 columns by evidence-based significance, with an "also identified" list.

**Agent 5 Pass 1 returning empty payloads** (twice). First from token
truncation at a 16K ceiling; then from a nested answer under a wrapper key
validating as empty because every field defaulted to `[]`. Fixes: stream with a
64K ceiling, reject `stop_reason == max_tokens` before parsing, no default on
the items list, `additionalProperties: false`, unwrap single wrapper keys,
warning-level logging of `stop_reason` and tokens, and **validate completeness
not just schema**.

**`create_all` does not alter existing tables** (18 Sept). Adding
`brief_files.columns` needed a manual `ALTER TABLE` on production. New tables
are fine; new columns on existing tables are not.

**Test isolation via `SessionFactory` at import** (4 Oct). Two modules assigned
`tech_regulation_service.SessionFactory` at import time; whichever imported last
won. Eight symmetrical failures in each file order, passing in isolation.
`conftest.py`'s guard catches `TestClient` without `override_get_db` but not
this. **Logged in conftest; will recur with the next service module.**

**CloudFront had no custom error responses** (18 Sept). Any deep link or page
refresh on a non-root route returned raw XML. Now 403 and 404 both rewrite to
`/index.html` with status 200.

**Scripts mixed credential sources** (5 Oct). URL and key resolved from
different prefixes, or a `--base-url` flag combined with an environment key —
which would send a production credential to staging. Now both from one source
or neither.

---

## Deploying

**Backend:**
```
cd /home/ubuntu/autostrat-loom-backend
git pull
source venv/bin/activate
pip install -r requirements.txt     # only when dependencies changed
sudo systemctl restart loom-api
systemctl status loom-api --no-pager | tail -4
```

**Frontend — a separate deploy. Merging does NOT ship it.**
```
cd frontend
npm run build
aws s3 sync dist/ s3://autostrat-app/ --delete
aws cloudfront create-invalidation --distribution-id E2YF1Y0LAQQTFV --paths "/*"
```

**Marketing site** — files live in `marketing/` in the repo. Individual
`aws s3 cp` only; **never `sync --delete`** against that bucket.

**Recurring deploy traps:**
- Commits sat unpushed several times and the server pulled stale code. Check
  `git log --oneline -1` shows `origin/main` before deploying
- A branch must be merged before the server can pull it
- `systemctl status` immediately after restart shows nothing useful — wait and
  re-check for "Application startup complete"

---

## Demo setup

**Loaders**, all using one credential prefix:
```
scripts/load_arden_brief.py            # Agent 5 decision inputs
scripts/load_arden_tech_reg_scope.py   # Tech & Reg envelope
scripts/load_arden_voc_context.py      # VoC context
scripts/agent5_smoke_test.py           # end-to-end pipeline check
```

Run order matters: Tech & Reg envelope first (VoC reads its product
categories), then VoC, then Agent 5.

**Agent 5 picks up the most recent successful run per upstream agent**
automatically, with `upstream_run_overrides` to pin a specific one.

**Timing:** Agent 5 takes 10–15 minutes on Opus. Market Insights longer.
**Do not run live in front of someone** — run beforehand, demo the output.

`STRATEGY_SYNTHESIS_MODEL=claude-sonnet-5` is the cheap-iteration override for
pipeline debugging. **Remove it before a demo run** — Opus is what ships.

---

## Known gaps, all logged

- **Patent database.** Tech & Reg's patent findings come from public reporting
  of filings, licensing and litigation — not a filings database. Counts, family
  sizes and whitespace analysis are out of reach
- **Run-to-run change detection.** Three agents have digest reports asking
  "what changed since last cycle". Recency is derived from evidence dates
  instead, and the output says which meaning is in use
- **`conftest` guard** doesn't catch service-module `SessionFactory`
  assignment at import
- **`DiscoveredCandidate` has no delete path.** Tech & Reg and Sustainment
  candidate work both have `DELETE` from the start
- **Office document formats** not supported — text, PDF and CSV only
- **No connectors.** CRM, ticketing, SharePoint, telemetry all shown as
  "planned integrations", deliberately not as greyed-out buttons
- **Automatic Lightsail snapshots still off.** One manual snapshot taken
  17 Sept. The database holds five agents' runs across two tenants in one place
- **Supplier quantity definition** — the Product Sustainment input spec lists
  it as pipeline inventory but omits it from the availability formula. The
  implementation excludes it (safer: including uncommitted stock would push
  runout dates later than reality) and labels the column "not counted". **Needs
  a customer to define the field**
- **Large BOMs are capped in reports.** A 200-LRU / 500-assembly /
  4,000-component BOM produced a 1MB runout table. Report tables show the 200
  most urgent rows with a count of the rest; the full set is served by
  `GET /runs/{id}/runout`. **The insufficient-data list is never capped** — a
  part missing from it reads as safe

---

## Open product questions

**Report 1 rethink.** Agent 5's Report 1 is currently the project universe —
two full tables, too much for executive consumption. Wanted: the prioritised
list, a scorecard against strategy, and discovered projects for consideration,
with detail pushed down. Deferred pending design partner input.

**`objectives_served` is a judgement, not a measurement.** Agent 5's coverage
gap check is deterministic set arithmetic over a Pass 1 field. A generous
Pass 1 makes the check find nothing. It found the SO-3 gap when upstream
evidence was present and missed it when it wasn't.

**Shared Product Profile.** Product categories now appear in three agents'
inputs, platforms and supplier watch list in two. VoC already reads Tech &
Reg's categories. Extraction stopped being premature; worth doing.

**Frontend bundle** at 575KB triggers Vite's chunk warning. Agent modules are
independent and could code-split.

---

## Documents in the repo

Specs and briefings are committed, not chat-only — an earlier briefing was lost
that way.

```
market_insights_agent_spec.md              Shared standards live here
agent5_prompt_draft_v2.md                  + decision inputs brief spec, test outputs v1/v2
tech_regulation_prompt_draft_v2.md         + scoping input spec, build briefing
voice_of_customer_prompt_draft_v2.md       + input spec, build briefing
product_sustainment_input_spec.md          + prompt draft v1, build briefing
AutoStrat_Loom_Input_Fields_Glossary.docx  Every input field, for design partner priming
DEPLOY-LIGHTSAIL.md, PRODUCTION-READINESS.md   Corrected 17 Sept to match reality
```

---

## What a demo looks like today

1. **Tech & Regulation** on the Arden envelope — scoped run, candidate work
   with dates, the Infineon discontinuation attributable to a named supplier
2. **Voice of Customer** — Tier 2, three stated beliefs tested against public
   evidence, with what each would need to settle it. The gap *is* the
   integration argument
3. **Product Sustainment** — runout dates, the blast radius across LRUs, and
   the four options a flagged part creates
4. **Agent 5** — 32 candidates, the power-electronics bottleneck at 115.7%
   behind a 67.8% aggregate, certification at 99.3% with no slack, and the
   decision brief connecting them

The strongest single finding across runs: **two projects, 323 weeks of
validated effort, serve no declared objective.** Unserved objectives are a
planning gap; effort pointed at nothing is money already being spent.
