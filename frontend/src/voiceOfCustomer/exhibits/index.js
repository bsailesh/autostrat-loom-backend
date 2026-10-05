// Voice of Customer's own exhibit registry instance -- separate from every
// other agent's, so no agent's renderers can be reached, mis-triggered or
// broken by another's. See reportWorkspace/exhibitRegistry.js.
//
// Every renderer works from a structured Markdown table the agent emits
// (header contracts in voice_of_customer/reports.py) and returns null on
// anything it cannot fully parse, leaving a plain themed table. No ASCII.
//
// Order is specific-to-general: the insights matrix (Audience + Quadrant)
// is tried before SWOT (Quadrant without Audience), though SWOT's detector
// also refuses an Audience column.
import { createExhibitRegistry } from "../../reportWorkspace/exhibitRegistry.js";
import { detectBeliefTesting, BeliefTestingExhibit } from "./beliefTesting.jsx";
import { detectPainPointChart, PainPointChartExhibit } from "./painPointChart.jsx";
import { detectOpportunityMap, OpportunityMapExhibit } from "./opportunityMap.jsx";
import { detectHarveyBallGrid, HarveyBallGridExhibit } from "./harveyBallGrid.jsx";
import { detectInsightsMatrix, InsightsMatrixExhibit, detectSwot, SwotExhibit } from "./quadrants.jsx";

const registry = createExhibitRegistry();
registry.register(detectBeliefTesting, BeliefTestingExhibit);
registry.register(detectPainPointChart, PainPointChartExhibit);
registry.register(detectOpportunityMap, OpportunityMapExhibit);
registry.register(detectHarveyBallGrid, HarveyBallGridExhibit);
registry.register(detectInsightsMatrix, InsightsMatrixExhibit);
registry.register(detectSwot, SwotExhibit);

export default registry;
