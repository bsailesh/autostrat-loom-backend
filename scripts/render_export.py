"""
Renders a .docx from the golden fixtures for visual QA of the export pipeline,
and prints the exact commands to convert it to page images.

word_export_briefing.md is explicit that a 200 response proves nothing --
someone has to actually look at the rendered pages. This script exists so
that step is a documented, repeatable command rather than something a
reviewer has to reconstruct from scratch:

    python -m scripts.render_export
    python -m scripts.render_export --output my_preview.docx

It builds one synthetic report pack out of all six committed fixtures
(tests/fixtures/reports/) rather than a real 9-report run, because that's
the maximum-coverage set already saved specifically for this purpose: both
Governing Insight and Key Insights, both confidence-tag conventions, the
Harvey Ball grid, both TAM/SAM/SOM exhibits, and the ASCII fallback exhibit,
across both production runs' subject-line formats. It is not a real run --
report numbers/titles are relabelled per-source so the pack reads sensibly
in the TOC.

soffice (LibreOffice headless) and pdftoppm (poppler-utils) aren't installed
in this dev environment, so this script does not attempt to run the
conversion itself -- it prints the commands so whoever has them installed
(or the CI box, or the Lightsail instance per word_export_briefing.md) can
run the actual visual check before merging.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.export.docx_builder import ExportBuilder  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "reports"

# (fixture file stem, report_number, title) -- report_number only affects
# ordering/logging, not GI-vs-KI rendering (that's driven by which heading
# is actually present in the markdown), so it's safe to renumber sequentially
# across the two source runs.
PACK = [
    ("act_report_01", 1, "Executive Market Summary (actuation run)"),
    ("act_report_02", 2, "Market Landscape Report (actuation run)"),
    ("act_report_04", 3, "Competitive Feature Comparison Matrix (actuation run)"),
    ("rec_report_01", 4, "Executive Market Summary (flight recorders run)"),
    ("rec_report_02", 5, "Market Landscape Report (flight recorders run)"),
    ("rec_report_03", 6, "Competitor Intelligence Report (flight recorders run)"),
]


def build(output_path: pathlib.Path) -> None:
    builder = ExportBuilder()
    builder.add_cover_page(
        scope_summary=(
            "QA preview pack -- not a real run. Combines all six golden "
            "fixtures (both production runs) for maximum exhibit coverage."
        ),
        run_date="2026-09-08",
    )
    builder.add_toc()

    for stem, report_number, title in PACK:
        markdown_text = (FIXTURES_DIR / f"{stem}.md").read_text(encoding="utf-8")
        builder.add_report(markdown_text, report_number=report_number, title=title)

    output_path.write_bytes(builder.to_bytes())


def _print_verification_commands(output_path: pathlib.Path) -> None:
    pdf_path = output_path.with_suffix(".pdf")
    page_prefix = output_path.with_suffix("").name + "_page"
    print()
    print("Rendered:", output_path)
    print()
    print("To visually verify (word_export_briefing.md, 'Verification'):")
    print()
    print(f'    soffice --headless --convert-to pdf --outdir "{output_path.parent}" "{output_path}"')
    print(f'    pdftoppm -jpeg -r 100 "{pdf_path}" "{output_path.parent / page_prefix}"')
    print()
    print("Then look at each page and confirm: cover correct; TOC present (after")
    print("accepting the 'update fields' prompt); page breaks between reports;")
    print("Governing Insight only on the two Executive Market Summary reports;")
    print("Key Insights elsewhere; Harvey Ball symbols all render in one consistent")
    print("font; that grid's section is landscape and fits; TAM/SAM/SOM nested boxes")
    print("are correct on both Market Landscape reports; the fallback ASCII exhibit")
    print("is bordered and unwrapped; footers correct on every page but the cover;")
    print("no black cells; no stray bullets. Also open the .docx directly in Word")
    print("or Google Docs at least once and confirm there's no repair prompt.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("export_preview.docx"),
        help="Where to write the rendered .docx (default: ./export_preview.docx)",
    )
    args = parser.parse_args()

    build(args.output)
    _print_verification_commands(args.output)


if __name__ == "__main__":
    main()
