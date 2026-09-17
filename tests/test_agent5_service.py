"""
Tests for `app/strategy_synthesis_service.py` -- brief assembly, fiscal-year
default derivation, upstream loading under the memory threshold, and
candidate persistence. Uses an isolated in-memory SQLite database (this
module's own engine, not shared with any router-level test module).
"""
import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    AgentReport,
    AgentRun,
    CapacityBucket,
    CapacityRow,
    DiscoveredCandidate,
    PortfolioProject,
    ProjectEffortRow,
    StrategyConfig,
    Tenant,
)
from app.strategy_synthesis_service import (
    AmbiguousFiscalYearError,
    UPSTREAM_SUMMARIZE_THRESHOLD_CHARS,
    _date_derived_fiscal_year,
    assemble_brief,
    default_fiscal_year,
    load_upstream_text,
    persist_candidates,
)
from strategy_synthesis.schemas import Pass1Candidate

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def tenant(db):
    t = Tenant(name="Fiscal Year Test Co")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestFiscalYearDefault:
    def test_single_capacity_year_is_used(self, db, tenant):
        db.add(CapacityRow(tenant_id=tenant.id, fiscal_year="FY27", bucket_key="HW", capacity_units=100))
        db.commit()
        assert default_fiscal_year(db, tenant, config=None) == "FY27"

    def test_multiple_capacity_years_raise_rather_than_guess(self, db, tenant):
        db.add(CapacityRow(tenant_id=tenant.id, fiscal_year="FY27", bucket_key="HW", capacity_units=100))
        db.add(CapacityRow(tenant_id=tenant.id, fiscal_year="FY28", bucket_key="HW", capacity_units=100))
        db.commit()
        with pytest.raises(AmbiguousFiscalYearError) as exc_info:
            default_fiscal_year(db, tenant, config=None)
        assert "FY27" in exc_info.value.candidates and "FY28" in exc_info.value.candidates

    def test_no_capacity_falls_back_to_date_derived_label(self, db, tenant):
        # no capacity rows at all -- harmless fallback since no bottleneck
        # analysis is possible either way
        result = default_fiscal_year(db, tenant, config=None)
        assert result.startswith("FY")

    def test_date_derived_label_respects_fiscal_year_start_month(self):
        config = StrategyConfig(fiscal_year_start_month=10, fiscal_year_label_format="FY{yy}")
        # Sep 2026, before an Oct start -- still in the FY that started Oct 2025
        result = _date_derived_fiscal_year(config, today=date(2026, 9, 17))
        assert result == "FY25"
        # Oct 2026 itself -- the new FY has started
        result2 = _date_derived_fiscal_year(config, today=date(2026, 10, 1))
        assert result2 == "FY26"

    def test_calendar_year_start_month_matches_the_calendar_year(self):
        config = StrategyConfig(fiscal_year_start_month=1, fiscal_year_label_format="FY{yy}")
        result = _date_derived_fiscal_year(config, today=date(2026, 1, 1))
        assert result == "FY26"


class TestAssembleBrief:
    def test_translates_rows_into_compute_dataclasses(self, db, tenant):
        db.add(CapacityBucket(tenant_id=tenant.id, bucket_key="HW", bucket_name="Hardware", contractable="yes"))
        db.add(CapacityRow(tenant_id=tenant.id, fiscal_year="FY27", bucket_key="HW", capacity_units=500))
        db.add(PortfolioProject(tenant_id=tenant.id, project_key="P-01", name="TSO cert", mandatory=True))
        db.add(ProjectEffortRow(tenant_id=tenant.id, project_key="P-01", bucket_key="HW", effort_remaining=40))
        db.commit()

        brief = assemble_brief(db, tenant, fiscal_year="FY27")

        assert brief.fiscal_year == "FY27"
        assert [b.bucket_key for b in brief.buckets] == ["HW"]
        assert brief.capacity[0].capacity_units == 500
        assert brief.projects[0].mandatory is True
        assert brief.project_effort[0].effort_remaining == 40

    def test_no_framework_configured_defaults_to_value_vs_effort(self, db, tenant):
        brief = assemble_brief(db, tenant, fiscal_year="FY27")
        assert brief.framework_name == "value_vs_effort"
        assert brief.weights == {"value": 0.5, "effort": 0.5}


class TestLoadUpstreamText:
    def _make_upstream_run(self, db, tenant, agent_type, contents: list[str], status="succeeded"):
        run = AgentRun(tenant_id=tenant.id, agent_type=agent_type, subject="x", status=status)
        db.add(run)
        db.flush()
        for i, content in enumerate(contents, start=1):
            db.add(AgentReport(tenant_id=tenant.id, run_id=run.id, report_number=i, title=f"R{i}", content=content))
        db.commit()
        return run

    def test_small_report_pack_is_not_summarized(self, db, tenant):
        self._make_upstream_run(db, tenant, "market-insights", ["short content"])
        agent = MagicMock()

        result = load_upstream_text(db, tenant, agent, overrides=None)

        assert result["market-insights"] == "short content"
        agent.summarize_upstream_agent.assert_not_called()

    def test_oversized_report_pack_is_summarized_and_noted(self, db, tenant):
        big_content = "x" * (UPSTREAM_SUMMARIZE_THRESHOLD_CHARS + 1)
        self._make_upstream_run(db, tenant, "market-insights", [big_content])
        agent = MagicMock()
        agent.summarize_upstream_agent.return_value = "compressed summary"

        result = load_upstream_text(db, tenant, agent, overrides=None)

        agent.summarize_upstream_agent.assert_called_once_with("market-insights", big_content)
        assert "compressed summary" in result["market-insights"]
        assert "summarized before analysis" in result["market-insights"]

    def test_only_successful_runs_are_selected_by_default(self, db, tenant):
        self._make_upstream_run(db, tenant, "market-insights", ["old failed content"], status="failed")
        result = load_upstream_text(db, tenant, MagicMock(), overrides=None)
        assert "market-insights" not in result  # no successful run exists

    def test_override_pins_a_specific_run(self, db, tenant):
        older = self._make_upstream_run(db, tenant, "market-insights", ["older"])
        newer = self._make_upstream_run(db, tenant, "market-insights", ["newer"])
        assert newer.created_at >= older.created_at

        result = load_upstream_text(db, tenant, MagicMock(), overrides={"market-insights": older.id})
        assert result["market-insights"] == "older"

    def test_strategy_synthesis_itself_is_never_treated_as_upstream(self, db, tenant):
        self._make_upstream_run(db, tenant, "strategy-synthesis", ["should never be upstream of itself"])
        result = load_upstream_text(db, tenant, MagicMock(), overrides=None)
        assert result == {}


class TestPersistCandidates:
    def test_genuinely_new_candidate_gets_status_new(self, db, tenant):
        run = AgentRun(tenant_id=tenant.id, agent_type="strategy-synthesis", subject="x", status="running")
        db.add(run)
        db.flush()

        candidate = Pass1Candidate(
            key="C-01", name="New candidate", origin="Discovered", problem="p",
            evidence_summary="e", support_classification="evidence-supported", evidence_strength_rank=1,
        )
        persist_candidates(db, tenant, run, [candidate])
        db.commit()

        row = db.query(DiscoveredCandidate).filter_by(tenant_id=tenant.id, candidate_key="C-01").one()
        assert row.status == "new"
        assert row.first_seen_run_id == run.id

    def test_dismissed_candidate_is_not_resurrected_as_new(self, db, tenant):
        """The exact case the user asked to confirm: a previously dismissed
        candidate, rediscovered by a later run, keeps its dismissed status
        and reason -- only its evidence fields refresh."""
        db.add(
            DiscoveredCandidate(
                tenant_id=tenant.id, candidate_key="C-01", name="Old name",
                origin="Discovered", problem_addressed="old problem",
                evidence_summary="old evidence", support_classification="partially supported",
                status="dismissed", dismissal_reason="Not aligned with strategy this year",
            )
        )
        db.commit()

        run = AgentRun(tenant_id=tenant.id, agent_type="strategy-synthesis", subject="x", status="running")
        db.add(run)
        db.flush()

        rediscovered = Pass1Candidate(
            key="C-01", name="Updated name", origin="Discovered", problem="new problem statement",
            evidence_summary="fresh evidence this run", support_classification="evidence-supported",
            evidence_strength_rank=1,
        )
        persist_candidates(db, tenant, run, [rediscovered])
        db.commit()

        row = db.query(DiscoveredCandidate).filter_by(tenant_id=tenant.id, candidate_key="C-01").one()
        assert row.status == "dismissed"
        assert row.dismissal_reason == "Not aligned with strategy this year"
        # evidence fields DID refresh
        assert row.name == "Updated name"
        assert row.problem_addressed == "new problem statement"
        assert row.evidence_summary == "fresh evidence this run"

    def test_existing_candidate_not_in_this_runs_output_is_left_untouched(self, db, tenant):
        db.add(
            DiscoveredCandidate(
                tenant_id=tenant.id, candidate_key="C-02", name="Untouched", status="under_review",
            )
        )
        db.commit()
        run = AgentRun(tenant_id=tenant.id, agent_type="strategy-synthesis", subject="x", status="running")
        db.add(run)
        db.flush()

        persist_candidates(db, tenant, run, candidates=[])  # this run found nothing
        db.commit()

        row = db.query(DiscoveredCandidate).filter_by(tenant_id=tenant.id, candidate_key="C-02").one()
        assert row.status == "under_review"
        assert row.name == "Untouched"
