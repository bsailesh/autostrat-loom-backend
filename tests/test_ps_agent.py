"""
Candidate work for Agent 4: schema, per-item validation, the merge with
computed numbers, and the structured call applying every Pass 1 lesson.
No real Anthropic calls -- the client is mocked at the same seam
tests/test_tech_regulation_agent.py uses.
"""
import logging
import os
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest
from pydantic import ValidationError

from product_sustainment.agent import (
    CANDIDATE_WORK_MAX_TOKENS,
    CandidateWorkError,
    ProductSustainmentAgent,
    unwrap_candidate_work_input,
)
from product_sustainment.compute import InventoryRow, compute_sustainment
from product_sustainment.config import Settings
from product_sustainment.reports import REPORTS
from product_sustainment.schemas import ModelCandidateWorkOutput
from product_sustainment.structure import (
    EXPOSURE_SCAN,
    Level1Info,
    Level2Info,
    LruInfo,
    QualifiedAlternate,
    RiskRecord,
    SustainmentData,
    compute_inputs,
    operating_tier,
    readiness_items,
    report_title,
)
from product_sustainment.validation import merge_and_partition

TODAY = date(2027, 1, 15)


def _data(**over) -> SustainmentData:
    base = dict(
        lrus=[LruInfo("AR-FIN", "Fin actuator", "Missile", "P-1"), LruInfo("AR-TVC", "TVC actuator", "Launch", "P-2"),
              LruInfo("AR-UTIL", "Utility actuator", "Aero", "P-3")],
        level1=[Level1Info("CCA-MC"), Level1Info("CCA-PWR"), Level1Info("CCA-SENS")],
        level2=[Level2Info("GaN-650", "GaN device", manufacturer="Infineon"), Level2Info("FPGA-A"), Level2Info("RES-PREC")],
        lru_l1={"AR-FIN": {"CCA-MC": 1, "CCA-PWR": 1, "CCA-SENS": 1}, "AR-TVC": {"CCA-MC": 1, "CCA-PWR": 2},
                "AR-UTIL": {"CCA-MC": 1, "CCA-SENS": 1}},
        l1_l2={"CCA-MC": {"FPGA-A": 1, "RES-PREC": 12}, "CCA-PWR": {"GaN-650": 6, "RES-PREC": 8},
               "CCA-SENS": {"FPGA-A": 1, "RES-PREC": 4}},
        lru_demand={"AR-FIN": {2027: 120, 2028: 120}, "AR-TVC": {2027: 120, 2028: 120}},
        inventory=[InventoryRow("GaN-650", "level2", "Plant A", "raw", 1000)],
        inventory_as_of=["2027-01-01"],
        risks=[RiskRecord("GaN-650", "end_of_life", source="Infineon PCN 2026-117", lifecycle_status="NFND",
                          last_time_buy_date="2027-09-30"),
               RiskRecord("FPGA-A", "single_source", source="Customer supplier register")],
        demand_supplied=True,
        inventory_supplied=True,
    )
    base.update(over)
    return SustainmentData(**base)


def _item(**over) -> dict:
    payload = {
        "part_id": "GaN-650",
        "driver": "GaN-650 end of life, Infineon PCN 2026-117",
        "work_implied": "last_time_buy",
        "work_implied_description": "A last-time-buy, a qualification of a candidate, or a redesign are open.",
        "candidate_alternates": [{
            "part_number": "IGT65R025D2", "manufacturer": "Infineon", "basis": "manufacturer_replacement",
            "evidence": "Named in the PCN as the recommended replacement.",
            "limits": "Package differs; has not been environmentally qualified for this application.",
            "source": "Infineon PCN 2026-117", "source_date": "2026-10-01",
        }],
        "classification": "FACT",
        "confidence": "High",
        "source": "Infineon PCN 2026-117",
        "source_date": "2026-10-01",
    }
    payload.update(over)
    return payload


def _merge(items, data=None):
    data = data or _data()
    result = compute_sustainment(compute_inputs(data, TODAY))
    return merge_and_partition(ModelCandidateWorkOutput.model_validate({"items": items}), result, data)


class TestSchema:
    def test_items_has_no_default(self):
        with pytest.raises(ValidationError):
            ModelCandidateWorkOutput.model_validate({})

    def test_a_misnamed_field_fails_by_name(self):
        with pytest.raises(ValidationError, match="quantity_required"):
            ModelCandidateWorkOutput.model_validate({"items": [_item(quantity_required=500)]})

    def test_tool_schema_forbids_extra_properties(self):
        schema = ModelCandidateWorkOutput.model_json_schema()
        assert schema["additionalProperties"] is False
        assert all(d.get("additionalProperties") is False for d in schema["$defs"].values())

    def test_the_model_has_no_field_for_numbers(self):
        fields = set(ModelCandidateWorkOutput.model_json_schema()["$defs"]["ModelCandidateWorkItem"]["properties"])
        assert not fields & {"quantity_required", "work_date", "applicability", "qualified_alternate_part_id"}

    def test_single_wrapper_key_is_unwrapped(self):
        assert unwrap_candidate_work_input({"result": {"items": []}}) == {"items": []}
        assert unwrap_candidate_work_input({"items": []}) == {"items": []}
        assert unwrap_candidate_work_input({"a": 1, "b": 2}) == {"a": 1, "b": 2}


class TestMerge:
    def test_numbers_come_from_compute_not_the_model(self):
        kept, dropped = _merge([_item()])
        assert not dropped
        item = kept[0]
        assert item.candidate_key == "PS-GaN-650"
        # Runout June 2027 binds before the LTB close in September.
        assert (item.work_date, item.date_basis) == ("2027-06", "runout")
        assert item.quantity_required == 4320 - 1000
        assert item.applicability["lrus"] == ["AR-FIN", "AR-TVC"]
        assert item.applicability["level1"] == ["CCA-PWR"]
        assert "end of the supplied forecast horizon (2028)" in item.quantity_basis

    def test_qualified_alternate_only_from_customer_table(self):
        kept, _ = _merge([_item()])
        assert kept[0].qualified_alternate_part_id is None
        data = _data(alternates=[QualifiedAlternate("GaN-650", "GaN-650-B", "qualified")])
        kept, _ = _merge([_item()], data)
        assert kept[0].qualified_alternate_part_id == "GaN-650-B"
        assert kept[0].candidate_alternates[0]["part_number"] == "IGT65R025D2"

    def test_in_qualification_alternate_is_not_called_qualified(self):
        data = _data(alternates=[QualifiedAlternate("GaN-650", "GaN-650-B", "in_qualification")])
        kept, _ = _merge([_item()], data)
        assert kept[0].qualified_alternate_part_id is None

    def test_undated_item_needs_a_reason(self):
        _, dropped = _merge([_item(part_id="FPGA-A", candidate_alternates=[])])
        assert dropped and "date_absent_reason" in " ".join(dropped[0][1])
        kept, _ = _merge([_item(part_id="FPGA-A", candidate_alternates=[],
                                date_absent_reason="Standing single-source exposure; no notice.")])
        assert kept[0].work_date is None and kept[0].date_basis == "none_established"


class TestPerItemCompleteness:
    @pytest.mark.parametrize("field,value", [("driver", " "), ("work_implied", "phase_out"), ("source", "")])
    def test_incomplete_item_is_dropped_with_reason(self, field, value):
        kept, dropped = _merge([_item(**{field: value}), _item(part_id="FPGA-A", candidate_alternates=[],
                                                              date_absent_reason="standing")])
        assert [k.part_id for k in kept] == ["FPGA-A"]
        assert dropped[0][0] == "PS-GaN-650"

    def test_unknown_part_cannot_get_applicability(self):
        _, dropped = _merge([_item(part_id="GHOST")])
        assert "applicability cannot be derived" in " ".join(dropped[0][1])

    def test_candidate_described_as_qualified_is_dropped(self):
        alt = _item()["candidate_alternates"][0] | {"evidence": "A drop-in replacement, fully qualified."}
        _, dropped = _merge([_item(candidate_alternates=[alt])])
        assert "never qualified" in " ".join(dropped[0][1])

    def test_negated_qualification_is_a_limit_not_a_claim(self):
        alt = _item()["candidate_alternates"][0] | {"limits": "Has not been fully qualified; is not a drop-in."}
        kept, dropped = _merge([_item(candidate_alternates=[alt])])
        assert kept and not dropped

    def test_a_recommendation_is_dropped(self):
        _, dropped = _merge([_item(work_implied_description="We recommend a last-time-buy of 4,000.")])
        assert "Agent 5 decides" in " ".join(dropped[0][1])

    def test_empty_payload_is_legitimate(self):
        assert _merge([]) == ([], [])


# ---------------------------------------------------------------------------
# The structured call
# ---------------------------------------------------------------------------


def _tool_response(payload, stop_reason="tool_use", tokens=4000):
    block = MagicMock(type="tool_use", input=payload)
    block.name = "emit_candidate_work"
    return MagicMock(content=[block], stop_reason=stop_reason, usage=MagicMock(output_tokens=tokens))


def _streaming(*responses):
    def one(r):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock(get_final_message=MagicMock(return_value=r)))
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx
    return MagicMock(side_effect=[one(r) for r in responses])


def _extract(agent, *responses):
    data = _data()
    result = compute_sustainment(compute_inputs(data, TODAY))
    with patch.object(agent._client.messages, "stream", _streaming(*responses)) as stream:
        out = agent.extract_candidate_work("structure", "results", "brief", result, data)
    return out, stream


class TestStructuredCall:
    def _agent(self):
        return ProductSustainmentAgent(Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5"))

    def test_streamed_with_an_adequate_ceiling(self):
        (kept, _), stream = _extract(self._agent(), _tool_response({"items": [_item()]}))
        assert kept and stream.call_args.kwargs["max_tokens"] == CANDIDATE_WORK_MAX_TOKENS >= 32000

    def test_truncation_is_rejected_before_parsing(self):
        # A fragment that WOULD validate if parsed -- it must not be.
        frag = _tool_response({"items": []}, stop_reason="max_tokens", tokens=CANDIDATE_WORK_MAX_TOKENS)
        (kept, _), stream = _extract(self._agent(), frag, _tool_response({"items": [_item()]}))
        assert stream.call_count == 2 and kept
        retry = stream.call_args_list[1].kwargs["messages"][0]["content"]
        assert "max_tokens" in retry

    def test_truncated_twice_fails_the_run(self):
        frag = _tool_response({"items": []}, stop_reason="max_tokens")
        with pytest.raises(CandidateWorkError, match="ceiling"):
            _extract(self._agent(), frag, frag)

    def test_stop_reason_logged_at_warning_on_every_attempt(self, caplog):
        with caplog.at_level(logging.WARNING, logger="product_sustainment.agent"):
            _extract(self._agent(), _tool_response({"items": [_item()]}))
        assert any("stop_reason=tool_use" in r.message and r.levelno == logging.WARNING for r in caplog.records)

    def test_misnamed_field_reaches_the_retry_by_name(self):
        bad = _tool_response({"items": [_item(quantity=10)]})
        (_, _), stream = _extract(self._agent(), bad, _tool_response({"items": [_item()]}))
        assert "quantity" in stream.call_args_list[1].kwargs["messages"][0]["content"]

    def test_wrapped_answer_is_unwrapped_not_retried(self):
        (kept, _), stream = _extract(self._agent(), _tool_response({"candidate_work": {"items": [_item()]}}))
        assert stream.call_count == 1 and kept


class TestTierAndReports:
    def test_nine_reports_report_9_deferred(self):
        assert [r.number for r in REPORTS] == [1, 2, 3, 4, 5, 6, 7, 8, 10]
        from product_sustainment.reports import DEFERRED_REPORTS_NOTE
        assert "Report 9" in DEFERRED_REPORTS_NOTE

    def test_no_bom_is_an_exposure_scan_titled_as_such(self):
        data = _data(lru_l1={}, l1_l2={})
        assert operating_tier(data) == EXPOSURE_SCAN
        assert report_title(EXPOSURE_SCAN, "Obsolescence report").startswith("Obsolescence and exposure scan — ")

    def test_readiness_consequence_empty_when_set(self):
        for item in readiness_items(_data()):
            assert (item.consequence == "") == (item.status == "set"), item.key

    def test_both_matrices_missing_is_the_most_consequential(self):
        bom = next(i for i in readiness_items(_data(lru_l1={}, l1_l2={})) if i.key == "bom")
        assert "single most consequential omission" in bom.consequence


class TestNoBuyVersusPhaseOut:
    def test_report_specs_ask_for_options_not_decisions(self):
        r1 = REPORTS[0].must_include
        assert "## Options" in r1 and "never a buy-versus-phase-out" in r1

    def test_runout_report_uses_horizon_language(self):
        r10 = next(r for r in REPORTS if r.number == 10).must_include
        assert "through the end of the supplied forecast horizon" in r10 and "never 'through end of life'" in r10


class TestFullRun:
    def test_computed_tables_are_appended_in_code(self):
        agent = ProductSustainmentAgent(Settings(anthropic_api_key="test-key-not-real", model="claude-opus-5"))
        text_block = MagicMock(type="text", text="narrative", citations=None)
        research = MagicMock(content=[text_block], stop_reason="end_turn")
        report = MagicMock(content=[MagicMock(type="text", text="## Key Insights\n- x")], stop_reason="end_turn")
        responses = [_tool_response({"items": [_item()]})] + [report] * len(REPORTS)
        with patch.object(agent._client.messages, "create", return_value=research), \
                patch.object(agent._client.messages, "stream", _streaming(*responses)):
            result = agent.run(_data(), today=TODAY, research_rounds=1)
        by_number = {r.report_number: r.content for r in result.reports}
        assert "## Component runout table (computed)" in by_number[10]
        assert "| GaN-650 | level2 |" in by_number[10]
        assert "Jun 2027" in by_number[10] and "Critical" in by_number[10]
        assert "## Insufficient data" in by_number[10] and "RES-PREC" in by_number[10]
        assert "## Candidate work (computed)" in by_number[1] and "PS-GaN-650" in by_number[1]
        assert "(candidate)" in by_number[1]
        assert "## Inventory depletion (computed)" in by_number[8]
        assert result.candidate_work[0].quantity_required == 3320
