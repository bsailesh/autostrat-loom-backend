"""
Agent 3 -> Agent 5: structured candidate work reaching Pass 1 without being
parsed out of report prose, and the single-source-of-truth property that
design rests on.

The load-bearing test here is
`TestACorrectedDatePropagatesWithNothingSpecialRequired`. The design
decision it pins (Option A) was taken because the alternative -- copying
`driver` and `work_date` onto discovered_candidates -- creates two copies of
one fact, and a Tech & Regulation re-run that corrects an effective date
would leave the stale value behind unless something remembered to refresh
it. Nothing would have.

Isolated per conftest.py's convention: this module defines
`override_get_db`.
"""
import os
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.tech_regulation_service as tech_regulation_service
from app.database import Base, get_db
from app.main import app
from app.models import AgentRun, DiscoveredCandidate, Tenant, TrCandidateWork
from app.strategy_synthesis_service import load_structured_candidate_work
from tech_regulation.agent import AgentRunResult as TrRunResult
from tech_regulation.agent import Report as TrReport
from tech_regulation.schemas import CandidateWorkItem

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _pin_tech_regulation_session_factory():
    """execute_run's background task opens its own session via
    SessionFactory, since the request-scoped one is closed by the time the
    task runs. Pinned per test and restored afterwards, NOT assigned at
    module import: more than one test module needs its own database behind
    this global, and an import-time assignment makes whichever module
    imported last win for the whole session -- the same collection-order
    trap conftest.py's `_pin_db_override` exists to prevent for
    app.dependency_overrides. Caught by running the suite in reversed file
    order, which is why the briefing asks for it."""
    previous = tech_regulation_service.SessionFactory
    tech_regulation_service.SessionFactory = TestingSessionLocal
    try:
        yield
    finally:
        tech_regulation_service.SessionFactory = previous


client = TestClient(app)

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}
TR = "/agents/tech-regulation"


def create_tenant(name: str) -> dict:
    resp = client.post("/admin/tenants", json={"name": name}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _tr_item(**overrides) -> CandidateWorkItem:
    payload = {
        "candidate_key": "TR-04",
        "driver": "RTCA DO-160G Section 21 revision, effective 14 Mar 2028",
        "work_date": "2028-03-14",
        "date_basis": "effective",
        "date_absent_reason": "",
        "applicability": {
            "categories": ["EMA-UTIL"],
            "certification_bases": ["TSO-C196b"],
            "platforms": [],
            "note": "",
        },
        "work_implied": "requalification",
        "work_implied_description": "Requalification of affected articles",
        "platform_relationship": None,
        "classification": "FACT",
        "confidence": "High",
        "source": "EUROCAE",
        "source_date": "2027-02-11",
    }
    payload.update(overrides)
    return CandidateWorkItem.model_validate(payload)


def _tr_result(items) -> TrRunResult:
    return TrRunResult(
        operating_state="scoped",
        operating_state_line="**Operating state: SCOPED.**",
        generated_at="2026-10-03T00:00:00Z",
        model="claude-opus-5",
        web_search_queries=[],
        research_sources=[],
        research_brief="brief",
        candidate_work=items,
        candidate_work_dropped=[],
        reports=[
            TrReport(report_number=n, title=f"Report {n}", content=f"# body {n}", confidence_summary="")
            for n in (1, 2, 3, 4, 5, 6, 7, 8, 11)
        ],
    )


def _run_tech_regulation(headers, items) -> str:
    """One Tech & Regulation run that persists `items` as candidate work."""
    with patch("app.tech_regulation_service.TechRegulationAgent") as agent_cls:
        agent_cls.return_value.run.return_value = _tr_result(items)
        resp = client.post(f"{TR}/runs", json={}, headers=headers)
    assert resp.status_code == 202, resp.text
    run = resp.json()
    assert client.get(f"{TR}/runs/{run['id']}", headers=headers).json()["status"] == "succeeded"
    return run["id"]


def _tenant_row(tenant_id: str) -> Tenant:
    db = TestingSessionLocal()
    try:
        return db.get(Tenant, tenant_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# The property Option A rests on
# ---------------------------------------------------------------------------


class TestACorrectedDatePropagatesWithNothingSpecialRequired:
    def test_a_rerun_that_changes_a_date_reaches_agent5s_next_run(self):
        tenant = create_tenant("Propagation Co")
        headers = auth_headers(tenant["api_key"])

        # Run 1: TR-04 effective 14 Mar 2028
        run_1 = _run_tech_regulation(headers, [_tr_item()])

        db = TestingSessionLocal()
        first = load_structured_candidate_work(db, _tenant_row(tenant["id"]), None)
        db.close()
        assert [r["candidate_key"] for r in first] == ["TR-04"]
        assert first[0]["work_date"] == "2028-03-14"

        # Agent 5 carries it into a DiscoveredCandidate keyed by the same key
        db = TestingSessionLocal()
        db.add(
            DiscoveredCandidate(
                tenant_id=tenant["id"],
                candidate_key="TR-04",
                name="DO-160G Section 21 requalification",
                origin="Tech & Regulation — candidate work TR-04",
                first_seen_run_id=None,
                status="new",
            )
        )
        db.commit()
        row_before = (
            db.query(DiscoveredCandidate).filter_by(candidate_key="TR-04").one()
        )
        updated_at_before = row_before.updated_at
        db.close()

        # Run 2: the SAME key, corrected to 1 Sep 2028. No Agent 5 involvement.
        run_2 = _run_tech_regulation(headers, [_tr_item(work_date="2028-09-01")])
        assert run_2 != run_1

        # What Agent 5's next run is handed carries the corrected date.
        db = TestingSessionLocal()
        second = load_structured_candidate_work(db, _tenant_row(tenant["id"]), None)
        db.close()
        assert [r["candidate_key"] for r in second] == ["TR-04"]
        assert second[0]["work_date"] == "2028-09-01", (
            "the corrected date must reach Pass 1 through the live read"
        )

        # ...and nothing wrote to discovered_candidates to make that true.
        db = TestingSessionLocal()
        row_after = db.query(DiscoveredCandidate).filter_by(candidate_key="TR-04").one()
        assert row_after.updated_at == updated_at_before, (
            "no refresh of the Agent 5 row was required; if this fails, a copy "
            "of the date has appeared somewhere and can now go stale"
        )
        db.close()

    def test_discovered_candidates_has_nowhere_to_hold_a_stale_copy(self):
        """The structural half. The two assertions above would also pass under
        Option B as long as something remembered to refresh the copy -- so the
        test has to pin the absence of the copy, not just today's behaviour.
        This is the assertion that starts failing the day those columns are
        added, which is exactly when we would want to know."""
        columns = {c.name for c in DiscoveredCandidate.__table__.columns}
        assert "driver" not in columns
        assert "work_date" not in columns
        assert "date_basis" not in columns
        assert "origin" in columns  # the join key lives here

    def test_the_api_also_reads_the_date_live(self):
        """Not just the Pass 1 read: the candidates endpoint resolves driver
        and date through the same live join, so the UI cannot show a stale
        date either."""
        tenant = create_tenant("Live API Co")
        headers = auth_headers(tenant["api_key"])
        _run_tech_regulation(headers, [_tr_item()])

        db = TestingSessionLocal()
        db.add(
            DiscoveredCandidate(
                tenant_id=tenant["id"],
                candidate_key="TR-04",
                name="DO-160G Section 21 requalification",
                origin="Tech & Regulation — candidate work TR-04",
                status="new",
            )
        )
        db.commit()
        db.close()

        before = client.get("/agents/strategy/candidates", headers=headers).json()
        assert before[0]["linked_candidate_work"]["work_date"] == "2028-03-14"

        _run_tech_regulation(headers, [_tr_item(work_date="2028-09-01")])

        after = client.get("/agents/strategy/candidates", headers=headers).json()
        assert after[0]["linked_candidate_work"]["work_date"] == "2028-09-01"


# ---------------------------------------------------------------------------
# The neighbour: dismissal and the live read coexisting
# ---------------------------------------------------------------------------


class TestDismissalAndTheLiveReadCoexist:
    def test_a_dismissed_item_is_not_offered_to_pass1_but_keeps_its_date(self):
        tenant = create_tenant("Dismissed Upstream Co")
        headers = auth_headers(tenant["api_key"])
        _run_tech_regulation(headers, [_tr_item()])

        client.patch(
            f"{TR}/candidate-work/TR-04",
            json={"status": "dismissed", "dismissal_reason": "covered by an in-flight programme"},
            headers=headers,
        )

        db = TestingSessionLocal()
        rows = load_structured_candidate_work(db, _tenant_row(tenant["id"]), None)
        db.close()
        assert rows == [], "Agent 3 judged the finding not relevant; Pass 1 is not offered it"

        # the row and its evidence survive, so the dismissal is reviewable
        work = client.get(f"{TR}/candidate-work", headers=headers).json()
        assert work[0]["status"] == "dismissed"
        assert work[0]["work_date"] == "2028-03-14"

    def test_a_disagreement_between_the_two_judgements_is_visible(self):
        """Dismissed in Tech & Regulation, still active in Agent 5. Two
        different questions -- "is this finding real" and "would we scope this
        as a project" -- so the UI shows both statuses rather than hiding the
        split."""
        tenant = create_tenant("Disagreement Co")
        headers = auth_headers(tenant["api_key"])
        _run_tech_regulation(headers, [_tr_item()])

        db = TestingSessionLocal()
        db.add(
            DiscoveredCandidate(
                tenant_id=tenant["id"],
                candidate_key="TR-04",
                name="DO-160G Section 21 requalification",
                origin="Tech & Regulation — candidate work TR-04",
                status="under_review",
            )
        )
        db.commit()
        db.close()

        client.patch(
            f"{TR}/candidate-work/TR-04",
            json={"status": "dismissed", "dismissal_reason": "not applicable after re-reading the TSO"},
            headers=headers,
        )

        candidates = client.get("/agents/strategy/candidates", headers=headers).json()
        assert len(candidates) == 1
        assert candidates[0]["status"] == "under_review"
        linked = candidates[0]["linked_candidate_work"]
        assert linked["status"] == "dismissed"
        assert linked["dismissal_reason"] == "not applicable after re-reading the TSO"
        assert candidates[0]["origin"] == "Tech & Regulation — candidate work TR-04"

    def test_a_prose_derived_candidate_has_no_linked_item(self):
        """The distinguishability test: a candidate Pass 1 inferred from
        upstream markdown has no row to link to, so it carries no driver and
        no date and the UI can tell it apart."""
        tenant = create_tenant("Prose Derived Co")
        headers = auth_headers(tenant["api_key"])

        db = TestingSessionLocal()
        db.add(
            DiscoveredCandidate(
                tenant_id=tenant["id"],
                candidate_key="C-01",
                name="Inferred from the market pack",
                origin="Discovered -- Market",
                status="new",
            )
        )
        db.commit()
        db.close()

        candidates = client.get("/agents/strategy/candidates", headers=headers).json()
        assert candidates[0]["candidate_key"] == "C-01"
        assert candidates[0]["linked_candidate_work"] is None


# ---------------------------------------------------------------------------
# Run selection, and the additive-ness of the change
# ---------------------------------------------------------------------------


class TestRunSelection:
    def test_an_explicit_upstream_override_selects_that_runs_rows(self):
        tenant = create_tenant("Override Co")
        headers = auth_headers(tenant["api_key"])
        run_1 = _run_tech_regulation(headers, [_tr_item()])
        _run_tech_regulation(headers, [_tr_item(candidate_key="TR-09", work_date="2029-01-01")])

        db = TestingSessionLocal()
        tenant_row = _tenant_row(tenant["id"])
        pinned = load_structured_candidate_work(db, tenant_row, {"tech-regulation": run_1})
        latest = load_structured_candidate_work(db, tenant_row, None)
        db.close()

        # last_seen_run_id means "the most recent run that surfaced this
        # item", so pinning a run yields the items whose latest sighting was
        # that run. The second run surfaced only TR-09 and did not touch
        # TR-04, so TR-04 still belongs to run_1.
        assert [r["candidate_key"] for r in pinned] == ["TR-04"]
        assert [r["candidate_key"] for r in latest] == ["TR-09"]

    def test_an_item_reconfirmed_by_a_later_run_moves_to_that_run(self):
        """The corollary, and the reason a corrected item is never orphaned:
        re-confirming an item moves it forward, so it leaves the earlier
        run's set and appears in the newer one's."""
        tenant = create_tenant("Reconfirm Co")
        headers = auth_headers(tenant["api_key"])
        run_1 = _run_tech_regulation(headers, [_tr_item()])
        run_2 = _run_tech_regulation(headers, [_tr_item(work_date="2028-09-01")])

        db = TestingSessionLocal()
        tenant_row = _tenant_row(tenant["id"])
        first = load_structured_candidate_work(db, tenant_row, {"tech-regulation": run_1})
        second = load_structured_candidate_work(db, tenant_row, {"tech-regulation": run_2})
        db.close()

        assert [r["candidate_key"] for r in first] == []
        assert [r["candidate_key"] for r in second] == ["TR-04"]
        assert second[0]["work_date"] == "2028-09-01"

    def test_no_tech_regulation_run_yields_no_rows_and_no_error(self):
        tenant = create_tenant("No TR Run Co")
        db = TestingSessionLocal()
        assert load_structured_candidate_work(db, _tenant_row(tenant["id"]), None) == []
        db.close()

    def test_a_failed_tech_regulation_run_is_not_selected(self):
        tenant = create_tenant("Failed TR Co")
        db = TestingSessionLocal()
        db.add(
            AgentRun(
                tenant_id=tenant["id"], agent_type="tech-regulation", subject="x", status="failed"
            )
        )
        db.commit()
        db.close()

        db = TestingSessionLocal()
        assert load_structured_candidate_work(db, _tenant_row(tenant["id"]), None) == []
        db.close()

    def test_rows_are_tenant_isolated(self):
        a = create_tenant("TR Isolation A")
        b = create_tenant("TR Isolation B")
        _run_tech_regulation(auth_headers(a["api_key"]), [_tr_item()])

        db = TestingSessionLocal()
        assert load_structured_candidate_work(db, _tenant_row(b["id"]), None) == []
        db.close()

    def test_triage_fields_are_not_sent_to_pass1(self):
        """Agent 3's own triage is not Pass 1's business, and the id and
        timestamps are noise in a prompt."""
        tenant = create_tenant("Prompt Fields Co")
        _run_tech_regulation(auth_headers(tenant["api_key"]), [_tr_item()])

        db = TestingSessionLocal()
        rows = load_structured_candidate_work(db, _tenant_row(tenant["id"]), None)
        db.close()
        assert "driver" in rows[0] and "work_date" in rows[0]
        for absent in ("status", "dismissal_reason", "id", "created_at", "updated_at",
                       "first_seen_run_id", "last_seen_run_id", "tenant_id"):
            assert absent not in rows[0], absent


class TestTheChangeIsAdditive:
    def test_pass1_prompt_omits_the_section_entirely_when_there_are_no_rows(self):
        from strategy_synthesis.prompts import pass1_user_prompt

        without = pass1_user_prompt("BRIEF", {"market-insights": "text"})
        assert "Pre-structured candidate work" not in without

        with_rows = pass1_user_prompt(
            "BRIEF", {"market-insights": "text"}, [{"candidate_key": "TR-04", "driver": "DO-160G"}]
        )
        assert "Pre-structured candidate work" in with_rows
        assert "TR-04" in with_rows

    def test_agent_run_still_works_with_no_structured_candidates_argument(self):
        """Every existing caller and test passes two arguments. The new one is
        defaulted, so Pass 1's prose discovery is untouched."""
        from strategy_synthesis.agent import StrategySynthesisAgent
        from strategy_synthesis.config import Settings
        from tests.test_agent5_agent import _bottleneck_brief, _pass1_output_for

        agent = StrategySynthesisAgent(Settings(anthropic_api_key="k", model="claude-opus-5"))
        brief = _bottleneck_brief()
        captured = {}

        def fake_call_pass1(b, brief_text, upstream, structured=None, sustainment_candidates=None):
            captured["structured"] = structured
            return _pass1_output_for(brief)

        with patch.object(agent, "_call_pass1", side_effect=fake_call_pass1):
            with patch.object(agent, "_call_pass2_report", return_value="ok"):
                agent.run(brief, {})

        assert captured["structured"] is None
