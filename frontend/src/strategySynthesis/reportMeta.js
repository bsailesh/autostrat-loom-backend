// The seven Strategy Synthesis reports, per strategy_synthesis/reports.py.
// Report 7 opens with a Governing Insight (opening="scqa"); Report 1 opens
// with Key Insights (opening="key_insights") -- the REVERSE of Market
// Insights' convention, where report 1 is the SCQA one. Reports 2-6 have
// neither heading ("plain").
export const REPORT_LABELS = {
  1: "Strategic opportunity",
  2: "Project strategic context",
  3: "Prioritised portfolio",
  4: "Mandatory / strategic / discretionary",
  5: "Dependency and sequencing",
  6: "Scenario analysis",
  7: "Decision brief",
};

export const REPORT_ORDER = [1, 2, 3, 4, 5, 6, 7];

export function reportLabel(n) {
  return REPORT_LABELS[n] || `Report ${n}`;
}

export function opensWithGoverningInsight(reportNumber) {
  return Number(reportNumber) === 7;
}

export const AGENT_NAME = "Strategy Synthesis";
