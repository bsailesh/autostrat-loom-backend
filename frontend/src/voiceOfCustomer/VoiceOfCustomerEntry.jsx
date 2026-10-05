import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api.js";
import { Spinner } from "../components/atoms.jsx";
import { theme } from "../theme.js";

// Landing route for the agent. No context precondition -- a run is never
// blocked: without evidence it degrades to Tier 2, so it lands on the
// workspace rather than being redirected to the context screen.
export default function VoiceOfCustomerEntry() {
  const [dest, setDest] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const runs = await api.voiceOfCustomer.listRuns();
        if (cancelled) return;
        setDest(
          Array.isArray(runs) && runs.length > 0
            ? `/agents/voice-of-customer/runs/${runs[0].id}`
            : "/agents/voice-of-customer/workspace"
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
