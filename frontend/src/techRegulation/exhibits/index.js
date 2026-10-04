// Tech & Regulation's own exhibit registry instance -- physically separate
// from Market Insights' (which has none) and Strategy Synthesis' own, so
// neither agent's renderers can be reached, mis-triggered or broken by the
// other's. See reportWorkspace/exhibitRegistry.js for the contract.
//
// Registration order matters where two detectors could claim the same
// table. It cannot happen here -- each detector requires a distinct header
// set, and the ecosystem pair is distinguished by Node/Node type versus
// From/To -- but the order below is still the specific-to-general one.
import { createExhibitRegistry } from "../../reportWorkspace/exhibitRegistry.js";
import { detectCandidateWorkTable, CandidateWorkTableExhibit } from "./candidateWorkTable.jsx";
import { detectMaturityLadder, MaturityLadderExhibit } from "./maturityLadder.jsx";
import { detectEvolutionTimeline, EvolutionTimelineExhibit } from "./evolutionTimeline.jsx";
import {
  detectEcosystemNodes,
  EcosystemNodesExhibit,
  detectEcosystemEdges,
  EcosystemEdgesExhibit,
} from "./ecosystemMap.jsx";

const registry = createExhibitRegistry();
registry.register(detectCandidateWorkTable, CandidateWorkTableExhibit);
registry.register(detectMaturityLadder, MaturityLadderExhibit);
registry.register(detectEvolutionTimeline, EvolutionTimelineExhibit);
registry.register(detectEcosystemNodes, EcosystemNodesExhibit);
registry.register(detectEcosystemEdges, EcosystemEdgesExhibit);

export default registry;
