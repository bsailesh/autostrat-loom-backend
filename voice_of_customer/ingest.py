"""
Voice of Customer Agent (Agent 1) — evidence ingest: text, PDF and CSV.

New infrastructure; neither Market Insights nor Tech & Regulation has it.
DB-free like the rest of the package: each parser takes a binary file
object and YIELDS items one at a time, so the service layer can write them
to the database in batches without the whole document ever being held in
memory. The production instance has 414MB of RAM.

Office formats (.docx, .xlsx, .msg) are deferred in v1 and rejected with a
message naming the supported formats. There is no OCR: a PDF with no
extractable text is almost certainly a scanned image, and it is rejected
with that specific message rather than stored as an empty document that
would let a run believe it had evidence.
"""
from __future__ import annotations

import csv
import io
import os
from typing import BinaryIO, Iterator

# Stated in the error. Ticket exports can be large; this bounds both the
# upload and the per-row ingest the service performs on it.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

SUPPORTED_EXTENSIONS = {".txt": "text", ".md": "text", ".pdf": "pdf", ".csv": "csv"}
_DEFERRED_OFFICE = {".docx", ".doc", ".xlsx", ".xls", ".msg", ".pptx"}

SUPPORTED_FORMATS_TEXT = "text (.txt, .md), PDF (.pdf) and CSV (.csv)"

SCANNED_PDF_MESSAGE = (
    "This PDF contains no extractable text, so it is almost certainly a scanned image. "
    "OCR is not supported. Export the document as a text-based PDF, a .txt file or a CSV, "
    "and upload that instead."
)

# A text document is stored in sections of about this size, split at a
# paragraph boundary, so the prompt can show evenly spaced passages of a long
# document rather than only its opening.
TEXT_SECTION_CHARS = 4_000

# Free-text ticket descriptions routinely exceed csv's 128KB default field
# limit in real exports; a row that big is still one ticket.
_CSV_FIELD_LIMIT = 1024 * 1024


class IngestRejected(Exception):
    """A file that will not be stored, with the message the customer sees."""


def upload_too_large_message(size: int) -> str:
    return (
        f"File is {size / (1024 * 1024):.1f} MB; the upload limit is "
        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB per file. Split the export by period and upload "
        "each part as its own file."
    )


def detect_format(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[ext]
    if ext in _DEFERRED_OFFICE:
        raise IngestRejected(
            f"{ext} files are not accepted in this version. Supported formats: "
            f"{SUPPORTED_FORMATS_TEXT}. Save the document as PDF or text, or a spreadsheet as CSV."
        )
    raise IngestRejected(
        f"Unsupported file format {ext or '(no extension)'!r}. Supported formats: {SUPPORTED_FORMATS_TEXT}."
    )


def _text_stream(fileobj: BinaryIO) -> io.TextIOWrapper:
    """utf-8 (tolerating an Excel BOM); undecodable bytes become U+FFFD
    rather than failing the whole upload, since one bad byte in a 40,000-row
    export should not cost the other 39,999."""
    fileobj.seek(0)
    return io.TextIOWrapper(fileobj, encoding="utf-8-sig", errors="replace", newline="")


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def iter_text_sections(fileobj: BinaryIO) -> Iterator[tuple[int, str]]:
    stream = _text_stream(fileobj)
    try:
        seq = 0
        buf: list[str] = []
        size = 0
        for line in stream:
            buf.append(line)
            size += len(line)
            if size >= TEXT_SECTION_CHARS and not line.strip():
                seq += 1
                yield seq, "".join(buf).strip("\n")
                buf, size = [], 0
            elif size >= TEXT_SECTION_CHARS * 2:
                # no paragraph break in sight -- split anyway, at a line end
                seq += 1
                yield seq, "".join(buf).strip("\n")
                buf, size = [], 0
        if "".join(buf).strip():
            seq += 1
            yield seq, "".join(buf).strip("\n")
    finally:
        stream.detach()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _pdf_reader(fileobj: BinaryIO):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    fileobj.seek(0)
    try:
        return PdfReader(fileobj)
    except (PdfReadError, ValueError, OSError) as exc:
        raise IngestRejected(f"This file could not be read as a PDF ({exc}).") from None


def pdf_page_count_with_text(fileobj: BinaryIO) -> int:
    """Total pages, after confirming at least one has extractable text --
    stopping at the first that does, so a normal PDF is not extracted twice
    in full. Raises IngestRejected with the scanned-PDF message otherwise."""
    reader = _pdf_reader(fileobj)
    for page in reader.pages:
        if (page.extract_text() or "").strip():
            return len(reader.pages)
    raise IngestRejected(SCANNED_PDF_MESSAGE)


def iter_pdf_pages(fileobj: BinaryIO) -> Iterator[tuple[int, str]]:
    reader = _pdf_reader(fileobj)
    for i, page in enumerate(reader.pages, start=1):
        yield i, (page.extract_text() or "").strip()


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _clean_header(raw: list[str]) -> list[str]:
    """Blank headers become column_N and duplicates get a suffix, so every
    cell has a stable key. Names are otherwise kept verbatim -- they are
    shown back to the customer for role mapping."""
    seen: dict[str, int] = {}
    out = []
    for i, name in enumerate(raw, start=1):
        name = (name or "").strip() or f"column_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out


def read_csv_header(fileobj: BinaryIO) -> list[str]:
    csv.field_size_limit(_CSV_FIELD_LIMIT)
    stream = _text_stream(fileobj)
    try:
        header = next(csv.reader(stream), None)
    finally:
        stream.detach()
    if not header or not any((h or "").strip() for h in header):
        raise IngestRejected("This CSV has no header row. The first row must name the columns.")
    return _clean_header(header)


def iter_csv_rows(fileobj: BinaryIO) -> Iterator[tuple[int, dict]]:
    """(row number, {column: value}) for every data row, skipping fully blank
    rows. Cells beyond the header are kept under "_extra" rather than
    dropped."""
    csv.field_size_limit(_CSV_FIELD_LIMIT)
    stream = _text_stream(fileobj)
    try:
        reader = csv.reader(stream)
        header = _clean_header(next(reader, []) or [])
        seq = 0
        for raw in reader:
            if not any((c or "").strip() for c in raw):
                continue
            seq += 1
            cells = {h: (raw[i] if i < len(raw) else "") for i, h in enumerate(header)}
            if len(raw) > len(header):
                cells["_extra"] = " | ".join(raw[len(header):])
            yield seq, cells
    finally:
        stream.detach()


def cells_char_count(cells: dict) -> int:
    return sum(len(str(v)) for v in cells.values())
