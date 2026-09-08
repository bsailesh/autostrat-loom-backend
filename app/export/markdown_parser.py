"""
Report markdown -> intermediate structure.

Walks the markdown-it-py token stream (never regexes the raw markdown body)
and produces a `ParsedReport`: a tolerant, docx-agnostic representation that
`docx_builder.py` consumes. Nothing here touches python-docx or the database,
so it's directly testable against the golden fixtures in
tests/fixtures/reports/.

Tolerance is the operating principle throughout: a block this parser doesn't
recognize is emitted as plain body text with a logged warning, never raised.
One malformed report must not fail the whole export pack -- see
word_export_briefing.md.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

from app.export import exhibits

logger = logging.getLogger(__name__)

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")

# ---------------------------------------------------------------------------
# Intermediate structure
# ---------------------------------------------------------------------------


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    link: str | None = None  # href, if this run should render as a hyperlink
    tag: str | None = None  # None | "confidence" | "staleness"


@dataclass
class Paragraph:
    runs: list[Run] = field(default_factory=list)
    style: str = "body"  # "body" | "so_what" | "legend" | "footnote"
    keep_with_next: bool = False

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class Heading:
    level: int
    text: str
    is_exhibit: bool = False


@dataclass
class HorizontalRule:
    pass


@dataclass
class TableBlock:
    headers: list[str]
    rows: list[list[str]]


@dataclass
class BulletListBlock:
    items: list[list[Run]] = field(default_factory=list)


@dataclass
class ExhibitBlock:
    content: "exhibits.TamSamSom | exhibits.FallbackExhibit"


@dataclass
class KeyInsightItem:
    lead: str
    rest: str
    confidence: str | None


@dataclass
class KeyInsightsBox:
    items: list[KeyInsightItem] = field(default_factory=list)


@dataclass
class SCQABlock:
    situation: str = ""
    complication: str = ""
    question: str = ""
    answer: str = ""


@dataclass
class SubjectLine:
    fields: dict[str, str]
    raw: str


Block = (
    Heading
    | Paragraph
    | HorizontalRule
    | TableBlock
    | BulletListBlock
    | ExhibitBlock
    | exhibits.HarveyBallGrid
)


@dataclass
class ParsedReport:
    subject: SubjectLine | None
    opening: KeyInsightsBox | SCQABlock | None
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Inline run extraction
# ---------------------------------------------------------------------------

_CONFIDENCE_LEAD_RE = re.compile(
    r"^(FACT|OBSERVATION|INTERPRETATION|FORECAST|UNKNOWN)\b", re.IGNORECASE
)
_STALENESS_RE = re.compile(r"^Staleness flag\b", re.IGNORECASE)
_SO_WHAT_RE = re.compile(r"^so what\b", re.IGNORECASE)

# Domain-like tokens inside citation parens, e.g. "safran-group.com",
# "gminsights.com/industry-analysis/...". Restricted to a common TLD
# whitelist to avoid false positives on things like "3.8x" or "U.S.".
_DOMAIN_RE = re.compile(
    r"\b((?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|org|net|gov|edu|io|co)\b(?:/[^\s,()]*)?)"
)


def _inline_runs(inline_token) -> list[Run]:
    """Walk one inline token's children into a flat list of styled Runs."""
    runs: list[Run] = []
    bold_depth = 0
    italic_depth = 0
    link_href: str | None = None
    for child in inline_token.children or []:
        if child.type == "strong_open":
            bold_depth += 1
        elif child.type == "strong_close":
            bold_depth = max(0, bold_depth - 1)
        elif child.type == "em_open":
            italic_depth += 1
        elif child.type == "em_close":
            italic_depth = max(0, italic_depth - 1)
        elif child.type == "link_open":
            href = dict(child.attrs or {}).get("href")
            link_href = href
        elif child.type == "link_close":
            link_href = None
        elif child.type in ("softbreak", "hardbreak"):
            runs.append(Run(text=" "))
        elif child.type == "text":
            if child.content:
                runs.append(
                    Run(
                        text=child.content,
                        bold=bold_depth > 0,
                        italic=italic_depth > 0,
                        link=link_href,
                    )
                )
        elif child.type == "code_inline":
            if child.content:
                runs.append(Run(text=child.content, bold=bold_depth > 0, italic=italic_depth > 0))
        # other inline node types (images, html) are dropped defensively --
        # not present in production report markdown.

    runs = _split_domains_into_links(runs)
    _tag_leading_confidence(runs)
    _tag_staleness(runs)
    return runs


def _split_domains_into_links(runs: list[Run]) -> list[Run]:
    """Turn bare domain tokens in citation text into hyperlink runs."""
    out: list[Run] = []
    for r in runs:
        if r.link or not r.text:
            out.append(r)
            continue
        pos = 0
        matched = False
        for m in _DOMAIN_RE.finditer(r.text):
            matched = True
            if m.start() > pos:
                out.append(Run(text=r.text[pos : m.start()], bold=r.bold, italic=r.italic))
            domain = m.group(1)
            out.append(Run(text=domain, bold=r.bold, italic=r.italic, link="https://" + domain))
            pos = m.end()
        if not matched:
            out.append(r)
        elif pos < len(r.text):
            out.append(Run(text=r.text[pos:], bold=r.bold, italic=r.italic))
    return out


def _tag_leading_confidence(runs: list[Run]) -> None:
    """Mark the paragraph's first bold run if it's a leading confidence tag
    (`**FACT (High).**`, `**UNKNOWN — insufficient public evidence.**`, ...)."""
    if not runs:
        return
    first = runs[0]
    if first.bold and _CONFIDENCE_LEAD_RE.match(first.text.strip()):
        first.tag = "confidence"


def _tag_staleness(runs: list[Run]) -> None:
    for r in runs:
        if r.bold and _STALENESS_RE.match(r.text.strip()):
            r.tag = "staleness"


def _split_so_what(runs: list[Run]) -> list[list[Run]]:
    """Split a paragraph's runs at a trailing italic "So what:" clause.

    Returns one run-list if there's no so-what clause, or two if there is:
    [main_runs, so_what_runs]. The so-what clause is rendered as its own
    paragraph (italic, small left indent) rather than flattened into the
    preceding body text -- see word_export_briefing.md.
    """
    for i, r in enumerate(runs):
        if r.italic and _SO_WHAT_RE.match(r.text.strip()):
            return [runs[:i], runs[i:]] if runs[:i] else [runs]
    return [runs]


# ---------------------------------------------------------------------------
# Subject line
# ---------------------------------------------------------------------------

_SUBJECT_KEY_ALIASES = {
    "subject": "subject",
    "evidence base": "evidence_base",
    "window": "window",
    "date window": "window",
    "compiled": "compiled",
}


def parse_subject_line(text: str) -> SubjectLine:
    """Parse the first line of a report into labelled fields.

    Format drifts between runs (whole-line bold vs. per-label bold, "Window:"
    vs. "Date window:", "Compiled <date>" present or absent) -- so this
    splits on "|", strips bold markers, and fuzzy-matches labels
    case-insensitively. A field that can't be matched is dropped, never
    assumed. See word_export_briefing.md, "Subject line".
    """
    raw = text.strip()
    fields: dict[str, str] = {}
    # Delimiter drifts too: "|" in most runs, "·" in at least one observed
    # subject line (rec_report_02) -- split on either.
    for part in re.split(r"[|·]", raw):
        part = part.strip().strip("*").strip()
        if not part:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z \-]{2,30}?):\s*(.*)$", part)
        if m:
            key = m.group(1).strip().lower()
            value = m.group(2).strip()
            canonical = _SUBJECT_KEY_ALIASES.get(key)
            if canonical:
                fields[canonical] = value
                continue
        # No recognised "Label: value" prefix on this segment (e.g. the bare
        # subject text before the first "|" in the whole-line-bold format).
        if "subject" not in fields:
            fields["subject"] = re.sub(r"^subject:\s*", "", part, flags=re.IGNORECASE).strip()
    return SubjectLine(fields=fields, raw=raw)


# ---------------------------------------------------------------------------
# Token stream -> flat node list
# ---------------------------------------------------------------------------


def _extract_table(tokens: list, start: int) -> tuple[list[str], list[list[str]], int]:
    """Read a table_open..table_close run starting at `start`. Returns
    (headers, rows, index of table_close)."""
    headers: list[str] = []
    rows: list[list[str]] = []
    in_body = False
    row: list[str] | None = None
    i = start + 1
    while tokens[i].type != "table_close":
        t = tokens[i]
        if t.type == "tbody_open":
            in_body = True
        elif t.type == "tr_open":
            row = []
        elif t.type == "inline":
            text = _plain_text(t)
            if in_body:
                row.append(text)
            else:
                headers.append(text)
        elif t.type == "tr_close":
            if in_body and row is not None:
                rows.append(row)
            row = None
        i += 1
    return headers, rows, i


def _plain_text(inline_token) -> str:
    """Flatten an inline token to plain text (markers stripped) -- used for
    table cells, where we don't need per-run styling."""
    return "".join(c.content for c in (inline_token.children or []) if c.type in ("text", "code_inline")).strip()


def _walk(tokens: list) -> list:
    """First pass: token stream -> flat list of raw nodes (headings,
    paragraphs-as-runs, tables, fences, bullet lists, hr)."""
    nodes: list = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t.type == "heading_open":
            level = int(t.tag[1:]) if t.tag[1:].isdigit() else 2
            inline = tokens[i + 1]
            text = _plain_text(inline)
            nodes.append(("heading", level, text))
            i += 3  # heading_open, inline, heading_close
            continue
        if t.type == "paragraph_open":
            inline = tokens[i + 1]
            runs = _inline_runs(inline)
            nodes.append(("paragraph", runs))
            i += 3
            continue
        if t.type == "hr":
            nodes.append(("hr",))
            i += 1
            continue
        if t.type == "table_open":
            headers, rows, close_idx = _extract_table(tokens, i)
            nodes.append(("table", headers, rows))
            i = close_idx + 1
            continue
        if t.type == "fence":
            nodes.append(("fence", t.content, t.info))
            i += 1
            continue
        if t.type == "bullet_list_open":
            items: list[list[Run]] = []
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if tokens[j].type == "bullet_list_open":
                    depth += 1
                elif tokens[j].type == "bullet_list_close":
                    depth -= 1
                    if depth == 0:
                        break
                elif tokens[j].type == "inline" and tokens[j - 1].type == "paragraph_open":
                    items.append(_inline_runs(tokens[j]))
                j += 1
            nodes.append(("bullet_list", items))
            i = j + 1
            continue
        # Anything else (blockquote, html, etc. -- not seen in production
        # report markdown) is skipped defensively rather than raised.
        i += 1
    return nodes


# ---------------------------------------------------------------------------
# Node list -> ParsedReport
# ---------------------------------------------------------------------------

_EXHIBIT_HEADING_RE = re.compile(r"^Exhibit\s+\d+", re.IGNORECASE)
# Trailing "(Confidence: X)" tag -- tolerate a stray closing "." or "*" left
# over from italic wrapping (e.g. "*(Confidence: Medium)*.") after the paren.
_KI_CONFIDENCE_RE = re.compile(r"\(Confidence:\s*([^)]+)\)[.\s*]*$", re.IGNORECASE)
_KI_BRACKET_RE = re.compile(r"^\[([^\]]+)\]\s*")
_PURE_BRACKET_RE = re.compile(r"^\[[^\]]+\]$")
# Third leading-tag convention: spelled-out confidence after an em/en dash,
# e.g. "FACT — High confidence" / "OBSERVATION — Medium/High confidence"
# (rec_report_03's Key Insights bullets). Renders fine today only because
# the generic FACT/OBSERVATION/... prefix check happens to also match it --
# this is the dedicated extraction so KeyInsightItem.confidence is actually
# populated for it rather than staying None by accident.
_LEAD_EMDASH_CONFIDENCE_RE = re.compile(
    r"^(?:FACT|OBSERVATION|INTERPRETATION|FORECAST|UNKNOWN)\s*[—-]\s*"
    r"([A-Za-z/ \-]+?)\s+confidence\b",
    re.IGNORECASE,
)


def _key_insight_item(runs: list[Run]) -> KeyInsightItem:
    """Parse one Key Insights bullet: bold lead text + trailing
    "(Confidence: X)", the "[High]" bracket-prefixed variant, or confidence
    spelled out inside the lead itself ("FACT — High confidence")."""
    full = "".join(r.text for r in runs)
    confidence = None
    m = _KI_CONFIDENCE_RE.search(full)
    if m:
        confidence = m.group(1).strip()
        full = full[: m.start()].strip()
    m2 = _KI_BRACKET_RE.match(full)
    if m2:
        confidence = confidence or m2.group(1).strip()
        full = full[m2.end() :].strip()
    lead = ""
    for r in runs:
        t = r.text.strip()
        if not t or _PURE_BRACKET_RE.match(t):
            continue  # the confidence bracket itself, not a topical lead
        if r.bold:
            lead = t.rstrip(":").rstrip("*")
            break
    if confidence is None and lead:
        m3 = _LEAD_EMDASH_CONFIDENCE_RE.match(lead)
        if m3:
            confidence = m3.group(1).strip()
    rest = full
    if lead and rest.startswith(lead):
        rest = rest[len(lead) :].strip(" -—:")
    return KeyInsightItem(lead=lead, rest=rest, confidence=confidence)


def _scqa_from_paragraphs(paragraphs: list[list[Run]]) -> SCQABlock:
    scqa = SCQABlock()
    labels = {
        "situation": "situation",
        "complication": "complication",
        "question": "question",
        "answer": "answer",
    }
    for runs in paragraphs:
        if not runs:
            continue
        full = "".join(r.text for r in runs)
        lead = runs[0].text.strip().rstrip(".").lower() if runs[0].bold else ""
        field_name = labels.get(lead)
        if not field_name:
            continue
        rest = full
        prefix = runs[0].text
        if rest.startswith(prefix):
            rest = rest[len(prefix) :].strip()
        setattr(scqa, field_name, rest)
    return scqa


def parse_report(markdown_text: str, *, report_number: int) -> ParsedReport:
    """Parse one report's markdown body into a ParsedReport.

    Never raises: any node this function can't make sense of degrades to
    plain body text with a warning appended to `ParsedReport.warnings`.
    """
    warnings: list[str] = []
    text = markdown_text.lstrip()
    if text.startswith('"'):
        # One report is known to begin with a stray quote character --
        # strip leading quote/whitespace defensively (word_export_briefing.md).
        text = text[1:].lstrip()

    try:
        tokens = _MD.parse(text)
        nodes = _walk(tokens)
    except Exception:  # noqa: BLE001 - a parse failure must degrade, not fail the pack
        logger.exception("Failed to tokenize report %s markdown; falling back to raw text", report_number)
        return ParsedReport(
            subject=None,
            opening=None,
            blocks=[Paragraph(runs=[Run(text=markdown_text)])],
            warnings=[f"report {report_number}: markdown tokenization failed, rendered as raw text"],
        )

    idx = 0
    subject: SubjectLine | None = None
    if nodes and nodes[0][0] == "paragraph":
        raw_text = "".join(r.text for r in nodes[0][1])
        subject = parse_subject_line(raw_text)
        idx = 1

    opening: KeyInsightsBox | SCQABlock | None = None
    if idx < len(nodes) and nodes[idx][0] == "heading" and nodes[idx][2].strip().lower() == "governing insight":
        para_runs = []
        j = idx + 1
        while j < len(nodes) and nodes[j][0] == "paragraph" and len(para_runs) < 4:
            para_runs.append(nodes[j][1])
            j += 1
        opening = _scqa_from_paragraphs(para_runs)
        idx = j
    elif idx < len(nodes) and nodes[idx][0] == "heading" and nodes[idx][2].strip().lower() == "key insights":
        j = idx + 1
        if j < len(nodes) and nodes[j][0] == "bullet_list":
            opening = KeyInsightsBox(items=[_key_insight_item(item) for item in nodes[j][1]])
            idx = j + 1
        else:
            warnings.append(f"report {report_number}: 'Key Insights' heading with no following bullet list")
            idx += 1

    blocks: list[Block] = []
    while idx < len(nodes):
        node = nodes[idx]
        kind = node[0]
        if kind == "heading":
            _, level, htext = node
            blocks.append(Heading(level=level, text=htext, is_exhibit=bool(_EXHIBIT_HEADING_RE.match(htext.strip()))))
        elif kind == "hr":
            blocks.append(HorizontalRule())
        elif kind == "table":
            _, headers, rows = node
            if exhibits.is_harvey_ball_table(headers, rows):
                blocks.append(exhibits.HarveyBallGrid(headers=headers, rows=rows))
            else:
                blocks.append(TableBlock(headers=headers, rows=rows))
        elif kind == "fence":
            _, content, info = node
            try:
                parsed_fence = exhibits.parse_fence(content, info=info)
            except Exception:  # noqa: BLE001
                logger.exception("Report %s: fence parsing failed, falling back to preformatted", report_number)
                parsed_fence = exhibits.FallbackExhibit(raw_text=content)
                warnings.append(f"report {report_number}: unrecognised fenced block, rendered as preformatted fallback")
            blocks.append(ExhibitBlock(content=parsed_fence))
        elif kind == "bullet_list":
            _, items = node
            blocks.append(BulletListBlock(items=items))
        elif kind == "paragraph":
            _, runs = node
            for i, split_runs in enumerate(_split_so_what(runs)):
                if not split_runs:
                    continue
                text_stripped = "".join(r.text for r in split_runs).strip()
                if i == 1:
                    style = "so_what"
                elif text_stripped.lower().startswith("legend:"):
                    style = "legend"
                elif text_stripped.startswith("*") or text_stripped.lower().startswith("formula footnote"):
                    style = "footnote"
                else:
                    style = "body"
                keep_with_next = style == "legend"
                blocks.append(Paragraph(runs=split_runs, style=style, keep_with_next=keep_with_next))
        else:
            warnings.append(f"report {report_number}: unrecognised node kind {kind!r}, skipped")
        idx += 1

    return ParsedReport(subject=subject, opening=opening, blocks=blocks, warnings=warnings)
