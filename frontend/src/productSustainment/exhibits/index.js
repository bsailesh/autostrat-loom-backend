// Product Sustainment's own exhibit registry instance, separate from every
// other agent's. See reportWorkspace/exhibitRegistry.js.
//
// The runout table, depletion series and exposure map are generated in code
// from compute.py's results; the failure trend series is model-emitted from
// counted evidence. Anything that does not parse is left as a plain themed
// table -- never ASCII.
import { createExhibitRegistry } from "../../reportWorkspace/exhibitRegistry.js";
import { detectRunoutTable, RunoutTableExhibit } from "./runoutTable.jsx";
import { detectDepletionChart, DepletionChartExhibit, detectFailureTrend, FailureTrendExhibit } from "./charts.jsx";
import { detectExposureMap, ExposureMapExhibit } from "./exposureMap.jsx";

const registry = createExhibitRegistry();
registry.register(detectRunoutTable, RunoutTableExhibit);
registry.register(detectDepletionChart, DepletionChartExhibit);
registry.register(detectExposureMap, ExposureMapExhibit);
registry.register(detectFailureTrend, FailureTrendExhibit);

export default registry;
