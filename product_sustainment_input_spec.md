# Agent 4 — Product Sustainment: input specification

Supersedes the input assumptions in `product_sustainment_prompt_draft_v1.md`,
which were written from the original specification before real industry output
was available. Where the two differ, this document is correct.

---

## What changed, and why it matters

The original specification described a "multi-level BOM" with quantity-per-unit
at every level, which implies a tree and a traversal. The real structure is not
a tree.

| Original assumption | Actual structure |
|---|---|
| Multi-level BOM, arbitrary depth | **Exactly three levels**: LRU → Level 1 (circuit card assemblies) → Level 2 (processors, FPGAs, resistors, amplifiers) |
| Parent-child, implicitly one-to-many | **Many-to-many at both joins.** A component sits in several assemblies; an assembly sits in several LRUs |
| Demand per part number at any level | **Demand at LRU level only.** Everything below is derived |
| Obsolescence triggered by EOL notices | **Four risk categories**, of which EOL is one |
| Inventory aggregated by level | **Inventory by location and form**, across multiple sites |
| Month-by-month depletion, month reported | **Monthly internally, year-end reported**, insights monthly where available |
| BOM file format undecided | **Matrix format**: rows are parts, columns are parents, cells are quantity |

**The consequence that matters most:** because the structure is many-to-many,
a component's depletion is driven by demand from *every* LRU that consumes it,
through every path. Examining one LRU in isolation shows a position that does
not exist. Total draw across all paths must be computed before any single LRU's
position means anything.

This is also why the calculation belongs in code rather than in the model. The
summation is across paths, not down a branch, and a plausible-looking error here
drives a six-figure last-time-buy.

---

## Part 1 — Product structure

### 1.1 The three levels

**LRU** — the line-replaceable unit the customer sells and supports.

**Level 1** — assemblies within an LRU. Typically circuit card assemblies.

**Level 2** — components within a Level 1 assembly. A specific processor, FPGA,
resistor or amplifier. Each has a unique identifier.

Level 2 is where end-of-life designations land. Manufacturers discontinue
components, not assemblies — and an LRU does not go obsolete directly, it
becomes unsupportable because a Level 2 component inside it did.

```
lru_id, lru_name, product_line, program, status
level1_id, level1_name, description
level2_id, level2_name, description, manufacturer, manufacturer_part_number
```

### 1.2 LRU to Level 1 mapping

Matrix. Rows are LRUs, columns are Level 1 assemblies, cells are quantity per
unit. An empty cell means that assembly is not in that LRU.

```
LRU,    XXX1, XXX2, XXX3, XXX4, XXX5, XXX6
LRU1,   1,    ,     ,     ,     ,
LRU2,   ,     1,    1,    ,     ,
LRU3,   ,     ,     1,    1,    ,
LRU5,   ,     ,     ,     1,    1,
```

**Many-to-many.** One assembly appears in several LRUs; one LRU contains
several assemblies. Both are normal.

### 1.3 Level 1 to Level 2 mapping

Same shape. Rows are Level 2 components, columns are Level 1 assemblies, cells
are quantity per unit.

```
Level2,       Aaa-L1, Bbb-L1, Ccc-L1, Ddd-L1
Aaa-level2,   ,       1,      2,      2
Ccc-level2,   1,      2,      1,
Ddd-level2,   ,       1,      ,       1
Eee-level2,   1,      ,       2,      2
```

### 1.4 Why matrix rather than parent-child rows

This is how customers export it. The alternative — a row per relationship —
is equivalent and the ingest should accept either, but the matrix is what
arrives from a spreadsheet and should be the documented format.

**Validation on upload:** every column header resolves to a declared Level 1
id; every row label resolves to a declared LRU or Level 2 id. A reference that
resolves to nothing is an error, not a warning — a missing link silently
removes demand from the calculation.

---

## Part 2 — Inventory

### 2.1 Shape

Inventory exists at Level 1 and Level 2, across multiple locations, in several
forms.

```
part_id, part_level, location, form, quantity, as_of
```

`form` is customer-defined. Common values: `raw`, `in_process`, `finished`,
`consigned`, `quarantine`. Do not impose a controlled list — customers
designate their own and the agent uses them verbatim.

`location` is customer-defined: plant, warehouse, supplier site.

### 2.2 Pipeline quantities

Tracked separately from on-hand, and all treated as available.

```
part_id, open_po_qty, supplier_qty, supplier_on_order_qty, supplier_wip_qty, as_of
```

**Available inventory = on-hand + open POs + supplier on-order + supplier WIP.**

Open POs are assumed accepted with full certainty. Arrival timing is treated as
immediate, on the basis that runout dates are typically far enough out that
receipt timing does not move them.

**Report the composition**, so a reader can see what rests on orders rather than
stock. A position that is 80% open PO is a different position from one that is
80% on-hand, even when the total is identical.

### 2.3 When the timing assumption is thin

The immediate-arrival assumption holds until a component is close to runout.

**Where the calculated runout falls within the typical lead time for that part,
flag it**: state that open-PO timing has been treated as immediate and may not
hold. This is exactly the case where the number drives an urgent decision, so
the assumption should be visible rather than buried.

Lead time may be supplied per part; where it is not, state that the check could
not be performed.

### 2.4 Inventory roll-up

Stock held at a higher level counts toward lower-level supply. Twenty spare
circuit cards each containing four of a resistor represent eighty additional
resistors, on top of raw resistor stock.

Roll up through the matrices, not down a branch.

---

## Part 3 — Demand

### 3.1 Shape

**LRU level only.** One row per LRU, one column per year.

```
LRU,  2025, 2026, 2027, 2028, 2029, 2030, ...
xxx,  2178, 2470, 2494, 2042, 2000, 2000
yyy,  190,  161,  ,     ,     ,
zzz,  4,    ,     ,     ,     ,
aaa,  2,    ,     ,     ,     ,
bbb,  ,     ,     ,     ,     ,
```

**A blank cell means zero demand that year, not missing data.** An LRU with an
entirely blank row has no forecast demand and must still appear — its absence
from the calculation is a finding, not an omission.

### 3.2 Derivation

Demand flows downward through the matrices:

```
Level 1 annual demand[j]  =  Σ over LRUs i  of  ( LRU_demand[i] × LRU_to_L1[i][j] )
Level 2 annual demand[k]  =  Σ over L1s j   of  ( L1_demand[j]  × L1_to_L2[k][j] )
```

**This summation across paths is the whole point.** A Level 2 component in three
assemblies, which between them go into five LRUs, is depleted by all five.

### 3.3 Spares and direct demand

Where a Level 1 or Level 2 part is also sold directly — as a spare, or into
aftermarket — that demand is **additional** to derived demand, not a
replacement for it. Supply it as an optional direct demand grid at that level
and add the two.

### 3.4 Where demand could come from instead

Demand may be pulled from a connected CRM or ERP rather than uploaded. Not
available today; listed so the direction is clear.

---

## Part 4 — Risk flags

The original specification treated end-of-life as the trigger. Four categories
drive a runout calculation, and they imply different responses.

```
part_id, risk_type, risk_detail, source, source_date, lifecycle_status,
last_time_buy_date, last_delivery_date, qualified_alternate_part_id, qualified_alternate_status
```

| Risk type | Meaning | What it implies |
|---|---|---|
| `end_of_life` | Manufacturer has announced discontinuation | A last-time-buy window with a closing date |
| `single_source` | One qualified supplier | No buy window; exposure is standing until a second source is qualified |
| `custom` | Made to the customer's own specification | Supplier leverage, and no market alternate by definition |
| `at_risk_region` | Manufactured where geopolitical or supply risk is material | Standing exposure with no date, unless an event supplies one |

`lifecycle_status` carries the manufacturer's own designation where available.
Common codes include **NFND** (not for new design) and **MXSTK** (max stock).
These are early warning — a part marked NFND is not yet EOL but will be.

### 4.1 Alternates — two different things

Knowing an alternate exists means knowing a part is form-fit-function
compatible **and** qualified for this application. The first is researchable.
The second is specific to the customer's certification basis and test evidence,
and no public source knows it.

**Qualified alternates are customer-supplied.** A second source already through
the customer's own qualification. Only they know this.

```
part_id, qualified_alternate_part_id, qualified_alternate_status, qualified_date
```

`qualified_alternate_status`: `qualified` · `in_qualification` · `approved_for_new_design_only`

**Candidate alternates are agent-found.** From manufacturer-recommended
replacements, pin-compatible families and distributor cross-references. The
agent reports these as **candidates for qualification**, with the evidence and
its limits — never as drop-in replacements.

The distinction decides what the work is:

| Situation | What phase-out means |
|---|---|
| Qualified alternate exists | A sourcing change. Available now |
| Candidate alternate found, not qualified | A qualification project with its own effort and schedule |
| No candidate found | Redesign, or buy and accept |

**The agent must never present a candidate alternate as though it were
qualified.** A pin-compatible part that has not been through environmental
qualification is not a solution, and treating it as one is the kind of error
that reaches a procurement decision.

---

## Part 5 — Reliability and quality evidence

Free-text documents from customer support, mined rather than parsed.

```
document_type, filename, as_of, period_covered, is_sample
```

Types: support tickets, field service reports, warranty claims, failure
reports, field investigation reports, return authorisations.

### 5.1 Level translation

**Findings may arrive at LRU level or Level 1 level, and must be translated to
LRU level for reporting.** A failure attributed to a circuit card assembly
affects every LRU containing that assembly — which the matrix already knows.

State when a finding has been rolled up this way, and which LRUs it reached.
A reader seeing an LRU-level failure rate needs to know whether it was observed
there or inherited from an assembly.

### 5.2 Same rules as Voice of Customer evidence

Text, PDF and CSV. A sample is not a census. Frequency requires counts. Do not
summarise verbatims — the language is the evidence.

---

## Part 6 — Fleet and configuration

Carried from the original specification, unchanged.

```
fleet_roster:    unit_id, lru_id, in_service_date, utilisation, environment, operator_segment
maintenance:     unit_id, lru_id, event_date, event_type, time_in_service, downtime
configuration:   unit_id, lru_id, as_maintained_config, as_designed_baseline
knowledge:       capability, components_affected, people_count, documentation_status
```

**The knowledge assessment has no data source.** It is a customer judgement
about where specialised repair knowledge sits with few people, or where tooling
and test equipment are being discontinued. Without it the analysis is
unavailable — it will not be inferred from headcount or age data.

---

## Part 7 — The runout calculation

Deterministic. **Computed in code, not by the model.**

1. **Resolve the matrices.** Validate every reference. A dangling reference
   silently removes demand.
2. **Derive demand at every level**, summing across all paths (§3.2), plus any
   direct demand (§3.3).
3. **Aggregate available inventory** per part: on-hand across all locations and
   forms, plus open POs, supplier on-order and supplier WIP. Roll up
   higher-level stock through the matrices (§2.4).
4. **Interpolate annual demand to monthly**, evenly across twelve months.
5. **Deplete month by month** from the current date.
6. **Runout is the first month in which projected inventory reaches zero.**
7. **Report year-end positions** for each projection year alongside the monthly
   runout date.
8. **Compare against the last-time-buy window** where one exists. A runout
   falling before the window closes is critical: the current buy opportunity is
   the only one remaining.
9. **Check the lead-time assumption** (§2.3) and flag where it is thin.
10. **Cascade upward.** Every Level 1 assembly and every LRU containing an
    at-risk part inherits the exposure, through the matrices.

### Precision

**Monthly internally. Year-end reported. Insights monthly where available.**

A year is too wide a bucket for a last-time-buy decision, and the Power BI
convention of year-end columns is a reporting format rather than the working
precision.

### When demand exceeds supply

Where total demand across all consuming LRUs exceeds available inventory, the
component runs out — and **which LRU goes unserved is a priority decision
nobody has stated.**

Do not assume an allocation. Report the shortfall, and **flag every competing
LRU**, so Agent 5 sees the full blast radius rather than one affected line.

### Insufficient data

A part lacking a BOM link, a demand path or inventory data gets **no runout
date**. List it in a separate section — never omit it, because a part missing
from the report reads as safe.

---

## Part 8 — Output contract

### 8.1 The component table

Matching the format customers already use:

| Column | Source |
|---|---|
| Component, description | Level 2 master |
| Quantity on hand | Inventory, summed across locations and forms |
| Open POs | Pipeline |
| Supplier quantity, on order, WIP | Pipeline, separately |
| Run-out year, and month | Calculated |
| End inventory by year | Calculated, one column per projection year |
| Risk type and lifecycle status | Risk flags |
| Affected LRUs | Derived through the matrices |

Filterable by component, LRU, product line, program, lifecycle status and
run-out year.

### 8.2 Candidate work for Agent 5

Product Sustainment emits **structured candidate work**, as Technology &
Regulation does — not textual findings. A runout is a dated event with money
attached, which is what makes it schedulable.

Each item carries:

| Field | Content |
|---|---|
| `driver` | The named part, its risk type, and the source — a PCN number, an EOL notice, a supplier statement |
| `date` | Runout month, or last-time-buy window close, whichever binds first. Where neither exists — a standing single-source or region exposure — state `none established` and why |
| `applicability` | **Every affected LRU**, not just one. Plus the Level 1 assemblies in the path |
| `quantity` | Units required to cover demand through end of life. This is what a last-time-buy would be for |
| `qualified_alternate` | Customer-supplied second source, already qualified. Makes phase-out available now |
| `candidate_alternates` | Agent-found, with evidence. Makes phase-out a qualification project, not a swap |
| `work_implied` | `last_time_buy`, `alternate_qualification`, `redesign`, `inventory_rebalance`, or `monitor` |
| `basis` | Evidence classification and confidence |

**This agent does not recommend buy versus phase out.** It supplies the date,
the quantity, the blast radius, the risk category, any qualified alternate and
any candidate alternates with their evidence — what Agent 5 needs to weigh a
last-time-buy against a qualification project against a redesign against
accepting the risk, scored against capacity and objectives this agent cannot
see.

Note the four options are genuinely different pieces of work. A qualified
alternate is a sourcing change; a candidate alternate is a qualification
project; a redesign is an engineering programme. Collapsing them into "phase
out" would hide the distinction that decides the cost.

---

## Part 9 — Degradation

The run is never blocked. Each absence has a stated consequence.

| Missing | Consequence |
|---|---|
| **Both BOM matrices** | **No runout calculation at all. The single most consequential omission** |
| LRU to Level 1 matrix | Level 1 and Level 2 demand cannot be derived |
| Level 1 to Level 2 matrix | Component-level exposure cannot be traced; analysis stops at assembly level |
| Demand | No runout dates. Risk flags reported without timing — standing context, not schedulable |
| Inventory | No runout dates. Risk and exposure reported without position |
| Pipeline quantities | Runout computed from on-hand only; stated, and will be pessimistic |
| Risk flags | Only parts with public EOL notices are flagged; single-source, custom and region exposure invisible |
| Lead times | Lead-time assumption check unavailable |
| Part list only, no BOM | **Still useful.** Lifecycle status and candidate alternates for the listed parts — an obsolescence and exposure scan, not a sustainment analysis |
| Qualified alternates | Phase-out options reported as qualification projects only; the agent cannot know what is already qualified |
| Reliability documents | No failure clustering, MTBUR or MTTR |
| Fleet roster | No aging fleet analysis |
| Configuration baseline | No drift analysis |
| Knowledge assessment | Unavailable. Not inferred |

---

## Part 10 — Shared with other agents

| Field | Sustainment | Tech & Reg | VoC |
|---|---|---|---|
| Product categories | yes | yes | yes |
| Platforms | yes | yes | no |
| Supplier watch list | yes | yes | no |
| Part lists and BOM | yes | no | no |
| Customer segments | partially | no | yes |

The supplier watch list is the same list Technology & Regulation uses. Where
that agent is configured, read it rather than asking twice — and note that
Tech & Regulation's supplier monitoring surfaces the PCNs and EOL notices that
become this agent's risk flags.

**That is the strongest cross-agent link in the platform:** Technology &
Regulation finds the discontinuation, Product Sustainment calculates what it
costs and when, Agent 5 decides what to do.

---

## Part 11 — Worked example: Arden Actuation Systems

Deliberately small, to show the matrix structure doing its work.

**LRUs:** AR-FIN (missile fin actuator), AR-TVC (TVC actuator), AR-UTIL
(utility actuator).

**Level 1:** CCA-MC (motor controller card), CCA-PWR (power stage card),
CCA-SENS (sensor interface card).

**Level 2:** GaN-650 (Infineon GaN device), FPGA-A, RES-PREC (precision
resistor).

**LRU to Level 1:**

```
LRU,      CCA-MC, CCA-PWR, CCA-SENS
AR-FIN,   1,      1,       1
AR-TVC,   1,      2,
AR-UTIL,  1,      ,        1
```

**Level 1 to Level 2:**

```
Level2,    CCA-MC, CCA-PWR, CCA-SENS
GaN-650,   ,       6,
FPGA-A,    1,      ,        1
RES-PREC,  12,     8,       4
```

**The point:** GaN-650 sits only in CCA-PWR. But CCA-PWR is in AR-FIN (one
each) and AR-TVC (two each). So GaN-650 depletion is driven by
`6 × (AR-FIN demand + 2 × AR-TVC demand)` — and anyone examining AR-FIN alone
sees a third of the true draw.

GaN-650 is single-sourced in the Technology & Regulation envelope, and the
Infineon discontinuation that agent found in October 2026 is its risk flag.
Committed project P-03 in the Agent 5 brief is the GaN redesign. **All three
agents meet on this one component.**

---

## Open questions

1. **Direct demand at Level 1 and Level 2.** §3.3 allows it as optional. Is
   spares demand at component level common enough to be a first-class input, or
   genuinely an edge case?
2. **Lead times.** Needed for the §2.3 assumption check. Per part, per supplier,
   or a default?
3. **Candidate alternate depth.** Manufacturer replacement guidance and
   distributor cross-references are reachable by web search; a parametric
   component database would find more. Is the shallower search enough for v1?
4. **More than three levels.** The structure is three levels today. If a
   customer has four, does the matrix pattern simply extend, or does the ingest
   need to know?
5. **Inventory as-of dates.** Multiple locations may be counted at different
   times. Does a single as-of per upload suffice, or is it per row?
6. **Allocation priority.** §7 reports shortfall without assuming allocation.
   Would customers want to supply an LRU priority order, so the agent can show
   who would be served first?
