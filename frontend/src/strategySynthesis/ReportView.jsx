import { useMemo } from "react";
import { theme } from "../theme.js";
import { opensWithGoverningInsight } from "./reportMeta.js";
import { extractGoverningInsight, extractKeyInsights, liftStrap } from "../reportWorkspace/insights.js";
import { GoverningInsightBox, KeyInsightsBox } from "../reportWorkspace/InsightBoxes.jsx";
import { ReportMarkdown } from "../reportWorkspace/markdown.jsx";
import exhibits from "./exhibits/index.js";
import CandidateActions from "./candidates/CandidateActions.jsx";

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
    const segments = exhibits.resolve(body);
    return { strap, box, segments };
  }, [report]);

  if (!report) return null;

  return (
    <article style={{ maxWidth: 860 }}>
      <header style={{ marginBottom: 6 }}>
        <p style={{ fontSize: 12, color: theme.textMuted, margin: 0, fontWeight: 600 }}>
          Report {report.report_number}
        </p>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "2px 0 0", color: theme.textPrimary }}>{report.title}</h1>
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
        {report.report_number === 7 && <CandidateActions />}
      </div>
    </article>
  );
}
