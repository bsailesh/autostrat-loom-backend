import { useMemo } from "react";
import { AlertTriangle } from "lucide-react";
import { theme } from "../theme.js";
import { opensWithGoverningInsight } from "./reportMeta.js";
import { extractGoverningInsight, extractKeyInsights, liftStrap } from "../reportWorkspace/insights.js";
import { GoverningInsightBox, KeyInsightsBox } from "../reportWorkspace/InsightBoxes.jsx";
import { ReportMarkdown } from "../reportWorkspace/markdown.jsx";
import exhibits from "./exhibits/index.js";

// An unscoped run titles every report with this prefix (see
// tech_regulation/scoping.py). The reader must never mistake an industry
// survey for their own regulatory obligations, so the prefix is lifted out
// of the title into a banner here rather than left to be skimmed past.
const UNSCOPED_PREFIX = "UNSCOPED INDUSTRY SURVEY — ";

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

  const unscoped = (report.title || "").startsWith(UNSCOPED_PREFIX);
  const title = unscoped ? report.title.slice(UNSCOPED_PREFIX.length) : report.title;

  return (
    <article style={{ maxWidth: 860 }}>
      {unscoped && (
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
              Unscoped industry survey — not an assessment of your obligations
            </p>
            <p style={{ margin: "3px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>
              This run had no applicability envelope, so nothing below has been checked against any product
              category, certification basis or platform. No finding here binds you. Supply product categories
              and certification basis, then re-run, to turn this into an applicability assessment.
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
