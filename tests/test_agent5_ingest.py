"""
Unit tests for `strategy_synthesis/ingest.py` -- pure parse/validate, no
database. The bucket-name mismatch test is the one this module exists to
get right: a roadmap column that doesn't match a declared bucket must be a
hard Error naming both sides, per agent5_build_briefing.md Part 2.
"""

import pytest

from strategy_synthesis import ingest

DECLARED_BUCKETS = {"HW", "SW", "SYS", "CERT"}


# ---------------------------------------------------------------------------
# roadmap.csv
# ---------------------------------------------------------------------------


class TestRoadmapBucketMismatch:
    def test_unmatched_effort_remaining_column_is_a_hard_error_naming_both_sides(self):
        csv_text = (
            "project_id,project,type,status,pct_complete,"
            "effort_remaining_cert,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
            "P-01,CVR-25 TSO,Compliance,In flight,72,40,Q2 FY27,FY27,Jane,true,TSO,Q2 FY27\n"
        )
        parsed, issues = ingest.parse_roadmap_csv(csv_text, DECLARED_BUCKETS)

        assert parsed == []  # nothing stored -- the whole file is blocked
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        message = errors[0].message
        assert "effort_remaining_cert" in message
        assert "does not match any declared bucket" in message
        # both sides named: the bad column AND the full declared set
        assert "CERT" in message and "HW" in message and "SW" in message and "SYS" in message

    def test_unmatched_effort_total_column_is_also_a_hard_error(self):
        csv_text = (
            "project_id,project,type,status,pct_complete,"
            "effort_remaining_HW,effort_total_cert,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
            "P-01,X,Y,Z,10,5,5,Q1,FY27,Jane,false,,\n"
        )
        parsed, issues = ingest.parse_roadmap_csv(csv_text, DECLARED_BUCKETS)
        assert parsed == []
        assert any(
            i.severity == "error" and "effort_total_cert" in i.message and "does not match" in i.message
            for i in issues
        )

    def test_matching_columns_produce_no_error(self):
        csv_text = (
            "project_id,project,type,status,pct_complete,"
            "effort_remaining_HW,effort_remaining_CERT,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
            "P-01,X,Compliance,In flight,50,10,20,Q1,FY27,Jane,true,TSO,Q1\n"
        )
        parsed, issues = ingest.parse_roadmap_csv(csv_text, DECLARED_BUCKETS)
        assert [i for i in issues if i.severity == "error"] == []
        assert len(parsed) == 1
        assert parsed[0].effort_remaining == {"HW": 10.0, "CERT": 20.0}

    def test_a_declared_bucket_with_no_csv_column_is_not_an_error(self):
        """Validation is one-directional: every CSV column must match a
        declared bucket, but not every declared bucket needs a column (a
        bucket with zero current effort is legitimate)."""
        csv_text = (
            "project_id,project,type,status,pct_complete,"
            "effort_remaining_HW,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
            "P-01,X,Y,Z,50,10,Q1,FY27,Jane,false,,\n"
        )
        parsed, issues = ingest.parse_roadmap_csv(csv_text, DECLARED_BUCKETS)
        assert [i for i in issues if i.severity == "error"] == []
        assert len(parsed) == 1


class TestRoadmapEffortConsistency:
    def _csv(self, remaining_hw, total_hw, pct_complete):
        return (
            "project_id,project,type,status,pct_complete,"
            "effort_remaining_HW,effort_total_HW,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
            f"P-01,X,Y,Z,{pct_complete},{remaining_hw},{total_hw},Q1,FY27,Jane,false,,\n"
        )

    def test_remaining_exceeds_total_is_a_warning_not_an_error(self):
        parsed, issues = ingest.parse_roadmap_csv(self._csv(45, 40, 10), DECLARED_BUCKETS)
        assert len(parsed) == 1  # not blocked
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("exceeds effort_total" in w.message and "P-01" in w.message and "HW" in w.message for w in warnings)

    def test_pct_complete_consistent_with_effort_is_silent(self):
        # remaining=10, total=40 -> implied 75% complete; declared 72% -- close
        parsed, issues = ingest.parse_roadmap_csv(self._csv(10, 40, 72), DECLARED_BUCKETS)
        assert issues == []

    def test_pct_complete_inconsistent_with_effort_is_a_warning(self):
        # remaining=10, total=40 -> implied 75% complete; declared 20% -- way off
        parsed, issues = ingest.parse_roadmap_csv(self._csv(10, 40, 20), DECLARED_BUCKETS)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("pct_complete" in (w.field or "") for w in warnings)
        message = next(w.message for w in warnings if w.field == "pct_complete")
        assert "20" in message and "75" in message

    def test_absent_total_skips_the_check_silently(self):
        csv_text = (
            "project_id,project,type,status,pct_complete,"
            "effort_remaining_HW,target_gate,target_fy,owner,mandatory,mandatory_driver,mandatory_deadline\n"
            "P-01,X,Y,Z,5,10,Q1,FY27,Jane,false,,\n"  # pct_complete=5%, no total supplied at all
        )
        parsed, issues = ingest.parse_roadmap_csv(csv_text, DECLARED_BUCKETS)
        assert issues == []  # absent is fine, not flagged


# ---------------------------------------------------------------------------
# capacity.csv
# ---------------------------------------------------------------------------


class TestCapacity:
    def test_undeclared_bucket_is_a_hard_error_naming_both_sides(self):
        csv_text = "fiscal_year,bucket_id,fte,capacity_units,budget\nFY27,certification,5,240,1300000\n"
        parsed, issues = ingest.parse_capacity_csv(csv_text, DECLARED_BUCKETS)
        assert parsed == []
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "certification" in errors[0].message
        assert "not declared" in errors[0].message
        assert "CERT" in errors[0].message

    def test_declared_bucket_parses_with_nullable_capacity(self):
        csv_text = "fiscal_year,bucket_id,fte,capacity_units,budget\nFY29,HW,,,\n"
        parsed, issues = ingest.parse_capacity_csv(csv_text, DECLARED_BUCKETS)
        assert issues == []
        assert len(parsed) == 1
        assert parsed[0].capacity_units is None  # unplanned, not zero
        assert parsed[0].fte is None


# ---------------------------------------------------------------------------
# dependencies.csv
# ---------------------------------------------------------------------------


class TestDependencies:
    def test_unresolved_project_reference_is_an_error(self):
        csv_text = "project_id,depends_on_project_id,dependency_type,note\nP-05,P-99,prerequisite,\n"
        parsed, issues = ingest.parse_dependencies_csv(csv_text, {"P-01", "P-05"})
        assert parsed == []
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "P-99" in errors[0].message
        assert "depends_on_project_id" in errors[0].message

    def test_both_sides_known_parses_clean(self):
        csv_text = "project_id,depends_on_project_id,dependency_type,note\nP-05,P-03,prerequisite,IC redesign\n"
        parsed, issues = ingest.parse_dependencies_csv(csv_text, {"P-03", "P-05"})
        assert issues == []
        assert len(parsed) == 1
        assert parsed[0].project_key == "P-05"
        assert parsed[0].depends_on_key == "P-03"


# ---------------------------------------------------------------------------
# products_fleet.csv
# ---------------------------------------------------------------------------


class TestProductsFleet:
    def test_duplicate_product_platform_is_a_warning_not_an_error(self):
        csv_text = (
            "product_id,product,platform,platform_class,units_in_service,avg_age_yrs,status,region\n"
            "MR-CVR20,CVR-20,A320ceo,Part 25 transport,1850,14,Sunsetting,\n"
            "MR-CVR20,CVR-20,A320ceo,Part 25 transport,999,14,Sunsetting,\n"
        )
        parsed, issues = ingest.parse_products_fleet_csv(csv_text)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("duplicates" in w.message for w in warnings)
        assert [i for i in issues if i.severity == "error"] == []
        assert len(parsed) == 1  # collapsed, not doubled

    def test_different_platforms_for_same_product_are_not_duplicates(self):
        csv_text = (
            "product_id,product,platform,platform_class,units_in_service,avg_age_yrs,status,region\n"
            "MR-CVR20,CVR-20,A320ceo,Part 25 transport,1850,14,Sunsetting,\n"
            "MR-CVR20,CVR-20,B737NG,Part 25 transport,2100,16,Sunsetting,\n"
        )
        parsed, issues = ingest.parse_products_fleet_csv(csv_text)
        assert issues == []
        assert len(parsed) == 2

    def test_non_positive_units_is_a_warning(self):
        csv_text = (
            "product_id,product,platform,platform_class,units_in_service,avg_age_yrs,status,region\n"
            "MR-X,X,P1,,0,1,Current,\n"
        )
        parsed, issues = ingest.parse_products_fleet_csv(csv_text)
        assert any(i.severity == "warning" and "units_in_service" in (i.field or "") for i in issues)


# ---------------------------------------------------------------------------
# project_financials.csv
# ---------------------------------------------------------------------------


class TestFinancials:
    def test_unresolved_project_is_an_error(self):
        csv_text = (
            "project_id,revenue_impact_y1,revenue_impact_y2,revenue_impact_y3,revenue_impact_y4,revenue_impact_y5,"
            "capex,opex_annual,discount_rate,currency,basis\n"
            "P-99,10,10,10,10,10,5,1,0.1,USD,estimate\n"
        )
        parsed, issues = ingest.parse_financials_csv(csv_text, {"P-01"})
        assert parsed == []
        assert any(i.severity == "error" and "P-99" in i.message for i in issues)

    def test_known_project_parses_with_partial_years(self):
        csv_text = (
            "project_id,revenue_impact_y1,revenue_impact_y2,revenue_impact_y3,revenue_impact_y4,revenue_impact_y5,"
            "capex,opex_annual,discount_rate,currency,basis\n"
            "P-01,10,,,,,\n"
        )
        parsed, issues = ingest.parse_financials_csv(csv_text, {"P-01"})
        assert issues == []
        assert parsed[0].revenue_impact == [10.0, None, None, None, None]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_roadmap_template_reflects_declared_buckets_in_order(self):
        csv_text = ingest.generate_template("roadmap", ["HW", "SW", "SYS", "CERT"])
        header = csv_text.strip().split(",")
        assert header[:5] == ["project_id", "project", "type", "status", "pct_complete"]
        assert "effort_remaining_HW" in header
        assert "effort_total_HW" in header
        # grouped per bucket: remaining immediately followed by total
        i = header.index("effort_remaining_CERT")
        assert header[i + 1] == "effort_total_CERT"
        assert header[-6:] == [
            "target_gate", "target_fy", "owner", "mandatory", "mandatory_driver", "mandatory_deadline",
        ]

    def test_capacity_template_is_static_regardless_of_buckets(self):
        a = ingest.generate_template("capacity", ["HW", "SW"])
        b = ingest.generate_template("capacity", ["HW", "SW", "SYS", "CERT", "OPS"])
        assert a == b
        assert "bucket_id" in a  # a value column, not per-bucket headers

    def test_unknown_file_type_raises(self):
        with pytest.raises(ValueError):
            ingest.generate_template("not_a_real_type", [])
