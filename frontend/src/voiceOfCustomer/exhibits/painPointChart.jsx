// Pain point bar chart -- horizontal, ranked by severity × frequency
// (the Composite column). Where frequency is unavailable the agent sets
// Composite to severity alone and says so in Frequency basis; the chart
// shows that basis on every bar so a severity-only rank is never read as a
// frequency rank.
//
// Contract (voice_of_customer/reports.py):
//   | Pain point | Segment | Severity | Frequency | Composite | Frequency basis |
import { theme } from "../../theme.js";
import { col, Figure, num } from "./common.jsx";

export function detectPainPointChart(table) {
  const { headers, rows } = table;
  const p = col(headers, /^pain point$/i);
  const sev = col(headers, /^severity$/i);
  const comp = col(headers, /^composite$/i);
  const basis = col(headers, /^frequency basis$/i);
  if (p === -1 || sev === -1 || comp === -1 || basis === -1 || !rows.length) return null;
  const seg = col(headers, /^segment$/i);
  const freq = col(headers, /^frequency$/i);
  const entries = [];
  for (const row of rows) {
    const composite = num(row[comp]?.text);
    const severity = num(row[sev]?.text);
    if (!row[p]?.text || composite === null || severity === null) return null;
    entries.push({
      label: row[p].text,
      segment: seg >= 0 ? row[seg]?.text || "" : "",
      severity,
      frequency: freq >= 0 ? row[freq]?.text || "" : "",
      composite,
      basis: row[basis]?.text || "",
    });
  }
  entries.sort((a, b) => b.composite - a.composite);
  return { entries };
}

export function PainPointChartExhibit({ data }) {
  const max = Math.max(...data.entries.map((e) => e.composite), 1);
  return (
    <Figure title="Pain points" note="ranked by severity × frequency — basis shown on each bar">
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {data.entries.map((e, i) => {
          const severityOnly = /unavailable/i.test(e.basis);
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(140px, 32%) 1fr", gap: 10, alignItems: "center" }}>
              <div style={{ minWidth: 0 }}>
                <p style={{ margin: 0, fontSize: 12.5, fontWeight: 600, color: theme.textPrimary }}>{e.label}</p>
                {e.segment && <p style={{ margin: "1px 0 0", fontSize: 11, color: theme.textMuted }}>{e.segment}</p>}
              </div>
              <div>
                <div
                  style={{
                    height: 14,
                    width: `${Math.max(2, (e.composite / max) * 100)}%`,
                    borderRadius: 3,
                    background: severityOnly ? theme.textMuted : theme.orange,
                  }}
                />
                <p style={{ margin: "3px 0 0", fontSize: 11, color: theme.textSecondary }}>
                  {e.composite} · severity {e.severity}
                  {e.frequency && !severityOnly ? ` · frequency ${e.frequency}` : ""} · <em>{e.basis}</em>
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Figure>
  );
}
