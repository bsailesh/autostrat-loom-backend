# Briefing: patent axis scoping, and tighter executive summaries

Two prompt-level changes. No code, no schema, no endpoints.

Both are driven by the first live Technology & Regulation run against the Arden
envelope (4 Oct 2026).

---

## Change 1 — Scope the patent requirement to what the tool can actually do

**Agent 3 only.**

### The problem

The run reported its own patent coverage as:

> "Patent — Gray. Unperformable for suppliers (anonymised) and unperformed for
> competitors… a web search is not a patent-database search."

And in Report 4:

> "Patent landscape — UNKNOWN on the central question. Axis-1 search in missile
> fin actuation returned [nothing usable]… no candidate work was raised from the
> patent axis, because the evidence does not establish a position."

That is honest, and the agent was right to say it. But the prompt asks for
patent filings, families, emerging assignees, technology clusters, activity
trends and licensing — and the agent has web search only. The requirement
cannot be met with the sources available, so the section is a shell.

A requirement that cannot be satisfied produces either a hollow section or, in
a less careful agent, invented content. Neither is acceptable.

### The change

Replace the patent landscape requirement in `tech_regulation/standards.py`
(§4.4 in `tech_regulation_prompt_draft_v2.md`) with one scoped to reachable
sources:

**What the agent researches:**

- Patent and application filings reported in trade press, company
  announcements, press releases and investor materials
- Licensing agreements, cross-licensing and patent-pool participation where
  publicly announced
- Patent litigation and opposition proceedings reported in public sources
- IP positions asserted in company technical papers, conference papers and
  standards contributions
- Patent-analytics vendor reports where a specific finding and date can be
  cited

**What the agent does not claim:**

- Filing counts, family sizes or assignee rankings. These require a patent
  database and cannot be derived from web search
- Technology clustering or whitespace analysis
- Any statement about what has *not* been filed

**Required statement in Report 4**, wherever patent material appears:

> "This is not a patent-database search. Patent findings below are limited to
> filings, licensing and litigation reported in public sources. Absence of a
> finding here is not evidence that no filing exists."

**The search axes, revised.** The three-axis rule stands, but axis 2 degrades
when the supplier watch list is anonymised:

1. The customer's own product categories — unchanged, and the most valuable
   axis, since an unknown entrant filing in your category is the signal worth
   catching
2. Named assignees from the supplier watch list and competitors found in
   research — **unavailable where supplier names are anonymised or
   placeholders.** Say so rather than reporting the axis as performed
3. Monitored technology domains — unchanged

State which axes ran and which did not.

**The existing rule stands unchanged:** a patent is evidence of investment and
intent, not of a working or commercially available product. Always distinguish
patent activity from commercial adoption.

### Logged as a known limitation

Full patent landscape analysis needs a patent database — EPO OPS, USPTO
PatentsView, Google Patents BigQuery or a commercial vendor. That is a new
dependency and a new cost, out of scope here. Record it as a gap so the next
person does not re-derive the same conclusion.

### A related data problem, worth fixing separately

The Arden demo envelope uses `Vendor A`, `Vendor B`, `Vendor C` as supplier
names. These are placeholders from the scoping spec's worked example, and the
agent handled them correctly — every supplier finding reads "category-adjacent
to Vendor A… BOM presence unestablished because the watch list is anonymised."

But supplier discontinuation monitoring is the highest-value function this
agent performs, because it produces **dated** candidate work. Anonymised names
make every finding unattributable.

**This is demo data, not a code change.** Replace the placeholders with real
supplier names in the Arden envelope before the demo.

---

## Change 2 — Tighter key insights, across all agents

**Shared standard. Affects all five agents.**

### The problem

Key insights blocks have grown into summaries of the report rather than the
findings that matter. From the 4 Oct run's executive summary, the Answer
paragraph alone carries: five dated items, a caveat about seven undated ones,
a statement that three held standards remain current, and a separate note about
certification basis mismatches. One paragraph doing four jobs.

The instruction "lead with the finding" is already in the standard and every
agent believes it is complying. The fix is a constraint, not a reframing.

### The change

In the **Consulting-Grade Output Standard**, for the **key insights** block
only:

**Maximum three insights. One sentence each. Each states its consequence.**

- Three is a ceiling, not a target. Two well-evidenced insights beat three
  where the third is padding
- One sentence means one sentence. A sentence with three semicolons is three
  sentences
- Each insight states what follows from it — the consequence — not just the
  observation
- Confidence and classification stay, as a short tag rather than a clause
- **Everything cut moves into the body.** Nothing is lost; it stops being
  presented as a headline

**Selection rule.** Where more than three candidates exist, prefer, in order:

1. A finding that changes what the reader would do
2. A finding that contradicts what the reader likely believes
3. A finding that is dated, and therefore schedulable
4. A gap that blocks something — a missing input, an unserved objective, an
   unavailable analysis

Prefer one insight that connects two findings over two insights that each state
one. The 4 Oct run's strongest available insight was not in its key insights
block: *a successor to a held standard has already published, and a supplier
discontinuation in a single-sourced category has already elapsed — both land on
work already committed.*

### What does not change

**The SCQA governing insight is unaffected.** Situation / Complication /
Question / Answer is four sentences by construction, and it is where synthesis
across findings happens. Agent 5's Report 7 governing insight — connecting the
capacity constraint to the unserved objective to reach a route-to-market
conclusion — is the standard working as intended. Do not cap it.

The distinction: **SCQA reasons, key insights report.** A cap on reporting does
not constrain reasoning.

### Risk, and how to check it

Market Insights and Agent 5 produce good summaries today. A cap could cut
something load-bearing.

After the change, re-read the key insights blocks from the three live agents'
most recent runs and confirm nothing essential was lost — specifically the
Agent 5 run in the Arden tenant, whose key insights carry the power-electronics
bottleneck, the certification bucket at the limit, and the objective coverage
position. If three is too tight for that report, say so rather than forcing it.

---

## Out of scope

- No patent database integration
- No code, schema or endpoint changes
- No change to SCQA
- No change to the Evidence & Confidence Standard

## Definition of done

- [ ] Agent 3's patent requirement scoped to reachable sources, with the
      required disclaimer in Report 4
- [ ] Axis availability stated, including when axis 2 is unavailable due to
      anonymised suppliers
- [ ] Patent database logged as a known limitation
- [ ] Key insights capped at three, one sentence each, consequence stated, in
      the shared standard
- [ ] SCQA explicitly exempt, with the reason
- [ ] Re-read of existing runs' key insights confirms nothing load-bearing is
      lost
- [ ] Committed, pushed, merged via PR
