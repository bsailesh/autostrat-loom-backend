// Impact vs effort 2×2, from structured coordinates. Effort here is a
// relative public-evidence judgement labelled `estimated`, NOT comparable
// to the effort figures in the customer's roadmap -- the caption says so
// on the chart itself, where a reader would otherwise assume it.
//
// Contract (voice_of_customer/reports.py):
//   | Opportunity | Impact | Effort | Effort basis | Confidence |
import { theme } from "../../theme.js";
import { col, Figure, num } from "./common.jsx";

export function detectOpportunityMap(table) {
  const { headers, rows } = table;
  const o = col(headers, /^opportunity$/i);
  const imp = col(headers, /^impact$/i);
  const eff = col(headers, /^effort$/i);
  if (o === -1 || imp === -1 || eff === -1 || !rows.length) return null;
  const conf = col(headers, /^confidence$/i);
  const points = [];
  for (const row of rows) {
    const impact = num(row[imp]?.text);
    const effort = num(row[eff]?.text);
    if (!row[o]?.text || impact === null || effort === null) return null;
    if (impact < 0 || impact > 10 || effort < 0 || effort > 10) return null;
    points.push({ label: row[o].text, impact, effort, confidence: conf >= 0 ? row[conf]?.text || "" : "" });
  }
  return { points };
}

const W = 560;
const H = 360;
const PAD = 44;

export function OpportunityMapExhibit({ data }) {
  const x = (effort) => PAD + (effort / 10) * (W - PAD * 2);
  const y = (impact) => H - PAD - (impact / 10) * (H - PAD * 2);
  const quadrant = (label, qx, qy) => (
    <text x={qx} y={qy} fontSize="11" fill={theme.textMuted} textAnchor="middle">
      {label}
    </text>
  );
  return (
    <Figure title="Impact vs effort" note="effort is estimated from public evidence — not comparable to your roadmap's effort figures">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Impact versus effort">
        <rect x={PAD} y={PAD} width={W - PAD * 2} height={H - PAD * 2} fill={theme.surfaceMuted} stroke={theme.border} />
        <line x1={x(5)} y1={PAD} x2={x(5)} y2={H - PAD} stroke={theme.border} strokeDasharray="4 4" />
        <line x1={PAD} y1={y(5)} x2={W - PAD} y2={y(5)} stroke={theme.border} strokeDasharray="4 4" />
        {quadrant("High impact, lower effort", x(2.5), PAD + 16)}
        {quadrant("High impact, higher effort", x(7.5), PAD + 16)}
        {quadrant("Lower impact, lower effort", x(2.5), H - PAD - 8)}
        {quadrant("Lower impact, higher effort", x(7.5), H - PAD - 8)}
        <text x={W / 2} y={H - 10} fontSize="11" fill={theme.textSecondary} textAnchor="middle">
          Effort (estimated, 1–10) →
        </text>
        <text x={14} y={H / 2} fontSize="11" fill={theme.textSecondary} textAnchor="middle" transform={`rotate(-90 14 ${H / 2})`}>
          Impact (1–10) →
        </text>
        {data.points.map((p, i) => (
          <g key={i}>
            <circle cx={x(p.effort)} cy={y(p.impact)} r="6" fill={theme.orange} stroke="#fff" strokeWidth="1.5" />
            <text x={x(p.effort) + 9} y={y(p.impact) + 4} fontSize="11" fill={theme.textPrimary}>
              {p.label.length > 34 ? `${p.label.slice(0, 33)}…` : p.label}
            </text>
          </g>
        ))}
      </svg>
    </Figure>
  );
}
