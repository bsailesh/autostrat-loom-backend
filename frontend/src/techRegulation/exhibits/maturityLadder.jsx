// Maturity ladder -- four stacked tiers, Investigate at the top through
// Deployed at the bottom. Explicitly NOT a radar or radial chart: the spec
// says so, and a ladder reads as "how far along is this" in a way a radial
// plot of the same data does not.
//
// Parses the table contract in tech_regulation/reports.py:
//   | Tier | Technology | Maturity | Trend | Evidence | Confidence |
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";

// Top to bottom: least mature first, so the ladder is read downward into
// deployment.
const TIERS = [
  { key: "investigate", label: "Investigate", note: "emerging technology" },
  { key: "monitor", label: "Monitor", note: "early development" },
  { key: "demonstrated", label: "Demonstrated", note: "pilot / prototype" },
  { key: "deployed", label: "Deployed", note: "commercial use" },
];

const TREND_TONE = {
  increasing: { tone: "success", arrow: "▲" },
  emerging: { tone: "accent", arrow: "▲" },
  stable: { tone: "muted", arrow: "■" },
  declining: { tone: "warning", arrow: "▼" },
  disrupted: { tone: "danger", arrow: "✕" },
};

function col(headers, re) {
  return headers.findIndex((h) => re.test(h));
}

function tierKey(raw) {
  const v = String(raw || "").toLowerCase();
  return TIERS.find((t) => v.includes(t.key))?.key || null;
}

export function detectMaturityLadder(table) {
  const { headers, rows } = table;
  const tierIdx = col(headers, /^tier$/i);
  const techIdx = col(headers, /^technolog/i);
  const maturityIdx = col(headers, /^maturity/i);
  const trendIdx = col(headers, /^trend$/i);
  if (tierIdx === -1 || techIdx === -1 || maturityIdx === -1 || trendIdx === -1) return null;
  if (!rows.length) return null;

  const evidenceIdx = col(headers, /^evidence/i);
  const confidenceIdx = col(headers, /^confidence/i);

  const entries = [];
  for (const row of rows) {
    const tier = tierKey(row[tierIdx]?.text);
    const technology = row[techIdx]?.text;
    // Shape doesn't hold -- fall back to a plain table rather than render a
    // half-populated ladder.
    if (!tier || !technology) return null;
    entries.push({
      tier,
      technology,
      maturity: row[maturityIdx]?.text || "",
      trend: String(row[trendIdx]?.text || "").toLowerCase().trim(),
      evidence: evidenceIdx >= 0 ? row[evidenceIdx]?.text || "" : "",
      confidence: confidenceIdx >= 0 ? row[confidenceIdx]?.text || "" : "",
    });
  }
  return { entries };
}

export function MaturityLadderExhibit({ data }) {
  const { entries } = data;

  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>Technology maturity ladder</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>
          observed maturity and activity — not an investment recommendation
        </span>
      </figcaption>

      {TIERS.map((tier, i) => {
        const inTier = entries.filter((e) => e.tier === tier.key);
        return (
          <div
            key={tier.key}
            style={{
              display: "flex",
              gap: 14,
              padding: "12px 14px",
              borderTop: i === 0 ? "none" : `1px solid ${theme.border}`,
              background: i % 2 ? theme.surfaceMuted : theme.surface,
            }}
          >
            <div style={{ width: 128, flexShrink: 0 }}>
              <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: theme.navy }}>{tier.label}</p>
              <p style={{ margin: "2px 0 0", fontSize: 11, color: theme.textMuted }}>{tier.note}</p>
            </div>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
              {inTier.length === 0 ? (
                <p style={{ margin: 0, fontSize: 12, color: theme.textMuted, fontStyle: "italic" }}>
                  Nothing at this tier
                </p>
              ) : (
                inTier.map((e, j) => {
                  const trend = TREND_TONE[e.trend] || { tone: "muted", arrow: "" };
                  return (
                    <div key={j} style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>{e.technology}</span>
                      <Badge tone={trend.tone}>
                        {trend.arrow} {e.trend || "trend unstated"}
                      </Badge>
                      {e.maturity && (
                        <span style={{ fontSize: 11, color: theme.textSecondary }}>{e.maturity}</span>
                      )}
                      {e.confidence && <Badge tone="muted">{e.confidence}</Badge>}
                      {e.evidence && (
                        <span style={{ fontSize: 11, color: theme.textMuted, flexBasis: "100%" }}>{e.evidence}</span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        );
      })}
    </figure>
  );
}
