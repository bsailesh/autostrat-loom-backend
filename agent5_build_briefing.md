# Briefing: Build Agent 5 — Strategy Synthesis & Decision

Full build in one pass: data model, CSV ingest, deterministic computation,
agent runner, endpoints, frontend.

**Read first, in this order:**

1. `agent5_prompt_draft_v2.md` — the agent's operating specification
2. `agent5_decision_inputs_brief_spec.md` — the input contract
3. `agent5_test_output_v2.md` — what good output looks like
4. `market_insights_agent_spec.md` — the shared Evidence & Confidence Standard
   and Consulting-Grade Output Standard, which this agent inherits

The existing `market_insights/` package is the structural reference. Follow its
patterns unless this briefing says otherwise.

**Do not start coding until you have told me your implementation plan and I have
approved it.** This is the largest single feature in the platform.

---

## The central design decision

**The model judges. Code computes.**

Agent 5's output in testing contained a finding that mattered: aggregate
capacity utilisation was 51% while one bucket sat at 115%. That finding is
arithmetic. So are weighted composite scores, scenario re-rankings, and funding
line placement.

A language model doing arithmetic across nine projects, four capacity buckets
and four scenarios will produce plausible-looking errors in the numbers an
executive acts on. Worse, it will produce *different* errors each run.

Therefore a **two-pass design**:

**Pass 1 — judgment.** The agent reads the upstream reports and the decision
brief. It produces structured JSON: discovered candidates, and per-project
dimension scores on a 1–10 scale with a basis label and a one-line reason for
each. No composites, no rankings, no utilisation.

**Computation — deterministic, in Python.** From Pass 1's dimension scores and
the brief's data, compute: weighted composite scores, rankings, per-bucket
capacity utilisation, funding line placement, scenario re-rankings, and the
cross-scenario prerequisite check. All pure arithmetic.

**Pass 2 — narrative.** The agent receives the computed results and writes the
seven reports, interpreting and explaining rather than calculating.

This makes scenarios nearly free — same dimension scores, different weights,
recomputed in code — and makes the bottleneck finding reliable rather than
emergent.

---

## Part 1 — Data model

Follow existing conventions in `app/models.py`. Every table is tenant-scoped.

### Reuse `agent_runs` and `agent_reports` if you can

Inspect them first. Agent 5 produces seven reports with the same shape as Market
Insights. If those tables can carry an agent discriminator without disturbing
Market Insights, **reuse them** — the Word export pipeline then works for Agent 5
with no changes, which is significant. If `agent_runs` carries
Market-Insights-specific columns that make this awkward, say so in your plan and
propose an alternative.

### New tables

**`strategy_config`** — one per tenant
- effort unit (string, used verbatim in output)
- fiscal year start month and label format
- project types (JSON list, customer-defined)

**`capacity_buckets`** — customer-declared, 2 to 8 per tenant
- `bucket_key` (used as a CSV column name — validate uniqueness and that it is
  safe as a column header)
- `bucket_name` (display)
- `contractable` — enum: yes / partial / no
- note

**`effort_bands`** — optional, customer-defined
- band name, min units, max units

**`strategic_objectives`**
- objective key, text, horizon, owner, measure

**`products_fleet`**
- product id, product, platform, platform class, units in service, avg age,
  status, region
- One row per product × platform. Platform granularity is required.

**`capacity`**
- fiscal year, `bucket_key`, fte, capacity units, budget
- Blank future years are recorded as unplanned, not zero. Use nullable columns,
  not zeros.

**`portfolio_projects`** — committed, from the roadmap
- project key, name, type, status, pct complete, target gate, target fy, owner
- `mandatory` (bool), `mandatory_driver`, `mandatory_deadline`
- `mandatory` is a customer declaration, never inferred

**`project_effort`**
- project, `bucket_key`, effort remaining, effort total
- One row per project × bucket. **Effort remaining is what feeds scoring.**

**`project_dependencies`**
- project, depends_on_project, dependency type, note, `source` enum:
  `customer` / `inferred`

**`project_financials`**
- project, revenue impact y1–y5, capex, opex annual, discount rate, currency,
  basis

**`proposed_projects`** — user-supplied, unscoped
- project key, name, proposed_by, description, rationale
- No effort. These never enter the ranked portfolio.

**`prioritization_frameworks`** — per run
- framework enum, and criteria with weights and `source_agent`

**`scenarios`** and **`scenario_weights`**
- scenario name, criterion, weight

**`strategy_rules`**
- rule type, value, note

**`discovered_candidates`** — persisted across runs
- candidate key, name, origin, problem addressed, evidence summary, support
  classification, first seen run, status enum: `new` / `under_review` /
  `scoped` / `dismissed`, dismissal reason
- **This solves the candidate persistence problem.** A dismissed candidate is
  not re-presented as new. If evidence changes materially, surface it as
  `changed`, not `new`.

### Uploaded files

**`brief_files`** — one row per uploaded CSV
- file type, filename, `as_of` date, uploaded by, row count, validation status
- Staleness is flagged in output at 180 days, matching the evidence staleness
  convention used elsewhere.

---

## Part 2 — CSV ingest and validation

Endpoint per file type. Parse, validate, store, report.

### Validation rules

| Check | Severity |
|---|---|
| Every roadmap effort column matches a declared `bucket_key` | Error |
| Every capacity row's `bucket_key` is declared | Error |
| Dependency references resolve to known project keys | Error |
| `pct_complete` consistent with effort remaining vs total | Warning |
| Fiscal years in capacity cover the horizon of `target_fy` | Warning |
| Platform rows sum to a plausible installed base | Warning |
| File older than 180 days | Warning |

**The bucket-name match is the important one.** A roadmap with `cert` against a
capacity file with `certification` joins to nothing and silently produces a
bottleneck analysis missing a constraint — the exact failure the analysis exists
to prevent. Fail loudly.

Provide downloadable CSV templates generated from the tenant's declared buckets,
so column names are correct by construction.

Validation errors block that file's ingest. They never block a run — the run
proceeds with whatever validated data exists, and states the consequence.

---

## Part 3 — The computation module

`strategy_synthesis/compute.py`. Pure functions, no LLM, no database access —
take data in, return results. Fully unit-testable, and test it thoroughly. This
is where correctness lives.

### 3.1 Composite scoring

Input: dimension scores (1–10) per project from Pass 1, and criterion weights.
Output: composite score per project, and the ranking.

Ties are reported as ties, not broken arbitrarily.

### 3.2 Capacity utilisation

For each fiscal year with capacity data, and each bucket: sum `effort_remaining`
across committed projects, compare against capacity, compute utilisation.

Also compute aggregate — but the report must never present aggregate alone.

### 3.3 Bottleneck analysis

For any bucket over 100%:
- The overage
- How much of that bucket's demand comes from `mandatory` projects
- The minimum set of deferrals that brings it under capacity. Search from the
  lowest-ranked project upward; report the smallest set found
- Whether that set agrees with the ranking
- Whether the bucket is `contractable`

### 3.4 Scenario re-ranking

Same dimension scores, each scenario's weights, recomputed. Also recompute
capacity utilisation per scenario where a scenario's ranking changes which
projects are deferred.

### 3.5 Cross-scenario prerequisite check

For every scenario, find any project ranked above a project it depends on.
Return the violations.

### 3.6 Financial metrics

NPV and payback from `project_financials` where present. **Never merged into the
composite score.** Return as a separate field.

Do not compute return for `mandatory` projects. Do not compute NPV where revenue
projections are absent — return cost only, with a reason.

---

## Part 4 — The agent

`strategy_synthesis/` — mirror `market_insights/`:

- `standards.py` — role, scope, evidence standard, the two-population rule,
  criterion substitution, customer vocabulary
- `prompts.py` — pass 1 and pass 2 prompts
- `reports.py` — seven `ReportSpec` objects
- `compute.py` — Part 3
- `agent.py` — orchestration
- `config.py`

### Pass 1 output schema

Strict JSON. Validate it; retry once on malformed output; fail the run with a
clear error rather than proceeding on a bad parse.

```
{
  "candidates": [
    {"key", "name", "origin", "problem", "evidence_summary",
     "support_classification", "evidence_strength_rank", "source_citations"}
  ],
  "project_scores": [
    {"project_key",
     "dimensions": [{"criterion", "score", "basis", "reason"}],
     "confidence"}
  ],
  "criterion_substitutions": [
    {"criterion", "declared_source_agent", "substituted_source", "rationale"}
  ],
  "inferred_dependencies": [
    {"project_key", "depends_on", "reason"}
  ]
}
```

### Upstream input and the memory constraint

Agent 5 consumes other agents' report markdown. Market Insights alone is ~120KB
across nine reports; four agents could be 500KB.

**The production instance has 414MB RAM and 2GB swap.** Do not load all upstream
reports into memory at once. Iterate cursors. If total upstream content exceeds
a threshold, summarise per agent in a preliminary step rather than truncating —
and say in the output that summarisation occurred.

Which upstream runs to consume is a run parameter: the most recent successful
run per agent by default, overridable.

### What must not be inferred

`mandatory` is a customer declaration. Effort for candidates is never estimated.
Dependencies not supplied by the customer are marked `inferred` and flagged for
confirmation in the report.

---

## Part 5 — Endpoints

Follow the router pattern in `app/routers/market_insights.py`. **Everything
tenant-scoped; 404 not 403 for cross-tenant access.**

```
GET/PUT  /agents/strategy/config
GET/PUT  /agents/strategy/buckets
GET/PUT  /agents/strategy/objectives
POST     /agents/strategy/files/{file_type}     upload + validate
GET      /agents/strategy/files
GET      /agents/strategy/templates/{file_type} download CSV template
GET/PUT  /agents/strategy/framework
GET/PUT  /agents/strategy/scenarios
GET      /agents/strategy/readiness             what is missing and its cost
POST     /agents/strategy/runs                  start a run
GET      /agents/strategy/runs
GET      /agents/strategy/runs/{run_id}/reports
GET      /agents/strategy/runs/{run_id}/export.docx
PATCH    /agents/strategy/candidates/{key}      status + dismissal reason
```

**`/readiness` matters.** It returns not just what is missing but what it costs —
"without capacity by bucket, 9 projects will be ranked but not scheduled". The
UI uses this to motivate completion rather than nag.

**A run is never blocked by an incomplete brief.** Degrade and state the
consequence.

Reuse the existing export pipeline if you reused `agent_reports`.

---

## Part 6 — Frontend

### Decision inputs screen

Settings-style, sections matching the brief spec: configuration, objectives,
products and installed base, capacity, roadmap, proposals, framework, scenarios,
rules.

Per section: status (set / partial / missing), and for file-backed sections the
filename, row count, `as_of` date and detected columns.

Show consequences from `/readiness`, not just red badges.

**Run is always enabled.** Warnings inform; they do not gate.

Bucket configuration is its own sub-screen: add, rename, set `contractable`.
Changing buckets after files are uploaded invalidates those files — warn
clearly.

### Report workspace

Reuse the Phase 5 pattern documented in `phase5_frontend_briefing.md` — report
list sidebar, governing insight on report 1, key insights elsewhere, named
exhibits. Do not redesign it.

New exhibit renderers needed:
- **Capacity utilisation** — horizontal bars per bucket, with the 100% line
  marked. Over-capacity bars visually distinct
- **Dependency graph** — nodes and edges from structured data. A simple layered
  layout is sufficient; do not pull in a heavy graph library
- **Scenario comparison** — rank movement across scenarios

All render from structured data in the report payload. **No ASCII art.** If a
renderer is missing, fall back to a table, never to character art.

### Candidate actions

From Report 7, a candidate can be marked under review, scoped or dismissed with
a reason. Scoping prompts to add it to the roadmap with effort by bucket.

---

## Part 7 — Testing

- **`compute.py` unit tests are the priority.** Cover: bottleneck detection
  including the aggregate-looks-fine case; minimum deferral set; scenario
  re-ranking; prerequisite violations; NPV absent and partial; ties
- Fixture-based ingest tests, including the bucket-name mismatch failing loudly
- Endpoint tests: cross-tenant 404, incomplete brief still runs, malformed pass 1
  JSON handled
- Follow `tests/conftest.py`. **Run the suite in more than one file order** —
  there was a real isolation bug here on 8 Sept

Reproduce the v1 test conditions as a fixture: the strawman brief and the flight
recorders run. `agent5_test_output_v2.md` is the reference for what the pipeline
should produce.

---

## Out of scope

- Do not build the other four domain agents
- Do not change Market Insights
- Do not change the export pipeline beyond what reuse requires
- Do not add run-to-run change detection — noted as a gap, not this task
- Do not add auth, CORS, DNS or infrastructure changes

---

## Deployment notes

- Any new dependencies pinned in `requirements.txt`
- Migrations: the app uses `Base.metadata.create_all`. New tables are created on
  restart — confirm that holds and say so in the PR
- Backend deploy is `git pull`, `pip install`, `systemctl restart loom-api`
- **Frontend is a separate deploy.** Merging does not deploy it — build, sync to
  `s3://autostrat-app/`, invalidate `E2YF1Y0LAQQTFV`
- Watch `free -h` during the first real run and report what you see

---

## Definition of done

- [ ] Two-pass design implemented; no arithmetic performed by the model
- [ ] `compute.py` pure, tested, high coverage
- [ ] Bottleneck analysis correct, including the aggregate-looks-comfortable case
- [ ] Candidates persist across runs with status
- [ ] No effort or score attached to any candidate
- [ ] `mandatory` never inferred
- [ ] Bucket-name mismatch fails loudly at ingest
- [ ] Runs succeed with an incomplete brief and state consequences
- [ ] Reports render from structured data; no ASCII art anywhere
- [ ] Word export works for Agent 5 runs
- [ ] Suite passes in multiple file orders
- [ ] Memory checked on the instance; result in the PR
- [ ] Committed, pushed, merged via PR
