"""
Tests for `tech_regulation/scoping.py` -- the applicability envelope's
operating state, the degradation table, and the rendering the prompts use.

No database and no client: scoping is plain data by design, exactly as
strategy_synthesis/brief.py is, so this file needs neither.
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

from tech_regulation.scoping import (
    PARTIALLY_SCOPED,
    SCOPED,
    UNSCOPED,
    UNSCOPED_TITLE_PREFIX,
    CertificationBasis,
    Exclusion,
    Jurisdiction,
    Platform,
    ProductCategory,
    ScopingEnvelope,
    StandardHeld,
    Supplier,
    missing_labels,
    operating_state,
    operating_state_statement,
    render_envelope_text,
    report_title,
    scope_items,
)


def _arden() -> ScopingEnvelope:
    """The worked example from the scoping spec's Part 6, complete."""
    return ScopingEnvelope(
        categories=[
            ProductCategory("EMA-FIN", "Missile fin actuation", "EM fin actuators for tactical missiles"),
            ProductCategory("EMA-TVC", "Thrust vector control", "Launch vehicle and upper stage TVC"),
            ProductCategory("EMA-UTIL", "Utility actuation", "Door, hatch and secondary system actuators"),
        ],
        jurisdictions=[
            Jurisdiction("United States", "primary"),
            Jurisdiction("European Union", "primary"),
            Jurisdiction("United Kingdom", "secondary"),
        ],
        certification_basis=[
            CertificationBasis("EMA-FIN", "MIL-STD", "MIL-STD-810H", "qualified", "2021"),
            CertificationBasis("EMA-UTIL", "TSO", "TSO-C196b", "approved", "2019"),
            CertificationBasis("EMA-UTIL", "Part", "14 CFR Part 25", "installed on", "2019"),
        ],
        platforms=[
            Platform("Tactical missile — surface launched", "Defence guided weapons", "shipping", "active production"),
            Platform("Narrowbody commercial", "Part 25 transport", "pursuing", "design-in window"),
        ],
        standards_held=[
            StandardHeld("DO-160", "G", "Environmental qualification", "compliant"),
            StandardHeld("DO-254", "", "Airborne electronic hardware", "in_progress"),
        ],
        suppliers=[
            Supplier("Vendor A", "GaN power devices", "single_source"),
            Supplier("Vendor B", "Roller screws", "dual_sourced"),
        ],
        domains=["Electrification", "Advanced air mobility", "Space systems"],
        exclusions=[
            Exclusion("platform_class", "Part 23 general aviation", "not a market we serve"),
            Exclusion("jurisdiction", "China", "no sales or certification intent"),
        ],
    )


class TestOperatingState:
    def test_a_complete_envelope_is_scoped(self):
        assert operating_state(_arden()) == SCOPED
        assert missing_labels(_arden()) == []

    def test_no_product_categories_is_unscoped_whatever_else_is_supplied(self):
        """Categories are the hinge: without them there is nothing to attach a
        finding to, so the degradation table calls this an unscoped run even
        when every other dimension is present."""
        envelope = ScopingEnvelope(
            jurisdictions=[Jurisdiction("United States")],
            certification_basis=[CertificationBasis("X", "TSO", "TSO-C196b")],
            platforms=[Platform("Narrowbody commercial")],
            standards_held=[StandardHeld("DO-160", "G")],
            suppliers=[Supplier("Vendor A")],
            domains=["Electrification"],
            exclusions=[Exclusion("jurisdiction", "China")],
        )
        assert operating_state(envelope) == UNSCOPED

    def test_categories_with_a_missing_dimension_is_partially_scoped(self):
        envelope = ScopingEnvelope(categories=[ProductCategory("EMA-FIN", "Fin actuation")])
        assert operating_state(envelope) == PARTIALLY_SCOPED

    def test_an_empty_envelope_is_unscoped(self):
        assert operating_state(ScopingEnvelope()) == UNSCOPED

    def test_tier1_evidence_alone_does_not_make_a_run_scoped(self):
        """From the scoping spec: a run with the envelope and no documents is a
        legitimate scoped run; a run with documents and no envelope is not,
        because nothing tells the agent what applies."""
        envelope = ScopingEnvelope(
            tier1_evidence_supplied=["Technology roadmap", "Certification documentation"]
        )
        assert operating_state(envelope) == UNSCOPED


class TestDegradationTable:
    def test_a_set_item_carries_no_consequence_text(self):
        """The bug fixed in b4f3282 for Agent 5's /readiness: consequence text
        shown alongside a satisfied item reads as a warning about something
        that is actually fine."""
        items = scope_items(_arden())
        assert items, "expected one item per envelope dimension"
        for item in items:
            assert item.status == "set", item.key
            assert item.consequence == "", item.key

    def test_every_dimension_is_reported_set_or_missing(self):
        items = scope_items(ScopingEnvelope())
        assert len(items) == 8
        assert {i.status for i in items} == {"missing"}
        assert all(i.consequence for i in items)

    def test_certification_basis_is_named_the_most_consequential_omission(self):
        items = {i.key: i for i in scope_items(ScopingEnvelope())}
        assert "most consequential" in items["certification_basis"].consequence

    def test_counts_are_reported_per_dimension(self):
        items = {i.key: i for i in scope_items(_arden())}
        assert items["product_categories"].count == 3
        assert items["certification_basis"].count == 3
        assert items["exclusions"].count == 2

    def test_a_partially_scoped_run_names_what_is_missing_and_its_cost(self):
        envelope = ScopingEnvelope(
            categories=[ProductCategory("EMA-UTIL", "Utility actuation")],
            jurisdictions=[Jurisdiction("United States")],
        )
        statement = operating_state_statement(envelope)
        assert "PARTIALLY SCOPED" in statement
        assert "Certification basis" in statement
        assert "most consequential" in statement
        assert "Standards held" in statement


class TestUnscopedIsUnmissable:
    def test_the_statement_says_it_is_not_the_customers_obligations(self):
        statement = operating_state_statement(ScopingEnvelope())
        assert "UNSCOPED" in statement
        assert "industry survey" in statement
        assert "NOT an assessment" in statement

    def test_report_titles_are_prefixed_when_unscoped(self):
        assert report_title(UNSCOPED, "Regulatory landscape") == (
            f"{UNSCOPED_TITLE_PREFIX}Regulatory landscape"
        )

    def test_report_titles_are_untouched_when_scoped_or_partially_scoped(self):
        assert report_title(SCOPED, "Regulatory landscape") == "Regulatory landscape"
        assert report_title(PARTIALLY_SCOPED, "Regulatory landscape") == "Regulatory landscape"

    def test_a_scoped_statement_does_not_warn(self):
        statement = operating_state_statement(_arden())
        assert "SCOPED" in statement
        assert "UNSCOPED" not in statement
        assert "industry survey" not in statement


class TestEnvelopeRendering:
    def test_customer_vocabulary_is_rendered_verbatim(self):
        text = render_envelope_text(_arden())
        for token in (
            "EMA-UTIL", "TSO-C196b", "14 CFR Part 25", "MIL-STD-810H",
            "Narrowbody commercial", "Advanced air mobility", "Vendor A", "DO-254",
        ):
            assert token in text, token

    def test_platform_relationship_is_rendered_because_it_changes_the_reading(self):
        text = render_envelope_text(_arden())
        assert "relationship: pursuing" in text
        assert "relationship: shipping" in text

    def test_exclusions_are_rendered_with_an_instruction_to_state_them(self):
        text = render_envelope_text(_arden())
        assert "Part 23 general aviation" in text
        assert "STATE them as excluded" in text

    def test_missing_dimensions_and_their_cost_reach_the_prompt(self):
        text = render_envelope_text(
            ScopingEnvelope(categories=[ProductCategory("EMA-UTIL", "Utility actuation")])
        )
        assert "What is missing from this envelope" in text
        assert "Certification basis" in text

    def test_empty_dimensions_render_as_none_supplied_not_as_a_blank(self):
        text = render_envelope_text(ScopingEnvelope())
        assert text.count("(none supplied)") >= 8
