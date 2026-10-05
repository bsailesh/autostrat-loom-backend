"""
Voice of Customer (Agent 1) service layer.

The boundary this file holds, as app/tech_regulation_service.py does for
Agent 3: `voice_of_customer/` never sees a database session. Context
assembly from the voc_* tables, evidence ingest into voc_evidence_items,
rendering evidence from database cursors, and background run execution
live here; the tier, degradation, sampling and attribution logic live in
the package where they can be tested without a database.

Memory is the constraint everything here is shaped by -- the production
instance has 414MB of RAM and ticket exports can be large:

  * ingest streams the upload (already spooled to disk by Starlette) through
    a parser that yields one row or page at a time, and writes in batches
    with Core inserts, so no ORM identity map grows with the file;
  * a run reads each file through a `yield_per` cursor, one file at a time,
    and evidence.py keeps only bounded counters and sample pools.
"""
from __future__ import annotations

import logging
import uuid
from typing import BinaryIO, Iterator

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AgentReport,
    AgentRun,
    Tenant,
    TrProductCategory,
    VocChannel,
    VocConfig,
    VocCustomer,
    VocEvidenceFile,
    VocEvidenceItem,
    VocKnownPainPoint,
    VocProductCategory,
    VocRunMeta,
    VocSegment,
)
from app.tenant_scope import scoped_query

from voice_of_customer import VoiceOfCustomerAgent
from voice_of_customer import evidence as evidence_render
from voice_of_customer import ingest
from voice_of_customer.attribution import NameEntry, build_name_list
from voice_of_customer.config import Settings as AgentSettings
from voice_of_customer.context import (
    DEFAULT_ATTRIBUTION_POLICY,
    Channel,
    ContextItem,
    Customer,
    CustomerContext,
    EvidenceFile,
    KnownPainPoint,
    ProductCategory,
    Segment,
    TIER_LABELS,
    context_items,
    operating_tier,
    run_label,
)

logger = logging.getLogger(__name__)

AGENT_TYPE = "voice-of-customer"

# The background task can't use the request-scoped session, so it opens its
# own. Module-level so tests can point it at their database -- pinned per
# test in a fixture, never at import (see the KNOWN GAP in tests/conftest.py).
SessionFactory = SessionLocal

_INSERT_BATCH = 500


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def merged_categories(db: Session, tenant: Tenant) -> list[ProductCategory]:
    """Tech & Regulation's categories read through, plus VoC's own
    additions. Where a key exists in both, the read-through wins -- the
    customer is never asked to maintain the same category twice."""
    tr = [
        ProductCategory(r.category_key, r.category_name, r.description, source="tech-regulation")
        for r in scoped_query(db, TrProductCategory, tenant).order_by(TrProductCategory.category_key.asc())
    ]
    tr_keys = {c.category_key for c in tr}
    local = [
        ProductCategory(r.category_key, r.category_name, r.description, source="voice-of-customer")
        for r in scoped_query(db, VocProductCategory, tenant).order_by(VocProductCategory.category_key.asc())
        if r.category_key not in tr_keys
    ]
    return tr + local


def attribution_policy(db: Session, tenant: Tenant) -> str:
    row = scoped_query(db, VocConfig, tenant).first()
    return row.attribution_policy if row else DEFAULT_ATTRIBUTION_POLICY


def _evidence_meta(row: VocEvidenceFile) -> EvidenceFile:
    return EvidenceFile(
        file_id=row.id,
        file_type=row.file_type,
        file_format=row.file_format,
        filename=row.filename,
        as_of=row.as_of or "",
        period_start=row.period_start or "",
        period_end=row.period_end or "",
        is_sample=bool(row.is_sample),
        sample_description=row.sample_description or "",
        segment_coverage=tuple(row.segment_coverage or ()),
        row_unit=row.row_unit or "",
        columns=tuple(row.columns or ()),
        column_roles=dict(row.column_roles or {}),
        row_count=row.row_count,
        page_count=row.page_count,
        char_count=row.char_count or 0,
    )


def assemble_context(db: Session, tenant: Tenant) -> CustomerContext:
    def rows(model, order_by):
        return scoped_query(db, model, tenant).order_by(order_by).all()

    return CustomerContext(
        segments=[
            Segment(r.segment_key, r.segment_name, r.description, r.approximate_count)
            for r in rows(VocSegment, VocSegment.segment_key.asc())
        ],
        channels=[
            Channel(r.channel, r.direction, r.note) for r in rows(VocChannel, VocChannel.channel.asc())
        ],
        customers=[
            Customer(r.customer_name, r.segment_key, r.products, r.relationship_status)
            for r in rows(VocCustomer, VocCustomer.customer_name.asc())
        ],
        known_pain_points=[
            KnownPainPoint(r.pain_point, r.segment_key, r.category_key, r.their_assessment)
            for r in rows(VocKnownPainPoint, VocKnownPainPoint.created_at.asc())
        ],
        categories=merged_categories(db, tenant),
        attribution_policy=attribution_policy(db, tenant),
        evidence=[
            _evidence_meta(r)
            for r in scoped_query(db, VocEvidenceFile, tenant)
            .filter(VocEvidenceFile.ingest_status == "ingested")
            .order_by(VocEvidenceFile.created_at.asc())
        ],
    )


def compute_context_state(db: Session, tenant: Tenant) -> tuple[CustomerContext, str, list[ContextItem]]:
    """Returns context_items() unchanged: consequence text is already empty
    for every item that is set, and must not be re-attached here (b4f3282)."""
    context = assemble_context(db, tenant)
    return context, operating_tier(context), context_items(context)


def compose_subject(context: CustomerContext) -> str:
    """Frozen at run time for the export cover and filename. Leads with the
    run label, so a Tier 2 run reads as an external customer-context
    analysis everywhere it is listed."""
    tier = operating_tier(context)
    segments = ", ".join(s.segment_name for s in context.segments[:3]) or "no segments"
    if len(context.segments) > 3:
        segments += f" (+{len(context.segments) - 3} more)"
    return f"{run_label(tier)} — {segments} — {len(context.evidence)} evidence file(s) — {TIER_LABELS[tier]}"


# ---------------------------------------------------------------------------
# Evidence ingest
# ---------------------------------------------------------------------------


def _bulk_insert_items(db: Session, tenant: Tenant, file_id: str, items: Iterator[dict]) -> None:
    batch: list[dict] = []
    for item in items:
        batch.append({"id": str(uuid.uuid4()), "tenant_id": tenant.id, "file_id": file_id, **item})
        if len(batch) >= _INSERT_BATCH:
            db.execute(insert(VocEvidenceItem), batch)
            batch = []
    if batch:
        db.execute(insert(VocEvidenceItem), batch)


def ingest_file(
    db: Session,
    tenant: Tenant,
    *,
    fileobj: BinaryIO,
    filename: str,
    content_type: str,
    size_bytes: int,
    metadata: dict,
) -> VocEvidenceFile:
    """Parse and store one upload. Raises ingest.IngestRejected, with the
    message the customer sees, for anything that will not be stored --
    nothing is written in that case."""
    if size_bytes > ingest.MAX_UPLOAD_BYTES:
        raise ingest.IngestRejected(ingest.upload_too_large_message(size_bytes))
    fmt = ingest.detect_format(filename)

    issues: list[dict] = []
    row = VocEvidenceFile(
        tenant_id=tenant.id,
        file_format=fmt,
        filename=filename,
        content_type=content_type or "",
        size_bytes=size_bytes,
        ingest_status="pending",
        **metadata,
    )

    if fmt == "pdf":
        row.page_count = ingest.pdf_page_count_with_text(fileobj)  # rejects scanned PDFs

    if fmt == "csv":
        row.columns = ingest.read_csv_header(fileobj)
        unknown = sorted(c for c in (row.column_roles or {}).values() if c and c not in row.columns)
        if unknown:
            raise ingest.IngestRejected(
                f"Column role mapping names column(s) not in this file: {', '.join(unknown)}. "
                f"Detected columns: {', '.join(row.columns)}."
            )

    db.add(row)
    db.flush()  # assigns row.id

    totals = {"items": 0, "chars": 0, "empty_pages": 0, "extra_cells": 0}

    def items() -> Iterator[dict]:
        if fmt == "csv":
            for seq, cells in ingest.iter_csv_rows(fileobj):
                totals["items"] += 1
                totals["chars"] += ingest.cells_char_count(cells)
                if "_extra" in cells:
                    totals["extra_cells"] += 1
                yield {"seq": seq, "cells": cells, "text": ""}
        else:
            source = ingest.iter_pdf_pages(fileobj) if fmt == "pdf" else ingest.iter_text_sections(fileobj)
            for seq, text in source:
                totals["items"] += 1
                totals["chars"] += len(text)
                if not text:
                    totals["empty_pages"] += 1
                yield {"seq": seq, "cells": None, "text": text}

    try:
        _bulk_insert_items(db, tenant, row.id, items())
    except Exception:
        db.rollback()
        raise

    if fmt == "csv":
        row.row_count = totals["items"]
        if totals["items"] == 0:
            db.rollback()
            raise ingest.IngestRejected("This CSV has a header row but no data rows.")
        if not row.row_unit:
            issues.append({
                "severity": "warning",
                "message": "What one row represents (ticket, claim, comment) was not stated. Counts "
                           "from this file will be reported with that caveat until it is set.",
            })
        if not row.column_roles:
            issues.append({
                "severity": "warning",
                "message": "No columns are mapped to roles. The file is used as-is, but the only exact "
                           "count is the row total; map a category or severity column to get counts.",
            })
        if totals["extra_cells"]:
            issues.append({
                "severity": "warning",
                "message": f"{totals['extra_cells']} row(s) had more cells than the header; the extra "
                           "cells were kept, not dropped.",
            })
    elif fmt == "text" and totals["chars"] == 0:
        db.rollback()
        raise ingest.IngestRejected("This text file is empty.")
    elif fmt == "pdf" and totals["empty_pages"]:
        issues.append({
            "severity": "warning",
            "message": f"{totals['empty_pages']} of {row.page_count} page(s) had no extractable text "
                       "(likely scanned images) and contribute nothing.",
        })

    row.char_count = totals["chars"]
    row.issues = issues
    row.ingest_status = "ingested"
    db.commit()
    db.refresh(row)
    return row


def delete_evidence_file(db: Session, tenant: Tenant, row: VocEvidenceFile) -> None:
    scoped_query(db, VocEvidenceItem, tenant).filter(VocEvidenceItem.file_id == row.id).delete(
        synchronize_session=False
    )
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Evidence rendering for a run
# ---------------------------------------------------------------------------


def _item_cursor(db: Session, tenant: Tenant, file_id: str):
    return (
        scoped_query(db, VocEvidenceItem, tenant)
        .filter(VocEvidenceItem.file_id == file_id)
        .order_by(VocEvidenceItem.seq.asc())
        .yield_per(_INSERT_BATCH)
    )


def render_evidence(
    db: Session, tenant: Tenant, context: CustomerContext
) -> tuple[str, list[str], set[str]]:
    """(evidence text for the prompt, one sampling note per file, customer
    names found in CSV columns mapped as `customer`). One file at a time,
    each through its own cursor."""
    budgets = evidence_render.allocate_budget(context.evidence)
    rendered = []
    customer_values: set[str] = set()
    for meta in context.evidence:
        budget = budgets.get(meta.file_id, evidence_render.PER_FILE_FLOOR_CHARS)
        if meta.file_format == "csv":
            rows = ((r.seq, r.cells or {}) for r in _item_cursor(db, tenant, meta.file_id))
            out = evidence_render.render_csv(meta, rows, budget)
            customer_values |= set(out.customer_values)
        else:
            count = (
                scoped_query(db, VocEvidenceItem, tenant)
                .filter(VocEvidenceItem.file_id == meta.file_id)
                .count()
            )
            items = ((r.seq, r.text or "") for r in _item_cursor(db, tenant, meta.file_id))
            out = evidence_render.render_document(meta, items, count, budget)
        rendered.append(out)
    return (
        evidence_render.render_evidence_text(rendered),
        [r.sampling_note for r in rendered],
        customer_values,
    )


def name_entries(context: CustomerContext, csv_customer_values: set[str]) -> list[NameEntry]:
    return build_name_list(context.customers, context.segments, sorted(csv_customer_values))


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------


def execute_run(
    *,
    run_id: str,
    model: str | None,
    max_searches: int | None,
    research_rounds: int | None,
) -> None:
    db = SessionFactory()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:  # deleted between scheduling and execution
            return
        tenant = db.get(Tenant, run.tenant_id)
        run.status = "running"
        db.commit()

        try:
            settings = AgentSettings.load(model_override=model)
            agent = VoiceOfCustomerAgent(settings)

            context = assemble_context(db, tenant)
            evidence_text, sampling_notes, csv_customers = render_evidence(db, tenant, context)
            names = name_entries(context, csv_customers)

            run_kwargs: dict = {}
            if max_searches is not None:
                run_kwargs["max_searches"] = max_searches
            if research_rounds is not None:
                run_kwargs["research_rounds"] = research_rounds

            result = agent.run(context, evidence_text, name_entries=names, **run_kwargs)

            for report in result.reports:
                db.add(
                    AgentReport(
                        tenant_id=run.tenant_id,
                        run_id=run.id,
                        report_number=report.report_number,
                        title=report.title,
                        content=report.content,
                        confidence_summary=report.confidence_summary,
                    )
                )
            db.add(
                VocRunMeta(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    tier=result.operating_tier,
                    attribution_policy=result.attribution_policy,
                    sampling_notes=sampling_notes,
                    attribution_replacements={str(k): v for k, v in result.attribution_replacements.items()},
                )
            )
            run.status = "succeeded"
            run.error = None
            db.commit()
        except Exception as exc:  # noqa: BLE001 -- any failure must land on the run row
            logger.exception("Voice of Customer run %s failed", run_id)
            db.rollback()
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"[:2000]
                db.commit()
    finally:
        db.close()
