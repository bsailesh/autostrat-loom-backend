"""
Report 0 -- the Executive Summary -- across all five agents
(executive_summary_briefing.md).

The per-agent ordering tests (written last, from the finished pack only,
presented first) live beside each agent's own run tests. This module holds
what spans the agents: the rules are the same in every copy of the
Consulting-Grade Output Standard, every pack has a Report 0, and the word
"executive" belongs to Report 0 alone.
"""
from unittest.mock import MagicMock, patch

import pytest

import market_insights.reports as mi_reports
import market_insights.standards as mi_standards
import product_sustainment.reports as ps_reports
import product_sustainment.standards as ps_standards
import strategy_synthesis.reports as ss_reports
import strategy_synthesis.standards as ss_standards
import tech_regulation.reports as tr_reports
import tech_regulation.standards as tr_standards
import voice_of_customer.reports as voc_reports
import voice_of_customer.standards as voc_standards
from market_insights.agent import MarketInsightsAgent
from market_insights.config import Settings as MISettings

SECTION_HEADING = "## Executive Summary Requirement (Report 0)"

# Strategy Synthesis imports Market Insights' copy; the other three carry
# their own. All four must say the same thing about Report 0.
STANDARD_COPIES = {
    "market_insights": mi_standards,
    "tech_regulation": tr_standards,
    "voice_of_customer": voc_standards,
    "product_sustainment": ps_standards,
}

ALL_REPORTS = {
    "market_insights": mi_reports,
    "voice_of_customer": voc_reports,
    "tech_regulation": tr_reports,
    "product_sustainment": ps_reports,
    "strategy_synthesis": ss_reports,
}

RENAMED_REPORT_1 = {
    "market_insights": "Market Summary",
    "voice_of_customer": "Customer Context Summary",
    "tech_regulation": "Technology & Regulatory Landscape",
    "product_sustainment": "Sustainment Landscape",
    "strategy_synthesis": "Project Universe",
}


def _section(standard: str) -> str:
    assert standard.count(SECTION_HEADING) == 1
    return standard.split(SECTION_HEADING, 1)[1]


class TestTheRulesLandInEveryCopy:
    def test_section_is_identical_in_all_four_copies(self):
        sections = {name: _section(m.CONSULTING_GRADE_OUTPUT_STANDARD) for name, m in STANDARD_COPIES.items()}
        reference = sections["market_insights"]
        for name, text in sections.items():
            assert text == reference, f"{name}'s Executive Summary Requirement has drifted"

    def test_strategy_synthesis_imports_rather_than_copies(self):
        assert ss_standards.CONSULTING_GRADE_OUTPUT_STANDARD is mi_standards.CONSULTING_GRADE_OUTPUT_STANDARD

    @pytest.mark.parametrize("name", list(STANDARD_COPIES))
    def test_key_insights_box_names_report_0_as_the_exception(self, name):
        standard = STANDARD_COPIES[name].CONSULTING_GRADE_OUTPUT_STANDARD
        before = standard.split(SECTION_HEADING, 1)[0]
        assert "Report 0, the Executive" in before

    def test_section_carries_the_load_bearing_rules(self):
        text = _section(mi_standards.CONSULTING_GRADE_OUTPUT_STANDARD)
        for rule in (
            "Up to ten bullets",
            "25 words or fewer",
            "Never cut a finding that passes the priority order",
            "exactly as the pack states them, or omit them",
            "Never present a risk as an event",
            "Never infer that an obligation was missed, breached or failed",
            "state non-compliance\n  only where the pack states it",
            "No sources, no citations, no confidence tags, no hedging",
            "Do not\nmanufacture bullets",
            "No Governing Insight",
            "The Visual\n  Requirement does not apply",
            "no Confidence Summary section",
            "a bullet with no backing is the\n  one failure that matters",
        ):
            assert rule in text, rule


class TestEveryPackHasAReport0:
    @pytest.mark.parametrize("name", list(ALL_REPORTS))
    def test_report_0_is_listed_first(self, name):
        reports = ALL_REPORTS[name]
        first = reports.REPORTS[0]
        assert reports.EXECUTIVE_SUMMARY_REPORT_NUMBER == 0
        assert (first.number, first.title, first.opening) == (0, "Executive Summary", "executive_summary")
        assert [r.number for r in reports.REPORTS] == sorted(r.number for r in reports.REPORTS)

    @pytest.mark.parametrize("name", list(ALL_REPORTS))
    def test_report_1_is_renamed(self, name):
        report_1 = next(r for r in ALL_REPORTS[name].REPORTS if r.number == 1)
        assert report_1.title == RENAMED_REPORT_1[name]

    @pytest.mark.parametrize("name", list(ALL_REPORTS))
    def test_only_report_0_carries_executive(self, name):
        for r in ALL_REPORTS[name].REPORTS:
            if r.number == 0:
                continue
            assert "executive" not in r.title.lower(), r.title
            assert "executive" not in r.exhibit.lower(), r.number
            assert not r.must_include.lower().lstrip().startswith("executive"), r.number

    def test_scqa_stays_where_it_was(self):
        def scqa(reports):
            return [r.number for r in reports.REPORTS if r.opening == "scqa"]

        assert scqa(ss_reports) == [7]
        for name in ("market_insights", "voice_of_customer", "tech_regulation", "product_sustainment"):
            assert scqa(ALL_REPORTS[name]) == [1], name


def _streaming(texts):
    def one(text):
        final = MagicMock(content=[MagicMock(type="text", text=text)], stop_reason="end_turn")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock(get_final_message=MagicMock(return_value=final)))
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    return MagicMock(side_effect=[one(t) for t in texts])


class TestMarketInsightsOrdering:
    def _agent(self):
        return MarketInsightsAgent(MISettings(anthropic_api_key="test-key-not-real", model="claude-opus-5"))

    def test_written_last_from_the_finished_pack_presented_first(self):
        agent = self._agent()
        texts = [f"body {n}" for n in range(1, 10)] + ["- summary bullet"]
        with patch.object(agent._client.messages, "stream", _streaming(texts)) as stream:
            result = agent.run("subject", prior_research=("RESEARCH BRIEF rows", [], []))

        assert [r.report_number for r in result.reports] == list(range(0, 10))
        assert result.reports[0].content == "- summary bullet"
        assert result.reports[0].title == "Executive Summary"

        summary_prompt = stream.call_args_list[-1].kwargs["messages"][0]["content"]
        assert "# Report 9 — Industry Trends\n\nbody 9" in summary_prompt
        assert "RESEARCH BRIEF rows" not in summary_prompt
        for call in stream.call_args_list[:-1]:
            assert "RESEARCH BRIEF rows" in call.kwargs["messages"][0]["content"]

    def test_report_0_alone_has_nothing_to_draw_on(self):
        agent = self._agent()
        with patch.object(agent._client.messages, "stream", _streaming([])):
            with pytest.raises(ValueError, match="Report 0"):
                agent.run("subject", only_reports=[0], prior_research=("brief", [], []))
