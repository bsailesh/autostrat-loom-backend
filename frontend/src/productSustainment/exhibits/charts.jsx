// Line charts, from structured rows:
//
//   Inventory depletion  | Component | Year | Position |          (computed, results.py)
//   Failure trends       | Series | Period | Value | Measure |   (model-emitted, from counted evidence)
//
// One series per component or subsystem. Drawn as SVG -- never ASCII -- and
// a table that does not parse falls back to a plain table.
import { theme } from "../../theme.js";

const PALETTE = ["#1B2A4A", "#E8703A", "#2F8F58", "#B8791E", "#5B6BA8", "#C4462D", "#7A6E5B", "#3E8E9E"];

function col(headers, re) {
  return headers.findIndex((h) => re.test(String(h).trim()));
}

function num(raw) {
  const n = Number(String(raw ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function LineChart({ title, note, series, xLabels, zeroLine, yLabel }) {
  const W = 680, H = 300, L = 56, R = 140, T = 18, B = 34;
  const values = series.flatMap((s) => s.points.map((p) => p.y));
  let min = Math.min(...values, zeroLine ? 0 : Infinity);
  let max = Math.max(...values, zeroLine ? 0 : -Infinity);
  if (min === max) { min -= 1; max += 1; }
  const x = (i) => L + (xLabels.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (xLabels.length - 1));
  const y = (v) => T + ((max - v) * (H - T - B)) / (max - min);
  const ticks = [min, (min + max) / 2, max];
  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{title}</span>
        {note && <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>{note}</span>}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={title}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={theme.border} />
            <text x={L - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill={theme.textMuted}>{Math.round(t).toLocaleString()}</text>
          </g>
        ))}
        {zeroLine && min < 0 && (
          <>
            <rect x={L} y={y(0)} width={W - L - R} height={y(min) - y(0)} fill={theme.dangerBg} opacity="0.6" />
            <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke={theme.danger} strokeDasharray="4 3" />
            <text x={W - R + 4} y={y(0) + 4} fontSize="10" fill={theme.danger}>runout</text>
          </>
        )}
        {xLabels.map((lab, i) => (
          <text key={lab} x={x(i)} y={H - 12} fontSize="10" textAnchor="middle" fill={theme.textMuted}>{lab}</text>
        ))}
        {yLabel && <text x={12} y={T + 6} fontSize="10" fill={theme.textMuted}>{yLabel}</text>}
        {series.map((s, si) => {
          const color = PALETTE[si % PALETTE.length];
          const d = s.points.map((p, i) => `${i ? "L" : "M"}${x(xLabels.indexOf(p.x))},${y(p.y)}`).join(" ");
          const last = s.points[s.points.length - 1];
          return (
            <g key={s.name}>
              <path d={d} fill="none" stroke={color} strokeWidth="2" />
              {s.points.map((p) => <circle key={p.x} cx={x(xLabels.indexOf(p.x))} cy={y(p.y)} r="2.5" fill={color} />)}
              {last && si < 12 && (
                <text x={W - R + 4} y={y(last.y) + 4} fontSize="10" fill={color}>{s.name.length > 20 ? `${s.name.slice(0, 19)}…` : s.name}</text>
              )}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

function group(rows, key) {
  const out = new Map();
  for (const r of rows) {
    if (!out.has(r[key])) out.set(r[key], []);
    out.get(r[key]).push(r);
  }
  return out;
}

export function detectDepletionChart(table) {
  const { headers, rows } = table;
  const c = col(headers, /^component$/i), yr = col(headers, /^year$/i), p = col(headers, /^position$/i);
  if (c === -1 || yr === -1 || p === -1 || headers.length !== 3 || !rows.length) return null;
  const parsed = [];
  for (const row of rows) {
    const year = row[yr]?.text, pos = num(row[p]?.text);
    if (!row[c]?.text || !/^\d{4}$/.test(year || "") || pos === null) return null;
    parsed.push({ name: row[c].text, x: year, y: pos });
  }
  const xLabels = [...new Set(parsed.map((r) => r.x))].sort();
  const series = [...group(parsed, "name")].map(([name, pts]) => ({ name, points: pts.sort((a, b) => a.x.localeCompare(b.x)) }));
  return { series, xLabels };
}

export function DepletionChartExhibit({ data }) {
  return (
    <LineChart
      title="Projected inventory by year-end"
      note="computed by the platform · below zero is a shortfall"
      series={data.series}
      xLabels={data.xLabels}
      zeroLine
      yLabel="units"
    />
  );
}

export function detectFailureTrend(table) {
  const { headers, rows } = table;
  const s = col(headers, /^series$/i), per = col(headers, /^period$/i), v = col(headers, /^value$/i), m = col(headers, /^measure$/i);
  if (s === -1 || per === -1 || v === -1 || !rows.length) return null;
  const parsed = [];
  for (const row of rows) {
    const value = num(row[v]?.text);
    if (!row[s]?.text || !row[per]?.text || value === null) return null;
    parsed.push({ name: row[s].text, x: row[per].text, y: value, measure: m >= 0 ? row[m]?.text || "" : "" });
  }
  const xLabels = [...new Set(parsed.map((r) => r.x))].sort();
  const series = [...group(parsed, "name")].map(([name, pts]) => ({ name, points: pts.sort((a, b) => a.x.localeCompare(b.x)) }));
  const measures = [...new Set(parsed.map((r) => r.measure).filter(Boolean))];
  return { series, xLabels, measure: measures.join(", ") };
}

export function FailureTrendExhibit({ data }) {
  return (
    <LineChart
      title="Failure trends"
      note={`one line per component or subsystem${data.measure ? ` · ${data.measure}` : ""}`}
      series={data.series}
      xLabels={data.xLabels}
    />
  );
}
