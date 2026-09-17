# Decision inputs brief — strawman v2

**Purpose:** test input for the Agent 5 prompt draft, paired with Market
Insights run `df344207` (extended-duration flight recorders).

**This is invented.** Meridian Avionics does not exist. Numbers are plausible
for a mid-size recorder OEM but none are real.

**Changes from v1:** installed base broken out by platform; engineering
capacity and project effort both split by discipline.

**Subject company:** Meridian Avionics — challenger recorder OEM, roughly $55M
revenue, not one of the two dominant franchises. Certified product line, real
installed base, no airframer line-fit position.

---

## 1. Strategic objectives

| ID | Objective | Horizon |
|---|---|---|
| SO-1 | Capture a defensible share of the US 25-hour CVR retrofit cohort before the statutory window closes | 2030 |
| SO-2 | Reduce dependence on single-source components across the recorder line | FY28 |
| SO-3 | Establish a route to market that does not depend on airframer service bulletins | FY29 |
| SO-4 | Protect the installed base through the legacy-to-25h transition without margin erosion | Ongoing |

## 2. Products and installed base

`products_fleet.csv`

| product_id | product | platform | platform_class | units_in_service | avg_age_yrs | status |
|---|---|---|---|---|---|---|
| MR-CVR20 | CVR-20 (2 h voice) | A320ceo family | Part 25 transport | 1,850 | 14 | Sunsetting |
| MR-CVR20 | CVR-20 (2 h voice) | B737NG | Part 25 transport | 2,100 | 16 | Sunsetting |
| MR-CVR20 | CVR-20 (2 h voice) | B757 / B767 | Part 25 transport | 640 | 24 | Sunsetting |
| MR-CVR20 | CVR-20 (2 h voice) | CRJ700 / 900 | Part 25 regional | 1,120 | 17 | Sunsetting |
| MR-CVR20 | CVR-20 (2 h voice) | ERJ 145 | Part 25 regional | 690 | 21 | Sunsetting |
| MR-CVR25 | CVR-25 (25 h voice) | A320neo family | Part 25 transport | 190 | 2 | Current |
| MR-CVR25 | CVR-25 (25 h voice) | B737 MAX | Part 25 transport | 120 | 2 | Current |
| MR-FDR140 | FDR-140 | A320 family | Part 25 transport | 2,400 | 11 | Current |
| MR-FDR140 | FDR-140 | B737NG / MAX | Part 25 transport | 2,150 | 12 | Current |
| MR-FDR140 | FDR-140 | E170 / E190 | Part 25 regional | 1,350 | 9 | Current |
| MR-CVFDR | Combined CVFDR | CRJ / ERJ | Part 25 regional | 810 | 13 | Current |
| MR-CVFDR | Combined CVFDR | Q400 | Part 25 regional | 340 | 15 | Current |
| MR-CVFDR | Combined CVFDR | Challenger / Gulfstream | Part 25 business | 700 | 8 | Current |
| MR-HELI | Helicopter CVFDR | S-92 / AW139 / H175 | Part 29 rotorcraft | 740 | 10 | Current |

Total units in service: 15,200.
Legacy 2 h CVRs requiring replacement or retirement: 6,400.

## 3. Engineering capacity, by discipline

`capacity_fy26_fy29.csv`

| fiscal_year | discipline | fte | capacity_weeks | budget_usd |
|---|---|---|---|---|
| FY27 | Hardware | 20 | 980 | 4,100,000 |
| FY27 | Software | 16 | 760 | 3,100,000 |
| FY27 | Systems | 11 | 540 | 2,300,000 |
| FY27 | Certification | 5 | 240 | 1,300,000 |
| FY28 | Hardware | 20 | 980 | 4,300,000 |
| FY28 | Software | 16 | 760 | 3,200,000 |
| FY28 | Systems | 11 | 540 | 2,400,000 |
| FY28 | Certification | 5 | 240 | 1,400,000 |
| FY29 | — | — | — | — |

FY27 total capacity: 2,520 weeks. FY29 not yet planned.

Certification includes DER and airworthiness liaison. Headcount is constrained
by DER availability and cannot be contracted at short notice.

## 4. Effort calibration

| Band | Engineering weeks (all disciplines) |
|---|---|
| Small | Under 40 |
| Medium | 40 – 150 |
| Large | 150 – 400 |
| Program | Over 400 |

## 5. In-flight projects

`roadmap_fy26.csv` — effort remaining, by discipline, in weeks

| project_id | project | type | status | pct_complete | hw | sw | sys | cert | total | target_gate |
|---|---|---|---|---|---|---|---|---|---|---|
| P-01 | CVR-25 Part 25 TSO certification | Compliance | In flight | 72 | 6 | 4 | 9 | 40 | 59 | Q2 FY27 |
| P-02 | STC package — 5 regional jet types | Compliance | In flight | 35 | 20 | 15 | 48 | 125 | 208 | Q4 FY27 |
| P-03 | Crash-survivable memory IC redesign | Sustainment | In flight | 20 | 130 | 18 | 40 | 20 | 208 | Q1 FY28 |
| P-04 | ULB dual-source qualification | Sustainment | In flight | 55 | 22 | 0 | 9 | 10 | 41 | Q3 FY27 |
| P-05 | Low-SWaP variant, business aviation | New product | In flight | 15 | 150 | 60 | 73 | 40 | 323 | Q2 FY28 |
| P-06 | Download tooling and workflow refresh | Service | In flight | 60 | 0 | 38 | 8 | 2 | 48 | Q1 FY27 |
| P-07 | FDR capacity extension to 200 h | Enhancement | In flight | 10 | 70 | 45 | 32 | 15 | 162 | Q3 FY28 |
| P-08 | DO-326A airworthiness security | Compliance | In flight | 45 | 5 | 30 | 27 | 15 | 77 | Q4 FY27 |
| P-09 | Production line capacity expansion | Manufacturing | In flight | 25 | 95 | 10 | 35 | 10 | 150 | Q2 FY28 |

**Demand against FY27 capacity**

| Discipline | Demand | Capacity | Utilisation |
|---|---|---|---|
| Hardware | 498 | 980 | 51% |
| Software | 220 | 760 | 29% |
| Systems | 281 | 540 | 52% |
| Certification | 277 | 240 | **115%** |
| Total | 1,276 | 2,520 | 51% |

## 6. User-proposed projects (not yet scoped)

| project_id | project | proposed_by | note |
|---|---|---|---|
| U-01 | Deployable recorder line extension | VP Engineering | No scope or effort established |
| U-02 | Direct-to-operator retrofit channel | VP Sales | Route-to-market play, no engineering scope |
| U-03 | Wireless data offload | CTO | Exploratory |

## 7. Prioritisation framework

**Weighted scoring.**

| Criterion | Weight |
|---|---|
| Customer value | 25% |
| Strategic alignment | 20% |
| Revenue impact | 20% |
| Risk reduction | 15% |
| Time criticality | 10% |
| Effort (inverse) | 10% |

## 8. Scenarios

| Scenario | Emphasis |
|---|---|
| Base | Weights as above |
| Growth | Revenue impact and customer value up; effort down |
| Sustainment | Risk reduction and installed-base protection up |
| Compliance-first | Time criticality and regulatory exposure up |

## 9. Exclusion rules and thresholds

- Mandatory projects are never cut at the funding line without escalation.
- Projects under 20 engineering weeks remaining are not individually ranked.
- No project may be recommended for cancellation without naming the
  contractual or regulatory consequence.

---

## What this brief is testing

| Question | How this brief probes it |
|---|---|
| **Does it find the bottleneck?** | Aggregate utilisation is 51% and looks comfortable. Certification is at 115%. Any answer that reports headroom without naming certification has failed |
| Does it see who consumes the bottleneck? | P-01, P-02 and P-08 are all compliance and consume 180 of 277 certification weeks. The constraint is largely mandatory work |
| Does it refuse to invent effort? | U-01, U-02, U-03 have none. Any score attached to them is a failure |
| Does it use platform granularity? | 6,400 legacy CVRs are spread across five platforms of differing age. Reach for an STC-dependent project depends on which platforms are covered |
| Does it connect to upstream evidence? | Market Insights found a 13,500-aircraft US retrofit cohort closing 2030; SO-1 targets it; P-02 is the STC work that would serve it |
| Does it distinguish prerequisite from priority? | P-03 memory IC redesign likely gates P-05 and P-07 but should score poorly alone |
| Does it quantify scenarios? | Four defined; re-weighting alone should be treated as insufficient |
| Does it state missing inputs? | FY29 capacity blank; no customer, technology or sustainment agent has run |
