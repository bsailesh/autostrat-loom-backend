# Claude Code Kickoff Briefing — Market Insights Agent, Phase 1

## Goal

Build a standalone, command-line-testable service that runs the Market Insights agent
against a given subject and produces the 9 required reports, following the attached
specification exactly. This is Phase 1 of 6 in bringing this agent to production — the
goal here is ONLY to prove the agent produces good, spec-compliant output as real code.
Nothing else.

## What "good" looks like

The output should match the rigor of the two sample runs already produced by hand for
this project (ask me for these if you don't have them — one on airborne collision
avoidance systems / TCAS, one on electromagnetic actuators). Specifically:

- Every finding is confidence-tagged (High/Medium/Low) per the Evidence & Confidence Standard.
- Report 1 (Executive Summary) opens with a Governing Insight in Situation/Complication/
  Question/Answer form.
- Every other report opens with a Key Insights box: 4-5 confidence-tagged bullets.
- Conflicting source estimates are triangulated (a defensible bottom-up estimate with
  stated assumptions), not just averaged or left as an unresolved range.
- Every material finding states a "so what" — the implication, never a recommendation
  (this agent must never recommend actions; that's Strategy Synthesis's job).
- Nothing is fabricated. Where evidence is insufficient, the agent says so explicitly
  rather than guessing.

## Attached

`market_insights_agent_spec.md` — the complete, self-contained specification for this
agent, including the two shared standards (Evidence & Confidence, Consulting-Grade
Output) it must follow. This file is everything you need; you should not need to open
the full requirements document.

## Technical approach

- Use the Claude API (Anthropic SDK) with the web search tool enabled — this agent's
  Tier 2 sources are public web research, and it needs to actually search, not rely on
  training data, since market conditions change and specific facts need live sources.
- Structure the system prompt around the attached spec's Agent Prompt / Mission / Scope
  Boundary / Required Analysis sections — don't paraphrase them, use them close to
  verbatim, since the wording (e.g. "never present interpretation or forecast as fact")
  is deliberate.
- Output format: structured JSON with one object per report (report number, title,
  content, confidence summary) — this will make Phase 2 (database storage) and Phase 3
  (API responses) straightforward later, even though neither exists yet.
- Entry point: a script callable like `python run_agent.py --subject "some market topic"`
  that prints or saves the 9 reports. No web server, no database, no auth in this phase.

## Explicit non-goals for this phase

Do NOT build any of the following yet — they're later phases and building them now
means testing everything at once instead of validating the agent core first:

- Database schema or persistence
- FastAPI endpoints
- Authentication / tenant scoping
- Any frontend UI
- Deployment to Lightsail or anywhere else

## When this phase is done

I should be able to run one command, give it a market/industry subject, and get back
9 reports that I can read and judge against the two hand-built samples for quality —
same evidence discipline, same structure, same refusal to fabricate. If the output is
noticeably weaker than the hand-built samples, that's the signal to iterate on the
prompt before moving to Phase 2, not to push forward anyway.
