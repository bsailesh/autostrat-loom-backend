# Briefing: Executive Summary report, all five agents

A new report at the front of every pack, and a rename of each agent's current
Report 1.

Prompt-level and report-definition changes. No schema change, no new endpoint,
no compute.

---

## Why

Consistent feedback: every agent's output is a firehose. A reader who is not
the analyst wants to know what needs their attention, at the top, without
reading nine reports to find it.

This does not change what the packs contain. It adds a front page that states
conclusions, and leaves the evidence where it already is.

---

## The change

**1. A new Report 0 — "Executive Summary"** — in all five agents, ahead of
everything else.

Report 0 rather than renumbering: `report_number` is stored and the export
iterates it, so existing numbers stay stable and nothing downstream moves.

**2. Each agent's current Report 1 is renamed** to describe what it actually
contains:

| Agent | Current Report 1 title | Renamed to |
|---|---|---|
| Market Insights | Executive Market Summary | Market Summary |
| Voice of Customer | Executive summary | Customer Context Summary |
| Technology & Regulation | Executive technology and regulatory intelligence summary | Technology & Regulatory Landscape |
| Product Sustainment | Sustainment intelligence report | Sustainment Landscape |
| Strategy Synthesis | Strategic opportunity and project universe | Project Universe |

The word "executive" belongs to Report 0 now. Nothing else should carry it.

---

## What Report 0 is

**Up to ten bullets. Fewer is better — most packs should produce five or six.**
Ten is a ceiling, not a target, and a list of ten is something a reader skims
rather than acts on.

Each bullet is **one thing that needs the reader's attention**, and possibly
their action.

### The rules

**State the conclusion, not the reasoning.** "Certification capacity has no
slack in FY27" — not "analysis of capacity data across five disciplines
indicates that certification is at 99.3% utilisation, suggesting…".

**No sources, no citations, no confidence tags, no hedging.** The proof is in
the report. A reader who wants to know why goes and looks. This page exists to
tell them whether they need to.

**Objective, not defensive.** State what is true. Do not justify, qualify, or
pre-empt disagreement.

**One sentence each.** Two at the very most, where the consequence genuinely
needs its own sentence.

**Plain language.** No report numbers, no internal vocabulary, no references to
what the agent did or how. The reader does not care that Pass 1 scored
something.

### What earns a bullet

In priority order, where more candidates exist than slots:

1. **Something is wrong, or about to be.** A constraint that binds, a deadline
   that is close, an exposure with no mitigation
2. **Something contradicts what the reader believes.** The most valuable
   bullet on the page, when there is one
3. **Something is dated and therefore schedulable.** An obligation, a runout, a
   window closing
4. **A gap that blocks something.** An objective with nothing against it, an
   analysis unavailable for want of an input

**Prefer one bullet that joins two findings over two that each state one.**

### What does not earn a bullet

- Anything the reader already knows
- Scope framing, methodology, or what the pack contains
- A finding that changes nothing
- Padding to reach ten

### Where the pack cannot support a bullet

If the run is thin — unscoped, Tier 2, missing its central input — say so in
one bullet and produce fewer. **Do not manufacture bullets.** A four-bullet
executive summary on a thin run is honest; ten is not.

---

## What Report 0 is not

**No governing insight.** SCQA stays exactly where it is — Report 7 for
Strategy Synthesis, Report 1 for the others. The two do different jobs: SCQA
reasons toward a conclusion, Report 0 states conclusions. Putting SCQA on the
executive page makes it longer, which is the problem being solved.

**No key insights block.** The three-insight cap and the `Validity:` exemption
apply to the reports as they do today. Report 0 is not a key insights block
with a different name.

**No tables, no exhibits, no structured data.** Bullets only.

**Not a summary of the pack.** It is a list of what needs attention. A pack can
contain a great deal that needs no attention at all.

---

## Agent-specific notes

**Strategy Synthesis.** This is the one that matters most, because it is the
only agent whose reader is the decision-maker. Its Report 0 draws on everything
— the ranking, the capacity position, objective coverage, candidates worth
scoping, and findings from upstream agents. Where a bullet comes from another
agent's evidence, state it as a fact about the business, not as "Technology &
Regulation found…".

**Voice of Customer.** On a Tier 2 run, the strongest available bullets are
usually the untested beliefs and what would settle them. Say that plainly.

**Technology & Regulation.** Dated obligations are the natural bullets. An
undated standing exposure earns one only when it is material.

**Product Sustainment.** A runout before its last-time-buy window, and any part
whose exposure reaches several LRUs. The blast radius is the part an executive
would not otherwise see.

**Market Insights.** Hardest case — its findings are about the world, not the
reader's own position. Prefer what changes a decision: a competitor move, a
structural shift, a closing window.

---

## Worked examples

**Good.**

> Certification capacity has no slack in FY27 — 99.3% committed, and it cannot
> be contracted because the constraint is DER availability.

> Two projects, 323 engineering weeks between them, serve no stated objective.

> A single-sourced power device went end-of-life on 30 September. The
> replacement decision is already late.

> Nothing in the portfolio addresses the retrofit margin objective, and the
> only candidate that would has no effort estimate.

**Bad — reasoning rather than conclusion.**

> Analysis of the capacity data supplied across five engineering disciplines
> indicates that the certification bucket is operating at 99.3% of declared
> capacity, which suggests limited headroom for additional work.

**Bad — defensive.**

> Based on available evidence, which should be treated with appropriate
> caution given the absence of Tier 1 data, it appears that lead times may
> possibly be a competitive concern.

**Bad — internal vocabulary.**

> Report 3's bottleneck analysis found ELEC at 115.7% utilisation per the
> computed bucket utilisation table.

**Bad — no action implied.**

> The market for electromechanical actuation is growing.

---

## Implementation

- A `ReportSpec` with `number=0` in each agent's `reports.py`
- Rename each agent's Report 1 title in its own `reports.py`
- The rules above belong in the **shared** Consulting-Grade Output Standard,
  since they apply to all five agents. Remember there are **two copies** —
  `market_insights/standards.py` (imported by Strategy Synthesis) and
  `tech_regulation/standards.py`. Check whether Voice of Customer and Product
  Sustainment import one or carry their own
- Report 0 is generated **last**, after every other report, so it can draw on
  what they found. It is **presented first**
- Frontend: the report list must show Report 0 at the top. Check that sorting
  by `report_number` handles 0 correctly and does not treat it as falsy
- Export: the Word pack must open with Report 0

---

## Verification

Prompt changes are unverified until a real run.

After implementing, run **Strategy Synthesis on the Arden tenant** and read
Report 0 as if you were an executive who has never seen the platform. The test:
does it tell you what needs your attention, and would you know what to do next?

Then check it against the pack — every bullet must be supported by something in
the reports. **A bullet with no backing is the one failure mode that matters**,
because this page carries no sources and a reader cannot check it themselves.

---

## Definition of done

- [ ] Report 0 "Executive Summary" in all five agents
- [ ] Each agent's Report 1 renamed; no other report carries "executive"
- [ ] Up to ten bullets, conclusions not reasoning, no sources or hedging
- [ ] Fewer bullets on thin runs; no padding
- [ ] SCQA unchanged in its current location
- [ ] Report 0 generated last, presented first
- [ ] Frontend lists it first; export opens with it
- [ ] Rules in the shared standard, all copies updated
- [ ] Verified by a real Agent 5 run, every bullet traceable to the pack
- [ ] Committed, pushed, merged via PR
