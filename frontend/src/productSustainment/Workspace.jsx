import { api } from "../api.js";
import ReportWorkspaceShell from "../reportWorkspace/ReportWorkspaceShell.jsx";
import { AGENT_NAME, REPORT_ORDER, reportLabel } from "./reportMeta.js";
import ReportView from "./ReportView.jsx";

// No Gate: a run is never blocked. Without BOM matrices it still produces
// nine reports, titled an obsolescence and exposure scan so they cannot be
// mistaken for a sustainment analysis.
export default function Workspace() {
  const adapter = {
    agentName: AGENT_NAME,
    reportOrder: REPORT_ORDER,
    reportLabel,
    routes: {
      configure: "/agents/product-sustainment/structure",
      run: (runId) => `/agents/product-sustainment/runs/${runId}`,
      report: (runId, reportId) => `/agents/product-sustainment/runs/${runId}/reports/${reportId}`,
    },
    listReports: api.productSustainment.listRunReports,
    getReport: api.productSustainment.getReport,
    listRuns: api.productSustainment.listRuns,
    getRun: api.productSustainment.getRun,
    startRun: api.productSustainment.startRun,
    exportDocx: api.productSustainment.exportRunDocx,
    ReportView,
    emptyStateCopy: {
      title: "No reports yet",
      body: "Run the agent to compute component runout across your BOM and research obsolescence, supplier risk and candidate alternates. Missing inputs never block a run — each report states what was unavailable and why.",
      cta: "Run",
    },
    runningStateCopy: {
      title: "Computing runout and researching exposure",
      body: "The platform computes every component's runout across the matrices, then the agent researches lifecycle notices and candidate alternates and writes all nine reports. You can leave this page and come back — the run keeps going.",
    },
  };

  return <ReportWorkspaceShell adapter={adapter} />;
}
