import { useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "../api.js";
import { Button, Spinner } from "../components/atoms.jsx";
import { theme } from "../theme.js";
import { EXPOSURE_SCAN_TITLE_PREFIX, RUNOUT_REPORT_NUMBER, opensWithGoverningInsight } from "./reportMeta.js";
import { extractGoverningInsight, extractKeyInsights, liftStrap } from "../reportWorkspace/insights.js";
import { GoverningInsightBox, KeyInsightsBox } from "../reportWorkspace/InsightBoxes.jsx";
import { ReportMarkdown } from "../reportWorkspace/markdown.jsx";
import exhibits from "./exhibits/index.js";
import { RunoutTableView, rowsFromApi } from "./exhibits/runoutTable.jsx";

// The report markdown carries the most urgent components only; the full
// computed table for the run is fetched on request.
function FullRunoutTable({ runId }) {
  const [state, setState] = useState({ open: false, loading: false, data: null, error: "" });

  async function open() {
    setState((s) => ({ ...s, open: true, loading: true }));
    try {
      const data = await api.productSustainment.getRunout(runId);
      setState({ open: true, loading: false, data, error: "" });
    } catch (e) {
      setState({ open: true, loading: false, data: null, error: e.message || "Couldn't load the full table." });
    }
  }

  if (!state.open) {
    return (
      <div style={{ margin: "16px 0" }}>
        <Button small onClick={open}>Show the full runout table for this run</Button>
      </div>
    );
  }
  if (state.loading) return <Spinner size={16} />;
  if (state.error) return <p style={{ fontSize: 12, color: theme.danger }}>{state.error}</p>;
  return (
    <RunoutTableView
      rows={rowsFromApi(state.data.rows)}
      years={(state.data.horizon_years || []).map(String)}
      caption="Full runout table — every component in this run"
      note={`${state.data.insufficient.length.toLocaleString()} further part(s) have no runout date and are listed under Insufficient data.`}
    />
  );
}

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

  // A run with no BOM is an obsolescence and exposure scan. Lifted out of the
  // title into a banner so it cannot be skimmed past.
  const scan = (report.title || "").startsWith(EXPOSURE_SCAN_TITLE_PREFIX);
  const title = scan ? report.title.slice(EXPOSURE_SCAN_TITLE_PREFIX.length) : report.title;

  return (
    <article style={{ maxWidth: 1000 }}>
      {scan && (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start", background: theme.dangerBg, border: `1px solid ${theme.danger}`,
                      borderRadius: 6, padding: "10px 12px", marginBottom: 14 }}>
          <AlertTriangle size={15} color={theme.danger} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <p style={{ margin: 0, fontSize: 12.5, fontWeight: 700, color: theme.danger }}>
              Obsolescence and exposure scan — not a sustainment analysis
            </p>
            <p style={{ margin: "3px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>
              No BOM matrices were loaded, so no runout date could be computed and nothing below is traced to the LRUs it
              affects. Load both matrices, demand and inventory to turn this into a sustainment analysis.
            </p>
          </div>
        </div>
      )}

      <header style={{ marginBottom: 6 }}>
        <p style={{ fontSize: 12, color: theme.textMuted, margin: 0, fontWeight: 600 }}>Report {report.report_number}</p>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "2px 0 0", color: theme.textPrimary }}>{title}</h1>
        {parsed.strap && <p style={{ fontSize: 12, color: theme.textMuted, margin: "8px 0 0", lineHeight: 1.5 }}>{parsed.strap}</p>}
      </header>

      <div style={{ marginTop: 16 }}>
        {parsed.box?.kind === "gi" && <GoverningInsightBox data={parsed.box.data} />}
        {parsed.box?.kind === "ki" && <KeyInsightsBox data={parsed.box.data} />}
        {parsed.segments.map((seg, i) =>
          seg.kind === "exhibit" ? <seg.Component key={i} data={seg.data} /> : <ReportMarkdown key={i}>{seg.text}</ReportMarkdown>
        )}
        {Number(report.report_number) === RUNOUT_REPORT_NUMBER && !scan && <FullRunoutTable key={report.run_id} runId={report.run_id} />}
      </div>
    </article>
  );
}
