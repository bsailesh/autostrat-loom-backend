# Briefing: Build Agent 1 — Voice of Customer

Full build: customer context input, evidence upload and ingest, agent package,
endpoints, frontend.

**Read first, in this order:**

1. `voice_of_customer_prompt_draft_v2.md` — the agent's operating specification
2. `voice_of_customer_input_spec.md` — the input contract
3. `market_insights_agent_spec.md` — the shared Evidence & Confidence Standard
   and Consulting-Grade Output Standard

`tech_regulation/` is the closest structural reference — single pass, no
deterministic compute module, scoping input plus reports. Follow its patterns.

**Do not start coding until you have given me an implementation plan and I have
approved it.**

---

## Three decisions already made

**1. Nine reports, not ten.** Build Reports 1–5 and 7–10, omitting Report 6
(the compiled Voice of Customer narrative), which restates Reports 1–5 and
doubles generation cost for a worse reader experience. Note it as deferred in
the output rather than dropping it silently.

**2. Ingest supports text, PDF and CSV. Office formats deferred.**

CSV is not optional. Ticket and claim exports arrive as CSV, and counts from
them are what make pain point frequency possible. Without CSV the agent stays
at Tier 2 in practice even when a customer supplies evidence.

**3. VoC emits no candidate work.** Tech & Regulation does, because a regulation
implies defined work with a date. A customer pain point does not — whether it
warrants a project is a judgement for a person with the portfolio in front of
them.

Instead, VoC contributes to Agent 5 in two ways, both textual:

- **Evidence that feeds scoring.** Agent 5 scores `customer_value` at 0.25
  weight from market-level demand today, because this agent has not run. Every
  Agent 5 run says so in its `Validity:` line. Closing that substitution is this
  agent's largest contribution to the platform
- **A "Findings for synthesis" section in Report 1**, whose contents reach Agent
  5's decision brief. Named exactly, so a finding is not lost in prose

---

## Part 1 — Data model

Follow `app/models.py` conventions. Every table tenant-scoped.

**Reuse `agent_runs` and `agent_reports`** via `agent_type="voice-of-customer"`.
Add it to `agent_label_for()`. The Word export then works unchanged.

### Context tables

**`voc_segments`** — segment_key, segment_name, description,
approximate_count (nullable — `unknown` is a legitimate answer and must not
become zero)

**`voc_channels`** — channel, direction (`inbound` / `outbound` / `both`), note

**`voc_customers`** — customer_name, segment_key, products, relationship_status.
Optional and sensitive

**`voc_known_pain_points`** — pain_point, segment_key, category_key,
their_assessment

The customer's stated beliefs, tested in Part 3 of the prompt. **This table is
the input to the highest-value analysis this agent performs**, and the analysis
is unavailable unless the beliefs were recorded before the run.

**`voc_config`** — attribution_policy (`segment_only` default /
`role_and_segment` / `named`)

### Product categories — read, do not duplicate

Product categories already exist as `tr_product_categories` for Tech &
Regulation. **Where that agent is configured, read its categories rather than
asking the customer twice**, with VoC-specific additions allowed in its own
table.

This is the second agent needing the same list and a third will. Do not extract
a shared Product Profile now — note it as the point at which extraction stops
being premature, and do it after this agent ships.

### Evidence tables

**`voc_evidence_files`** — the uploaded documents

- file_type, from the controlled list in the input spec §2.1
- filename, content_type, size_bytes
- `as_of` date, `period_start`, `period_end`
- `is_sample` (bool) and `sample_description`
- segment coverage, JSON, where known
- row_count for CSV, page_count for PDF, char_count for text
- ingest_status, issues JSON

**`is_sample` is load-bearing.** A sample is not a census, and the agent must
never report frequency from one as though it were. Carry it through to the
prompt.

---

## Part 2 — Evidence ingest

New infrastructure — neither Market Insights nor Tech & Regulation has it.

### Formats

**Text** (`.txt`, `.md`) — stored as-is.

**PDF** — text extracted. A PDF with no extractable text is almost certainly
scanned; **reject it with that specific message** rather than storing an empty
document. Do not add OCR.

**CSV** — parsed to rows. This is the format that enables frequency analysis.

Do not accept `.docx`, `.xlsx` or `.msg` in v1. Reject with a clear message
naming the supported formats.

### CSV handling

Ticket and claim exports have no standard schema. Do not require one.

On upload: parse the header row, store it, and return the detected columns so
the customer can confirm. Offer an optional mapping of detected columns to
roles the agent understands — date, segment, product, description, category,
severity, status. Unmapped columns are retained and passed through; a mapping
helps the agent but its absence must not block ingest.

**Row count is what matters most.** Frequency analysis needs counts, and a count
needs to know what one row represents. Capture that on upload: one row per
ticket, per comment, per claim.

### Volume

The instance is 414MB with 2GB swap. Ticket exports can be large.

- Cap upload size and state the cap in the error
- **Do not summarise verbatims.** The upstream-report summarisation threshold
  does not apply here — summarising customer language destroys exactly what
  makes it valuable. For large CSVs, pass aggregate counts plus a sampled set of
  verbatims, and state in the output that verbatims were sampled and how
- Iterate cursors. Do not load all evidence into memory at once

### Attribution enforcement

`segment_only` is a prompt instruction today, which is weak for a privacy
control.

**Flag this in your plan with a recommendation.** Options: strip names before
the model sees them, which is robust but may break context; pass through and
rely on the prompt, which is current behaviour; or redact on output. Say which
you would choose and why. Do not implement stripping without agreement — it
changes what the agent can reason about.

---

## Part 3 — The agent

`voice_of_customer/` mirroring `tech_regulation/`:

- `standards.py` — role, do-not-invent, attribution, evidence standard, tier
  model
- `prompts.py` — system prompt and per-report prompts
- `reports.py` — nine `ReportSpec` objects
- `context.py` — assemble the customer context, determine the operating tier
- `evidence.py` — load and render evidence for the prompt
- `agent.py` — orchestration
- `config.py`

Declare `WEB_SEARCH_TOOL_TYPE` locally rather than importing from
`market_insights.config`, consistent with how the other agent packages stay
independent.

### Single pass, one call per report

No deterministic computation. Stream one call per report; do not generate nine
in one call.

### Operating tier

`context.py` determines Tier 2 / Tier 1 partial / Tier 1 substantial from what
evidence exists, and the agent states it in the first line of every run.

**A Tier 2 run is titled "External customer-context analysis", not Voice of
Customer.** The title is the unmissable signal; the first-line statement is the
detail.

Per-analysis availability follows the table in prompt v2 Part 1 — each analysis
names which source enabled it and which are missing.

### Findings for synthesis

A section in Report 1 headed exactly **"Findings for synthesis"**.

Textual, no schema. Each finding is a short paragraph written to stand alone,
because a reader meeting it in Agent 5's decision brief will not have this
report open.

**The section appears even in a Tier 2 run**, stating which beliefs could not be
tested and what evidence would settle each.

### Agent 5 integration

Agent 5 already reads upstream report markdown. **No new integration code is
required** — VoC's reports become available to it through the existing
most-recent-successful-run selection.

Verify this rather than assuming: confirm Agent 5 discovers a
`voice-of-customer` run as upstream and that "Findings for synthesis" survives
into its Pass 1 input. If `summarize_upstream_agent` would compress that section
away, say so — it would defeat the section's purpose.

### What must not be inferred

Customer complaints, market trends, competitor features, personas, product
deficiencies, market share, customer priorities. Frequency from a sample.
Sentiment without feedback text. Any effort estimate.

---

## Part 4 — Endpoints

Follow `app/routers/tech_regulation.py`. **Tenant-scoped; 404 not 403.**

```
GET/PUT  /agents/voice-of-customer/context/segments
GET/PUT  /agents/voice-of-customer/context/channels
GET/PUT  /agents/voice-of-customer/context/customers
GET/PUT  /agents/voice-of-customer/context/known-pain-points
GET/PUT  /agents/voice-of-customer/context/config
GET      /agents/voice-of-customer/context/categories    read-through to tr_product_categories plus local additions
GET      /agents/voice-of-customer/context/state         tier, what is missing, what it costs
POST     /agents/voice-of-customer/evidence              upload
GET      /agents/voice-of-customer/evidence
DELETE   /agents/voice-of-customer/evidence/{id}
POST     /agents/voice-of-customer/run
GET      /agents/voice-of-customer/runs
GET      /agents/voice-of-customer/runs/{run_id}/reports
GET      /agents/voice-of-customer/runs/{run_id}/export.docx
```

`/context/state` mirrors `/scope/state` and `/readiness`: what is missing **and
what it costs**, from the degradation table in the input spec Part 4.
**Consequence text is empty for items that are set** — the bug fixed in
`b4f3282`.

**A run is never blocked.** It degrades to Tier 2 and says so.

---

## Part 5 — Frontend

Per-agent module, shared shell. `voiceOfCustomer/` alongside the others, using
`reportWorkspace/`.

### Context screen

Sections: segments, channels, customers, known pain points, attribution policy,
product categories (read-through, with additions).

Each shows status and the consequence from `/context/state`.

**The operating tier is shown prominently at the top**, with what Tier 2 means.

**Known pain points deserves emphasis in the UI.** It is the one field a
customer may not think to fill, and the analysis it enables — testing their own
beliefs — is the most valuable thing this agent does. The section should say so.

### Evidence screen

Upload by type. Per file: type, `as_of`, period covered, sample flag and
description, detected columns for CSV with optional role mapping, row or page
count, ingest status.

### Planned integrations — display only

A section headed **"Planned integrations"**, listing: Salesforce, Dynamics 365,
Zendesk / ServiceNow, SharePoint, Qualtrics / Medallia, fleet telemetry. Each
with a one-line statement of what it would supply.

**Do not render these as buttons, greyed-out controls, or anything that invites
a click.** They are a roadmap statement. A connector that looks present and does
nothing contradicts the thing this platform is built on — that it states what it
does not know — and a design partner who clicks one has been shown that the
surface and the substance differ.

Label them clearly as not yet available.

### Report workspace

Shared shell, own exhibit registry instance. Renderers needed:

- **Pain point bar chart** — horizontal, ranked by severity × frequency
- **Impact vs effort 2×2** — scatter from structured coordinates
- **Harvey Ball grid** — same contract as Market Insights'. **Build its own
  renderer in this agent's registry rather than importing**, consistent with
  agent independence
- **SWOT and insights matrix** — quadrant layouts

All from structured data. **No ASCII art.** Fall back to a table.

---

## Part 6 — Testing

- Context assembly: tier determination across no evidence, partial, substantial
- Ingest: PDF with no extractable text rejected with the specific message;
  unsupported format rejected naming supported ones; CSV header detection;
  `is_sample` carried through to the prompt
- `/context/state`: empty consequence for set items
- Attribution: `segment_only` produces no customer names in output
- Belief testing: corroborated, contradicted and both not-found causes
- Tier 2: report titled "External customer-context analysis"; sentiment,
  frequency, personas and win/loss reported unavailable rather than thin
- Findings for synthesis present in both Tier 2 and Tier 1 runs
- Export with the correct cover label; other agents' export tests unchanged
- Follow `tests/conftest.py`. **Run the suite in more than one file order** —
  and note the `SessionFactory`-at-import trap from the Agent 3 build, logged in
  conftest

---

## Out of scope

- Do not build Product Sustainment
- Do not implement any connector
- Do not add OCR
- Do not extract a shared Product Profile
- Do not change Market Insights, Agent 5 or Tech & Regulation beyond
  `agent_label_for()`

---

## Deployment notes

- New dependencies pinned. PDF extraction needs one — `pypdf` is already a
  transitive dependency via the export pipeline; check before adding another
- **`create_all` creates new tables but does not alter existing ones.** New
  tables are fine; any column on an existing table needs a manual `ALTER TABLE`
  on production. Say so explicitly in the PR if required
- Backend deploy is `git pull`, `pip install`, `systemctl restart loom-api`
- **Frontend is a separate deploy**
- **Push as part of committing**
- Watch `free -h` during the first real run, particularly with a large CSV

---

## Definition of done

- [ ] Nine reports; Report 6 noted as deferred
- [ ] Operating tier stated in the first line and in the title where Tier 2
- [ ] Text, PDF and CSV ingest; scanned PDF rejected with a specific message
- [ ] `is_sample` carried through; frequency never reported from a sample as a
      census
- [ ] Belief testing produces all three outcomes, with both not-found causes
      distinguished
- [ ] "Findings for synthesis" present in Report 1, in Tier 2 runs too
- [ ] Attribution policy honoured; `segment_only` produces no names
- [ ] Planned integrations shown as a roadmap statement, not as controls
- [ ] Agent 5 discovers a VoC run as upstream; findings survive into Pass 1
- [ ] Reports render from structured data; no ASCII art
- [ ] Word export works with the correct cover label
- [ ] Suite passes in multiple file orders
- [ ] Committed, pushed, merged via PR
