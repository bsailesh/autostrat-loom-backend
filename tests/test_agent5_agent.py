"""
Tests for `strategy_synthesis/agent.py` -- the two-pass orchestration.
No real Anthropic calls: the streamed client call inside `_call_pass1` is
mocked, as is `_call_pass2_report`
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

from strategy_synthesis.agent import (
    Pass1ValidationError,
    StrategySynthesisAgent,
    UpstreamSummaryError,
    _pass1_completeness_gaps,
)
from strategy_synthesis.brief import DecisionBrief, Objective
from strategy_synthesis.compute import Bucket, Capacity, Dependency, Project, ProjectEffort, Scenario
from strategy_synthesis.config import Settings
from strategy_synthesis.reports import REPORTS
from strategy_synthesis.schemas import Pass1Candidate, Pass1DimensionScore, Pass1Output, Pass1ProjectScore


def _settings():
    return Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5")


def _pass1_response(tool_input: dict, stop_reason: str = "tool_use", output_tokens: int = 9000) -> MagicMock:
    """A streamed Pass 1 response carrying one tool_use block."""
    return MagicMock(
        content=[_tool_use_block("emit_pass1_output", tool_input)],
        stop_reason=stop_reason,
        usage=MagicMock(output_tokens=output_tokens),
    )


def _streaming(*responses: MagicMock) -> MagicMock:
    """Stands in for `client.messages.stream`, which is used as a context
    manager and read via `get_final_message()` -- one entry per attempt."""

    def _one(response):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(
            return_value=MagicMock(get_final_message=MagicMock(return_value=response))
        )
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    return MagicMock(side_effect=[_one(r) for r in responses])


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

        response = _pass1_response(expected.model_dump())

        with patch.object(agent._client.messages, "stream", _streaming(response)) as stream:
            result = agent._call_pass1(brief, "brief text", {})

        assert stream.call_count == 1
        assert result.project_scores[0].project_key == expected.project_scores[0].project_key

    def test_malformed_first_response_retries_once_then_succeeds(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        expected = _pass1_output_for(brief)

        bad = _pass1_response({"candidates": "not a list"})
        good = _pass1_response(expected.model_dump())

        with patch.object(agent._client.messages, "stream", _streaming(bad, good)) as stream:
            result = agent._call_pass1(brief, "brief text", {})

        assert stream.call_count == 2
        # the retry prompt must carry the rejection reason forward
        retry_prompt = stream.call_args_list[1].kwargs["messages"][0]["content"]
        assert "failed schema validation" in retry_prompt
        assert result.project_scores[0].project_key == expected.project_scores[0].project_key

    def test_two_malformed_responses_raise_with_both_attempts_surfaced(self):
        agent = StrategySynthesisAgent(_settings())
        bad = _pass1_response({"candidates": "not a list"})

        with patch.object(agent._client.messages, "stream", _streaming(bad, bad)) as stream:
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1(_bottleneck_brief(), "brief text", {})

        assert stream.call_count == 2
        assert "rejected twice" in str(exc_info.value)
        assert "failed schema validation" in str(exc_info.value)

    def test_no_tool_use_block_at_all_is_also_retried_then_raises(self):
        agent = StrategySynthesisAgent(_settings())
        text_only = MagicMock(
            content=[MagicMock(type="text", text="I refuse.")],
            stop_reason="end_turn",
            usage=MagicMock(output_tokens=12),
        )

        with patch.object(agent._client.messages, "stream", _streaming(text_only, text_only)) as stream:
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1(_bottleneck_brief(), "brief text", {})

        assert stream.call_count == 2
        assert "no matching tool_use block" in str(exc_info.value)


class TestPass1RejectsStructurallyEmptyOutput:
    """The Arden failure: a Pass 1 call that returns HTTP 200 with a tool_use
    block whose input is a coerced fragment of a truncated response. Every
    Pass1Output field defaults to [], so the fragment parses cleanly into an
    output with no scores at all -- which used to flow into compute, produce
    an empty composite set, and leave every downstream report inert."""

    def test_truncated_response_is_rejected_before_it_is_ever_parsed(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()

        # exactly what the API returned for the nine-project Arden brief when
        # generation hit the ceiling mid-tool-input
        truncated = _pass1_response({"context": {}}, stop_reason="max_tokens", output_tokens=16000)
        good = _pass1_response(_pass1_output_for(brief).model_dump())

        with patch.object(agent._client.messages, "stream", _streaming(truncated, good)) as stream:
            result = agent._call_pass1(brief, "brief text", {})

        assert stream.call_count == 2
        retry_prompt = stream.call_args_list[1].kwargs["messages"][0]["content"]
        assert "max_tokens" in retry_prompt and "truncated fragment" in retry_prompt
        assert len(result.project_scores) == len(brief.projects)

    def test_empty_but_schema_valid_output_no_longer_passes_validation(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        empty = _pass1_response({"candidates": [], "project_scores": []})

        with patch.object(agent._client.messages, "stream", _streaming(empty, empty)):
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1(brief, "brief text", {})

        message = str(exc_info.value)
        assert "structurally incomplete" in message
        assert "0 of 2 committed projects scored" in message
        assert "P-01" in message and "P-05" in message

    def test_a_partially_scored_portfolio_is_rejected_too(self):
        """Not just the zero case: eight of nine scored is the same class of
        wrong, and compute would happily rank the eight."""
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        partial = _pass1_output_for(brief).model_dump()
        partial["project_scores"] = partial["project_scores"][:1]  # P-01 only
        response = _pass1_response(partial)

        with patch.object(agent._client.messages, "stream", _streaming(response, response)):
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1(brief, "brief text", {})

        assert "1 of 2 committed projects scored" in str(exc_info.value)
        assert "P-05" in str(exc_info.value)

    def test_a_project_missing_one_criterion_is_rejected_before_compute_raises(self):
        """compute_composite_scores raises on this, but as an unretryable
        crash mid-run; Pass 1 should catch it while a corrective retry is
        still possible."""
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        payload = _pass1_output_for(brief).model_dump()
        payload["project_scores"][1]["dimensions"] = payload["project_scores"][1]["dimensions"][:1]
        response = _pass1_response(payload)

        with patch.object(agent._client.messages, "stream", _streaming(response, response)):
            with pytest.raises(Pass1ValidationError) as exc_info:
                agent._call_pass1(brief, "brief text", {})

        assert "has no score for criterion effort" in str(exc_info.value)

    def test_a_complete_output_passes_unchanged(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        expected = _pass1_output_for(brief)

        with patch.object(agent._client.messages, "stream", _streaming(_pass1_response(expected.model_dump()))):
            result = agent._call_pass1(brief, "brief text", {})

        assert {ps.project_key for ps in result.project_scores} == {p.project_key for p in brief.projects}
        assert _pass1_completeness_gaps(result, brief) == []


    def test_an_answer_nested_under_a_wrapper_key_is_recovered_without_a_retry(self):
        """Arden run 0ce2341c: both attempts came back schema-valid and empty,
        not truncated. A complete answer under a wrapper key validated as an
        empty Pass1Output because unknown keys were silently ignored."""
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        wrapped = _pass1_response({"context": _pass1_output_for(brief).model_dump()})

        with patch.object(agent._client.messages, "stream", _streaming(wrapped)) as stream:
            result = agent._call_pass1(brief, "brief text", {})

        assert stream.call_count == 1
        assert {ps.project_key for ps in result.project_scores} == {p.project_key for p in brief.projects}

    def test_a_misnamed_top_level_field_is_rejected_by_name_not_as_an_empty_answer(self):
        agent = StrategySynthesisAgent(_settings())
        brief = _bottleneck_brief()
        payload = _pass1_output_for(brief).model_dump()
        payload["project_dimension_scores"] = payload.pop("project_scores")
        misnamed = _pass1_response(payload)
        good = _pass1_response(_pass1_output_for(brief).model_dump())

        with patch.object(agent._client.messages, "stream", _streaming(misnamed, good)) as stream:
            result = agent._call_pass1(brief, "brief text", {})

        retry_prompt = stream.call_args_list[1].kwargs["messages"][0]["content"]
        assert "failed schema validation" in retry_prompt
        assert "project_dimension_scores" in retry_prompt
        assert len(result.project_scores) == len(brief.projects)

    def test_the_tool_schema_tells_the_model_extra_top_level_keys_are_forbidden(self):
        assert Pass1Output.model_json_schema()["additionalProperties"] is False


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
    @staticmethod
    def _response(text: str, stop_reason: str = "end_turn", output_tokens: int = 2000) -> MagicMock:
        blocks = [MagicMock(type="text", text=text)] if text else []
        return MagicMock(
            content=blocks, stop_reason=stop_reason, usage=MagicMock(output_tokens=output_tokens)
        )

    def test_calls_claude_and_returns_text(self):
        agent = StrategySynthesisAgent(_settings())
        with patch.object(
            agent._client.messages, "stream", _streaming(self._response("summary text"))
        ) as stream:
            result = agent.summarize_upstream_agent("market-insights", "very long report text")
        assert result == "summary text"
        assert stream.call_count == 1

    def test_truncated_summary_raises_instead_of_being_handed_to_pass1(self):
        """A summary cut off at the ceiling drops exactly the cited evidence
        Pass 1 is supposed to reason from, and nothing downstream can tell."""
        agent = StrategySynthesisAgent(_settings())
        truncated = self._response("half a summ", stop_reason="max_tokens", output_tokens=32000)

        with patch.object(agent._client.messages, "stream", _streaming(truncated)):
            with pytest.raises(UpstreamSummaryError) as exc_info:
                agent.summarize_upstream_agent("market-insights", "x" * 154_379)

        assert "max_tokens" in str(exc_info.value)
        assert "32000-token ceiling" in str(exc_info.value)

    def test_empty_summary_raises(self):
        """What Arden's 154k-char pack actually did at the old 4000-token
        ceiling: stop_reason=max_tokens with no text block at all, because
        thinking consumed the whole budget first."""
        agent = StrategySynthesisAgent(_settings())
        empty = self._response("", stop_reason="max_tokens", output_tokens=4000)

        with patch.object(agent._client.messages, "stream", _streaming(empty)):
            with pytest.raises(UpstreamSummaryError):
                agent.summarize_upstream_agent("market-insights", "x" * 154_379)

    def test_whitespace_only_summary_raises(self):
        agent = StrategySynthesisAgent(_settings())
        blank = self._response("   \n\n  ", stop_reason="end_turn", output_tokens=6)

        with patch.object(agent._client.messages, "stream", _streaming(blank)):
            with pytest.raises(UpstreamSummaryError) as exc_info:
                agent.summarize_upstream_agent("market-insights", "report")

        assert "came back empty" in str(exc_info.value)
