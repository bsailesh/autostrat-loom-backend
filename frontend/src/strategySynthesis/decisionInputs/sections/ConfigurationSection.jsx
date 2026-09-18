import { useEffect, useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { api } from "../../../api.js";
import { theme, FONT } from "../../../theme.js";
import { Button, Spinner } from "../../../components/atoms.jsx";

// PUT /config replaces the whole config object at once, and Rules (a
// sibling section, RulesSection.jsx) lives in that same payload -- so
// every save here re-fetches fresh first and only overwrites this
// section's own fields, carrying the current `rules` through unchanged
// rather than risking clobbering an edit made there in the same session.
export default function ConfigurationSection({ onChanged }) {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategySynthesis
      .getConfig()
      .then((c) =>
        setForm({
          effort_unit: c.effort_unit,
          fiscal_year_start_month: c.fiscal_year_start_month,
          fiscal_year_label_format: c.fiscal_year_label_format,
          project_types: c.project_types,
          effort_bands: c.effort_bands.map((b) => ({ band_name: b.band_name, min_units: b.min_units, max_units: b.max_units })),
        })
      )
      .catch((e) => setError(e.message));
  }, []);

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }
  function setProjectTypes(text) {
    set("project_types", text.split(",").map((t) => t.trim()).filter(Boolean));
  }
  function updateBand(i, field, value) {
    setForm((prev) => ({ ...prev, effort_bands: prev.effort_bands.map((b, idx) => (idx === i ? { ...b, [field]: value } : b)) }));
  }
  function addBand() {
    setForm((prev) => ({ ...prev, effort_bands: [...prev.effort_bands, { band_name: "", min_units: "", max_units: "" }] }));
  }
  function removeBand(i) {
    setForm((prev) => ({ ...prev, effort_bands: prev.effort_bands.filter((_, idx) => idx !== i) }));
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const fresh = await api.strategySynthesis.getConfig();
      const payload = {
        effort_unit: form.effort_unit,
        fiscal_year_start_month: parseInt(form.fiscal_year_start_month, 10) || 1,
        fiscal_year_label_format: form.fiscal_year_label_format,
        project_types: form.project_types,
        effort_bands: form.effort_bands.map((b) => ({
          band_name: b.band_name,
          min_units: b.min_units === "" ? null : parseFloat(b.min_units),
          max_units: b.max_units === "" ? null : parseFloat(b.max_units),
        })),
        rules: fresh.rules.map((r) => ({ rule_type: r.rule_type, value: r.value, note: r.note })),
      };
      await api.strategySynthesis.putConfig(payload);
      onChanged();
    } catch (e) {
      setError(e.message || "Couldn't save configuration.");
    } finally {
      setSaving(false);
    }
  }

  if (form === null) return <Spinner size={16} />;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
        <label style={{ fontSize: 11, color: theme.textMuted }}>
          Effort unit
          <input value={form.effort_unit} onChange={(e) => set("effort_unit", e.target.value)} style={{ ...inputStyle, display: "block", marginTop: 3, width: "100%" }} />
        </label>
        <label style={{ fontSize: 11, color: theme.textMuted }}>
          Fiscal year start month (1-12)
          <input
            type="number"
            min="1"
            max="12"
            value={form.fiscal_year_start_month}
            onChange={(e) => set("fiscal_year_start_month", e.target.value)}
            style={{ ...inputStyle, display: "block", marginTop: 3, width: "100%" }}
          />
        </label>
        <label style={{ fontSize: 11, color: theme.textMuted, gridColumn: "1 / -1" }}>
          Fiscal year label format
          <input value={form.fiscal_year_label_format} onChange={(e) => set("fiscal_year_label_format", e.target.value)} style={{ ...inputStyle, display: "block", marginTop: 3, width: "100%" }} />
        </label>
        <label style={{ fontSize: 11, color: theme.textMuted, gridColumn: "1 / -1" }}>
          Project types (comma-separated)
          <input
            value={form.project_types.join(", ")}
            onChange={(e) => setProjectTypes(e.target.value)}
            style={{ ...inputStyle, display: "block", marginTop: 3, width: "100%" }}
          />
        </label>
      </div>

      <p style={{ fontSize: 11, fontWeight: 700, color: theme.textSecondary, textTransform: "uppercase", letterSpacing: 0.4, margin: "12px 0 8px" }}>
        Effort bands
      </p>
      <div style={{ display: "grid", gap: 6 }}>
        {form.effort_bands.map((b, i) => (
          <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input value={b.band_name} onChange={(e) => updateBand(i, "band_name", e.target.value)} placeholder="Band name" style={{ ...inputStyle, flex: 1 }} />
            <input type="number" value={b.min_units} onChange={(e) => updateBand(i, "min_units", e.target.value)} placeholder="Min" style={{ ...inputStyle, width: 80 }} />
            <input type="number" value={b.max_units} onChange={(e) => updateBand(i, "max_units", e.target.value)} placeholder="Max" style={{ ...inputStyle, width: 80 }} />
            <button title="Remove" onClick={() => removeBand(i)} style={{ border: "none", background: "transparent", cursor: "pointer" }}>
              <Trash2 size={13} color={theme.danger} />
            </button>
          </div>
        ))}
      </div>
      <Button small variant="ghost" icon={Plus} onClick={addBand} style={{ marginTop: 8 }}>
        Add effort band
      </Button>

      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, margin: "12px 0 0", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}
      <Button variant="primary" small disabled={saving} onClick={save} style={{ marginTop: 14 }}>
        {saving ? "Saving…" : "Save configuration"}
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
