import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api.js";
import { Spinner } from "../components/atoms.jsx";
import { theme } from "../theme.js";

// Landing route for the agent. No scope precondition, unlike Market
// Insights -- Part 6: "Run is always enabled."
export default function StrategySynthesisEntry() {
  const [dest, setDest] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const runs = await api.strategySynthesis.listRuns();
        if (cancelled) return;
        if (Array.isArray(runs) && runs.length > 0) {
          setDest(`/agents/strategy-synthesis/runs/${runs[0].id}`);
        } else {
          setDest("/agents/strategy-synthesis/workspace");
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
    return <div style={{ padding: "40px 32px", color: theme.danger, fontSize: 13 }}>{error}</div>;
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
