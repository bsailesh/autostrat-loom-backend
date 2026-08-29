// The nine Market Insights reports, keyed by the report_number the backend
// returns. `label` is the short sidebar name (from the briefing); the main panel
// still shows the agent's own `title`.
export const REPORT_LABELS = {
  1: "Executive Summary",
  2: "Market Landscape",
  3: "Competitor Intelligence",
  4: "Feature Comparison",
  5: "Customer Demand",
  6: "Market Trends",
  7: "Market SWOT",
  8: "Intelligence Digest",
  9: "Industry Trends",
};

export const REPORT_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9];

export function reportLabel(n) {
  return REPORT_LABELS[n] || `Report ${n}`;
}

// Report 1 opens with a Governing Insight (SCQA); every other report opens with
// a Key Insights box. (Agent + briefing design.)
export function opensWithGoverningInsight(reportNumber) {
  return Number(reportNumber) === 1;
}

export const AGENT_NAME = "Market Insights";
