import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "../../../api.js";
import { theme } from "../../../theme.js";
import { Button, Spinner } from "../../../components/atoms.jsx";
import SimpleListEditor from "../SimpleListEditor.jsx";

const FIELDS = [
  { key: "objective_key", label: "Key (e.g. SO-1)" },
  { key: "text", label: "Objective", textarea: true },
  { key: "horizon", label: "Horizon (e.g. FY28)" },
  { key: "owner", label: "Owner" },
  { key: "measure", label: "Measure" },
];

export default function ObjectivesSection({ onChanged }) {
  const [rows, setRows] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategySynthesis.getObjectives().then(setRows).catch((e) => setError(e.message));
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    try {
      const saved = await api.strategySynthesis.putObjectives(rows);
      setRows(saved);
      onChanged();
    } catch (e) {
      setError(e.message || "Couldn't save objectives.");
    } finally {
      setSaving(false);
    }
  }

  if (rows === null) return <Spinner size={16} />;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: theme.textSecondary, margin: "0 0 12px" }}>
        Strategic objectives the portfolio is judged against. Each committed project can serve one or more.
      </p>
      <SimpleListEditor fields={FIELDS} rows={rows} onChange={setRows} addLabel="Add objective" />
      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, margin: "10px 0 0", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}
      <Button variant="primary" small disabled={saving} onClick={save} style={{ marginTop: 14 }}>
        {saving ? "Saving…" : "Save objectives"}
      </Button>
    </div>
  );
}
