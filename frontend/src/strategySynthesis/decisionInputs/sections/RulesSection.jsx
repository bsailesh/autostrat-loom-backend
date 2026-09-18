import { useEffect, useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { api } from "../../../api.js";
import { theme, FONT } from "../../../theme.js";
import { Button, Spinner } from "../../../components/atoms.jsx";

// Rules live inside the same PUT /config payload as ConfigurationSection's
// fields (see that file's own note) -- saving here re-fetches fresh config
// and only overwrites `rules`, carrying everything else through unchanged.
export default function RulesSection({ onChanged }) {
  const [rules, setRules] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategySynthesis
      .getConfig()
      .then((c) => setRules(c.rules.map((r) => ({ rule_type: r.rule_type, value: r.value, note: r.note }))))
      .catch((e) => setError(e.message));
  }, []);

  function update(i, field, value) {
    setRules((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)));
  }
  function addRow() {
    setRules((prev) => [...prev, { rule_type: "", value: "", note: "" }]);
  }
  function removeRow(i) {
    setRules((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const fresh = await api.strategySynthesis.getConfig();
      await api.strategySynthesis.putConfig({
        effort_unit: fresh.effort_unit,
        fiscal_year_start_month: fresh.fiscal_year_start_month,
        fiscal_year_label_format: fresh.fiscal_year_label_format,
        project_types: fresh.project_types,
        effort_bands: fresh.effort_bands.map((b) => ({ band_name: b.band_name, min_units: b.min_units, max_units: b.max_units })),
        rules,
      });
      onChanged();
    } catch (e) {
      setError(e.message || "Couldn't save rules.");
    } finally {
      setSaving(false);
    }
  }

  if (rules === null) return <Spinner size={16} />;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: theme.textSecondary, margin: "0 0 12px" }}>
        Business rules and thresholds, e.g. a minimum effort to rank, or that mandatory projects are never cut
        without escalation.
      </p>
      <div style={{ display: "grid", gap: 8 }}>
        {rules.map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input value={r.rule_type} onChange={(e) => update(i, "rule_type", e.target.value)} placeholder="rule_type" style={{ ...inputStyle, flex: 1 }} />
            <input value={r.value} onChange={(e) => update(i, "value", e.target.value)} placeholder="value" style={{ ...inputStyle, flex: 1 }} />
            <input value={r.note} onChange={(e) => update(i, "note", e.target.value)} placeholder="note" style={{ ...inputStyle, flex: 2 }} />
            <button title="Remove" onClick={() => removeRow(i)} style={{ border: "none", background: "transparent", cursor: "pointer", padding: 4 }}>
              <Trash2 size={13} color={theme.danger} />
            </button>
          </div>
        ))}
      </div>
      <Button small variant="ghost" icon={Plus} onClick={addRow} style={{ marginTop: 10 }}>
        Add rule
      </Button>

      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, margin: "10px 0 0", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}
      <Button variant="primary" small disabled={saving} onClick={save} style={{ marginTop: 14 }}>
        {saving ? "Saving…" : "Save rules"}
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
