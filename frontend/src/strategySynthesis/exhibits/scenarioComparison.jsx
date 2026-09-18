// Scenario comparison -- Report 6's "Project | <scenario columns...>" rank
// table as a movement matrix. Never assumes a fixed number or names of
// scenarios (2-6 per PUT /scenarios' own limit); the first scenario column
// is treated as the baseline everything else is compared against, since
// every real example (agent5_test_output_v2.md and production runs) puts
// "Base" first. Kept simple -- this exhibit matters less than capacity
// utilisation.
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { theme } from "../../theme.js";

function parseRank(text) {
  const m = String(text).match(/\d+/);
  return m ? parseInt(m[0], 10) : null;
}

export function detectScenarioComparison(table) {
  const { headers, rows } = table;
  if (!/^project/i.test(headers[0] || "")) return null;
  const scenarioNames = headers.slice(1);
  if (scenarioNames.length < 2 || !rows.length) return null;

  const parsedRows = [];
  for (const row of rows) {
    const project = row[0]?.text;
    if (!project) return null;
    const ranks = [];
    for (let i = 1; i < headers.length; i++) {
      const rank = parseRank(row[i]?.text);
      if (rank === null) return null; // not a pure rank table -- fall back to a plain table
      ranks.push({ rank, bold: !!row[i]?.bold });
    }
    parsedRows.push({ project, ranks });
  }
  return { scenarioNames, rows: parsedRows };
}

function MovementPill({ rank, bold, baselineRank }) {
  const delta = baselineRank == null ? 0 : rank - baselineRank;
  let Icon = Minus;
  let color = theme.textMuted;
  if (delta < 0) {
    Icon = ArrowUp;
    color = theme.success;
  } else if (delta > 0) {
    Icon = ArrowDown;
    color = theme.danger;
  }
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 12.5,
        fontWeight: bold ? 700 : 500,
        color: bold ? theme.textPrimary : theme.textSecondary,
        background: bold ? theme.orangeSoft : "transparent",
        padding: bold ? "2px 7px" : "2px 0",
        borderRadius: 6,
      }}
    >
      {rank}
      {baselineRank != null && delta !== 0 && <Icon size={11} color={color} />}
    </span>
  );
}

export function ScenarioComparisonExhibit({ data }) {
  const { scenarioNames, rows } = data;
  return (
    <div style={{ margin: "4px 0 20px", border: `1px solid ${theme.border}`, borderRadius: 10, overflow: "hidden" }}>
      <p
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.6,
          textTransform: "uppercase",
          color: theme.textSecondary,
          margin: 0,
          padding: "12px 16px 0",
        }}
      >
        Scenario comparison
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5, marginTop: 10 }}>
        <thead>
          <tr style={{ background: theme.surfaceMuted }}>
            <th style={{ textAlign: "left", padding: "8px 16px", fontWeight: 700, color: theme.textSecondary, borderBottom: `1px solid ${theme.border}` }}>
              Project
            </th>
            {scenarioNames.map((name, i) => (
              <th
                key={name}
                style={{ textAlign: "left", padding: "8px 12px", fontWeight: 700, color: theme.textSecondary, borderBottom: `1px solid ${theme.border}` }}
              >
                {name}
                {i === 0 && <span style={{ fontWeight: 500, color: theme.textMuted }}> (baseline)</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.project}>
              <td style={{ padding: "7px 16px", borderBottom: `1px solid ${theme.border}`, fontWeight: 600 }}>{r.project}</td>
              {r.ranks.map((cell, i) => (
                <td key={i} style={{ padding: "7px 12px", borderBottom: `1px solid ${theme.border}` }}>
                  <MovementPill rank={cell.rank} bold={cell.bold} baselineRank={i === 0 ? null : r.ranks[0].rank} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
