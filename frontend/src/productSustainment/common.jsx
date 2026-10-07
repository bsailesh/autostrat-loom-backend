// Pieces shared by this agent's input screens.
import { useState } from "react";
import { AlertTriangle, ArrowLeft, Download, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Badge, Button } from "../components/atoms.jsx";
import { FONT, theme } from "../theme.js";
import { TIER_COPY, saveBlob } from "./reportMeta.js";

const TONE_BORDER = { success: "success", warning: "warning", danger: "danger" };

export function TierBanner({ readiness, showMissing = true }) {
  const copy = TIER_COPY[readiness?.operating_tier];
  if (!copy) return null;
  const tone = TONE_BORDER[copy.tone];
  const missing = (readiness.items || []).filter((i) => i.status === "missing");
  return (
    <div style={{ border: `1px solid ${theme[tone]}`, background: theme[`${tone}Bg`], borderRadius: 8, padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: theme.textSecondary }}>
          Operating tier
        </span>
        <Badge tone={copy.tone}>{copy.label}</Badge>
      </div>
      <p style={{ margin: "7px 0 0", fontSize: 13, color: theme.textPrimary, lineHeight: 1.55 }}>{copy.note}</p>
      {showMissing && missing.length > 0 && (
        <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 12, color: theme.textSecondary, lineHeight: 1.6 }}>
          {missing.map((i) => (
            <li key={i.key}>
              <strong>{i.label}</strong> — {i.consequence}
            </li>
          ))}
        </ul>
      )}
      <p style={{ margin: "10px 0 0", fontSize: 11.5, color: theme.textMuted }}>
        A run is never blocked. It degrades, and states its tier in the first line of every report.
      </p>
    </div>
  );
}

export function BackLink({ to, label }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(to)}
      style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: theme.textMuted, fontFamily: FONT, marginBottom: 10 }}
    >
      <ArrowLeft size={13} /> {label}
    </button>
  );
}

const STATUS_TONE = { valid: "success", valid_with_warnings: "warning", invalid: "danger" };
const STATUS_LABEL = { valid: "Valid", valid_with_warnings: "Valid with warnings", invalid: "Rejected — nothing written" };

export function ValidationResult({ file }) {
  if (!file) return null;
  const errors = (file.issues || []).filter((i) => i.severity === "error");
  const warnings = (file.issues || []).filter((i) => i.severity === "warning");
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Badge tone={STATUS_TONE[file.validation_status] || "muted"}>{STATUS_LABEL[file.validation_status] || file.validation_status}</Badge>
        <span style={{ fontSize: 11.5, color: theme.textMuted }}>
          {file.filename} · {file.row_count.toLocaleString()} row(s) loaded{file.as_of ? ` · as of ${file.as_of}` : ""}
        </span>
      </div>
      {[...errors, ...warnings].slice(0, 30).map((i, k) => (
        <p key={k} style={{ margin: "4px 0 0", fontSize: 11.5, color: i.severity === "error" ? theme.danger : theme.warning, display: "flex", gap: 5 }}>
          <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>
            {i.row ? `Row ${i.row}` : ""}
            {i.field ? ` · ${i.field}` : ""}
            {i.row || i.field ? ": " : ""}
            {i.message}
          </span>
        </p>
      ))}
      {errors.length + warnings.length > 30 && (
        <p style={{ margin: "4px 0 0", fontSize: 11.5, color: theme.textMuted }}>
          … and {errors.length + warnings.length - 30} more.
        </p>
      )}
    </div>
  );
}

// Template download is the primary action: headers generated from the
// declared ids are correct by construction.
export function UploadCard({ title, blurb, templateKey, onUpload, file, item, asOf }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [asOfValue, setAsOfValue] = useState("");

  async function pick(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setError("");
    try {
      await onUpload(f, asOfValue);
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, padding: "12px 14px", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: theme.textPrimary }}>{title}</h3>
        {item && <Badge tone={item.status === "set" ? "success" : "warning"}>{item.status === "set" ? "Loaded" : "Not loaded"}</Badge>}
      </div>
      <p style={{ margin: "5px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>{blurb}</p>
      {item?.consequence && (
        <p style={{ margin: "6px 0 0", fontSize: 12, color: theme.warning, display: "flex", gap: 6 }}>
          <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>
            <strong>If left empty:</strong> {item.consequence}
          </span>
        </p>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
        <Button small variant="primary" icon={Download} onClick={async () => saveBlob(await api.productSustainment.downloadTemplate(templateKey))}>
          Download template
        </Button>
        <label
          style={{
            fontSize: 12, fontWeight: 600, padding: "5px 10px", borderRadius: 8, border: `1px solid ${theme.border}`,
            background: theme.surface, cursor: busy ? "default" : "pointer", display: "inline-flex", alignItems: "center", gap: 6,
            opacity: busy ? 0.55 : 1, fontFamily: FONT,
          }}
        >
          <Upload size={13} /> {busy ? "Uploading…" : "Upload CSV"}
          <input type="file" accept=".csv" onChange={pick} disabled={busy} style={{ display: "none" }} />
        </label>
        {asOf && (
          <label style={{ fontSize: 11.5, color: theme.textMuted, display: "flex", gap: 6, alignItems: "center" }}>
            As of
            <input type="date" value={asOfValue} onChange={(e) => setAsOfValue(e.target.value)}
                   style={{ fontFamily: FONT, fontSize: 12, padding: "3px 6px", border: `1px solid ${theme.border}`, borderRadius: 4 }} />
          </label>
        )}
        {error && <span style={{ fontSize: 11.5, color: theme.danger }}>{error}</span>}
      </div>
      <ValidationResult file={file} />
    </section>
  );
}
