// The applicability envelope: eight form-based sections with repeatable
// rows, each showing its status and — when missing — what that absence
// costs, never a bare badge.
//
// Two things the briefing is specific about and this screen implements:
//
// 1. The OPERATING STATE IS SHOWN PROMINENTLY at the top, with what
//    unscoped actually means. A reader must never mistake an industry
//    survey for their own regulatory obligations.
// 2. Consequence text appears ONLY for a dimension that is missing. The
//    backend already returns "" for a dimension that is set (the bug fixed
//    in b4f3282 on Agent 5's /readiness was showing every section's
//    missing-case warning regardless of status), and this screen renders
//    what it is given rather than deciding for itself.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { FONT, theme } from "../theme.js";
import { OPERATING_STATE_COPY, SCOPE_SECTIONS } from "./reportMeta.js";

function blankRow(fields) {
  return Object.fromEntries(fields.map((f) => [f.name, f.options ? f.options[0] : ""]));
}

function Field({ field, value, onChange }) {
  const common = {
    value: value ?? "",
    onChange: (e) => onChange(e.target.value),
    style: {
      fontFamily: FONT,
      fontSize: 12,
      padding: "5px 7px",
      border: `1px solid ${theme.border}`,
      borderRadius: 4,
      background: theme.surface,
      color: theme.textPrimary,
      width: field.grow ? "100%" : field.width || 150,
      minWidth: 0,
    },
  };
  if (field.options) {
    return (
      <select {...common}>
        {field.options.map((o) => (
          <option key={o} value={o}>
            {o === "" ? "—" : o}
          </option>
        ))}
      </select>
    );
  }
  return <input {...common} placeholder={field.placeholder || ""} />;
}

function Section({ section, item, onSaved }) {
  const [rows, setRows] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await api.techRegulation.getScope(section.dimension);
      setRows(Array.isArray(data) ? data : []);
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load this section.");
      setRows([]);
    }
  }, [section.dimension]);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setSaving(true);
    setError("");
    try {
      // Drop rows the user added and left entirely blank rather than
      // rejecting the whole save over them.
      const payload = rows.filter((r) =>
        section.fields.some((f) => String(r[f.name] ?? "").trim() !== "")
      );
      const saved = await api.techRegulation.putScope(section.dimension, payload);
      setRows(Array.isArray(saved) ? saved : payload);
      setSavedAt(Date.now());
      onSaved();
    } catch (e) {
      setError(e.message || "Couldn't save this section.");
    } finally {
      setSaving(false);
    }
  }

  const isSet = item?.status === "set";

  return (
    <section
      style={{
        border: `1px solid ${theme.border}`,
        borderRadius: 8,
        background: theme.surface,
        marginBottom: 14,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "12px 14px",
          background: theme.surfaceMuted,
          borderBottom: `1px solid ${theme.border}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>{section.title}</h2>
          {item && (
            <Badge tone={isSet ? "success" : "warning"}>
              {isSet ? `${item.count} supplied` : "Not supplied"}
            </Badge>
          )}
        </div>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>
          {section.blurb}
        </p>
        {/* Rendered only when the backend sends it, which is only when the
            dimension is missing. */}
        {item?.consequence && (
          <p
            style={{
              margin: "8px 0 0",
              fontSize: 12,
              color: theme.warning,
              display: "flex",
              gap: 6,
              alignItems: "flex-start",
              lineHeight: 1.5,
            }}
          >
            <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>
              <strong>If left empty:</strong> {item.consequence}
            </span>
          </p>
        )}
      </div>

      <div style={{ padding: "10px 14px 14px" }}>
        {rows === null ? (
          <Spinner size={14} />
        ) : (
          <>
            {rows.length > 0 && (
              <div style={{ display: "flex", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                {section.fields.map((f) => (
                  <span
                    key={f.name}
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: 0.4,
                      textTransform: "uppercase",
                      color: theme.textMuted,
                      width: f.grow ? undefined : f.width || 150,
                      flex: f.grow ? 1 : undefined,
                      minWidth: 0,
                    }}
                  >
                    {f.label}
                  </span>
                ))}
                <span style={{ width: 24 }} />
              </div>
            )}

            {rows.map((row, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6, alignItems: "center", flexWrap: "wrap" }}>
                {section.fields.map((f) => (
                  <div key={f.name} style={{ flex: f.grow ? 1 : undefined, minWidth: 0 }}>
                    <Field
                      field={f}
                      value={row[f.name]}
                      onChange={(v) =>
                        setRows((prev) => prev.map((r, j) => (j === i ? { ...r, [f.name]: v } : r)))
                      }
                    />
                  </div>
                ))}
                <button
                  title="Remove this row"
                  onClick={() => setRows((prev) => prev.filter((_, j) => j !== i))}
                  style={{ border: "none", background: "transparent", cursor: "pointer", padding: 4, width: 24 }}
                >
                  <Trash2 size={13} color={theme.textMuted} />
                </button>
              </div>
            ))}

            {rows.length === 0 && (
              <p style={{ margin: "0 0 8px", fontSize: 12, color: theme.textMuted, fontStyle: "italic" }}>
                Nothing supplied yet.
              </p>
            )}

            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
              <Button small icon={Plus} onClick={() => setRows((prev) => [...prev, blankRow(section.fields)])}>
                Add row
              </Button>
              <Button small icon={Save} disabled={saving} onClick={save}>
                {saving ? "Saving…" : "Save section"}
              </Button>
              {savedAt && !saving && !error && (
                <span style={{ fontSize: 11, color: theme.success }}>Saved</span>
              )}
              {error && <span style={{ fontSize: 11, color: theme.danger }}>{error}</span>}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

export default function ScopeScreen() {
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [error, setError] = useState("");

  const loadState = useCallback(async () => {
    try {
      setState(await api.techRegulation.getScopeState());
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load the scope state.");
    }
  }, []);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const byKey = Object.fromEntries((state?.items || []).map((i) => [i.key, i]));
  const copy = OPERATING_STATE_COPY[state?.operating_state] || null;
  const missing = (state?.items || []).filter((i) => i.status === "missing");

  return (
    <div style={{ padding: "28px 32px 48px", overflowY: "auto", background: theme.bg, flex: 1 }}>
      <div style={{ maxWidth: 1000 }}>
        <button
          onClick={() => navigate("/agents/tech-regulation")}
          style={{
            border: "none",
            background: "transparent",
            cursor: "pointer",
            padding: 0,
            display: "flex",
            alignItems: "center",
            gap: 5,
            fontSize: 12,
            color: theme.textMuted,
            fontFamily: FONT,
            marginBottom: 10,
          }}
        >
          <ArrowLeft size={13} /> Back to the agent
        </button>

        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>
          Applicability envelope
        </h1>
        <p style={{ margin: "6px 0 0", fontSize: 13, color: theme.textSecondary, maxWidth: 740, lineHeight: 1.55 }}>
          What you make, where you sell it, and what it is approved under. Regulation does not work like a
          market: without this, the agent can only report that FAA, EASA and ICAO exist. Roughly fifteen
          minutes of work, and it changes what the agent can say.
        </p>

        {error && (
          <p style={{ marginTop: 12, fontSize: 12, color: theme.danger, display: "flex", gap: 6, alignItems: "center" }}>
            <AlertTriangle size={13} /> {error}
          </p>
        )}

        {/* Operating state, prominently, with what it means. */}
        {copy && (
          <div
            style={{
              marginTop: 18,
              marginBottom: 22,
              border: `1px solid ${
                copy.tone === "success" ? theme.success : copy.tone === "warning" ? theme.warning : theme.danger
              }`,
              background:
                copy.tone === "success" ? theme.successBg : copy.tone === "warning" ? theme.warningBg : theme.dangerBg,
              borderRadius: 8,
              padding: "14px 16px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: 0.6,
                  textTransform: "uppercase",
                  color: theme.textSecondary,
                }}
              >
                Operating state
              </span>
              <Badge tone={copy.tone}>{copy.label}</Badge>
            </div>
            <p style={{ margin: "7px 0 0", fontSize: 13, color: theme.textPrimary, lineHeight: 1.55 }}>
              {copy.note}
            </p>
            {missing.length > 0 && (
              <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 12, color: theme.textSecondary, lineHeight: 1.6 }}>
                {missing.map((i) => (
                  <li key={i.key}>
                    <strong>{i.label}</strong> — {i.consequence}
                  </li>
                ))}
              </ul>
            )}
            <p style={{ margin: "10px 0 0", fontSize: 11.5, color: theme.textMuted }}>
              A run is never blocked by an incomplete envelope. It degrades, and says so in the first line of
              every report.
            </p>
          </div>
        )}

        {SCOPE_SECTIONS.map((section) => (
          <Section key={section.key} section={section} item={byKey[section.key]} onSaved={loadState} />
        ))}
      </div>
    </div>
  );
}
