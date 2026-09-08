"""
Golden-fixture tests for app/export/markdown_parser.py.

These fixtures (tests/fixtures/reports/*.md) are real markdown from two
production Market Insights runs, saved specifically because the export
parser and the frontend's own markdown parsing are two independent
implementations of one contract -- and the subject-line format alone
already drifted between runs three days apart. These tests are the drift
alarm word_export_briefing.md calls for: if a future run's format moves in
a way this parser doesn't tolerate, one of these should fail loudly.
"""
import pathlib

from app.export import exhibits
from app.export.markdown_parser import (
    BulletListBlock,
    ExhibitBlock,
    Heading,
    KeyInsightsBox,
    SCQABlock,
    TableBlock,
    parse_report,
)

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "reports"


def _load(name: str) -> str:
    return (FIXTURES_DIR / f"{name}.md").read_text(encoding="utf-8")


def _headings(report):
    return [b for b in report.blocks if isinstance(b, Heading)]


def _confidence_tag_count(report):
    from app.export.markdown_parser import Paragraph

    return sum(
        1
        for b in report.blocks
        if isinstance(b, Paragraph)
        for r in b.runs
        if r.tag == "confidence"
    )


def _so_what_count(report):
    from app.export.markdown_parser import Paragraph

    return sum(1 for b in report.blocks if isinstance(b, Paragraph) and b.style == "so_what")


# ---------------------------------------------------------------------------
# act_report_01 -- Governing Insight, leading confidence tags, staleness flag
# ---------------------------------------------------------------------------


def test_act_report_01_governing_insight_and_body():
    report = parse_report(_load("act_report_01"), report_number=1)

    assert report.subject is not None
    assert "actuation" in report.subject.fields["subject"].lower()
    assert report.subject.fields["window"] == "Sept 2021 – Sept 2026"

    assert isinstance(report.opening, SCQABlock)
    assert report.opening.situation.startswith("Aircraft actuation")
    assert report.opening.complication.startswith("On a single day")
    assert report.opening.question.startswith("Over the next several years")
    assert report.opening.answer.startswith("On the evidence available")

    headings = _headings(report)
    exhibit_headings = [h for h in headings if h.is_exhibit]
    assert len(exhibit_headings) == 1
    assert exhibit_headings[0].text.startswith("Exhibit 1")
    assert any(h.text == "Confidence Summary" for h in headings)

    # Exhibit 1 table + the market-size triangulation step table.
    tables = [b for b in report.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 2

    # Multiple leading confidence tags: **FACT (High).**, **OBSERVATION (High).**, etc.
    assert _confidence_tag_count(report) >= 5

    # At least one "*So what:*" clause split into its own styled paragraph.
    assert _so_what_count(report) >= 5

    # The staleness flag is tagged on its run.
    from app.export.markdown_parser import Paragraph

    staleness_runs = [
        r for b in report.blocks if isinstance(b, Paragraph) for r in b.runs if r.tag == "staleness"
    ]
    assert len(staleness_runs) == 1
    assert staleness_runs[0].text.startswith("Staleness flag")

    assert report.warnings == []


# ---------------------------------------------------------------------------
# act_report_02 -- Key Insights, TAM/SAM/SOM exhibit
# ---------------------------------------------------------------------------


def test_act_report_02_key_insights_and_tam_sam_som():
    report = parse_report(_load("act_report_02"), report_number=2)

    assert isinstance(report.opening, KeyInsightsBox)
    assert len(report.opening.items) == 5
    confidences = [i.confidence for i in report.opening.items]
    assert confidences == ["High", "High", "Medium", "High", "High"]

    exhibit_blocks = [b for b in report.blocks if isinstance(b, ExhibitBlock)]
    assert len(exhibit_blocks) == 1
    tam_sam_som = exhibit_blocks[0].content
    assert isinstance(tam_sam_som, exhibits.TamSamSom)
    assert [r.label for r in tam_sam_som.rings] == ["TAM", "SAM", "SOM"]
    assert tam_sam_som.rings[0].status == "Low"
    assert "15.0bn" in tam_sam_som.rings[0].value
    assert tam_sam_som.rings[2].label == "SOM"
    assert tam_sam_som.rings[2].status == "Low"

    assert report.warnings == []


# ---------------------------------------------------------------------------
# act_report_04 -- Key Insights, Harvey Ball grid, horizontal rules
# ---------------------------------------------------------------------------


def test_act_report_04_harvey_ball_grid():
    report = parse_report(_load("act_report_04"), report_number=4)

    assert isinstance(report.opening, KeyInsightsBox)
    assert len(report.opening.items) == 5

    from app.export.markdown_parser import HorizontalRule

    assert sum(1 for b in report.blocks if isinstance(b, HorizontalRule)) == 3

    grids = [b for b in report.blocks if isinstance(b, exhibits.HarveyBallGrid)]
    assert len(grids) == 1
    grid = grids[0]
    assert len(grid.headers) == 6
    assert grid.headers[0] == "Feature"
    assert "Moog" in grid.headers[1]
    assert len(grid.rows) == 20  # word_export_briefing.md: "6-column, 20-row grid"
    assert grid.rows[0][1] == "●"  # Moog, portfolio breadth

    headings = _headings(report)
    exhibit_headings = [h for h in headings if h.is_exhibit]
    assert len(exhibit_headings) == 1
    assert "Harvey Ball" in exhibit_headings[0].text

    assert report.warnings == []


# ---------------------------------------------------------------------------
# rec_report_01 -- Governing Insight, body bullet lists (not a Key Insights box)
# ---------------------------------------------------------------------------


def test_rec_report_01_governing_insight_and_bullet_lists():
    report = parse_report(_load("rec_report_01"), report_number=1)

    assert isinstance(report.opening, SCQABlock)
    assert report.opening.answer.startswith("Advantage has migrated")

    assert report.subject.fields["subject"].startswith("Extended-duration flight recorders")
    assert report.subject.fields["window"].startswith("2021")

    bullet_lists = [b for b in report.blocks if isinstance(b, BulletListBlock)]
    assert len(bullet_lists) == 2

    tables = [b for b in report.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1  # Exhibit 1's developments table (the market-size table is a bullet list here)

    assert report.warnings == []


# ---------------------------------------------------------------------------
# rec_report_02 -- Key Insights ("·"-delimited subject), TAM/SAM/SOM exhibit
# ---------------------------------------------------------------------------


def test_rec_report_02_dot_delimited_subject_and_tam_sam_som():
    report = parse_report(_load("rec_report_02"), report_number=2)

    # This subject line uses "·" as its delimiter, not "|" -- format drift
    # this parser must tolerate (word_export_briefing.md).
    assert report.subject.fields["subject"].startswith("Market landscape for 25-hour CVR")
    assert report.subject.fields["evidence_base"].startswith("Tier 2 public sources only")
    assert report.subject.fields["window"] == "2020–Sep 2026"

    assert isinstance(report.opening, KeyInsightsBox)
    assert len(report.opening.items) == 5

    exhibit_blocks = [b for b in report.blocks if isinstance(b, ExhibitBlock)]
    assert len(exhibit_blocks) == 1
    tam_sam_som = exhibit_blocks[0].content
    assert isinstance(tam_sam_som, exhibits.TamSamSom)
    assert [r.label for r in tam_sam_som.rings] == ["TAM", "SAM", "SOM"]
    assert "178" in tam_sam_som.rings[0].value
    assert tam_sam_som.rings[0].status == "GROWTH"

    headings = _headings(report)
    exhibit_headings = [h for h in headings if h.is_exhibit]
    assert {h.text.split(" —")[0] for h in exhibit_headings} == {"Exhibit 2A", "Exhibit 2B"}

    assert report.warnings == []


# ---------------------------------------------------------------------------
# rec_report_03 -- Key Insights, fenced brand-map fallback exhibit
# ---------------------------------------------------------------------------


def test_rec_report_03_fallback_exhibit():
    report = parse_report(_load("rec_report_03"), report_number=3)

    assert isinstance(report.opening, KeyInsightsBox)
    assert len(report.opening.items) == 5

    # Third leading-confidence-tag convention: spelled out after an em dash
    # ("FACT — High confidence"), not the parenthetical "(High)" form or the
    # trailing "(Confidence: X)"/"[X]" Key Insights forms. Every bullet here
    # uses it, so this is exactly the fixture that should catch a regression.
    assert [i.confidence for i in report.opening.items] == [
        "High",
        "High",
        "Medium/High",
        "High",
        "Medium",
    ]
    assert report.opening.items[0].lead == "FACT — High confidence"

    exhibit_blocks = [b for b in report.blocks if isinstance(b, ExhibitBlock)]
    assert len(exhibit_blocks) == 1
    fallback = exhibit_blocks[0].content
    assert isinstance(fallback, exhibits.FallbackExhibit)
    assert "DESIGN AUTHORITY" in fallback.raw_text
    assert "Acron Aviation" in fallback.raw_text

    tables = [b for b in report.blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1  # the competitor activity table

    assert report.warnings == []


# ---------------------------------------------------------------------------
# Cross-fixture tolerance checks
# ---------------------------------------------------------------------------


def test_parser_never_raises_on_any_fixture():
    for name in [
        "act_report_01",
        "act_report_02",
        "act_report_04",
        "rec_report_01",
        "rec_report_02",
        "rec_report_03",
    ]:
        report = parse_report(_load(name), report_number=1)
        assert report.blocks, f"{name}: parser produced no blocks at all"


def test_malformed_markdown_degrades_instead_of_raising():
    garbage = "### unterminated **bold\n\n| broken | table\n|---\nrow\n\n```\nfence never closes"
    report = parse_report(garbage, report_number=99)
    assert report.blocks  # something came out, no exception
