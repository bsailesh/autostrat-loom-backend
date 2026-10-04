// Triage actions for one candidate work item, rendered inside Report 1's
// candidate work table.
//
// The report's own Status column is frozen at run time, so status is read
// live from GET /candidate-work instead -- a dismissal has to show
// immediately, not wait for the next run to regenerate the report text.
//
// One shared fetch, not one per row: the table renders this component once
// per item, and a module-level store means the list is fetched once and
// every row re-renders from it after any mutation.
import { useEffect, useState } from "react";
import { Check, CircleDot, Eye, Trash2, X } from "lucide-react";
import { api } from "../../api.js";
import { theme, FONT } from "../../theme.js";
import { Badge, Button, Spinner } from "../../components/atoms.jsx";

const STATUS_TONE = { new: "accent", under_review: "warning", accepted: "success", dismissed: "muted" };
const STATUS_LABEL = { new: "New", under_review: "Under review", accepted: "Accepted", dismissed: "Dismissed" };

// --- the shared store -----------------------------------------------------

let cache = null;
let inflight = null;
const listeners = new Set();

function publish() {
  for (const fn of listeners) fn(cache);
}

function load({ force = false } = {}) {
  if (inflight && !force) return inflight;
  inflight = api.techRegulation
    .listCandidateWork()
    .then((rows) => {
      cache = Array.isArray(rows) ? rows : [];
      publish();
      return cache;
    })
    .catch((e) => {
      cache = { error: e.message || "Couldn't load candidate work status." };
      publish();
      return cache;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

function useCandidateWork(key) {
  const [state, setState] = useState(cache);

  useEffect(() => {
    const fn = (next) => setState(next);
    listeners.add(fn);
    if (cache === null) load();
    return () => listeners.delete(fn);
  }, []);

  const error = state && !Array.isArray(state) ? state.error : "";
  const item = Array.isArray(state) ? state.find((r) => r.candidate_key === key) : null;
  return { item, error, loading: state === null, reload: () => load({ force: true }) };
}

// --- the component --------------------------------------------------------

export default function CandidateWorkActions({ candidateKey }) {
  const { item, error, loading, reload } = useCandidateWork(candidateKey);
  const [busy, setBusy] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState("");

  if (loading) return <div style={{ marginTop: 6 }}><Spinner size={12} /></div>;
  if (error) {
    return (
      <p style={{ margin: "6px 0 0", fontSize: 11, color: theme.danger }}>{error}</p>
    );
  }
  // An item in the report that no longer exists in the table: deleted since
  // the run. Say so rather than offering actions that would 404.
  if (!item) {
    return (
      <p style={{ margin: "6px 0 0", fontSize: 11, color: theme.textMuted, fontStyle: "italic" }}>
        No longer in the candidate work list — removed since this run.
      </p>
    );
  }

  async function setStatus(status, dismissalReason = "") {
    setBusy(true);
    setActionError("");
    try {
      await api.techRegulation.patchCandidateWork(candidateKey, {
        status,
        dismissal_reason: dismissalReason,
      });
      setDismissing(false);
      setReason("");
      await reload();
    } catch (e) {
      setActionError(e.message || "Couldn't update the item.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    // Delete and dismissal are genuinely different, and the difference bites
    // on the next run: persistence is keyed by candidate_key, so a deleted
    // item whose evidence still exists comes back as new. Say that here
    // rather than letting someone discover it next run.
    const ok = window.confirm(
      `Remove ${candidateKey} entirely?\n\nIf the evidence behind it still exists, the next run will surface it again as new. ` +
        `To suppress it durably, dismiss it with a reason instead — that survives re-discovery.`
    );
    if (!ok) return;
    setBusy(true);
    setActionError("");
    try {
      await api.techRegulation.deleteCandidateWork(candidateKey);
      await reload();
    } catch (e) {
      setActionError(e.message || "Couldn't remove the item.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
        <Badge tone={STATUS_TONE[item.status] || "muted"}>{STATUS_LABEL[item.status] || item.status}</Badge>

        {item.status !== "under_review" && (
          <Button small icon={Eye} disabled={busy} onClick={() => setStatus("under_review")}>
            Under review
          </Button>
        )}
        {item.status !== "accepted" && (
          <Button small icon={Check} disabled={busy} onClick={() => setStatus("accepted")}>
            Accept
          </Button>
        )}
        {item.status !== "dismissed" && (
          <Button small icon={X} disabled={busy} onClick={() => setDismissing((v) => !v)}>
            Dismiss
          </Button>
        )}
        {item.status === "dismissed" && (
          <Button small icon={CircleDot} disabled={busy} onClick={() => setStatus("new")}>
            Reopen
          </Button>
        )}
        <button
          title="Remove this item"
          disabled={busy}
          onClick={remove}
          style={{
            border: "none",
            background: "transparent",
            cursor: busy ? "default" : "pointer",
            padding: 4,
            display: "flex",
            alignItems: "center",
          }}
        >
          <Trash2 size={13} color={theme.textMuted} />
        </button>
      </div>

      {item.status === "dismissed" && item.dismissal_reason && (
        <p style={{ margin: "4px 0 0", fontSize: 11, color: theme.textMuted }}>
          Dismissed: {item.dismissal_reason}
        </p>
      )}

      {dismissing && (
        <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this not work? (required)"
            style={{
              flex: 1,
              minWidth: 220,
              fontFamily: FONT,
              fontSize: 12,
              padding: "5px 8px",
              border: `1px solid ${theme.border}`,
              borderRadius: 4,
              background: theme.surface,
              color: theme.textPrimary,
            }}
          />
          <Button small disabled={busy || !reason.trim()} onClick={() => setStatus("dismissed", reason.trim())}>
            Confirm
          </Button>
          <Button small onClick={() => setDismissing(false)}>
            Cancel
          </Button>
          <p style={{ margin: 0, fontSize: 10.5, color: theme.textMuted, flexBasis: "100%" }}>
            A reason is required: it is what makes the dismissal reviewable later, and the dismissal is
            what stops every future run surfacing this again.
          </p>
        </div>
      )}

      {actionError && <p style={{ margin: "4px 0 0", fontSize: 11, color: theme.danger }}>{actionError}</p>}
    </div>
  );
}
