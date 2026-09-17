# Agent 5 — Decision Inputs Brief

Specification for the customer-supplied inputs to the Strategy Synthesis &
Decision agent.

This is one of two briefs in the platform. The **product/market brief** supplies
Tier 1 evidence to the domain agents. This one supplies decision parameters to
Agent 5. They are filled by different people at different times and should not
be merged.

---

## Design principles

**The customer's vocabulary, not ours.** Discipline buckets, effort bands,
project types and scenario names are all declared by the customer and used
verbatim in the output. The agent never needs to know what a bucket means — only
that a project consumes N units of it and M units exist.

**Evidence classifications are not configurable.** FACT / OBSERVATION /
INTERPRETATION / FORECAST / UNKNOWN and the High / Medium / Low confidence scale
are platform standards. Renaming them breaks comparability across agents,
customers and time.

**Missing inputs degrade, they never block.** Every absent field has a defined
consequence that appears in the output. Nothing stalls waiting for input.

**Two populations.** Committed projects have validated effort and are scored.
Candidates do not and are not. The brief supplies the former; the agent
discovers the latter.

---

## Section 1 — Configuration

Declared once per tenant, editable per run.

### 1.1 Capacity buckets

The customer names their own. Between 2 and 8.

```
bucket_id, bucket_name, contractable, note
HW,        Hardware,     yes,         
SW,        Software,     yes,         
SYS,       Systems,      partial,     
CERT,      Certification, no,         DER-constrained, cannot be contracted at short notice
```

`contractable` matters: a bottleneck in a bucket that can be contracted is a
budget decision; one that cannot is a scheduling constraint. The agent must
treat them differently.

`bucket_id` becomes a column header in both capacity and roadmap files. **They
must match exactly.** Validate on upload; a silent mismatch produces a
bottleneck analysis with a missing constraint.

### 1.2 Effort bands

Customer-defined names and thresholds. Optional — absent, effort is reported in
raw units only.

```
band_name, min_units, max_units
Small,     0,         40
Medium,    40,        150
Large,     150,       400
Program,   400,       
```

### 1.3 Effort unit

`engineer_weeks` | `engineer_months` | `person_days` | custom string.
Used verbatim in output.

### 1.4 Project types

Customer-defined list. Used for grouping, not logic. Example: Compliance,
Sustainment, New product, Enhancement, Service, Manufacturing.

### 1.5 Fiscal year convention

Start month, and the label format. Needed to align deadlines with capacity years.

---

## Section 2 — Strategic objectives

```
objective_id, objective, horizon, owner, measure
```

`measure` optional — how the customer knows the objective is being met.

**Consequence if absent:** strategic alignment cannot be scored. The dimension
is scored from evidence at reduced confidence if the framework requires it, and
the degradation is stated. Objective coverage analysis (Report 4) is
unavailable.

---

## Section 3 — Products and installed base

`products_fleet.csv`

```
product_id, product, platform, platform_class, units_in_service,
avg_age_yrs, status, region
```

One row per product × platform. Platform granularity is required, not optional:
reach for a certification-dependent project depends on which platforms are
covered, not on a total fleet number.

`status` — customer-defined (e.g. Current, Sunsetting, Legacy).

**Consequence if absent:** RICE Reach cannot be calculated and RICE becomes
unavailable as a framework. Revenue impact is scored qualitatively.

---

## Section 4 — Capacity

`capacity.csv` — one row per fiscal year × bucket

```
fiscal_year, bucket_id, fte, capacity_units, budget
```

Partial years are acceptable. A blank future year is recorded as unplanned, not
as zero.

**Consequence if absent:** no funding line is drawn, no bottleneck analysis is
possible. The ranking is still produced. This is the single most valuable
optional input — without it the agent cannot tell the customer what is actually
schedulable.

---

## Section 5 — Committed projects

`roadmap.csv` — effort columns are named by `bucket_id`

```
project_id, project, type, status, pct_complete,
effort_remaining_<bucket_id>  [one column per bucket],
target_gate, target_fy, owner, mandatory, mandatory_driver, mandatory_deadline
```

**Effort must be remaining, not total.** A project 80% through a 40-week build
has 8 weeks left. Total effort systematically misranks everything underway.

`mandatory` is a customer declaration, not an agent inference. The agent may
observe that a project appears compliance-driven, but only the customer knows
what is contractually or regulatorily binding.

`mandatory_driver` — which regulation, contract or certification.

### 5.1 Dependencies

`dependencies.csv` — optional but high-value

```
project_id, depends_on_project_id, dependency_type, note
```

**Consequence if absent:** the agent infers dependencies from project
descriptions and marks them `estimated`. Inferred dependencies are stated as
inferred and flagged for confirmation.

### 5.2 Financials

`project_financials.csv` — optional

```
project_id, revenue_impact_y1..y5, capex, opex_annual,
discount_rate, currency, basis
```

`basis` — how the numbers were derived (business case, estimate, allocation).

**Financials are never folded into the priority score.** They are reported as a
parallel column. A project ranking third strategically with the highest NPV, or
ranking first and being NPV-negative because it is compliance, are both findings
that a composite score would destroy.

**Mandatory projects are not evaluated on ROI.** The counterfactual for a
compliance project is usually exit from the segment, not a lower return. Where
a mandatory project has financials, report cost of non-compliance if the
customer supplies it; otherwise report cost only and say why return is not
computed.

**Consequence if absent:** no financial column. Scoring is unaffected.

---

## Section 6 — User-proposed projects

```
project_id, project, proposed_by, description, rationale
```

No effort required. These enter the candidate set, never the ranked portfolio,
until scoped.

**These are never eliminated.** A proposal with no supporting evidence is
classified `user-provided, no supporting evidence found` and stated neutrally.
The proposer may know things the evidence base does not.

---

## Section 7 — Framework selection

**Per run**, not per tenant. Comparing the same portfolio under two frameworks
is a legitimate and valuable use.

| Framework | Requires | Available when |
|---|---|---|
| Value vs effort | Effort only | Always |
| Weighted scoring | Criteria + weights | Always |
| RICE | Reach denominators, effort | Products/installed base supplied |
| WSJF | Cost of delay inputs, effort | Deadlines or financials supplied |
| Kano | Customer response data | Voice of Customer agent has run |
| Custom | Customer-defined criteria and weights | Always |

The UI should show which frameworks the current inputs support rather than
offering all six equally. Selecting an unsupported framework is permitted but
must warn what will be estimated.

**Default when unselected:** value vs effort. Stated explicitly in the output,
with a note that richer frameworks need more input.

**Recommendation rule:** where the evidence base contains dated regulatory or
contractual deadlines, the agent should note that WSJF may fit better than the
selected framework, and why. Cost of delay is literal in a market driven by
compliance cohorts.

### 7.1 Weights

```
criterion, weight, source_agent
```

`source_agent` declares which agent supplies evidence for that criterion. If
that agent has not run, the agent scores the criterion from the best available
evidence at reduced confidence and states the substitution — it does not drop
the dimension or silently redistribute weight.

---

## Section 8 — Scenarios

```
scenario_name, criterion, weight
```

Customer-named. Two to six.

**Consequence if absent:** base case only; scenario analysis unavailable.

---

## Section 9 — Rules and thresholds

```
rule_type, value, note
```

Examples: minimum effort to rank individually; whether mandatory projects may
fall below the funding line; whether cancellation recommendations are permitted
and what must accompany them.

---

## Validation on upload

| Check | Severity |
|---|---|
| Every roadmap effort column matches a declared `bucket_id` | Error |
| Every capacity row's `bucket_id` is declared | Error |
| `pct_complete` and effort remaining are consistent with total where both given | Warning |
| Dependency references resolve to known `project_id`s | Error |
| Platform rows sum to a plausible installed base | Warning |
| Fiscal years in capacity cover the horizon of `target_fy` in roadmap | Warning |
| Any file older than 180 days | Warning — staleness |

Each file carries an `as_of` date. Stale inputs are flagged in the output the
same way stale evidence is flagged in the domain agents.

---

## Completeness and its consequences

The UI should express what is missing in terms of what it costs, not as a red
badge. "Without capacity by bucket, we cannot tell you which constraint binds —
11 of 14 projects will be ranked but not scheduled" is more motivating than
`Missing`.

**The Run action is never blocked by an incomplete brief.**

| Missing | Consequence stated in output |
|---|---|
| Objectives | Strategic alignment scored from evidence at reduced confidence; no objective coverage analysis |
| Products / installed base | RICE unavailable; revenue scored qualitatively |
| Capacity | No funding line, no bottleneck analysis |
| Effort bands | Effort reported in raw units only |
| Dependencies | Inferred and flagged for confirmation |
| Financials | No financial column |
| Framework | Defaults to value vs effort, stated |
| Scenarios | Base case only |

---

## Open questions

1. **Multi-year capacity.** Projects span fiscal years; the current shape
   analyses one year at a time. Does the agent need to spread effort across
   years, or is single-year analysis with a stated horizon sufficient for v1?
2. **Candidate persistence.** A dismissed candidate should not reappear
   unchanged every run. This needs state outside the brief — likely a
   `candidates` table with status and dismissal reason.
3. **Who owns this brief.** Objectives and roadmap are a product manager's;
   capacity and financials are a programme or finance owner's. One form with
   one save action may not survive contact with a real organisation.
