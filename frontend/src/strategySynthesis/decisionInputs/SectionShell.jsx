// The one accordion pattern every decision-inputs section uses: a header
// with status + (when not fully set) the readiness consequence inline --
// never a bare red badge, per Part 6 -- expanding to the section's own
// editor.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";

const STATUS_TONE = { set: "success", partial: "warning", missing: "muted" };
const STATUS_LABEL = { set: "Set", partial: "Partial", missing: "Missing" };

export default function SectionShell({ title, status, consequence, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ border: `1px solid ${theme.border}`, borderRadius: 12, background: theme.surface, marginBottom: 12 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "14px 16px",
          border: "none",
          background: "transparent",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {open ? <ChevronDown size={15} color={theme.textMuted} /> : <ChevronRight size={15} color={theme.textMuted} />}
          <span style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>{title}</span>
        </span>
        <Badge tone={STATUS_TONE[status] || "muted"}>{STATUS_LABEL[status] || status}</Badge>
      </button>
      {status !== "set" && consequence && (
        <p style={{ margin: "0 16px 12px 41px", fontSize: 12, color: theme.textMuted, lineHeight: 1.5 }}>{consequence}</p>
      )}
      {open && <div style={{ padding: "4px 16px 18px", borderTop: `1px solid ${theme.border}` }}>{children}</div>}
    </div>
  );
}
