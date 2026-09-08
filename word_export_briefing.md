# Briefing: Word (.docx) Export — Full Report Pack

**Supersedes the earlier draft of this briefing.** That draft was written before
the real report markdown had been inspected and got several things wrong. This
version is written against actual output from two production runs.

## Objective

Make the Export button in the report workspace produce a single Word document
containing **all reports from a run**, generated on demand from the markdown
already stored in the database.

The output must meet the Consulting-Grade Output Standard in
`market_insights_agent_spec.md` — a document a user could send to an executive
without editing it first.

## Verified current state

Schema of `agent_reports` (confirmed, do not re-derive):

```
id                 VARCHAR NOT NULL
tenant_id          VARCHAR NOT NULL
run_id             VARCHAR NOT NULL
report_number      INTEGER NOT NULL
title              VARCHAR NOT NULL
content            TEXT    NOT NULL   -- the markdown
confidence_summary TEXT    NOT NULL
created_at         DATETIME NOT NULL
PRIMARY KEY (id)
FOREIGN KEY (tenant_id) REFERENCES tenants (id)
FOREIGN KEY (run_id)    REFERENCES agent_runs (id)
```

- **The data model is multi-tenant.** Scope the export query by `tenant_id`,
  not by user id. Getting this wrong either leaks another tenant's reports or
  blocks legitimate teammates.
- A run produces **9 reports**: Executive Market Summary, Market Landscape,
  Competitor Intelligence, Competitive Feature Comparison Matrix, Customer
  Demand, Market Trends, Market SWOT, Market Intelligence Digest, Industry
  Trends.
- Each report body is ~11–17KB of markdown. A full pack is ~120KB, likely
  60–90 rendered pages.
- `confidence_summary` is a **separate column** and also appears as a
  `## Confidence Summary` section inside the markdown. Check whether they
  duplicate before rendering both — do not emit the same text twice.
- There is **no stored structured representation**. The React frontend parses
  the raw markdown at render time.

## Scope

**In scope:** a backend endpoint rendering all reports for a run into one
`.docx`, plus frontend wiring.

**Out of scope — do not do these:**

- Do not refactor report storage into structured JSON. Correct long-term
  direction, explicitly deferred.
- Do not change the frontend's markdown rendering.
- Do not add PDF export.
- Do not touch auth, CORS, Caddy, DNS, or CloudFront.

## Endpoint

`GET /runs/{run_id}/export.docx`

- Use the **same auth dependency** as existing report endpoints. Match the
  codebase; do not invent a pattern.
- **Scope the query by `tenant_id`.** Return 404 (not 403) for a run outside
  the caller's tenant, so the endpoint does not leak run existence.
- 404 if the run has no reports.
- Build in memory (`io.BytesIO`). **Do not write temp files to disk.**
- Return `StreamingResponse`, media type
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  with `Content-Disposition: attachment; filename="..."`.
- Filename: `AutoStrat_Loom_Market_Insights_<scope-slug>_<YYYY-MM-DD>.docx`.
  Derive the slug from the run's scope configuration, ASCII-safe, truncated.
  Fall back to the run id.
- Order by `report_number` ascending.

Synchronous. Do not add a job queue.

### Memory constraint — read this

The production instance has **414MB RAM and 2GB swap** (swap added 8 Sep 2026
after chronic OOM kills made the box unreachable). Building a 90-page document
in memory on this box is genuinely tight.

- Do not hold the parsed structure for all 9 reports plus the document object
  simultaneously if avoidable — build and append report by report, releasing
  each parsed structure after use.
- Do not read all report rows into a list up front; iterate the cursor.
- Test the endpoint on the actual instance and watch `free -h` during a run.
  If swap usage climbs by hundreds of MB, say so in the PR — that is the
  trigger for resizing the instance.

## Module layout

- `app/export/markdown_parser.py` — markdown → intermediate structure
- `app/export/exhibits.py` — fenced-block handlers (see below)
- `app/export/docx_builder.py` — structure → bytes
- `app/export/template.docx` — reference template carrying styles
- Route handler stays thin.

Parser must be testable with no database and no web request.

## Actual markdown structure

Verified across runs `1f843fe9` (actuation, 4 Sep) and `df344207` (flight
recorders, 7 Sep).

### Subject line

First non-empty line, bold, pipe-delimited. **Format drifts between runs:**

```
**Subject: EMA/EMEC actuation ... | Evidence base: ... | Window: Sept 2021 – Sept 2026 | Compiled 4 Sept 2026**
**Subject:** Extended-duration flight recorders ... | **Evidence base:** ... | **Date window:** 2021–Sep 2026
```

Differences observed: whole-line bold vs per-label bold; `Window:` vs
`Date window:`; `Compiled <date>` present in one run, absent in the other.

Therefore: split on `|`, strip bold markers, match labels case-insensitively
against a fuzzy key set, **never assume a field is present**. Prefer the run
record and scope config as the authority for cover-page data; treat the subject
line as a supplement.

One report (`1f843fe9` report 1) begins with a **stray `"` character**. Strip
leading quote/whitespace defensively. Worth a separate look at the agent writer,
but not this task.

### Governing Insight — Report 1 only

`## Governing Insight` followed by four bold-labelled paragraphs:
**Situation.** **Complication.** **Question.** **Answer.**

Render as four labelled blocks inside one callout — not as undifferentiated
body text. This is SCQA and the structure carries meaning.

### Key Insights — reports other than 1

`## Key Insights` followed by a bullet list. Each bullet has bold lead text and
a **trailing** `(Confidence: High)` / `(Confidence: Medium)` paren.

### Confidence tags — TWO different conventions

1. **Leading**, at paragraph start: `**FACT (High).**`,
   `**OBSERVATION (Medium-High).**`, `**FORECAST (Medium, vendor-attributed).**`,
   `**INTERPRETATION (Medium).**`, `**UNKNOWN — insufficient public evidence.**`
2. **Trailing**, in Key Insights bullets: `(Confidence: High)`
3. Also appears **inside table cells** as a bare column value.

The parser must handle all three. Render as bold + subtle run shading. Word has
no pill primitive — do not attempt rounded corners.

### Other recurring elements

- `## Exhibit N — <title>` — exhibits are **headings**, not special blocks.
- `*So what:*` italic closers ending most evidence paragraphs. Style distinctly
  (italic, small left indent). Do not flatten into body text.
- `---` horizontal rules as section separators → paragraph bottom border,
  **never a table**.
- `**Staleness flag:**` inline callouts.
- Inline source citations in parens with URLs — render as real hyperlinks.
- Dense markdown tables, 4–6 columns.

## Exhibits: fenced code blocks

Only 5 of 18 reports contain a fenced block, always exactly one. **Three
distinct structures, sharing nothing but their fences.** Build a dispatcher
that sniffs the block and routes to a handler, with preformatted fallback.

### Handler 1 — TAM/SAM/SOM (Report 2, both runs) — BUILD THIS

Nested box-drawing rectangles, three levels. Every field is parseable text:

```
TAM ≈ USD 178 M/yr [GROWTH]
Global commercial-transport recorder hardware, 2026-30
  SAM ≈ USD 122.5 M/yr [GROWTH]
  25-hour-CVR-class demand: ...
    SOM ≈ USD 24.5 M/yr [GRAY — assumption-led]
    One of five publicly verified 25 h-class product families ...
```

Each level: label, `≈`, value with unit, bracketed status tag, definition line.

Render as **nested shaded tables** — a cell containing a table containing a
table, progressive indentation and shading. Preserves the containment metaphor
with no exotic glyphs. This also addresses a separate known follow-up item
(the ASCII TAM/SAM/SOM exhibit). **Do not change the frontend rendering.**

`python-docx` nested tables are fiddly: width inheritance does not work as
expected, and **every nesting level needs explicit absolute widths** or inner
tables collapse.

### Handler 2 — Design authority / brand map (Report 3) — FALLBACK ONLY

Column-aligned relationship map: DESIGN AUTHORITY / BRAND / CHANNEL / STATUS
headers, `──▸` arrows, `└──▸` branch rows, optional parenthetical sub-lines.
Row structure varies (arrow lengths differ, branches optional).

Not worth a dedicated handler in v1. Ship as preformatted fallback.

### Handler 3 — Report 9 (`1f843fe9` only) — UNINSPECTED, FALLBACK

### The fallback path is load-bearing

It must look deliberate: monospace paragraph style, light border, caption,
preserved whitespace, no wrapping. Box-drawing and arrow glyphs
(`─ ▸ └ ≈ │`) carry the same font-substitution risk as the Harvey Balls —
**set an explicit font on those runs.**

## The Harvey Ball grid — hardest single element

Report 4 (Competitive Feature Comparison Matrix) contains a **6-column,
20-row** grid using Unicode geometric characters: `● ◕ ◑ ◔ ○` plus `—` for
undisclosed. It has a legend line above and a `\*` footnote below, both plain
paragraphs structurally part of the exhibit.

Three specific failure modes:

1. **Font coverage.** Calibri handles `●` and `○` but is patchy on `◕ ◑ ◔`.
   Per-character font substitution makes the grid visually incoherent, which
   destroys the point of a Harvey Ball chart. Set an explicit font on these
   runs — Segoe UI Symbol or DejaVu Sans — **on the run, not inherited**.
2. **Width.** Long row labels ("Portfolio breadth vs. subject application
   list") against five symbol columns will not fit US Letter portrait. This
   exhibit needs **landscape orientation in its own section**: wide first
   column, narrow fixed symbol columns, centered.
3. **Legend and footnote must not orphan** from the table.

**Mixed orientation means the builder needs multiple `python-docx` sections,
not one continuous flow.** Without this the grid renders broken.

## Parsing approach

The frontend already parses this markdown. **You are not porting that code.**
Implement against the contract in `market_insights_agent_spec.md` — read it
first. Consult the frontend parser only to resolve ambiguity.

- Use `markdown-it-py` and walk the **token stream**. Do not regex the raw
  markdown.
- Parsing must be **tolerant, never fatal**. Missing or malformed block →
  emit as body text and continue. One bad report must not fail the pack.
- Log a warning on any unrecognised block so drift is visible.

### Golden fixtures — required

Two parsers of one contract will drift, and the subject-line differences above
prove drift is already happening between runs three days apart.

- Save real markdown into `tests/fixtures/reports/`. Minimum: `1f843fe9`
  reports 1, 2, 4 and `df344207` reports 1, 2, 3. That set covers Governing
  Insight, both confidence conventions, the Harvey Ball grid, both known ASCII
  exhibits, and both subject-line formats.
- Redact anything tenant-identifying before committing.
- Assert per fixture: title, Governing Insight where present, Key Insights with
  tags, all exhibits, all headings, fenced blocks routed to the right handler.
- These tests are the drift alarm. They must fail loudly.

## Document structure

1. **Cover page** — product name, "Market Insights", scope, run date. Page
   break after.
2. **Table of contents** — field-based.
3. **Each report**, starting on a new page:
   - Title as Heading 1
   - Governing Insight (Report 1) or Key Insights (others)
   - Body with headings preserved
   - Exhibits with captions
4. **Footer on every page except cover** — page number and run date.

Follow the Phase 5 workspace pattern. Do not redesign it.

## Markdown → Word mapping

| Source | Word output |
|---|---|
| Report title | Heading 1 (built-in) |
| `##` / `###` | Heading 2 / 3 (built-in) |
| Governing Insight | Callout table, four labelled SCQA blocks |
| Key Insights | Shaded table, bulleted, trailing tags inline |
| Leading confidence tag | Bold + shaded run at paragraph start |
| `*So what:*` | Italic, small left indent |
| `---` | Paragraph bottom border |
| `## Exhibit N — X` | `Caption` style, kept with following content |
| Markdown table | Real Word table, named style, explicit column widths |
| Harvey Ball grid | Landscape section, explicit symbol font |
| TAM/SAM/SOM fence | Nested shaded tables |
| Other fences | Preformatted fallback, explicit font, bordered |
| Citations with URLs | Real hyperlinks |

## python-docx gotchas

- **Build against a reference template.** Define heading, caption, table,
  callout, and monospace styles in `template.docx` and open with
  `Document('template.docx')`. Defining styles programmatically is far worse.
- **US Letter explicitly.** Do not rely on defaults.
- **TOC is a field code** — no helper exists; insert field XML. Word populates
  it only on "update fields" prompt. Acceptable; note it in the PR.
- **TOC needs built-in heading styles**, or custom styles need `outlineLevel`.
- **Cell shading** requires raw XML (`w:shd`) with `w:val="clear"`. Solid
  renders black.
- **Bullets:** built-in `List Bullet` style. Never a literal `•`.
- **Tables:** explicit width on table *and* every cell, absolute units.
  Percentages render inconsistently.
- **Page breaks** go on a run, not a paragraph.
- **Never embed `\n` in a run.** Separate paragraphs.
- **Keep-with-next** on captions and legend lines so exhibits don't orphan.
- Never use a table as a horizontal rule.

## Verification

A 200 response proves nothing. Render and look:

```
soffice --headless --convert-to pdf output.docx
pdftoppm -jpeg -r 100 output.pdf page
```

Confirm: cover correct; TOC present; page breaks between reports; Governing
Insight on Report 1 only; Key Insights elsewhere; **Harvey Ball symbols all
render in one consistent font**; grid section is landscape and fits;
TAM/SAM/SOM nested boxes correct; fallback blocks bordered and unwrapped;
footers correct; no black cells; no stray bullets.

Open in real Word or Google Docs at least once — confirm no repair prompt.

Test with **both** runs. They differ.

## Frontend

- Export button calls `GET /runs/{run_id}/export.docx` with existing auth,
  receives blob, downloads using the `Content-Disposition` filename.
- Disable button + spinner while in flight. A 9-report pack will take seconds.
- Clear error message on failure.
- **No client-side docx library.** No new heavy dependencies.
- Label it so it's clear this exports the full pack, not the visible report.

## Dependencies and deployment

- Add `python-docx` and `markdown-it-py` to `requirements.txt`, pinned.
- Additive: no migration, no config change, no Caddy/DNS change.
- On the server: pull, install into the existing venv
  (`/home/ubuntu/autostrat-loom-backend/venv`), `sudo systemctl restart
  loom-api`, verify `systemctl status loom-api` and a real export.
- **Terminal caution:** the Lightsail browser SSH terminal is unreliable on
  this project. If it freezes, open a fresh session, `cd` back, and re-check
  state before re-running — earlier commands often completed.

## Definition of done

- [ ] Endpoint returns valid `.docx`, auth correct, **scoped by `tenant_id`**
- [ ] Golden-fixture tests exist and pass, covering both runs
- [ ] Malformed markdown degrades to plain text, never fails the pack
- [ ] Harvey Ball grid renders in landscape with consistent symbol font
- [ ] TAM/SAM/SOM renders as nested tables
- [ ] Unrecognised fences render as deliberate preformatted blocks
- [ ] Output visually verified page by page, both runs
- [ ] Opens in Word without repair prompt
- [ ] Memory checked on the instance during export; result noted in PR
- [ ] Frontend downloads correctly with loading and error states
- [ ] Committed, pushed, merged via PR
