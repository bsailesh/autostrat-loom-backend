// Quadrant layouts: SWOT (Report 7) and the customer insights matrix
// (Report 10). Both are structured tables the agent emits; both fall back
// to a plain table if any row names a quadrant outside the contract.
//
// Contracts (voice_of_customer/reports.py):
//   | Quadrant | Statement | Evidence | Business impact | Confidence |
//   | Audience | Quadrant | Entry | Evidence | Confidence |
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";
import { col, confidenceToneName, Figure } from "./common.jsx";

// ---------------------------------------------------------------------------
// SWOT
// ---------------------------------------------------------------------------

const SWOT = [
  { key: "strengths", label: "Strengths", color: theme.success, note: "internal" },
  { key: "weaknesses", label: "Weaknesses", color: theme.warning, note: "internal" },
  { key: "opportunities", label: "Opportunities", color: theme.navyLight, note: "external" },
  { key: "threats", label: "Threats", color: theme.danger, note: "external" },
];

export function detectSwot(table) {
  const { headers, rows } = table;
  const q = col(headers, /^quadrant$/i);
  const s = col(headers, /^statement$/i);
  if (q === -1 || s === -1 || col(headers, /^audience$/i) !== -1 || !rows.length) return null;
  const e = col(headers, /^evidence$/i);
  const b = col(headers, /^business impact$/i);
  const c = col(headers, /^confidence$/i);
  const entries = [];
  for (const row of rows) {
    const key = String(row[q]?.text || "").toLowerCase().trim();
    if (!SWOT.some((x) => x.key === key) || !row[s]?.text) return null;
    entries.push({
      quadrant: key,
      statement: row[s].text,
      evidence: e >= 0 ? row[e]?.text || "" : "",
      impact: b >= 0 ? row[b]?.text || "" : "",
      confidence: c >= 0 ? row[c]?.text || "" : "",
    });
  }
  return { entries };
}

function Entry({ title, evidence, extra, confidence }) {
  return (
    <div style={{ marginBottom: 9 }}>
      <p style={{ margin: 0, fontSize: 12.5, color: theme.textPrimary, fontWeight: 600, lineHeight: 1.4 }}>
        {title} {confidence && <Badge tone={confidenceToneName(confidence)}>{confidence}</Badge>}
      </p>
      {extra && <p style={{ margin: "2px 0 0", fontSize: 11.5, color: theme.textSecondary }}>{extra}</p>}
      {evidence && <p style={{ margin: "2px 0 0", fontSize: 11, color: theme.textMuted }}>{evidence}</p>}
    </div>
  );
}

function Quad({ label, color, note, children }) {
  return (
    <div style={{ border: `1px solid ${theme.border}`, borderTop: `3px solid ${color}`, borderRadius: 6, padding: "10px 12px", minWidth: 0 }}>
      <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700, color }}>
        {label}
        {note && <span style={{ fontWeight: 400, color: theme.textMuted, marginLeft: 6 }}>{note}</span>}
      </p>
      {children}
    </div>
  );
}

const empty = <p style={{ margin: 0, fontSize: 12, color: theme.textMuted, fontStyle: "italic" }}>Nothing evidenced</p>;

export function SwotExhibit({ data }) {
  return (
    <Figure title="SWOT" note="strengths and weaknesses internal to product capability; opportunities and threats external">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10 }}>
        {SWOT.map((q) => {
          const items = data.entries.filter((e) => e.quadrant === q.key);
          return (
            <Quad key={q.key} label={q.label} color={q.color} note={q.note}>
              {items.length
                ? items.map((e, i) => (
                    <Entry key={i} title={e.statement} extra={e.impact} evidence={e.evidence} confidence={e.confidence} />
                  ))
                : empty}
            </Quad>
          );
        })}
      </div>
    </Figure>
  );
}

// ---------------------------------------------------------------------------
// Customer insights matrix
// ---------------------------------------------------------------------------

const AUDIENCES = [
  { key: "existing", label: "Existing customers" },
  { key: "adjacent", label: "Adjacent customers" },
];

const INSIGHT_QUADS = [
  { key: "firmographics", label: "Firmographics" },
  { key: "buyer persona", label: "Buyer persona" },
  { key: "pain points and triggers", label: "Pain points and triggers" },
  { key: "jobs-to-be-done", label: "Jobs-to-be-done" },
];
const GAPS = "unsolved market gaps";

function audienceKey(raw) {
  const v = String(raw || "").toLowerCase();
  return AUDIENCES.find((a) => v.startsWith(a.key))?.key || null;
}

function quadKey(raw) {
  const v = String(raw || "").toLowerCase().trim().replace(/jobs to be done/, "jobs-to-be-done");
  if (v === GAPS) return GAPS;
  return INSIGHT_QUADS.find((q) => q.key === v)?.key || null;
}

export function detectInsightsMatrix(table) {
  const { headers, rows } = table;
  const a = col(headers, /^audience$/i);
  const q = col(headers, /^quadrant$/i);
  const en = col(headers, /^entry$/i);
  if (a === -1 || q === -1 || en === -1 || !rows.length) return null;
  const e = col(headers, /^evidence$/i);
  const c = col(headers, /^confidence$/i);
  const entries = [];
  for (const row of rows) {
    const audience = audienceKey(row[a]?.text);
    const quadrant = quadKey(row[q]?.text);
    if (!audience || !quadrant || !row[en]?.text) return null;
    entries.push({
      audience,
      quadrant,
      entry: row[en].text,
      evidence: e >= 0 ? row[e]?.text || "" : "",
      confidence: c >= 0 ? row[c]?.text || "" : "",
    });
  }
  return { entries };
}

export function InsightsMatrixExhibit({ data }) {
  return (
    <Figure title="Customer insights matrix">
      {AUDIENCES.map((aud) => {
        const mine = data.entries.filter((e) => e.audience === aud.key);
        const gaps = mine.filter((e) => e.quadrant === GAPS);
        return (
          <div key={aud.key} style={{ marginBottom: 16 }}>
            <p style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700, color: theme.navy }}>{aud.label}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
              {INSIGHT_QUADS.map((q) => {
                const items = mine.filter((e) => e.quadrant === q.key);
                return (
                  <Quad key={q.key} label={q.label} color={theme.navyLight}>
                    {items.length
                      ? items.map((e, i) => <Entry key={i} title={e.entry} evidence={e.evidence} confidence={e.confidence} />)
                      : empty}
                  </Quad>
                );
              })}
            </div>
            <div style={{ marginTop: 10 }}>
              <Quad label="Unsolved market gaps" color={theme.orange}>
                {gaps.length
                  ? gaps.map((e, i) => <Entry key={i} title={e.entry} evidence={e.evidence} confidence={e.confidence} />)
                  : empty}
              </Quad>
            </div>
          </div>
        );
      })}
    </Figure>
  );
}
