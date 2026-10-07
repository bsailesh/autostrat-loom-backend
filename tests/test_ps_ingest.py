"""
product_sustainment/ingest.py -- the matrix and data-file parsers.

A dangling reference is an ERROR: it would silently remove demand from the
calculation, invisibly, the same class of failure as Agent 5's bucket-name
mismatch.
"""
from product_sustainment.ingest import (
    DeclaredParts,
    mapping_template,
    parse_demand,
    parse_direct_demand,
    parse_mapping,
    parse_records,
    unlinked_part_warnings,
)

PARTS = DeclaredParts(
    lrus=frozenset({"AR-FIN", "AR-TVC", "AR-UTIL"}),
    level1=frozenset({"CCA-MC", "CCA-PWR", "CCA-SENS"}),
    level2=frozenset({"GaN-650", "FPGA-A", "RES-PREC"}),
)

LRU_L1 = """LRU,CCA-MC,CCA-PWR,CCA-SENS
AR-FIN,1,1,1
AR-TVC,1,2,
AR-UTIL,1,,1
"""

L1_L2 = """Level2,CCA-MC,CCA-PWR,CCA-SENS
GaN-650,,6,
FPGA-A,1,,1
RES-PREC,12,8,4
"""


def errors(issues):
    return [i for i in issues if i.severity == "error"]


class TestMatrix:
    def test_the_spec_example_parses_to_edges(self):
        edges, issues = parse_mapping(LRU_L1, "lru-level1", PARTS)
        assert not issues
        assert ("AR-TVC", "CCA-PWR", 2) in edges
        assert ("AR-TVC", "CCA-SENS", 0) not in edges and len(edges) == 7

    def test_level1_level2_rows_are_components(self):
        edges, issues = parse_mapping(L1_L2, "level1-level2", PARTS)
        assert not issues
        assert ("CCA-PWR", "GaN-650", 6) in edges
        assert sum(1 for p, c, _ in edges if c == "RES-PREC") == 3

    def test_dangling_column_header_is_an_error(self):
        bad = LRU_L1.replace("CCA-SENS", "CCA-GHOST")
        _, issues = parse_mapping(bad, "lru-level1", PARTS)
        errs = errors(issues)
        assert errs and "CCA-GHOST" in errs[0].message and "silently remove demand" in errs[0].message

    def test_dangling_row_label_is_an_error(self):
        _, issues = parse_mapping(L1_L2 + "GHOST-L2,1,,\n", "level1-level2", PARTS)
        assert any("GHOST-L2" in i.message for i in errors(issues))

    def test_non_integer_and_negative_cells_are_errors(self):
        _, issues = parse_mapping(LRU_L1.replace("AR-TVC,1,2,", "AR-TVC,1.5,-2,"), "lru-level1", PARTS)
        assert len(errors(issues)) == 2

    def test_edge_list_is_accepted(self):
        edge_list = "level1_id,level2_id,quantity_per_unit\nCCA-PWR,GaN-650,6\nCCA-MC,RES-PREC,12\n"
        edges, issues = parse_mapping(edge_list, "level1-level2", PARTS)
        assert not issues and set(edges) == {("CCA-PWR", "GaN-650", 6), ("CCA-MC", "RES-PREC", 12)}

    def test_edge_list_dangling_reference_is_an_error(self):
        edges, issues = parse_mapping("lru_id,level1_id,quantity_per_unit\nAR-NOPE,CCA-MC,1\n", "lru-level1", PARTS)
        assert errors(issues)

    def test_unlinked_parts_are_warnings_not_errors(self):
        lru_l1, _ = parse_mapping(LRU_L1, "lru-level1", PARTS)
        parts = DeclaredParts(PARTS.lrus, PARTS.level1, PARTS.level2 | {"ORPHAN"})
        l1_l2, _ = parse_mapping(L1_L2, "level1-level2", parts)
        issues = unlinked_part_warnings(parts, lru_l1, l1_l2)
        assert [i.field for i in issues] == ["ORPHAN"] and issues[0].severity == "warning"

    def test_template_headers_are_the_declared_ids(self):
        header, *rows = mapping_template("lru-level1", PARTS).splitlines()
        assert header == "LRU,CCA-MC,CCA-PWR,CCA-SENS"
        assert [r.split(",")[0] for r in rows] == ["AR-FIN", "AR-TVC", "AR-UTIL"]


class TestDemand:
    def test_blank_cell_is_zero_not_missing(self):
        rows, issues = parse_demand("LRU,2027,2028\nAR-FIN,100,\nAR-UTIL,,\n", PARTS)
        assert not issues and rows == [("AR-FIN", 2027, 100)]

    def test_demand_for_an_undeclared_lru_is_an_error(self):
        _, issues = parse_demand("LRU,2027\nAR-GHOST,5\n", PARTS)
        assert errors(issues) and "AR-GHOST" in errors(issues)[0].message

    def test_direct_demand_at_level1(self):
        rows, issues = parse_direct_demand("part_id,part_level,2027\nCCA-PWR,level1,5\n", PARTS)
        assert not issues and rows == [("CCA-PWR", "level1", 2027, 5)]


class TestRecords:
    def test_inventory_part_must_exist_at_its_level(self):
        _, issues = parse_records("part_id,part_level,location,form,quantity\nGaN-650,level1,A,raw,5\n", "inventory", PARTS)
        assert errors(issues)

    def test_inventory_location_and_form_are_verbatim(self):
        rows, issues = parse_records("part_id,part_level,location,form,quantity\nGaN-650,level2,Bay 7 (Hamble),Quarantine-MRB,5\n",
                                     "inventory", PARTS)
        assert not issues and rows[0]["form"] == "Quarantine-MRB" and rows[0]["location"] == "Bay 7 (Hamble)"

    def test_risk_type_is_controlled_and_dates_are_iso(self):
        _, issues = parse_records("part_id,risk_type,last_time_buy_date\nGaN-650,obsolete,30/09/2027\n", "risk", PARTS)
        assert len(errors(issues)) == 2

    def test_risk_flag_on_unknown_part_warns(self):
        rows, issues = parse_records("part_id,risk_type\nNOT-DECLARED,end_of_life\n", "risk", PARTS)
        assert rows and issues and issues[0].severity == "warning"

    def test_missing_required_column(self):
        _, issues = parse_records("part_id,quantity\nGaN-650,5\n", "inventory", PARTS)
        assert errors(issues) and "part_level" in errors(issues)[0].message
