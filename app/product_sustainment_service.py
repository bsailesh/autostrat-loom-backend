"""
Product Sustainment (Agent 4) service layer.

Holds the boundary the other services hold: `product_sustainment/` never
sees a database session. Assembly of SustainmentData from the ps_* tables,
file ingest, evidence rendering from cursors, candidate-work persistence and
background run execution live here.

Referential integrity is enforced in BOTH directions, because a dangling
reference silently removes demand:
  * a matrix, demand or inventory upload naming an undeclared part is an
    error (product_sustainment/ingest.py);
  * replacing a part master that would orphan an existing matrix edge,
    demand row or inventory row is refused, naming what still refers to it.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import BinaryIO, Iterator

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AgentReport,
    AgentRun,
    PsCandidateWork,
    PsConfiguration,
    PsDemand,
    PsDirectDemand,
    PsEvidenceFile,
    PsEvidenceItem,
    PsFile,
    PsFleet,
    PsInventory,
    PsKnowledge,
    PsLeadTime,
    PsLevel1,
    PsLevel1Level2,
    PsLevel2,
    PsLru,
    PsLruLevel1,
    PsMaintenance,
    PsPipeline,
    PsQualifiedAlternate,
    PsRiskFlag,
    PsRunMeta,
    Tenant,
    TrSupplier,
)
from app.tenant_scope import scoped_query

from product_sustainment import ProductSustainmentAgent
from product_sustainment import evidence as evidence_render
from product_sustainment import evidence_ingest, ingest, results
from product_sustainment.compute import InventoryRow, Pipeline
from product_sustainment.config import Settings as AgentSettings
from product_sustainment.ingest import DeclaredParts, IngestIssue
from product_sustainment.schemas import CandidateWorkItem
from product_sustainment.structure import (
    KnowledgeItem,
    Level1Info,
    Level2Info,
    LruInfo,
    QualifiedAlternate,
    RiskRecord,
    Supplier,
    SustainmentData,
)

logger = logging.getLogger(__name__)

AGENT_TYPE = "product-sustainment"

# Background tasks open their own session. Pinned per test in a fixture,
# never at import (the trap logged in tests/conftest.py).
SessionFactory = SessionLocal

_BATCH = 500


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------

MASTER_MODELS = {"lrus": (PsLru, "lru_id"), "level1": (PsLevel1, "level1_id"), "level2": (PsLevel2, "level2_id")}


def declared_parts(db: Session, tenant: Tenant) -> DeclaredParts:
    return DeclaredParts(
        lrus=frozenset(r.lru_id for r in scoped_query(db, PsLru, tenant)),
        level1=frozenset(r.level1_id for r in scoped_query(db, PsLevel1, tenant)),
        level2=frozenset(r.level2_id for r in scoped_query(db, PsLevel2, tenant)),
    )


def references_to(db: Session, tenant: Tenant, which: str, ids: set[str]) -> list[str]:
    """What still refers to each id about to be removed from a master."""
    if not ids:
        return []
    refs: list[str] = []

    def add(rows, label):
        for r in rows:
            refs.append(label(r))

    if which == "lrus":
        add(scoped_query(db, PsLruLevel1, tenant).filter(PsLruLevel1.lru_id.in_(ids)),
            lambda r: f"{r.lru_id} in the LRU -> Level 1 matrix")
        add(scoped_query(db, PsDemand, tenant).filter(PsDemand.lru_id.in_(ids)),
            lambda r: f"{r.lru_id} in demand ({r.year})")
    elif which == "level1":
        add(scoped_query(db, PsLruLevel1, tenant).filter(PsLruLevel1.level1_id.in_(ids)),
            lambda r: f"{r.level1_id} in the LRU -> Level 1 matrix")
        add(scoped_query(db, PsLevel1Level2, tenant).filter(PsLevel1Level2.level1_id.in_(ids)),
            lambda r: f"{r.level1_id} in the Level 1 -> Level 2 matrix")
    else:
        add(scoped_query(db, PsLevel1Level2, tenant).filter(PsLevel1Level2.level2_id.in_(ids)),
            lambda r: f"{r.level2_id} in the Level 1 -> Level 2 matrix")
    level = {"lrus": "lru", "level1": "level1", "level2": "level2"}[which]
    add(scoped_query(db, PsInventory, tenant).filter(PsInventory.part_level == level, PsInventory.part_id.in_(ids)),
        lambda r: f"{r.part_id} in inventory")
    return sorted(set(refs))


class ReferentialError(Exception):
    pass


def replace_master(db: Session, tenant: Tenant, which: str, rows: list[dict]) -> list:
    model, key = MASTER_MODELS[which]
    existing = {getattr(r, key) for r in scoped_query(db, model, tenant)}
    removed = existing - {r[key] for r in rows}
    refs = references_to(db, tenant, which, removed)
    if refs:
        raise ReferentialError(
            "These ids are still referenced, and removing them would silently drop demand or stock: "
            + "; ".join(refs[:20]) + (f" (and {len(refs) - 20} more)" if len(refs) > 20 else "")
            + ". Re-upload the referring files first."
        )
    scoped_query(db, model, tenant).delete(synchronize_session=False)
    for r in rows:
        db.add(model(tenant_id=tenant.id, **r))
    db.commit()
    return scoped_query(db, model, tenant).order_by(getattr(model, key).asc()).all()


# ---------------------------------------------------------------------------
# Structured file ingest
# ---------------------------------------------------------------------------


def _record_file(db, tenant, file_type, filename, as_of, row_count, issues: list[IngestIssue], columns) -> PsFile:
    has_errors = any(i.severity == "error" for i in issues)
    row = scoped_query(db, PsFile, tenant).filter(PsFile.file_type == file_type).first()
    if row is None:
        row = PsFile(tenant_id=tenant.id, file_type=file_type)
        db.add(row)
    row.filename = filename
    row.as_of = as_of
    row.row_count = 0 if has_errors else row_count
    row.validation_status = "invalid" if has_errors else ("valid_with_warnings" if issues else "valid")
    row.issues = [i.as_dict() for i in issues]
    row.columns = columns
    row.created_at = datetime.now(timezone.utc)
    return row


def ingest_mapping(db: Session, tenant: Tenant, which: str, text: str, filename: str) -> tuple[PsFile, list[dict]]:
    """Any error blocks the whole file -- nothing is written and the previous
    edges stay. On success the mapping is replaced wholesale."""
    parts = declared_parts(db, tenant)
    edges, issues = ingest.parse_mapping(text, which, parts)
    has_errors = any(i.severity == "error" for i in issues)
    model = PsLruLevel1 if which == "lru-level1" else PsLevel1Level2
    if not has_errors:
        scoped_query(db, model, tenant).delete(synchronize_session=False)
        for p, c, q in edges:
            if which == "lru-level1":
                db.add(PsLruLevel1(tenant_id=tenant.id, lru_id=p, level1_id=c, quantity_per_unit=q))
            else:
                db.add(PsLevel1Level2(tenant_id=tenant.id, level1_id=p, level2_id=c, quantity_per_unit=q))
        db.flush()
        lru_l1 = [(r.lru_id, r.level1_id, r.quantity_per_unit) for r in scoped_query(db, PsLruLevel1, tenant)]
        l1_l2 = [(r.level1_id, r.level2_id, r.quantity_per_unit) for r in scoped_query(db, PsLevel1Level2, tenant)]
        issues = issues + ingest.unlinked_part_warnings(parts, lru_l1, l1_l2)
    header = text.splitlines()[0].split(",") if text.strip() else []
    rec = _record_file(db, tenant, f"matrix:{which}", filename, "", len(edges), issues, [h.strip() for h in header])
    db.commit()
    db.refresh(rec)
    return rec, [i.as_dict() for i in issues]


DATA_MODELS = {
    "inventory": PsInventory, "pipeline": PsPipeline, "lead-times": PsLeadTime, "risk": PsRiskFlag,
    "alternates": PsQualifiedAlternate, "fleet": PsFleet, "maintenance": PsMaintenance,
    "configuration": PsConfiguration,
}


def ingest_data_file(db: Session, tenant: Tenant, file_type: str, text: str, filename: str, as_of: str) -> PsFile:
    parts = declared_parts(db, tenant)
    if file_type == "demand":
        parsed, issues = ingest.parse_demand(text, parts)
        rows = [{"lru_id": l, "year": y, "quantity": q} for l, y, q in parsed]
        model = PsDemand
    elif file_type == "direct-demand":
        parsed, issues = ingest.parse_direct_demand(text, parts)
        rows = [{"part_id": p, "part_level": lv, "year": y, "quantity": q} for p, lv, y, q in parsed]
        model = PsDirectDemand
    else:
        rows, issues = ingest.parse_records(text, file_type, parts)
        model = DATA_MODELS[file_type]
        cols = set(model.__table__.columns.keys())
        rows = [{k: v for k, v in r.items() if k in cols} for r in rows]
        if file_type in ("inventory", "pipeline") and as_of:
            rows = [{**r, "as_of": r.get("as_of") or as_of} for r in rows]
    if not any(i.severity == "error" for i in issues):
        scoped_query(db, model, tenant).delete(synchronize_session=False)
        for start in range(0, len(rows), _BATCH):
            chunk = rows[start:start + _BATCH]
            if chunk:
                db.execute(insert(model), [{"id": str(uuid.uuid4()), "tenant_id": tenant.id, **r} for r in chunk])
    header = text.splitlines()[0].split(",") if text.strip() else []
    rec = _record_file(db, tenant, file_type, filename, as_of, len(rows), issues, [h.strip() for h in header])
    db.commit()
    db.refresh(rec)
    return rec


def structure_summary(db: Session, tenant: Tenant) -> dict:
    """The derived picture after an upload. `parts_without_demand_path` --
    parts no LRU reaches through the matrices and with no direct demand --
    is the number that catches a bad matrix."""
    parts = declared_parts(db, tenant)
    lru_l1 = [(r.lru_id, r.level1_id) for r in scoped_query(db, PsLruLevel1, tenant)]
    l1_l2 = [(r.level1_id, r.level2_id) for r in scoped_query(db, PsLevel1Level2, tenant)]
    direct = {(r.part_level, r.part_id) for r in scoped_query(db, PsDirectDemand, tenant)}
    l1_reached = {j for _, j in lru_l1} | {p for lv, p in direct if lv == "level1"}
    l2_reached = {k for j, k in l1_l2 if j in l1_reached} | {p for lv, p in direct if lv == "level2"}
    no_path = sorted(parts.level1 - l1_reached) + sorted(parts.level2 - l2_reached)
    return {
        "lrus": len(parts.lrus),
        "level1": len(parts.level1),
        "level2": len(parts.level2),
        "lru_level1_edges": len(lru_l1),
        "level1_level2_edges": len(l1_l2),
        "parts_without_demand_path": no_path,
    }


def template(db: Session, tenant: Tenant, which: str, today: date) -> str:
    parts = declared_parts(db, tenant)
    if which in ingest.MATRIX_KINDS:
        return ingest.mapping_template(which, parts)
    if which == "demand":
        return ingest.demand_template(parts, today.year)
    if which == "direct-demand":
        return "part_id,part_level," + ",".join(str(today.year + n) for n in range(6)) + "\n"
    return ingest.record_template(which)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def assemble_data(db: Session, tenant: Tenant) -> SustainmentData:
    q = lambda model: scoped_query(db, model, tenant)
    lru_l1: dict[str, dict[str, int]] = defaultdict(dict)
    for r in q(PsLruLevel1):
        lru_l1[r.lru_id][r.level1_id] = r.quantity_per_unit
    l1_l2: dict[str, dict[str, int]] = defaultdict(dict)
    for r in q(PsLevel1Level2):
        l1_l2[r.level1_id][r.level2_id] = r.quantity_per_unit
    demand: dict[str, dict[int, int]] = defaultdict(dict)
    for r in q(PsDemand):
        demand[r.lru_id][r.year] = r.quantity
    direct: dict[tuple[str, str], dict[int, int]] = defaultdict(dict)
    for r in q(PsDirectDemand):
        direct[(r.part_level, r.part_id)][r.year] = r.quantity
    inventory_rows = q(PsInventory).all()
    files = {f.file_type for f in q(PsFile).filter(PsFile.validation_status != "invalid")}

    return SustainmentData(
        lrus=[LruInfo(r.lru_id, r.lru_name, r.product_line, r.program, r.status) for r in q(PsLru).order_by(PsLru.lru_id)],
        level1=[Level1Info(r.level1_id, r.level1_name, r.description) for r in q(PsLevel1).order_by(PsLevel1.level1_id)],
        level2=[Level2Info(r.level2_id, r.level2_name, r.description, r.manufacturer, r.manufacturer_part_number)
                for r in q(PsLevel2).order_by(PsLevel2.level2_id)],
        lru_l1=dict(lru_l1),
        l1_l2=dict(l1_l2),
        lru_demand=dict(demand),
        direct_demand=dict(direct),
        inventory=[InventoryRow(r.part_id, r.part_level, r.location, r.form, r.quantity) for r in inventory_rows],
        inventory_as_of=[r.as_of for r in inventory_rows if r.as_of],
        pipeline={r.part_id: Pipeline(r.open_po_qty, r.supplier_qty, r.supplier_on_order_qty, r.supplier_wip_qty)
                  for r in q(PsPipeline)},
        lead_time_days={r.part_id: r.lead_time_days for r in q(PsLeadTime)},
        risks=[RiskRecord(r.part_id, r.risk_type, r.risk_detail, r.source, r.source_date, r.lifecycle_status,
                          r.last_time_buy_date, r.last_delivery_date) for r in q(PsRiskFlag)],
        alternates=[QualifiedAlternate(r.part_id, r.alternate_part_id, r.status, r.qualified_date)
                    for r in q(PsQualifiedAlternate)],
        knowledge=[KnowledgeItem(r.capability, r.components_affected, r.people_count, r.documentation_status)
                   for r in q(PsKnowledge)],
        suppliers=[Supplier(r.supplier, r.what_they_supply, r.criticality) for r in q(TrSupplier)],
        evidence=[_evidence_meta(r) for r in q(PsEvidenceFile).filter(PsEvidenceFile.ingest_status == "ingested")
                  .order_by(PsEvidenceFile.created_at)],
        fleet_count=q(PsFleet).count(),
        maintenance_count=q(PsMaintenance).count(),
        configuration_count=q(PsConfiguration).count(),
        demand_supplied="demand" in files or bool(demand),
        inventory_supplied="inventory" in files or bool(inventory_rows),
        pipeline_supplied="pipeline" in files,
    )


def _evidence_meta(r: PsEvidenceFile) -> evidence_render.EvidenceFile:
    return evidence_render.EvidenceFile(
        file_id=r.id, file_type=r.file_type, file_format=r.file_format, filename=r.filename,
        as_of=r.as_of or "", period_start=r.period_start or "", period_end=r.period_end or "",
        is_sample=bool(r.is_sample), sample_description=r.sample_description or "",
        row_unit=r.row_unit or "", columns=tuple(r.columns or ()), column_roles=dict(r.column_roles or {}),
        row_count=r.row_count, page_count=r.page_count, char_count=r.char_count or 0,
    )


# ---------------------------------------------------------------------------
# Free-text evidence -- the Voice of Customer pattern
# ---------------------------------------------------------------------------


def ingest_evidence(db: Session, tenant: Tenant, *, fileobj: BinaryIO, filename: str, content_type: str,
                    size_bytes: int, metadata: dict) -> PsEvidenceFile:
    if size_bytes > evidence_ingest.MAX_UPLOAD_BYTES:
        raise evidence_ingest.IngestRejected(evidence_ingest.upload_too_large_message(size_bytes))
    fmt = evidence_ingest.detect_format(filename)
    row = PsEvidenceFile(tenant_id=tenant.id, file_format=fmt, filename=filename, content_type=content_type or "",
                         size_bytes=size_bytes, ingest_status="pending", **metadata)
    if fmt == "pdf":
        row.page_count = evidence_ingest.pdf_page_count_with_text(fileobj)
    if fmt == "csv":
        row.columns = evidence_ingest.read_csv_header(fileobj)
    db.add(row)
    db.flush()
    totals = {"items": 0, "chars": 0}

    def items() -> Iterator[dict]:
        if fmt == "csv":
            for seq, cells in evidence_ingest.iter_csv_rows(fileobj):
                totals["items"] += 1
                totals["chars"] += evidence_ingest.cells_char_count(cells)
                yield {"seq": seq, "cells": cells, "text": ""}
        else:
            src = evidence_ingest.iter_pdf_pages(fileobj) if fmt == "pdf" else evidence_ingest.iter_text_sections(fileobj)
            for seq, text in src:
                totals["items"] += 1
                totals["chars"] += len(text)
                yield {"seq": seq, "cells": None, "text": text}

    batch: list[dict] = []
    for item in items():
        batch.append({"id": str(uuid.uuid4()), "tenant_id": tenant.id, "file_id": row.id, **item})
        if len(batch) >= _BATCH:
            db.execute(insert(PsEvidenceItem), batch)
            batch = []
    if batch:
        db.execute(insert(PsEvidenceItem), batch)
    if totals["chars"] == 0:
        db.rollback()
        raise evidence_ingest.IngestRejected("This file has no content.")
    if fmt == "csv":
        row.row_count = totals["items"]
    row.char_count = totals["chars"]
    row.ingest_status = "ingested"
    db.commit()
    db.refresh(row)
    return row


def delete_evidence(db: Session, tenant: Tenant, row: PsEvidenceFile) -> None:
    scoped_query(db, PsEvidenceItem, tenant).filter(PsEvidenceItem.file_id == row.id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()


def _cursor(db, tenant, file_id):
    return (scoped_query(db, PsEvidenceItem, tenant).filter(PsEvidenceItem.file_id == file_id)
            .order_by(PsEvidenceItem.seq).yield_per(_BATCH))


def render_evidence(db: Session, tenant: Tenant, data: SustainmentData) -> str:
    budgets = evidence_render.allocate_budget(data.evidence)
    rendered = []
    for meta in data.evidence:
        budget = budgets.get(meta.file_id, evidence_render.PER_FILE_FLOOR_CHARS)
        if meta.file_format == "csv":
            rendered.append(evidence_render.render_csv(meta, ((r.seq, r.cells or {}) for r in _cursor(db, tenant, meta.file_id)), budget))
        else:
            count = scoped_query(db, PsEvidenceItem, tenant).filter(PsEvidenceItem.file_id == meta.file_id).count()
            rendered.append(evidence_render.render_document(meta, ((r.seq, r.text or "") for r in _cursor(db, tenant, meta.file_id)), count, budget))
    return evidence_render.render_evidence_text(rendered) if rendered else ""


# Fleet, maintenance and configuration are rendered with the same rule as
# evidence -- counts over every row, a stated sample of rows -- by treating
# each table as a CSV with mapped roles.
_OPERATIONAL = [
    ("fleet", PsFleet, ("unit_id", "lru_id", "in_service_date", "utilisation", "environment", "operator_segment"),
     {"lru": "lru_id", "category": "environment"}),
    ("maintenance", PsMaintenance, ("unit_id", "lru_id", "event_date", "event_type", "time_in_service", "downtime"),
     {"lru": "lru_id", "date": "event_date", "failure_mode": "event_type"}),
    ("configuration", PsConfiguration, ("unit_id", "lru_id", "as_maintained_config", "as_designed_baseline"),
     {"lru": "lru_id"}),
]
OPERATIONAL_BUDGET_CHARS = 20_000


def render_operational(db: Session, tenant: Tenant) -> str:
    parts = []
    for name, model, cols, roles in _OPERATIONAL:
        count = scoped_query(db, model, tenant).count()
        if not count:
            continue
        meta = evidence_render.EvidenceFile(
            file_id=f"{tenant.id}:{name}", file_type=name, file_format="csv", filename=f"{name} (structured upload)",
            columns=cols, column_roles=roles, row_count=count, row_unit={"fleet": "unit", "maintenance": "event",
                                                                         "configuration": "unit"}[name],
        )
        rows = ((n, {c: getattr(r, c) or "" for c in cols})
                for n, r in enumerate(scoped_query(db, model, tenant).order_by(model.unit_id).yield_per(_BATCH), start=1))
        parts.append(evidence_render.render_csv(meta, rows, OPERATIONAL_BUDGET_CHARS).text)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Candidate work persistence
# ---------------------------------------------------------------------------

_EVIDENCE_FIELDS = (
    "part_id", "driver", "work_date", "date_basis", "date_absent_reason", "applicability", "quantity_required",
    "quantity_basis", "qualified_alternate_part_id", "candidate_alternates", "work_implied",
    "work_implied_description", "classification", "confidence", "source", "source_date",
)


def persist_candidate_work(db: Session, tenant: Tenant, run: AgentRun, items: list[CandidateWorkItem]) -> None:
    """Additive, keyed by candidate_key. A re-run refreshes evidence fields
    but never status or dismissal_reason: a dismissed item stays dismissed."""
    existing = {r.candidate_key: r for r in scoped_query(db, PsCandidateWork, tenant)}
    for item in items:
        values = {f: getattr(item, f) for f in _EVIDENCE_FIELDS}
        row = existing.get(item.candidate_key)
        if row is None:
            db.add(PsCandidateWork(tenant_id=tenant.id, candidate_key=item.candidate_key, status="new",
                                   first_seen_run_id=run.id, last_seen_run_id=run.id, **values))
            continue
        for k, v in values.items():
            setattr(row, k, v)
        row.last_seen_run_id = run.id


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------


def execute_run(*, run_id: str, model: str | None, max_searches: int | None, research_rounds: int | None) -> None:
    db = SessionFactory()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:
            return
        tenant = db.get(Tenant, run.tenant_id)
        run.status = "running"
        db.commit()
        try:
            agent = ProductSustainmentAgent(AgentSettings.load(model_override=model))
            data = assemble_data(db, tenant)
            kwargs: dict = {}
            if max_searches is not None:
                kwargs["max_searches"] = max_searches
            if research_rounds is not None:
                kwargs["research_rounds"] = research_rounds
            result = agent.run(
                data,
                today=datetime.now(timezone.utc).date(),
                evidence_text=render_evidence(db, tenant, data),
                operational_text=render_operational(db, tenant),
                **kwargs,
            )
            for r in result.reports:
                db.add(AgentReport(tenant_id=run.tenant_id, run_id=run.id, report_number=r.report_number,
                                   title=r.title, content=r.content, confidence_summary=r.confidence_summary))
            persist_candidate_work(db, tenant, run, result.candidate_work)
            db.add(PsRunMeta(
                tenant_id=run.tenant_id, run_id=run.id, tier=result.operating_tier,
                notes=list(result.computation.notes),
                horizon_years=results.years_of(result.computation),
                runout_rows=results.runout_rows(result.computation, data),
                insufficient_rows=[{"part_id": p.part_id, "level": p.level, "reasons": list(p.reasons),
                                    "affected_lrus": list(p.affected_lrus)} for p in result.computation.insufficient],
                candidate_work_dropped=[{"candidate_key": d.candidate_key, "gaps": d.gaps}
                                        for d in result.candidate_work_dropped],
            ))
            if result.candidate_work_dropped:
                logger.warning("Product Sustainment run %s dropped %d candidate work item(s)",
                               run_id, len(result.candidate_work_dropped))
            run.status = "succeeded"
            run.error = None
            db.commit()
        except Exception as exc:  # noqa: BLE001 -- any failure must land on the run row
            logger.exception("Product Sustainment run %s failed", run_id)
            db.rollback()
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"[:2000]
                db.commit()
    finally:
        db.close()
