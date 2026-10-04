import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export const isActiveStatus = (s) => s === "pending" || s === "running";

// Run list plus operating state, with polling while a run is in flight.
// Shared by the home card, the entry route and the scope screen.
//
// Unlike Market Insights there is no "configured" gate: a run is never
// blocked by incomplete scoping, it degrades and says so. The operating
// state is therefore informational, not a precondition -- but it is loaded
// here so the run button can warn before an unscoped run rather than after.
export function useTechRegulationStatus({ poll = true } = {}) {
  const [runs, setRuns] = useState([]);
  const [scopeState, setScopeState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([
        api.techRegulation.listRuns(),
        api.techRegulation.getScopeState().catch(() => null),
      ]);
      setRuns(Array.isArray(r) ? r : []);
      setScopeState(s);
      setError("");
    } catch (e) {
      setError(e.message || "Failed to load agent status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const latestRun = runs[0] || null;
  const active = !!latestRun && isActiveStatus(latestRun.status);

  useEffect(() => {
    if (!poll || !active) return undefined;
    timer.current = setInterval(async () => {
      try {
        const r = await api.techRegulation.listRuns();
        setRuns(Array.isArray(r) ? r : []);
      } catch {
        /* keep last-known state; next tick retries */
      }
    }, 6000);
    return () => clearInterval(timer.current);
  }, [poll, active]);

  const startRun = useCallback(async (payload) => {
    const run = await api.techRegulation.startRun(payload);
    setRuns((prev) => [run, ...prev.filter((x) => x.id !== run.id)]);
    return run;
  }, []);

  return {
    runs,
    latestRun,
    active,
    loading,
    error,
    operatingState: scopeState?.operating_state || null,
    scopeState,
    reload: load,
    startRun,
  };
}
