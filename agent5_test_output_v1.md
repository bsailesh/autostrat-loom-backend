# Agent 5 — test output

**Test conditions.** Prompt draft v1, decision brief strawman v2, and Market
Insights run `df344207` (extended-duration flight recorders, 9 reports).
Subject: Meridian Avionics, fictional.

Reports 1, 3, 4, 5, 6 and 7 produced. Report 2 (strategic context) abbreviated
— it is long and repetitive and tests nothing the others do not.

---

## Report 1 — Strategic opportunity and project universe

### Key insights

- **Certification is oversubscribed while the portfolio looks comfortable.**
  Aggregate FY27 utilisation is 51%, but certification demand is 277 weeks
  against 240 available — 115%. Three compliance projects consume 180 of those
  277 weeks. *(Confidence: High — calculated from supplied capacity data)*
- **The committed portfolio does not address the company's stated route-to-
  market objective.** SO-3 seeks a channel independent of airframer service
  bulletins; no in-flight project pursues one, while Market Insights finds
  advantage has migrated to exactly that layer. *(Confidence: High)*
- **Nine committed projects are scored. Eleven candidates are not**, because
  none has a validated effort estimate. They are described below and carried
  into Report 7 for scoping, not ranked. *(Confidence: High)*
- **Four of six rationale types cannot be sourced.** Only Market Insights has
  run. Customer, technology, regulatory and sustainment rationale are absent
  or inferred from market evidence, and are marked as such throughout.

### Committed projects

Nine, from `roadmap_fy26.csv`. Total remaining effort 1,276 weeks.

| ID | Project | Type | Effort left | Cert weeks | Evidence support |
|---|---|---|---|---|---|
| P-01 | CVR-25 Part 25 TSO certification | Compliance | 59 | 40 | Evidence-supported |
| P-02 | STC package — 5 regional jet types | Compliance | 208 | 125 | Evidence-supported |
| P-03 | Crash-survivable memory IC redesign | Sustainment | 208 | 20 | User-provided, no upstream evidence |
| P-04 | ULB dual-source qualification | Sustainment | 41 | 10 | Partially supported |
| P-05 | Low-SWaP variant, business aviation | New product | 323 | 40 | Evidence-supported |
| P-06 | Download tooling and workflow refresh | Service | 48 | 2 | Evidence-supported |
| P-07 | FDR capacity extension to 200 h | Enhancement | 162 | 15 | Partially supported |
| P-08 | DO-326A airworthiness security | Compliance | 77 | 15 | User-provided, no upstream evidence |
| P-09 | Production line capacity expansion | Manufacturing | 150 | 10 | Evidence-supported |

### Candidates — not scored

Discovered from upstream evidence or proposed by the user. None has validated
effort, so none is ranked.

| ID | Candidate | Origin | Problem addressed | Evidence |
|---|---|---|---|---|
| C-01 | Airframer qualification programme | Discovered — Market | Airbus selected a single qualified 25 h CVR and moved supply into its own service bulletin; advantage sits at the airframer layer, not the datasheet | Exec Summary; FACT, High |
| C-02 | ED-112B standards headroom | Discovered — Market | Differentiation migrating from spec parity to standards headroom (ED-112A → ED-112B) | Industry shifts; OBSERVATION, Medium |
| C-03 | GADSS connectivity / streaming tie-in | Discovered — Market | HCR-25 pairs with Aspire SATCOM streaming; connectivity named as a differentiation axis | Industry shifts; OBSERVATION, Medium |
| C-04 | Readout and data services offering | Discovered — Market | Universal launched readout services May 2024; value pool broadening from box sales to services | Industry shifts; OBSERVATION, Medium |
| C-05 | AAM / UAS lightweight recorder | Discovered — Market | Adjacent white space forming; Acron already fielding xLDR | Industry shifts; OBSERVATION, Medium |
| C-06 | Cargo and combi operator campaign | Discovered — Customer demand | Statutory cohort explicitly includes all-cargo and combi derivatives; freight fleets carry identical exposure | Customer Demand; FACT, High |
| C-07 | Installation capacity / shop-slot partnership | Discovered — Customer demand | Retrofit labour reported ~6× line-fit; installation friction is the variable determining whether 2030 is a flow or a bottleneck | Customer Demand; FACT, High (contested) |
| C-08 | Asia-Pacific channel development | Discovered — Market | APAC fastest-growing region; India 7.4% CAGR | Customer demand; FORECAST, Medium |
| C-09 | MRO vertical-entry defence | Discovered — Market | Lufthansa Technik markets its own 25 h-capable CVFDR — a customer becoming a competitor | Industry shifts; OBSERVATION, Medium |
| U-01 | Deployable recorder line extension | User — VP Engineering | No scope established | No upstream evidence found. Market Insights notes Leonardo DRS is Acron's deployable partner and its ADFR status is undisclosed |
| U-02 | Direct-to-operator retrofit channel | User — VP Sales | No engineering scope | Strongly corroborated: C-01 and C-07 both bear on it |
| U-03 | Wireless data offload | User — CTO | Exploratory | Partially corroborated by C-03 |

**Note on U-01.** No evidence was found supporting a deployable recorder
opportunity, and the one adjacent data point is that a competitor already
holds that partnership. This is recorded, not dismissed — the proposer may
hold information this evidence base does not.

---

## Report 2 — Project strategic context *(abbreviated)*

Produced in full for each project. One example, to show the shape and the
handling of absent agents:

**P-02 — STC package, 5 regional jet types**

| Rationale | Finding |
|---|---|
| Customer | **Not available** — Voice of Customer agent has not run. Market-level demand evidence used in its place, and scored at reduced confidence |
| Market | Statutory retrofit cohort of 13,500 dual-recorder aircraft closing 2030; ~US$67 M/yr equipment demand. Airbus channel closed to Meridian, making STC the viable route *(Market Insights, Exec Summary + Customer Demand; FACT/Medium)* |
| Technology | **Not available** — Tech & Regulation agent has not run |
| Regulatory | Partially available from market evidence: cohort dates 2 Feb 2027, 2 Feb 2029, statutory 2030 *(FACT, High)*. Not independently verified |
| Sustainment | **Not available** — Product Sustainment agent has not run |
| Business | 5 regional types map to 1,810 units in service across CRJ/ERJ in the installed base *(calculated from `products_fleet.csv`)* |

---

## Report 3 — Prioritised portfolio

**Committed projects only.** Eleven candidates are excluded because they have
no validated effort; see Report 7 for which are worth scoping.

**Framework:** weighted scoring, as supplied. One adjustment, stated: customer
value carries 25% weight but no Voice of Customer agent has run. Rather than
drop the dimension, it is scored from Market Insights' Customer Demand Report
— market-level demand rather than customer-specific feedback. Every customer
value score below is therefore `source-derived` at reduced confidence, not
`measured`.

| Rank | Project | Score | Effort left | Class | Key driver | Confidence |
|---|---|---|---|---|---|---|
| 1 | P-01 CVR-25 TSO certification | 9.15 | 59 | Mandatory | Gates all 25 h revenue; cohort dates from Feb 2027 | High |
| 2 | P-02 STC package, 5 types | 7.80 | 208 | Mandatory | Only viable route to the retrofit cohort absent airframer access | High |
| 3 | P-09 Production capacity | 6.90 | 150 | Discretionary | Capacity must precede the 2030 wave | Medium |
| 4 | P-08 DO-326A security | 6.05 | 77 | Mandatory | Airworthiness security precondition | Medium |
| 5 | P-04 ULB dual-source | 5.70 | 41 | Discretionary | SO-2 single-source exposure | Medium |
| 6 | P-06 Download tooling | 5.55 | 48 | Discretionary | Service differentiation; third-party tools already serve 7+ brands | Medium |
| 7 | P-03 Memory IC redesign | 5.15 | 208 | Discretionary | **Prerequisite — see Report 5** | Medium |
| 8 | P-05 Low-SWaP bizav variant | 5.05 | 323 | Discretionary | Bizav demand is voluntary, not mandated | Medium |
| 9 | P-07 FDR 200 h extension | 4.65 | 162 | Discretionary | Parity play; a competitor already publishes 210 h | Medium |

### Score breakdown, top three

| | Customer | Strategic | Revenue | Risk | Time | Effort | Total |
|---|---|---|---|---|---|---|---|
| Weight | 25% | 20% | 20% | 15% | 10% | 10% | |
| P-01 | 9 | 10 | 9 | 8 | 10 | 9 | **9.15** |
| P-02 | 8 | 9 | 9 | 6 | 9 | 4 | **7.80** |
| P-09 | 6 | 8 | 8 | 6 | 8 | 5 | **6.90** |

Basis: strategic alignment `calculated` against stated objectives; customer
value and revenue `source-derived` from Market Insights; risk, time and effort
`estimated` from roadmap data and evidence. No dimension is `measured` —
Meridian supplied no win/loss, pricing or revenue data.

### The funding line

FY27 capacity is 2,520 weeks against 1,276 weeks of committed demand. **In
aggregate, every project fits with 1,244 weeks to spare.**

That number is misleading, and acting on it would be an error.

| Discipline | Demand | Capacity | Utilisation |
|---|---|---|---|
| Hardware | 498 | 980 | 51% |
| Software | 220 | 760 | 29% |
| Systems | 281 | 540 | 52% |
| **Certification** | **277** | **240** | **115%** |

**Certification is oversubscribed by 37 weeks.** The committed portfolio as
scheduled cannot be delivered in FY27.

Worse, the constraint is largely mandatory. P-01, P-02 and P-08 consume 180 of
the 277 certification weeks — 75% of available DER capacity before any
discretionary work is considered. Only 60 certification weeks remain for
everything else, against 97 requested.

Deferring **P-05** alone resolves it: its 40 certification weeks bring demand
to 237, inside the 240 available. P-05 is also ranked 8th of 9, so the
schedule constraint and the priority ranking agree — an unusually clean
outcome that should not be assumed to recur.

The brief states certification headcount is DER-constrained and cannot be
contracted at short notice, so relief by hiring is not available inside FY27.

**This is the single most consequential finding in this report, and it is
invisible in an aggregate capacity model.**

---

## Report 4 — Mandatory, strategic, discretionary

### Mandatory

| Project | Driver | Deadline | Cert weeks |
|---|---|---|---|
| P-01 | Part 25 TSO — without it there is no sellable 25 h CVR | Q2 FY27 gate; cohort dates Feb 2027 | 40 |
| P-02 | STC required for each type before retrofit installation | Q4 FY27; statutory 2030 | 125 |
| P-08 | DO-326A airworthiness security | Q4 FY27 | 15 |

No mandatory project falls below the funding line. All three sit inside the
certification constraint, which is the binding issue rather than funding.

### Strategic

P-09 production capacity — serves SO-1 directly. Without capacity, winning the
retrofit cohort is unachievable regardless of certification status.

P-04 ULB dual-source — serves SO-2 directly.

### Discretionary

P-03, P-05, P-06, P-07. Of these P-03 is a prerequisite and must not be
treated as freely deferrable — see Report 5.

### Objective coverage gap

**SO-3 has no project against it.** The objective seeks a route to market
independent of airframer service bulletins. Market Insights finds this is
precisely where advantage now sits. Candidates C-01, C-07 and U-02 all address
it; none is scoped. This is a stated gap, not a ranking outcome.

---

## Report 5 — Dependency and sequencing

Structured output; the rendering layer draws the graph.

| Project | Prerequisites | Blocks | Parallel-safe |
|---|---|---|---|
| P-01 | — | P-02 | No — gates STC |
| P-02 | P-01 | — | After P-01 |
| P-03 | — | P-05, P-07 | Yes |
| P-04 | — | — | Yes |
| P-05 | P-03 | — | No |
| P-06 | — | — | Yes |
| P-07 | P-03 | — | No |
| P-08 | — | P-02 (partial) | Yes |
| P-09 | — | — | Yes |

### Where sequence differs from rank

**P-03 ranks 7th and must be scheduled before P-05 and P-07.**

The memory IC redesign is a component-level change beneath both the low-SWaP
variant and the FDR capacity extension. Building either on the outgoing IC
means redoing the work. P-03 scores poorly because it is invisible to
customers and generates no revenue — it protects rather than grows.

Treating rank as schedule here would waste the effort in two higher-cost
projects. **Priority is not sequence.**

**P-01 gates P-02.** TSO certification precedes STC work. Both are already
ordered correctly by rank; noted so the dependency is not lost if weights
change.

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

### Quantified consequences

**Growth.** P-05 rises 8th → 6th and P-06 5th; P-03 falls 7th → 9th and P-04
5th → 7th. The top four are unchanged — mandatory compliance work dominates
under any weighting, because the demand is scheduled rather than discretionary.
**P-03 falling to last is the material risk**: it remains a prerequisite for
P-05, which the same scenario promotes. Growth weighting would sequence a
project ahead of its own prerequisite.

**Sustainment.** P-04 rises 5th → 3rd, P-03 7th → 6th, P-05 falls to 9th.
Certification demand drops by 40 weeks with P-05 deprioritised, resolving the
FY27 constraint without further action. **This scenario is schedulable as
ranked; the base case is not.**

**Compliance-first is not quantified.** The top four under base weighting are
already the three mandatory projects plus production capacity. Raising time
criticality and regulatory exposure reorders nothing material. Stating this is
more useful than manufacturing a difference — the portfolio is already
compliance-led.

---

## Report 7 — Decision brief

### Governing insight

**Situation.** Meridian holds a 15,200-unit installed base with 6,400 legacy
2 h CVRs facing a statutory replacement deadline in 2030, and nine committed
projects consuming 1,276 engineering weeks against 2,520 available.

**Complication.** Aggregate capacity is comfortable but certification is
oversubscribed at 115%, and three-quarters of that constrained resource is
consumed by mandatory work that cannot be deferred. Meanwhile the company's
own evidence says advantage in this market has moved to the airframer and STC
layer — where Meridian has no position and no project.

**Question.** Is the binding constraint on Meridian's 2030 opportunity
engineering capacity, or route to market?

**Answer.** Route to market. The certification bottleneck is real and resolves
with a single deferral. The unaddressed strategic gap does not. Airbus has
closed its channel to a competitor, retrofit installation friction is contested
and unresolved, and no in-flight project pursues an independent route to the
13,500-aircraft cohort. Meridian can deliver its committed portfolio and still
miss the opportunity it exists to capture.

### Top committed projects

**P-01 — CVR-25 TSO certification (9.15).** Highest on every dimension except
effort. Gates all 25 h revenue and all downstream STC work. 40 certification
weeks against a Q2 FY27 gate.
*Primary uncertainty:* none material. This is unambiguous.

**P-02 — STC package, 5 regional types (7.80).** The only viable route to the
retrofit cohort absent airframer access. Covers 1,810 CRJ/ERJ units in the
installed base.
*Primary uncertainty:* 125 certification weeks — 52% of total FY27 DER
capacity in one project. Any slip cascades into everything else.

**P-09 — Production capacity (6.90).** Ranks third on strategic alignment and
revenue. Market Insights finds installation and shop-slot capacity contested;
if the 2030 wave becomes a bottleneck, capacity is the constraint that decides
share.
*Primary uncertainty:* timing. Too early wastes capital, too late misses the
wave. No evidence in this base resolves it.

### What would change the decision

| Project | Assumption | Threshold |
|---|---|---|
| P-02 | 125 certification weeks is accurate | If it exceeds 160, the FY27 portfolio is unschedulable even with P-05 deferred |
| P-09 | Retrofit demand arrives as a wave | If retrofits extend past 2030 — which Market Insights flags as plausible — capacity expansion can be deferred a year at no cost |
| All | Customer value scored from market demand, not customer feedback | A Voice of Customer run could move any project up to two ranks |
| P-05 | Bizav demand is discretionary | Confirmed High by Market Insights; NBAA publicly welcomed the absence of a retrofit mandate |

### Decisions required

| Decision | Owner | Why now |
|---|---|---|
| Defer P-05 or add DER capacity | VP Engineering | FY27 is unschedulable as committed. Deferral is the cheaper answer and agrees with rank |
| Sequence P-03 ahead of P-05 and P-07 regardless of rank | VP Engineering | Building on the outgoing memory IC wastes effort in two projects |
| Scope a route-to-market initiative | VP Sales + VP Engineering | SO-3 has no project. The evidence says this is where advantage sits |
| Plan FY29 capacity | Finance | Blank in the brief. The 2030 deadline falls inside an unplanned year |

### What to scope next

Candidates ranked by evidence strength, with what is needed to bring each into
the portfolio.

**1. C-01 / U-02 — independent route to market.** Strongest evidence in the
set and directly serves SO-3, which currently has no project. Market Insights
finds the contest is decided at the airframer/STC layer. U-02 was proposed by
the VP Sales and is corroborated by discovered evidence.
*Needed to scope:* whether this is an extension of P-02's STC work or a
distinct commercial programme; engineering effort by discipline, particularly
certification, which is the constrained resource.

**2. C-07 — installation capacity partnership.** Market Insights records a
direct contradiction in the public record: the FAA states 25 h units swap for
2 h units without much difficulty, while industry estimates put retrofit
labour at ~6× line-fit. Whichever is true decides whether 2030 is a smooth flow
or a shop-slot bottleneck — and if it is a bottleneck, installation capacity
is worth more than product differentiation.
*Needed to scope:* resolve the contradiction. This is a question for a Voice of
Customer run, not an engineering estimate.

**3. C-06 — cargo and combi campaign.** Cheapest of the set. The statutory
cohort explicitly includes all-cargo and combi derivatives, and no competitor
activity in this segment appears in the evidence base.
*Needed to scope:* almost certainly commercial rather than engineering effort.
May not need to enter the engineering portfolio at all.

**4. C-04 — readout and data services.** Universal launched readout services in
May 2024; Market Insights finds the value pool broadening from box sales to
services. Meridian's 15,200-unit installed base is the asset.
*Needed to scope:* software effort, and whether P-06's tooling refresh is the
foundation or a separate track.

Not recommended for scoping now: C-02, C-03, C-05, C-08, C-09, U-01, U-03 —
each rests on a single Medium-confidence observation, or in U-01's case on no
evidence at all.

### Human decision gates

Weight selection, the P-05 deferral, FY29 capacity planning, and any
route-to-market commitment all require human approval. This agent has
recommended; it has not decided.

### Confidence summary

The certification bottleneck, the dependency finding and the SO-3 gap rest on
**High** confidence — all are calculated from supplied data or directly sourced
to Market Insights findings with dates.

All nine scores are **Medium** at best. No dimension is measured: Meridian
supplied no revenue, win/loss or pricing data, so customer value and revenue
impact are source-derived from market-level evidence and the rest estimated.

**Four of six rationale types have no source agent.** Customer, technology,
sustainment and most regulatory rationale are unavailable. The most valuable
single addition to this analysis is not more market research — it is a Voice of
Customer run, which would convert the largest-weighted scoring dimension from
inference to evidence, and would resolve the installation-friction contradiction
that C-07 turns on.
