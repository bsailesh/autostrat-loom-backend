import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, Target } from "lucide-react";
import { api } from "../api.js";
import { theme, FONT } from "../theme.js";
import { Button, Spinner } from "../components/atoms.jsx";
import { PageHeader } from "../components/PageHeader.jsx";
import { FormError } from "../auth/AuthShell.jsx";

export default function ConfigureScope() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [existing, setExisting] = useState(false);
  const [productLine, setProductLine] = useState("");
  const [competitors, setCompetitors] = useState("");
  const [geography, setGeography] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const scope = await api.getScope();
        if (cancelled) return;
        if (scope?.configured) {
          setExisting(true);
          setProductLine(scope.product_line || "");
          setCompetitors(scope.competitors || "");
          setGeography(scope.geography || "");
        }
      } catch (e) {
        if (!cancelled) setError(e.message || "Couldn't load the current scope.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Mirror the backend's own rule: product_line must be non-empty.
  const canSave = productLine.trim().length > 0 && !saving;

  async function onSave(e) {
    e.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError("");
    try {
      await api.putScope({
        product_line: productLine.trim(),
        competitors: competitors.trim(),
        geography: geography.trim(),
      });
      navigate("/agents/market-insights", { replace: true });
    } catch (err) {
      setError(err.message || "Couldn't save the scope.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title={existing ? "Configure scope" : "Set up Market Insights"}
        subtitle="Market Insights"
        right={
          <Button small variant="ghost" icon={ChevronLeft} onClick={() => navigate("/")}>
            Home
          </Button>
        }
      />
      <div style={{ padding: "28px 32px", overflowY: "auto" }}>
        {loading ? (
          <Spinner size={18} />
        ) : (
          <div style={{ maxWidth: 560 }}>
            <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 20 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: theme.orangeSoft,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Target size={19} color={theme.orange} />
              </div>
              <div>
                <p style={{ fontWeight: 600, fontSize: 15, margin: "0 0 4px" }}>
                  What should this agent watch?
                </p>
                <p style={{ fontSize: 13, color: theme.textSecondary, margin: 0, lineHeight: 1.5 }}>
                  The agent researches this scope continuously — every run works from what you set here.
                  You can update it any time from the agent card.
                </p>
              </div>
            </div>

            <form onSubmit={onSave}>
              <FormError>{error}</FormError>

              <ScopeField
                label="Product line / market focus"
                required
                textarea
                rows={4}
                value={productLine}
                onChange={setProductLine}
                placeholder="e.g. Battery-electric propulsion systems for coastal and inland ferries under 40m — including the drivetrain, energy storage, and shore-charging interface. Focus on newbuild and retrofit."
                note="Required. The more specific you are — segment, vessel class, sub-systems, buyer type — the sharper the reports."
              />
              <ScopeField
                label="Known competitors"
                textarea
                rows={2}
                value={competitors}
                onChange={setCompetitors}
                placeholder="e.g. Corvus Energy, Leclanché, EST-Floattech, Echandia"
                note="Optional. One per line or comma-separated."
              />
              <ScopeField
                label="Geographic focus"
                value={geography}
                onChange={setGeography}
                placeholder="e.g. Northern Europe and North America"
                note="Optional."
              />

              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                <Button type="submit" variant="primary" disabled={!canSave}>
                  {saving ? "Saving…" : existing ? "Save changes" : "Save and continue"}
                </Button>
                {existing && (
                  <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
                    Cancel
                  </Button>
                )}
              </div>
              {productLine.trim().length === 0 && (
                <p style={{ fontSize: 11, color: theme.textMuted, margin: "10px 0 0" }}>
                  Add a product line to continue.
                </p>
              )}
            </form>
          </div>
        )}
      </div>
    </>
  );
}

function ScopeField({ label, required, textarea, rows = 3, value, onChange, placeholder, note }) {
  const shared = {
    width: "100%",
    fontFamily: FONT,
    fontSize: 14,
    padding: "9px 11px",
    borderRadius: 8,
    border: `1px solid ${theme.border}`,
    background: "#fff",
    color: theme.textPrimary,
    outline: "none",
    resize: textarea ? "vertical" : "none",
    lineHeight: 1.5,
  };
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ fontSize: 12, color: theme.textMuted, display: "block", marginBottom: 5 }}>
        {label}
        {required && <span style={{ color: theme.orange }}> *</span>}
      </label>
      {textarea ? (
        <textarea rows={rows} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} style={shared} />
      ) : (
        <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} style={shared} />
      )}
      {note && <p style={{ fontSize: 11, color: theme.textMuted, margin: "5px 0 0", lineHeight: 1.5 }}>{note}</p>}
    </div>
  );
}
