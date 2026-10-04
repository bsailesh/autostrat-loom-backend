"""
Tests for `tech_regulation/agent.py` and `tech_regulation/validation.py`.

No real Anthropic calls: the streamed client call is mocked directly, the
same testability seam tests/test_agent5_agent.py uses.

The load-bearing class in this file is
`TestCandidateWorkCallAppliesThePass1Lessons`. The structured candidate-work
call is the same shape as Agent 5's Pass 1 -- one forced-tool-choice call
whose output everything downstream depends on -- and Pass 1 failed silently
on truncation, producing an empty but schema-valid payload that flowed into
compute and left nine reports narrating nothing (fixed in fff5b4a). Each of
the four fixes from that commit has a test here:

  1. streamed, with an adequate ceiling
  2. stop_reason == "max_tokens" rejected BEFORE parsing
  3. stop_reason and output tokens logged on every attempt
  4. completeness validated, not just schema
"""
import logging
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest

from tech_regulation.agent import (
    CANDIDATE_WORK_MAX_TOKENS,
    CandidateWorkError,
    TechRegulationAgent,
)
from tech_regulation.config import Settings
from tech_regulation.reports import REPORTS
from tech_regulation.schemas import CandidateWorkItem, CandidateWorkOutput
from tech_regulation.scoping import (
    CertificationBasis,
    Jurisdiction,
    Platform,
    ProductCategory,
    ScopingEnvelope,
    StandardHeld,
    Supplier,
    Exclusion,
)
from tech_regulation.validation import candidate_work_gaps, partition_candidate_work


def _settings():
    return Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5")


def _envelope() -> ScopingEnvelope:
    return ScopingEnvelope(
        categories=[ProductCategory("EMA-UTIL", "Utility actuation")],
        jurisdictions=[Jurisdiction("European Union", "primary")],
        certification_basis=[CertificationBasis("EMA-UTIL", "TSO", "TSO-C196b", "approved", "2019")],
        platforms=[Platform("Narrowbody commercial", "Part 25 transport", "pursuing", "design-in window")],
        standards_held=[StandardHeld("DO-160", "G", "Environmental qualification", "compliant")],
        suppliers=[Supplier("Vendor A", "GaN power devices", "single_source")],
        domains=["Electrification"],
        exclusions=[Exclusion("jurisdiction", "China", "no sales intent")],
    )


def _item(**overrides) -> dict:
    payload = {
        "candidate_key": "TR-01",
        "driver": "RTCA DO-160G Section 21 revision, published 11 Feb 2027, effective 14 Mar 2028",
        "work_date": "2028-03-14",
        "date_basis": "effective",
        "date_absent_reason": "",
        "applicability": {
            "categories": ["EMA-UTIL"],
            "certification_bases": ["TSO-C196b"],
            "platforms": [],
            "note": "Does not touch the defence lines, which qualify to MIL-STD-461G",
        },
        "work_implied": "requalification",
        "work_implied_description": "Requalification of affected articles against the revised section",
        "platform_relationship": None,
        "classification": "FACT",
        "confidence": "High",
        "source": "EUROCAE",
        "source_date": "2027-02-11",
    }
    payload.update(overrides)
    return payload


def _tool_use_block(tool_name: str, payload: dict) -> MagicMock:
    block = MagicMock(type="tool_use", input=payload)
    block.name = tool_name
    return block


def _response(payload: dict, stop_reason: str = "tool_use", output_tokens: int = 4000) -> MagicMock:
    return MagicMock(
        content=[_tool_use_block("emit_candidate_work", payload)],
        stop_reason=stop_reason,
        usage=MagicMock(output_tokens=output_tokens),
    )


def _streaming(*responses: MagicMock) -> MagicMock:
    """Stands in for `client.messages.stream`, used as a context manager and
    read via `get_final_message()` -- one entry per attempt."""

    def _one(response):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(
            return_value=MagicMock(get_final_message=MagicMock(return_value=response))
        )
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    return MagicMock(side_effect=[_one(r) for r in responses])


# ---------------------------------------------------------------------------
# The four Pass 1 lessons
# ---------------------------------------------------------------------------


class TestCandidateWorkCallAppliesThePass1Lessons:
    def test_1_the_call_is_streamed_with_an_adequate_ceiling(self):
        agent = TechRegulationAgent(_settings())
        with patch.object(
            agent._client.messages, "stream", _streaming(_response({"items": [_item()]}))
        ) as stream:
            with patch.object(agent._client.messages, "create") as create:
                kept, dropped = agent.extract_candidate_work(_envelope(), "brief")

        assert (kept, dropped) != ([], [])
        assert stream.call_count == 1
        # the structured call must stream, not fall back to messages.create
        assert create.call_count == 0
        assert stream.call_args.kwargs["max_tokens"] == CANDIDATE_WORK_MAX_TOKENS
        assert CANDIDATE_WORK_MAX_TOKENS >= 32000

    def test_2_truncation_is_rejected_before_the_payload_is_parsed(self):
        """The sharp version of this test: the truncated response carries a
        payload that WOULD parse and WOULD pass completeness. It must still be
        rejected, because a tool input cut off at the ceiling is a fragment of
        what the model was writing -- here, whatever items it had finished --
        and accepting it silently loses every item after the cut."""
        agent = TechRegulationAgent(_settings())
        truncated = _response(
            {"items": [_item()]}, stop_reason="max_tokens", output_tokens=CANDIDATE_WORK_MAX_TOKENS
        )
        good = _response({"items": [_item(), _item(candidate_key="TR-02")]})

        with patch.object(agent._client.messages, "stream", _streaming(truncated, good)) as stream:
            kept, dropped = agent.extract_candidate_work(_envelope(), "brief")

        assert stream.call_count == 2, "truncation must trigger the retry, not be accepted"
        retry_prompt = stream.call_args_list[1].kwargs["messages"][0]["content"]
        assert "max_tokens" in retry_prompt and "truncated fragment" in retry_prompt
        assert [i.candidate_key for i in kept] == ["TR-01", "TR-02"]
        assert dropped == []

    def test_2b_truncation_twice_fails_the_run(self):
        agent = TechRegulationAgent(_settings())
        truncated = _response({"items": [_item()]}, stop_reason="max_tokens", output_tokens=32000)

        with patch.object(agent._client.messages, "stream", _streaming(truncated, truncated)):
            with pytest.raises(CandidateWorkError) as exc_info:
                agent.extract_candidate_work(_envelope(), "brief")

        assert "unusable twice" in str(exc_info.value)
        assert "max_tokens" in str(exc_info.value)

    def test_3_stop_reason_and_output_tokens_are_logged_every_attempt(self, caplog):
        agent = TechRegulationAgent(_settings())
        truncated = _response({"items": []}, stop_reason="max_tokens", output_tokens=32000)
        good = _response({"items": [_item()]}, output_tokens=5123)

        with caplog.at_level(logging.INFO, logger="tech_regulation.agent"):
            with patch.object(agent._client.messages, "stream", _streaming(truncated, good)):
                agent.extract_candidate_work(_envelope(), "brief")

        logged = [r.getMessage() for r in caplog.records if "Candidate work attempt" in r.getMessage()]
        assert len(logged) == 2, logged
        assert "stop_reason=max_tokens" in logged[0] and "32000" in logged[0]
        assert "stop_reason=tool_use" in logged[1] and "5123" in logged[1]

    def test_4_completeness_is_validated_not_just_schema(self):
        """Schema-valid but not ready to emit: no driver. Dropped with a
        reason rather than passed downstream as a candidate with no cause."""
        agent = TechRegulationAgent(_settings())
        bad = _response({"items": [_item(driver="")]})

        with patch.object(agent._client.messages, "stream", _streaming(bad, bad)):
            kept, dropped = agent.extract_candidate_work(_envelope(), "brief")

        assert kept == []
        assert len(dropped) == 1
        key, gaps = dropped[0]
        assert key == "TR-01"
        assert any("driver is empty" in g for g in gaps)

    def test_the_fragment_that_defeated_pass1_fails_schema_validation_here(self):
        """`{"context": {}}` is what the API returned for Agent 5's truncated
        Pass 1 call. Every Pass1Output field defaulted to [], so it validated
        into an empty output. CandidateWorkOutput.items has no default, so the
        same fragment is a schema failure -- the stop_reason check is the first
        line of defence and this is the second."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CandidateWorkOutput.model_validate({"context": {}})
        with pytest.raises(ValidationError):
            CandidateWorkOutput.model_validate({})


# ---------------------------------------------------------------------------
# Where this agent's completeness rules differ from Pass 1's
# ---------------------------------------------------------------------------


class TestEmptyIsLegitimateHere:
    def test_an_empty_item_list_is_accepted(self):
        """Unlike Agent 5's Pass 1, there is no denominator: the brief does not
        name which candidate work must exist. A run that genuinely surfaces
        none is a legitimate outcome, and padding to fill a quota is the
        failure mode."""
        agent = TechRegulationAgent(_settings())
        with patch.object(agent._client.messages, "stream", _streaming(_response({"items": []}))) as stream:
            kept, dropped = agent.extract_candidate_work(_envelope(), "brief")

        assert stream.call_count == 1, "an empty list is valid and must not trigger a retry"
        assert kept == []
        assert dropped == []

    def test_one_bad_item_does_not_discard_the_good_ones(self):
        agent = TechRegulationAgent(_settings())
        mixed = _response({"items": [_item(), _item(candidate_key="TR-02", work_implied="")]})

        with patch.object(agent._client.messages, "stream", _streaming(mixed, mixed)) as stream:
            kept, dropped = agent.extract_candidate_work(_envelope(), "brief")

        assert stream.call_count == 2, "incomplete items get one corrective retry"
        assert [i.candidate_key for i in kept] == ["TR-01"]
        assert [key for key, _ in dropped] == ["TR-02"]

    def test_a_retry_that_fixes_the_item_keeps_it(self):
        agent = TechRegulationAgent(_settings())
        bad = _response({"items": [_item(candidate_key="TR-02", work_implied="")]})
        fixed = _response({"items": [_item(candidate_key="TR-02")]})

        with patch.object(agent._client.messages, "stream", _streaming(bad, fixed)):
            kept, dropped = agent.extract_candidate_work(_envelope(), "brief")

        assert [i.candidate_key for i in kept] == ["TR-02"]
        assert dropped == []


# ---------------------------------------------------------------------------
# Per-item completeness rules
# ---------------------------------------------------------------------------


class TestCandidateWorkGaps:
    def _parse(self, **overrides) -> CandidateWorkItem:
        return CandidateWorkItem.model_validate(_item(**overrides))

    def test_a_complete_item_has_no_gaps(self):
        assert candidate_work_gaps(self._parse()) == []

    def test_a_null_date_without_a_reason_is_rejected(self):
        gaps = candidate_work_gaps(
            self._parse(work_date=None, date_basis="none_established", date_absent_reason="")
        )
        assert any("honest absence" in g for g in gaps)

    def test_a_null_date_with_a_reason_is_accepted(self):
        """An undated candidate is standing context downstream, which is
        correct -- so long as the absence is stated."""
        gaps = candidate_work_gaps(
            self._parse(
                work_date=None,
                date_basis="none_established",
                date_absent_reason="EASA has called for the requirement; no standard published",
            )
        )
        assert gaps == []

    def test_a_null_date_with_a_dated_basis_is_rejected(self):
        gaps = candidate_work_gaps(
            self._parse(work_date=None, date_basis="effective", date_absent_reason="none exists")
        )
        assert any("expected 'none_established'" in g for g in gaps)

    def test_a_date_with_a_none_established_basis_is_rejected(self):
        gaps = candidate_work_gaps(self._parse(date_basis="none_established"))
        assert any("but work_date carries a date" in g for g in gaps)

    def test_applicability_touching_nothing_is_rejected(self):
        gaps = candidate_work_gaps(
            self._parse(applicability={"categories": [], "certification_bases": [], "platforms": []})
        )
        assert any("touches nothing in the envelope" in g for g in gaps)

    def test_an_unknown_work_implied_kind_is_rejected(self):
        gaps = candidate_work_gaps(self._parse(work_implied="think about it"))
        assert any("is not one of" in g for g in gaps)

    def test_work_implied_other_requires_a_description(self):
        gaps = candidate_work_gaps(self._parse(work_implied="other", work_implied_description=""))
        assert any("requires work_implied_description" in g for g in gaps)

    def test_an_unknown_classification_or_confidence_is_rejected(self):
        assert any("classification" in g for g in candidate_work_gaps(self._parse(classification="PROBABLY")))
        assert any("confidence" in g for g in candidate_work_gaps(self._parse(confidence="quite sure")))

    def test_sized_work_is_rejected_even_though_no_field_asks_for_it(self):
        """The schema has no effort field, so sizing can only leak through
        prose. This is the one place it still can."""
        gaps = candidate_work_gaps(
            self._parse(work_implied_description="Requalification, roughly 6 man-months of effort")
        )
        assert any("sizes or ranks the work" in g for g in gaps)

    def test_ranked_work_is_rejected(self):
        gaps = candidate_work_gaps(
            self._parse(work_implied_description="The most urgent regulatory exposure in the portfolio")
        )
        assert any("sizes or ranks the work" in g for g in gaps)

    def test_a_duplicate_key_within_one_payload_is_dropped_not_overwritten(self):
        """Persistence is keyed by candidate_key, so two items claiming one key
        would collapse into a single row carrying whichever evidence landed
        last."""
        output = CandidateWorkOutput.model_validate({"items": [_item(), _item()]})
        kept, dropped = partition_candidate_work(output)
        assert [i.candidate_key for i in kept] == ["TR-01"]
        assert any("duplicate candidate_key" in g for _, gaps in dropped for g in gaps)

    def test_platform_relationship_is_validated_when_present(self):
        assert candidate_work_gaps(self._parse(platform_relationship="pursuing")) == []
        assert any(
            "platform_relationship" in g
            for g in candidate_work_gaps(self._parse(platform_relationship="maybe"))
        )


# ---------------------------------------------------------------------------
# Structure first, narration second
# ---------------------------------------------------------------------------


class TestCandidateWorkIsGeneratedBeforeItIsNarrated:
    def test_reports_receive_the_validated_payload_and_are_told_not_to_re_derive_it(self):
        """The property that makes the Agent 5 integration parse-free:
        candidate work is a validated object before any report prose exists,
        and the reports narrate it rather than producing it."""
        agent = TechRegulationAgent(_settings())
        envelope = _envelope()
        captured: list[str] = []

        def fake_research(env, **kwargs):
            return ("RESEARCH BRIEF — evidence rows", [], [])

        def fake_synthesize(spec, title, envelope_text, brief, candidate_work, state_line):
            from tech_regulation.agent import Report
            from tech_regulation.prompts import synthesis_user_prompt

            captured.append(
                synthesis_user_prompt(spec, envelope_text, brief, candidate_work, state_line, title)
            )
            return Report(spec.number, title, f"# body {spec.number}", "")

        with patch.object(agent, "research", side_effect=fake_research):
            with patch.object(
                agent,
                "extract_candidate_work",
                return_value=([CandidateWorkItem.model_validate(_item())], []),
            ):
                with patch.object(agent, "_synthesize_one", side_effect=fake_synthesize):
                    result = agent.run(envelope)

        assert len(captured) == len(REPORTS)
        for prompt in captured:
            assert "TR-01" in prompt
            assert "2028-03-14" in prompt
            assert "narrate, do not re-derive" in prompt
        assert [r.report_number for r in result.reports] == [s.number for s in REPORTS]
        assert [i.candidate_key for i in result.candidate_work] == ["TR-01"]

    def test_report_1_carries_the_deferred_reports_note(self):
        from tech_regulation.prompts import synthesis_user_prompt

        spec_1 = next(s for s in REPORTS if s.number == 1)
        spec_2 = next(s for s in REPORTS if s.number == 2)
        args = ("envelope", "brief", [CandidateWorkItem.model_validate(_item())], "state line", "T")

        assert "Report 9" in synthesis_user_prompt(spec_1, *args)
        assert "Report 10" in synthesis_user_prompt(spec_1, *args)
        assert "Report 9" not in synthesis_user_prompt(spec_2, *args)

    def test_nine_reports_with_9_and_10_absent_and_11_keeping_its_number(self):
        numbers = [s.number for s in REPORTS]
        assert numbers == [1, 2, 3, 4, 5, 6, 7, 8, 11]

    def test_unscoped_runs_prefix_every_report_title(self):
        agent = TechRegulationAgent(_settings())
        with patch.object(agent, "research", return_value=("brief", [], [])):
            with patch.object(agent, "extract_candidate_work", return_value=([], [])):
                with patch.object(
                    agent,
                    "_synthesize_one",
                    side_effect=lambda spec, title, *a: __import__(
                        "tech_regulation.agent", fromlist=["Report"]
                    ).Report(spec.number, title, "body", ""),
                ):
                    result = agent.run(ScopingEnvelope())

        assert result.operating_state == "unscoped"
        assert all(r.title.startswith("UNSCOPED INDUSTRY SURVEY") for r in result.reports)
        assert "industry survey" in result.operating_state_line
