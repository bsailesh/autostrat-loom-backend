// Repeatable-row editor for one context section. Saves the section
// wholesale (PUT), matching the backend.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Plus, Save, Trash2 } from "lucide-react";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { FONT, theme } from "../theme.js";

export function blankRow(fields) {
  return Object.fromEntries(fields.map((f) => [f.name, f.options ? f.options[0] : ""]));
}

export function Field({ field, value, onChange }) {
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
            {o}
          </option>
        ))}
      </select>
    );
  }
  return <input {...common} placeholder={field.placeholder || ""} inputMode={field.numeric ? "numeric" : undefined} />;
}

// Blank numeric cells become null, never 0: an unknown segment size is a
// legitimate answer and the agent says so.
function toPayload(rows, fields) {
  return rows
    .filter((r) => fields.some((f) => String(r[f.name] ?? "").trim() !== ""))
    .map((r) =>
      Object.fromEntries(
        fields.map((f) => {
          const v = r[f.name];
          if (f.numeric) return [f.name, String(v ?? "").trim() === "" ? null : Number(v)];
          return [f.name, v ?? ""];
        })
      )
    );
}

export function SectionCard({ title, blurb, item, emphasis, children }) {
  const isSet = item?.status === "set";
  return (
    <section
      style={{
        border: `${emphasis ? 2 : 1}px solid ${emphasis ? theme.orange : theme.border}`,
        borderRadius: 8,
        background: theme.surface,
        marginBottom: 14,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "12px 14px",
          background: emphasis ? theme.orangeSoft : theme.surfaceMuted,
          borderBottom: `1px solid ${theme.border}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>{title}</h2>
          {emphasis && <Badge tone="accent">Highest-value input</Badge>}
          {item && (
            <Badge tone={isSet ? "success" : "warning"}>{isSet ? `${item.count} supplied` : "Not supplied"}</Badge>
          )}
        </div>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: theme.textSecondary, lineHeight: 1.5 }}>{blurb}</p>
        {/* Only present when the backend sends it -- i.e. only when missing. */}
        {item?.consequence && (
          <p style={{ margin: "8px 0 0", fontSize: 12, color: theme.warning, display: "flex", gap: 6, lineHeight: 1.5 }}>
            <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>
              <strong>If left empty:</strong> {item.consequence}
            </span>
          </p>
        )}
      </div>
      <div style={{ padding: "10px 14px 14px" }}>{children}</div>
    </section>
  );
}

export function RowsEditor({ fields, load, save, onSaved }) {
  const [rows, setRows] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState(null);

  const reload = useCallback(async () => {
    try {
      const data = await load();
      setRows(
        (Array.isArray(data) ? data : []).map((r) =>
          Object.fromEntries(fields.map((f) => [f.name, r[f.name] === null || r[f.name] === undefined ? "" : String(r[f.name])]))
        )
      );
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load this section.");
      setRows([]);
    }
  }, [load, fields]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onSave() {
    setSaving(true);
    setError("");
    try {
      await save(toPayload(rows, fields));
      await reload();
      setSavedAt(Date.now());
      onSaved?.();
    } catch (e) {
      setError(e.message || "Couldn't save this section.");
    } finally {
      setSaving(false);
    }
  }

  if (rows === null) return <Spinner size={14} />;

  return (
    <>
      {rows.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
          {fields.map((f) => (
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
          {fields.map((f) => (
            <div key={f.name} style={{ flex: f.grow ? 1 : undefined, minWidth: 0 }}>
              <Field
                field={f}
                value={row[f.name]}
                onChange={(v) => setRows((prev) => prev.map((r, j) => (j === i ? { ...r, [f.name]: v } : r)))}
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
        <p style={{ margin: "0 0 8px", fontSize: 12, color: theme.textMuted, fontStyle: "italic" }}>Nothing supplied yet.</p>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
        <Button small icon={Plus} onClick={() => setRows((prev) => [...prev, blankRow(fields)])}>
          Add row
        </Button>
        <Button small icon={Save} disabled={saving} onClick={onSave}>
          {saving ? "Saving…" : "Save section"}
        </Button>
        {savedAt && !saving && !error && <span style={{ fontSize: 11, color: theme.success }}>Saved</span>}
        {error && <span style={{ fontSize: 11, color: theme.danger }}>{error}</span>}
      </div>
    </>
  );
}
