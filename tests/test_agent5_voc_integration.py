"""
Agent 1 (Voice of Customer) -> Agent 5 (Strategy Synthesis).

Verifies rather than assumes the two claims the VoC briefing makes:

  1. Agent 5 discovers a `voice-of-customer` run as upstream through the
     existing most-recent-successful-run selection, with no VoC-specific
     integration code.
  2. "Findings for synthesis" survives into Pass 1's input -- including when
     the pack is over the summarisation threshold, where the generic
     summarizer would otherwise fold it away.

And the gap found while verifying (2): Pass 2 writes the decision brief from
Pass 1's structured output and never sees upstream text, so the section
could reach Pass 1 and still never reach the brief. It is now handed to the
decision brief's Pass 2 call verbatim, and only to that one.

DB-direct, no TestClient, so no `override_get_db` is needed.
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AgentReport, AgentRun, Tenant
from app.strategy_synthesis_service import (
    UPSTREAM_SUMMARIZE_THRESHOLD_CHARS,
    load_upstream_text,
    upstream_findings_for_synthesis,
)
from strategy_synthesis.agent import DECISION_BRIEF_REPORT_NUMBER, StrategySynthesisAgent
from strategy_synthesis.config import Settings
from strategy_synthesis.prompts import pass1_user_prompt, pass2_user_prompt
from strategy_synthesis.reports import REPORTS as A5_REPORTS
from strategy_synthesis.schemas import Pass1Output
from strategy_synthesis.upstream import extract_findings_for_synthesis
from voice_of_customer.reports import FINDINGS_FOR_SYNTHESIS_HEADING

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

FINDING = (
    "Integration effort, not lead time, is the complaint three Tier 1 integrators raise in "
    "programme reviews (Confidence: Medium -- OBSERVATION)."
)

REPORT_1 = f"""**Operating tier: TIER 1 PARTIAL.**

## Governing Insight
Situation. Complication. Question. Answer.

{FINDINGS_FOR_SYNTHESIS_HEADING}

{FINDING}

## Recommended actions
None the evidence supports.
"""


@pytest.fixture
def db():
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _tenant(db) -> Tenant:
    t = Tenant(name="A5-VoC")
    db.add(t)
    db.commit()
    return t


def _voc_run(db, tenant, report_1=REPORT_1, filler_chars=0, status="succeeded") -> AgentRun:
    run = AgentRun(tenant_id=tenant.id, agent_type="voice-of-customer", subject="VoC", status=status)
    db.add(run)
    db.flush()
    db.add(AgentReport(tenant_id=tenant.id, run_id=run.id, report_number=1, title="Executive summary",
                       content=report_1, confidence_summary=""))
    db.add(AgentReport(tenant_id=tenant.id, run_id=run.id, report_number=2, title="Pain points",
                       content="## Key Insights\n" + "x" * filler_chars, confidence_summary=""))
    db.commit()
    return run


class TestDiscovery:
    def test_voc_run_is_discovered_as_upstream(self, db):
        tenant = _tenant(db)
        _voc_run(db, tenant)
        agent = MagicMock()
        upstream = load_upstream_text(db, tenant, agent, None)
        assert "voice-of-customer" in upstream
        agent.summarize_upstream_agent.assert_not_called()

    def test_failed_voc_run_is_not_used(self, db):
        tenant = _tenant(db)
        _voc_run(db, tenant, status="failed")
        assert "voice-of-customer" not in load_upstream_text(db, tenant, MagicMock(), None)


class TestFindingsSurviveIntoPass1:
    def test_below_threshold_section_reaches_pass1_verbatim(self, db):
        tenant = _tenant(db)
        _voc_run(db, tenant)
        upstream = load_upstream_text(db, tenant, MagicMock(), None)
        prompt = pass1_user_prompt("brief", upstream)
        assert FINDINGS_FOR_SYNTHESIS_HEADING in prompt
        assert FINDING in prompt

    def test_above_threshold_section_is_reattached_verbatim_after_summary(self, db):
        tenant = _tenant(db)
        _voc_run(db, tenant, filler_chars=UPSTREAM_SUMMARIZE_THRESHOLD_CHARS + 1)
        agent = MagicMock()
        # A summarizer that drops the section entirely -- the failure mode.
        agent.summarize_upstream_agent.return_value = "Compressed summary with no named sections."
        upstream = load_upstream_text(db, tenant, agent, None)
        agent.summarize_upstream_agent.assert_called_once()
        text = upstream["voice-of-customer"]
        assert "Compressed summary" in text
        assert FINDINGS_FOR_SYNTHESIS_HEADING in text
        assert FINDING in text
        assert "not summarised" in text
        assert FINDING in pass1_user_prompt("brief", upstream)


class TestExtraction:
    def test_section_ends_at_next_level_2_heading(self):
        assert extract_findings_for_synthesis(REPORT_1) == FINDING

    def test_level_3_headings_stay_inside_the_section(self):
        text = f"{FINDINGS_FOR_SYNTHESIS_HEADING}\n\n### Lead times\n{FINDING}\n\n## Next\nno"
        assert "### Lead times" in extract_findings_for_synthesis(text)
        assert "no" not in extract_findings_for_synthesis(text).split(FINDING)[1]

    def test_no_section_extracts_nothing(self):
        assert extract_findings_for_synthesis("## Key Insights\n- a") == ""
        assert upstream_findings_for_synthesis({"market-insights": "## Key Insights\n- a"}) == {}


class TestFindingsReachTheDecisionBrief:
    def test_pass2_prompt_carries_the_block(self):
        spec = next(s for s in A5_REPORTS if s.number == DECISION_BRIEF_REPORT_NUMBER)
        prompt = pass2_user_prompt(spec, "brief", Pass1Output(), "computed", {"voice-of-customer": FINDING})
        assert "## Upstream findings for synthesis" in prompt
        assert FINDING in prompt
        assert "do not turn any into a project" in prompt.lower()

    def test_no_findings_no_block(self):
        spec = A5_REPORTS[0]
        assert "Upstream findings for synthesis" not in pass2_user_prompt(spec, "b", Pass1Output(), "c")

    def test_only_the_decision_brief_receives_them(self):
        agent = StrategySynthesisAgent(Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5"))
        received = {}

        def fake_pass2(spec, brief_text, pass1_out, computed_text, upstream_findings=None):
            received[spec.number] = upstream_findings
            return f"# Report {spec.number}"

        findings = {"voice-of-customer": FINDING}
        with patch.object(agent, "_call_pass1", return_value=Pass1Output()), \
                patch.object(agent, "_compute", return_value=MagicMock()), \
                patch("strategy_synthesis.agent.render_brief_text", return_value="brief"), \
                patch("strategy_synthesis.agent.render_computed_text", return_value="computed"), \
                patch.object(agent, "_call_pass2_report", side_effect=fake_pass2):
            agent.run(MagicMock(), {"voice-of-customer": REPORT_1}, upstream_findings=findings)

        assert received[DECISION_BRIEF_REPORT_NUMBER] == findings
        assert all(v is None for k, v in received.items() if k != DECISION_BRIEF_REPORT_NUMBER)
