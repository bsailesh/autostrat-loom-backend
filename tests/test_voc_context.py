"""
Tests for voice_of_customer/context.py: operating tier, per-analysis
availability, degradation consequences, and the Tier 2 title.

DB-free, like the package.
"""
from voice_of_customer.context import (
    TIER_1_PARTIAL,
    TIER_1_SUBSTANTIAL,
    TIER_2,
    TIER_2_TITLE,
    Channel,
    Customer,
    CustomerContext,
    EvidenceFile,
    KnownPainPoint,
    ProductCategory,
    Segment,
    analysis_availability,
    context_items,
    operating_tier,
    operating_tier_statement,
    render_context_text,
    report_title,
    run_label,
)


def _file(file_type: str, name: str | None = None, **kw) -> EvidenceFile:
    return EvidenceFile(
        file_id=f"id-{name or file_type}",
        file_type=file_type,
        file_format=kw.pop("file_format", "csv"),
        filename=name or f"{file_type}.csv",
        **kw,
    )


def _arden(**overrides) -> CustomerContext:
    base = dict(
        segments=[
            Segment("OEM-PRIME", "Prime contractors", "", 6),
            Segment("OPERATOR", "End operators", "", None),
        ],
        channels=[Channel("Field service", "inbound", "Primary source of failure reports")],
        customers=[Customer("Northwind Defence", "OEM-PRIME")],
        known_pain_points=[
            KnownPainPoint("Primes say our lead times are the longest in the qualified set", "OEM-PRIME"),
        ],
        categories=[ProductCategory("EMA-FIN", "Missile fin actuation", source="tech-regulation")],
    )
    base.update(overrides)
    return CustomerContext(**base)


class TestTierDetermination:
    def test_no_evidence_is_tier_2(self):
        assert operating_tier(_arden()) == TIER_2

    def test_some_evidence_is_tier_1_partial(self):
        ctx = _arden(evidence=[_file("support_tickets")])
        assert operating_tier(ctx) == TIER_1_PARTIAL

    def test_five_of_six_analyses_is_substantial(self):
        ctx = _arden(
            evidence=[
                _file("support_tickets", column_roles={"segment": "Segment"}),  # frequency, sentiment, clustering
                _file("visit_interview_notes", file_format="text"),  # personas
            ]
        )
        # four of six: feature requests and win/loss missing -- still partial
        assert operating_tier(ctx) == TIER_1_PARTIAL
        ctx = _arden(evidence=[*ctx.evidence, _file("win_loss_reports", file_format="pdf")])
        assert operating_tier(ctx) == TIER_1_SUBSTANTIAL

    def test_segment_clustering_needs_attribution_not_a_type(self):
        unattributed = _arden(evidence=[_file("support_tickets")])
        attributed = _arden(evidence=[_file("support_tickets", segment_coverage=("OEM-PRIME",))])
        by_key = lambda ctx: {a.key: a for a in analysis_availability(ctx)}
        assert not by_key(unattributed)["segment_clustering"].available
        assert by_key(attributed)["segment_clustering"].available


class TestAnalysisAvailability:
    def test_each_analysis_names_the_source_that_enabled_it(self):
        ctx = _arden(evidence=[_file("warranty_claims", "claims_fy26.csv")])
        freq = next(a for a in analysis_availability(ctx) if a.key == "pain_point_frequency")
        assert freq.available and freq.enabled_by == ["claims_fy26.csv"]

    def test_unavailable_analysis_names_what_it_needs(self):
        win_loss = next(a for a in analysis_availability(_arden()) if a.key == "win_loss")
        assert not win_loss.available
        assert "Win/loss reports" in win_loss.note

    def test_sample_only_source_is_flagged_as_never_a_census(self):
        ctx = _arden(evidence=[_file("support_tickets", is_sample=True)])
        freq = next(a for a in analysis_availability(ctx) if a.key == "pain_point_frequency")
        assert freq.available
        assert "never a census" in freq.note

    def test_belief_testing_unavailable_without_recorded_beliefs(self):
        ctx = _arden(known_pain_points=[], evidence=[_file("support_tickets")])
        belief = next(a for a in analysis_availability(ctx) if a.key == "belief_testing")
        assert not belief.available
        assert "No known pain points" in belief.note


class TestTier2IsUnmissable:
    def test_tier_2_report_title(self):
        assert report_title(TIER_2, "Executive summary") == f"{TIER_2_TITLE} — Executive summary"
        assert TIER_2_TITLE == "External customer-context analysis"
        assert report_title(TIER_1_PARTIAL, "Executive summary") == "Executive summary"

    def test_tier_2_run_label(self):
        assert run_label(TIER_2) == "External Customer-Context Analysis"
        assert run_label(TIER_1_SUBSTANTIAL) == "Voice of Customer"

    def test_tier_2_statement_reports_each_analysis_unavailable(self):
        line = operating_tier_statement(_arden())
        assert line.startswith("**Operating tier: TIER 2")
        assert "NOT a voice of customer analysis" in line
        for unavailable in ("sentiment", "frequency", "personas", "win/loss"):
            assert unavailable in line.lower()
        assert "persona hypotheses to validate" in line

    def test_partial_statement_names_enabled_and_missing(self):
        line = operating_tier_statement(_arden(evidence=[_file("support_tickets", "tix.csv")]))
        assert "TIER 1 PARTIAL" in line
        assert "tix.csv" in line
        assert "Win/loss rationale" in line


class TestContextState:
    def test_consequence_is_empty_for_every_set_item(self):
        ctx = _arden(evidence=[_file("support_tickets")])
        for item in context_items(ctx):
            if item.status == "set":
                assert item.consequence == "", item.key
            else:
                assert item.consequence, item.key

    def test_missing_evidence_is_the_most_consequential_omission(self):
        evidence = next(i for i in context_items(_arden()) if i.key == "evidence")
        assert evidence.status == "missing"
        assert "single most consequential omission" in evidence.consequence

    def test_known_pain_points_consequence_when_missing(self):
        item = next(i for i in context_items(_arden(known_pain_points=[])) if i.key == "known_pain_points")
        assert "highest-value analysis is unavailable" in item.consequence


class TestRenderContext:
    def test_unknown_segment_size_stays_unknown(self):
        text = render_context_text(_arden())
        assert "approximate count: unknown" in text
        assert "approximate count: 0" not in text

    def test_research_rendering_withholds_named_customers(self):
        assert "Northwind Defence" in render_context_text(_arden(), include_customers=True)
        assert "Northwind Defence" not in render_context_text(_arden(), include_customers=False)
