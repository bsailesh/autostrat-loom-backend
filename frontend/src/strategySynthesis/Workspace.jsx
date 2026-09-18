import { api } from "../api.js";
import ReportWorkspaceShell from "../reportWorkspace/ReportWorkspaceShell.jsx";
import { AGENT_NAME, REPORT_ORDER, reportLabel } from "./reportMeta.js";
import ReportView from "./ReportView.jsx";

// No Gate -- Part 6: "Run is always enabled," unlike Market Insights' scope
// requirement (marketInsights/Workspace.jsx).
export default function Workspace() {
  const adapter = {
    agentName: AGENT_NAME,
    reportOrder: REPORT_ORDER,
    reportLabel,
    routes: {
      configure: "/agents/strategy-synthesis/inputs",
      run: (runId) => `/agents/strategy-synthesis/runs/${runId}`,
      report: (runId, reportId) => `/agents/strategy-synthesis/runs/${runId}/reports/${reportId}`,
    },
    listReports: api.strategySynthesis.listRunReports,
    getReport: api.strategySynthesis.getReport,
    listRuns: api.strategySynthesis.listRuns,
    getRun: api.strategySynthesis.getRun,
    startRun: api.strategySynthesis.startRun,
    exportDocx: api.strategySynthesis.exportRunDocx,
    ReportView,
    emptyStateCopy: {
      title: "No reports yet",
      body: "Run the agent to generate a decision brief from your declared inputs. An incomplete brief still runs -- see the decision inputs screen for what's missing and what it costs.",
      cta: "Run",
    },
    runningStateCopy: {
      title: "Assembling the decision brief",
      body: "The agent is scoring the portfolio, computing capacity and scenarios, and writing all seven reports. You can leave this page and come back — the run keeps going.",
    },
  };

  return <ReportWorkspaceShell adapter={adapter} />;
}
