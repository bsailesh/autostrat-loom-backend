// Shared report workspace shell -- report list sidebar, top bar with run
// history + export, run polling, and the empty/running/failed states.
// Extracted from marketInsights/Workspace.jsx (Phase 5) so a second agent
// (Strategy Synthesis) can reuse it without duplicating ~500 lines. Every
// agent-specific bit -- API calls, routes, the agent's name/report list, an
// optional pre-run gate, and the ReportView component -- comes in via
// `adapter`, so this file has no knowledge of any one agent.
//
// adapter shape:
//   agentName: string
//   reportOrder: number[]                    // sidebar order, e.g. [1..9]
//   reportLabel(n): string
//   routes: {
//     configure?: string,                    // optional "gear icon" route
//     run(runId): string,
//     report(runId, reportId): string,
//   }
//   listReports(runId), getReport(reportId): Promise
//   listRuns(), getRun(runId), startRun(payload?): Promise
//   exportDocx?(runId): Promise<{blob, filename}>   // omit to hide the button
//   Gate?: React component accepting `{ children }`. Renders `children` (the
//          shell) once its own precondition is satisfied, or its own
//          blocking UI otherwise (e.g. a spinner while loading, or a
//          <Navigate/> to a "configure this first" screen -- Market
//          Insights' scope requirement). A plain wrapper component, so it
//          can use its own hooks/state without breaking Rules of Hooks.
//   ReportView: React component, given `{ report }`
//   emptyStateCopy?: { title, body, cta }     // shown when there are no runs yet
//   runningStateCopy?: { title, body }        // shown while a run is in flight
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { ChevronDown, Play, Settings as SettingsIcon, RefreshCw, AlertTriangle, ChevronLeft, Download } from "lucide-react";
import { theme } from "../theme.js";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { PageHeader } from "../components/PageHeader.jsx";
import { relativeTime, absoluteTime, elapsedSince } from "../lib/time.js";

const isActiveStatus = (s) => s === "pending" || s === "running";

export default function ReportWorkspaceShell({ adapter }) {
  const Gate = adapter.Gate;
  const shell = <ReportWorkspaceContent adapter={adapter} />;
  return Gate ? <Gate>{shell}</Gate> : shell;
}

function ReportWorkspaceContent({ adapter }) {
  const { runId, reportId } = useParams();
  const navigate = useNavigate();

  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState("");
  const [bootErr, setBootErr] = useState("");

  const [run, setRun] = useState(null); // full detail of the viewed run
  const [reports, setReports] = useState([]); // summaries for the viewed run
  const [reportsLoading, setReportsLoading] = useState(false);

  const [content, setContent] = useState({}); // reportId -> full report
  const [contentLoading, setContentLoading] = useState(false);

  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const pollRef = useRef(null);

  // --- boot: run list ---
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await adapter.listRuns();
        if (cancelled) return;
        setRuns(Array.isArray(r) ? r : []);
      } catch (e) {
        if (!cancelled) setBootErr(e.message || "Couldn't load the workspace.");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const latestRunId = runs[0]?.id || null;

  // --- load the viewed run's detail + report list ---
  const loadRun = useCallback(
    async (id) => {
      if (!id) return;
      setReportsLoading(true);
      try {
        const [detail, list] = await Promise.all([adapter.getRun(id), adapter.listReports(id)]);
        setRun(detail);
        setReports((Array.isArray(list) ? list : []).slice().sort((a, b) => a.report_number - b.report_number));
      } catch (e) {
        setRunsError(e.message || "Couldn't load this run.");
      } finally {
        setReportsLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    if (runId) loadRun(runId);
  }, [runId, loadRun]);

  // --- poll while the viewed run is in flight ---
  useEffect(() => {
    const active = run && isActiveStatus(run.status) && run.id === runId;
    if (!active) return undefined;
    pollRef.current = setInterval(async () => {
      try {
        const detail = await adapter.getRun(run.id);
        setRun(detail);
        if (!isActiveStatus(detail.status)) {
          clearInterval(pollRef.current);
          if (detail.status === "succeeded") loadRun(detail.id);
          adapter
            .listRuns()
            .then((r) => setRuns(Array.isArray(r) ? r : []))
            .catch(() => {});
        }
      } catch {
        /* keep last-known; next tick retries */
      }
    }, 6000);
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    adapter
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSummary, content]);

  // --- run ---
  async function onRun() {
    setStarting(true);
    setRunsError("");
    try {
      const newRun = await adapter.startRun();
      setRuns((prev) => [newRun, ...prev.filter((x) => x.id !== newRun.id)]);
      navigate(adapter.routes.run(newRun.id));
    } catch (e) {
      setRunsError(e.message || "Couldn't start the run.");
    } finally {
      setStarting(false);
    }
  }

  // --- export full report pack ---
  async function onExport() {
    if (!runId || !adapter.exportDocx) return;
    setExporting(true);
    setExportError("");
    try {
      const { blob, filename } = await adapter.exportDocx(runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(e.message || "Couldn't export the report pack.");
    } finally {
      setExporting(false);
    }
  }

  // --- routing guards ---
  if (bootErr) {
    return (
      <>
        <PageHeader title={adapter.agentName} right={<HomeBtn navigate={navigate} />} />
        <Centered>
          <p style={{ color: theme.danger, fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
            <AlertTriangle size={14} /> {bootErr}
          </p>
        </Centered>
      </>
    );
  }
  // On the param-less workspace route: jump to the latest run if there is one.
  if (!runId && latestRunId) {
    return <Navigate to={adapter.routes.run(latestRunId)} replace />;
  }

  const viewedRun = runId ? run : null;
  const runActive = viewedRun && isActiveStatus(viewedRun.status);
  const runFailed = viewedRun && viewedRun.status === "failed";
  const anyRunActive = runs.some((r) => isActiveStatus(r.status));

  const fullReport = selectedSummary ? content[selectedSummary.id] : null;
  const ReportView = adapter.ReportView;

  return (
    <>
      <PageHeader
        title={adapter.agentName}
        subtitle={
          viewedRun
            ? `${viewedRun.status === "succeeded" ? "Run" : viewedRun.status} · ${relativeTime(viewedRun.created_at)}`
            : "No runs yet"
        }
        right={
          <>
            <RunHistoryMenu runs={runs} currentId={runId} onPick={(id) => navigate(adapter.routes.run(id))} />
            {adapter.routes.configure && (
              <button
                title="Configure"
                onClick={() => navigate(adapter.routes.configure)}
                style={{ border: "none", background: "transparent", cursor: "pointer", padding: 6, display: "flex" }}
              >
                <SettingsIcon size={16} color={theme.textMuted} />
              </button>
            )}
            {adapter.exportDocx && viewedRun && viewedRun.status === "succeeded" && (
              <Button
                small
                variant="ghost"
                title="Export the full report pack as a Word document (not just the report you're viewing)"
                icon={exporting ? undefined : Download}
                disabled={exporting}
                onClick={onExport}
              >
                {exporting ? "Exporting…" : "Export .docx"}
              </Button>
            )}
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
          reportOrder={adapter.reportOrder}
          reportLabel={adapter.reportLabel}
          reports={reports}
          selectedId={selectedSummary?.id}
          loading={reportsLoading}
          runActive={runActive}
          onPick={(id) => navigate(adapter.routes.report(runId, id))}
        />

        <div style={{ flex: 1, overflowY: "auto", padding: "28px 34px", minWidth: 0 }}>
          {runsError && (
            <p style={{ color: theme.danger, fontSize: 13, marginBottom: 14, display: "flex", gap: 6, alignItems: "center" }}>
              <AlertTriangle size={14} /> {runsError}
            </p>
          )}
          {exportError && (
            <p style={{ color: theme.danger, fontSize: 13, marginBottom: 14, display: "flex", gap: 6, alignItems: "center" }}>
              <AlertTriangle size={14} /> {exportError}
            </p>
          )}

          {!runId && !latestRunId ? (
            <EmptyRunState onRun={onRun} starting={starting} copy={adapter.emptyStateCopy} />
          ) : runActive ? (
            <RunningState run={viewedRun} copy={adapter.runningStateCopy} />
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

function ReportSidebar({ reportOrder, reportLabel, reports, selectedId, loading, runActive, onPick }) {
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
      {reportOrder.map((n) => {
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

function RunningState({ run, copy }) {
  const title = copy?.title || "Generating reports";
  const body = copy?.body || "The agent is working. You can leave this page and come back — the run keeps going.";
  return (
    <div style={{ maxWidth: 460, padding: "32px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <Spinner size={18} />
        <p style={{ fontWeight: 700, fontSize: 16, margin: 0 }}>{title}</p>
      </div>
      <p style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, margin: "0 0 12px" }}>{body}</p>
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

function EmptyRunState({ onRun, starting, copy }) {
  const title = copy?.title || "No reports yet";
  const body = copy?.body || "Run the agent to generate your first set of reports.";
  const cta = copy?.cta || "Run";
  return (
    <div style={{ maxWidth: 460, padding: "32px 0" }}>
      <p style={{ fontWeight: 700, fontSize: 16, margin: "0 0 6px" }}>{title}</p>
      <p style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.6, margin: "0 0 16px" }}>{body}</p>
      <Button variant="primary" icon={starting ? undefined : Play} disabled={starting} onClick={onRun}>
        {starting ? "Starting…" : cta}
      </Button>
    </div>
  );
}
