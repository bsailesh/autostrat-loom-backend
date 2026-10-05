// Harvey Ball grid -- the same contract as Market Insights' competitive
// feature matrix (a Markdown table, first header "Feature", one column per
// vendor, each cell one of ● ◕ ◑ ◔ ○ —), but this agent's own renderer in
// its own registry rather than an import, consistent with agent
// independence.
//
// "—" is UNDISCLOSED, which differs from ○ none; it is drawn as a dash,
// never as an empty ball, so the two cannot be confused.
import { theme } from "../../theme.js";
import { Figure } from "./common.jsx";

const LEVELS = {
  "●": { fill: 1, label: "full" },
  "◕": { fill: 0.75, label: "strong" },
  "◑": { fill: 0.5, label: "partial" },
  "◔": { fill: 0.25, label: "limited" },
  "○": { fill: 0, label: "none" },
  "—": { fill: null, label: "undisclosed" },
  "-": { fill: null, label: "undisclosed" },
  "–": { fill: null, label: "undisclosed" },
};

function level(raw) {
  const t = String(raw || "").trim();
  if (!t) return null;
  return LEVELS[t[0]] || null;
}

export function detectHarveyBallGrid(table) {
  const { headers, rows } = table;
  if (!/^feature$/i.test(String(headers[0] || "").trim()) || headers.length < 3 || headers.length > 7) return null;
  if (!rows.length) return null;
  const grid = [];
  for (const row of rows) {
    const cells = headers.slice(1).map((_, i) => level(row[i + 1]?.text));
    if (!row[0]?.text || cells.some((c) => c === null)) return null;
    grid.push({ feature: row[0].text, cells });
  }
  return { vendors: headers.slice(1), grid };
}

function Ball({ fill, label }) {
  if (fill === null) {
    return (
      <span title={label} style={{ fontSize: 14, color: theme.textMuted }}>
        —
      </span>
    );
  }
  const r = 8;
  const angle = fill * 2 * Math.PI;
  const x = 10 + r * Math.sin(angle);
  const y = 10 - r * Math.cos(angle);
  const large = fill > 0.5 ? 1 : 0;
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" role="img" aria-label={label}>
      <title>{label}</title>
      <circle cx="10" cy="10" r={r} fill="#fff" stroke={theme.navy} strokeWidth="1.4" />
      {fill >= 1 && <circle cx="10" cy="10" r={r} fill={theme.navy} />}
      {fill > 0 && fill < 1 && <path d={`M10 10 L10 ${10 - r} A${r} ${r} 0 ${large} 1 ${x} ${y} Z`} fill={theme.navy} />}
    </svg>
  );
}

export function HarveyBallGridExhibit({ data }) {
  return (
    <Figure title="Competitive feature comparison" note="● full · ◕ strong · ◑ partial · ◔ limited · ○ none · — undisclosed">
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "6px 8px", color: theme.textMuted, fontWeight: 600 }}>Feature</th>
              {data.vendors.map((v, i) => (
                <th key={i} style={{ padding: "6px 8px", color: i === 0 ? theme.navy : theme.textPrimary, fontWeight: 700 }}>
                  {v}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.grid.map((row, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${theme.border}`, background: i % 2 ? theme.surfaceMuted : theme.surface }}>
                <td style={{ padding: "6px 8px", color: theme.textPrimary }}>{row.feature}</td>
                {row.cells.map((c, j) => (
                  <td key={j} style={{ padding: "6px 8px", textAlign: "center" }}>
                    <Ball fill={c.fill} label={c.label} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Figure>
  );
}
