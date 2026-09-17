# Agent 5 — test output, prompt v2

**Test conditions identical to v1.** Prompt draft v2, decision brief strawman
v2, Market Insights run `df344207`. Subject: Meridian Avionics, fictional.

Purpose: check whether making the three high-value analyses *required* produces
them reliably, rather than depending on the model noticing.

---

## Report 1 — Strategic opportunity and project universe

### Key insights

- **Certification is oversubscribed at 115% while the portfolio appears to have
  1,244 weeks of headroom.** Three mandatory projects consume 180 of 277
  certification weeks, and the brief declares certification non-contractable.
  *(Confidence: High — calculated from supplied capacity data)*
- **Two of four strategic objectives are unserved or barely served.** SO-3 has
  no committed project. SO-4 is addressed only incidentally. *(Confidence: High)*
- **The selected framework may not be the best fit.** This market runs on dated
  compliance cohorts. WSJF is recommended for comparison — see Report 3.
  *(Confidence: Medium)*
- **Nine committed projects are scored. Twelve candidates are not**, lacking
  validated effort. Ordered below by evidence strength.
- **Four of six rationale types have no source agent.** Only Market Insights has
  run.

### Committed projects

| ID | Project | Type | HW | SW | SYS | CERT | Total | Mandatory | Evidence support |
|---|---|---|---|---|---|---|---|---|---|
| P-01 | CVR-25 Part 25 TSO certification | Compliance | 6 | 4 | 9 | 40 | 59 | Yes | Evidence-supported |
| P-02 | STC package — 5 regional jet types | Compliance | 20 | 15 | 48 | 125 | 208 | Yes | Evidence-supported |
| P-03 | Crash-survivable memory IC redesign | Sustainment | 130 | 18 | 40 | 20 | 208 | No | User-provided, no upstream evidence |
| P-04 | ULB dual-source qualification | Sustainment | 22 | 0 | 9 | 10 | 41 | No | Partially supported |
| P-05 | Low-SWaP variant, business aviation | New product | 150 | 60 | 73 | 40 | 323 | No | Evidence-supported |
| P-06 | Download tooling and workflow refresh | Service | 0 | 38 | 8 | 2 | 48 | No | Evidence-supported |
| P-07 | FDR capacity extension to 200 h | Enhancement | 70 | 45 | 32 | 15 | 162 | No | Partially supported |
| P-08 | DO-326A airworthiness security | Compliance | 5 | 30 | 27 | 15 | 77 | Yes | User-provided, no upstream evidence |
| P-09 | Production line capacity expansion | Manufacturing | 95 | 10 | 35 | 10 | 150 | No | Evidence-supported |

### Candidates — not scored

**Ordering basis: evidence strength** — the classification and confidence of
supporting upstream findings, and how many independent findings converge. This
is not a ranking and implies no priority.

| # | Candidate | Origin | Evidence | Strength |
|---|---|---|---|---|
| C-01 | Airframer qualification programme | Discovered — Market | Airbus selected a single qualified 25 h CVR and moved supply into its own service bulletin; advantage sits at the airframer layer, not the datasheet | FACT High, 3 converging findings |
| C-06 | Cargo and combi operator campaign | Discovered — Customer demand | Statutory cohort explicitly includes all-cargo and combi derivatives | FACT High, 1 finding |
| C-07 | Installation capacity / shop-slot partnership | Discovered — Customer demand | FAA states 25 h units swap "without much difficulty"; industry estimates put retrofit labour at ~6× line-fit. Contradiction unresolved in the public record | FACT High but contested, 2 findings |
| U-02 | Direct-to-operator retrofit channel | Customer — VP Sales | No engineering scope. Corroborated by C-01 and C-07 | Customer + 2 converging discovered findings |
| C-04 | Readout and data services | Discovered — Market | Universal launched readout services May 2024; value pool broadening from box sales to services | OBSERVATION Medium, 2 findings |
| C-03 | GADSS connectivity / streaming tie-in | Discovered — Market | HCR-25 pairs with Aspire SATCOM streaming; connectivity named a differentiation axis | OBSERVATION Medium, 1 finding |
| C-02 | ED-112B standards headroom | Discovered — Market | Differentiation migrating from spec parity to standards headroom | OBSERVATION Medium, 1 finding |
| C-09 | MRO vertical-entry defence | Discovered — Market | Lufthansa Technik markets its own 25 h-capable CVFDR — a customer becoming a competitor | OBSERVATION Medium, 1 finding |
| C-05 | AAM / UAS lightweight recorder | Discovered — Market | Adjacent white space; Acron already fielding xLDR | OBSERVATION Medium, 1 finding |
| C-08 | Asia-Pacific channel development | Discovered — Market | APAC fastest-growing; India 7.4% CAGR | FORECAST Medium, 1 finding |
| U-03 | Wireless data offload | Customer — CTO | Exploratory. Partially corroborated by C-03 | Customer + 1 adjacent finding |
| U-01 | Deployable recorder line extension | Customer — VP Engineering | No supporting evidence found. Market Insights notes Leonardo DRS is Acron's deployable partner and its ADFR status is undisclosed | Customer only |

**Note on U-01.** No evidence supports a deployable recorder opportunity, and
the one adjacent data point is that a competitor holds that partnership.
Recorded, not dismissed — the proposer may hold information this evidence base
does not.

---

## Report 2 — Project strategic context *(abbreviated, as in v1)*

Rationale table per project. Absent agents stated rather than inferred. No
change from v1 in shape.

---

## Report 3 — Prioritised portfolio

**Committed projects only.** Twelve candidates excluded for lack of validated
effort; see Report 7.

### Framework

Weighted scoring, as selected for this run.

**Criterion substitution applied.** Customer value carries the heaviest weight
(25%) and its declared source is the Voice of Customer agent, which has not run.
Scored instead from Market Insights' Customer Demand Report. This is
market-level demand evidence, not customer-specific feedback. Basis
`source-derived`, confidence reduced to Medium for that dimension throughout.

**Framework recommendation.** This market's demand is created by dated
compliance cohorts — 16 May 2025 line-fit, 2 Feb 2027 for Part 91/125/135, 2 Feb
2029 for other CVR-equipped aircraft, and a statutory retrofit deadline of 2030
*(Market Insights, Customer Demand; FACT, High)*. Cost of delay is literal here:
missing a cohort date forfeits that cohort. **WSJF would likely produce a more
defensible ranking than weighted scoring** and is recommended for a comparison
run. Not switched — framework selection is the customer's.

**Financial metrics unavailable.** No `project_financials.csv` supplied. No NPV,
ROI or payback column is produced. Scoring is unaffected.

### Ranking

| Rank | Project | Score | Effort left | Class | Key driver | Confidence |
|---|---|---|---|---|---|---|
| 1 | P-01 CVR-25 TSO certification | 9.15 | 59 | Mandatory | Gates all 25 h revenue; cohort dates from Feb 2027 | High |
| 2 | P-02 STC package, 5 types | 7.80 | 208 | Mandatory | Only viable route to the retrofit cohort absent airframer access | High |
| 3 | P-09 Production capacity | 6.90 | 150 | Discretionary | Capacity must precede the 2030 wave | Medium |
| 4 | P-08 DO-326A security | 6.05 | 77 | Mandatory | Airworthiness security precondition | Medium |
| 5 | P-04 ULB dual-source | 5.70 | 41 | Discretionary | SO-2 single-source exposure | Medium |
| 6 | P-06 Download tooling | 5.55 | 48 | Discretionary | Third-party tools already serve 7+ brands | Medium |
| 7 | P-03 Memory IC redesign | 5.15 | 208 | Discretionary | **Prerequisite — see Report 5** | Medium |
| 8 | P-05 Low-SWaP bizav variant | 5.05 | 323 | Discretionary | Bizav demand voluntary, not mandated | Medium |
| 9 | P-07 FDR 200 h extension | 4.65 | 162 | Discretionary | Parity play; competitor publishes 210 h | Medium |

### Dimension values, top three

| | Customer | Strategic | Revenue | Risk | Time | Effort | Total |
|---|---|---|---|---|---|---|---|
| Weight | 25% | 20% | 20% | 15% | 10% | 10% | |
| P-01 | 9 | 10 | 9 | 8 | 10 | 9 | **9.15** |
| P-02 | 8 | 9 | 9 | 6 | 9 | 4 | **7.80** |
| P-09 | 6 | 8 | 8 | 6 | 8 | 5 | **6.90** |

Basis: strategic alignment `calculated` against stated objectives; customer
value and revenue `source-derived`; risk, time and effort `estimated`. **No
dimension is `measured`** — Meridian supplied no win/loss, pricing or revenue
data.

### Capacity analysis

Per bucket, FY27.

| Bucket | Demand | Capacity | Utilisation | Contractable |
|---|---|---|---|---|
| Hardware | 498 | 980 | 51% | Yes |
| Software | 220 | 760 | 29% | Yes |
| Systems | 281 | 540 | 52% | Partial |
| **Certification** | **277** | **240** | **115%** | **No** |
| Aggregate | 1,276 | 2,520 | 51% | — |

**The aggregate figure is misleading and must not be acted upon.** At 51% it
implies 1,244 weeks of headroom. The portfolio as committed cannot be delivered
in FY27.

**Mandatory consumption of the constrained bucket.** P-01, P-02 and P-08 consume
180 of 277 certification weeks — 75% of available DER capacity before any
discretionary work. Only 60 certification weeks remain against 97 requested.
This portion cannot be relieved by deprioritisation.

**Relief by contracting is unavailable.** The brief declares certification
non-contractable, DER-constrained and not expandable at short notice. Hiring is
not a FY27 option.

**Smallest resolving deferral.** Deferring P-05 removes 40 certification weeks,
bringing demand to 237 against 240 available.

**Agreement with ranking:** yes. P-05 ranks 8th of 9, so the schedule constraint
and the priority ranking point the same way. This agreement should not be
assumed to recur under a different framework or scenario — see Report 6.

---

## Report 4 — Mandatory, strategic, discretionary

### Mandatory

| Project | Declared driver | Deadline | Cert weeks |
|---|---|---|---|
| P-01 | Part 25 TSO — no sellable 25 h CVR without it | Q2 FY27 | 40 |
| P-02 | STC required per type before retrofit installation | Q4 FY27; statutory 2030 | 125 |
| P-08 | DO-326A airworthiness security | Q4 FY27 | 15 |

No mandatory project falls below a funding line. All three sit inside the
constrained bucket, which is the binding issue rather than funding.

### Strategic

P-09 production capacity — SO-1. P-04 ULB dual-source — SO-2.

### Discretionary

P-03, P-05, P-06, P-07. P-03 is a prerequisite and not freely deferrable — see
Report 5.

### Objective coverage

| Objective | Committed projects serving it | Status |
|---|---|---|
| SO-1 — capture US 25 h retrofit cohort before the window closes | P-01, P-02, P-09 | Well served |
| SO-2 — reduce single-source component dependence | P-03, P-04 | Served |
| SO-3 — route to market independent of airframer service bulletins | **None** | **Unserved** |
| SO-4 — protect installed base through the transition without margin erosion | P-06 (incidental) | **Barely served** |

**SO-3 is unserved.** No committed project pursues a route to market independent
of airframer service bulletins. Market Insights finds this is precisely where
advantage has migrated: Airbus selected a single qualified 25 h CVR and moved
supply into its own service-bulletin channel, converting a hardware sale into an
OEM-mediated one *(Exec Summary; FACT, High)*. Candidates C-01, C-07 and U-02
address it; none is scoped.

**SO-4 is barely served.** P-06's download tooling refresh touches the installed
base, but no committed project addresses margin erosion during the legacy-to-25h
transition. 6,400 legacy 2 h CVRs are in service across five platforms. The
objective names margin explicitly; nothing in the portfolio defends it.

Both are strategic gaps regardless of how well the ranked portfolio scores.

---

## Report 5 — Dependency and sequencing

| Project | Prerequisites | Blocks | Parallel-safe | Basis |
|---|---|---|---|---|
| P-01 | — | P-02 | No | Inferred — confirm |
| P-02 | P-01 | — | After P-01 | Inferred — confirm |
| P-03 | — | P-05, P-07 | Yes | Inferred — confirm |
| P-04 | — | — | Yes | — |
| P-05 | P-03 | — | No | Inferred — confirm |
| P-06 | — | — | Yes | — |
| P-07 | P-03 | — | No | Inferred — confirm |
| P-08 | — | P-02 (partial) | Yes | Inferred — confirm |
| P-09 | — | — | Yes | — |

**No `dependencies.csv` was supplied.** All dependencies above are inferred from
project descriptions and flagged for confirmation. A single incorrect inference
here would change the sequencing recommendation.

### Where sequence differs from rank

**P-03 ranks 7th and must precede P-05 and P-07.** The memory IC redesign sits
beneath both the low-SWaP variant and the FDR capacity extension. Building either
on the outgoing IC means redoing the work. P-03 scores poorly because it is
invisible to customers and generates no revenue — it protects rather than grows.

Treating rank as schedule would waste effort in two higher-cost projects.
**Priority is not sequence.**

---

## Report 6 — Scenario analysis

| Project | Base | Growth | Sustainment |
|---|---|---|---|
| P-01 | 1 | 1 | 1 |
| P-02 | 2 | 2 | 2 |
| P-09 | 3 | 3 | 5 |
| P-08 | 4 | 4 | 4 |
| P-04 | 5 | 7 | **3** |
| P-06 | 6 | 5 | 7 |
| P-03 | 7 | **9** | 6 |
| P-05 | 8 | 6 | **9** |
| P-07 | 9 | 8 | 8 |

**Growth.** P-05 rises 8th → 6th, P-06 6th → 5th; P-03 falls 7th → 9th, P-04 5th
→ 7th. The top four are unchanged. **Certification demand is unchanged at 277
weeks** — the constraint persists, and promoting P-05 makes it worse, since
P-05's 40 certification weeks were the deferral that resolved it. Under growth
weighting the constraint has no clean resolution inside the ranking.

**Sustainment.** P-04 rises 5th → 3rd, P-03 7th → 6th, P-05 falls to 9th.
**Certification demand falls to 237 weeks with P-05 deprioritised, resolving the
FY27 constraint without further action.** This scenario is schedulable as
ranked; the base case is not, and growth is worse.

**Compliance-first — no material reordering.** The top four under base weighting
are already the three mandatory projects plus production capacity. Raising time
criticality and regulatory exposure changes no rank above 5th. **The portfolio is
already compliance-led**, so this scenario tells the customer something real:
there is no compliance-weighted reordering available because compliance already
dominates. No difference is manufactured.

### Cross-scenario prerequisite check

**Growth scenario contains a violation.** P-05 ranks 6th and P-07 ranks 8th,
while their shared prerequisite P-03 ranks 9th. Under growth weighting the
portfolio would sequence two projects ahead of work they depend on.

This is invisible when each scenario is read alone. Base and sustainment
scenarios are clean.

---

## Report 7 — Decision brief

### Governing insight

**Situation.** Meridian holds a 15,200-unit installed base with 6,400 legacy 2 h
CVRs facing a statutory replacement deadline in 2030, and nine committed
projects consuming 1,276 engineering weeks against 2,520 available.

**Complication.** Aggregate capacity looks comfortable at 51%, but certification
is oversubscribed at 115% and cannot be contracted. Three-quarters of that
constrained resource is consumed by mandatory work. Meanwhile two of four
strategic objectives have no committed project against them, including the one
the company's own market evidence identifies as decisive.

**Question.** Is the binding constraint on Meridian's 2030 opportunity
engineering capacity, or route to market?

**Answer.** Route to market. The certification bottleneck is real and resolves
with a single deferral that the ranking already supports. The strategic gaps do
not resolve at all. Airbus has closed its channel to a competitor, retrofit
installation friction is contested and unresolved, and no committed project
pursues an independent route to the 13,500-aircraft cohort. **Meridian can
deliver its entire committed portfolio and still miss the opportunity it exists
to capture.**

### Top committed projects

**P-01 — CVR-25 TSO certification (9.15).** Highest on every dimension except
effort. Gates all 25 h revenue and all downstream STC work.
*Uncertainty:* none material.

**P-02 — STC package, 5 regional types (7.80).** The only viable route to the
retrofit cohort absent airframer access. Covers 1,810 CRJ/ERJ units.
*Uncertainty:* 125 certification weeks — 52% of total FY27 DER capacity in one
project. Any slip cascades.

**P-09 — Production capacity (6.90).** Market Insights finds installation and
shop-slot capacity contested; if 2030 becomes a bottleneck, capacity decides
share.
*Uncertainty:* timing. No evidence in this base resolves it.

### What would change the decision

| Assumption | Threshold |
|---|---|
| P-02 requires 125 certification weeks | Above 160, FY27 is unschedulable even with P-05 deferred |
| Retrofit demand arrives as a wave before 2030 | If retrofits extend past 2030 — which Market Insights flags as plausible — P-09 can defer a year at no cost |
| P-03 gates P-05 and P-07 | Inferred, not supplied. If wrong, the sequencing recommendation is wrong |
| Customer value scored from market demand, not customer feedback | A Voice of Customer run could move any project up to two ranks |
| Bizav demand is discretionary | Confirmed High — NBAA publicly welcomed the absence of a retrofit mandate |

### Decisions required

| Decision | Owner | Why now |
|---|---|---|
| Defer P-05 or accept FY27 slip | VP Engineering | FY27 unschedulable as committed; certification non-contractable |
| Confirm the inferred dependency set | VP Engineering | No dependencies file supplied; sequencing rests on inference |
| Sequence P-03 ahead of P-05 and P-07 regardless of rank | VP Engineering | Building on the outgoing IC wastes effort in two projects |
| Scope a route-to-market initiative | VP Sales + VP Engineering | SO-3 unserved; evidence says this is where advantage sits |
| Address SO-4 or retire it | Product leadership | Objective names margin erosion; nothing defends it |
| Plan FY29 capacity | Finance | Blank in the brief. The 2030 deadline falls in an unplanned year |
| Consider a WSJF comparison run | Product leadership | Demand is cohort-dated; cost of delay is literal |

### What to scope next

**1. C-01 / U-02 — independent route to market.** Strongest evidence in the set,
three converging findings, and serves SO-3 which has no project. Proposed
independently by the VP Sales.
*Needed:* whether this extends P-02's STC work or is a distinct commercial
programme; effort by bucket, particularly certification.

**2. C-07 — installation capacity partnership.** Market Insights records a
direct contradiction: the FAA states units swap without much difficulty, while
industry estimates put retrofit labour at ~6× line-fit. Whichever is true decides
whether 2030 is a smooth flow or a shop-slot bottleneck.
*Needed:* resolve the contradiction. A Voice of Customer question, not an
engineering estimate.

**3. C-06 — cargo and combi campaign.** Cheapest in the set. The statutory cohort
explicitly includes all-cargo and combi derivatives; no competitor activity
appears in the evidence base.
*Needed:* likely commercial rather than engineering effort. May not enter the
engineering portfolio at all.

**4. C-04 — readout and data services.** Value pool broadening from box sales to
services; the 15,200-unit installed base is the asset. Also the most direct
answer to SO-4's margin concern.
*Needed:* software effort, and whether P-06 is the foundation or a separate track.

Not recommended for scoping now: C-02, C-03, C-05, C-08, C-09, U-01, U-03 — each
rests on a single Medium-confidence observation, or in U-01's case none.

### Human decision gates

Weight selection, the P-05 deferral, dependency confirmation, FY29 capacity
planning, and any route-to-market commitment require human approval. This agent
has recommended; it has not decided.

### Confidence summary

The certification bottleneck, both objective coverage gaps, and the growth-
scenario prerequisite violation rest on **High** confidence — calculated from
supplied data or sourced to dated Market Insights findings.

All nine scores are **Medium** at best. No dimension is `measured`. The
dependency set is **inferred and unconfirmed**, and the sequencing recommendation
depends on it.

**Four of six rationale types have no source agent.** The most valuable single
addition is not more market research — it is a **Voice of Customer run**, which
would convert the largest-weighted scoring dimension from inference to evidence
and resolve the installation-friction contradiction that C-07 turns on.

Second most valuable: a **`dependencies.csv`** from the customer, which would
convert the sequencing recommendation from inferred to confirmed.
