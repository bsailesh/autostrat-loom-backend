"""
Tests for Agent 3's (Technology & Regulatory Intelligence) data model --
the eight applicability-envelope tables plus `tr_candidate_work`, and the
cover-page label the Word export needs.

Isolated in-memory SQLite, this module's own engine, same pattern as
tests/test_agent5_service.py. No TestClient here, so no `override_get_db`
is needed (see tests/conftest.py).

Two of the assertions below are structural guards rather than behaviour
tests, and are the point of the file:

  * `tr_candidate_work` carries no effort, cost, duration, reach or
    priority column. This agent cannot see the customer's capacity, so
    sizing and ranking are Agent 5's; keeping the columns absent makes
    that a property of the schema instead of a prompt instruction.
  * `discovered_candidates` carries no `driver` or `work_date`. Agent 5's
    linked candidate reaches those through `tr_candidate_work`, so there
    is exactly one copy of each fact and nothing to refresh. The
    behavioural half of that property -- a corrected date reaching
    Agent 5's next run with nothing special required -- is
    tests/test_agent5_tech_regulation_integration.py.
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    DiscoveredCandidate,
    Tenant,
    TrCandidateWork,
    TrCertificationBasis,
    TrDomain,
    TrExclusion,
    TrJurisdiction,
    TrPlatform,
    TrProductCategory,
    TrStandardHeld,
    TrSupplier,
)
from app.tenant_scope import scoped_query

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

ENVELOPE_MODELS = [
    TrProductCategory,
    TrJurisdiction,
    TrCertificationBasis,
    TrPlatform,
    TrStandardHeld,
    TrSupplier,
    TrDomain,
    TrExclusion,
]


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
    t = Tenant(name="Arden Actuation Systems")
    db.add(t)
    db.commit()
    return t


@pytest.fixture()
def other_tenant(db):
    t = Tenant(name="Unrelated Co")
    db.add(t)
    db.commit()
    return t


# ---------------------------------------------------------------------------
# Schema creation -- create_all is the whole deployment story for this agent
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_every_envelope_table_and_candidate_work_is_created(self):
        """`Base.metadata.create_all` creates new tables but does not alter
        existing ones, so this agent deploys on a restart only as long as all
        of its storage is new tables -- which this asserts."""
        names = set(inspect(engine).get_table_names())
        expected = {m.__tablename__ for m in ENVELOPE_MODELS} | {"tr_candidate_work"}
        assert expected <= names

    def test_agent_runs_and_agent_reports_are_reused_not_replaced(self):
        """Agent 3 rides the existing `agent_type` discriminator. If either
        table ever grows a tech-regulation-specific column, that is an ALTER
        on production and this test is where it should first hurt."""
        inspector = inspect(engine)
        run_columns = {c["name"] for c in inspector.get_columns("agent_runs")}
        report_columns = {c["name"] for c in inspector.get_columns("agent_reports")}
        assert run_columns == {
            "id", "tenant_id", "agent_type", "subject", "status", "error", "created_at",
        }
        assert report_columns == {
            "id", "tenant_id", "run_id", "report_number", "title", "content",
            "confidence_summary", "created_at",
        }


# ---------------------------------------------------------------------------
# Tenant isolation and natural keys
# ---------------------------------------------------------------------------


class TestTenantScoping:
    def test_envelope_rows_are_invisible_to_another_tenant(self, db, tenant, other_tenant):
        db.add_all([
            TrProductCategory(tenant_id=tenant.id, category_key="EMA-FIN", category_name="Missile fin actuation"),
            TrJurisdiction(tenant_id=tenant.id, jurisdiction="European Union", role="primary"),
            TrCertificationBasis(
                tenant_id=tenant.id, category_key="EMA-UTIL", basis_type="TSO",
                basis_identifier="TSO-C196b", status="approved", held_since="2019",
            ),
            TrPlatform(
                tenant_id=tenant.id, platform="Narrowbody commercial",
                platform_class="Part 25 transport", relationship="pursuing",
                programme_status="design-in window",
            ),
            TrStandardHeld(tenant_id=tenant.id, standard_id="DO-160", revision="G", status="compliant"),
            TrSupplier(tenant_id=tenant.id, supplier="Vendor A", criticality="single_source"),
            TrDomain(tenant_id=tenant.id, domain="Advanced air mobility"),
            TrExclusion(tenant_id=tenant.id, exclusion_type="jurisdiction", value="China", reason="no sales intent"),
        ])
        db.commit()

        for model in ENVELOPE_MODELS:
            assert scoped_query(db, model, tenant).count() == 1, model.__tablename__
            assert scoped_query(db, model, other_tenant).count() == 0, model.__tablename__

    def test_same_natural_key_is_allowed_in_two_tenants(self, db, tenant, other_tenant):
        db.add(TrProductCategory(tenant_id=tenant.id, category_key="EMA-FIN", category_name="Fin actuation"))
        db.add(TrProductCategory(tenant_id=other_tenant.id, category_key="EMA-FIN", category_name="Something else"))
        db.commit()
        assert scoped_query(db, TrProductCategory, tenant).count() == 1
        assert scoped_query(db, TrProductCategory, other_tenant).count() == 1

    def test_duplicate_natural_key_within_a_tenant_is_rejected(self, db, tenant):
        db.add(TrDomain(tenant_id=tenant.id, domain="Electrification"))
        db.commit()
        db.add(TrDomain(tenant_id=tenant.id, domain="Electrification"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_one_category_may_hold_several_certification_bases(self, db, tenant):
        """Arden's utility actuation holds both TSO-C196b and a 14 CFR Part 25
        installation approval, so the natural key is the triple."""
        db.add_all([
            TrCertificationBasis(
                tenant_id=tenant.id, category_key="EMA-UTIL", basis_type="TSO",
                basis_identifier="TSO-C196b",
            ),
            TrCertificationBasis(
                tenant_id=tenant.id, category_key="EMA-UTIL", basis_type="Part",
                basis_identifier="14 CFR Part 25",
            ),
        ])
        db.commit()
        assert scoped_query(db, TrCertificationBasis, tenant).count() == 2


# ---------------------------------------------------------------------------
# Candidate work
# ---------------------------------------------------------------------------


class TestCandidateWork:
    def _item(self, tenant_id, **overrides):
        fields = dict(
            tenant_id=tenant_id,
            candidate_key="TR-01",
            driver="EUROCAE ED-14G / RTCA DO-160G Section 21 revision, effective 14 Mar 2028",
            work_date="2028-03-14",
            date_basis="effective",
            applicability={"categories": ["EMA-UTIL"], "bases": ["TSO-C196b"]},
            work_implied="requalification",
            work_implied_description="Requalification of affected articles against the revised section",
            classification="FACT",
            confidence="High",
            source="EUROCAE",
            source_date="2027-02-11",
        )
        fields.update(overrides)
        return TrCandidateWork(**fields)

    def test_a_complete_item_round_trips_with_its_applicability_json(self, db, tenant):
        db.add(self._item(tenant.id))
        db.commit()
        row = scoped_query(db, TrCandidateWork, tenant).one()
        assert row.candidate_key == "TR-01"
        assert row.applicability == {"categories": ["EMA-UTIL"], "bases": ["TSO-C196b"]}
        assert row.status == "new"
        assert row.platform_relationship is None

    def test_a_dateless_item_stores_its_absence_reason(self, db, tenant):
        """An undated candidate is standing context and a dated one can be
        scheduled, so the absence has to be honest rather than an omission.
        The rejection path for a null date with no reason is the agent's
        completeness validation, not a DB check -- this only asserts the
        column pair exists to carry it."""
        db.add(self._item(
            tenant.id,
            candidate_key="TR-02",
            work_date=None,
            date_basis="none_established",
            date_absent_reason="EASA has called for the requirement; no standard published and no date set",
        ))
        db.commit()
        row = scoped_query(db, TrCandidateWork, tenant).filter_by(candidate_key="TR-02").one()
        assert row.work_date is None
        assert "no date set" in row.date_absent_reason

    def test_platform_relationship_survives_to_the_row(self, db, tenant):
        """A change on a shipping platform is a cost; the same change on a
        pursued one is an entry condition. The distinction has to reach
        Agent 5, so it is stored rather than left in prose."""
        db.add(self._item(tenant.id, candidate_key="TR-03", platform_relationship="pursuing"))
        db.commit()
        row = scoped_query(db, TrCandidateWork, tenant).filter_by(candidate_key="TR-03").one()
        assert row.platform_relationship == "pursuing"

    def test_candidate_key_is_unique_per_tenant(self, db, tenant):
        db.add(self._item(tenant.id))
        db.commit()
        db.add(self._item(tenant.id))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_first_and_last_seen_runs_are_tracked_separately(self, db, tenant):
        """Agent 5 reads the candidate work *for an upstream run*, which has
        to include items that run re-surfaced and not only ones it first
        discovered -- otherwise a corrected item disappears from the very run
        that corrected it."""
        row = self._item(tenant.id)
        row.first_seen_run_id = None
        row.last_seen_run_id = None
        db.add(row)
        db.commit()
        columns = {c.name for c in TrCandidateWork.__table__.columns}
        assert {"first_seen_run_id", "last_seen_run_id"} <= columns


# ---------------------------------------------------------------------------
# Structural guards
# ---------------------------------------------------------------------------


class TestWhatTheSchemaMustNotCarry:
    def test_candidate_work_has_no_effort_cost_or_priority_column(self):
        """Naming the work is this agent's job; sizing and ranking it is
        Agent 5's, against capacity and objectives this agent cannot see.
        Absent columns make that structural rather than a prompt rule."""
        columns = {c.name for c in TrCandidateWork.__table__.columns}
        forbidden = {
            "effort", "effort_remaining", "effort_estimate", "duration", "cost",
            "capex", "opex", "reach", "priority", "rank", "score", "weight",
        }
        assert columns & forbidden == set()

    def test_discovered_candidates_stores_no_driver_or_work_date(self):
        """Option A: `driver` and `work_date` live once, in
        `tr_candidate_work`, and Agent 5's linked candidate reaches them
        through the `TR-xx` key carried in `origin`. Adding either column
        here would create a second copy of the same fact that nothing
        refreshes when a Tech & Regulation re-run corrects it -- which is the
        drift this design exists to avoid. If this assertion ever fails,
        the ALTER TABLE is the smaller half of the problem."""
        columns = {c.name for c in DiscoveredCandidate.__table__.columns}
        assert "driver" not in columns
        assert "work_date" not in columns
        assert "date_basis" not in columns
        assert "origin" in columns  # the join key lives here


# Export cover labels moved to tests/test_export_labels.py, which checks every
# agent rather than borrowing an unbuilt one as the unregistered example.
