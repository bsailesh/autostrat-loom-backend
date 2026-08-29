import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ChevronDown, Play, Settings as SettingsIcon, RefreshCw, AlertTriangle, ChevronLeft } from "lucide-react";
import { api } from "../api.js";
import { theme } from "../theme.js";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { PageHeader } from "../components/PageHeader.jsx";
import { AGENT_NAME, REPORT_ORDER, reportLabel } from "./reportMeta.js";
import { isActiveStatus } from "./useMarketInsights.js";
import { relativeTime, absoluteTime, elapsedSince } from "../lib/time.js";
import ReportView from "./ReportView.jsx";

export default function Workspace() {
  const { runId, reportId } = useParams();
  const navigate = useNavigate();

  const [scope, setScope] = useState(undefined); // undefined = loading
  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState("");
  const [bootErr, setBootErr] = useState("");

  const [run, setRun] = useState(null); // full detail of the viewed run
  const [reports, setReports] = useState([]); // summaries for the viewed run
  const [reportsLoading, setReportsLoading] = useState(false);

  const [content, setContent] = useState({}); // reportId -> full report
  const [contentLoading, setContentLoading] = useState(false);

  const [starting, setStarting] = useState(false);
  const pollRef = useRef(null);

  // --- boot: scope + run list ---
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, r] = await Promise.all([api.getScope(), api.listRuns()]);
        if (cancelled) return;
        setScope(s);
        setRuns(Array.isArray(r) ? r : []);
      } catch (e) {
        if (!cancelled) setBootErr(e.message || "Couldn't load the workspace.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const latestRunId = runs[0]?.id || null;

  // --- load the viewed run's detail + report list ---
  const loadRun = useCallback(async (id) => {
    if (!id) return;
    setReportsLoading(true);
    try {
      const [detail, list] = await Promise.all([api.getRun(id), api.listRunReports(id)]);
      setRun(detail);
      setReports((Array.isArray(list) ? list : []).slice().sort((a, b) => a.report_number - b.report_number));
    } catch (e) {
      setRunsError(e.message || "Couldn't load this run.");
    } finally {
      setReportsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (runId) loadRun(runId);
  }, [runId, loadRun]);

  // --- poll while the viewed run is in flight ---
  useEffect(() => {
    const active = run && isActiveStatus(run.status) && run.id === runId;
    if (!active) return undefined;
    pollRef.current = setInterval(async () => {
      try {
        const detail = await api.getRun(run.id);
        setRun(detail);
        if (!isActiveStatus(detail.status)) {
          clearInterval(pollRef.current);
          if (detail.status === "succeeded") loadRun(detail.id);
          api.listRuns().then((r) => setRuns(Array.isArray(r) ? r : [])).catch(() => {});
        }
      } catch {
        /* keep last-known; next tick retries */
      }
    }, 6000);
    return () => clearInterval(pollRef.current);
  }, [run, runId, loadRun]);

  // --- selected report content ---
  const selectedSummary = useMemo(() => {
    if (!reports.length) return null;
    if (reportId) return reports.find((r) => r.id === reportId) || null;
    return reports.find((r) => r.report_number === 1) || reports[0];
  }, [reports, reportId]);

  useEffect(() => {
    const id = selectedSummary?.id;
    if (!id || content[id]) return;
    let cancelled = false;
    setContentLoading(true);
    api
      .getReport(id)
      .then((full) => {
        if (!cancelled) setContent((c) => ({ ...c, [id]: full }));
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setContentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSummary, content]);

  // --- run ---
  async function onRun() {
    setStarting(true);
    setRunsError("");
    try {
      const newRun = await api.startRun();
      setRuns((prev) => [newRun, ...prev.filter((x) => x.id !== newRun.id)]);
      navigate(`/agents/market-insights/runs/${newRun.id}`);
    } catch (e) {
      setRunsError(e.message || "Couldn't start the run.");
    } finally {
      setStarting(false);
    }
  }

  // --- routing guards ---
  if (bootErr) {
    return (
      <>
        <PageHeader title={AGENT_NAME} right={<HomeBtn navigate={navigate} />} />
        <Centered>
          <p style={{ color: theme.danger, fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
            <AlertTriangle size={14} /> {bootErr}
          </p>
        </Centered>
      </>
    );
  }
  if (scope === undefined) {
    return (
      <>
        <PageHeader title={AGENT_NAME} />
        <Centered>
          <Spinner size={20} />
        </Centered>
      </>
    );
  }
  if (!scope?.configured || !(scope.product_line || "").trim()) {
    return <Navigate to="/agents/market-insights/scope" replace />;
  }
  // On the param-less /workspace route: jump to the latest run if there is one.
  if (!runId && latestRunId) {
    return <Navigate to={`/agents/market-insights/runs/${latestRunId}`} replace />;
  }

  const viewedRun = runId ? run : null;
  const runActive = viewedRun && isActiveStatus(viewedRun.status);
  const runFailed = viewedRun && viewedRun.status === "failed";
  const anyRunActive = runs.some((r) => isActiveStatus(r.status));

  const fullReport = selectedSummary ? content[selectedSummary.id] : null;

  return (
    <>
      <PageHeader
        title={AGENT_NAME}
        subtitle={
          viewedRun
            ? `${viewedRun.status === "succeeded" ? "Run" : viewedRun.status} · ${relativeTime(viewedRun.created_at)}`
            : "No runs yet"
        }
        right={
          <>
            <RunHistoryMenu runs={runs} currentId={runId} onPick={(id) => navigate(`/agents/market-insights/runs/${id}`)} />
            <button
              title="Configure scope"
              onClick={() => navigate("/agents/market-insights/scope")}
              style={{ border: "none", background: "transparent", cursor: "pointer", padding: 6, display: "flex" }}
            >
              <SettingsIcon size={16} color={theme.textMuted} />
            </button>
            <Button
              small
              variant="primary"
              icon={starting || anyRunActive ? undefined : Play}
              disabled={starting || anyRunActive}
              onClick={onRun}
            >
              {starting ? "Starting…" : anyRunActive ? "Running…" : "Run"}
            </Button>
          </>
        }
      />

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <ReportSidebar
          reports={reports}
          selectedId={selectedSummary?.id}
          loading={reportsLoading}
          runActive={runActive}
          onPick={(id) => navigate(`/agents/market-insights/runs/${runId}/reports/${id}`)}
        />

        <div style={{ flex: 1, overflowY: "auto", padding: "28px 34px", minWidth: 0 }}>
          {runsError && (
            <p style={{ color: theme.danger, fontSize: 13, marginBottom: 14, display: "flex", gap: 6, alignItems: "center" }}>
              <AlertTriangle size={14} /> {runsError}
            </p>
          )}

          {!runId && !latestRunId ? (
            <EmptyRunState onRun={onRun} starting={starting} />
          ) : runActive ? (
            <RunningState run={viewedRun} />
          ) : runFailed ? (
            <FailedState run={viewedRun} onRetry={onRun} starting={starting} />
          ) : contentLoading && !fullReport ? (
            <Centered>
              <Spinner size={18} />
            </Centered>
          ) : fullReport ? (
            <ReportView report={fullReport} />
          ) : reportsLoading ? (
            <Centered>
              <Spinner size={18} />
            </Centered>
          ) : (
            <p style={{ fontSize: 13, color: theme.textMuted }}>No reports found for this run.</p>
          )}
        </div>
      </div>
    </>
  );
}

// ---------- pieces ----------

function HomeBtn({ navigate }) {
  return (
    <Button small variant="ghost" icon={ChevronLeft} onClick={() => navigate("/")}>
      Home
    </Button>
  );
}

function Centered({ children }) {
  return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>{children}</div>
  );
}

function ReportSidebar({ reports, selectedId, loading, runActive, onPick }) {
  const byNumber = new Map(reports.map((r) => [r.report_number, r]));
  return (
    <div
      style={{
        width: 236,
        borderRight: `1px solid ${theme.border}`,
        background: theme.surfaceMuted,
        padding: "18px 12px",
        overflowY: "auto",
        flexShrink: 0,
      }}
    >
      <p style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, textTransform: "uppercase", letterSpacing: 0.4, margin: "0 8px 10px" }}>
        Reports
      </p>
      {REPORT_ORDER.map((n) => {
        const summary = byNumber.get(n);
        const available = !!summary;
        const active = summary && summary.id === selectedId;
        return (
          <button
            key={n}
            disabled={!available}
            onClick={() => available && onPick(summary.id)}
            style={{
              display: "flex",
              gap: 8,
              alignItems: "baseline",
              width: "100%",
              textAlign: "left",
              padding: "7px 8px",
              borderRadius: 8,
              border: "none",
              marginBottom: 2,
              cursor: available ? "pointer" : "default",
              background: active ? "#fff" : "transparent",
              boxShadow: active ? `0 0 0 1px ${theme.border}` : "none",
              opacity: available ? 1 : 0.4,
            }}
          >
            <span style={{ fontSize: 11, color: theme.textMuted, width: 12, flexShrink: 0 }}>{n}</span>
            <span
              style={{
                fontSize: 12.5,
                fontWeight: active ? 700 : 500,
                color: active ? theme.textPrimary : theme.textSecondary,
                lineHeight: 1.4,
              }}
            >
              {reportLabel(n)}
            </span>
          </button>
        );
      })}
      {(loading || runActive) && (
        <p style={{ fontSize: 11, color: theme.textMuted, margin: "12px 8px 0", display: "flex", gap: 6, alignItems: "center" }}>
          <Spinner size={10} /> {runActive ? "Generating…" : "Loading…"}
        </p>
      )}
    </div>
  );
}

function RunHistoryMenu({ runs, currentId, onPick }) {
  const [open, setOpen] = useState(false);
  const current = runs.find((r) => r.id === currentId) || runs[0];
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 12,
          padding: "6px 10px",
          borderRadius: 8,
          border: `1px solid ${theme.border}`,
          background: theme.surface,
          cursor: "pointer",
          color: theme.textSecondary,
        }}
      >
        {current ? `${relativeTime(current.created_at)}` : "No runs"}
        <ChevronDown size={13} />
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            width: 320,
            maxHeight: 340,
            overflowY: "auto",
            background: theme.surface,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            boxShadow: "0 10px 30px rgba(0,0,0,0.12)",
            zIndex: 30,
            padding: 6,
          }}
        >
          <p style={{ fontSize: 11, color: theme.textMuted, margin: "4px 8px 6px", fontWeight: 700 }}>Run history</p>
          {runs.length === 0 && <p style={{ fontSize: 12, color: theme.textMuted, margin: 8 }}>No runs yet.</p>}
          {runs.map((r) => (
            <button
              key={r.id}
              onClick={() => {
                setOpen(false);
                onPick(r.id);
              }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "8px",
                borderRadius: 8,
                border: "none",
                cursor: "pointer",
                background: r.id === currentId ? theme.surfaceMuted : "transparent",
                marginBottom: 2,
              }}
            >
              <span style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12.5, color: theme.textPrimary }}>{absoluteTime(r.created_at)}</span>
                <RunStatusBadge status={r.status} />
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: theme.textMuted,
                  display: "block",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  marginTop: 2,
                }}
              >
                {r.subject}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RunStatusBadge({ status }) {
  if (status === "succeeded") return <Badge tone="success">Done</Badge>;
  if (status === "failed") return <Badge tone="danger">Failed</Badge>;
  return (
    <Badge tone="accent">
      <Spinner size={9} /> {status === "pending" ? "Queued" : "Running"}
    </Badge>
  );
}

function RunningState({ run }) {
  return (
    <div style={{ maxWidth: 460, padding: "32px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <Spinner size={18} />
        <p style={{ fontWeight: 700, fontSize: 16, margin: 0 }}>Research in progress</p>
      </div>
      <p style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, margin: "0 0 12px" }}>
        The agent is doing live web research and writing all nine reports. A full run typically takes
        <strong> 30–60 minutes</strong> — you can leave this page and come back; the run keeps going.
      </p>
      <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>
        Started {relativeTime(run.created_at)} · running {elapsedSince(run.created_at)}
      </p>
    </div>
  );
}

function FailedState({ run, onRetry, starting }) {
  return (
    <div style={{ maxWidth: 520, padding: "24px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <AlertTriangle size={18} color={theme.danger} />
        <p style={{ fontWeight: 700, fontSize: 16, margin: 0 }}>This run failed</p>
      </div>
      {run.error && (
        <pre
          style={{
            fontSize: 12,
            background: theme.dangerBg,
            color: theme.danger,
            padding: "10px 12px",
            borderRadius: 8,
            whiteSpace: "pre-wrap",
            margin: "0 0 14px",
          }}
        >
          {run.error}
        </pre>
      )}
      <Button variant="primary" icon={starting ? undefined : RefreshCw} disabled={starting} onClick={onRetry}>
        {starting ? "Starting…" : "Run again"}
      </Button>
    </div>
  );
}

function EmptyRunState({ onRun, starting }) {
  return (
    <div style={{ maxWidth: 460, padding: "32px 0" }}>
      <p style={{ fontWeight: 700, fontSize: 16, margin: "0 0 6px" }}>No reports yet</p>
      <p style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, margin: "0 0 16px" }}>
        Run the agent to generate your first set of nine Market Insights reports from the scope you configured.
      </p>
      <Button variant="primary" icon={starting ? undefined : Play} disabled={starting} onClick={onRun}>
        {starting ? "Starting…" : "Run Market Insights"}
      </Button>
    </div>
  );
}
