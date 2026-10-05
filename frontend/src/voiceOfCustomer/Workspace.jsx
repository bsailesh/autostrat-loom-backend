import { api } from "../api.js";
import ReportWorkspaceShell from "../reportWorkspace/ReportWorkspaceShell.jsx";
import { AGENT_NAME, REPORT_ORDER, reportLabel } from "./reportMeta.js";
import ReportView from "./ReportView.jsx";

// No Gate: a run is never blocked. Without customer evidence it still
// produces nine reports, titled an external customer-context analysis so
// they cannot be mistaken for a voice of customer analysis.
export default function Workspace() {
  const adapter = {
    agentName: AGENT_NAME,
    reportOrder: REPORT_ORDER,
    reportLabel,
    routes: {
      configure: "/agents/voice-of-customer/context",
      run: (runId) => `/agents/voice-of-customer/runs/${runId}`,
      report: (runId, reportId) => `/agents/voice-of-customer/runs/${runId}/reports/${reportId}`,
    },
    listReports: api.voiceOfCustomer.listRunReports,
    getReport: api.voiceOfCustomer.getReport,
    listRuns: api.voiceOfCustomer.listRuns,
    getRun: api.voiceOfCustomer.getRun,
    startRun: api.voiceOfCustomer.startRun,
    exportDocx: api.voiceOfCustomer.exportRunDocx,
    ReportView,
    emptyStateCopy: {
      title: "No reports yet",
      body: "Run the agent to analyse what your customers say. Without uploaded evidence the run still goes ahead — as an external customer-context analysis from public sources, titled as such, with each customer-evidence analysis stated as unavailable.",
      cta: "Run",
    },
    runningStateCopy: {
      title: "Analysing customer evidence",
      body: "The agent is researching the public context, then reading your evidence and writing all nine reports. You can leave this page and come back — the run keeps going.",
    },
  };

  return <ReportWorkspaceShell adapter={adapter} />;
}
