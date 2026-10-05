"""
Strategy Synthesis Agent (Agent 5) — named sections in upstream report text.

An upstream agent can flag findings for a product leader under a section
headed exactly "## Findings for synthesis" (Voice of Customer does, in its
Report 1). Two things would otherwise lose them:

  1. Summarisation. An upstream pack over the size threshold is compressed
     by `summarize_upstream_agent`, whose instruction preserves facts and
     tags but not section structure -- the section's stand-alone paragraphs
     would be folded into the general summary.
  2. Pass 2 never sees upstream text. The decision brief is written from
     Pass 1's structured output and the computed results, and Pass1Output
     has no field for a finding that is not a candidate. VoC deliberately
     emits no candidates, so its findings could reach the brief only if
     Pass 1 happened to work one into a score's reason.

So the section is extracted verbatim, by heading, before any summarisation;
re-attached after it; and handed to the decision brief's Pass 2 call as its
own block. Agent-agnostic: any upstream agent using the heading gets the
same treatment, and this package imports nothing from the agent that wrote
it.
"""
from __future__ import annotations

import re

FINDINGS_FOR_SYNTHESIS_HEADING = "## Findings for synthesis"

_SECTION_START = re.compile(r"^##\s+Findings for synthesis\s*$", re.IGNORECASE | re.MULTILINE)
# The section ends at the next heading of level 1 or 2.
_NEXT_TOP_HEADING = re.compile(r"^#{1,2}\s", re.MULTILINE)


def extract_findings_for_synthesis(text: str) -> str:
    """The body of every "## Findings for synthesis" section in `text`,
    verbatim, joined in order; empty if there is none."""
    bodies: list[str] = []
    for m in _SECTION_START.finditer(text or ""):
        rest = text[m.end():]
        nxt = _NEXT_TOP_HEADING.search(rest)
        body = (rest[: nxt.start()] if nxt else rest).strip()
        if body:
            bodies.append(body)
    return "\n\n".join(bodies)


def reattach_findings(summary: str, findings: str) -> str:
    """A summarised pack with the section restored, verbatim, at the end."""
    if not findings:
        return summary
    return (
        f"{summary}\n\n{FINDINGS_FOR_SYNTHESIS_HEADING}\n\n"
        "[Carried verbatim from the source reports; not summarised.]\n\n"
        f"{findings}"
    )
