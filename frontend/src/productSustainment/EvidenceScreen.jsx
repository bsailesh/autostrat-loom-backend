// Reliability and quality evidence -- the Voice of Customer evidence pattern,
// rebuilt here rather than imported to keep the agent modules independent.
// Free text is mined, never summarised; findings at assembly level are rolled
// up to every LRU containing that assembly, and the reports say so.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Trash2, Upload } from "lucide-react";
import { api } from "../api.js";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { FONT, theme } from "../theme.js";
import { BackLink } from "./common.jsx";
import { EVIDENCE_TYPES } from "./reportMeta.js";

const TYPE_LABEL = Object.fromEntries(EVIDENCE_TYPES);
const input = { fontFamily: FONT, fontSize: 12, padding: "5px 7px", border: `1px solid ${theme.border}`, borderRadius: 4, background: theme.surface };
const EMPTY = { file_type: EVIDENCE_TYPES[0][0], as_of: "", period_start: "", period_end: "", is_sample: false, sample_description: "" };

export default function EvidenceScreen() {
  const [files, setFiles] = useState(null);
  const [file, setFile] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setFiles(await api.productSustainment.listEvidence());
    } catch (e) {
      setError(e.message || "Couldn't load evidence.");
      setFiles([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await api.productSustainment.uploadEvidence(file, { ...form, is_sample: form.is_sample ? "true" : "false" });
      setFile(null);
      setForm(EMPTY);
      await load();
    } catch (e) {
      setError(e.message || "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(f) {
    if (!window.confirm(`Remove ${f.filename}? Future runs will not use it.`)) return;
    await api.productSustainment.deleteEvidence(f.id);
    await load();
  }

  return (
    <div style={{ padding: "28px 32px 48px", overflowY: "auto", background: theme.bg, flex: 1 }}>
      <div style={{ maxWidth: 1000 }}>
        <BackLink to="/agents/product-sustainment/data" label="Back to inventory, demand and risk" />
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>Reliability evidence</h1>
        <p style={{ margin: "6px 0 16px", fontSize: 13, color: theme.textSecondary, maxWidth: 720, lineHeight: 1.55 }}>
          Support tickets, field service and failure reports, warranty claims, investigations and return authorisations.
          Text, PDF or CSV, up to 25 MB. A finding attributed to an assembly is rolled up to every LRU containing it, and
          the reports say when that has happened. Without evidence, failure clustering, MTBUR and MTTR are unavailable.
        </p>

        <section style={{ border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, padding: "14px 16px", marginBottom: 18 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <select value={form.file_type} onChange={set("file_type")} style={input}>
              {EVIDENCE_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <input type="file" accept=".txt,.md,.pdf,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ fontSize: 12 }} />
            <label style={{ fontSize: 11.5, color: theme.textMuted }}>As of <input type="date" value={form.as_of} onChange={set("as_of")} style={input} /></label>
            <label style={{ fontSize: 11.5, color: theme.textMuted }}>From <input type="date" value={form.period_start} onChange={set("period_start")} style={input} /></label>
            <label style={{ fontSize: 11.5, color: theme.textMuted }}>To <input type="date" value={form.period_end} onChange={set("period_end")} style={input} /></label>
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={form.is_sample} onChange={set("is_sample")} /> This file is a sample, not the complete set
            </label>
            {form.is_sample && (
              <input value={form.sample_description} onChange={set("sample_description")} placeholder="How it was sampled"
                     style={{ ...input, flex: 1, minWidth: 220 }} />
            )}
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center" }}>
            <Button variant="primary" small icon={Upload} disabled={!file || busy} onClick={submit}>
              {busy ? "Uploading…" : "Upload"}
            </Button>
            {error && <span style={{ fontSize: 12, color: theme.danger, display: "flex", gap: 5 }}><AlertTriangle size={13} /> {error}</span>}
          </div>
        </section>

        {files === null ? (
          <Spinner size={16} />
        ) : files.length === 0 ? (
          <p style={{ fontSize: 12.5, color: theme.textMuted, fontStyle: "italic" }}>No reliability evidence uploaded.</p>
        ) : (
          files.map((f) => (
            <div key={f.id} style={{ border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, padding: "10px 14px", marginBottom: 8, display: "flex", justifyContent: "space-between", gap: 10 }}>
              <div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{f.filename}</span>
                  <Badge tone="muted">{TYPE_LABEL[f.file_type] || f.file_type}</Badge>
                  {f.is_sample ? <Badge tone="warning">Sample</Badge> : <Badge tone="muted">Complete</Badge>}
                </div>
                <p style={{ margin: "3px 0 0", fontSize: 12, color: theme.textSecondary }}>
                  {f.file_format === "csv" ? `${(f.row_count ?? 0).toLocaleString()} rows` : f.file_format === "pdf" ? `${f.page_count} page(s)` : `${f.char_count.toLocaleString()} characters`}
                  {" · "}as of {f.as_of || "not stated"}
                </p>
              </div>
              <button title="Remove this file" onClick={() => remove(f)} style={{ border: "none", background: "transparent", cursor: "pointer" }}>
                <Trash2 size={14} color={theme.textMuted} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
