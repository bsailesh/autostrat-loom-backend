import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export const isActiveStatus = (s) => s === "pending" || s === "running";

// Run list plus operating tier, with polling while a run is in flight.
// Shared by the home card and the entry route.
//
// No "configured" gate: a run is never blocked. Without BOM matrices it is an
// obsolescence and exposure scan, titled as such. The tier is loaded here so
// the run button can say so before such a run rather than only after.
export function useProductSustainmentStatus({ poll = true } = {}) {
  const [runs, setRuns] = useState([]);
  const [readiness, setReadiness] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([
        api.productSustainment.listRuns(),
        api.productSustainment.getReadiness().catch(() => null),
      ]);
      setRuns(Array.isArray(r) ? r : []);
      setReadiness(s);
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
        const r = await api.productSustainment.listRuns();
        setRuns(Array.isArray(r) ? r : []);
      } catch {
        /* keep last-known state; next tick retries */
      }
    }, 6000);
    return () => clearInterval(timer.current);
  }, [poll, active]);

  const startRun = useCallback(async (payload) => {
    const run = await api.productSustainment.startRun(payload);
    setRuns((prev) => [run, ...prev.filter((x) => x.id !== run.id)]);
    return run;
  }, []);

  return {
    runs,
    latestRun,
    active,
    loading,
    error,
    operatingTier: readiness?.operating_tier || null,
    readiness,
    reload: load,
    startRun,
  };
}
