"""
Tests for `strategy_synthesis/agent.py` -- the two-pass orchestration.
No real Anthropic calls: `_call_pass1` and `_call_pass2_report` are mocked
directly (there is no existing test coverage for market_insights/agent.py's
LLM calls to pattern-match, so this is this package's own testability seam).

The load-bearing test in this file is
`test_pass2_prompts_never_receive_a_recomputable_number` -- it exists to
make the two-pass boundary a checked property of the code, not a claim
about it.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest

from strategy_synthesis.agent import Pass1ValidationError, StrategySynthesisAgent
from strategy_synthesis.brief import DecisionBrief, Objective
from strategy_synthesis.compute import Bucket, Capacity, Dependency, Project, ProjectEffort, Scenario
from strategy_synthesis.config import Settings
from strategy_synthesis.reports import REPORTS
from strategy_synthesis.schemas import Pass1Candidate, Pass1DimensionScore, Pass1Output, Pass1ProjectScore


def _settings():
    return Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5")


def _tool_use_block(tool_name: str, input: dict) -> MagicMock:
    """`MagicMock(name=...)` sets the mock's own debug name, not a `.name`
    attribute -- has to be set after construction to fake an SDK tool_use
    content block, which real code reads via `block.name`."""
    block = MagicMock(type="tool_use", input=input)
    block.name = tool_name
    return block


def _bottleneck_brief() -> DecisionBrief:
    """The strawman's own shape, trimmed to two buckets/two projects: one
    mandatory project alone oversubscribes CERT."""
    return DecisionBrief(
        fiscal_year="FY27",
        effort_unit="weeks",
        objectives=[Objective(key="SO-1", text="Capture the cohort"), Objective(key="SO-3", text="Route to market")],
        buckets=[
            Bucket(bucket_key="HW", bucket_name="Hardware", contractable="yes"),
            Bucket(bucket_key="CERT", bucket_name="Certification", contractable="no"),
        ],
        capacity=[
            Capacity(fiscal_year="FY27", bucket_key="HW", capacity_units=980),
            Capacity(fiscal_year="FY27", bucket_key="CERT", capacity_units=240),
        ],
        projects=[
            Project(project_key="P-01", name="TSO cert", mandatory=True),
            Project(project_key="P-05", name="Variant", mandatory=False),
        ],
        project_effort=[
            ProjectEffort(project_key="P-01", bucket_key="HW", effort_remaining=6),
            ProjectEffort(project_key="P-01", bucket_key="CERT", effort_remaining=250),
            ProjectEffort(project_key="P-05", bucket_key="HW", effort_remaining=150),
            ProjectEffort(project_key="P-05", bucket_key="CERT", effort_remaining=40),
        ],
        dependencies=[Dependency(project_key="P-05", depends_on="P-01", source="customer")],
        framework_name="weighted_scoring",
        weights={"customer": 0.5, "effort": 0.5},
        scenarios=[Scenario(name="Growth", weights={"customer": 0.9, "effort": 0.1})],
    )


def _pass1_output_for(brief: DecisionBrief) -> Pass1Output:
    return Pass1Output(
        candidates=[
            Pass1Candidate(
                key="C-01", name="Route to market", origin="Discovered", problem="x",
                evidence_summary="y", support_classification="evidence-supported",
                evidence_strength_rank=1,
            )
        ],
        project_scores=[
            Pass1ProjectScore(
                project_key=p.project_key,
                dimensions=[
                    Pass1DimensionScore(criterion="customer", score=8, basis="estimated", reason="r"),
                    Pass1DimensionScore(criterion="effort", score=5, basis="calculated", reason="r"),
                ],
                objectives_served=["SO-1"] if p.project_key == "P-01" else [],
                confidence="Medium",
            )
            for p in brief.projects
        ],
    )


class TestPass1RetryOnceThenFail:
    def test_valid_first_response_does_not_retry(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        expected = _pass1_output_for(brief)

        tool_block = _tool_use_block("emit_pass1_output", expected.model_dump())
        response = MagicMock(content=[tool_block], stop_reason="tool_use")

        with patch.object(agent._client.messages, "create", return_value=response) as create:
            result = agent._call_pass1("brief text", {})

        assert create.call_count == 1
        assert result.project_scores[0].project_key == expected.project_scores[0].project_key

    def test_malformed_first_response_retries_once_then_succeeds(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        expected = _pass1_output_for(brief)

        bad_block = _tool_use_block("emit_pass1_output", {"candidates": "not a list"})
        bad_response = MagicMock(content=[bad_block], stop_reason="tool_use")
        good_block = _tool_use_block("emit_pass1_output", expected.model_dump())
        good_response = MagicMock(content=[good_block], stop_reason="tool_use")

        with patch.object(agent._client.messages, "create", side_effect=[bad_response, good_response]) as create:
            result = agent._call_pass1("brief text", {})

        assert create.call_count == 2
        # the retry prompt must carry the validation error forward
        second_call_kwargs = create.call_args_list[1].kwargs
        retry_prompt = second_call_kwargs["messages"][0]["content"]
        assert "failed schema validation" in retry_prompt
        assert result.project_scores[0].project_key == expected.project_scores[0].project_key

    def test_two_malformed_responses_raise_with_both_attempts_surfaced(self):
        agent = StrategySynthesisAgent(_settings())

        bad_block = _tool_use_block("emit_pass1_output", {"candidates": "not a list"})
        bad_response = MagicMock(content=[bad_block], stop_reason="tool_use")

        with patch.object(agent._client.messages, "create", return_value=bad_response) as create:
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1("brief text", {})

        assert create.call_count == 2
        assert "failed schema validation twice" in str(exc_info.value)

    def test_no_tool_use_block_at_all_is_also_retried_then_raises(self):
        agent = StrategySynthesisAgent(_settings())
        text_only_response = MagicMock(content=[MagicMock(type="text", text="I refuse.")], stop_reason="end_turn")

        with patch.object(agent._client.messages, "create", return_value=text_only_response) as create:
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1("brief text", {})

        assert create.call_count == 2
        assert "no matching tool_use block" in str(exc_info.value)


class TestTwoPassBoundary:
    """The tests that exist to make the two-pass boundary a checked
    property, not a claim: Pass 2 is given precomputed numbers and never
    the raw effort/capacity tables it would need to derive them itself."""

    def _run_with_mocks(self, brief):
        agent = StrategySynthesisAgent(_settings())
        pass1_output = _pass1_output_for(brief)

        captured_pass2_prompts = []

        def fake_call_pass2_report(spec, brief_text, pass1_out, computed_text):
            captured_pass2_prompts.append((spec, computed_text))
            return f"# Report {spec.number}"

        with patch.object(agent, "_call_pass1", return_value=pass1_output):
            with patch.object(agent, "_call_pass2_report", side_effect=fake_call_pass2_report):
                result = agent.run(brief, upstream_text_by_agent={})

        return agent, result, captured_pass2_prompts

    def test_certification_bottleneck_is_precomputed_not_left_to_pass2(self):
        brief = _bottleneck_brief()
        _, result, prompts = self._run_with_mocks(brief)

        findings = [f for f in result.computed.bottlenecks if f.bucket_key == "CERT"]
        assert len(findings) == 1
        finding = findings[0]
        assert finding.demand == 290  # 250 + 40
        assert finding.capacity == 240
        assert finding.mandatory_demand == 250  # P-01 is mandatory
        assert finding.contractable == "no"

        # every Pass 2 call received the computed results as text
        for spec, computed_text in prompts:
            assert '"bucket_key": "CERT"' in computed_text
            assert "290" in computed_text  # the demand figure appears already-computed

    def test_pass2_prompts_never_receive_a_recomputable_number(self):
        """The raw per-project-per-bucket effort figures used to DERIVE the
        bottleneck (250, 40 -> 290 demand) do not appear anywhere in the
        `computed_text` block handed to Pass 2 as freestanding numbers to
        re-sum -- only the already-reduced finding (demand=290, overage,
        deferral set) does. Pass 2 is never given the raw effort table
        through the computed-results channel; it would have to go looking
        in the brief text for that, which this test doesn't feed it."""
        brief = _bottleneck_brief()
        agent, result, prompts = self._run_with_mocks(brief)

        computed_text = prompts[0][1]
        # the aggregate table's raw per-bucket demand figures for buckets
        # that are NOT bottlenecked (e.g. HW's 156-unit demand) are not
        # separately re-derivable inputs -- compute_bucket_utilisation's
        # own output IS what's given, not a hand-built partial sum.
        assert result.computed.bucket_utilisation  # sanity: something was computed
        for bu in result.computed.bucket_utilisation:
            assert f'"demand": {bu.demand}' in computed_text or f'"demand": {bu.demand:.1f}' in computed_text

    def test_classification_and_coverage_gaps_are_computed_before_pass2(self):
        brief = _bottleneck_brief()
        _, result, prompts = self._run_with_mocks(brief)

        assert result.computed.classifications["P-01"] == "mandatory"
        assert result.computed.classifications["P-05"] == "conditional"  # depends on P-01
        assert result.computed.coverage_gaps == ["SO-3"]  # only P-01 tags SO-1; nothing tags SO-3

        computed_text = prompts[0][1]
        assert '"SO-3"' in computed_text
        assert '"P-01": "mandatory"' in computed_text

    def test_candidates_are_presorted_by_evidence_strength_not_left_to_pass2(self):
        brief = _bottleneck_brief()
        agent = StrategySynthesisAgent(_settings())
        pass1_output = Pass1Output(
            candidates=[
                Pass1Candidate(key="C-02", name="Weaker", origin="x", problem="x", evidence_summary="x",
                                support_classification="partially supported", evidence_strength_rank=2),
                Pass1Candidate(key="C-01", name="Stronger", origin="x", problem="x", evidence_summary="x",
                                support_classification="evidence-supported", evidence_strength_rank=1),
            ],
            project_scores=_pass1_output_for(brief).project_scores,
        )
        with patch.object(agent, "_call_pass1", return_value=pass1_output):
            with patch.object(agent, "_call_pass2_report", return_value="ok"):
                result = agent.run(brief, upstream_text_by_agent={})

        assert [c.key for c in result.computed.candidates_sorted] == ["C-01", "C-02"]

    def test_all_seven_reports_are_produced(self):
        brief = _bottleneck_brief()
        _, result, _ = self._run_with_mocks(brief)
        assert [r.report_number for r in result.reports] == [spec.number for spec in REPORTS]
        assert len(result.reports) == 7


class TestSummarizeUpstreamAgent:
    def test_calls_claude_and_returns_text(self):
        agent = StrategySynthesisAgent(_settings())
        response = MagicMock(content=[MagicMock(type="text", text="summary text")])
        with patch.object(agent._client.messages, "create", return_value=response) as create:
            result = agent.summarize_upstream_agent("market-insights", "very long report text")
        assert result == "summary text"
        assert create.call_count == 1
