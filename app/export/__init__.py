"""Word (.docx) export for Market Insights report packs.

Pipeline: markdown_parser.py (report markdown -> intermediate structure) ->
docx_builder.py (structure -> bytes), with exhibits.py handling the fenced
and table-shaped exhibit blocks that don't map to plain prose. See
word_export_briefing.md at the repo root for the full contract.
"""
