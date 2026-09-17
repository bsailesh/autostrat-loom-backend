# Briefing: Fix competitor discovery in the Market Insights agent

## The bug

The agent treats the user's supplied competitor list as a closed set rather
than a starting point, and truncates discovered competitors to fit a hard cap
of four.

Evidence from production run `1f843fe9` (aerospace actuation, 4 Sept). The
user named three competitors: Moog, Safran, Honeywell. Report 4's comparison
grid held five: those three plus Woodward and Curtiss-Wright, which the agent
was forced to surface because the Safran/Collins divestiture made them
unavoidable. Meanwhile Report 1's own Governing Insight names **Parker Hannifin
and Liebherr** as two of the five firms holding 47.6% of aircraft EMA revenue —
and neither appears in the grid or as a profile. The agent found them and
dropped them.

Three things combine to cause this:

1. **A hard cap of four competitors**, in `market_insights/reports.py` (twice)
   and `market_insights/standards.py` (once).
2. **No instruction anywhere to discover competitors.** `prompts.py:73` says
   "profiles of the leading players"; `standards.py:161` asks "which
   competitors have introduced new products"; `standards.py:227` monitors
   "competitors" — all presuming a known set. Nothing tells the agent to go
   find them.
3. **The user's list is framed as a restriction.** `app/routers/market_insights.py:66`
   injects `Competitor focus: {list}` into the run subject, and
   `app/schemas.py:89` describes the field as "Competitors to focus on."

## The fix, in principle

**Separate discovery from display, and separate source precedence from scope.**

- Discovery is uncapped and evidence-driven.
- Display caps exist only because pages have widths.
- A user-named competitor is guaranteed to appear *somewhere in the report*,
  but is not guaranteed a grid column. Grid selection is by significance.
- A user-named competitor that turns out to be insignificant or publicly
  undisclosed goes in an "Also identified" list **with the reason** — that
  is itself a useful finding, and silently dropping it is the failure we are
  fixing.

Caps after this change:
- **Discovery**: uncapped
- **Report 3 profiles**: up to 10, ranked by significance
- **Report 4 grid**: 6 columns total (reference product + up to 5 competitors)
- **Everyone else**: "Also identified" list, one line each

The 6-column figure is not arbitrary: the Word export renders the Harvey Ball
grid in a landscape section, and 6 columns × 20 rows was verified to fit on
8 Sept. Do not raise it without re-verifying the export rendering.

## Changes

### 1. `market_insights/standards.py` — replace the Competitor Comparison block

Currently at line 243, beginning `Competitor Comparison: Compare the current
product against up to four competitors`. Replace that whole paragraph with:

```
Competitor Set Definition: You must independently identify the significant
competitors in this market from evidence, not rely on a supplied list. There is
no cap on how many you may discover. Any competitors the user has named are
guaranteed to appear somewhere in the reports, but they do not define or limit
the competitive set, and they earn a comparison-grid column only if they rank
among the most significant by evidence. If a user-named competitor proves
insignificant, publicly undisclosed, or in an adjacent market, say so explicitly
in the "Also identified" list rather than omitting it.

Rank competitors by market significance: revenue or share where disclosed,
platform or program presence, breadth of public technical disclosure, and
recent structural activity.

Competitor Comparison: Compare the current product against the most significant
competitors using only publicly available information. Compare product
portfolio, performance specifications, market positioning, digital capabilities,
connectivity, service offerings, warranty (if publicly disclosed), sustainability
claims, and public differentiators. Do not speculate about undisclosed
capabilities.
```

### 2. `market_insights/standards.py` — Competitive Monitoring (line ~227)

Add a clause making clear that monitoring covers **all identified competitors**,
not only those the user named.

### 3. `market_insights/reports.py` — Report 3, `must_include` (line ~69)

Append:

```
"Profile up to 10 competitors, ranked by market significance. Close the report "
"with an 'Also identified' list naming every other competitor found, each with "
"a one-line reason it is not profiled (for example: insufficient public "
"disclosure, adjacent market, below significance threshold)."
```

### 4. `market_insights/reports.py` — Report 4, `must_include` (line ~83)

Replace `"Compare the current product plus up to four competitors."` with:

```
"Compare the current product plus the 5 most significant competitors (6 columns "
"total, which is what fits one landscape page). Selection is by evidence-based "
"significance, not by whether the user named them. Below the grid, list any "
"competitor excluded from it with a one-line reason."
```

Keep the existing "no current product defined" fallback that follows — it is
correct behaviour and produced the right result in production.

### 5. `market_insights/reports.py` — Report 4, exhibit spec (line ~93)

Replace `"columns = the reference product + up to 4 competitors"` with:

```
"columns = the reference product + up to 5 competitors, 6 columns maximum"
```

### 6. `app/routers/market_insights.py` — line 66

Replace:

```python
parts.append(f"Competitor focus: {scope.competitors.strip()}")
```

with:

```python
parts.append(
    "Competitors the user has specifically asked about (include these in the "
    "analysis, but do not limit the competitive set to them): "
    f"{scope.competitors.strip()}"
)
```

**Check whether this string is persisted** — `AgentRun.subject` is a frozen
snapshot composed by `_compose_subject()` and is used for the Word export
filename. If a longer string would make filenames unwieldy, keep the stored
subject short and pass the expanded wording to the agent separately. Tell me
which you did.

### 7. `app/schemas.py` — line 89

Change the field description from "Optional. Competitors to focus on." to
"Optional. Competitors the user wants explicitly covered. Does not limit which
competitors the agent discovers."

### 8. `market_insights_agent_spec.md` — lines 443 and 539

Mirror changes 1 and 4 so the spec and the code do not drift. The spec is the
contract; leaving it stale reintroduces the bug next time someone works from it.

## Out of scope

- Do not change the frontend scope-configuration form.
- Do not change the report count, report titles, or any other report's content.
- Do not touch the export pipeline.
- Do not alter the Evidence & Confidence Standard or the Consulting-Grade
  Output Standard.

## Verification

The existing test suite will not catch this — it is prompt behaviour, not code
logic. So:

1. Run the full suite and confirm 60/60 still passing, in more than one file
   order (see `tests/conftest.py`).
2. Grep the whole repo for `up to four`, `up to 4`, and `4 competitors` and
   confirm no stale instances remain.
3. Note in the PR that behavioural verification requires a live agent run,
   which cannot be done from here.

## Definition of done

- [ ] No remaining cap of four anywhere in code or spec
- [ ] Explicit discovery instruction present, stating that user-named
      competitors do not limit the set
- [ ] "Also identified" list required in Report 3 and below the Report 4 grid
- [ ] Router and schema wording no longer frame the user's list as a restriction
- [ ] Spec markdown updated to match the code
- [ ] Test suite passing in multiple orders
- [ ] Committed, pushed, merged via PR
