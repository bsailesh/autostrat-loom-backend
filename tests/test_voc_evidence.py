"""
Tests for voice_of_customer/evidence.py -- the rule that customer verbatims
are never summarised: counts come from every row, only the choice of which
rows to quote is sampled, and both are stated.
"""
import re

from voice_of_customer import evidence as ev
from voice_of_customer.context import EvidenceFile


def _csv_meta(row_count: int, **kw) -> EvidenceFile:
    return EvidenceFile(
        file_id=kw.pop("file_id", "file-1"),
        file_type="support_tickets",
        file_format="csv",
        filename=kw.pop("filename", "tickets.csv"),
        row_count=row_count,
        columns=("Date", "Category", "Description"),
        row_unit=kw.pop("row_unit", "ticket"),
        column_roles=kw.pop("column_roles", {"date": "Date", "category": "Category", "description": "Description"}),
        char_count=kw.pop("char_count", row_count * 60),
        **kw,
    )


def _rows(n: int, categories=("Integration", "Lead time", "Diagnosis"), weights=(6, 3, 1)):
    pattern = [c for c, w in zip(categories, weights) for _ in range(w)]
    for i in range(1, n + 1):
        cat = pattern[(i - 1) % len(pattern)]
        yield i, {"Date": f"2026-{(i % 12) + 1:02d}-15", "Category": cat, "Description": f"ticket text {i}"}


class TestCountsComeFromEveryRow:
    def test_large_csv_counts_cover_all_rows_while_verbatims_are_sampled(self):
        out = ev.render_csv(_csv_meta(5_000), _rows(5_000), budget=20_000)
        # exact counts over all 5,000 rows: 6/10, 3/10, 1/10
        assert "Integration: 3,000" in out.text
        assert "Lead time: 1,500" in out.text
        assert "Diagnosis: 500" in out.text
        assert "exact, not sampled" in out.text
        shown = len(re.findall(r"^\[row \d+\]", out.text, re.MULTILINE))
        assert 0 < shown < 5_000
        assert f"{shown:,} of 5,000 rows sampled verbatim" in out.sampling_note
        assert "counts cover every row" in out.sampling_note

    def test_sample_is_stratified_with_every_category_represented(self):
        out = ev.render_csv(_csv_meta(5_000), _rows(5_000), budget=6_000)
        quoted = re.findall(r"Category: (\w[\w ]*?) \|", out.text)
        assert {"Integration", "Lead time", "Diagnosis"} <= set(quoted)
        assert "stratified by category" in out.sampling_note

    def test_sample_is_deterministic_for_the_same_file(self):
        a = ev.render_csv(_csv_meta(2_000), _rows(2_000), budget=8_000)
        b = ev.render_csv(_csv_meta(2_000), _rows(2_000), budget=8_000)
        assert a.text == b.text

    def test_month_counts_cover_all_rows(self):
        out = ev.render_csv(_csv_meta(1_200), _rows(1_200), budget=10_000)
        assert "2026-01: 100" in out.text

    def test_without_mapped_columns_theme_frequency_is_an_estimate(self):
        meta = _csv_meta(1_000, column_roles={})
        out = ev.render_csv(meta, _rows(1_000), budget=10_000)
        assert "ESTIMATE" in out.text
        assert "only the total row count is exact" in out.sampling_note


class TestSmallFiles:
    def test_small_csv_is_passed_whole(self):
        out = ev.render_csv(_csv_meta(50), _rows(50), budget=50_000)
        assert len(re.findall(r"^\[row \d+\]", out.text, re.MULTILINE)) == 50
        assert "all 50 rows passed verbatim; nothing sampled" in out.sampling_note

    def test_small_csv_too_big_for_its_budget_is_sampled_not_cut_off(self):
        out = ev.render_csv(_csv_meta(300), _rows(300), budget=4_000)
        assert "sampled verbatim" in out.sampling_note
        assert "in file order" not in out.sampling_note

    def test_long_verbatim_is_cut_with_a_marker_not_reworded(self):
        long_text = "x" * 5_000
        rows = [(1, {"Date": "2026-01-01", "Category": "A", "Description": long_text})]
        out = ev.render_csv(_csv_meta(1), iter(rows), budget=50_000)
        assert f"[truncated at {ev.VERBATIM_MAX_CHARS:,} of" in out.text


class TestSampleVersusCensus:
    def test_is_sample_is_carried_into_the_prompt(self):
        meta = _csv_meta(100, is_sample=True, sample_description="Q3 tickets from two regions only")
        out = ev.render_csv(meta, _rows(100), budget=50_000)
        assert "COMPLETENESS: SAMPLE — Q3 tickets from two regions only" in out.text
        assert "NOT a census" in out.text
        assert "in the sample supplied" in out.text

    def test_complete_file_is_declared_complete(self):
        out = ev.render_csv(_csv_meta(10), _rows(10), budget=50_000)
        assert "declared complete" in out.text
        assert "SAMPLE" not in out.text.split("COMPLETENESS:")[1].split("\n")[0]

    def test_unstated_row_unit_is_called_out(self):
        out = ev.render_csv(_csv_meta(10, row_unit=""), _rows(10), budget=50_000)
        assert "what one row represents was not stated" in out.text


class TestCustomerValuesForTheAttributionCheck:
    def test_customer_column_values_are_collected_from_every_row(self):
        meta = _csv_meta(2_000, column_roles={"customer": "Customer"}, )
        rows = ((i, {"Customer": f"Cust {i % 7}", "Description": "d"}) for i in range(1, 2_001))
        out = ev.render_csv(meta, rows, budget=5_000)
        assert out.customer_values == frozenset(f"Cust {i}" for i in range(7))


class TestBudgetAllocation:
    def _f(self, fid, chars):
        return EvidenceFile(file_id=fid, file_type="survey_responses", file_format="text", filename=fid, char_count=chars)

    def test_small_files_get_what_they_need_and_the_rest_is_shared(self):
        files = [self._f("small", 2_000), self._f("big1", 900_000), self._f("big2", 300_000)]
        alloc = ev.allocate_budget(files)
        assert alloc["small"] == ev.estimated_need(files[0])
        assert sum(alloc.values()) <= ev.EVIDENCE_BUDGET_CHARS
        assert alloc["big1"] > alloc["big2"] >= ev.PER_FILE_FLOOR_CHARS

    def test_floor_holds(self):
        files = [self._f("tiny-share", 20_000), self._f("huge", 5_000_000)]
        alloc = ev.allocate_budget(files)
        assert alloc["tiny-share"] >= min(ev.PER_FILE_FLOOR_CHARS, ev.estimated_need(files[0]))


class TestDocuments:
    def _meta(self, chars, pages):
        return EvidenceFile(
            file_id="doc", file_type="visit_interview_notes", file_format="pdf",
            filename="visits.pdf", page_count=pages, char_count=chars,
        )

    def test_small_document_is_complete(self):
        pages = [(i, f"page {i} text") for i in range(1, 4)]
        out = ev.render_document(self._meta(30, 3), iter(pages), 3, budget=10_000)
        assert "complete — all 3 pages passed verbatim" in out.sampling_note

    def test_large_document_is_evenly_spaced_passages_never_summarised(self):
        pages = [(i, "w" * 1_000) for i in range(1, 41)]
        out = ev.render_document(self._meta(40_000, 40), iter(pages), 40, budget=12_000)
        assert "of 40 passed verbatim as evenly spaced unedited passages" in out.sampling_note
        assert "nothing was summarised" in out.sampling_note
        assert "[page 1]" in out.text and "[page 40]" in out.text

    def test_no_evidence_renders_tier_2_instruction(self):
        assert "NO CUSTOMER EVIDENCE WAS SUPPLIED" in ev.render_evidence_text([])
