"""
Technology & Regulatory Intelligence Agent (Agent 3) — completeness
validation for candidate work.

Schema validity is not sufficiency. The lesson from Agent 5's Pass 1
(fff5b4a) is that a payload can satisfy its schema and still be
structurally wrong, so the structured call checks what the schema cannot
express. This module is that check, kept out of agent.py so it can be
tested without a client.

**Where this differs from Pass 1's check, and why.** Agent 5 validates at
the *set* level: zero project_scores against nine committed projects is a
missing answer, because the brief names exactly which projects must be
scored. This agent has no such denominator -- a run that genuinely surfaces
no candidate work is a legitimate outcome, and inventing items to fill a
quota is the failure mode, not the fix. So completeness here is per-item:
an item missing a required field is dropped with a reason, the rest of the
payload proceeds, and an empty list is accepted.

Per prompt_draft_v2 Part 3: "An item missing any of them is not ready to
emit -- state the finding without the candidate work rather than guessing."
Dropping is therefore the specified behaviour, not a lenient reading of it.
"""
from __future__ import annotations

from tech_regulation.schemas import (
    CLASSIFICATIONS,
    CONFIDENCES,
    DATE_BASES,
    PLATFORM_RELATIONSHIPS,
    WORK_IMPLIED_KINDS,
    CandidateWorkItem,
    CandidateWorkOutput,
)

# Anything matching these in a work description means the model has sized or
# ranked the work, which is Agent 5's job and not available to this agent.
# The schema has no field for it, so this catches it leaking into prose
# instead -- the one place it still can.
_SIZING_MARKERS = (
    "man-month", "man month", "person-month", "person month", "man-hour", "man hour",
    "engineer-month", "fte", "weeks of effort", "months of effort", "hours of effort",
    "highest priority", "top priority", "most urgent", "first priority",
    "estimated cost", "estimated effort", "estimated duration", "budget of",
)


def candidate_work_gaps(item: CandidateWorkItem) -> list[str]:
    """Why this one item is not ready to emit. Empty list means it is."""
    gaps: list[str] = []

    if not item.candidate_key.strip():
        gaps.append("candidate_key is empty")
    if not item.driver.strip():
        gaps.append("driver is empty -- the named regulation, revision or notice is the finding")
    if not item.work_implied.strip():
        gaps.append("work_implied is empty")
    elif item.work_implied not in WORK_IMPLIED_KINDS:
        gaps.append(
            f"work_implied {item.work_implied!r} is not one of {', '.join(WORK_IMPLIED_KINDS)}"
        )
    if item.work_implied == "other" and not item.work_implied_description.strip():
        gaps.append("work_implied 'other' requires work_implied_description to say what the activity is")

    applies_to = (
        item.applicability.categories
        + item.applicability.certification_bases
        + item.applicability.platforms
    )
    if not [a for a in applies_to if a.strip()]:
        gaps.append(
            "applicability names no category, certification basis or platform -- work that "
            "touches nothing in the envelope is not this customer's work"
        )

    # Dates are what make candidate work schedulable downstream, so a missing
    # one has to be an explicit, reasoned absence rather than a blank field.
    if item.work_date is None or not str(item.work_date).strip():
        if not item.date_absent_reason.strip():
            gaps.append(
                "work_date is absent with no date_absent_reason -- an undated item is standing "
                "context, which must be an honest absence rather than an omission"
            )
        if item.date_basis and item.date_basis != "none_established":
            gaps.append(
                f"work_date is absent but date_basis is {item.date_basis!r}; expected "
                "'none_established'"
            )
    elif item.date_basis not in DATE_BASES:
        gaps.append(f"date_basis {item.date_basis!r} is not one of {', '.join(DATE_BASES)}")
    elif item.date_basis == "none_established":
        gaps.append("date_basis is 'none_established' but work_date carries a date")

    if item.classification not in CLASSIFICATIONS:
        gaps.append(f"classification {item.classification!r} is not one of {', '.join(CLASSIFICATIONS)}")
    if item.confidence not in CONFIDENCES:
        gaps.append(f"confidence {item.confidence!r} is not one of {', '.join(CONFIDENCES)}")
    if not item.source.strip():
        gaps.append("source is empty")

    if item.platform_relationship is not None and item.platform_relationship not in PLATFORM_RELATIONSHIPS:
        gaps.append(
            f"platform_relationship {item.platform_relationship!r} is not one of "
            f"{', '.join(PLATFORM_RELATIONSHIPS)}"
        )

    sized = _sizing_language(item)
    if sized:
        gaps.append(
            f"work description sizes or ranks the work ({sized!r}) -- this agent names work; "
            "Agent 5 sizes and ranks it against capacity it can see"
        )

    return gaps


def _sizing_language(item: CandidateWorkItem) -> str | None:
    haystack = f"{item.work_implied_description} {item.driver} {item.applicability.note}".lower()
    for marker in _SIZING_MARKERS:
        if marker in haystack:
            return marker
    return None


def partition_candidate_work(
    output: CandidateWorkOutput,
) -> tuple[list[CandidateWorkItem], list[tuple[str, list[str]]]]:
    """Split a schema-valid payload into emittable items and dropped ones.

    Returns (kept, dropped) where dropped is [(candidate_key, gaps), ...].
    Duplicate keys within one payload are a drop rather than a silent
    overwrite: persistence is keyed by candidate_key, so two items claiming
    the same key would collapse into one row with whichever evidence landed
    last."""
    kept: list[CandidateWorkItem] = []
    dropped: list[tuple[str, list[str]]] = []
    seen: set[str] = set()

    for index, item in enumerate(output.items):
        gaps = candidate_work_gaps(item)
        key = item.candidate_key.strip()
        if key and key in seen:
            gaps.append(f"duplicate candidate_key {key!r} within this payload")
        if gaps:
            dropped.append((key or f"<item {index + 1} with no key>", gaps))
            continue
        seen.add(key)
        kept.append(item)

    return kept, dropped
