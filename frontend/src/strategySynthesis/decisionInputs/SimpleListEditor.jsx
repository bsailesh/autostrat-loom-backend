// Generic editor for "a list of small records, replaced wholesale on save"
// -- the shape Objectives and Proposals both are. Not shared outside Agent 5.
import { Plus, Trash2 } from "lucide-react";
import { theme, FONT } from "../../theme.js";
import { Button } from "../../components/atoms.jsx";

export default function SimpleListEditor({ fields, rows, onChange, addLabel }) {
  function update(i, key, value) {
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)));
  }
  function addRow() {
    onChange([...rows, Object.fromEntries(fields.map((f) => [f.key, ""]))]);
  }
  function removeRow(i) {
    onChange(rows.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      <div style={{ display: "grid", gap: 10 }}>
        {rows.map((row, i) => (
          <div key={i} style={{ border: `1px solid ${theme.border}`, borderRadius: 8, padding: "10px 12px", position: "relative" }}>
            <button
              title="Remove"
              onClick={() => removeRow(i)}
              style={{ position: "absolute", top: 8, right: 8, border: "none", background: "transparent", cursor: "pointer", padding: 2 }}
            >
              <Trash2 size={13} color={theme.danger} />
            </button>
            <div style={{ display: "grid", gap: 8, paddingRight: 20 }}>
              {fields.map((f) => (
                <label key={f.key} style={{ fontSize: 11, color: theme.textMuted, display: "block" }}>
                  {f.label}
                  {f.textarea ? (
                    <textarea
                      rows={2}
                      value={row[f.key] || ""}
                      onChange={(e) => update(i, f.key, e.target.value)}
                      style={{ ...inputStyle, width: "100%", resize: "vertical", display: "block", marginTop: 3 }}
                    />
                  ) : (
                    <input
                      value={row[f.key] || ""}
                      onChange={(e) => update(i, f.key, e.target.value)}
                      style={{ ...inputStyle, width: "100%", display: "block", marginTop: 3 }}
                    />
                  )}
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <Button small variant="ghost" icon={Plus} onClick={addRow} style={{ marginTop: 10 }}>
        {addLabel}
      </Button>
    </div>
  );
}

const inputStyle = {
  fontFamily: FONT,
  fontSize: 12.5,
  padding: "6px 9px",
  borderRadius: 6,
  border: `1px solid ${theme.border}`,
  background: "#fff",
  color: theme.textPrimary,
  outline: "none",
};

export { inputStyle };
