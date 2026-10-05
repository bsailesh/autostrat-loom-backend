// Customer context: segments, known pain points, channels, named customers,
// attribution policy and product categories. Each section shows its status
// and, only when missing, what that absence costs -- taken verbatim from
// /context/state, which already sends "" for anything set (b4f3282).
//
// What the briefing is specific about, and this screen implements:
//  1. The OPERATING TIER is shown prominently at the top, with what Tier 2
//     means: an external customer-context analysis, not voice of customer.
//  2. KNOWN PAIN POINTS is emphasised. It is the field a customer is least
//     likely to think to fill, and belief testing -- the most valuable
//     thing this agent does -- is unavailable without it.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Badge, Button, Spinner } from "../components/atoms.jsx";
import { FONT, theme } from "../theme.js";
import { ATTRIBUTION_POLICIES, CONTEXT_SECTIONS, TIER_COPY } from "./reportMeta.js";
import { RowsEditor, SectionCard } from "./RowsEditor.jsx";

// Stable references, so RowsEditor's load effect runs once per section.
const LOADERS = Object.fromEntries(
  CONTEXT_SECTIONS.map((s) => [s.section, () => api.voiceOfCustomer.getContext(s.section)])
);
const SAVERS = Object.fromEntries(
  CONTEXT_SECTIONS.map((s) => [s.section, (rows) => api.voiceOfCustomer.putContext(s.section, rows)])
);

const CATEGORY_FIELDS = [
  { name: "category_key", label: "Key", placeholder: "SVC-TOOL", width: 110 },
  { name: "category_name", label: "Name", placeholder: "Service tooling", width: 200 },
  { name: "description", label: "Description", placeholder: "", grow: true },
];
const loadAdditions = async () =>
  (await api.voiceOfCustomer.getContext("categories")).filter((c) => c.source === "voice-of-customer");
const saveAdditions = (rows) => api.voiceOfCustomer.putContext("categories", rows);

export function TierBanner({ state, compact = false }) {
  const copy = TIER_COPY[state?.operating_tier];
  if (!copy) return null;
  const border = copy.tone === "success" ? theme.success : copy.tone === "warning" ? theme.warning : theme.danger;
  const bg = copy.tone === "success" ? theme.successBg : copy.tone === "warning" ? theme.warningBg : theme.dangerBg;
  return (
    <div style={{ border: `1px solid ${border}`, background: bg, borderRadius: 8, padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: theme.textSecondary }}>
          Operating tier
        </span>
        <Badge tone={copy.tone}>{copy.label}</Badge>
      </div>
      <p style={{ margin: "7px 0 0", fontSize: 13, color: theme.textPrimary, lineHeight: 1.55 }}>{copy.note}</p>
      {!compact && state.analyses?.length > 0 && (
        <ul style={{ margin: "10px 0 0", padding: 0, listStyle: "none", fontSize: 12, lineHeight: 1.7 }}>
          {state.analyses.map((a) => (
            <li key={a.key} style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
              {a.available ? (
                <Check size={13} color={theme.success} style={{ marginTop: 3, flexShrink: 0 }} />
              ) : (
                <X size={13} color={theme.textMuted} style={{ marginTop: 3, flexShrink: 0 }} />
              )}
              <span style={{ color: theme.textSecondary }}>
                <strong style={{ color: theme.textPrimary }}>{a.label}</strong>
                {a.available && a.enabled_by.length > 0 && <> — from {a.enabled_by.join(", ")}</>}
                {a.note && <> — {a.note}</>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p style={{ margin: "10px 0 0", fontSize: 11.5, color: theme.textMuted }}>
        A run is never blocked. It degrades, and states its tier in the first line of every report.
      </p>
    </div>
  );
}

function AttributionPolicy({ onSaved }) {
  const [policy, setPolicy] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.voiceOfCustomer
      .getContext("config")
      .then((c) => setPolicy(c.attribution_policy))
      .catch((e) => setError(e.message || "Couldn't load the policy."));
  }, []);

  async function choose(value) {
    setError("");
    try {
      const saved = await api.voiceOfCustomer.putContext("config", { attribution_policy: value });
      setPolicy(saved.attribution_policy);
      onSaved();
    } catch (e) {
      setError(e.message || "Couldn't save the policy.");
    }
  }

  return (
    <SectionCard
      title="Attribution policy"
      blurb="How customers may appear in the reports. After every report is written, it is checked against your named customers and any CSV column mapped as customer, and matches are replaced with a segment label. That is a check, not a guarantee: it cannot catch a name it was never given, a programme unique to one customer, or a quotation someone would recognise."
    >
      {policy === null && !error ? (
        <Spinner size={14} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {ATTRIBUTION_POLICIES.map((p) => (
            <label key={p.value} style={{ display: "flex", gap: 8, alignItems: "flex-start", cursor: "pointer", fontSize: 12.5 }}>
              <input type="radio" name="attribution" checked={policy === p.value} onChange={() => choose(p.value)} />
              <span>
                <strong style={{ color: theme.textPrimary }}>{p.label}</strong>
                <span style={{ color: theme.textSecondary }}> — {p.example}</span>
              </span>
            </label>
          ))}
        </div>
      )}
      {error && <p style={{ fontSize: 11, color: theme.danger, margin: "8px 0 0" }}>{error}</p>}
    </SectionCard>
  );
}

function Categories({ item, onSaved }) {
  const [readThrough, setReadThrough] = useState(null);
  const loadReadThrough = useCallback(async () => {
    try {
      const all = await api.voiceOfCustomer.getContext("categories");
      setReadThrough(all.filter((c) => c.source === "tech-regulation"));
    } catch {
      setReadThrough([]);
    }
  }, []);
  useEffect(() => {
    loadReadThrough();
  }, [loadReadThrough]);

  return (
    <SectionCard
      title="Product categories"
      item={item}
      blurb="Which product a piece of feedback is about. Categories already declared for Technology & Regulation are read through here rather than asked for twice; add only what is specific to customer feedback."
    >
      <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: theme.textMuted }}>
        From Technology &amp; Regulation
      </p>
      {readThrough === null ? (
        <Spinner size={14} />
      ) : readThrough.length === 0 ? (
        <p style={{ margin: "0 0 10px", fontSize: 12, color: theme.textMuted, fontStyle: "italic" }}>
          None declared there yet.
        </p>
      ) : (
        <ul style={{ margin: "0 0 12px", paddingLeft: 18, fontSize: 12.5, color: theme.textPrimary, lineHeight: 1.6 }}>
          {readThrough.map((c) => (
            <li key={c.category_key}>
              <strong>{c.category_key}</strong> — {c.category_name}
            </li>
          ))}
        </ul>
      )}
      <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: theme.textMuted }}>
        Additions for Voice of Customer
      </p>
      <RowsEditor fields={CATEGORY_FIELDS} load={loadAdditions} save={saveAdditions} onSaved={onSaved} />
    </SectionCard>
  );
}

export default function ContextScreen() {
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [error, setError] = useState("");

  const loadState = useCallback(async () => {
    try {
      setState(await api.voiceOfCustomer.getContextState());
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load the context state.");
    }
  }, []);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const byKey = Object.fromEntries((state?.items || []).map((i) => [i.key, i]));

  return (
    <div style={{ padding: "28px 32px 48px", overflowY: "auto", background: theme.bg, flex: 1 }}>
      <div style={{ maxWidth: 1000 }}>
        <button
          onClick={() => navigate("/agents/voice-of-customer")}
          style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: theme.textMuted, fontFamily: FONT, marginBottom: 10 }}
        >
          <ArrowLeft size={13} /> Back to the agent
        </button>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>Customer context</h1>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: theme.textSecondary, maxWidth: 680, lineHeight: 1.55 }}>
              Who your customers are, so evidence can be attributed. Roughly fifteen minutes. Context alone produces an
              external customer-context analysis; the customer voice itself comes from evidence you upload.
            </p>
          </div>
          <Button icon={ArrowRight} onClick={() => navigate("/agents/voice-of-customer/evidence")}>
            Evidence
          </Button>
        </div>

        {error && (
          <p style={{ marginTop: 12, fontSize: 12, color: theme.danger, display: "flex", gap: 6, alignItems: "center" }}>
            <AlertTriangle size={13} /> {error}
          </p>
        )}

        {state && (
          <div style={{ margin: "18px 0 22px" }}>
            <TierBanner state={state} />
          </div>
        )}

        {CONTEXT_SECTIONS.map((s) => (
          <SectionCard
            key={s.key}
            title={s.title}
            blurb={s.blurb}
            emphasis={s.emphasis}
            item={s.stateKey ? byKey[s.stateKey] : undefined}
          >
            <RowsEditor fields={s.fields} load={LOADERS[s.section]} save={SAVERS[s.section]} onSaved={loadState} />
          </SectionCard>
        ))}

        <AttributionPolicy onSaved={loadState} />
        <Categories item={byKey.products} onSaved={loadState} />
      </div>
    </div>
  );
}
