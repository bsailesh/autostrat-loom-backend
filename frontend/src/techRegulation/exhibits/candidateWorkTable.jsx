// Candidate work table -- the consolidated list in Report 1, and the one
// exhibit that carries actions.
//
// Parses the table contract in tech_regulation/reports.py:
//   | Key | Driver | Date | Date basis | Applicability | Work implied |
//   | Classification | Confidence | Status |
//
// Two things this renderer is careful about:
//
// 1. The STATUS COLUMN IN THE REPORT IS FROZEN at run time, so it is not
//    displayed. Status is read live from the API by CandidateWorkActions,
//    which is also what makes the actions meaningful -- a status rendered
//    from report prose would be stale the moment anyone triaged anything.
// 2. Undated items sort LAST under their own heading, never interleaved.
//    An undated candidate is standing context rather than a scheduled item,
//    and the ordering is the thing that says so.
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";
import CandidateWorkActions from "../candidateWork/CandidateWorkActions.jsx";

const DATE_BASIS_LABEL = {
  effective: "effective",
  compliance_deadline: "compliance deadline",
  runout: "runout",
  transition_end: "transition ends",
  window_closes: "window closes",
  none_established: "none established",
};

const CLASSIFICATION_TONE = {
  FACT: "success",
  OBSERVATION: "muted",
  INTERPRETATION: "warning",
  FORECAST: "accent",
  UNKNOWN: "danger",
};

function col(headers, re) {
  return headers.findIndex((h) => re.test(h));
}

// Sortable key from a mixed-precision external date: "2028-03-14",
// "14 Mar 2028" and "Q3 FY28" all have to order sensibly against each
// other, and the year is the part that always survives.
function sortKey(raw) {
  const text = String(raw || "").trim();
  if (!text || /none|n\/?a|tbd|—|--/i.test(text)) return null;
  const iso = text.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[1]}${iso[2]}${iso[3]}`;
  const year = text.match(/(19|20)\d{2}/);
  if (!year) return null;
  const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  const monthIdx = MONTHS.findIndex((m) => new RegExp(m, "i").test(text));
  const day = text.match(/\b(\d{1,2})\b(?!\d)/);
  const mm = monthIdx >= 0 ? String(monthIdx + 1).padStart(2, "0") : "00";
  const dd = day ? String(day[1]).padStart(2, "0") : "00";
  return `${year[0]}${mm}${dd}`;
}

export function detectCandidateWorkTable(table) {
  const { headers, rows } = table;
  const keyIdx = col(headers, /^key$/i);
  const driverIdx = col(headers, /^driver$/i);
  const dateIdx = col(headers, /^date$/i);
  const workIdx = col(headers, /^work implied$/i);
  if (keyIdx === -1 || driverIdx === -1 || dateIdx === -1 || workIdx === -1) return null;
  if (!rows.length) return null;

  const basisIdx = col(headers, /^date basis$/i);
  const applicabilityIdx = col(headers, /^applicability$/i);
  const classificationIdx = col(headers, /^classification$/i);
  const confidenceIdx = col(headers, /^confidence$/i);

  const items = [];
  for (const row of rows) {
    const key = row[keyIdx]?.text;
    const driver = row[driverIdx]?.text;
    if (!key || !driver) return null; // shape doesn't hold
    const dateText = row[dateIdx]?.text || "";
    items.push({
      key,
      driver,
      dateText,
      sortKey: sortKey(dateText),
      dateBasis: basisIdx >= 0 ? row[basisIdx]?.text || "" : "",
      applicability: applicabilityIdx >= 0 ? row[applicabilityIdx]?.text || "" : "",
      workImplied: row[workIdx]?.text || "",
      classification: classificationIdx >= 0 ? row[classificationIdx]?.text || "" : "",
      confidence: confidenceIdx >= 0 ? row[confidenceIdx]?.text || "" : "",
    });
  }
  return { items };
}

function Row({ item }) {
  const basis = DATE_BASIS_LABEL[item.dateBasis.trim()] || item.dateBasis;
  const classification = item.classification.replace(/[^A-Z]/gi, "").toUpperCase();

  return (
    <li
      style={{
        display: "grid",
        gridTemplateColumns: "72px 136px 1fr",
        gap: 12,
        padding: "10px 14px",
        borderTop: `1px solid ${theme.border}`,
        alignItems: "start",
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 700, color: theme.navy }}>{item.key}</span>

      <div>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>
          {item.dateText || "No date"}
        </p>
        {basis && <p style={{ margin: "1px 0 0", fontSize: 10, color: theme.textMuted }}>{basis}</p>}
      </div>

      <div style={{ minWidth: 0 }}>
        <p style={{ margin: 0, fontSize: 12, color: theme.textPrimary, lineHeight: 1.45 }}>{item.driver}</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "baseline", marginTop: 4 }}>
          {item.workImplied && <Badge tone="accent">{item.workImplied}</Badge>}
          {classification && (
            <Badge tone={CLASSIFICATION_TONE[classification] || "muted"}>{classification}</Badge>
          )}
          {item.confidence && <Badge tone="muted">{item.confidence}</Badge>}
        </div>
        {item.applicability && (
          <p style={{ margin: "4px 0 0", fontSize: 11, color: theme.textSecondary }}>{item.applicability}</p>
        )}
        <CandidateWorkActions candidateKey={item.key} />
      </div>
    </li>
  );
}

export function CandidateWorkTableExhibit({ data }) {
  const { items } = data;
  const dated = items.filter((i) => i.sortKey).sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  const undated = items.filter((i) => !i.sortKey);

  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", background: theme.surfaceMuted, borderBottom: `1px solid ${theme.border}` }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>Candidate work</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>
          {items.length} {items.length === 1 ? "item" : "items"}, soonest first — ordered by date, not by importance
        </span>
      </figcaption>

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {dated.map((item) => (
          <Row key={item.key} item={item} />
        ))}
      </ul>

      {undated.length > 0 && (
        <>
          <p
            style={{
              margin: 0,
              padding: "8px 14px 6px",
              borderTop: `1px solid ${theme.border}`,
              background: theme.surfaceMuted,
              fontSize: 11,
              fontWeight: 600,
              color: theme.textSecondary,
            }}
          >
            No date established — standing context rather than scheduled work
          </p>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {undated.map((item) => (
              <Row key={item.key} item={item} />
            ))}
          </ul>
        </>
      )}
    </figure>
  );
}
