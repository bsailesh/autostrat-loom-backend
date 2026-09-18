// Strategy Synthesis's own exhibit registry instance -- physically separate
// from Market Insights' (which has none yet), so neither can affect the
// other. See reportWorkspace/exhibitRegistry.js for the contract.
import { createExhibitRegistry } from "../../reportWorkspace/exhibitRegistry.js";
import { detectCapacityUtilisation, CapacityUtilisationExhibit } from "./capacityUtilisation.jsx";
import { detectDependencyGraph, DependencyGraphExhibit } from "./dependencyGraph.jsx";
import { detectScenarioComparison, ScenarioComparisonExhibit } from "./scenarioComparison.jsx";

const registry = createExhibitRegistry();
registry.register(detectCapacityUtilisation, CapacityUtilisationExhibit);
registry.register(detectDependencyGraph, DependencyGraphExhibit);
registry.register(detectScenarioComparison, ScenarioComparisonExhibit);

export default registry;
