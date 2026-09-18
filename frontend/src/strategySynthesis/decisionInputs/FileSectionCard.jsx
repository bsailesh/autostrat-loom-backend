// The CSV section pattern shared by the five file-backed sections (products
// fleet, capacity, roadmap, dependencies, financials). Template-first, per
// the explicit product decision: a design partner won't have files in our
// column format, so "download template" leads, visually primary, and
// upload is the secondary, subordinate action -- never the first thing
// shown.
import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, Upload } from "lucide-react";
import { api } from "../../api.js";
import { theme, FONT, MONO } from "../../theme.js";
import { Badge, Button } from "../../components/atoms.jsx";
import { absoluteTime } from "../../lib/time.js";

const STATUS_BADGE = {
  invalid: { tone: "danger", label: "Invalid" },
  valid_with_warnings: { tone: "warning", label: "Set, with warnings" },
  valid: { tone: "success", label: "Set" },
};

export default function FileSectionCard({ fileType, fileInfo, bucketsReady, onChanged }) {
  const inputRef = useRef(null);
  const [asOf, setAsOf] = useState("");
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [lastResult, setLastResult] = useState(null); // IngestResultOut from the most recent upload attempt
  const [error, setError] = useState("");

  async function downloadTemplate() {
    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await api.strategySynthesis.getTemplate(fileType);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message || "Couldn't download the template.");
    } finally {
      setDownloading(false);
    }
  }

  async function onFileChosen(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-choosing the same filename after a fix
    if (!file) return;
    setUploading(true);
    setError("");
    setLastResult(null);
    try {
      const result = await api.strategySynthesis.uploadFile(fileType, file, { asOf: asOf || undefined });
      setLastResult(result);
      onChanged();
    } catch (e2) {
      setError(e2.message || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  const badge = fileInfo ? STATUS_BADGE[fileInfo.validation_status] || STATUS_BADGE.valid : null;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <Button
          icon={downloading ? undefined : Download}
          disabled={downloading || (bucketsReady === false)}
          title={bucketsReady === false ? "Declare capacity buckets first — this template is shaped by your declared buckets." : undefined}
          onClick={downloadTemplate}
        >
          {downloading ? "Preparing…" : "Download template"}
        </Button>
        <span style={{ fontSize: 12, color: theme.textMuted }}>Start here — get the column format right before uploading.</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, paddingLeft: 2 }}>
        <label style={{ fontSize: 12, color: theme.textMuted }}>
          As of (optional)
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            style={{ marginLeft: 6, fontFamily: FONT, fontSize: 12, padding: "4px 7px", borderRadius: 6, border: `1px solid ${theme.border}` }}
          />
        </label>
        <input ref={inputRef} type="file" accept=".csv" style={{ display: "none" }} onChange={onFileChosen} />
        <Button small variant="ghost" icon={uploading ? undefined : Upload} disabled={uploading} onClick={() => inputRef.current?.click()}>
          {uploading ? "Uploading…" : "Upload completed CSV"}
        </Button>
      </div>

      {error && (
        <p style={{ color: theme.danger, fontSize: 12.5, display: "flex", gap: 6, alignItems: "center", margin: "0 0 12px" }}>
          <AlertTriangle size={13} /> {error}
        </p>
      )}

      {lastResult && (lastResult.errors.length > 0 || lastResult.warnings.length > 0) && (
        <div style={{ marginBottom: 14 }}>
          {lastResult.errors.map((e, i) => (
            <p key={`e${i}`} style={{ color: theme.danger, fontSize: 12.5, margin: "0 0 4px", display: "flex", gap: 6 }}>
              <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
              {e.row ? `Row ${e.row}: ` : ""}
              {e.message}
            </p>
          ))}
          {lastResult.warnings.map((w, i) => (
            <p key={`w${i}`} style={{ color: theme.warning, fontSize: 12.5, margin: "0 0 4px", display: "flex", gap: 6 }}>
              <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
              {w.row ? `Row ${w.row}: ` : ""}
              {w.message}
            </p>
          ))}
          {!lastResult.stored && (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: "4px 0 0" }}>
              Nothing was stored — whatever was previously uploaded (if anything) is still in effect.
            </p>
          )}
        </div>
      )}

      <div style={{ background: theme.surfaceMuted, borderRadius: 10, padding: "12px 14px" }}>
        {!fileInfo ? (
          <p style={{ fontSize: 12.5, color: theme.textMuted, margin: 0 }}>No file uploaded yet.</p>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <Badge tone={badge.tone}>{badge.label}</Badge>
              <span style={{ fontSize: 12.5, fontWeight: 600, color: theme.textPrimary }}>{fileInfo.filename}</span>
              {fileInfo.is_stale && <Badge tone="warning">Stale</Badge>}
            </div>
            <p style={{ fontSize: 12, color: theme.textMuted, margin: "0 0 8px" }}>
              {fileInfo.row_count} row{fileInfo.row_count === 1 ? "" : "s"} · as of{" "}
              {fileInfo.as_of ? absoluteTime(fileInfo.as_of) : "not provided"} · uploaded {absoluteTime(fileInfo.created_at)}
            </p>
            {fileInfo.columns?.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {fileInfo.columns.map((c) => (
                  <span
                    key={c}
                    style={{
                      fontFamily: MONO,
                      fontSize: 10.5,
                      padding: "2px 6px",
                      borderRadius: 5,
                      background: theme.surface,
                      border: `1px solid ${theme.border}`,
                      color: theme.textSecondary,
                    }}
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
            {fileInfo.issues?.length > 0 && !lastResult && (
              <div style={{ marginTop: 8 }}>
                {fileInfo.issues.map((issue, i) => (
                  <p
                    key={i}
                    style={{ fontSize: 11.5, color: issue.severity === "error" ? theme.danger : theme.warning, margin: "0 0 3px", display: "flex", gap: 5 }}
                  >
                    <AlertTriangle size={11} style={{ flexShrink: 0, marginTop: 2 }} />
                    {issue.message}
                  </p>
                ))}
              </div>
            )}
            {fileInfo.validation_status === "valid" && !fileInfo.is_stale && (
              <p style={{ fontSize: 11.5, color: theme.success, margin: "8px 0 0", display: "flex", gap: 5, alignItems: "center" }}>
                <CheckCircle2 size={12} /> Looks good.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
