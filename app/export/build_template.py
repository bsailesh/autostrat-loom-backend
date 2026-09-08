"""
Generates app/export/template.docx -- the reference template docx_builder.py
opens with `Document('template.docx')` and builds every export against.

There's no way to hand-author a .docx (it's a zip of XML), so this script is
the source of truth for the template: run it whenever the styles need to
change, and commit the regenerated binary alongside it.

    python -m app.export.build_template

Defining styles programmatically inside docx_builder.py on every request
would work but is far worse (word_export_briefing.md, "python-docx
gotchas") -- a style defined once here is inherited by every export instead
of being rebuilt per request.
"""
from __future__ import annotations

import pathlib

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches

TEMPLATE_PATH = pathlib.Path(__file__).parent / "template.docx"

_INK = RGBColor(0x1A, 0x1A, 0x1A)
_MUTED = RGBColor(0x55, 0x55, 0x55)
_ACCENT = RGBColor(0x1F, 0x3A, 0x5F)
_BORDER = RGBColor(0xC8, 0xC8, 0xC8)


def build() -> None:
    doc = Document()

    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(0.9)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = _INK

    for level, size, color in ((1, 20, _ACCENT), (2, 15, _ACCENT), (3, 12.5, _INK)):
        style = doc.styles[f"Heading {level}"]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(14 if level == 1 else 10)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True

    # Based on Normal, not Heading 1: it needs to *look* like a big title
    # but must not carry an outline level, or the TOC field's "\o 1-2" scan
    # picks up the cover title itself as an entry.
    title_style = doc.styles.add_style("Loom Cover Title", WD_STYLE_TYPE.PARAGRAPH)
    title_style.base_style = doc.styles["Normal"]
    title_style.font.size = Pt(28)
    title_style.font.bold = True
    title_style.font.color.rgb = _ACCENT
    title_style.paragraph_format.space_before = Pt(14)
    title_style.paragraph_format.space_after = Pt(6)
    title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    subtitle_style = doc.styles.add_style("Loom Cover Subtitle", WD_STYLE_TYPE.PARAGRAPH)
    subtitle_style.base_style = doc.styles["Normal"]
    subtitle_style.font.size = Pt(13)
    subtitle_style.font.color.rgb = _MUTED

    caption_style = doc.styles.add_style("Loom Caption", WD_STYLE_TYPE.PARAGRAPH)
    caption_style.base_style = doc.styles["Normal"]
    caption_style.font.size = Pt(9.5)
    caption_style.font.italic = True
    caption_style.font.color.rgb = _MUTED
    caption_style.paragraph_format.space_before = Pt(2)
    caption_style.paragraph_format.space_after = Pt(8)
    caption_style.paragraph_format.keep_with_next = True

    so_what_style = doc.styles.add_style("Loom So What", WD_STYLE_TYPE.PARAGRAPH)
    so_what_style.base_style = doc.styles["Normal"]
    so_what_style.font.italic = True
    so_what_style.font.color.rgb = _MUTED
    so_what_style.paragraph_format.left_indent = Inches(0.25)
    so_what_style.paragraph_format.space_after = Pt(8)

    footnote_style = doc.styles.add_style("Loom Footnote", WD_STYLE_TYPE.PARAGRAPH)
    footnote_style.base_style = doc.styles["Normal"]
    footnote_style.font.size = Pt(9)
    footnote_style.font.color.rgb = _MUTED
    footnote_style.paragraph_format.space_before = Pt(2)

    mono_style = doc.styles.add_style("Loom Monospace", WD_STYLE_TYPE.PARAGRAPH)
    mono_style.base_style = doc.styles["Normal"]
    mono_style.font.name = "Consolas"
    mono_style.font.size = Pt(9)
    mono_style.paragraph_format.space_after = Pt(0)

    callout_label_style = doc.styles.add_style("Loom Callout Label", WD_STYLE_TYPE.CHARACTER)
    callout_label_style.font.bold = True
    callout_label_style.font.color.rgb = _ACCENT

    confidence_run_style = doc.styles.add_style("Loom Confidence Tag", WD_STYLE_TYPE.CHARACTER)
    confidence_run_style.font.bold = True

    footer_style = doc.styles.add_style("Loom Footer", WD_STYLE_TYPE.PARAGRAPH)
    footer_style.base_style = doc.styles["Normal"]
    footer_style.font.size = Pt(8.5)
    footer_style.font.color.rgb = _MUTED

    # A visible "Table Grid"-based style with explicit borders, used for the
    # cover/body Word tables (Key Insights box, callouts, exhibit tables).
    table_style = doc.styles.add_style("Loom Table", WD_STYLE_TYPE.TABLE)
    table_style.base_style = doc.styles["Table Grid"]
    table_style.font.size = Pt(9.5)

    doc.core_properties.title = "AutoStrat Loom Market Insights"
    doc.core_properties.author = "AutoStrat Loom"

    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(TEMPLATE_PATH))
    print(f"Wrote {TEMPLATE_PATH}")


if __name__ == "__main__":
    build()
