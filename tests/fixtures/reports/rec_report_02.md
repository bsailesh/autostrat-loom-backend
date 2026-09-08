**Subject:** Market landscape for 25-hour CVR / 140+ hour FDR compact crash-protected recorders · **Evidence base:** Tier 2 public sources only (no Tier 1 user data supplied) · **Date window:** 2020–Sep 2026

## Key Insights

- **Published market sizes diverge ~30× (USD 87 M → USD 4.7 B) because of scope definition, not disagreement about demand** — the low cluster measures crash-protected hardware, the high cluster appears to bundle systems, DAUs/QARs and data services *(Confidence: Medium)*.
- **An independent bottom-up reconstruction of commercial-transport recorder hardware demand lands at ~USD 178 M/yr for the 2026–2030 window**, sitting just above the hardware cluster because it annualises a temporary US retrofit wave that the 2025-dated estimates appear to exclude *(Confidence: Medium)*.
- **The line-fit channel is consolidating around airframer qualification rather than open aftermarket competition** — Acron's SRVIVR25 is described as Airbus' chosen and "only Airbus-qualified" 25-hour CVR, distributed via Airbus service bulletin *(Confidence: High)*.
- **Two of the eight named competitors are not verifiable as current 25-hour recorder suppliers** — Thales lists no crash-protected recorder in its own catalogue, and RUAG International states it has largely completed divestment of non-space businesses *(Confidence: High on the corporate facts, Medium on the negative product finding)*.
- **Growth is concentrated in three adjacencies rather than in the core box**: connected/streaming recorders, ground readout tooling and data services, and extra-lightweight AAM/UAS recorders *(Confidence: Medium)*.

---

## 1. Industry Overview

**FACT (Medium):** The category is described as regulation-driven with high barriers to entry, non-discretionary requirements that scale with fleet size, and competition concentrated among a small number of certified specialists (Source: Future Market Insights, gminsights-class industry report, May 2026); a second source calls the structure "moderately concentrated" (Source: Credence Research, Jun 2025). *So what: demand volume is set by fleet and delivery cadence rather than by discretionary buyer preference, which means the competitive contest is over qualification and channel access, not demand creation.*

**OBSERVATION (High):** Form-fit-function replacement is the shared design constraint across every vendor with a published 25-hour product — Acron ("same physical dimensions and mounting points," direct ARINC 757/FA2100 replacement), Curtiss-Wright Fortress ("form-and-fit replacements requiring no airframe change"), Universal KAPTURE (adapter tray for any brand of CVR), Honeywell (lightweight CVR/FDR/COMBI variants) (Sources: acronaviation.com 2026; Curtiss-Wright release, 15 Sep 2022; Universal Avionics; Honeywell product pages). *So what: physical interchangeability is table stakes, so differentiation has migrated to capacity, weight, integrated RIPS, and spares/part-number commonality.*

## 2. Market Size — Triangulation

### Exhibit 2A — Published estimates by source (two scales; the split is the finding)

**Cluster A — hardware-scope estimates** (each █ ≈ USD 10 M)

| Source | Base-year value | Bar |
|---|---|---|
| Credence Research (2024) | $87.3 M | ████████▉ |
| Global Market Insights (2024) | $112.7 M | ███████████▎ |
| Mordor Intelligence (2025) | $117.9 M | ███████████▊ |
| Future Market Insights (2025) | $119.3 M | ███████████▉ |

**Cluster B — broader-scope estimates** (each █ ≈ USD 250 M)

| Source | Base-year value | Bar |
|---|---|---|
| The Business Research Company (2025) | $1.47 B | █████▉ |
| 360iResearch (2025) | $1.88 B | ███████▌ |
| Spherical Insights (2025) | $2.10 B | ████████▍ |
| Market Research Future (2025) | $4.70 B | ██████████████████▊ |

**OBSERVATION (Medium):** No source in the evidence base publishes an explicit scope reconciliation. *So what: any plan, pricing model or share calculation built on a Cluster B figure will overstate reachable recorder-hardware revenue by roughly an order of magnitude.*

### Internal bottom-up estimate — INTERPRETATION (Confidence: Medium)

**Global commercial-transport recorder hardware demand, 2026–2030 window ≈ USD 178 M/yr**

| Input | Value | Source / status |
|---|---|---|
| New commercial deliveries per year | 2,200 | Derived: 44,000 deliveries ÷ 20 yrs (Boeing CMO, boeing.com, 18 Jul 2026) — FORECAST-derived |
| Recorders per Part 25 transport aircraft | 2 (separate CVR + FDR) | NBAA *Business Aviation Insider*, Jul 2026 |
| Unit cost | $25,000 | FAA NPRM costing assumption (Forbes citing FAA, forbes.com, 14 Feb 2024); **ASSUMPTION** that FDR unit cost equals the FAA CVR figure — no FDR price source exists |
| Line-fit subtotal | $110 M/yr | 2,200 × 2 × $25,000 |
| US retrofit cohort | 13,500 aircraft | NTSB comment letter (ntsb.gov), Cirium query 5 Dec 2023 |
| Retrofit units per aircraft | 1 CVR | FAA Reauthorization Act cohort is CVR-only (NBAA, 4 Feb 2026) |
| Retrofit window | 5 yrs to 2030 | Statutory six-year retrofit (NBAA, 4 Feb 2026); **ASSUMPTION** of even annual spread |
| Retrofit subtotal | $67.5 M/yr | 13,500 × $25,000 ÷ 5 |

**Reconciliation:** $178 M sits *above* the Cluster A base-year range ($87–119 M) and far below Cluster B — the most likely reason is that Cluster A's 2024–25 base years predate the annualised US retrofit wave, and that the $110 M line-fit component alone lands almost exactly inside Cluster A, corroborating that Cluster A measures hardware only. **Non-commercial platforms (military, rotorcraft, business aviation, AAM) are excluded: UNKNOWN — insufficient public volume data.**

### Exhibit 2B — TAM / SAM / SOM (concentric rings)

```
 ┌──────────────────────────────────────────────────────────────┐
 │ TAM  ≈ USD 178 M/yr  [GROWTH]                                │
 │ Global commercial-transport recorder hardware, 2026-30       │
 │  ┌────────────────────────────────────────────────────────┐  │
 │  │ SAM  ≈ USD 122.5 M/yr  [GROWTH]                        │  │
 │  │ 25-hour-CVR-class demand: global line-fit CVR +        │  │
 │  │ US mandated retrofit CVR                               │  │
 │  │  ┌──────────────────────────────────────────────────┐  │  │
 │  │  │ SOM  ≈ USD 24.5 M/yr  [GRAY — assumption-led]    │  │  │
 │  │  │ One of five publicly verified 25 h-class         │  │  │
 │  │  │ product families, equal-share basis              │  │  │
 │  │  └──────────────────────────────────────────────────┘  │  │
 │  └────────────────────────────────────────────────────────┘  │
 └──────────────────────────────────────────────────────────────┘
```

**Formula footnotes.** TAM = (2,200 deliveries/yr × 2 recorders × $25,000) + (13,500 retrofit aircraft × $25,000 ÷ 5 yrs). SAM = (2,200 × 1 CVR × $25,000) + $67.5 M retrofit. SOM = SAM × 20%, where 20% = **ASSUMPTION, no source** — equal split across the five publicly verified 25 h-class product families (Acron SRVIVR25; Honeywell HCR-25 / Curtiss-Wright Fortress; Curtiss-Wright Fortress CSR military; Universal KAPTURE; Flight Data Systems Sentry 25 h, company-stated 2026 entry). **Vendor unit shipments, share percentages and list prices are UNKNOWN — no public source found**, so SOM carries Low confidence.

## 3. Segmentation

| Segment axis | Observation | Source | Conf. |
|---|---|---|---|
| End-use | Civil/commercial >55% share (2024); ~70% of revenue (2026F) | GMI Nov 2024; Persistence MR ~2026 | Medium / Low |
| Product | FDR ≈60% of FDR-market value (2026F); CVR fastest-growing at ~6.3% CAGR to 2033 | Persistence MR | Low |
| Demand type | Line-fit narrow-body cadence is primary driver; retrofit/life-extension second | MarketsandMarkets, May 2026 | Medium |
| Business aviation | Line-fit-led, not retrofit-led; NBAA frames upgrades as voluntary | AeroTime, 6 Feb 2026 | High |
| Platform architecture | Part 25 uses separate boxes; next-gen bizav moving to combined CVFDR | NBAA, Jul 2026 | Medium |

*So what: the mandated retrofit cohort and the voluntary business-aviation cohort behave as two different markets — one deadline-driven and finite, one modernisation-driven and open-ended.*

## 4. Geographic Trends

**FACT / FORECAST (Medium):** North America holds the largest share and is forecast to exceed USD 75 M by 2034 (GMI, Nov 2024); Asia-Pacific is forecast fastest-growing, led by China and India including COMAC programmes (Mordor 2025; Spherical Insights Jul 2026), with India at a forecast 7.4% CAGR (FMI, May 2026). **OBSERVATION (Medium):** One vendor reports demand "surging across all three markets at once" — US, EASA and Mexico (Flight Data Systems, Jun 2026). *So what: the retrofit wave is not a single-jurisdiction event, which compresses installer and STC capacity across regions simultaneously.*

Supply-side geography is concentrated in the UK and US: Curtiss-Wright manufactures recorders at Bournemouth, England (CW release, 20 Jun 2023); Acron operates in Britain, the US, Thailand and India (Aviation Today, Apr 2025); Universal's repair station is in Tucson, AZ.

## 5. Growth, Decline and Landscape Status

| Segment / adjacency | Status | Evidence | Conf. |
|---|---|---|---|
| US 25 h CVR retrofit to 2030 | 🟩 [GROWTH] | Statutory six-year retrofit; shops "may be backlogged as 2030 approaches" (Aviation Today, 30 Oct 2025) | Medium |
| Commercial line-fit recorders | 🟩 [GROWTH] | CW guided Commercial Aerospace +13–15% citing "increased sales of avionics and flight data recorders" (CW Q3 2025 8-K, 5 Nov 2025) | High |
| Ground readout tooling / data services | 🟨 [EMERGING] | FDS HHMPI licensed for HCR-25 and SRVIVR25 (Mar 2025); UA Readout Services (15 May 2024) | Medium |
| Connected / streaming recorders (GADSS) | 🟨 [EMERGING] | HCR-25 + Honeywell Aspire SATCOM; RTAR partitioned design | High |
| AAM / eVTOL / UAS lightweight recorders | 🟨 [EMERGING] | xLDR for eVTOL/UAS, Lilium selection (2022); EASA calls VTOL recorder requirement "essential" (2022) | Medium |
| 2-hour CVR class | 🟧 [DECLINING] | Legacy SRVIVR (2 h) and UA 5th-gen 120-min units being superseded by 25 h generations | Medium |
| Civil deployable recorders (ADFR) | 🟧 [DECLINING/STALLED] | Certification was "on schedule" for Q2 2020, EIS "on target" 2021 (FlightGlobal, 2021); no 2024–26 status disclosed | Medium |
| Military CVFDR volumes | ⬜ [GRAY] | Only datapoint is DFIRS ~1,400 units on F/A-18 (2018, historic) | Low |

*So what: the near-term revenue pool is a finite, deadline-bounded hardware wave, while the recurring-revenue pools sit in adjacencies that are still small and, in the deployable case, publicly stalled.*

## 6. Industry Consolidation

**FACT (High):** L3Harris completed the sale of Commercial Aviation Solutions to TJC on 31 March 2025 for ~$800 M ($700 M upfront + $100 M earn-out), creating Acron Aviation with ~1,400 employees; L3Harris flagged a ~$525 M reduction to expected 2025 revenues (FlightGlobal/AeroTime, 31 Mar–1 Apr 2025; Reuters, 24 Apr 2025). **FACT (High):** Honeywell completed the separation of Honeywell Aerospace on 29 June 2026 (Nasdaq: HONA) (Honeywell release / SEC 8-K, Jun 2026). **FACT (High):** RUAG International states it has "largely completed the divestment of its non-aerospace business units and is now fully focused on the space business" (ruag.com, 24 Mar 2026) — contradicting analyst listings that still name RUAG as a CVFDR supplier (Intel Market Research, Feb 2026). *So what: two of the market's largest named participants are now differently-owned entities with narrower mandates, and at least one analyst-listed competitor is a legacy entry rather than a live supplier.*

**OBSERVATION (High):** Consolidation is also vertical and contractual rather than only ownership-based — Curtiss-Wright is the exclusive supplier of Honeywell's next-generation recorders (2019 partnership; Business Wire/Military & Aerospace 2021–23), and Lufthansa Technik, an MRO, now markets its own 25-hour-capable CVFDR. *So what: the effective number of independent 25 h-class engineering bases is smaller than the number of brands in the market, while a new entrant class (MRO-branded units, FDS Sentry) is forming at the edges.*

## Confidence Summary

Corporate-event evidence in this report is strong: the Acron divestiture, the Honeywell Aerospace spin-off, the RUAG exit, the Airbus–Acron SRVIVR25 selection, and Curtiss-Wright's SEC-filed recorder revenue commentary are all High confidence and primary-sourced. Regulator-derived cost and fleet inputs (FAA/NTSB) are also High confidence, and they carry most of the weight in the bottom-up estimate. Market sizing itself is Medium at best: all eight published figures are paywalled-abstract industry forecasts with no scope reconciliation, and four of them are Low confidence. The SOM ring is the weakest element in this report — it rests on an unsourced equal-share assumption, because vendor unit shipments, share percentages and list prices are entirely absent from public evidence. The other material gaps are: no public 25-hour recorder product for Thales or RUAG despite both appearing in analyst vendor lists; no disclosed status for the civil deployable-recorder programme after 2021; no military, rotorcraft or AAM unit volumes with which to size the platforms excluded from the TAM; and an unreconciled US fleet-count discrepancy (29,651 vs 29,561) plus an internal vendor inconsistency in Acron's own voice-capacity claims (25 h vs 50+ h) that no third-party source resolves.