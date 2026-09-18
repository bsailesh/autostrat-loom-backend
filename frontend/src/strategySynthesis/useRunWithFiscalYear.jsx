// Wraps a startRun call so an ambiguous fiscal year is resolved by asking
// before the run starts, rather than surfacing POST /runs' 400
// (AmbiguousFiscalYearError) as a raw error/alert mid-demo. Used by both
// the home dashboard's Run button and the workspace's own -- fiscal-year
// selection is Strategy Synthesis-specific, so this lives here, not in the
// shared reportWorkspace/ shell.
import { useCallback, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "../api.js";
import { theme, FONT } from "../theme.js";
import { Button } from "../components/atoms.jsx";

// Distinct from a real failure -- callers can check `err.message ===
// CANCELLED_MESSAGE` to skip showing it as an error (e.g. not worth an
// alert()).
export const CANCELLED_MESSAGE = "Run cancelled -- no fiscal year chosen.";

export function useRunWithFiscalYear(startRun) {
  const [prompt, setPrompt] = useState(null); // { years, resolve, reject } | null

  const run = useCallback(
    async (payload = {}) => {
      if (payload.fiscal_year) return startRun(payload);

      let years = [];
      try {
        years = await api.strategySynthesis.getFiscalYears();
      } catch {
        // Lookup failed -- fall through to the old behavior (server decides
        // or 400s) rather than blocking Run on this being unavailable.
      }
      if (years.length <= 1) return startRun(payload);

      return new Promise((resolve, reject) => {
        setPrompt({ years: [...years].sort(), payload, resolve, reject });
      });
    },
    [startRun]
  );

  function onConfirm(fiscalYear) {
    const { payload, resolve, reject } = prompt;
    setPrompt(null);
    startRun({ ...payload, fiscal_year: fiscalYear }).then(resolve, reject);
  }
  function onCancel() {
    prompt.reject(new Error(CANCELLED_MESSAGE));
    setPrompt(null);
  }

  const modal = prompt ? <FiscalYearModal years={prompt.years} onConfirm={onConfirm} onCancel={onCancel} /> : null;

  return { run, modal };
}

function FiscalYearModal({ years, onConfirm, onCancel }) {
  const [selected, setSelected] = useState(years[0]);
  return (
    <div
      // Stops a click anywhere in the modal (Cancel, the select, Run)
      // bubbling up to an ancestor's own onClick -- e.g. the home
      // dashboard's card, whose onClick navigates to the workspace, would
      // otherwise fire on every click here since this modal renders as
      // that card's React child even though it's visually a fixed overlay.
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20, 20, 20, 0.35)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 200,
      }}
    >
      <div style={{ background: theme.surface, borderRadius: 14, padding: "22px 24px", width: 380, boxShadow: "0 20px 60px rgba(0,0,0,0.25)" }}>
        <p style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 15, margin: "0 0 6px", color: theme.textPrimary }}>
          <AlertTriangle size={16} color={theme.warning} /> Which fiscal year?
        </p>
        <p style={{ fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.5, margin: "0 0 16px" }}>
          Capacity data covers more than one fiscal year ({years.join(", ")}). Pick the one this run should analyze
          -- capacity, utilisation and bottlenecks are computed against it specifically.
        </p>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          style={{
            fontFamily: FONT,
            fontSize: 13,
            padding: "7px 10px",
            borderRadius: 7,
            border: `1px solid ${theme.border}`,
            width: "100%",
            marginBottom: 18,
          }}
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
              {y === years[0] ? " (earliest)" : ""}
            </option>
          ))}
        </select>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button small variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button small variant="primary" onClick={() => onConfirm(selected)}>
            Run {selected}
          </Button>
        </div>
      </div>
    </div>
  );
}
