import { theme } from "../theme.js";

// The white top strip used across the app (ported from the reference Home view).
export function PageHeader({ title, subtitle, right }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "16px 28px",
        borderBottom: `1px solid ${theme.border}`,
        background: theme.surface,
        flexShrink: 0,
      }}
    >
      <div style={{ minWidth: 0 }}>
        <p style={{ fontWeight: 700, fontSize: 17, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {title}
        </p>
        {subtitle && <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>{subtitle}</p>}
      </div>
      {right && <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>{right}</div>}
    </div>
  );
}
