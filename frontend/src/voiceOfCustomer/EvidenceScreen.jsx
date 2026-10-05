// Evidence: the customer voice itself. Upload by type; per file, its type,
// as-of date, period, sample flag and description, row or page count,
// ingest status, and -- for a CSV -- the detected columns with an optional
// role mapping. The mapping helps the agent (it turns a theme into a count)
// but its absence never blocks ingest.
//
// "Planned integrations" at the bottom is a roadmap statement and nothing
// else. It is deliberately NOT rendered as buttons, toggles or greyed-out
// controls: a connector that looks present and does nothing would
// contradict the thing this platform is built on -- that it states what it
// does not know.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Save, Trash2, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { FONT, theme } from "../theme.js";
import { COLUMN_ROLES, FILE_TYPE_LABEL, FILE_TYPES, PLANNED_INTEGRATIONS } from "./reportMeta.js";
import { TierBanner } from "./ContextScreen.jsx";

const input = {
  fontFamily: FONT,
  fontSize: 12,
  padding: "5px 7px",
  border: `1px solid ${theme.border}`,
  borderRadius: 4,
  background: theme.surface,
  color: theme.textPrimary,
};

function Labelled({ label, children, grow }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, flex: grow ? 1 : undefined, minWidth: 0 }}>
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: theme.textMuted }}>
        {label}
      </span>
      {children}
    </label>
  );
}

const EMPTY_FORM = {
  file_type: FILE_TYPES[0][0],
  as_of: "",
  period_start: "",
  period_end: "",
  is_sample: false,
  sample_description: "",
  segment_coverage: "",
  row_unit: "",
};

function UploadForm({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const isCsv = file && /\.csv$/i.test(file.name);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await api.voiceOfCustomer.uploadEvidence(file, { ...form, is_sample: form.is_sample ? "true" : "false" });
      setFile(null);
      setForm(EMPTY_FORM);
      onUploaded();
    } catch (e) {
      setError(e.message || "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, padding: "14px 16px", marginBottom: 18 }}>
      <h2 style={{ margin: "0 0 4px", fontSize: 14, fontWeight: 700 }}>Upload evidence</h2>
      <p style={{ margin: "0 0 12px", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>
        Text (.txt, .md), PDF or CSV, up to 25 MB per file. Office formats are not accepted yet — save as PDF, or a
        spreadsheet as CSV. Scanned PDFs are rejected: there is no OCR. The type you choose decides which analyses the
        file enables.
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Labelled label="Type">
          <select value={form.file_type} onChange={set("file_type")} style={input}>
            {FILE_TYPES.map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </Labelled>
        <Labelled label="File">
          <input type="file" accept=".txt,.md,.pdf,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ fontSize: 12 }} />
        </Labelled>
        <Labelled label="As of">
          <input type="date" value={form.as_of} onChange={set("as_of")} style={input} />
        </Labelled>
        <Labelled label="Period from">
          <input type="date" value={form.period_start} onChange={set("period_start")} style={input} />
        </Labelled>
        <Labelled label="Period to">
          <input type="date" value={form.period_end} onChange={set("period_end")} style={input} />
        </Labelled>
        <Labelled label="Segments covered">
          <input value={form.segment_coverage} onChange={set("segment_coverage")} placeholder="OEM-PRIME, MRO" style={{ ...input, width: 150 }} />
        </Labelled>
        {isCsv && (
          <Labelled label="One row is one…">
            <input value={form.row_unit} onChange={set("row_unit")} placeholder="ticket" style={{ ...input, width: 110 }} />
          </Labelled>
        )}
      </div>
      <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={form.is_sample} onChange={set("is_sample")} />
          This file is a sample, not the complete set
        </label>
        {form.is_sample && (
          <input
            value={form.sample_description}
            onChange={set("sample_description")}
            placeholder="How it was sampled, e.g. Q3 tickets from EMEA only"
            style={{ ...input, flex: 1, minWidth: 240 }}
          />
        )}
      </div>
      {form.is_sample && (
        <p style={{ margin: "6px 0 0", fontSize: 11.5, color: theme.textMuted }}>
          A sample is never reported as a census: every count from it is stated as “in the sample supplied”.
        </p>
      )}
      <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center" }}>
        <Button variant="primary" small icon={Upload} disabled={!file || busy} onClick={submit}>
          {busy ? "Uploading…" : "Upload"}
        </Button>
        {error && (
          <span style={{ fontSize: 12, color: theme.danger, display: "flex", gap: 5, alignItems: "center" }}>
            <AlertTriangle size={13} /> {error}
          </span>
        )}
      </div>
    </section>
  );
}

function ColumnMapping({ file, onSaved }) {
  const [roles, setRoles] = useState(file.column_roles || {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [rowUnit, setRowUnit] = useState(file.row_unit || "");

  async function save() {
    setSaving(true);
    setError("");
    try {
      const clean = Object.fromEntries(Object.entries(roles).filter(([, v]) => v));
      await api.voiceOfCustomer.patchEvidence(file.id, { column_roles: clean, row_unit: rowUnit });
      onSaved();
    } catch (e) {
      setError(e.message || "Couldn't save the mapping.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ marginTop: 10, borderTop: `1px dashed ${theme.border}`, paddingTop: 10 }}>
      <p style={{ margin: "0 0 4px", fontSize: 12, color: theme.textSecondary }}>
        <strong>Detected columns:</strong> {file.columns.join(", ")}
      </p>
      <p style={{ margin: "0 0 8px", fontSize: 11.5, color: theme.textMuted, lineHeight: 1.5 }}>
        Optional. Mapping a column lets the agent count it across every row — a mapped category column turns theme
        frequency from an estimate into a count. Unmapped columns are still passed through.
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Labelled label="One row is one…">
          <input value={rowUnit} onChange={(e) => setRowUnit(e.target.value)} placeholder="ticket" style={{ ...input, width: 110 }} />
        </Labelled>
        {COLUMN_ROLES.map(([role, label]) => (
          <Labelled key={role} label={label}>
            <select value={roles[role] || ""} onChange={(e) => setRoles((r) => ({ ...r, [role]: e.target.value }))} style={{ ...input, width: 130 }}>
              <option value="">—</option>
              {file.columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Labelled>
        ))}
        <Button small icon={Save} disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save mapping"}
        </Button>
      </div>
      {error && <p style={{ margin: "6px 0 0", fontSize: 11, color: theme.danger }}>{error}</p>}
    </div>
  );
}

function FileRow({ file, onChanged }) {
  const size =
    file.file_format === "csv"
      ? `${(file.row_count ?? 0).toLocaleString()} rows${file.row_unit ? ` (one per ${file.row_unit})` : ""}`
      : file.file_format === "pdf"
      ? `${file.page_count} page(s)`
      : `${file.char_count.toLocaleString()} characters`;
  const period = file.period_start || file.period_end ? `${file.period_start || "?"} → ${file.period_end || "?"}` : "period not stated";

  async function remove() {
    if (!window.confirm(`Remove ${file.filename}? Its content is deleted and future runs will not use it.`)) return;
    await api.voiceOfCustomer.deleteEvidence(file.id);
    onChanged();
  }

  return (
    <div style={{ border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, padding: "12px 14px", marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>{file.filename}</span>
            <Badge tone="muted">{FILE_TYPE_LABEL[file.file_type] || file.file_type}</Badge>
            <Badge tone={file.ingest_status === "ingested" ? "success" : "warning"}>{file.ingest_status}</Badge>
            {file.is_sample ? <Badge tone="warning">Sample</Badge> : <Badge tone="muted">Complete</Badge>}
          </div>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: theme.textSecondary }}>
            {size} · as of {file.as_of || "not stated"} · {period}
            {file.segment_coverage?.length ? ` · segments ${file.segment_coverage.join(", ")}` : ""}
          </p>
          {file.is_sample && (
            <p style={{ margin: "3px 0 0", fontSize: 12, color: theme.textMuted }}>
              Sample: {file.sample_description || "no description given"}
            </p>
          )}
          {file.issues?.map((i, k) => (
            <p key={k} style={{ margin: "4px 0 0", fontSize: 11.5, color: theme.warning, display: "flex", gap: 5 }}>
              <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 2 }} /> {i.message}
            </p>
          ))}
        </div>
        <button title="Remove this file" onClick={remove} style={{ border: "none", background: "transparent", cursor: "pointer", padding: 4 }}>
          <Trash2 size={14} color={theme.textMuted} />
        </button>
      </div>
      {file.file_format === "csv" && <ColumnMapping key={file.id + JSON.stringify(file.column_roles)} file={file} onSaved={onChanged} />}
    </div>
  );
}

function PlannedIntegrations() {
  return (
    <section style={{ marginTop: 28 }}>
      <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>Planned integrations</h2>
      <p style={{ margin: "4px 0 10px", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>
        <strong>Not yet available.</strong> None of these is connected or connectable today. They are listed so it is
        clear what each would add — today, the same evidence comes in as an upload above.
      </p>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: theme.textPrimary, lineHeight: 1.75 }}>
        {PLANNED_INTEGRATIONS.map(([name, what]) => (
          <li key={name}>
            <strong>{name}</strong> <span style={{ color: theme.textMuted }}>(not yet available)</span> —{" "}
            <span style={{ color: theme.textSecondary }}>{what}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function EvidenceScreen() {
  const navigate = useNavigate();
  const [files, setFiles] = useState(null);
  const [state, setState] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([api.voiceOfCustomer.listEvidence(), api.voiceOfCustomer.getContextState()]);
      setFiles(f);
      setState(s);
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load evidence.");
      setFiles([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div style={{ padding: "28px 32px 48px", overflowY: "auto", background: theme.bg, flex: 1 }}>
      <div style={{ maxWidth: 1000 }}>
        <button
          onClick={() => navigate("/agents/voice-of-customer/context")}
          style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: theme.textMuted, fontFamily: FONT, marginBottom: 10 }}
        >
          <ArrowLeft size={13} /> Back to customer context
        </button>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>Evidence</h1>
        <p style={{ margin: "6px 0 16px", fontSize: 13, color: theme.textSecondary, maxWidth: 720, lineHeight: 1.55 }}>
          The customer voice itself. Large exports are never summarised: counts are taken over every row, and the
          verbatims the agent quotes are a stated sample, word for word.
        </p>

        {state && (
          <div style={{ marginBottom: 18 }}>
            <TierBanner state={state} compact />
          </div>
        )}

        <UploadForm onUploaded={load} />

        {error && <p style={{ fontSize: 12, color: theme.danger }}>{error}</p>}
        {files === null ? (
          <Spinner size={16} />
        ) : files.length === 0 ? (
          <p style={{ fontSize: 12.5, color: theme.textMuted, fontStyle: "italic" }}>
            No evidence uploaded. A run now is an external customer-context analysis.
          </p>
        ) : (
          files.map((f) => <FileRow key={f.id} file={f} onChanged={load} />)
        )}

        <PlannedIntegrations />
      </div>
    </div>
  );
}
