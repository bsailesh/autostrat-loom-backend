// Shared pieces for this agent's own exhibits. Local to voiceOfCustomer/ --
// not imported from another agent's exhibits, consistent with agent
// independence.
import { theme } from "../../theme.js";

export function col(headers, re) {
  return headers.findIndex((h) => re.test(String(h || "").trim()));
}

export function num(raw) {
  const m = String(raw ?? "").replace(/,/g, "").match(/-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : null;
}

export function confidenceToneName(raw) {
  const v = String(raw || "").toLowerCase();
  if (v.startsWith("high")) return "success";
  if (v.startsWith("med")) return "warning";
  if (v.startsWith("low")) return "danger";
  return "muted";
}

export function Figure({ title, note, children }) {
  return (
    <figure
      style={{
        margin: "18px 0",
        border: `1px solid ${theme.border}`,
        borderRadius: 8,
        background: theme.surface,
        overflow: "hidden",
      }}
    >
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>{title}</span>
        {note && <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>{note}</span>}
      </figcaption>
      <div style={{ padding: "12px 14px" }}>{children}</div>
    </figure>
  );
}
