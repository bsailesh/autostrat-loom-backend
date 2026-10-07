"""
Product Sustainment Agent (Agent 4) — candidate work completeness, and the
merge with computed numbers.

Completeness is PER ITEM, as in Tech & Regulation: this agent has no
denominator, so a run surfacing no candidate work is legitimate. An item
that is not ready is dropped with a reason; the rest proceed.

The merge is where "the model judges, code computes" is enforced. For each
kept item, the date, quantity and applicability come from compute.py and the
qualified alternate from the customer's table -- whatever the model thought
they were is irrelevant, because it had no field to say it in.
"""
from __future__ import annotations

from datetime import date

from product_sustainment.compute import PartPosition, SustainmentResult, cascade
from product_sustainment.schemas import (
    ALTERNATE_BASES,
    CLASSIFICATIONS,
    CONFIDENCES,
    WORK_IMPLIED_KINDS,
    CandidateWorkItem,
    ModelCandidateWorkItem,
    ModelCandidateWorkOutput,
)
from product_sustainment.structure import SustainmentData

# A candidate alternate described as qualified or drop-in is the error that
# reaches a procurement decision. Caught in prose, since the schema already
# has no field for it.
_QUALIFIED_CLAIMS = (
    "drop-in", "drop in replacement", "is qualified", "are qualified", "fully qualified",
    "already qualified", "qualified replacement", "qualified alternate", "qualified second source",
    "direct replacement", "form-fit-function equivalent",
)

# Options, not decisions: a selection, a recommendation or a sizing.
_DECISION_MARKERS = (
    "should execute", "should buy", "should place", "should redesign", "should phase out",
    "we recommend", "is recommended", "recommend that", "the right answer", "highest priority",
    "top priority", "must be bought", "man-month", "person-month", "engineer-month", "estimated cost",
    "estimated effort",
)


def candidate_key(part_id: str) -> str:
    return f"PS-{part_id}"


def item_gaps(item: ModelCandidateWorkItem, known_parts: set[str], computed_date: str | None) -> list[str]:
    gaps: list[str] = []
    if not item.part_id.strip():
        gaps.append("part_id is empty")
    elif item.part_id not in known_parts:
        gaps.append(f"part_id {item.part_id!r} is not in any part master or risk flag -- applicability cannot be derived")
    if not item.driver.strip():
        gaps.append("driver is empty -- the named part, risk and source are the finding")
    if item.work_implied not in WORK_IMPLIED_KINDS:
        gaps.append(f"work_implied {item.work_implied!r} is not one of {', '.join(WORK_IMPLIED_KINDS)}")
    if item.classification not in CLASSIFICATIONS:
        gaps.append(f"classification {item.classification!r} is not one of {', '.join(CLASSIFICATIONS)}")
    if item.confidence not in CONFIDENCES:
        gaps.append(f"confidence {item.confidence!r} is not one of {', '.join(CONFIDENCES)}")
    if not item.source.strip():
        gaps.append("source is empty")
    if computed_date is None and not item.date_absent_reason.strip():
        gaps.append(
            "no runout within the horizon and no last-time-buy date, and no date_absent_reason -- an undated "
            "item is standing context, which must be an honest absence rather than an omission"
        )

    for n, alt in enumerate(item.candidate_alternates, start=1):
        if alt.basis not in ALTERNATE_BASES:
            gaps.append(f"candidate alternate {n} basis {alt.basis!r} is not one of {', '.join(ALTERNATE_BASES)}")
        if not alt.evidence.strip() or not alt.source.strip():
            gaps.append(f"candidate alternate {n} ({alt.part_number}) has no evidence or no source")
        if not alt.limits.strip():
            gaps.append(f"candidate alternate {n} ({alt.part_number}) does not state the limits of its evidence")
        claim = _found(f"{alt.evidence} {alt.limits}", _QUALIFIED_CLAIMS)
        if claim:
            gaps.append(
                f"candidate alternate {n} ({alt.part_number}) is described as {claim!r} -- an agent-found "
                "alternate is a candidate for qualification, never qualified"
            )

    claim = _found(f"{item.driver} {item.work_implied_description}", _QUALIFIED_CLAIMS)
    if claim and item.candidate_alternates:
        gaps.append(f"the item describes an alternate as {claim!r}; only the customer's table can say qualified")
    decision = _found(f"{item.driver} {item.work_implied_description}", _DECISION_MARKERS)
    if decision:
        gaps.append(f"the item selects, recommends or sizes ({decision!r}) -- this agent supplies options; Agent 5 decides")
    return gaps


_NEGATIONS = ("not ", "never ", "n't ", "no ", "nor ", "neither ")


def _found(text: str, markers: tuple[str, ...]) -> str | None:
    """The first marker present and NOT negated -- "has not been fully
    qualified" states a limit; "is fully qualified" makes a claim."""
    low = text.lower()
    for m in markers:
        start = low.find(m)
        while start != -1:
            window = low[max(0, start - 14):start]
            if not any(n in window for n in _NEGATIONS):
                return m
            start = low.find(m, start + 1)
    return None


def _iso_month_end(y: int, m: int) -> str:
    return date(y, m, 1).isoformat()[:7]


def computed_date(position: PartPosition | None, ltb: date | None) -> tuple[str | None, str]:
    """Runout month or last-time-buy close, whichever binds first."""
    runout = position.depletion.runout if position else None
    candidates: list[tuple[date, str, str]] = []
    if runout:
        candidates.append((date(runout[0], runout[1], 1), _iso_month_end(*runout), "runout"))
    if ltb:
        candidates.append((ltb, ltb.isoformat(), "window_closes"))
    if not candidates:
        return None, "none_established"
    first = min(candidates, key=lambda c: c[0])
    return first[1], first[2]


def _ltb_for(part: str, data: SustainmentData) -> date | None:
    dates = []
    for r in data.risks:
        if r.part_id == part and r.last_time_buy_date:
            try:
                dates.append(date.fromisoformat(r.last_time_buy_date))
            except ValueError:
                pass
    return min(dates) if dates else None


def merge_and_partition(
    output: ModelCandidateWorkOutput, result: SustainmentResult, data: SustainmentData
) -> tuple[list[CandidateWorkItem], list[tuple[str, list[str]]]]:
    """(kept, dropped). Kept items carry computed numbers, never model ones."""
    positions = {p.part_id: p for p in result.positions}
    insufficient = {p.part_id: p for p in result.insufficient}
    levels = {l.lru_id: "lru" for l in data.lrus} | {l.level1_id: "level1" for l in data.level1} \
        | {l.level2_id: "level2" for l in data.level2}
    known = set(levels) | {r.part_id for r in data.risks}
    qualified = {a.part_id: a.alternate_part_id for a in data.alternates if a.status == "qualified"}

    kept: list[CandidateWorkItem] = []
    dropped: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for index, item in enumerate(output.items):
        pos = positions.get(item.part_id)
        ltb = _ltb_for(item.part_id, data)
        work_date, basis = computed_date(pos, ltb)
        gaps = item_gaps(item, known, work_date)
        if item.part_id in seen:
            gaps.append(f"duplicate part_id {item.part_id!r} within this payload")
        if gaps:
            dropped.append((candidate_key(item.part_id) if item.part_id else f"<item {index + 1}>", gaps))
            continue
        seen.add(item.part_id)

        if pos is not None:
            lrus, level1 = list(pos.affected_lrus), list(pos.affected_level1)
            quantity = pos.quantity_required
            horizon = result.horizon_end
            quantity_basis = (
                f"Demand through the end of the supplied forecast horizon ({horizon}) minus available supply "
                f"of {pos.supply.total:,}. Not necessarily through end of life: if the product is supported "
                "beyond the horizon, this undersizes a last-time-buy."
            )
        else:
            level = levels.get(item.part_id, "")
            level1_t, lrus_t = cascade(item.part_id, level, data.lru_l1, data.l1_l2) if level else ((), ())
            lrus, level1 = list(lrus_t), list(level1_t)
            quantity = None
            reasons = insufficient[item.part_id].reasons if item.part_id in insufficient else ()
            quantity_basis = "Not computable: " + (" ".join(reasons) or "no position for this part.")

        kept.append(
            CandidateWorkItem(
                candidate_key=candidate_key(item.part_id),
                part_id=item.part_id,
                driver=item.driver,
                work_date=work_date,
                date_basis=basis,
                date_absent_reason=item.date_absent_reason if work_date is None else "",
                applicability={
                    "part": item.part_id,
                    "lrus": lrus,
                    "level1": level1,
                    "note": "" if lrus else "No LRU reached through the supplied matrices.",
                },
                quantity_required=quantity,
                quantity_basis=quantity_basis,
                qualified_alternate_part_id=qualified.get(item.part_id),
                candidate_alternates=[a.model_dump() for a in item.candidate_alternates],
                work_implied=item.work_implied,
                work_implied_description=item.work_implied_description,
                classification=item.classification,
                confidence=item.confidence,
                source=item.source,
                source_date=item.source_date,
            )
        )
    return kept, dropped
