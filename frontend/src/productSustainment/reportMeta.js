// The nine Product Sustainment reports, per product_sustainment/reports.py.
// Report 9 (sustainment trend digest) is deferred -- it needs run-to-run
// change detection -- so the order has a gap; Report 1 names the deferral.
export const REPORT_LABELS = {
  1: "Sustainment intelligence",
  2: "Obsolescence",
  3: "Field performance and failure trends",
  4: "Supplier and component risk",
  5: "Aging fleet",
  6: "Service intelligence",
  7: "Knowledge and capability loss",
  8: "Lifecycle dashboard",
  10: "Component runout and inventory bridge",
};

export const REPORT_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 10];
export const RUNOUT_REPORT_NUMBER = 10;

export function reportLabel(n) {
  return REPORT_LABELS[n] || `Report ${n}`;
}

export function opensWithGoverningInsight(reportNumber) {
  return Number(reportNumber) === 1;
}

export const AGENT_NAME = "Product Sustainment";

// product_sustainment/structure.py report_title()
export const EXPOSURE_SCAN_TITLE_PREFIX = "Obsolescence and exposure scan — ";

export const TIER_COPY = {
  exposure_scan: {
    label: "Obsolescence and exposure scan",
    tone: "danger",
    note:
      "No BOM matrices are loaded, so a run now cannot compute any runout date and is not a sustainment analysis. It reports lifecycle status and candidate alternates for the listed parts. Loading both matrices, demand and inventory converts it into a sustainment analysis.",
  },
  tier_1_partial: {
    label: "Tier 1 partial",
    tone: "warning",
    note: "Some analyses are enabled. Each missing input costs something specific — listed below.",
  },
  tier_1_substantial: {
    label: "Tier 1 substantial",
    tone: "success",
    note: "Runout is computable, and most of the reliability, fleet, configuration and knowledge analyses are enabled.",
  },
};

export const MATRICES = [
  {
    which: "lru-level1",
    title: "LRU → Level 1",
    blurb:
      "Rows are LRUs, columns are Level 1 assemblies, cells are quantity per unit. An empty cell means the assembly is not in that LRU. Many-to-many: an assembly can sit in several LRUs.",
  },
  {
    which: "level1-level2",
    title: "Level 1 → Level 2",
    blurb:
      "Rows are Level 2 components, columns are Level 1 assemblies, cells are quantity per unit. Many-to-many: a component can sit in several assemblies.",
  },
];

export const MASTERS = [
  {
    which: "lrus",
    title: "LRUs",
    fields: [
      { name: "lru_id", label: "LRU id", placeholder: "AR-FIN", width: 110 },
      { name: "lru_name", label: "Name", placeholder: "Missile fin actuator", width: 190 },
      { name: "product_line", label: "Product line", placeholder: "Missile", width: 130 },
      { name: "program", label: "Program", placeholder: "", width: 120 },
      { name: "status", label: "Status", placeholder: "active", width: 100 },
    ],
  },
  {
    which: "level1",
    title: "Level 1 assemblies",
    fields: [
      { name: "level1_id", label: "Level 1 id", placeholder: "CCA-PWR", width: 120 },
      { name: "level1_name", label: "Name", placeholder: "Power stage card", width: 200 },
      { name: "description", label: "Description", placeholder: "", grow: true },
    ],
  },
  {
    which: "level2",
    title: "Level 2 components",
    fields: [
      { name: "level2_id", label: "Level 2 id", placeholder: "GaN-650", width: 120 },
      { name: "level2_name", label: "Name", placeholder: "GaN power device", width: 170 },
      { name: "manufacturer", label: "Manufacturer", placeholder: "Infineon", width: 130 },
      { name: "manufacturer_part_number", label: "MPN", placeholder: "", width: 140 },
      { name: "description", label: "Description", placeholder: "", grow: true },
    ],
  },
];

// Data files, in the order the input spec presents them. `readiness` ties
// each to its /readiness item where one exists.
export const DATA_FILES = [
  { type: "demand", title: "Demand", readiness: "demand", asOf: false,
    blurb: "LRU level only: one row per LRU, one column per year. A blank cell is zero demand that year, not missing data." },
  { type: "direct-demand", title: "Direct demand (spares, aftermarket)", readiness: null, asOf: false,
    blurb: "Optional. Demand at LRU, Level 1 or Level 2 that is ADDED to derived demand and flows down through the matrices — a spare card consumes its components." },
  { type: "inventory", title: "Inventory", readiness: "inventory", asOf: true,
    blurb: "By part, level, location and form. Location and form are your own words, used verbatim. Card and LRU stock rolls down to component equivalents." },
  { type: "pipeline", title: "Pipeline quantities", readiness: "pipeline", asOf: true,
    blurb: "Open POs, supplier on-order and supplier WIP, all counted as available on arrival. Supplier quantity is reported but not counted." },
  { type: "risk", title: "Risk flags", readiness: "risk", asOf: false,
    blurb: "End of life, single source, custom or at-risk region, with lifecycle status (NFND, MXSTK…) and any last-time-buy date." },
  { type: "alternates", title: "Qualified alternates", readiness: "alternates", asOf: false,
    blurb: "Second sources already through YOUR qualification. Only these are ever called qualified; alternates the agent finds are candidates." },
  { type: "lead-times", title: "Lead times", readiness: "lead_times", asOf: false,
    blurb: "Days per part. Needed to flag where a runout falls inside the lead time and immediate PO arrival may not hold." },
  { type: "fleet", title: "Fleet roster", readiness: "fleet", asOf: false, blurb: "Unit, LRU, in-service date, utilisation, environment." },
  { type: "maintenance", title: "Maintenance records", readiness: null, asOf: false, blurb: "Events with time in service and downtime — enables MTBF and MTTR." },
  { type: "configuration", title: "Configuration baseline", readiness: "configuration", asOf: false,
    blurb: "As-maintained against as-designed, per unit." },
];

export const KNOWLEDGE_FIELDS = [
  { name: "capability", label: "Capability", placeholder: "Resolver alignment on legacy test sets", grow: true },
  { name: "components_affected", label: "Components affected", placeholder: "CCA-SENS", width: 170 },
  { name: "people_count", label: "People", placeholder: "2", width: 70, numeric: true },
  { name: "documentation_status", label: "Documentation", placeholder: "undocumented", width: 140 },
];

export const EVIDENCE_TYPES = [
  ["support_tickets", "Support tickets"],
  ["field_service_reports", "Field service reports"],
  ["warranty_claims", "Warranty claims"],
  ["failure_reports", "Failure reports"],
  ["field_investigation_reports", "Field investigation reports"],
  ["return_authorisations", "Return authorisations"],
];

export async function saveBlob({ blob, filename }) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
