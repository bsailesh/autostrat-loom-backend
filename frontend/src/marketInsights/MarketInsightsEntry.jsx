import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api.js";
import { Spinner } from "../components/atoms.jsx";
import { theme } from "../theme.js";

// Landing route for the agent. Decides where the user actually belongs:
//  - no scope yet            -> Configure Scope (the briefing's first-time gate)
//  - scope, has runs         -> newest run's workspace
//  - scope, no runs          -> workspace in its empty/"Run to begin" state
export default function MarketInsightsEntry() {
  const [dest, setDest] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [scope, runs] = await Promise.all([api.getScope(), api.listRuns()]);
        if (cancelled) return;
        if (!scope?.configured || !(scope.product_line || "").trim()) {
          setDest("/agents/market-insights/scope");
        } else if (Array.isArray(runs) && runs.length > 0) {
          setDest(`/agents/market-insights/runs/${runs[0].id}`);
        } else {
          setDest("/agents/market-insights/workspace");
        }
      } catch (e) {
        if (!cancelled) setError(e.message || "Couldn't load the agent.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div style={{ padding: "40px 32px", color: theme.danger, fontSize: 13 }}>{error}</div>
    );
  }
  if (!dest) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spinner size={20} />
      </div>
    );
  }
  return <Navigate to={dest} replace />;
}
