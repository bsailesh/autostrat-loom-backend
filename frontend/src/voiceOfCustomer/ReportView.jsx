import { useMemo } from "react";
import { AlertTriangle } from "lucide-react";
import { theme } from "../theme.js";
import { opensWithGoverningInsight, TIER_2_TITLE_PREFIX } from "./reportMeta.js";
import { extractGoverningInsight, extractKeyInsights, liftStrap } from "../reportWorkspace/insights.js";
import { GoverningInsightBox, KeyInsightsBox } from "../reportWorkspace/InsightBoxes.jsx";
import { ReportMarkdown } from "../reportWorkspace/markdown.jsx";
import exhibits from "./exhibits/index.js";

// A Tier 2 run titles every report "External customer-context analysis — …"
// (voice_of_customer/context.py). A reader must never mistake it for a
// voice of customer analysis, so the prefix is lifted into a banner here
// rather than left in a title to be skimmed past.
export default function ReportView({ report }) {
  const parsed = useMemo(() => {
    if (!report) return null;
    const { strap, body: afterStrap } = liftStrap(report.content || "");

    let box = null;
    let body = afterStrap;
    if (opensWithGoverningInsight(report.report_number)) {
      const gi = extractGoverningInsight(afterStrap);
      if (gi) {
        box = { kind: "gi", data: gi };
        body = gi.body;
      }
    } else {
      const ki = extractKeyInsights(afterStrap);
      if (ki) {
        box = { kind: "ki", data: ki };
        body = ki.body;
      }
    }
    return { strap, box, segments: exhibits.resolve(body) };
  }, [report]);

  if (!report) return null;

  const tier2 = (report.title || "").startsWith(TIER_2_TITLE_PREFIX);
  const title = tier2 ? report.title.slice(TIER_2_TITLE_PREFIX.length) : report.title;

  return (
    <article style={{ maxWidth: 860 }}>
      {tier2 && (
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
            background: theme.dangerBg,
            border: `1px solid ${theme.danger}`,
            borderRadius: 6,
            padding: "10px 12px",
            marginBottom: 14,
          }}
        >
          <AlertTriangle size={15} color={theme.danger} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <p style={{ margin: 0, fontSize: 12.5, fontWeight: 700, color: theme.danger }}>
              External customer-context analysis — not a voice of customer analysis
            </p>
            <p style={{ margin: "3px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>
              No customer evidence was supplied, so this run is built from public sources alone. Sentiment,
              frequency rankings, validated personas, win/loss rationale and tests of your stated beliefs are
              unavailable, and the report says so. Uploading tickets, claims, surveys, visit notes or win/loss
              reports turns this into a voice of customer analysis.
            </p>
          </div>
        </div>
      )}

      <header style={{ marginBottom: 6 }}>
        <p style={{ fontSize: 12, color: theme.textMuted, margin: 0, fontWeight: 600 }}>
          Report {report.report_number}
        </p>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "2px 0 0", color: theme.textPrimary }}>{title}</h1>
        {parsed.strap && (
          <p style={{ fontSize: 12, color: theme.textMuted, margin: "8px 0 0", lineHeight: 1.5 }}>{parsed.strap}</p>
        )}
      </header>

      <div style={{ marginTop: 16 }}>
        {parsed.box?.kind === "gi" && <GoverningInsightBox data={parsed.box.data} />}
        {parsed.box?.kind === "ki" && <KeyInsightsBox data={parsed.box.data} />}
        {parsed.segments.map((seg, i) =>
          seg.kind === "exhibit" ? (
            <seg.Component key={i} data={seg.data} />
          ) : (
            <ReportMarkdown key={i}>{seg.text}</ReportMarkdown>
          )
        )}
      </div>
    </article>
  );
}
