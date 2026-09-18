import { theme } from "../theme.js";
import { ConfidenceTag } from "../components/ConfidenceTag.jsx";
import { ReportMarkdown } from "./markdown.jsx";

// Report 1 only. Accent left border; Situation / Complication / Question /
// Answer as separate labelled lines (per the agent's SCQA output format).
export function GoverningInsightBox({ data }) {
  return (
    <div
      style={{
        borderLeft: `3px solid ${theme.orange}`,
        background: theme.orangeSoft,
        borderRadius: "0 10px 10px 0",
        padding: "16px 18px",
        margin: "4px 0 22px",
      }}
    >
      <p
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.6,
          textTransform: "uppercase",
          color: theme.orange,
          margin: "0 0 10px",
        }}
      >
        Governing Insight
      </p>
      {data.parts ? (
        <div style={{ display: "grid", gap: 8 }}>
          {[
            ["Situation", data.parts.situation],
            ["Complication", data.parts.complication],
            ["Question", data.parts.question],
            ["Answer", data.parts.answer],
          ].map(([label, value]) =>
            value ? (
              <div key={label} style={{ display: "grid", gridTemplateColumns: "104px 1fr", gap: 10 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: theme.textSecondary, paddingTop: 1 }}>{label}</span>
                <span style={{ fontSize: 13.5, lineHeight: 1.6, color: theme.textPrimary, fontWeight: label === "Answer" ? 600 : 400 }}>
                  {value}
                </span>
              </div>
            ) : null
          )}
        </div>
      ) : (
        <div style={{ fontSize: 13.5 }}>
          <ReportMarkdown>{data.raw}</ReportMarkdown>
        </div>
      )}
    </div>
  );
}

// Reports 2–9. 4–5 bullets, each ending with its confidence tag.
export function KeyInsightsBox({ data }) {
  return (
    <div
      style={{
        border: `1px solid ${theme.border}`,
        background: theme.surfaceMuted,
        borderRadius: 12,
        padding: "16px 18px",
        margin: "4px 0 22px",
      }}
    >
      <p
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.6,
          textTransform: "uppercase",
          color: theme.textSecondary,
          margin: "0 0 10px",
        }}
      >
        Key Insights
      </p>
      {data.bullets ? (
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 8 }}>
          {data.bullets.map((b, i) => (
            <li key={i} style={{ fontSize: 13.5, lineHeight: 1.6, color: theme.textPrimary }}>
              {b.text}{" "}
              {b.level && (
                <span style={{ whiteSpace: "nowrap" }}>
                  <ConfidenceTag level={b.level} size="xs" />
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <div style={{ fontSize: 13.5 }}>
          <ReportMarkdown>{data.raw}</ReportMarkdown>
        </div>
      )}
    </div>
  );
}
