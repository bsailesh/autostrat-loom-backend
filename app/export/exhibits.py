"""
Handlers for the "exotic" exhibit shapes: fenced code blocks that aren't code,
and markdown tables that are actually Harvey Ball grids.

Only 5 of 18 production reports contain a fenced block, and they share nothing
but their triple-backtick fences (see word_export_briefing.md). The dispatcher
here sniffs each fence's content and routes it to the one handler we build
(TAM/SAM/SOM nested rings) or to a deliberate preformatted fallback. Harvey
Ball grids aren't fenced at all -- they're ordinary markdown tables whose
cells are mostly geometric glyphs -- so that detection lives here too, applied
by the parser to every table it sees.

Nothing in this module touches python-docx. It only classifies and extracts
text, so it's usable with no database and no web request.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Characters used to draw the TAM/SAM/SOM nested boxes.
_BOX_CHARS = "┌┐└┘─"
_BORDER_ONLY_RE = re.compile(r"^[\s│┌┐└┘─]*$")
_STRIP_BOX_RE = re.compile(r"[┌┐└┘─│]")
_WS_RE = re.compile(r"\s+")

_RING_LABEL_RE = re.compile(
    r"^(TAM|SAM|SOM)\b\s*[:\-]?\s*(.*?)\s*(?:\[([^\]]+)\]\s*)?$"
)

# Harvey Ball glyph set (Handler note: "6-column, 20-row grid using Unicode
# geometric characters: ● ◕ ◑ ◔ ○ plus — for undisclosed").
_HARVEY_GLYPHS = {"●", "◕", "◑", "◔", "○", "—", "-", ""}


@dataclass
class Ring:
    """One level of a TAM/SAM/SOM nested-box exhibit."""

    label: str  # "TAM" | "SAM" | "SOM"
    value: str = ""  # e.g. "≈ USD 178 M/yr" or "~$15.0bn"
    status: str | None = None  # bracketed tag, e.g. "GROWTH", "Low"
    definition: str = ""


@dataclass
class TamSamSom:
    """TAM/SAM/SOM nested-rings exhibit (Handler 1 -- the one we build)."""

    rings: list[Ring] = field(default_factory=list)


@dataclass
class FallbackExhibit:
    """Any fenced block we don't have a dedicated handler for.

    Rendered as a deliberate preformatted block: monospace, bordered,
    captioned, whitespace preserved -- never silently dropped.
    """

    raw_text: str


@dataclass
class HarveyBallGrid:
    """A markdown table that is actually a Harvey Ball capability grid."""

    headers: list[str]
    rows: list[list[str]]


def _clean_ring_line(line: str) -> tuple[int, str]:
    """Strip box-drawing border chars from one line of a nested-box exhibit.

    Returns (depth, text) where depth is how many '│' characters preceded
    the first real content character -- TAM lines are depth 1, SAM depth 2,
    SOM depth 3, regardless of how many spaces of padding each fixture uses.
    A pure border line (all box-drawing chars / whitespace) comes back with
    empty text and is dropped by the caller.
    """
    depth = 0
    i = 0
    while i < len(line) and line[i] in " │":
        if line[i] == "│":
            depth += 1
        i += 1
    rest = line[i:]
    cleaned = _WS_RE.sub(" ", _STRIP_BOX_RE.sub(" ", rest)).strip()
    return depth, cleaned


def looks_like_tam_sam_som(fence_content: str) -> bool:
    """Sniff: does this fence contain a TAM/SAM/SOM nested-box exhibit?"""
    return bool(re.search(r"\bTAM\b", fence_content)) and "│" in fence_content


def parse_tam_sam_som(fence_content: str) -> TamSamSom:
    """Parse a nested box-drawing TAM/SAM/SOM exhibit into ordered Rings.

    Tolerant: a malformed or oddly-indented line just gets folded into the
    nearest ring's definition text rather than raising. Never fatal -- if the
    label line can't be matched at all, the ring is still emitted with
    whatever text was recovered so the exhibit doesn't vanish.
    """
    by_depth: dict[int, list[str]] = {}
    for raw_line in fence_content.splitlines():
        if _BORDER_ONLY_RE.match(raw_line):
            continue
        depth, text = _clean_ring_line(raw_line)
        if not text:
            continue
        by_depth.setdefault(depth, []).append(text)

    order = {1: "TAM", 2: "SAM", 3: "SOM"}
    rings: list[Ring] = []
    for depth in sorted(by_depth):
        lines = list(by_depth[depth])
        label = order.get(depth, f"LEVEL{depth}")

        # The bracketed status tag usually sits on the label's own line, but
        # a long value/description can wrap it onto a continuation line
        # instead (act_report_02's TAM ring does this) -- so search every
        # line for the block's status bracket, not just the first.
        status = None
        for idx in range(len(lines) - 1, -1, -1):
            m = re.search(r"\[([^\]]+)\]", lines[idx])
            if m:
                status = m.group(1)
                lines[idx] = (lines[idx][: m.start()] + lines[idx][m.end():]).strip()
                break

        first, *rest_lines = lines
        m = _RING_LABEL_RE.match(first)
        if m and m.group(1):
            label = m.group(1)
            value = (m.group(2) or "").strip()
        else:
            # Doesn't match the expected "LABEL value" shape -- keep the
            # text anyway rather than dropping the ring.
            value = first
        definition = " ".join(l for l in rest_lines if l).strip()
        rings.append(Ring(label=label, value=value, status=status, definition=definition))

    return TamSamSom(rings=rings)


def parse_fence(fence_content: str, *, info: str = "") -> TamSamSom | FallbackExhibit:
    """Dispatch a fenced code block to the right exhibit handler.

    Always succeeds: an unrecognized fence becomes a FallbackExhibit rather
    than being dropped or raising.
    """
    if looks_like_tam_sam_som(fence_content):
        return parse_tam_sam_som(fence_content)
    return FallbackExhibit(raw_text=fence_content)


def is_harvey_ball_table(headers: list[str], rows: list[list[str]]) -> bool:
    """Is this markdown table actually a Harvey Ball capability grid?

    Heuristic: most of the non-header cells are drawn from the Harvey Ball
    glyph set (● ◕ ◑ ◔ ○ / — for undisclosed), and there's more than one data
    column -- distinguishes it from an ordinary table that happens to use an
    em dash in one cell.
    """
    if len(headers) < 3:
        return False
    cells = [c.strip() for row in rows for c in row[1:]]  # skip the label column
    if not cells:
        return False
    glyph_cells = sum(1 for c in cells if c in _HARVEY_GLYPHS and c not in ("", "-"))
    return glyph_cells >= max(3, int(0.5 * len(cells)))
