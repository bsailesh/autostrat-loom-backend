# Agent 3 — Tech & Regulation: scoping input specification

## Why this agent needs scoping more than the others

Market Insights works on a free-text product line because markets are publicly
discussed — name a market and there is a market to research.

Regulation does not work that way. There are tens of thousands of regulations,
standards and certification requirements across the jurisdictions this agent
covers. Without knowing what the customer makes, where they sell it, and what
it is approved under, the agent can only report that FAA, EASA and ICAO exist.

The difference between the two output sentences:

> "EASA has issued an amendment to CS-25."

> "EASA has issued an amendment to CS-25 Subpart F effective 14 March 2028,
> which applies to equipment certified under TSO-C106 — three of your five
> product lines — and triggers requalification of the affected articles."

The second sentence is the product. The only thing standing between them is
the scoping input.

**Two things are being conflated in the source spec and must be separated.**
The Tier 1 list — technology roadmaps, engineering reports, R&D reports, PLM,
ECN documentation, certification and compliance documentation, internal
standards databases — is *evidence to ingest*. It is twelve document types and
nobody fills that in a settings form.

The **applicability envelope** is a dozen structured fields describing what the
customer makes and where. It is small, fillable in fifteen minutes, and it is
what makes the agent on-point. Tier 1 evidence deepens the analysis; the
envelope decides whether the analysis is about the customer at all.

---

## Part 1 — The applicability envelope

Required for a scoped run. Each field below states what it scopes and what is
lost without it.

### 1.1 Product categories

What the customer makes, in their own words, as a list rather than a paragraph.

```
category_key, category_name, description
EMA-FIN,  Missile fin actuation,      Electromechanical fin actuators for tactical missiles
EMA-TVC,  Thrust vector control,      Launch vehicle and upper stage TVC actuators
EMA-UTIL, Utility actuation,          Door, hatch and secondary system actuators
```

**Scopes:** which technology domains and regulation classes are relevant at all.

**Without it:** the agent reports the industry's technology landscape rather
than the customer's. Every subsequent field becomes less useful because there
is nothing to attach findings to.

### 1.2 Jurisdictions

Where the product is sold, certified or operated.

```
jurisdiction, role
United States,    primary market
European Union,   primary market
United Kingdom,   secondary
Japan,            export only
```

`role` matters: a regulator in a primary market and one in an export-only
market produce findings of different weight, and the agent should say which.

**Scopes:** which regulators apply — FAA, EASA, CAA, CAAC, ANAC, national
defence authorities.

**Without it:** the agent reports every major regulator, which is noise.

### 1.3 Certification basis — the highest-leverage field

What each product category is approved under.

```
category_key, basis_type, basis_identifier, status, held_since
EMA-FIN,  MIL-STD,  MIL-STD-810H,     qualified,     2021
EMA-TVC,  Standard, AIAA S-120A,      qualified,     2022
EMA-UTIL, TSO,      TSO-C196b,        approved,      2019
EMA-UTIL, Part,     14 CFR Part 25,   installed on,  2019
```

**Scopes:** which specific requirements attach to the customer's approvals, and
therefore which regulatory changes actually bind them.

**Without it:** the agent can report that a regulation changed but not whether
it applies. This is the single field that most determines whether output is
intelligence or a newsletter. If a customer supplies nothing else, ask for this.

### 1.4 Platforms and applications

What the product goes on.

```
platform, platform_class, relationship, programme_status
Tactical missile — surface launched, Defence guided weapons, shipping, active production
Small launch vehicle,                Space launch,           shipping, active production
Rotorcraft — medium,                 Part 29 rotorcraft,     shipping, in service
Narrowbody commercial,               Part 25 transport,      pursuing, design-in window
```

`relationship` distinguishes what they supply today from what they are chasing
— and the agent should treat a design-in pursuit differently from an installed
position. A regulatory change on a platform you are pursuing is an entry
condition; the same change on a platform you ship is a cost.

**Scopes:** which airworthiness, safety and emissions rules attach.

**Without it:** certification findings cannot be connected to revenue.

### 1.5 Standards held

Which standards the customer is currently compliant with or certified against.

```
standard_id, revision, scope, status
DO-160,   G,     Environmental qualification,     compliant
DO-254,   —,     Airborne electronic hardware,    in progress
AS9100,   D,     Quality management,              certified
MIL-STD-461, G,  EMI/EMC,                         compliant
```

**Scopes:** what a revision to that standard would cost. A new revision of a
standard you hold is a requalification event with a date; a new revision of one
you don't is background.

**Without it:** standards changes are reported without consequence.

### 1.6 Supplier watch list

Named suppliers whose technology developments and discontinuations matter.

```
supplier, what_they_supply, criticality
Vendor A,  GaN power devices,              single source
Vendor B,  Roller screws,                  dual sourced
Vendor C,  Position sensors — resolver,    single source
```

**Scopes:** whose product change notices and end-of-life announcements to
surface.

**Without it:** supplier developments are reported only when they are
newsworthy enough to appear in trade press, which is far too late for a
discontinuation.

**Shared with Product Sustainment**, which needs the same list for obsolescence
monitoring. See Part 5.

### 1.7 Technology domains to monitor

Selected from a list the spec already provides per industry. For aerospace and
defence: electrification, advanced air mobility, UAV/UAS, space systems,
cybersecurity, digital twins, advanced manufacturing. Plus free text for
anything not listed.

**Scopes:** the technology half of the agent's remit.

**Without it:** the agent infers domains from product categories, which works
but misses adjacent technologies the customer is watching deliberately.

---

## Part 2 — Exclusions

**A scoping input that can only add scope produces noise.** Equally important
is what not to report.

```
exclusion_type, value, reason
platform_class, Part 23 general aviation, not a market we serve
jurisdiction,   China,                     no sales or certification intent
domain,         Digital twins,             not on our roadmap
```

Exclusions are stated in the output — "excluded at your direction" — not
silently applied. A customer should be able to see what was filtered, because
an exclusion that turns out to be wrong is itself a finding.

---

## Part 3 — Tier 1 evidence (optional, deepens rather than scopes)

Separate from the envelope. These are documents, not form fields, and each is
optional.

| Evidence | What it enables |
|---|---|
| Technology roadmap | Mapping external technology maturity against the customer's own plan |
| Certification documentation | Precise applicability rather than inferred from basis identifiers |
| Internal standards database | Gap analysis between standards held and standards changing |
| Engineering change documentation | Connecting regulatory change to work already in flight |
| Competitive technology assessments | Correcting or confirming public evidence on competitors |
| Supplier technical documentation | Earlier warning than public PCNs |

**None of these is required**, and the agent must state which were supplied.
A run with the envelope and no documents is a legitimate scoped run; a run with
documents and no envelope is not, because nothing tells the agent what applies.

---

## Part 4 — Degradation

The agent never blocks on missing input. Each absence has a stated consequence,
in the output, in the same way Agent 5 reports a missing capacity file.

| Missing | Consequence stated in output |
|---|---|
| Product categories | Unscoped run — industry landscape, not your obligations. Say so at the top |
| Jurisdictions | All major regulators reported; relevance not assessed |
| **Certification basis** | **Regulatory changes reported without applicability. The single most consequential omission** |
| Platforms | Findings cannot be connected to programmes or revenue |
| Standards held | Standards changes reported without requalification consequence |
| Supplier watch list | Supplier developments limited to what reaches trade press |
| Technology domains | Inferred from product categories; deliberate adjacencies missed |
| Exclusions | No filtering; expect noise from adjacent markets |

**An unscoped run must say so in its first line.** The failure mode to avoid is
a reader mistaking an industry survey for their own regulatory obligations.

---

## Part 5 — What is shared with other agents

Three fields are needed by more than one agent:

| Field | Tech & Reg | Sustainment | Voice of Customer |
|---|---|---|---|
| Product categories | yes | yes | yes |
| Platforms and applications | yes | yes | yes |
| Supplier watch list | yes | yes | no |
| Certification basis | yes | partially | no |
| Standards held | yes | no | no |
| Customer segments | no | no | yes |
| Part lists / BOM | no | yes | no |

**Recommendation: build this as Agent 3's own scoping input for now, but name
the shared fields explicitly** so a shared Product Profile can be extracted
later without renaming anything. Building the shared abstraction before two
agents actually use it repeats the mistake of designing an interface before
knowing what flows through it.

The natural future shape is a **Product Profile** holding categories, platforms
and suppliers, with per-agent extensions: certification basis and standards for
Tech & Reg, part lists and BOM for Sustainment, segments and channels for Voice
of Customer.

---

## Part 6 — Worked example: Arden Actuation Systems

Using the demo company already in the platform, to show the envelope is small
enough to be real.

**Product categories:** missile fin actuation; thrust vector control; utility
actuation; ground-based air defence actuation; hydraulic-replacement retrofit.

**Jurisdictions:** United States (primary), European Union (primary), United
Kingdom (secondary).

**Certification basis:** MIL-STD-810H and MIL-STD-461G for defence lines;
TSO-C196b and 14 CFR Part 25 installation for utility actuation; AIAA S-120A
for launch TVC.

**Platforms:** tactical missile surface- and air-launched (shipping); small
launch vehicle and upper stage (shipping); medium rotorcraft (shipping);
business jet (shipping); mobile launcher (shipping); narrowbody commercial
(**pursuing** — design-in window).

**Standards held:** DO-160G compliant; DO-254 in progress; AS9100D certified;
MIL-STD-461G compliant.

**Supplier watch list:** GaN power devices (single source); roller screws (dual
sourced); resolver position sensors (single source).

**Technology domains:** electrification; advanced air mobility; UAV/UAS; space
systems; cybersecurity.

**Exclusions:** Part 23 general aviation; China; rail and marine.

That is roughly fifteen minutes of work and it transforms what the agent can
say. Note the two fields that connect directly to findings already in the
platform: **DO-254 in progress** matches committed project P-01, and **GaN
power devices, single source** matches P-03 and objective SO-2. A regulatory or
supplier finding against either lands straight on work Arden is already doing.

---

## Open questions

1. **Form or CSV?** The envelope is small enough for a form, but certification
   basis and platforms are naturally tabular and a customer may already have
   them in a spreadsheet. Suggest form-first with CSV import as an option,
   rather than Agent 5's CSV-first pattern.
2. **Certification basis vocabulary.** TSO, CS, Part, MIL-STD, ETSO, STC and
   PMA are not interchangeable and the agent needs to know which is which.
   Controlled list with free text fallback, or free text with the agent
   interpreting?
3. **Does `relationship: pursuing` change agent behaviour**, or is it only
   context for the reader? It should change behaviour — an entry condition is
   not a cost — but that needs stating in the prompt.
4. **How does an unscoped run present itself?** A banner, a different report
   title, or a first-line statement. Needs to be unmissable.
