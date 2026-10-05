"""
Tests for voice_of_customer/agent.py, attribution.py and the prompt
contract. No real Anthropic calls: research (`messages.create`) and the
per-report streamed call (`messages.stream`) are mocked directly, the same
seam tests/test_tech_regulation_agent.py uses.

Belief testing and the Tier 2 "unavailable rather than thin" rule are model
behaviour. What can be tested deterministically is that the contract the
model is given carries every outcome and every rule, and that Report 1 is
rejected if it comes back without the sections other parts of the platform
depend on -- which is what the classes below do.
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest

from voice_of_customer import prompts, standards
from voice_of_customer.agent import ReportStructureError, VoiceOfCustomerAgent
from voice_of_customer.attribution import apply_attribution_check, build_name_list
from voice_of_customer.config import Settings
from voice_of_customer.context import (
    Customer,
    CustomerContext,
    EvidenceFile,
    KnownPainPoint,
    Segment,
)
from voice_of_customer.reports import (
    BELIEF_TESTING_HEADING,
    DEFERRED_REPORTS_NOTE,
    FINDINGS_FOR_SYNTHESIS_HEADING,
    REPORTS,
)

CUSTOMER = "Northwind Defence"


def _settings():
    return Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5")


def _context(evidence=(), policy="segment_only") -> CustomerContext:
    return CustomerContext(
        segments=[Segment("OEM-PRIME", "Prime contractors", "", 6)],
        customers=[Customer(CUSTOMER, "OEM-PRIME")],
        known_pain_points=[KnownPainPoint("Primes say our lead times are the longest", "OEM-PRIME")],
        attribution_policy=policy,
        evidence=list(evidence),
    )


def _evidence_file():
    return EvidenceFile(file_id="f1", file_type="support_tickets", file_format="csv", filename="t.csv", row_count=10)


GOOD_REPORT_1 = f"""**Operating tier: ...**

## Governing Insight
Situation. Complication. Question. Answer.

{BELIEF_TESTING_HEADING}
| Belief | Segment | Outcome | Evidence | Confidence |
|---|---|---|---|---|
| Lead times | OEM-PRIME | Contradicted | {CUSTOMER} raised integration effort, not lead time | Low |

{FINDINGS_FOR_SYNTHESIS_HEADING}
{CUSTOMER} is the only source for the integration finding.

## Recommended actions
None the evidence supports.
"""


def _text_message(text: str, stop_reason: str = "end_turn") -> MagicMock:
    block = MagicMock(type="text", text=text, citations=None)
    return MagicMock(content=[block], stop_reason=stop_reason, usage=MagicMock(output_tokens=100))


def _stream_ctx(message: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=MagicMock(get_final_message=MagicMock(return_value=message)))
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _run(agent, context, report_texts, *, names=None, only=None):
    """report_texts: list of texts returned by successive stream calls."""
    stream = MagicMock(side_effect=[_stream_ctx(_text_message(t)) for t in report_texts])
    create = MagicMock(return_value=_text_message("public evidence rows"))
    with patch.object(agent._client.messages, "stream", stream), patch.object(
        agent._client.messages, "create", create
    ):
        result = agent.run(
            context,
            "evidence text",
            name_entries=names if names is not None else build_name_list(context.customers, context.segments),
            research_rounds=1,
            only_reports=only,
        )
    return result, stream, create


class TestNineReports:
    def test_nine_reports_and_report_6_deferred(self):
        assert [r.number for r in REPORTS] == [1, 2, 3, 4, 5, 7, 8, 9, 10]
        assert "Report 6" in DEFERRED_REPORTS_NOTE
        report1_instruction = prompts.synthesis_report_instruction(REPORTS[0], "Executive summary")
        assert DEFERRED_REPORTS_NOTE in report1_instruction

    def test_one_streamed_call_per_report(self):
        agent = VoiceOfCustomerAgent(_settings())
        texts = [GOOD_REPORT_1] + [f"body {n}" for n in range(2, 10)]
        result, stream, _ = _run(agent, _context(), texts)
        assert stream.call_count == 9
        assert [r.report_number for r in result.reports] == [1, 2, 3, 4, 5, 7, 8, 9, 10]


class TestTier2Run:
    def test_titled_external_customer_context_analysis(self):
        agent = VoiceOfCustomerAgent(_settings())
        result, _, _ = _run(agent, _context(), [GOOD_REPORT_1, "b"], only=[1, 2])
        assert result.operating_tier == "tier_2"
        for r in result.reports:
            assert r.title.startswith("External customer-context analysis — ")
        assert result.operating_tier_line.startswith("**Operating tier: TIER 2")

    def test_tier_1_run_is_not_titled_external(self):
        agent = VoiceOfCustomerAgent(_settings())
        result, _, _ = _run(agent, _context(evidence=[_evidence_file()]), [GOOD_REPORT_1], only=[1])
        assert result.reports[0].title == "Executive summary"

    def test_tier_line_is_in_every_report_prompt(self):
        agent = VoiceOfCustomerAgent(_settings())
        _, stream, _ = _run(agent, _context(), [GOOD_REPORT_1, "b"], only=[1, 2])
        for call in stream.call_args_list:
            shared = call.kwargs["messages"][0]["content"][0]["text"]
            assert "Operating tier: TIER 2" in shared


class TestFindingsForSynthesis:
    @pytest.mark.parametrize("evidence", [(), (_evidence_file(),)], ids=["tier2", "tier1"])
    def test_report_1_missing_findings_is_retried_then_fails(self, evidence):
        agent = VoiceOfCustomerAgent(_settings())
        no_findings = GOOD_REPORT_1.replace(FINDINGS_FOR_SYNTHESIS_HEADING, "## Other")
        with pytest.raises(ReportStructureError, match="Findings for synthesis"):
            _run(agent, _context(evidence), [no_findings, no_findings], only=[1])

    @pytest.mark.parametrize("evidence", [(), (_evidence_file(),)], ids=["tier2", "tier1"])
    def test_retry_names_the_missing_heading_and_recovers(self, evidence):
        agent = VoiceOfCustomerAgent(_settings())
        no_findings = GOOD_REPORT_1.replace(FINDINGS_FOR_SYNTHESIS_HEADING, "## Other")
        result, stream, _ = _run(agent, _context(evidence), [no_findings, GOOD_REPORT_1], only=[1])
        retry_text = stream.call_args_list[1].kwargs["messages"][0]["content"][1]["text"]
        assert FINDINGS_FOR_SYNTHESIS_HEADING in retry_text
        assert FINDINGS_FOR_SYNTHESIS_HEADING in result.reports[0].content

    def test_contract_requires_the_section_even_at_tier_2(self):
        assert "the section still appears" in standards.FINDINGS_FOR_SYNTHESIS
        assert FINDINGS_FOR_SYNTHESIS_HEADING in REPORTS[0].must_include
        assert "including Tier 2" in REPORTS[0].must_include


class TestBeliefTestingContract:
    def test_all_outcomes_and_both_not_found_causes_are_specified(self):
        text = standards.BELIEF_TESTING
        assert "**Corroborated**" in text
        assert "**Contradicted**" in text
        assert "Not found — no evidence supplied that could test it" in text
        assert "Not found — absent from the evidence supplied" in text
        for outcome in ("Corroborated", "Contradicted", "no evidence supplied", "absent from the evidence"):
            assert outcome in REPORTS[0].must_include

    def test_report_1_missing_belief_section_is_rejected(self):
        agent = VoiceOfCustomerAgent(_settings())
        bad = GOOD_REPORT_1.replace(BELIEF_TESTING_HEADING, "## Something else")
        with pytest.raises(ReportStructureError, match="Testing your stated beliefs"):
            _run(agent, _context(), [bad, bad], only=[1])


class TestAttribution:
    def test_segment_only_produces_no_customer_names(self):
        agent = VoiceOfCustomerAgent(_settings())
        report2 = f"{CUSTOMER.upper()} and {CUSTOMER}'s programme both report this."
        result, _, _ = _run(agent, _context(), [GOOD_REPORT_1, report2], only=[1, 2])
        for r in result.reports:
            assert CUSTOMER.lower() not in r.content.lower(), r.report_number
        assert "[customer in segment: Prime contractors]" in result.reports[1].content
        assert result.attribution_replacements == {1: 2, 2: 2}

    def test_note_says_it_is_a_check_not_a_guarantee(self):
        agent = VoiceOfCustomerAgent(_settings())
        result, _, _ = _run(agent, _context(), [GOOD_REPORT_1], only=[1])
        content = result.reports[0].content
        assert "## Attribution check" in content
        assert "This is a check, not a guarantee." in content
        assert "2 occurrence(s) were replaced" in content

    def test_named_policy_leaves_names(self):
        agent = VoiceOfCustomerAgent(_settings())
        result, _, _ = _run(agent, _context(policy="named"), [GOOD_REPORT_1], only=[1])
        assert CUSTOMER in result.reports[0].content
        assert "no output check was applied" in result.reports[0].content

    def test_no_names_known_is_stated(self):
        agent = VoiceOfCustomerAgent(_settings())
        result, _, _ = _run(agent, _context(), [GOOD_REPORT_1], names=[], only=[1])
        assert "nothing to check" in result.reports[0].content

    def test_names_reach_the_model_in_synthesis(self):
        """Not stripped before the model: it must see that documents concern
        the same customer to identify a single-source finding."""
        agent = VoiceOfCustomerAgent(_settings())
        _, stream, _ = _run(agent, _context(), [GOOD_REPORT_1], only=[1])
        shared = stream.call_args.kwargs["messages"][0]["content"][0]["text"]
        assert CUSTOMER in shared

    def test_names_never_reach_web_search(self):
        agent = VoiceOfCustomerAgent(_settings())
        _, _, create = _run(agent, _context(), [GOOD_REPORT_1], only=[1])
        sent = str(create.call_args.kwargs["messages"])
        assert CUSTOMER not in sent

    def test_short_names_match_case_sensitively(self):
        entries = build_name_list([Customer("GE", "")], [])
        text, n = apply_attribution_check("GE said the gear was good", entries, "segment_only")
        assert n == 1 and "gear" in text

    def test_longest_name_replaced_first(self):
        entries = build_name_list([Customer("Acme", ""), Customer("Acme Aerospace", "")], [])
        text, n = apply_attribution_check("Acme Aerospace and Acme", entries, "segment_only")
        assert n == 2 and "Acme" not in text


class TestCaching:
    def test_shared_block_is_the_cached_prefix_and_identical_across_reports(self):
        agent = VoiceOfCustomerAgent(_settings())
        _, stream, _ = _run(agent, _context(), [GOOD_REPORT_1, "b", "c"], only=[1, 2, 3])
        shared = [c.kwargs["messages"][0]["content"][0] for c in stream.call_args_list]
        assert all(s["cache_control"] == {"type": "ephemeral"} for s in shared)
        assert len({s["text"] for s in shared}) == 1


class TestNoCandidateWork:
    def test_effort_is_labelled_estimated_and_not_comparable(self):
        r5 = next(r for r in REPORTS if r.number == 5)
        assert "NOT comparable to the effort figures in the customer's roadmap" in r5.must_include
        assert "No candidate work" in standards.WHAT_AGENT_5_MUST_NOT_RECEIVE
