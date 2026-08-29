import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const TERMINAL = new Set(["succeeded", "failed"]);
export const isActiveStatus = (s) => s === "pending" || s === "running";

// Scope + run list for the Market Insights agent, with polling while a run is
// in flight. Shared by the home card and the report workspace.
export function useMarketInsightsStatus({ poll = true } = {}) {
  const [scope, setScope] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([api.getScope(), api.listRuns()]);
      setScope(s);
      setRuns(Array.isArray(r) ? r : []);
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
        const r = await api.listRuns();
        setRuns(Array.isArray(r) ? r : []);
      } catch {
        /* keep last-known state; next tick retries */
      }
    }, 6000);
    return () => clearInterval(timer.current);
  }, [poll, active]);

  const configured = !!(scope && scope.configured && (scope.product_line || "").trim());

  const startRun = useCallback(async () => {
    const run = await api.startRun();
    setRuns((prev) => [run, ...prev.filter((x) => x.id !== run.id)]);
    return run;
  }, []);

  return { scope, configured, runs, latestRun, active, loading, error, reload: load, startRun };
}

export { TERMINAL };
