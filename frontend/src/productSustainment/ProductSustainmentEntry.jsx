import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api.js";
import { Spinner } from "../components/atoms.jsx";
import { theme } from "../theme.js";

// Landing route for the agent. No structure precondition -- a run is never
// blocked: without a BOM it is an obsolescence and exposure scan, so it lands
// on the workspace rather than being redirected to the structure screen.
export default function ProductSustainmentEntry() {
  const [dest, setDest] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const runs = await api.productSustainment.listRuns();
        if (cancelled) return;
        setDest(
          Array.isArray(runs) && runs.length > 0
            ? `/agents/product-sustainment/runs/${runs[0].id}`
            : "/agents/product-sustainment/workspace"
        );
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
