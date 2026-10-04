# Briefing: Build Agent 3 — Technology & Regulatory Intelligence

Full build: scoping input, agent package, candidate work persistence, endpoints,
frontend.

**Read first, in this order:**

1. `tech_regulation_prompt_draft_v2.md` — the agent's operating specification
2. `tech_regulation_scoping_input_spec.md` — the scoping contract
3. `market_insights_agent_spec.md` — the shared Evidence & Confidence Standard
   and Consulting-Grade Output Standard, which this agent inherits

`market_insights/` is the structural reference. This agent is closer to Market
Insights than to Agent 5 — single pass, no deterministic compute module, no
decision brief. Follow those patterns unless this briefing says otherwise.

**Do not start coding until you have given me an implementation plan and I have
approved it.**

---

## Two decisions already made

**1. Nine reports in v1, not eleven.** Build Reports 1–8 and 11. Omit Report 9
(technology and regulatory timeline), which recombines content from 4, 6, 7 and
8, and Report 10 (digest), which needs run-to-run change detection the platform
does not have. Both are noted as deferred in the output, not silently dropped.

Report 11 stays because competitor *technical capability* is genuinely distinct
from Market Insights' commercial and structural view of the same competitors.

**2. Candidate work is persisted as structured rows, not only markdown.**

This agent's main contribution to Agent 5 is candidate work with five defined
fields. If it exists only as prose inside a report, Agent 5's Pass 1 has to
re-parse it — a second parser of an undocumented contract, which is a failure
mode this codebase has already hit twice (the Word export markdown parser, and
Agent 5's own report consumption).

A structured table means Agent 5 reads candidate work directly, with no parsing
and no drift.

---

## Part 1 — Data model

Follow existing conventions in `app/models.py`. Every table tenant-scoped.

**Reuse `agent_runs` and `agent_reports`** via the existing `agent_type`
discriminator — `agent_type="tech-regulation"`. The Word export then works with
no changes, as it did for Agent 5. Add `"tech-regulation"` to
`agent_label_for()`, which raises on unregistered types.

### Scoping tables

**`tr_product_categories`** — category_key, category_name, description

**`tr_jurisdictions`** — jurisdiction, role (`primary` / `secondary` /
`export_only`)

**`tr_certification_basis`** — category_key, basis_type, basis_identifier,
status, held_since

`basis_type` is a controlled list with free-text fallback: `TSO`, `ETSO`,
`CS`, `Part`, `MIL-STD`, `STC`, `PMA`, `Standard`, `Other`. These are not
interchangeable and the agent needs to know which is which. Where `Other`, the
free-text value is used verbatim.

**`tr_platforms`** — platform, platform_class, relationship
(`shipping` / `pursuing` / `in_service` / `sunsetting`), programme_status

`relationship` changes how the agent reads a finding and must be preserved
through to the output — a change on a shipping platform is a cost, the same
change on a pursued one is an entry condition.

**`tr_standards_held`** — standard_id, revision, scope, status
(`compliant` / `certified` / `in_progress` / `lapsed`)

**`tr_suppliers`** — supplier, what_they_supply, criticality
(`single_source` / `dual_sourced` / `multi_source`)

**`tr_domains`** — domain (from the per-industry list, plus free text)

**`tr_exclusions`** — exclusion_type (`platform_class` / `jurisdiction` /
`domain` / `category`), value, reason

### Candidate work

**`tr_candidate_work`** — the contract with Agent 5

- tenant_id, run_id
- `candidate_key` (e.g. `TR-01`), unique per tenant
- `driver` — the named regulation, standard revision, supplier notice or
  development, with its identifier
- `work_date` (nullable) and `date_basis` — `effective` / `compliance_deadline`
  / `runout` / `transition_end` / `window_closes` / `none_established`
- `date_absent_reason` — required when `work_date` is null
- `applicability` — which categories, bases or platforms, as JSON
- `work_implied` — `requalification` / `new_approval` / `design_change` /
  `standards_participation` / `supplier_qualification` / `documentation` /
  `other`, plus a free-text description
- `platform_relationship` (nullable) — carried from the platform where it
  differs
- `classification` and `confidence` — the evidence basis
- `source` and `source_date`
- `status` — `new` / `under_review` / `accepted` / `dismissed`, with
  `dismissal_reason`

**Persistence mirrors `DiscoveredCandidate`:** additive, keyed by
`candidate_key`, refreshing evidence fields on an existing key and never
resurrecting a dismissed item as new.

**Note the known gap:** `DiscoveredCandidate` has no delete path, logged as a
comment in `app/routers/strategy_synthesis.py`. Do not repeat it here — include
`DELETE /agents/tech-regulation/candidate-work/{key}` from the start.

### Agent 5 integration

Agent 5's Pass 1 currently discovers candidates from upstream report markdown.
It should **additionally** read `tr_candidate_work` rows directly for the
selected upstream Tech & Regulation run, and treat them as pre-structured
candidates — no parsing.

Keep the two populations distinguishable in Agent 5's output: a candidate
derived from structured candidate work carries its driver and date; one
inferred from prose does not. Say which is which.

**This is a change to Agent 5.** Keep it minimal and additive. Do not refactor
Pass 1's existing discovery.

---

## Part 2 — The agent

`tech_regulation/` mirroring `market_insights/`:

- `standards.py` — role, scope boundary, the implication / candidate work /
  recommendation distinction, evidence standard, source precedence, do-not-
  invent rules
- `prompts.py` — system prompt and per-report prompts
- `reports.py` — nine `ReportSpec` objects
- `scoping.py` — assemble the applicability envelope from the tables, render it
  for the prompt, and determine the operating state
- `agent.py` — orchestration
- `config.py`

### Single pass, one call per report

Market Insights' pattern, not Agent 5's. There is no deterministic computation
here — no scores, no utilisation, no arithmetic. The model researches and
writes.

**One streamed call per report**, as Market Insights does and as Agent 5's
Pass 2 does. Do not generate all nine in one call.

### Candidate work extraction

Candidate work appears in report prose *and* as structured rows. Generate it
once, structurally, then render it into the reports — not the other way round.

Suggested: a dedicated structured call after the research phase and before
report writing, emitting candidate work against the five-field schema with
forced tool choice, validated with Pydantic. Reports then narrate from it.

**Apply the lessons from Agent 5's Pass 1:**
- Stream, with an adequate token ceiling
- Reject `stop_reason == "max_tokens"` before parsing — a truncated tool input
  is a fragment, not an answer
- Log `stop_reason` and output tokens on every attempt
- Retry once with the validation error appended, then fail with a clear error
- **Validate completeness, not just schema.** An item missing `driver`,
  `applicability` or `work_implied` is not emitted. An item with a null
  `work_date` must carry `date_absent_reason`

### Operating state

`scoping.py` determines `scoped` / `partially_scoped` / `unscoped` and the
agent states it in the first line of every run.

**An unscoped run must be unmissable** — a reader must never mistake an
industry survey for their own regulatory obligations. Suggest a distinct report
title prefix as well as the first-line statement.

### What must not be inferred

Effort, duration, cost or reach for candidate work. Priority or ranking. Legal
obligation beyond the document. TRLs not established by a source. Commercial
viability from patent activity.

---

## Part 3 — Endpoints

Follow `app/routers/market_insights.py`. **Tenant-scoped; 404 not 403.**

```
GET/PUT  /agents/tech-regulation/scope/categories
GET/PUT  /agents/tech-regulation/scope/jurisdictions
GET/PUT  /agents/tech-regulation/scope/certification-basis
GET/PUT  /agents/tech-regulation/scope/platforms
GET/PUT  /agents/tech-regulation/scope/standards
GET/PUT  /agents/tech-regulation/scope/suppliers
GET/PUT  /agents/tech-regulation/scope/domains
GET/PUT  /agents/tech-regulation/scope/exclusions
GET      /agents/tech-regulation/scope/state       scoped | partially | unscoped, with what is missing and its cost
POST     /agents/tech-regulation/runs
GET      /agents/tech-regulation/runs
GET      /agents/tech-regulation/runs/{run_id}/reports
GET      /agents/tech-regulation/runs/{run_id}/export.docx
GET      /agents/tech-regulation/candidate-work
PATCH    /agents/tech-regulation/candidate-work/{key}
DELETE   /agents/tech-regulation/candidate-work/{key}
```

`/scope/state` mirrors Agent 5's `/readiness`: it returns what is missing **and
what that costs**, using the degradation table in the scoping spec. Note the
bug fixed in `b4f3282` — consequence text must be empty when an item is set.

CSV import is optional for v1. The envelope is small enough for forms.

**A run is never blocked by incomplete scoping.** It degrades and says so.

---

## Part 4 — Frontend

Per-agent modules, shared shell — the structure established in Part 6 of the
Agent 5 build. `techRegulation/` alongside `marketInsights/` and
`strategySynthesis/`, with the shared `reportWorkspace/` shell.

### Scoping screen

Eight sections, form-based. Each shows status and the consequence from
`/scope/state`, never a bare badge.

**The operating state is shown prominently at the top** — scoped, partially
scoped, or unscoped, with what unscoped means.

Certification basis and platforms are naturally tabular; use repeatable rows
rather than free text.

### Report workspace

Reuse the shared shell. Four new exhibit renderers in this agent's own registry
instance, physically separate from the others:

- **Maturity ladder** — four stacked tiers, Investigate at the top through
  Deployed at the bottom. Not a radar or radial chart
- **Evolution timeline** — horizontal, year axis, stage-labelled entries
- **Ecosystem map** — network graph. The most work of the four; a simple
  layered layout is sufficient, do not pull in a heavy graph library
- **Candidate work table** — driver, date, applicability, work implied, status,
  with the status actions

All render from structured data. **No ASCII art.** Fall back to a table, never
to character art.

### Candidate work actions

From the candidate work table and Report 1's consolidated list: mark under
review, accepted or dismissed with a reason.

---

## Part 5 — Testing

- Scoping assembly: scoped, partially scoped and unscoped states produce the
  right operating state and consequence text
- Candidate work validation: an item missing a required field is rejected; a
  null `work_date` without `date_absent_reason` is rejected; truncated
  structured output is rejected before parsing
- Persistence: a dismissed candidate work item rediscovered in a later run
  keeps its status and reason; only genuinely new keys get `new`
- Export: a Tech & Regulation run exports with the correct cover label, and
  Market Insights' and Agent 5's own export tests pass unchanged
- Endpoints: cross-tenant 404, incomplete scoping still runs, `/scope/state`
  returns empty consequence for set items
- Agent 5 integration: structured candidate work from a Tech & Regulation run
  reaches Agent 5's candidate population, distinguishable from prose-derived
  candidates
- Follow `tests/conftest.py`. **Run the suite in more than one file order**

---

## Out of scope

- Do not build Voice of Customer or Product Sustainment
- Do not change Market Insights
- Do not refactor Agent 5 beyond the additive candidate work read
- Do not add run-to-run change detection — noted as a gap
- Do not add auth, CORS, DNS or infrastructure changes

---

## Deployment notes

- New dependencies pinned in `requirements.txt`
- **`Base.metadata.create_all` creates new tables but does not alter existing
  ones.** New tables are fine; any column added to an existing table needs a
  manual `ALTER TABLE` on production first. This bit on 18 Sept with
  `brief_files.columns`. If the Agent 5 integration requires a column change,
  say so explicitly in the PR
- Backend deploy is `git pull`, `pip install`, `systemctl restart loom-api`
- **Frontend is a separate deploy.** Merging does not ship it
- **Push as part of committing.** Several commits this project have sat
  unpushed, and the server pulled stale code as a result
- Watch `free -h` during the first real run and report what you see. The
  instance is 414MB with 2GB swap; Agent 5's full synthesis peaked at 75Mi swap

---

## Definition of done

- [ ] Nine reports produced; 9 and 10 noted as deferred in the output
- [ ] Operating state stated in the first line of every run; unscoped is
      unmissable
- [ ] Candidate work persisted as structured rows with all five required fields
- [ ] No effort, cost, duration or priority anywhere in candidate work
- [ ] Null `work_date` always carries `date_absent_reason`
- [ ] Dismissed candidate work is not resurrected; DELETE exists
- [ ] Agent 5 reads structured candidate work directly, distinguishable from
      prose-derived candidates
- [ ] Exclusions honoured and stated, never silently applied
- [ ] Reports render from structured data; no ASCII art
- [ ] Word export works with the correct cover label
- [ ] Suite passes in multiple file orders
- [ ] Committed, pushed, merged via PR
