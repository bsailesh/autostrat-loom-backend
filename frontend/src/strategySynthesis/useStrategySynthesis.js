import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export const isActiveStatus = (s) => s === "pending" || s === "running";

// Run list for Strategy Synthesis, with polling while a run is in flight.
// No scope/configured concept here -- Part 6: "Run is always enabled."
// Shared by the home card and (indirectly, via reload after a run
// completes) the report workspace.
export function useStrategySynthesisStatus({ poll = true } = {}) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await api.strategySynthesis.listRuns();
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
        const r = await api.strategySynthesis.listRuns();
        setRuns(Array.isArray(r) ? r : []);
      } catch {
        /* keep last-known state; next tick retries */
      }
    }, 6000);
    return () => clearInterval(timer.current);
  }, [poll, active]);

  const startRun = useCallback(async (payload) => {
    const run = await api.strategySynthesis.startRun(payload);
    setRuns((prev) => [run, ...prev.filter((x) => x.id !== run.id)]);
    return run;
  }, []);

  return { runs, latestRun, active, loading, error, reload: load, startRun };
}
