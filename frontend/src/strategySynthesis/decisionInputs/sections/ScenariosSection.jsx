import { useEffect, useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { api } from "../../../api.js";
import { theme, FONT } from "../../../theme.js";
import { Button, Spinner } from "../../../components/atoms.jsx";

// Each scenario's weights are per-criterion OVERRIDES on the framework's
// declared weights (see app/models.py's ScenarioWeight docstring) -- an
// unmentioned criterion just keeps its framework weight. An empty list
// (e.g. a "Base" scenario) means "use the framework's weights unchanged."
export default function ScenariosSection({ onChanged }) {
  const [scenarios, setScenarios] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategySynthesis
      .getScenarios()
      .then((rows) => setScenarios(rows.map((s) => ({ name: s.name, emphasis: s.emphasis, weights: s.weights }))))
      .catch((e) => setError(e.message));
  }, []);

  function updateScenario(i, field, value) {
    setScenarios((prev) => prev.map((s, idx) => (idx === i ? { ...s, [field]: value } : s)));
  }
  function addScenario() {
    if (scenarios.length >= 6) return;
    setScenarios((prev) => [...prev, { name: "", emphasis: "", weights: [] }]);
  }
  function removeScenario(i) {
    if (scenarios.length <= 2) return;
    setScenarios((prev) => prev.filter((_, idx) => idx !== i));
  }

  function updateWeight(si, wi, field, value) {
    setScenarios((prev) =>
      prev.map((s, idx) => (idx !== si ? s : { ...s, weights: s.weights.map((w, j) => (j === wi ? { ...w, [field]: value } : w)) }))
    );
  }
  function addWeight(si) {
    setScenarios((prev) => prev.map((s, idx) => (idx !== si ? s : { ...s, weights: [...s.weights, { criterion: "", weight: 0 }] })));
  }
  function removeWeight(si, wi) {
    setScenarios((prev) => prev.map((s, idx) => (idx !== si ? s : { ...s, weights: s.weights.filter((_, j) => j !== wi) })));
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const payload = scenarios.map((s) => ({
        ...s,
        weights: s.weights.map((w) => ({ criterion: w.criterion, weight: parseFloat(w.weight) || 0 })),
      }));
      const saved = await api.strategySynthesis.putScenarios(payload);
      setScenarios(saved.map((s) => ({ name: s.name, emphasis: s.emphasis, weights: s.weights })));
      onChanged();
    } catch (e) {
      setError(e.message || "Couldn't save scenarios.");
    } finally {
      setSaving(false);
    }
  }

  if (scenarios === null) return <Spinner size={16} />;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: theme.textSecondary, margin: "0 0 12px" }}>
        2-6 named scenarios. Leave weights empty for "use the framework's weights unchanged" (a Base case); otherwise
        each listed criterion overrides that one weight, with everything else inherited from the framework.
      </p>

      <div style={{ display: "grid", gap: 14 }}>
        {scenarios.map((s, si) => (
          <div key={si} style={{ border: `1px solid ${theme.border}`, borderRadius: 8, padding: "10px 12px", position: "relative" }}>
            <button
              title="Remove scenario"
              onClick={() => removeScenario(si)}
              disabled={scenarios.length <= 2}
              style={{ position: "absolute", top: 8, right: 8, border: "none", background: "transparent", cursor: scenarios.length <= 2 ? "default" : "pointer", opacity: scenarios.length <= 2 ? 0.3 : 1 }}
            >
              <Trash2 size={13} color={theme.danger} />
            </button>
            <div style={{ display: "flex", gap: 8, marginBottom: 8, paddingRight: 20 }}>
              <input value={s.name} onChange={(e) => updateScenario(si, "name", e.target.value)} placeholder="Name (e.g. Growth)" style={{ ...inputStyle, flex: 1 }} />
              <input value={s.emphasis} onChange={(e) => updateScenario(si, "emphasis", e.target.value)} placeholder="Emphasis (optional)" style={{ ...inputStyle, flex: 2 }} />
            </div>
            <div style={{ display: "grid", gap: 6 }}>
              {s.weights.map((w, wi) => (
                <div key={wi} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input value={w.criterion} onChange={(e) => updateWeight(si, wi, "criterion", e.target.value)} placeholder="criterion" style={{ ...inputStyle, flex: 1 }} />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={w.weight}
                    onChange={(e) => updateWeight(si, wi, "weight", e.target.value)}
                    placeholder="weight"
                    style={{ ...inputStyle, width: 80 }}
                  />
                  <button title="Remove override" onClick={() => removeWeight(si, wi)} style={{ border: "none", background: "transparent", cursor: "pointer" }}>
                    <Trash2 size={12} color={theme.danger} />
                  </button>
                </div>
              ))}
            </div>
            <Button small variant="ghost" icon={Plus} onClick={() => addWeight(si)} style={{ marginTop: 8 }}>
              Add weight override
            </Button>
          </div>
        ))}
      </div>

      <Button small variant="ghost" icon={Plus} disabled={scenarios.length >= 6} onClick={addScenario} style={{ marginTop: 12 }}>
        Add scenario
      </Button>

      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, margin: "10px 0 0", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}
      <div style={{ marginTop: 14 }}>
        <Button variant="primary" small disabled={saving || scenarios.length < 2} onClick={save}>
          {saving ? "Saving…" : "Save scenarios"}
        </Button>
      </div>
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
