import { Navigate } from "react-router-dom";
import { api } from "../api.js";
import ReportWorkspaceShell from "../reportWorkspace/ReportWorkspaceShell.jsx";
import { Spinner } from "../components/atoms.jsx";
import { PageHeader } from "../components/PageHeader.jsx";
import { theme } from "../theme.js";
import { useMarketInsightsStatus } from "./useMarketInsights.js";
import { AGENT_NAME, REPORT_ORDER, reportLabel } from "./reportMeta.js";
import ReportView from "./ReportView.jsx";

// Market Insights' own precondition: a scope must be configured before the
// workspace is usable at all. Wraps the shared shell rather than living
// inside it, so this agent's requirement can't leak into another agent's
// workspace (see reportWorkspace/ReportWorkspaceShell.jsx's `Gate` contract).
function ScopeGate({ children }) {
  // Own fetch, independent of the shared shell's run-list boot fetch below --
  // a small doubled network call, traded for keeping the scope precondition
  // entirely out of the shared shell (see ReportWorkspaceShell's Gate contract).
  const { scope, error } = useMarketInsightsStatus({ poll: false });

  if (error) {
    return (
      <>
        <PageHeader title={AGENT_NAME} />
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
          <p style={{ color: theme.danger, fontSize: 13 }}>{error}</p>
        </div>
      </>
    );
  }
  if (scope === null) {
    return (
      <>
        <PageHeader title={AGENT_NAME} />
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
          <Spinner size={20} />
        </div>
      </>
    );
  }
  if (!scope?.configured || !(scope.product_line || "").trim()) {
    return <Navigate to="/agents/market-insights/scope" replace />;
  }
  return children;
}

export default function Workspace() {
  const adapter = {
    agentName: AGENT_NAME,
    reportOrder: REPORT_ORDER,
    reportLabel,
    routes: {
      configure: "/agents/market-insights/scope",
      run: (runId) => `/agents/market-insights/runs/${runId}`,
      report: (runId, reportId) => `/agents/market-insights/runs/${runId}/reports/${reportId}`,
    },
    listReports: api.marketInsights.listRunReports,
    getReport: api.marketInsights.getReport,
    listRuns: api.marketInsights.listRuns,
    getRun: api.marketInsights.getRun,
    startRun: api.marketInsights.startRun,
    exportDocx: api.marketInsights.exportRunDocx,
    Gate: ScopeGate,
    ReportView,
    emptyStateCopy: {
      title: "No reports yet",
      body: "Run the agent to generate your first set of nine Market Insights reports from the scope you configured.",
      cta: "Run Market Insights",
    },
    runningStateCopy: {
      title: "Research in progress",
      body: (
        <>
          The agent is doing live web research and writing all nine reports. A full run typically takes
          <strong> 30–60 minutes</strong> — you can leave this page and come back; the run keeps going.
        </>
      ),
    },
  };

  return <ReportWorkspaceShell adapter={adapter} />;
}
