// The nine Voice of Customer reports, per voice_of_customer/reports.py.
//
// Report 6 (the compiled Voice of Customer narrative) is deferred, so the
// order has a gap in it. Deliberate: renumbering would make this pack's
// numbers disagree with the spec, and Report 1 names the deferral itself.
export const REPORT_LABELS = {
  1: "Executive summary",
  2: "Ranked pain points",
  3: "Feature requests",
  4: "Customer personas",
  5: "Opportunity map",
  7: "SWOT",
  8: "Competitive feature matrix",
  9: "STEEP analysis",
  10: "Customer insights matrix",
};

export const REPORT_ORDER = [1, 2, 3, 4, 5, 7, 8, 9, 10];

export function reportLabel(n) {
  return REPORT_LABELS[n] || `Report ${n}`;
}

export function opensWithGoverningInsight(reportNumber) {
  return Number(reportNumber) === 1;
}

export const AGENT_NAME = "Voice of Customer";

// A Tier 2 run titles every report with this prefix (voice_of_customer/
// context.py). Lifted into a banner by ReportView.
export const TIER_2_TITLE_PREFIX = "External customer-context analysis — ";

export const TIER_COPY = {
  tier_2: {
    label: "Tier 2 — External customer-context analysis",
    tone: "danger",
    note:
      "No customer evidence has been supplied, so a run now is built from public sources alone. It will be titled an external customer-context analysis, not Voice of Customer. Sentiment scores, pain points ranked by frequency, validated personas, feature request frequency, win/loss rationale, segment clustering and any test of your stated beliefs are unavailable — the reports say so rather than producing thin versions. Persona hypotheses to validate are produced instead.",
  },
  tier_1_partial: {
    label: "Tier 1 partial",
    tone: "warning",
    note:
      "Customer evidence has been supplied. Each analysis is enabled only by its specific source — the list below shows which are available and what each missing one needs.",
  },
  tier_1_substantial: {
    label: "Tier 1 substantial",
    tone: "success",
    note:
      "Customer evidence supports the full analysis. Public evidence is used for external forces and competitive context only.",
  },
};

// Context sections, in the input spec's order. `section` is the API path
// segment; `fields` drives the repeatable-row editor. `stateKey` ties the
// section to its /context/state item, where one exists.
export const CONTEXT_SECTIONS = [
  {
    key: "segments",
    section: "segments",
    stateKey: "segments",
    title: "Customer segments",
    blurb:
      "Who findings are attributed to. Without segments, findings cannot be grouped, and frequency means nothing — ten complaints from one operator and ten from ten primes are different findings. Leave the count blank where it is unknown; an honest unknown is better than a guess.",
    fields: [
      { name: "segment_key", label: "Key", placeholder: "OEM-TIER1", width: 110 },
      { name: "segment_name", label: "Name", placeholder: "Tier 1 integrators", width: 180 },
      { name: "description", label: "Description", placeholder: "System integrators specifying actuation", grow: true },
      { name: "approximate_count", label: "Approx. count", placeholder: "unknown", width: 100, numeric: true },
    ],
  },
  {
    key: "known_pain_points",
    section: "known-pain-points",
    stateKey: "known_pain_points",
    emphasis: true,
    title: "Known pain points — what you believe your customers complain about",
    blurb:
      "The most valuable thing this agent does is test your own beliefs against the evidence: corroborated, contradicted, or not found. It can only do that for beliefs written down before the run. A contradicted belief — \"we thought it was lead times; the evidence says integration effort\" — is the single most useful finding the agent can give you, and it is easy to skip this section without realising what is lost.",
    fields: [
      { name: "pain_point", label: "Belief", placeholder: "Primes say our lead times are the longest in the qualified set", grow: true },
      { name: "segment_key", label: "Segment", placeholder: "OEM-PRIME", width: 110 },
      { name: "category_key", label: "Product", placeholder: "EMA-FIN", width: 100 },
      { name: "their_assessment", label: "Your assessment", placeholder: "procurement", width: 160 },
    ],
  },
  {
    key: "channels",
    section: "channels",
    stateKey: "channels",
    title: "Channels",
    blurb:
      "How you reach customers and how feedback arrives. A declared channel with no evidence from it is itself a finding — absent feedback is not the same as no complaints.",
    fields: [
      { name: "channel", label: "Channel", placeholder: "Field service", width: 200 },
      { name: "direction", label: "Direction", width: 110, options: ["inbound", "outbound", "both"] },
      { name: "note", label: "Note", placeholder: "Primary source of failure reports", grow: true },
    ],
  },
  {
    key: "customers",
    section: "customers",
    stateKey: null,
    title: "Named customers (optional, confidential)",
    blurb:
      "Used for attribution inside the analysis — so the agent can see that three documents concern the same customer, which is how a single-source finding is recognised. How names may appear in output is set by the attribution policy below. Every report is checked against these names after it is written.",
    fields: [
      { name: "customer_name", label: "Customer", placeholder: "Customer name", width: 200 },
      { name: "segment_key", label: "Segment", placeholder: "OEM-PRIME", width: 110 },
      { name: "products", label: "Products", placeholder: "EMA-FIN, EMA-TVC", grow: true },
      { name: "relationship_status", label: "Relationship", placeholder: "active", width: 120 },
    ],
  },
];

export const ATTRIBUTION_POLICIES = [
  {
    value: "segment_only",
    label: "Segment only (default)",
    example: "\"Three Tier 1 integrators report…\" Never a customer name.",
  },
  {
    value: "role_and_segment",
    label: "Role and segment",
    example: "\"A programme manager at a Tier 1 integrator reports…\"",
  },
  {
    value: "named",
    label: "Named",
    example: "Customers named directly. Only where your customers have confirmed this is permitted.",
  },
];

// voice_of_customer/context.py FILE_TYPES, in order.
export const FILE_TYPES = [
  ["support_tickets", "Support tickets"],
  ["warranty_claims", "Warranty claims"],
  ["service_reports", "Service and field reports"],
  ["survey_responses", "Survey responses and verbatims"],
  ["nps_detail", "NPS detail"],
  ["win_loss_reports", "Win/loss reports"],
  ["visit_interview_notes", "Customer visit and interview notes"],
  ["call_centre_logs", "Call centre logs"],
  ["meeting_minutes", "Meeting minutes and programme reviews"],
  ["dealer_feedback", "Dealer and distributor feedback"],
  ["product_reviews_public", "Product reviews, public"],
  ["field_investigation_reports", "Field investigation reports"],
  ["feature_request_logs", "Feature request logs and CRM opportunity notes"],
];

export const FILE_TYPE_LABEL = Object.fromEntries(FILE_TYPES);

export const COLUMN_ROLES = [
  ["date", "Date"],
  ["segment", "Segment"],
  ["product", "Product"],
  ["customer", "Customer"],
  ["description", "Description"],
  ["category", "Category"],
  ["severity", "Severity"],
  ["status", "Status"],
];

// Display only. A roadmap statement, not controls -- see EvidenceScreen.
export const PLANNED_INTEGRATIONS = [
  ["Salesforce", "Opportunities, win/loss, contacts and activity notes."],
  ["Dynamics 365", "Opportunities, win/loss, contacts and activity notes."],
  ["Zendesk / ServiceNow", "Support tickets and resolution times."],
  ["SharePoint", "Visit reports, programme reviews and meeting minutes."],
  ["Qualtrics / Medallia", "Survey responses and NPS."],
  ["Fleet telemetry", "Operational data and usage patterns."],
];
