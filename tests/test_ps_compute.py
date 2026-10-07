"""
product_sustainment/compute.py -- where correctness lives.

Built on the Arden worked example (input spec Part 11):

    LRU,      CCA-MC, CCA-PWR, CCA-SENS        Level2,    CCA-MC, CCA-PWR, CCA-SENS
    AR-FIN,   1,      1,       1               GaN-650,   ,       6,
    AR-TVC,   1,      2,                       FPGA-A,    1,      ,        1
    AR-UTIL,  1,      ,        1               RES-PREC,  12,     8,       4

Per LRU unit, summed over every path:
    GaN-650   AR-FIN 6    AR-TVC 12   AR-UTIL 0
    RES-PREC  AR-FIN 24   AR-TVC 28   AR-UTIL 16
    FPGA-A    AR-FIN 2    AR-TVC 1    AR-UTIL 2

The class TestTheMatrixIsNotATree pins the one property the briefing calls
most likely to be got wrong.
"""
import random
from datetime import date
from fractions import Fraction

import pytest

from product_sustainment.compute import (
    LEVEL1,
    LEVEL2,
    LRU,
    WATCH_MARGIN_MONTHS,
    InventoryRow,
    Pipeline,
    RiskFlag,
    SustainmentInputs,
    cascade,
    composite_lru_l2,
    compute_sustainment,
    deplete,
    derive_demand,
)

LRU_L1 = {
    "AR-FIN": {"CCA-MC": 1, "CCA-PWR": 1, "CCA-SENS": 1},
    "AR-TVC": {"CCA-MC": 1, "CCA-PWR": 2},
    "AR-UTIL": {"CCA-MC": 1, "CCA-SENS": 1},
}
L1_L2 = {
    "CCA-MC": {"FPGA-A": 1, "RES-PREC": 12},
    "CCA-PWR": {"GaN-650": 6, "RES-PREC": 8},
    "CCA-SENS": {"FPGA-A": 1, "RES-PREC": 4},
}
START = date(2027, 1, 1)


def _inputs(**over) -> SustainmentInputs:
    base = dict(
        lrus=["AR-FIN", "AR-TVC", "AR-UTIL"],
        level1=["CCA-MC", "CCA-PWR", "CCA-SENS"],
        level2=["GaN-650", "FPGA-A", "RES-PREC"],
        lru_l1=LRU_L1,
        l1_l2=L1_L2,
        lru_demand={"AR-FIN": {2027: 120, 2028: 120}, "AR-TVC": {2027: 120, 2028: 120}},
        start=START,
        inventory=[InventoryRow("GaN-650", LEVEL2, "Plant A", "raw", 1000)],
    )
    base.update(over)
    return SustainmentInputs(**base)


def _pos(result, part):
    return next(p for p in result.positions if p.part_id == part)


class TestTheMatrixIsNotATree:
    def test_gan_650_is_six_times_fin_plus_two_tvc(self):
        lru_demand = {"AR-FIN": {2027: 100}, "AR-TVC": {2027: 100}}
        _, _, d2 = derive_demand(_inputs(lru_demand=lru_demand))
        assert d2["GaN-650"][2027] == 6 * (100 + 2 * 100) == 1800
        # Examining AR-FIN alone -- the error this design exists to prevent.
        _, _, fin_only = derive_demand(_inputs(lru_demand={"AR-FIN": {2027: 100}}))
        assert fin_only["GaN-650"][2027] == 600 == Fraction(1, 3) * 1800

    def test_a_component_reached_through_three_assemblies_sums_all_three(self):
        m = composite_lru_l2(LRU_L1, L1_L2)
        # A walk that takes the first path finds 12; one that marks visited
        # nodes finds 12 or 20 depending on order. All three paths count.
        assert m["AR-FIN"]["RES-PREC"] == 12 + 8 + 4
        assert m["AR-TVC"]["RES-PREC"] == 12 + 2 * 8
        assert m["AR-UTIL"]["RES-PREC"] == 12 + 4

    def test_an_assembly_appearing_twice_counts_twice(self):
        assert composite_lru_l2(LRU_L1, L1_L2)["AR-TVC"]["GaN-650"] == 12

    def test_a_shared_assembly_draws_from_every_lru(self):
        _, d1, _ = derive_demand(_inputs(lru_demand={"AR-FIN": {2027: 10}, "AR-TVC": {2027: 20}, "AR-UTIL": {2027: 30}}))
        assert d1["CCA-MC"][2027] == 60
        assert d1["CCA-PWR"][2027] == 10 + 2 * 20

    def test_result_is_independent_of_edge_order(self):
        def shuffled(mat, seed):
            rng = random.Random(seed)
            rows = list(mat.items())
            rng.shuffle(rows)
            out = {}
            for r, cols in rows:
                items = list(cols.items())
                rng.shuffle(items)
                out[r] = dict(items)
            return out

        expected = composite_lru_l2(LRU_L1, L1_L2)
        for seed in range(5):
            assert composite_lru_l2(shuffled(LRU_L1, seed), shuffled(L1_L2, seed)) == expected

    def test_level2_demand_equals_lru_demand_times_composite(self):
        dem = {"AR-FIN": {2027: 7}, "AR-TVC": {2027: 11}, "AR-UTIL": {2027: 13}}
        m = composite_lru_l2(LRU_L1, L1_L2)
        _, _, d2 = derive_demand(_inputs(lru_demand=dem))
        for k in ("GaN-650", "FPGA-A", "RES-PREC"):
            assert d2[k][2027] == sum(dem[i][2027] * m[i].get(k, 0) for i in dem)


class TestDirectDemandFlowsDown:
    def test_level1_spares_consume_level2(self):
        inputs = _inputs(lru_demand={}, direct_demand={(LEVEL1, "CCA-PWR"): {2027: 5}})
        _, d1, d2 = derive_demand(inputs)
        assert d1["CCA-PWR"][2027] == 5
        assert d2["GaN-650"][2027] == 30  # 5 spare cards x 6

    def test_lru_direct_demand_reaches_level2(self):
        inputs = _inputs(lru_demand={}, direct_demand={(LRU, "AR-TVC"): {2027: 1}})
        _, _, d2 = derive_demand(inputs)
        assert d2["GaN-650"][2027] == 12

    def test_direct_level2_demand_is_added_not_substituted(self):
        inputs = _inputs(lru_demand={"AR-FIN": {2027: 10}}, direct_demand={(LEVEL2, "GaN-650"): {2027: 7}})
        _, _, d2 = derive_demand(inputs)
        assert d2["GaN-650"][2027] == 60 + 7


class TestInventoryRollUp:
    def test_level1_and_lru_stock_roll_down_to_level2_equivalents(self):
        inv = [
            InventoryRow("RES-PREC", LEVEL2, "Plant A", "raw", 100),
            InventoryRow("RES-PREC", LEVEL2, "Plant B", "consigned", 50),
            InventoryRow("CCA-MC", LEVEL1, "Plant A", "finished", 20),  # 20 x 12
            InventoryRow("CCA-SENS", LEVEL1, "Plant A", "in_process", 5),  # 5 x 4
            InventoryRow("AR-FIN", LRU, "Depot", "finished", 3),  # 3 x 24, all paths
        ]
        result = compute_sustainment(_inputs(inventory=inv))
        s = _pos(result, "RES-PREC").supply
        assert s.on_hand == 150
        assert {(l.location, l.form) for l in s.on_hand_lines} == {("Plant A", "raw"), ("Plant B", "consigned")}
        assert s.from_level1 == 240 + 20
        assert s.from_lru == 72
        assert s.total == 150 + 260 + 72

    def test_composition_separates_pipeline_and_ignores_supplier_qty(self):
        result = compute_sustainment(_inputs(pipeline={"GaN-650": Pipeline(400, 999, 100, 50)}))
        s = _pos(result, "GaN-650").supply
        assert (s.on_hand, s.open_po, s.supplier_on_order, s.supplier_wip) == (1000, 400, 100, 50)
        assert s.supplier_qty_not_counted == 999
        assert s.total == 1550
        assert s.pipeline_share == Fraction(550, 1550)


class TestDepletion:
    def test_first_zero_month(self):
        # 1,200 a year = 100 a month; 350 in stock runs out in April.
        dep = deplete(350, {2027: Fraction(1200)}, START, 2027)
        assert dep.runout == (2027, 4)

    def test_exact_zero_is_runout(self):
        assert deplete(300, {2027: Fraction(1200)}, START, 2027).runout == (2027, 3)

    def test_start_mid_year_skips_past_months(self):
        dep = deplete(150, {2027: Fraction(1200)}, date(2027, 10, 1), 2027)
        assert dep.runout == (2027, 11)
        assert dep.demand_in_horizon == 300

    def test_year_end_positions_alongside_monthly_runout(self):
        # GaN: 6 x (120 + 2 x 120) = 2,160 a year = 180 a month, 1,000 on hand.
        p = _pos(compute_sustainment(_inputs()), "GaN-650")
        assert p.depletion.runout == (2027, 6)  # 1000 - 6 x 180 < 0
        assert p.depletion.year_end == {2027: 1000 - 2160, 2028: 1000 - 4320}

    def test_fractional_monthly_demand_is_exact(self):
        # 1,000 a year is 83.33... a month; float drift must not move the month.
        dep = deplete(1000, {2027: Fraction(1000)}, START, 2027)
        assert dep.runout == (2027, 12)
        assert dep.year_end[2027] == 0

    def test_no_demand_never_runs_out(self):
        dep = deplete(0, {}, START, 2028)
        assert dep.runout is None and dep.shortfall == 0


class TestShortfallAndCompetingDemand:
    def test_shortfall_lists_every_competing_lru(self):
        p = _pos(compute_sustainment(_inputs()), "GaN-650")
        assert p.quantity_required == 4320 - 1000
        sources = {s.source: s for s in p.competing_lrus}
        assert set(sources) == {"AR-FIN", "AR-TVC"}  # every consumer, none chosen
        assert sources["AR-FIN"].demand_in_horizon == 240 * 6
        assert sources["AR-TVC"].demand_in_horizon == 240 * 12

    def test_zero_demand_consumer_is_still_listed(self):
        p = _pos(compute_sustainment(_inputs(inventory=[InventoryRow("RES-PREC", LEVEL2, "A", "raw", 10)])), "RES-PREC")
        utl = next(s for s in p.demand_shares if s.source == "AR-UTIL")
        assert utl.qty_per_unit == 16 and utl.demand_in_horizon == 0
        assert "AR-UTIL" in {s.source for s in p.competing_lrus}

    def test_no_shortfall_no_competition(self):
        p = _pos(compute_sustainment(_inputs(inventory=[InventoryRow("GaN-650", LEVEL2, "A", "raw", 10**6)])), "GaN-650")
        assert p.quantity_required == 0 and p.competing_lrus == ()


class TestLastTimeBuy:
    def _with_ltb(self, ltb: date):
        flags = {"GaN-650": [RiskFlag("end_of_life", "NFND", last_time_buy_date=ltb)]}
        return _pos(compute_sustainment(_inputs(risk_flags=flags)), "GaN-650")

    def test_runout_before_window_closes_is_critical(self):
        p = self._with_ltb(date(2027, 9, 30))  # runout June 2027
        assert p.ltb_status == "critical" and p.months_runout_after_ltb == -3

    def test_runout_within_margin_after_close_is_watch(self):
        p = self._with_ltb(date(2026, 12, 31))
        assert p.ltb_status == "watch" and 0 < p.months_runout_after_ltb <= WATCH_MARGIN_MONTHS

    def test_runout_well_after_close_is_ok(self):
        assert self._with_ltb(date(2025, 1, 1)).ltb_status == "ok"

    def test_no_ltb_date_no_status(self):
        assert _pos(compute_sustainment(_inputs()), "GaN-650").ltb_status is None

    def test_the_margin_is_stated_in_the_notes(self):
        notes = " ".join(compute_sustainment(_inputs()).notes)
        assert f"{WATCH_MARGIN_MONTHS} months" in notes
        assert "end of the supplied forecast horizon" in notes


class TestLeadTimeCheck:
    def test_fires_when_runout_is_inside_lead_time_with_pipeline(self):
        inputs = _inputs(pipeline={"GaN-650": Pipeline(open_po_qty=100)}, lead_time_days={"GaN-650": 365})
        lt = _pos(compute_sustainment(inputs), "GaN-650").lead_time
        assert lt.status == "flagged" and "may not hold" in lt.message

    def test_clear_when_runout_is_beyond_lead_time(self):
        inputs = _inputs(pipeline={"GaN-650": Pipeline(open_po_qty=100)}, lead_time_days={"GaN-650": 30})
        assert _pos(compute_sustainment(inputs), "GaN-650").lead_time.status == "clear"

    def test_no_lead_time_reports_unavailable(self):
        lt = _pos(compute_sustainment(_inputs()), "GaN-650").lead_time
        assert lt.status == "unavailable" and "could not be performed" in lt.message


class TestInsufficientData:
    def test_parts_without_inventory_are_listed_never_dropped(self):
        result = compute_sustainment(_inputs())
        listed = {p.part_id for p in result.insufficient}
        assert {"FPGA-A", "RES-PREC", "CCA-MC", "CCA-PWR", "CCA-SENS"} <= listed
        every = {p.part_id for p in result.positions} | listed
        assert every == {"GaN-650", "FPGA-A", "RES-PREC", "CCA-MC", "CCA-PWR", "CCA-SENS"}

    def test_component_in_no_assembly(self):
        result = compute_sustainment(_inputs(level2=["GaN-650", "ORPHAN"]))
        orphan = next(p for p in result.insufficient if p.part_id == "ORPHAN")
        assert any("No BOM link" in r for r in orphan.reasons)

    def test_assembly_in_no_lru_has_no_demand_path(self):
        result = compute_sustainment(_inputs(level1=["CCA-MC", "CCA-PWR", "CCA-SENS", "CCA-SPARE"]))
        spare = next(p for p in result.insufficient if p.part_id == "CCA-SPARE")
        assert any("No demand path" in r for r in spare.reasons)
        assert "CCA-SPARE" in result.parts_without_demand_path

    def test_no_demand_file_means_no_runout_for_anyone(self):
        result = compute_sustainment(_inputs(lru_demand={}, demand_supplied=False))
        assert result.positions == ()
        assert all(any("No demand forecast" in r for r in p.reasons) for p in result.insufficient)

    def test_risk_flag_on_unknown_part_is_reported(self):
        result = compute_sustainment(_inputs(risk_flags={"GHOST": [RiskFlag("end_of_life")]}))
        assert any(p.part_id == "GHOST" for p in result.insufficient)

    def test_lru_with_no_demand_rows_still_appears(self):
        summary = {s.lru_id: s for s in compute_sustainment(_inputs()).lru_summary}
        assert summary["AR-UTIL"].has_demand_rows is False

    def test_demand_path_but_zero_forecast_is_a_position_not_insufficient(self):
        inputs = _inputs(lru_demand={"AR-UTIL": {2027: 0}}, inventory=[InventoryRow("FPGA-A", LEVEL2, "A", "raw", 5)])
        p = _pos(compute_sustainment(inputs), "FPGA-A")
        assert p.no_forecast_demand and p.depletion.runout is None


class TestLevel1Runout:
    def test_an_assembly_with_its_own_stock_runs_out_independently(self):
        inputs = _inputs(inventory=[InventoryRow("CCA-PWR", LEVEL1, "A", "finished", 300)])
        p = _pos(compute_sustainment(inputs), "CCA-PWR")
        # (120 + 2 x 120) = 360 a year = 30 a month; 300 lasts ten months.
        assert p.depletion.runout == (2027, 10)
        assert p.affected_lrus == ("AR-FIN", "AR-TVC")

    def test_lru_stock_rolls_into_level1_supply(self):
        inputs = _inputs(inventory=[InventoryRow("AR-TVC", LRU, "Depot", "finished", 5)])
        assert _pos(compute_sustainment(inputs), "CCA-PWR").supply.from_lru == 10


class TestUpwardCascade:
    def test_component_reaches_every_lru_through_every_assembly(self):
        assert cascade("RES-PREC", LEVEL2, LRU_L1, L1_L2) == (
            ("CCA-MC", "CCA-PWR", "CCA-SENS"),
            ("AR-FIN", "AR-TVC", "AR-UTIL"),
        )
        assert cascade("GaN-650", LEVEL2, LRU_L1, L1_L2) == (("CCA-PWR",), ("AR-FIN", "AR-TVC"))

    def test_position_carries_the_full_affected_set(self):
        p = _pos(compute_sustainment(_inputs()), "GaN-650")
        assert p.affected_level1 == ("CCA-PWR",)
        assert p.affected_lrus == ("AR-FIN", "AR-TVC")
