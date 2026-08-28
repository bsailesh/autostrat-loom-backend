# Market Insights Agent — Phase 1

Standalone, command-line-testable service that runs the Market Insights agent
against a subject and produces the 9 required reports, following
`market_insights_agent_spec.md`.

Phase 1 goal (from `claude_code_kickoff_briefing.md`): **prove the agent
produces good, spec-compliant output as real code.** No web server, no database,
no auth — those are later phases.

## Install

```bash
python -m venv venv && venv\Scripts\activate      # Windows
pip install -r requirements-phase1.txt
```

Set your key (either export it or drop it in a `.env` at the repo root — the same
file the backend uses; only `ANTHROPIC_API_KEY` and `MARKET_INSIGHTS_MODEL` are
read here):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
python run_agent.py --subject "marine propulsion electrification"
```

Output lands in `./output/` as two files:

- `<subject>-<timestamp>.json` — one object per report
  (`report_number`, `title`, `content`, `confidence_summary`) plus the research
  brief and the list of sources actually consulted. This is the shape Phase 2
  (DB) and Phase 3 (API) will build on.
- `<subject>-<timestamp>.md` — the same 9 reports as one readable document, for
  judging against the hand-built TCAS / electromagnetic-actuator samples.

### Useful flags

| Flag | Purpose |
| --- | --- |
| `--model claude-sonnet-5` | Cheaper/faster model while iterating on prompts (default is `claude-opus-5`). |
| `--only-reports 1,2,6` | Generate a subset of the 9 reports. Research still runs in full. |
| `--max-searches 24` | Raise the web-search cap for the research phase (default 16). |
| `--research-rounds 3` | More research passes; rounds 2+ target the weakest areas. |
| `--from-research output/<prior>.json` | Reuse a prior run's research brief + sources and skip the slow/paid web-search phase. For iterating on synthesis prompts. |
| `--print` | Also print the full Markdown bundle to stdout. |

**Runtime:** the research phase runs ~10–15 min (live web search, ~25 queries,
Opus 5). Each report then takes ~4–5 min to synthesize, so a full 9-report run is
roughly 45–60 min. Use `--only-reports` + `--from-research` to iterate quickly
without paying for research each time. `--model claude-sonnet-5` is faster still.

## How it works

1. **Research phase** (`market_insights/agent.py::research`) — one conversation
   with the Claude **web search** tool enabled. The system prompt is built from
   the spec's Agent Prompt / Mission / Scope Boundary / Time Horizon / Required
   Analysis text close to verbatim (`market_insights/standards.py`). The model
   actually searches the web, organizes findings into evidence rows under 9
   headings, and does a second pass on the weakest areas. We capture the brief
   text, every search query, and every source URL returned.
2. **Synthesis phase** (`::_synthesize_one`) — for each of the 9 reports, one
   streamed call that returns the report as plain Markdown (700–1400 words). No
   web search here: synthesis draws **only** on the research brief, so gaps
   surface as `UNKNOWN` instead of being invented. The JSON shape the briefing
   asks for (`report_number`, `title`, `content`, `confidence_summary`) is
   assembled from that Markdown — `confidence_summary` is sliced from the
   report's own closing `## Confidence Summary` section. The Evidence &
   Confidence Standard and the Consulting-Grade Output Standard (SCQA opening,
   Key Insights boxes, triangulation, "so what" on every finding, a visual per
   report, no recommendations) are enforced in the synthesis system prompt.

## Files

```
run_agent.py                 CLI entry point
market_insights/
  standards.py               verbatim spec text (standards + agent prompt)
  reports.py                 the 9 report specs (contents + required exhibits)
  prompts.py                 research / synthesis prompt assembly
  agent.py                   MarketInsightsAgent: research() + synthesize()
  config.py                  API key + model selection
requirements-phase1.txt
```

## What to check in the output

Per the briefing, the bar is the two hand-built samples:

- Every finding confidence-tagged (High / Medium / Low).
- Report 1 opens with a Situation / Complication / Question / Answer governing
  insight (a claim, not a topic label).
- Every other report opens with a 4–5 bullet Key Insights box.
- Conflicting market-size estimates are triangulated with a stated bottom-up
  method and listed assumptions — not averaged, not left as a bare range.
- Every material finding has a "so what:" implication — never a recommendation.
- Where evidence is insufficient, the agent says so instead of guessing.

If the output is noticeably weaker than the samples, iterate on the prompts in
`market_insights/prompts.py` and `standards.py` before moving to Phase 2.
