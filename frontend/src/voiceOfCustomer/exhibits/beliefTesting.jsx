// Belief testing -- one row per belief the customer stated, with its
// outcome. The two "not found" causes are kept visibly distinct: "no
// evidence supplied that could test it" is not informative at all, "absent
// from the evidence supplied" is weakly informative, and merging them would
// lose exactly that difference.
//
// Contract (voice_of_customer/reports.py):
//   | Belief | Segment | Outcome | Evidence | Confidence |
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";
import { col, confidenceToneName, Figure } from "./common.jsx";

function outcome(raw) {
  const v = String(raw || "").toLowerCase();
  if (v.startsWith("corroborated")) return { key: "corroborated", label: "Corroborated", tone: "success" };
  if (v.startsWith("contradicted")) return { key: "contradicted", label: "Contradicted", tone: "danger" };
  if (v.startsWith("not found")) {
    if (v.includes("no evidence")) return { key: "nf-none", label: "Not found — no evidence supplied that could test it", tone: "muted" };
    if (v.includes("absent")) return { key: "nf-absent", label: "Not found — absent from the evidence supplied", tone: "warning" };
  }
  return null;
}

export function detectBeliefTesting(table) {
  const { headers, rows } = table;
  const b = col(headers, /^belief$/i);
  const o = col(headers, /^outcome$/i);
  if (b === -1 || o === -1 || !rows.length) return null;
  const s = col(headers, /^segment$/i);
  const e = col(headers, /^evidence$/i);
  const c = col(headers, /^confidence$/i);
  const entries = [];
  for (const row of rows) {
    const out = outcome(row[o]?.text);
    if (!out || !row[b]?.text) return null;
    entries.push({
      belief: row[b].text,
      segment: s >= 0 ? row[s]?.text || "" : "",
      outcome: out,
      evidence: e >= 0 ? row[e]?.text || "" : "",
      confidence: c >= 0 ? row[c]?.text || "" : "",
    });
  }
  return { entries };
}

export function BeliefTestingExhibit({ data }) {
  return (
    <Figure title="Your stated beliefs, tested" note="corroborated · contradicted · not found">
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {data.entries.map((e, i) => (
          <div
            key={i}
            style={{
              borderLeft: `3px solid ${
                e.outcome.tone === "success" ? theme.success : e.outcome.tone === "danger" ? theme.danger : e.outcome.tone === "warning" ? theme.warning : theme.border
              }`,
              paddingLeft: 10,
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>“{e.belief}”</span>
              {e.segment && <span style={{ fontSize: 11, color: theme.textMuted }}>{e.segment}</span>}
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
              <Badge tone={e.outcome.tone}>{e.outcome.label}</Badge>
              {e.confidence && <Badge tone={confidenceToneName(e.confidence)}>{e.confidence}</Badge>}
            </div>
            {e.evidence && (
              <p style={{ margin: "5px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>{e.evidence}</p>
            )}
          </div>
        ))}
      </div>
    </Figure>
  );
}
