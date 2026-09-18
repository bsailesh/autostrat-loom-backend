# Decision inputs brief — Arden Actuation Systems

**Demo brief for Agent 5, paired with Market Insights run `1f843fe9`**
(electrical and electromechanical actuation for aerospace and defence).

**Arden Actuation Systems is fictional.** The numbers are plausible for a
mid-tier EMA supplier but none are real, and nothing here describes any actual
company. The shape is chosen so the findings are recognisable to anyone in this
segment — a certification-and-electronics squeeze, obsolescence exposure in
power electronics, and no line-fit position on a major commercial programme.

**Subject:** Arden Actuation Systems — roughly $85M revenue. Strong in defence
and space actuation, where EMA is genuinely winning. Effectively absent from
commercial flight control, where the five named leaders hold 47.6% of aircraft
EMA revenue. Roller-screw and motor technology adapted from commercial
industrial lines.

---

## 1. Strategic objectives

| ID | Objective | Horizon |
|---|---|---|
| SO-1 | Convert defence actuation growth into a commercial flight-control position before the next-generation narrowbody design-in window closes | 2031 |
| SO-2 | Eliminate single-source dependency in power electronics and position sensing | FY28 |
| SO-3 | Establish a qualification pathway that does not depend on a prime's shipset integration | FY29 |
| SO-4 | Protect margin on hydraulic-replacement retrofits as competitors enter | Ongoing |

## 2. Products and installed base

`products_fleet.csv`

| product_id | product | platform | platform_class | units_in_service | avg_age_yrs | status |
|---|---|---|---|---|---|---|
| AR-FIN | Missile fin actuator set | Tactical missile — surface-launched | Defence, guided weapons | 14,200 | 4 | Current |
| AR-FIN | Missile fin actuator set | Tactical missile — air-launched | Defence, guided weapons | 8,600 | 3 | Current |
| AR-TVC | Thrust vector control actuator | Small launch vehicle | Space, launch | 310 | 3 | Current |
| AR-TVC | Thrust vector control actuator | Upper stage | Space, launch | 145 | 5 | Current |
| AR-UTIL | Utility and door actuator | Rotorcraft — medium | Part 29 rotorcraft | 2,900 | 9 | Current |
| AR-UTIL | Utility and door actuator | Business jet | Part 25 business | 1,750 | 7 | Current |
| AR-GBAD | Ground-based air defence actuator | Mobile launcher | Defence, ground | 620 | 2 | Current |
| AR-HYDX | Hydraulic-replacement retrofit kit | Military transport | Part 25 / military | 480 | 12 | Sunsetting |
| AR-HYDX | Hydraulic-replacement retrofit kit | Legacy rotorcraft | Part 29 rotorcraft | 390 | 15 | Sunsetting |

Total units in service: 29,395.
No commercial primary flight-control or high-lift position.

## 3. Engineering capacity, by discipline

`capacity_fy26_fy29.csv`

| fiscal_year | discipline | fte | capacity_weeks | budget_usd | contractable |
|---|---|---|---|---|---|
| FY27 | Mechanical | 16 | 780 | 3,200,000 | yes |
| FY27 | Power electronics | 7 | 350 | 1,900,000 | **no** |
| FY27 | Software | 13 | 620 | 2,600,000 | partial |
| FY27 | Systems | 10 | 470 | 2,100,000 | partial |
| FY27 | Certification & qualification | 6 | 300 | 1,700,000 | **no** |
| FY28 | Mechanical | 16 | 780 | 3,300,000 | yes |
| FY28 | Power electronics | 8 | 400 | 2,200,000 | no |
| FY28 | Software | 13 | 620 | 2,700,000 | partial |
| FY28 | Systems | 10 | 470 | 2,200,000 | partial |
| FY28 | Certification & qualification | 6 | 300 | 1,800,000 | no |
| FY29 | — | — | — | — | — |

FY27 total capacity: 2,520 weeks. FY29 not yet planned.

**Power electronics** headcount is constrained by security clearance — most of
the workload is ITAR-controlled defence programmes, and cleared power
electronics engineers cannot be contracted at short notice.

**Certification & qualification** is DER- and test-slot constrained.

## 4. Effort calibration

| Band | Engineering weeks |
|---|---|
| Small | Under 60 |
| Medium | 60 – 200 |
| Large | 200 – 400 |
| Program | Over 400 |

## 5. In-flight projects

`roadmap_fy26.csv` — effort remaining by discipline, in weeks

| project_id | project | type | status | pct_complete | MECH | ELEC | SW | SYS | CERT | total | target_gate | mandatory |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P-01 | DO-254 design assurance, flight-control motor controller | Compliance | In flight | 40 | 8 | 95 | 40 | 30 | 85 | 258 | Q3 FY27 | Yes |
| P-02 | Roller-screw life extension qualification | Sustainment | In flight | 55 | 70 | 0 | 0 | 15 | 45 | 130 | Q2 FY27 | No |
| P-03 | Power electronics module redesign — GaN transition | Sustainment | In flight | 18 | 15 | 140 | 25 | 35 | 30 | 245 | Q1 FY28 | No |
| P-04 | Missile fin actuator rate capacity expansion | Manufacturing | In flight | 30 | 110 | 30 | 10 | 40 | 15 | 205 | Q4 FY27 | No |
| P-05 | High-lift actuator demonstrator, narrowbody | New product | In flight | 12 | 130 | 65 | 55 | 80 | 40 | 370 | Q2 FY28 | No |
| P-06 | Motor position sensor dual-source qualification | Sustainment | In flight | 45 | 20 | 35 | 5 | 12 | 28 | 100 | Q3 FY27 | No |
| P-07 | Prognostics and health monitoring software | Enhancement | In flight | 25 | 0 | 10 | 95 | 30 | 12 | 147 | Q1 FY28 | No |
| P-08 | DO-326A airworthiness security | Compliance | In flight | 35 | 0 | 15 | 60 | 35 | 25 | 135 | Q4 FY27 | Yes |
| P-09 | TVC actuator thermal margin improvement | Enhancement | In flight | 20 | 55 | 15 | 5 | 25 | 18 | 118 | Q3 FY28 | No |

Total remaining effort: 1,708 weeks.

### Demand against FY27 capacity

| Discipline | Demand | Capacity | Utilisation | Contractable |
|---|---|---|---|---|
| Mechanical | 408 | 780 | 52.3% | yes |
| **Power electronics** | **405** | **350** | **115.7%** | **no** |
| Software | 295 | 620 | 47.6% | partial |
| Systems | 302 | 470 | 64.3% | partial |
| **Certification & qual** | **298** | **300** | **99.3%** | **no** |
| Aggregate | 1,708 | 2,520 | 67.8% | — |

## 6. Dependencies

`dependencies.csv`

| project_id | depends_on_project_id | dependency_type | note |
|---|---|---|---|
| P-05 | P-03 | prerequisite | High-lift demonstrator uses the redesigned power electronics module |
| P-09 | P-03 | prerequisite | Thermal margin work assumes the GaN drive stage |
| P-07 | P-06 | prerequisite | PHM algorithms depend on the qualified position sensor |

## 7. User-proposed projects (not yet scoped)

| project_id | project | proposed_by | note |
|---|---|---|---|
| U-01 | Electro-hydrostatic actuator line extension | VP Engineering | No scope or effort established |
| U-02 | Independent shipset qualification capability | VP Programs | Would reduce dependence on prime integration; no engineering scope |
| U-03 | AAM / eVTOL actuation entry | CTO | Exploratory |

## 8. Prioritisation framework

**Weighted scoring.**

| Criterion | Weight |
|---|---|
| Customer value | 0.25 |
| Strategic alignment | 0.20 |
| Revenue impact | 0.20 |
| Risk reduction | 0.15 |
| Time criticality | 0.10 |
| Effort (inverse) | 0.10 |

## 9. Scenarios

| Scenario | Emphasis |
|---|---|
| Base | Weights as above |
| Defence-led | Revenue impact and time criticality up; strategic alignment down |
| Commercial entry | Strategic alignment and customer value up; effort down |
| Sustainment | Risk reduction and installed-base protection up |

## 10. Exclusion rules and thresholds

- Mandatory projects are never cut at the funding line without escalation.
- Projects under 30 engineering weeks remaining are not individually ranked.
- No project may be recommended for cancellation without naming the contractual
  or regulatory consequence.

---

## What this brief should surface in the demo

| Finding | Why it lands |
|---|---|
| **Two constrained buckets, not one.** Power electronics is over at 115.7% and certification sits at 99.3% — no slack. Aggregate utilisation is a comfortable 67.8% | The second constraint is the interesting one: not over capacity, but any slip anywhere has nowhere to go |
| **Neither constrained bucket is contractable** — one clearance-limited, one DER-limited | Relief is a hiring and clearance problem measured in quarters, not a budget decision |
| **The bottleneck is mostly discretionary.** Only 27% of power electronics demand is mandatory, so deferral is genuinely available | Different from a compliance-driven squeeze — here there is a real choice to make |
| **Deferring P-05 resolves it**, bringing power electronics to 97.1% — and P-05 also depends on P-03 | Priority, sequence and capacity all point at the same project for different reasons |
| **P-03 gates two projects and scores poorly alone** | Priority is not prerequisite, in a form an engineering audience recognises immediately |
| **SO-4 has no project against it** | Margin on hydraulic-replacement retrofits is named as an objective and nothing defends it, while the market evidence shows E/EM forecast as the fastest-growing actuator technology |
| **SO-3 is served only by an unscoped proposal (U-02)** | The bridge between populations: a strategic objective whose only answer has no effort estimate |
| **Candidates from the actuation market run** | Safran/Collins consolidation, the forced Woodward divestiture, hybrid electro-hydrostatic on landing gear, missile and TVC growth — all become candidates a mid-tier supplier should consider |

## Demo notes

- Upstream run: `1f843fe9` (aerospace actuation, 4 Sept). Pass it explicitly as
  `upstream_run_overrides` rather than relying on most-recent, since the
  recorders run is newer.
- That run predates the competitor-discovery fix of 10 Sept, so its grid was
  produced under the old four-competitor cap. Consider a fresh Market Insights
  run on the same scope if the competitor set matters in the room.
- Remove `STRATEGY_SYNTHESIS_MODEL=claude-sonnet-5` from the server `.env`
  before a demo run — Opus is what ships.
