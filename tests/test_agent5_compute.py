"""
Unit tests for `strategy_synthesis/compute.py` — the deterministic core of
Agent 5. No LLM, no database; every test here is pure arithmetic.

The capacity/bottleneck tests reproduce the exact shape
`agent5_decision_brief_strawman_v2.md` was built to probe: aggregate FY27
utilisation looks comfortable at 51%, while certification alone sits at
115%. Any implementation that reports the aggregate without surfacing the
certification bottleneck has failed the test the brief was designed for.
"""

import pytest

from strategy_synthesis.compute import (
    CompositeScore,
    Dependency,
    DimensionScore,
    ProjectFinancials,
    ProjectScore,
    Scenario,
    check_cross_scenario_prerequisites,
    compute_bucket_utilisation,
    compute_composite_scores,
    compute_financial_metrics,
    compute_scenarios,
    find_bottlenecks,
)
from tests.fixtures.agent5.strawman import (
    BASE_RANK_ORDER,
    BUCKETS,
    CAPACITY,
    COMMITTED_PROJECT_KEYS,
    PROJECT_EFFORT,
    PROJECTS,
)

BASE_WEIGHTS = {
    "customer": 0.25,
    "strategic": 0.20,
    "revenue": 0.20,
    "risk": 0.15,
    "time": 0.10,
    "effort": 0.10,
}


def _ranking_from_order(order: list[str]) -> list[CompositeScore]:
    """Build a CompositeScore ranking directly from a rank order, for tests
    that exercise bottleneck/prerequisite logic against a known ranking
    without having to fabricate dimension scores for every project."""
    return [
        CompositeScore(project_key=key, composite_score=float(len(order) - i), rank=i + 1, tied_with=[])
        for i, key in enumerate(order)
    ]


# ---------------------------------------------------------------------------
# 3.2 Capacity utilisation — the case the strawman brief exists to test
# ---------------------------------------------------------------------------


class TestBucketUtilisation:
    def test_matches_strawman_fy27_shape(self):
        buckets, aggregate = compute_bucket_utilisation(
            PROJECT_EFFORT, CAPACITY, BUCKETS, COMMITTED_PROJECT_KEYS, fiscal_year="FY27"
        )
        by_key = {b.bucket_key: b for b in buckets}

        assert by_key["hardware"].demand == 498
        assert by_key["software"].demand == 220
        assert by_key["systems"].demand == 281
        assert by_key["certification"].demand == 277

        assert round(by_key["hardware"].utilisation_pct) == 51
        assert round(by_key["software"].utilisation_pct) == 29
        assert round(by_key["systems"].utilisation_pct) == 52
        assert round(by_key["certification"].utilisation_pct) == 115

        assert aggregate is not None
        assert aggregate.demand == 1276
        assert aggregate.capacity == 2520
        assert round(aggregate.utilisation_pct) == 51
        assert aggregate.excluded_buckets == []

    def test_aggregate_headroom_does_not_hide_the_bucket_bottleneck(self):
        """The finding the brief is built to force: aggregate utilisation
        alone (51%) implies over 1,000 weeks of headroom, but one bucket is
        already oversubscribed. over_capacity must be computed per bucket,
        never inferred from the aggregate."""
        buckets, aggregate = compute_bucket_utilisation(
            PROJECT_EFFORT, CAPACITY, BUCKETS, COMMITTED_PROJECT_KEYS, fiscal_year="FY27"
        )
        assert aggregate.utilisation_pct < 100
        over_capacity_buckets = [b.bucket_key for b in buckets if b.over_capacity]
        assert over_capacity_buckets == ["certification"]

    def test_unplanned_fiscal_year_is_none_not_zero(self):
        """FY29 has no capacity rows at all in the brief. Every bucket must
        come back with capacity=None (unplanned), never 0 -- 0 would read as
        a real, catastrophic bottleneck instead of an unplanned year."""
        buckets, aggregate = compute_bucket_utilisation(
            PROJECT_EFFORT, CAPACITY, BUCKETS, COMMITTED_PROJECT_KEYS, fiscal_year="FY29"
        )
        assert all(b.capacity is None for b in buckets)
        assert all(b.utilisation_pct is None for b in buckets)
        assert all(b.over_capacity is False for b in buckets)
        assert aggregate is None

    def test_partially_unplanned_year_excludes_only_the_unplanned_bucket(self):
        """One bucket can be unplanned while the rest of that fiscal year is
        set (e.g. a bucket added mid-cycle). The aggregate must still be
        computed from the planned buckets, and must name what it excluded."""
        from strategy_synthesis.compute import Bucket, Capacity, ProjectEffort

        buckets = [
            Bucket(bucket_key="hardware", bucket_name="Hardware", contractable="yes"),
            Bucket(bucket_key="certification", bucket_name="Certification", contractable="no"),
        ]
        capacity = [Capacity(fiscal_year="FY29", bucket_key="hardware", capacity_units=500)]
        effort = [
            ProjectEffort(project_key="P-01", bucket_key="hardware", effort_remaining=100),
            ProjectEffort(project_key="P-01", bucket_key="certification", effort_remaining=10),
        ]
        results, aggregate = compute_bucket_utilisation(effort, capacity, buckets, {"P-01"}, fiscal_year="FY29")
        by_key = {b.bucket_key: b for b in results}

        assert by_key["hardware"].capacity == 500
        assert by_key["certification"].capacity is None
        assert aggregate is not None
        assert aggregate.demand == 100  # certification's demand excluded, not zeroed into the total
        assert aggregate.capacity == 500
        assert aggregate.excluded_buckets == ["certification"]

    def test_only_committed_projects_count_toward_demand(self):
        buckets, _ = compute_bucket_utilisation(
            PROJECT_EFFORT, CAPACITY, BUCKETS, committed_project_keys=set(), fiscal_year="FY27"
        )
        assert all(b.demand == 0 for b in buckets)


# ---------------------------------------------------------------------------
# 3.3 Bottleneck analysis
# ---------------------------------------------------------------------------


class TestBottleneckAnalysis:
    def test_certification_bottleneck_with_minimum_deferral(self):
        bucket_utilisation, _ = compute_bucket_utilisation(
            PROJECT_EFFORT, CAPACITY, BUCKETS, COMMITTED_PROJECT_KEYS, fiscal_year="FY27"
        )
        ranking = _ranking_from_order(BASE_RANK_ORDER)

        findings = find_bottlenecks(bucket_utilisation, PROJECT_EFFORT, PROJECTS, ranking)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.bucket_key == "certification"
        assert finding.overage == 37
        assert finding.mandatory_demand == 180  # P-01 (40) + P-02 (125) + P-08 (15)
        assert finding.mandatory_share_pct == 75.0  # 180 / 240 capacity
        assert finding.contractable == "no"
        assert finding.resolvable_by_deferral is True
        assert finding.deferral_set == ["P-05"]
        assert finding.deferral_weeks_removed == 40
        assert round(finding.resulting_utilisation_pct) == 99  # 237 / 240
        assert finding.agrees_with_ranking is True  # a single project resolves it

    def test_non_bottlenecked_buckets_produce_no_finding(self):
        bucket_utilisation, _ = compute_bucket_utilisation(
            PROJECT_EFFORT, CAPACITY, BUCKETS, COMMITTED_PROJECT_KEYS, fiscal_year="FY27"
        )
        ranking = _ranking_from_order(BASE_RANK_ORDER)
        findings = find_bottlenecks(bucket_utilisation, PROJECT_EFFORT, PROJECTS, ranking)
        flagged = {f.bucket_key for f in findings}
        assert "hardware" not in flagged
        assert "software" not in flagged
        assert "systems" not in flagged

    def test_unresolvable_bottleneck_reports_no_deferral_set(self):
        """If even deferring every discretionary project in the bucket can't
        bring it under capacity, say so rather than returning a partial or
        misleading set."""
        from strategy_synthesis.compute import Bucket, Capacity, Project, ProjectEffort

        buckets = [Bucket(bucket_key="certification", bucket_name="Certification", contractable="no")]
        capacity = [Capacity(fiscal_year="FY27", bucket_key="certification", capacity_units=100)]
        projects = [
            Project(project_key="M-01", name="Mandatory", mandatory=True),
            Project(project_key="D-01", name="Discretionary", mandatory=False),
        ]
        effort = [
            # mandatory demand alone (110) already exceeds capacity (100) --
            # no deferral of discretionary work can resolve this bucket.
            ProjectEffort(project_key="M-01", bucket_key="certification", effort_remaining=110),
            ProjectEffort(project_key="D-01", bucket_key="certification", effort_remaining=20),
        ]
        bucket_utilisation, _ = compute_bucket_utilisation(
            effort, capacity, buckets, {"M-01", "D-01"}, fiscal_year="FY27"
        )
        ranking = _ranking_from_order(["M-01", "D-01"])

        findings = find_bottlenecks(bucket_utilisation, effort, projects, ranking)

        assert len(findings) == 1
        assert findings[0].resolvable_by_deferral is False
        assert findings[0].deferral_set == []
        assert findings[0].agrees_with_ranking is None

    def test_deferral_of_two_projects_is_not_the_clean_case(self):
        from strategy_synthesis.compute import Bucket, Capacity, Project, ProjectEffort

        buckets = [Bucket(bucket_key="certification", bucket_name="Certification", contractable="no")]
        capacity = [Capacity(fiscal_year="FY27", bucket_key="certification", capacity_units=50)]
        projects = [
            Project(project_key="D-01", name="D1", mandatory=False),
            Project(project_key="D-02", name="D2", mandatory=False),
        ]
        effort = [
            ProjectEffort(project_key="D-01", bucket_key="certification", effort_remaining=60),
            ProjectEffort(project_key="D-02", bucket_key="certification", effort_remaining=55),
        ]
        bucket_utilisation, _ = compute_bucket_utilisation(
            effort, capacity, buckets, {"D-01", "D-02"}, fiscal_year="FY27"
        )
        # demand=115, capacity=50: neither project alone (60 or 55) resolves
        # it, so both must be deferred -- the non-clean, multi-project case.
        ranking = _ranking_from_order(["D-01", "D-02"])
        findings = find_bottlenecks(bucket_utilisation, effort, projects, ranking)
        assert findings[0].resolvable_by_deferral is True
        assert set(findings[0].deferral_set) == {"D-01", "D-02"}
        assert findings[0].agrees_with_ranking is False


# ---------------------------------------------------------------------------
# 3.1 Composite scoring
# ---------------------------------------------------------------------------


class TestCompositeScoring:
    def test_matches_reference_output_for_top_three(self):
        """Dimension scores transcribed from `agent5_test_output_v2.md`
        Report 3's "Dimension values, top three" table."""
        project_scores = [
            ProjectScore(
                project_key="P-01",
                dimensions=[
                    DimensionScore("customer", 9),
                    DimensionScore("strategic", 10),
                    DimensionScore("revenue", 9),
                    DimensionScore("risk", 8),
                    DimensionScore("time", 10),
                    DimensionScore("effort", 9),
                ],
            ),
            ProjectScore(
                project_key="P-02",
                dimensions=[
                    DimensionScore("customer", 8),
                    DimensionScore("strategic", 9),
                    DimensionScore("revenue", 9),
                    DimensionScore("risk", 6),
                    DimensionScore("time", 9),
                    DimensionScore("effort", 4),
                ],
            ),
            ProjectScore(
                project_key="P-09",
                dimensions=[
                    DimensionScore("customer", 6),
                    DimensionScore("strategic", 8),
                    DimensionScore("revenue", 8),
                    DimensionScore("risk", 6),
                    DimensionScore("time", 8),
                    DimensionScore("effort", 5),
                ],
            ),
        ]

        results = compute_composite_scores(project_scores, BASE_WEIGHTS)
        by_key = {r.project_key: r for r in results}

        assert by_key["P-01"].composite_score == 9.15
        assert by_key["P-01"].rank == 1
        assert by_key["P-02"].composite_score == 7.80
        assert by_key["P-02"].rank == 2
        assert by_key["P-09"].composite_score == 6.90
        assert by_key["P-09"].rank == 3

    def test_ties_share_a_rank_and_are_not_broken_arbitrarily(self):
        project_scores = [
            ProjectScore(project_key="A", dimensions=[DimensionScore("only", 10)]),
            ProjectScore(project_key="B", dimensions=[DimensionScore("only", 10)]),
            ProjectScore(project_key="C", dimensions=[DimensionScore("only", 5)]),
        ]
        results = compute_composite_scores(project_scores, {"only": 1.0})
        by_key = {r.project_key: r for r in results}

        assert by_key["A"].rank == 1
        assert by_key["B"].rank == 1
        assert set(by_key["A"].tied_with) == {"B"}
        assert set(by_key["B"].tied_with) == {"A"}
        # third place is skipped -- two projects hold rank 1, so C is rank 3
        assert by_key["C"].rank == 3
        assert by_key["C"].tied_with == []

    def test_weights_must_sum_to_one(self):
        project_scores = [ProjectScore(project_key="A", dimensions=[DimensionScore("only", 5)])]
        with pytest.raises(ValueError):
            compute_composite_scores(project_scores, {"only": 0.5})

    def test_missing_dimension_score_raises(self):
        project_scores = [ProjectScore(project_key="A", dimensions=[DimensionScore("customer", 5)])]
        with pytest.raises(ValueError, match="'A'"):
            compute_composite_scores(project_scores, {"customer": 0.5, "risk": 0.5})


# ---------------------------------------------------------------------------
# 3.4 / 3.5 Scenario re-ranking and cross-scenario prerequisite check
# ---------------------------------------------------------------------------


class TestScenariosAndPrerequisites:
    def _scores(self):
        # A: strong on strategic, weak on revenue. B: the reverse.
        return [
            ProjectScore(
                project_key="A",
                dimensions=[DimensionScore("strategic", 10), DimensionScore("revenue", 2)],
            ),
            ProjectScore(
                project_key="B",
                dimensions=[DimensionScore("strategic", 2), DimensionScore("revenue", 10)],
            ),
        ]

    def test_scenario_reweighting_can_change_the_ranking(self):
        scenarios = [
            Scenario(name="Strategic-led", weights={"strategic": 0.8, "revenue": 0.2}),
            Scenario(name="Revenue-led", weights={"strategic": 0.2, "revenue": 0.8}),
        ]
        results = compute_scenarios(self._scores(), scenarios, bucket_utilisation=[], project_effort=[], projects=[])
        by_name = {r.scenario_name: r for r in results}

        strategic_led_first = min(by_name["Strategic-led"].ranking, key=lambda c: c.rank)
        revenue_led_first = min(by_name["Revenue-led"].ranking, key=lambda c: c.rank)
        assert strategic_led_first.project_key == "A"
        assert revenue_led_first.project_key == "B"

    def test_prerequisite_violation_detected_when_scenario_promotes_dependent(self):
        from strategy_synthesis.compute import Bucket, Capacity, Project, ProjectEffort

        # A depends on B. Base weighting ranks B ahead of A (correct order).
        # A "Growth" scenario flips it, ranking A ahead of its own
        # prerequisite B -- a violation.
        project_scores = [
            ProjectScore(project_key="A", dimensions=[DimensionScore("customer", 9), DimensionScore("effort", 2)]),
            ProjectScore(project_key="B", dimensions=[DimensionScore("customer", 2), DimensionScore("effort", 9)]),
        ]
        scenarios = [
            Scenario(name="Base", weights={"customer": 0.3, "effort": 0.7}),
            Scenario(name="Growth", weights={"customer": 0.9, "effort": 0.1}),
        ]
        dependencies = [Dependency(project_key="A", depends_on="B", source="inferred")]

        results = compute_scenarios(project_scores, scenarios, bucket_utilisation=[], project_effort=[], projects=[])
        violations = check_cross_scenario_prerequisites(results, dependencies)

        assert len(violations) == 1
        violation = violations[0]
        assert violation.scenario_name == "Growth"
        assert violation.project_key == "A"
        assert violation.depends_on == "B"
        assert violation.project_rank < violation.depends_on_rank

    def test_clean_scenario_has_no_violations(self):
        project_scores = [
            ProjectScore(project_key="A", dimensions=[DimensionScore("only", 2)]),
            ProjectScore(project_key="B", dimensions=[DimensionScore("only", 9)]),
        ]
        scenarios = [Scenario(name="Base", weights={"only": 1.0})]
        dependencies = [Dependency(project_key="A", depends_on="B")]

        results = compute_scenarios(project_scores, scenarios, bucket_utilisation=[], project_effort=[], projects=[])
        violations = check_cross_scenario_prerequisites(results, dependencies)
        assert violations == []


# ---------------------------------------------------------------------------
# 3.6 Financial metrics
# ---------------------------------------------------------------------------


class TestFinancialMetrics:
    def test_mandatory_project_is_cost_only(self):
        financials = [ProjectFinancials(project_key="P-01", revenue_impact=[10, 10], capex=5, discount_rate=0.1)]
        results = compute_financial_metrics(financials, mandatory_project_keys={"P-01"})
        assert results[0].cost_only is True
        assert results[0].npv is None
        assert results[0].reason == "mandatory — return not computed"
        assert results[0].total_cost == 5

    def test_revenue_absent_is_cost_only(self):
        financials = [ProjectFinancials(project_key="P-05", revenue_impact=[], capex=100, opex_annual=10)]
        results = compute_financial_metrics(financials, mandatory_project_keys=set())
        assert results[0].cost_only is True
        assert results[0].npv is None
        assert results[0].reason == "revenue projections absent"
        assert results[0].total_cost == 110

    def test_missing_discount_rate_is_cost_only(self):
        financials = [ProjectFinancials(project_key="P-05", revenue_impact=[50, 50], capex=10)]
        results = compute_financial_metrics(financials, mandatory_project_keys=set())
        assert results[0].cost_only is True
        assert results[0].reason == "discount rate not supplied"

    def test_computes_npv_and_payback_when_data_present(self):
        financials = [
            ProjectFinancials(
                project_key="P-05",
                revenue_impact=[60, 60, 60],
                capex=100,
                opex_annual=10,
                discount_rate=0.10,
            )
        ]
        results = compute_financial_metrics(financials, mandatory_project_keys=set())
        result = results[0]
        assert result.cost_only is False
        assert result.npv is not None
        # net cash flow is 50/yr; payback lands during year 2 (100 / 50 = 2.0)
        assert result.payback_years == pytest.approx(2.0, abs=0.01)
