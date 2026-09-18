import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "../../../api.js";
import { theme } from "../../../theme.js";
import { Button, Spinner } from "../../../components/atoms.jsx";
import SimpleListEditor from "../SimpleListEditor.jsx";

const FIELDS = [
  { key: "project_key", label: "Key (e.g. U-01)" },
  { key: "name", label: "Name" },
  { key: "proposed_by", label: "Proposed by" },
  { key: "description", label: "Description", textarea: true },
  { key: "rationale", label: "Rationale", textarea: true },
];

// How a design partner's own project ideas enter the candidate set --
// distinct from DiscoveredCandidate's agent-discovered ones. Never scored
// or ranked directly; a proposal still needs scoping (effort by bucket)
// like any candidate before it enters the roadmap.
export default function ProposalsSection({ onChanged }) {
  const [rows, setRows] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategySynthesis.getProposals().then(setRows).catch((e) => setError(e.message));
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    try {
      const saved = await api.strategySynthesis.putProposals(rows);
      setRows(saved);
      onChanged();
    } catch (e) {
      setError(e.message || "Couldn't save proposals.");
    } finally {
      setSaving(false);
    }
  }

  if (rows === null) return <Spinner size={16} />;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: theme.textSecondary, margin: "0 0 12px" }}>
        Your own project ideas, with no effort estimate yet -- never scored or ranked directly.
      </p>
      <SimpleListEditor fields={FIELDS} rows={rows} onChange={setRows} addLabel="Add proposal" />
      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, margin: "10px 0 0", display: "flex", gap: 6, alignItems: "center" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}
      <Button variant="primary" small disabled={saving} onClick={save} style={{ marginTop: 14 }}>
        {saving ? "Saving…" : "Save proposals"}
      </Button>
    </div>
  );
}
