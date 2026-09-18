import { useEffect, useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { api } from "../../../api.js";
import { theme, FONT } from "../../../theme.js";
import { Button, Spinner } from "../../../components/atoms.jsx";

export default function FrameworkSection({ onChanged }) {
  const [framework, setFramework] = useState("weighted_scoring");
  const [criteria, setCriteria] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategySynthesis
      .getFramework()
      .then((r) => {
        setFramework(r.framework || "weighted_scoring");
        setCriteria(r.criteria || []);
      })
      .catch((e) => setError(e.message));
  }, []);

  function update(i, key, value) {
    setCriteria((prev) => prev.map((c, idx) => (idx === i ? { ...c, [key]: value } : c)));
  }
  function addRow() {
    setCriteria((prev) => [...prev, { criterion: "", weight: 0, source_agent: "" }]);
  }
  function removeRow(i) {
    setCriteria((prev) => prev.filter((_, idx) => idx !== i));
  }

  const total = (criteria || []).reduce((sum, c) => sum + (parseFloat(c.weight) || 0), 0);
  const sumOk = Math.abs(total - 1) < 0.01;

  async function save() {
    setSaving(true);
    setError("");
    try {
      const payload = { framework, criteria: criteria.map((c) => ({ ...c, weight: parseFloat(c.weight) || 0 })) };
      const saved = await api.strategySynthesis.putFramework(payload);
      setFramework(saved.framework);
      setCriteria(saved.criteria);
      onChanged();
    } catch (e) {
      setError(e.message || "Couldn't save the framework.");
    } finally {
      setSaving(false);
    }
  }

  if (criteria === null) return <Spinner size={16} />;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: theme.textSecondary, margin: "0 0 12px" }}>
        Weights are fractions of 1.0 (e.g. 0.25 for 25%) and must sum to 1.0. Defaults to value-vs-effort if left empty.
      </p>
      <label style={{ fontSize: 11, color: theme.textMuted, display: "block", marginBottom: 12 }}>
        Framework
        <input value={framework} onChange={(e) => setFramework(e.target.value)} style={{ ...inputStyle, display: "block", marginTop: 3, width: 220 }} />
      </label>

      <div style={{ display: "grid", gap: 8 }}>
        {criteria.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input value={c.criterion} onChange={(e) => update(i, "criterion", e.target.value)} placeholder="criterion" style={{ ...inputStyle, flex: 1 }} />
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={c.weight}
              onChange={(e) => update(i, "weight", e.target.value)}
              placeholder="weight"
              style={{ ...inputStyle, width: 80 }}
            />
            <input
              value={c.source_agent || ""}
              onChange={(e) => update(i, "source_agent", e.target.value)}
              placeholder="source agent (optional)"
              style={{ ...inputStyle, flex: 1 }}
            />
            <button title="Remove" onClick={() => removeRow(i)} style={{ border: "none", background: "transparent", cursor: "pointer", padding: 4 }}>
              <Trash2 size={13} color={theme.danger} />
            </button>
          </div>
        ))}
      </div>
      <Button small variant="ghost" icon={Plus} onClick={addRow} style={{ marginTop: 10 }}>
        Add criterion
      </Button>

      <p style={{ fontSize: 12, margin: "12px 0 0", color: criteria.length && !sumOk ? theme.danger : theme.textMuted }}>
        Sum of weights: {total.toFixed(2)} {criteria.length > 0 && !sumOk && "— must equal 1.00"}
      </p>

      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, margin: "10px 0 0", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}
      <Button variant="primary" small disabled={saving || (criteria.length > 0 && !sumOk)} onClick={save} style={{ marginTop: 14 }}>
        {saving ? "Saving…" : "Save framework"}
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
