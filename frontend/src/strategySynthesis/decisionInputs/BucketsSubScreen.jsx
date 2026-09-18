// Bucket configuration's own sub-screen (Part 6): add, rename, set
// contractable. Changing buckets after capacity/roadmap files are uploaded
// invalidates those files' bucket-shaped columns -- the backend deliberately
// leaves warning about this to the frontend (see put_buckets' own
// docstring), so this screen watches for it and says so plainly. There's no
// backend field that tracks "this specific file no longer matches the
// buckets" -- that plumbing doesn't exist, so this is a point-in-time
// warning tied to editing buckets, not an ongoing per-file flag.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronLeft, Plus, Trash2 } from "lucide-react";
import { api } from "../../api.js";
import { theme, FONT } from "../../theme.js";
import { Button, Spinner } from "../../components/atoms.jsx";
import { PageHeader } from "../../components/PageHeader.jsx";

const CONTRACTABLE_OPTIONS = ["yes", "partial", "no"];

export default function BucketsSubScreen() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [buckets, setBuckets] = useState([]);
  const [originalKeys, setOriginalKeys] = useState([]);
  const [affectedFiles, setAffectedFiles] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [existing, files] = await Promise.all([api.strategySynthesis.getBuckets(), api.strategySynthesis.listFiles()]);
        setBuckets(existing.length ? existing : [blankBucket(), blankBucket()]);
        setOriginalKeys(existing.map((b) => b.bucket_key));
        setAffectedFiles(files.filter((f) => (f.file_type === "capacity" || f.file_type === "roadmap") && f.row_count > 0));
      } catch (e) {
        setError(e.message || "Couldn't load buckets.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function blankBucket() {
    return { bucket_key: "", bucket_name: "", contractable: "no", note: "" };
  }

  function update(i, field, value) {
    setBuckets((prev) => prev.map((b, idx) => (idx === i ? { ...b, [field]: value } : b)));
  }

  function addRow() {
    if (buckets.length >= 8) return;
    setBuckets((prev) => [...prev, blankBucket()]);
  }

  function removeRow(i) {
    if (buckets.length <= 2) return;
    setBuckets((prev) => prev.filter((_, idx) => idx !== i));
  }

  const currentKeys = buckets.map((b) => b.bucket_key.trim()).filter(Boolean);
  const keysChanged = affectedFiles.length > 0 && JSON.stringify([...originalKeys].sort()) !== JSON.stringify([...currentKeys].sort());

  async function onSave() {
    setSaving(true);
    setError("");
    try {
      const cleaned = buckets.map((b) => ({ ...b, bucket_key: b.bucket_key.trim(), bucket_name: b.bucket_name.trim() }));
      const saved = await api.strategySynthesis.putBuckets(cleaned);
      setBuckets(saved);
      setOriginalKeys(saved.map((b) => b.bucket_key));
      navigate("/agents/strategy-synthesis/inputs");
    } catch (e) {
      setError(e.message || "Couldn't save buckets.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Capacity buckets"
        subtitle="Decision inputs"
        right={
          <Button small variant="ghost" icon={ChevronLeft} onClick={() => navigate("/agents/strategy-synthesis/inputs")}>
            Back
          </Button>
        }
      />
      <div style={{ padding: "24px 32px", overflowY: "auto" }}>
        {loading ? (
          <Spinner size={18} />
        ) : (
          <div style={{ maxWidth: 640 }}>
            <p style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, margin: "0 0 16px" }}>
              2-8 buckets. Each key is used verbatim as a CSV column header in the capacity and roadmap templates
              (letters, digits and underscore only, starting with a letter).
            </p>

            {keysChanged && (
              <p
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "flex-start",
                  fontSize: 12.5,
                  color: theme.warning,
                  background: theme.warningBg,
                  padding: "10px 12px",
                  borderRadius: 8,
                  margin: "0 0 16px",
                }}
              >
                <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                Changing buckets can invalidate previously uploaded files: {affectedFiles.map((f) => f.filename).join(", ")}.
                Re-upload them against the new template after saving.
              </p>
            )}

            {error && (
              <p style={{ color: theme.danger, fontSize: 13, margin: "0 0 14px", display: "flex", gap: 6, alignItems: "center" }}>
                <AlertTriangle size={14} /> {error}
              </p>
            )}

            <div style={{ display: "grid", gap: 10, marginBottom: 14 }}>
              {buckets.map((b, i) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    value={b.bucket_key}
                    onChange={(e) => update(i, "bucket_key", e.target.value)}
                    placeholder="KEY (e.g. HW)"
                    style={{ ...inputStyle, width: 120, fontFamily: "monospace" }}
                  />
                  <input
                    value={b.bucket_name}
                    onChange={(e) => update(i, "bucket_name", e.target.value)}
                    placeholder="Name (e.g. Hardware)"
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  <select value={b.contractable} onChange={(e) => update(i, "contractable", e.target.value)} style={inputStyle}>
                    {CONTRACTABLE_OPTIONS.map((o) => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                  <button
                    title="Remove bucket"
                    onClick={() => removeRow(i)}
                    disabled={buckets.length <= 2}
                    style={{ border: "none", background: "transparent", cursor: buckets.length <= 2 ? "default" : "pointer", opacity: buckets.length <= 2 ? 0.3 : 1, padding: 6 }}
                  >
                    <Trash2 size={15} color={theme.danger} />
                  </button>
                </div>
              ))}
            </div>

            <Button small variant="ghost" icon={Plus} disabled={buckets.length >= 8} onClick={addRow}>
              Add bucket
            </Button>

            <div style={{ marginTop: 20 }}>
              <Button variant="primary" disabled={saving} onClick={onSave}>
                {saving ? "Saving…" : "Save buckets"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

const inputStyle = {
  fontFamily: FONT,
  fontSize: 13,
  padding: "7px 10px",
  borderRadius: 7,
  border: `1px solid ${theme.border}`,
  background: "#fff",
  color: theme.textPrimary,
  outline: "none",
};
