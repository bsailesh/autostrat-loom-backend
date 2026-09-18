// Report 7's "what to scope next" is the bridge between the unscoped
// candidate population and the ranked portfolio (Part 6: "Candidate
// actions"). Report 7's own text is frozen at run time, so this panel reads
// live candidate state from GET /candidates rather than parsing the report
// body -- a dismissed or scoped candidate needs to reflect that immediately,
// not wait for the next run to regenerate the report text.
import { useEffect, useState } from "react";
import { AlertTriangle, Check, CircleDot, X } from "lucide-react";
import { api } from "../../api.js";
import { theme, FONT } from "../../theme.js";
import { Badge, Button, Spinner } from "../../components/atoms.jsx";

const STATUS_TONE = { new: "accent", under_review: "warning", scoped: "success", dismissed: "muted" };
const STATUS_LABEL = { new: "New", under_review: "Under review", scoped: "Scoped", dismissed: "Dismissed" };

export default function CandidateActions() {
  const [candidates, setCandidates] = useState(null);
  const [buckets, setBuckets] = useState([]);
  const [projectTypes, setProjectTypes] = useState([]);
  const [error, setError] = useState("");

  const reload = () => api.strategySynthesis.listCandidates().then(setCandidates).catch((e) => setError(e.message));

  useEffect(() => {
    reload();
    api.strategySynthesis.getBuckets().then(setBuckets).catch(() => {});
    api.strategySynthesis.getConfig().then((c) => setProjectTypes(c.project_types || [])).catch(() => {});
  }, []);

  if (error) {
    return (
      <p style={{ color: theme.danger, fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
        <AlertTriangle size={14} /> {error}
      </p>
    );
  }
  if (candidates === null) return <Spinner size={16} />;

  const actionable = candidates.filter((c) => c.status === "new" || c.status === "under_review");
  const resolved = candidates.filter((c) => c.status === "scoped" || c.status === "dismissed");

  return (
    <div style={{ marginTop: 28, paddingTop: 20, borderTop: `2px solid ${theme.border}` }}>
      <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: theme.textSecondary, margin: "0 0 12px" }}>
        Candidates awaiting a decision
      </p>
      {actionable.length === 0 ? (
        <p style={{ fontSize: 13, color: theme.textMuted }}>No candidates need a decision right now.</p>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {actionable.map((c) => (
            <CandidateRow key={c.id} candidate={c} buckets={buckets} projectTypes={projectTypes} onChanged={reload} />
          ))}
        </div>
      )}

      {resolved.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ fontSize: 12, color: theme.textMuted, cursor: "pointer" }}>
            {resolved.length} resolved candidate{resolved.length === 1 ? "" : "s"}
          </summary>
          <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
            {resolved.map((c) => (
              <div key={c.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, padding: "6px 0" }}>
                <span>
                  <strong>{c.candidate_key}</strong> {c.name}
                </span>
                <Badge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function CandidateRow({ candidate, buckets, projectTypes, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [mode, setMode] = useState(null); // null | "dismiss" | "scope"
  const [reason, setReason] = useState("");
  const [projectType, setProjectType] = useState("");
  const [targetFy, setTargetFy] = useState("");
  const [effort, setEffort] = useState({});

  async function patch(status, extra = {}) {
    setBusy(true);
    setErr("");
    try {
      await api.strategySynthesis.patchCandidate(candidate.candidate_key, { status, ...extra });
      setMode(null);
      onChanged();
    } catch (e) {
      setErr(e.message || "Couldn't update this candidate.");
    } finally {
      setBusy(false);
    }
  }

  async function submitScope() {
    const effort_by_bucket = Object.fromEntries(
      Object.entries(effort)
        .map(([k, v]) => [k, parseFloat(v)])
        .filter(([, v]) => !Number.isNaN(v) && v > 0)
    );
    if (Object.keys(effort_by_bucket).length === 0) {
      setErr("Enter effort for at least one bucket.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await api.strategySynthesis.scopeCandidate(candidate.candidate_key, {
        project_type: projectType, target_fy: targetFy, effort_by_bucket,
      });
      setMode(null);
      onChanged();
    } catch (e) {
      setErr(e.message || "Couldn't scope this candidate.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ border: `1px solid ${theme.border}`, borderRadius: 10, padding: "12px 14px", background: theme.surface }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <p style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: theme.textPrimary }}>
            {candidate.candidate_key} — {candidate.name}
          </p>
          <p style={{ margin: "3px 0 0", fontSize: 12.5, color: theme.textSecondary }}>{candidate.problem_addressed}</p>
          <p style={{ margin: "3px 0 0", fontSize: 11.5, color: theme.textMuted }}>
            {candidate.origin}
            {candidate.support_classification ? ` · ${candidate.support_classification}` : ""}
          </p>
        </div>
        <Badge tone={STATUS_TONE[candidate.status]}>{STATUS_LABEL[candidate.status]}</Badge>
      </div>

      {err && (
        <p style={{ color: theme.danger, fontSize: 12, margin: "8px 0 0", display: "flex", gap: 5, alignItems: "center" }}>
          <AlertTriangle size={12} /> {err}
        </p>
      )}

      {mode === null && (
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          {candidate.status !== "under_review" && (
            <Button small variant="ghost" icon={CircleDot} disabled={busy} onClick={() => patch("under_review")}>
              Mark under review
            </Button>
          )}
          <Button small variant="primary" disabled={busy} onClick={() => setMode("scope")}>
            Scope
          </Button>
          <Button small variant="ghost" icon={X} disabled={busy} onClick={() => setMode("dismiss")}>
            Dismiss
          </Button>
        </div>
      )}

      {mode === "dismiss" && (
        <div style={{ marginTop: 10 }}>
          <input
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for dismissing (required)"
            style={inputStyle}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <Button small variant="primary" icon={Check} disabled={busy || !reason.trim()} onClick={() => patch("dismissed", { dismissal_reason: reason.trim() })}>
              Confirm dismiss
            </Button>
            <Button small variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {mode === "scope" && (
        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <select value={projectType} onChange={(e) => setProjectType(e.target.value)} style={inputStyle}>
              <option value="">Project type…</option>
              {projectTypes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input value={targetFy} onChange={(e) => setTargetFy(e.target.value)} placeholder="Target FY (optional)" style={inputStyle} />
          </div>
          <div>
            <p style={{ fontSize: 11, color: theme.textMuted, margin: "0 0 6px" }}>Effort by bucket (at least one required)</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {buckets.map((b) => (
                <label key={b.bucket_key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                  {b.bucket_key}
                  <input
                    type="number"
                    min="0"
                    value={effort[b.bucket_key] || ""}
                    onChange={(e) => setEffort((prev) => ({ ...prev, [b.bucket_key]: e.target.value }))}
                    style={{ ...inputStyle, width: 70 }}
                  />
                </label>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button small variant="primary" icon={Check} disabled={busy} onClick={submitScope}>
              Add to roadmap
            </Button>
            <Button small variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

const inputStyle = {
  fontFamily: FONT,
  fontSize: 13,
  padding: "6px 9px",
  borderRadius: 7,
  border: `1px solid ${theme.border}`,
  background: "#fff",
  color: theme.textPrimary,
  outline: "none",
};
