// The nine Tech & Regulation reports, per tech_regulation/reports.py.
//
// Report 1 opens with a Governing Insight (opening="scqa"); the rest open
// with Key Insights. Note the numbering: Reports 9 and 10 are deferred in
// v1 and 11 keeps its own number, so the order has a gap in it. That is
// deliberate -- renumbering 11 to 9 would make this pack's numbers disagree
// with the spec that describes them, and Report 1 names both deferrals in
// its own text rather than leaving a reader to wonder.
export const REPORT_LABELS = {
  1: "Executive summary",
  2: "Technology landscape",
  3: "Maturity ladder",
  4: "Evolution timeline",
  5: "Ecosystem map",
  6: "Regulatory landscape",
  7: "Regulatory change",
  8: "Standards and certification",
  11: "Competitor technology",
};

export const REPORT_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 11];

export function reportLabel(n) {
  return REPORT_LABELS[n] || `Report ${n}`;
}

export function opensWithGoverningInsight(reportNumber) {
  return Number(reportNumber) === 1;
}

export const AGENT_NAME = "Technology & Regulation";

// The eight scoping dimensions, in the order the scoping spec presents them
// and the order the screen shows them. `dimension` is the API path segment;
// `fields` drives the repeatable-row editor.
//
// Certification basis and platforms are naturally tabular and get real
// columns rather than free text, per the briefing.
export const SCOPE_SECTIONS = [
  {
    key: "product_categories",
    dimension: "categories",
    title: "Product categories",
    blurb:
      "What you make, in your own words. Without this the run is an industry survey rather than an assessment of your obligations — every other dimension has nothing to attach findings to.",
    fields: [
      { name: "category_key", label: "Key", placeholder: "EMA-UTIL", width: 110 },
      { name: "category_name", label: "Name", placeholder: "Utility actuation", width: 200 },
      { name: "description", label: "Description", placeholder: "Door, hatch and secondary system actuators", grow: true },
    ],
  },
  {
    key: "certification_basis",
    dimension: "certification-basis",
    title: "Certification basis",
    blurb:
      "What each category is approved under. The highest-leverage field here: it decides whether a regulatory change is reported as applicable to you or merely reported. If you supply nothing else, supply this.",
    fields: [
      { name: "category_key", label: "Category", placeholder: "EMA-UTIL", width: 110 },
      {
        name: "basis_type",
        label: "Type",
        width: 110,
        options: ["TSO", "ETSO", "CS", "Part", "MIL-STD", "STC", "PMA", "Standard", "Other"],
      },
      { name: "basis_identifier", label: "Identifier", placeholder: "TSO-C196b", width: 170 },
      { name: "status", label: "Status", placeholder: "approved", width: 120 },
      { name: "held_since", label: "Since", placeholder: "2019", width: 80 },
    ],
  },
  {
    key: "jurisdictions",
    dimension: "jurisdictions",
    title: "Jurisdictions",
    blurb:
      "Where the product is sold, certified or operated. Role matters: a finding from a primary market and one from an export-only market carry different weight, and the agent says which.",
    fields: [
      { name: "jurisdiction", label: "Jurisdiction", placeholder: "European Union", grow: true },
      { name: "role", label: "Role", width: 150, options: ["primary", "secondary", "export_only"] },
    ],
  },
  {
    key: "platforms",
    dimension: "platforms",
    title: "Platforms and applications",
    blurb:
      "What the product goes on. Relationship changes how a finding reads — a regulatory change on a platform you ship is a cost against existing revenue; the same change on one you are pursuing is an entry condition on a design-in window.",
    fields: [
      { name: "platform", label: "Platform", placeholder: "Narrowbody commercial", width: 200 },
      { name: "platform_class", label: "Class", placeholder: "Part 25 transport", width: 170 },
      {
        name: "relationship",
        label: "Relationship",
        width: 140,
        options: ["shipping", "pursuing", "in_service", "sunsetting"],
      },
      { name: "programme_status", label: "Programme status", placeholder: "design-in window", grow: true },
    ],
  },
  {
    key: "standards_held",
    dimension: "standards",
    title: "Standards held",
    blurb:
      "What you are compliant with or certified against. A revision to a standard you hold is dated work with a consequence; a revision to one you do not hold is background, and the agent reports it as such.",
    fields: [
      { name: "standard_id", label: "Standard", placeholder: "DO-160", width: 130 },
      { name: "revision", label: "Revision", placeholder: "G", width: 90 },
      { name: "scope", label: "Scope", placeholder: "Environmental qualification", grow: true },
      {
        name: "status",
        label: "Status",
        width: 140,
        options: ["", "compliant", "certified", "in_progress", "lapsed"],
      },
    ],
  },
  {
    key: "suppliers",
    dimension: "suppliers",
    title: "Supplier watch list",
    blurb:
      "Whose product change notices and end-of-life announcements to surface. Without it, supplier developments are only reported once they reach trade press — far too late for a discontinuation.",
    fields: [
      { name: "supplier", label: "Supplier", placeholder: "Vendor A", width: 180 },
      { name: "what_they_supply", label: "Supplies", placeholder: "GaN power devices", grow: true },
      {
        name: "criticality",
        label: "Criticality",
        width: 150,
        options: ["", "single_source", "dual_sourced", "multi_source"],
      },
    ],
  },
  {
    key: "domains",
    dimension: "domains",
    title: "Technology domains",
    blurb:
      "Domains to monitor deliberately. Without them, domains are inferred from your product categories, which works but misses adjacencies you are watching on purpose.",
    fields: [{ name: "domain", label: "Domain", placeholder: "Advanced air mobility", grow: true }],
  },
  {
    key: "exclusions",
    dimension: "exclusions",
    title: "Exclusions",
    blurb:
      "What not to report. A scope that can only add produces noise. Exclusions are stated in the output — “excluded at your direction” — never applied silently, because an exclusion that turns out to be wrong is itself a finding.",
    fields: [
      {
        name: "exclusion_type",
        label: "Type",
        width: 150,
        options: ["platform_class", "jurisdiction", "domain", "category"],
      },
      { name: "value", label: "Value", placeholder: "Part 23 general aviation", width: 200 },
      { name: "reason", label: "Reason", placeholder: "not a market we serve", grow: true },
    ],
  },
];

export const OPERATING_STATE_COPY = {
  scoped: {
    label: "Scoped",
    tone: "success",
    note: "Findings are assessed against your own approvals, standards and platforms.",
  },
  partially_scoped: {
    label: "Partially scoped",
    tone: "warning",
    note: "Findings are assessed against what you have supplied. Each missing dimension costs something specific — listed below.",
  },
  unscoped: {
    label: "Unscoped",
    tone: "danger",
    note: "A run now would be an industry survey, not an assessment of your obligations. Reports would be titled as such, and no finding in them would be checked against any product category, certification basis or platform.",
  },
};
