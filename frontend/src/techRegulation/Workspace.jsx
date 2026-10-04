import { api } from "../api.js";
import ReportWorkspaceShell from "../reportWorkspace/ReportWorkspaceShell.jsx";
import { AGENT_NAME, REPORT_ORDER, reportLabel } from "./reportMeta.js";
import ReportView from "./ReportView.jsx";

// No Gate: a run is never blocked by incomplete scoping. An unscoped run
// still produces nine reports, titled so they cannot be mistaken for an
// applicability assessment.
export default function Workspace() {
  const adapter = {
    agentName: AGENT_NAME,
    reportOrder: REPORT_ORDER,
    reportLabel,
    routes: {
      configure: "/agents/tech-regulation/scope",
      run: (runId) => `/agents/tech-regulation/runs/${runId}`,
      report: (runId, reportId) => `/agents/tech-regulation/runs/${runId}/reports/${reportId}`,
    },
    listReports: api.techRegulation.listRunReports,
    getReport: api.techRegulation.getReport,
    listRuns: api.techRegulation.listRuns,
    getRun: api.techRegulation.getRun,
    startRun: api.techRegulation.startRun,
    exportDocx: api.techRegulation.exportRunDocx,
    ReportView,
    emptyStateCopy: {
      title: "No reports yet",
      body: "Run the agent to survey the technology and regulatory environment against your applicability envelope. An incomplete envelope still runs — the reports state the operating state and what each gap costs.",
      cta: "Run",
    },
    runningStateCopy: {
      title: "Researching the environment",
      body: "The agent is searching for regulatory changes, standards revisions, supplier notices and technology evidence, then extracting candidate work and writing all nine reports. You can leave this page and come back — the run keeps going.",
    },
  };

  return <ReportWorkspaceShell adapter={adapter} />;
}
