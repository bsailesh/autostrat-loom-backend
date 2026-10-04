// Technology evolution timeline -- horizontal, year axis, stage-labelled
// entries. Inline SVG, no chart library.
//
// Parses the table contract in tech_regulation/reports.py:
//   | Year | Label | Stage | Source | Confidence |
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";

// The stage progression the spec names, in order. Position in this list is
// what drives vertical placement, so a reader sees progression as a climb.
const STAGES = ["research", "prototype", "pilot", "demonstration", "launch", "adoption"];

const STAGE_COLOR = {
  research: theme.textMuted,
  prototype: theme.navyLight,
  pilot: theme.navy,
  demonstration: theme.warning,
  launch: theme.orange,
  adoption: theme.success,
};

function col(headers, re) {
  return headers.findIndex((h) => re.test(h));
}

function parseYear(text) {
  const m = String(text || "").match(/(19|20)\d{2}/);
  return m ? parseInt(m[0], 10) : null;
}

function stageKey(raw) {
  const v = String(raw || "").toLowerCase();
  return STAGES.find((s) => v.includes(s)) || null;
}

export function detectEvolutionTimeline(table) {
  const { headers, rows } = table;
  const yearIdx = col(headers, /^year$/i);
  const labelIdx = col(headers, /^label$/i);
  const stageIdx = col(headers, /^stage$/i);
  if (yearIdx === -1 || labelIdx === -1 || stageIdx === -1) return null;
  if (!rows.length) return null;

  const sourceIdx = col(headers, /^source/i);
  const confidenceIdx = col(headers, /^confidence/i);

  const entries = [];
  for (const row of rows) {
    const year = parseYear(row[yearIdx]?.text);
    const label = row[labelIdx]?.text;
    const stage = stageKey(row[stageIdx]?.text);
    if (year === null || !label || !stage) return null; // shape doesn't hold
    entries.push({
      year,
      label,
      stage,
      source: sourceIdx >= 0 ? row[sourceIdx]?.text || "" : "",
      confidence: confidenceIdx >= 0 ? row[confidenceIdx]?.text || "" : "",
    });
  }
  entries.sort((a, b) => a.year - b.year || STAGES.indexOf(a.stage) - STAGES.indexOf(b.stage));
  return { entries };
}

const WIDTH = 820;
const PAD_LEFT = 104;
const PAD_RIGHT = 24;
const ROW_H = 30;
const AXIS_H = 26;

export function EvolutionTimelineExhibit({ data }) {
  const { entries } = data;
  const years = entries.map((e) => e.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const span = Math.max(1, maxYear - minYear);
  const usedStages = STAGES.filter((s) => entries.some((e) => e.stage === s));
  const height = AXIS_H + usedStages.length * ROW_H + 12;

  const x = (year) => PAD_LEFT + ((year - minYear) / span) * (WIDTH - PAD_LEFT - PAD_RIGHT);
  const y = (stage) => AXIS_H + usedStages.indexOf(stage) * ROW_H + ROW_H / 2;

  // Year ticks: every year when the span is short, otherwise ends plus a
  // couple of interior marks, so the axis never crowds.
  const tickYears =
    span <= 8
      ? Array.from({ length: span + 1 }, (_, i) => minYear + i)
      : [minYear, minYear + Math.round(span / 3), minYear + Math.round((2 * span) / 3), maxYear];

  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>Technology evolution timeline</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>
          {minYear}–{maxYear}
        </span>
      </figcaption>

      <div style={{ overflowX: "auto", padding: "8px 0 4px" }}>
        <svg width={WIDTH} height={height} role="img" aria-label="Technology evolution timeline">
          {tickYears.map((yr) => (
            <g key={yr}>
              <line x1={x(yr)} y1={AXIS_H - 8} x2={x(yr)} y2={height - 6} stroke={theme.border} strokeWidth={1} />
              <text x={x(yr)} y={14} fontSize={10} fill={theme.textMuted} textAnchor="middle">
                {yr}
              </text>
            </g>
          ))}

          {usedStages.map((stage) => (
            <g key={stage}>
              <text x={PAD_LEFT - 10} y={y(stage) + 3} fontSize={10} fill={theme.textSecondary} textAnchor="end">
                {stage}
              </text>
              <line
                x1={PAD_LEFT}
                y1={y(stage)}
                x2={WIDTH - PAD_RIGHT}
                y2={y(stage)}
                stroke={theme.border}
                strokeWidth={1}
                strokeDasharray="2 3"
              />
            </g>
          ))}

          {entries.map((e, i) => (
            <g key={i}>
              <circle cx={x(e.year)} cy={y(e.stage)} r={5} fill={STAGE_COLOR[e.stage] || theme.navy} />
              <title>
                {e.year} · {e.label} · {e.stage}
                {e.source ? ` · ${e.source}` : ""}
                {e.confidence ? ` · ${e.confidence}` : ""}
              </title>
            </g>
          ))}
        </svg>
      </div>

      {/* The entries in full underneath: the plot shows shape, the list
          carries the labels, sources and confidence without crowding it. */}
      <ol style={{ listStyle: "none", margin: 0, padding: "4px 14px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
        {entries.map((e, i) => (
          <li key={i} style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 8, fontSize: 12 }}>
            <span style={{ fontWeight: 700, color: theme.navy, minWidth: 38 }}>{e.year}</span>
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: STAGE_COLOR[e.stage] || theme.navy,
                textTransform: "uppercase",
                letterSpacing: 0.4,
                minWidth: 94,
              }}
            >
              {e.stage}
            </span>
            <span style={{ color: theme.textPrimary }}>{e.label}</span>
            {e.confidence && <Badge tone="muted">{e.confidence}</Badge>}
            {e.source && <span style={{ fontSize: 11, color: theme.textMuted }}>{e.source}</span>}
          </li>
        ))}
      </ol>
    </figure>
  );
}
