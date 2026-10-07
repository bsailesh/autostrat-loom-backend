# Briefing: Build Agent 4 — Product Sustainment

Full build: product structure and inventory input, evidence upload, the runout
computation, agent package, endpoints, frontend.

**Read first, in this order:**

1. `product_sustainment_input_spec.md` — the input contract. **This supersedes
   the input assumptions in the prompt draft**, which were written before real
   industry output was available
2. `product_sustainment_prompt_draft_v1.md` — the agent's operating
   specification, excluding its input assumptions
3. `market_insights_agent_spec.md` — the shared standards

This agent is the only one that resembles **Agent 5** structurally: it has a
deterministic compute module. Use `strategy_synthesis/compute.py` as the
reference for that, and `tech_regulation/` for everything else.

**Do not start coding until you have given me an implementation plan and I have
approved it.** This is the second-largest feature in the platform.

---

## Three decisions already made

**1. Nine reports, not ten.** Build Reports 1–8 and 10, omitting Report 9 (the
sustainment trend digest), which needs run-to-run change detection the platform
does not have. Note it as deferred in the output rather than dropping it
silently.

**2. A deterministic compute module.** The runout calculation is matrix
arithmetic across potentially thousands of parts. Same reasoning that produced
Agent 5's `compute.py`: the model judges, code computes. A plausible-looking
arithmetic error here drives a six-figure last-time-buy.

**3. Structured candidate work, as Technology & Regulation emits.** A runout is
a dated event with a quantity attached, so it converts cleanly. Not textual
findings as Voice of Customer produces.

---

## Part 1 — The thing most likely to be got wrong

**The BOM is a matrix, not a tree.**

Level 2 to Level 1 is many-to-many. Level 1 to LRU is many-to-many. A component
sits in several assemblies; an assembly sits in several LRUs.

**Therefore a component's depletion is driven by demand from every LRU that
consumes it, through every path.** Examining one LRU in isolation shows a
position that does not exist.

The worked example in the input spec Part 11: `GaN-650` sits only in `CCA-PWR`,
but `CCA-PWR` is in `AR-FIN` once and `AR-TVC` twice. Depletion is
`6 × (AR-FIN demand + 2 × AR-TVC demand)`. Anyone examining `AR-FIN` alone sees
a third of the true draw.

Every part of this build follows from that. If the implementation treats the
BOM as traversable, it is wrong.

---

## Part 2 — Data model

Follow `app/models.py` conventions. Every table tenant-scoped.

**Reuse `agent_runs` and `agent_reports`** via
`agent_type="product-sustainment"`. Add it to `agent_label_for()`.

**Note:** an existing test uses `product-sustainment` as its example of an agent
with no export label. That assumption breaks here. This is the last agent, so
the test needs a different approach rather than another substitution.

### Structure

**`ps_lrus`** — lru_id, lru_name, product_line, program, status

**`ps_level1`** — level1_id, level1_name, description

**`ps_level2`** — level2_id, level2_name, description, manufacturer,
manufacturer_part_number

**`ps_lru_level1`** — lru_id, level1_id, quantity_per_unit

**`ps_level1_level2`** — level1_id, level2_id, quantity_per_unit

The two mapping tables are stored as edges even though they are **uploaded as
matrices**. See Part 3.

### Inventory

**`ps_inventory`** — part_id, part_level (`lru` / `level1` / `level2`),
location, form, quantity, as_of

`location` and `form` are customer-defined strings used verbatim. Do not impose
a controlled list.

**`ps_pipeline`** — part_id, open_po_qty, supplier_qty, supplier_on_order_qty,
supplier_wip_qty, as_of

**`ps_lead_times`** — part_id, lead_time_days. Optional; needed for the
assumption check in Part 4.

### Demand

**`ps_demand`** — lru_id, year, quantity

One row per LRU per year. **A missing row means zero demand that year, not
missing data.** An LRU with no rows at all still appears in reporting.

**`ps_direct_demand`** — part_id, part_level, year, quantity. Optional. Spares
or aftermarket demand at Level 1 or Level 2, **added to** derived demand, never
replacing it.

### Risk

**`ps_risk_flags`** — part_id, risk_type (`end_of_life` / `single_source` /
`custom` / `at_risk_region`), risk_detail, source, source_date,
lifecycle_status, last_time_buy_date, last_delivery_date

`lifecycle_status` carries the manufacturer's designation — `NFND` (not for new
design), `MXSTK` (max stock), and others. Free text; these are early warning,
not yet EOL.

**`ps_qualified_alternates`** — part_id, alternate_part_id, status
(`qualified` / `in_qualification` / `approved_for_new_design_only`),
qualified_date

**Customer-supplied only.** Candidate alternates the agent finds are not stored
here — they are research findings, reported with their evidence, and must never
be presented as qualified.

### Fleet, configuration, evidence

**`ps_fleet`** — unit_id, lru_id, in_service_date, utilisation, environment,
operator_segment

**`ps_maintenance`** — unit_id, lru_id, event_date, event_type,
time_in_service, downtime

**`ps_configuration`** — unit_id, lru_id, as_maintained_config,
as_designed_baseline

**`ps_knowledge`** — capability, components_affected, people_count,
documentation_status. Customer judgement; no data source produces it

**`ps_evidence_files`** — same shape as `voc_evidence_files`. Reuse that
pattern rather than inventing a second one

### Candidate work

**`ps_candidate_work`** — mirroring `tr_candidate_work`, with additions

- candidate_key, driver, work_date, date_basis, date_absent_reason
- applicability — **every affected LRU plus the Level 1 assemblies in the
  path**, as JSON
- `quantity_required` — units to cover demand through end of life
- `qualified_alternate_part_id` (nullable)
- `candidate_alternates` — JSON, agent-found, each with its evidence
- work_implied — `last_time_buy` / `alternate_qualification` / `redesign` /
  `inventory_rebalance` / `monitor`
- classification, confidence, source, source_date
- status, dismissal_reason, first_seen_run_id, last_seen_run_id

**Include `DELETE` from the start**, as Tech & Regulation does.

---

## Part 3 — Matrix ingest

New format. Neither existing ingest handles it.

### Upload shape

Rows are parts, columns are parents, cells are quantity. Empty cell means no
relationship.

```
LRU,      CCA-MC, CCA-PWR, CCA-SENS
AR-FIN,   1,      1,       1
AR-TVC,   1,      2,
AR-UTIL,  1,      ,        1
```

Parse into edge rows. Store as edges; the matrix is a transport format.

### Validation

| Check | Severity |
|---|---|
| Every column header resolves to a declared Level 1 id | **Error** |
| Every row label resolves to a declared LRU or Level 2 id | **Error** |
| Cell values are non-negative integers or empty | Error |
| A part appears in no matrix | Warning — it will have no demand path |
| Demand references an LRU not in `ps_lrus` | Error |

**The reference checks are errors, not warnings.** A dangling reference
silently removes demand from the calculation, which is the same class of failure
as the bucket-name mismatch in Agent 5's ingest — invisible, and it corrupts the
analysis the agent exists to perform.

Accept an edge-list format as an alternative upload. The matrix is what arrives
from a spreadsheet; the edge list is what arrives from a PLM export.

### Templates

Generate from declared ids, so headers are correct by construction.

---

## Part 4 — The computation module

`product_sustainment/compute.py`. Pure functions, no LLM, no database. Fully
unit-testable, and **test it thoroughly** — this is where correctness lives.

### 4.1 Demand derivation

```
level1_demand[j][year]  =  Σ over LRUs i      ( lru_demand[i][year] × qty_lru_l1[i][j] )
level2_demand[k][year]  =  Σ over Level1s j   ( level1_demand[j][year] × qty_l1_l2[j][k] )
```

Plus any direct demand at that level, added not substituted.

**The summation across paths is the whole point.** Do not short-circuit it.

### 4.2 Inventory aggregation

Available inventory for a Level 2 part:

```
raw Level 2 stock
+ Σ over Level1s j   ( level1_inventory[j] × qty_l1_l2[j][k] )
+ Σ over LRUs i      ( lru_inventory[i] × Σ over j ( qty_lru_l1[i][j] × qty_l1_l2[j][k] ) )
+ open POs + supplier on-order + supplier WIP
```

All pipeline quantities are treated as available with immediate arrival.

**Return the composition**, not only the total. A position 80% dependent on open
POs is different from one 80% on-hand.

### 4.3 Depletion

1. Interpolate annual demand evenly across twelve months
2. Deplete month by month from the current date
3. **Runout is the first month projected inventory reaches zero**
4. Report year-end position for each projection year alongside the monthly date

**Monthly internally, year-end reported, insights monthly where available.** A
year is too wide for a last-time-buy decision; the year-end columns are a
reporting convention, not the working precision.

### 4.4 Lead-time assumption check

Where the calculated runout falls within the part's lead time, flag that open-PO
timing was treated as immediate and may not hold.

Where no lead time is supplied, state the check could not be performed.

### 4.5 Shortfall and competing demand

Where total demand across all consuming LRUs exceeds available inventory:

- Report the shortfall quantity
- **Return every competing LRU**, not the first or the largest
- Do not assume an allocation — which LRU goes unserved is a priority decision
  nobody has stated

### 4.6 Upward cascade

Every Level 1 assembly and every LRU containing an at-risk part inherits the
exposure, through the matrices. Return the full affected set.

### 4.7 Insufficient data

A part lacking a BOM link, a demand path or inventory gets **no runout date**.
Return it in a separate collection with the reason. **Never omit it** — a part
missing from the report reads as safe.

---

## Part 5 — The agent

`product_sustainment/` mirroring `tech_regulation/`, plus `compute.py`:

- `standards.py` — role, scope boundary, options-not-decisions, evidence
  standard, do-not-invent
- `prompts.py`, `reports.py` (nine specs), `structure.py` (assemble the BOM and
  determine data completeness), `evidence.py`, `compute.py`, `agent.py`,
  `config.py`

Declare `WEB_SEARCH_TOOL_TYPE` locally.

### Two-pass where it matters

Not Agent 5's full two-pass. But the **candidate work extraction is structured**
and must apply every lesson from Agent 5's Pass 1 failure:

- Stream, with an adequate token ceiling
- **Reject `stop_reason == "max_tokens"` before parsing** — a truncated tool
  input is a fragment
- Log `stop_reason` and output tokens at warning level on every attempt
- **No default on the items list**, so a coerced fragment cannot validate as
  empty
- **`additionalProperties: false`**, so a misnamed field fails by name and the
  name reaches the retry prompt
- Unwrap a single wrapper key rather than retrying
- Validate completeness per item: an item missing `driver`, `applicability` or
  `work_implied` is dropped with a reason; a null `work_date` must carry
  `date_absent_reason`

**Completeness is per-item, not set-level.** Like Tech & Regulation, this agent
has no denominator — a run surfacing no candidate work is legitimate.

### Options, not decisions

Several reports call for recommendations. These are **engineering options with
their evidence**, never selections. Label the sections **Options**.

**This agent does not recommend buy versus phase out.** It supplies the date,
the quantity, the blast radius, the risk category, any qualified alternate and
any candidate alternates — what Agent 5 needs to weigh four genuinely different
pieces of work: a sourcing change, a qualification project, a redesign, or
accepting the risk.

### Candidate alternates

Research them from manufacturer replacement guidance, pin-compatible families
and distributor cross-references. Report as **candidates for qualification**,
with evidence and its limits.

**Never present a candidate alternate as qualified.** A pin-compatible part that
has not been through environmental qualification is not a solution, and that
error reaches procurement decisions.

### Evidence mining and level translation

Reliability and quality evidence is free text. Findings may arrive at LRU or
Level 1 level and **must be translated to LRU level** through the matrices.

State when a finding was rolled up and which LRUs it reached — a reader seeing
an LRU failure rate needs to know whether it was observed there or inherited.

---

## Part 6 — Endpoints

Follow `app/routers/tech_regulation.py`. Tenant-scoped; 404 not 403.

```
GET/PUT  /agents/product-sustainment/structure/lrus
GET/PUT  /agents/product-sustainment/structure/level1
GET/PUT  /agents/product-sustainment/structure/level2
POST     /agents/product-sustainment/structure/matrix/{which}   lru-level1 | level1-level2
GET      /agents/product-sustainment/structure/templates/{which}
POST     /agents/product-sustainment/files/{file_type}          inventory, pipeline, demand, risk, alternates, fleet, maintenance, configuration, lead-times
GET      /agents/product-sustainment/files
GET/PUT  /agents/product-sustainment/knowledge
POST     /agents/product-sustainment/evidence                   free-text documents
GET      /agents/product-sustainment/evidence
DELETE   /agents/product-sustainment/evidence/{id}
GET      /agents/product-sustainment/readiness
POST     /agents/product-sustainment/run
GET      /agents/product-sustainment/runs
GET      /agents/product-sustainment/runs/{run_id}/reports
GET      /agents/product-sustainment/runs/{run_id}/export.docx
GET      /agents/product-sustainment/candidate-work
PATCH    /agents/product-sustainment/candidate-work/{key}
DELETE   /agents/product-sustainment/candidate-work/{key}
```

`/readiness` returns what is missing **and what it costs**, from the
degradation table in the input spec Part 9. **Consequence text is empty for
items that are set** — the bug fixed in `b4f3282`.

**A run is never blocked.** It degrades and says so.

---

## Part 7 — Frontend

Per-agent module, shared shell. `productSustainment/` with its own exhibit
registry instance.

### Structure screen

LRU, Level 1 and Level 2 masters. Matrix upload for each mapping, with template
download as the primary action and validation results shown per upload.

**Show the derived picture after upload:** how many LRUs, assemblies and
components, and how many parts have no demand path. That last number is the one
that catches a bad matrix.

### Data screens

Inventory, pipeline, demand, risk flags, qualified alternates, lead times,
fleet, maintenance, configuration. Each with template download and validation.

Knowledge assessment is a form, not an upload — there is no source file.

### Evidence screen

Reuse the Voice of Customer pattern. Text, PDF, CSV.

### Report workspace

Shared shell, own registry. Renderers:

- **Runout table** — the primary exhibit. Component, description, on-hand, open
  POs, supplier quantities, runout year and month, end inventory by year, risk
  type, lifecycle status, affected LRUs. Filterable by component, LRU, product
  line, program, lifecycle status and runout year
- **Inventory depletion chart** — projected position by year per component
- **Failure trend lines** — one series per component or subsystem
- **Dependency and exposure map** — which LRUs a flagged component reaches

All from structured data. **No ASCII art.** Fall back to a table.

---

## Part 8 — Testing

**`compute.py` is the priority.** Cover:

- A component in multiple assemblies in multiple LRUs — the summation across
  paths. Use the input spec's `GaN-650` example, where the correct answer is
  `6 × (AR-FIN + 2 × AR-TVC)` and the naive answer is a third of it
- Inventory roll-up from LRU and Level 1 stock down to Level 2 equivalents
- Monthly depletion and the first-zero month
- Year-end positions alongside the monthly date
- Runout before and after the last-time-buy window
- Shortfall returning every competing LRU
- Lead-time check firing and, with no lead time, reporting unavailable
- Insufficient-data parts returned separately, never dropped
- Upward cascade reaching every affected LRU

Then: matrix ingest with a dangling reference failing loudly; candidate work
validation including the truncation case; persistence not resurrecting a
dismissed item; export with the correct cover label; cross-tenant 404;
incomplete data still runs.

Follow `tests/conftest.py`. **Run the suite in more than one file order**, and
note the `SessionFactory`-at-import trap logged there — this agent will have its
own service module and the same trap applies.

---

## Out of scope

- No connector implementation
- No parametric component database for alternate search
- No run-to-run change detection
- No shared Product Profile extraction
- Do not change other agents beyond `agent_label_for()` and the test noted in
  Part 2

---

## Deployment notes

- New dependencies pinned
- **`create_all` creates new tables but does not alter existing ones.** All
  tables here are new; say so in the PR
- Backend: `git pull`, `pip install`, `systemctl restart loom-api`
- **Frontend is a separate deploy**
- **Push as part of committing**
- Watch `free -h` during the first real run. The instance is 414MB with 2GB
  swap; a large BOM is the heaviest input the platform will have handled

---

## Definition of done

- [ ] Nine reports; Report 9 noted as deferred
- [ ] BOM treated as a matrix throughout; demand summed across all paths
- [ ] `compute.py` pure, tested, with the multi-path case covered explicitly
- [ ] Monthly runout, year-end positions reported
- [ ] Shortfall returns every competing LRU; no allocation assumed
- [ ] Insufficient-data parts listed separately, never omitted
- [ ] Dangling matrix references fail loudly at ingest
- [ ] Qualified and candidate alternates distinguished; a candidate is never
      presented as qualified
- [ ] Candidate work emitted structurally with quantity and full LRU
      applicability
- [ ] No buy-versus-phase-out recommendation anywhere
- [ ] Runs succeed with incomplete data and state the consequences
- [ ] Reports render from structured data; no ASCII art
- [ ] Word export works with the correct cover label
- [ ] Suite passes in multiple file orders
- [ ] Committed, pushed, merged via PR
