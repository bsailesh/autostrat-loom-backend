import { useNavigate } from "react-router-dom";
import {
  MessageCircle,
  LineChart,
  FlaskConical,
  Wrench,
  Sparkles,
  Play,
  Plus,
  Settings as SettingsIcon,
  AlertTriangle,
} from "lucide-react";
import { theme } from "../theme.js";
import { Badge, Button, Card, Spinner } from "../components/atoms.jsx";
import { PageHeader } from "../components/PageHeader.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
import { useMarketInsightsStatus } from "../marketInsights/useMarketInsights.js";
import { useStrategySynthesisStatus } from "../strategySynthesis/useStrategySynthesis.js";
import { relativeTime } from "../lib/time.js";

// Only Market Insights has a backend. The rest render in the reference's
// "Not subscribed" state and are intentionally inert.
const PLACEHOLDER_AGENTS = [
  { id: "voc", name: "Voice of customer", icon: MessageCircle, blurb: "Ranked pain points, personas, opportunity map" },
  { id: "tech", name: "Tech & regulation", icon: FlaskConical, blurb: "Patents, research and growth-tech visibility" },
  { id: "sustainment", name: "Product sustainment", icon: Wrench, blurb: "Quality, obsolescence and reliability needs" },
];

export default function HomeDashboard() {
  const { session } = useAuth();
  const mi = useMarketInsightsStatus();
  const strategy = useStrategySynthesisStatus();

  return (
    <>
      <PageHeader title="Home" subtitle={session?.tenant_name} />
      <div style={{ padding: "24px 28px", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16 }}>
          <div>
            <p style={{ fontWeight: 700, fontSize: 18, margin: "0 0 2px" }}>Your agents</p>
            <p style={{ fontSize: 13, color: theme.textSecondary, margin: 0 }}>Complexity in. Clarity out.</p>
          </div>
          <p style={{ fontSize: 13, color: theme.textMuted, margin: 0 }}>1 of 4 active</p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, maxWidth: 720 }}>
          <MarketInsightsCard mi={mi} />
          {PLACEHOLDER_AGENTS.map((def) => (
            <NotSubscribedCard key={def.id} def={def} />
          ))}
        </div>

        <StrategySynthesisCard strategy={strategy} />
      </div>
    </>
  );
}

function CardHeader({ Icon, right }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
      <Icon size={19} color={theme.textSecondary} />
      {right}
    </div>
  );
}

function MarketInsightsCard({ mi }) {
  const navigate = useNavigate();
  const { configured, latestRun, active, loading, error } = mi;

  const goWorkspace = () => navigate("/agents/market-insights");
  const goConfigure = () => navigate("/agents/market-insights/scope");

  let right;
  if (loading) right = <Spinner size={12} />;
  else if (active)
    right = (
      <Badge tone="accent">
        <Spinner size={10} /> Running
      </Badge>
    );
  else if (latestRun?.status === "failed") right = <Badge tone="danger">Last run failed</Badge>;
  else if (configured) right = <Badge tone="success">Active</Badge>;
  else right = <Badge tone="warning">Setup needed</Badge>;

  async function onRun(e) {
    e.stopPropagation();
    try {
      const run = await mi.startRun();
      navigate(`/agents/market-insights/runs/${run.id}`);
    } catch (err) {
      alert(err.message || "Couldn't start the run.");
    }
  }

  return (
    <Card onClick={configured ? goWorkspace : goConfigure}>
      <CardHeader Icon={LineChart} right={right} />
      <p style={{ fontWeight: 600, fontSize: 14, margin: "0 0 4px" }}>Market insights</p>
      <p style={{ fontSize: 12, color: theme.textSecondary, margin: "0 0 12px" }}>
        Industry, market and competitive signals
      </p>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderTop: `1px solid ${theme.border}`,
          paddingTop: 10,
          gap: 8,
        }}
      >
        <div style={{ minWidth: 0 }}>
          {error ? (
            <p style={{ fontSize: 12, color: theme.danger, margin: 0, display: "flex", alignItems: "center", gap: 4 }}>
              <AlertTriangle size={12} /> {error}
            </p>
          ) : !configured ? (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>Configure a scope to start</p>
          ) : active ? (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>Run in progress…</p>
          ) : latestRun ? (
            <>
              <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>
                {latestRun.status === "failed" ? "Last run failed" : "Last run"} · {relativeTime(latestRun.created_at)}
              </p>
              <p style={{ fontSize: 11, color: theme.textMuted, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220 }}>
                {latestRun.subject}
              </p>
            </>
          ) : (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>No runs yet</p>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {configured && (
            <button
              title="Configure scope"
              onClick={(e) => {
                e.stopPropagation();
                goConfigure();
              }}
              style={{
                border: "none",
                background: "transparent",
                cursor: "pointer",
                padding: 4,
                display: "flex",
                alignItems: "center",
              }}
            >
              <SettingsIcon size={15} color={theme.textMuted} />
            </button>
          )}
          {configured ? (
            <Button small icon={active ? undefined : Play} disabled={active} onClick={onRun}>
              {active ? "Running…" : "Run"}
            </Button>
          ) : (
            <Button
              small
              variant="primary"
              onClick={(e) => {
                e.stopPropagation();
                goConfigure();
              }}
            >
              Set up this agent
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

function NotSubscribedCard({ def }) {
  const Icon = def.icon;
  return (
    <Card style={{ background: theme.surfaceMuted, opacity: 0.9 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Icon size={19} color={theme.textMuted} />
        <Badge tone="muted">Not subscribed</Badge>
      </div>
      <p style={{ fontWeight: 600, fontSize: 14, margin: "0 0 4px", color: theme.textSecondary }}>{def.name}</p>
      <p style={{ fontSize: 12, color: theme.textMuted, margin: "0 0 12px" }}>{def.blurb}</p>
      <Button small icon={Plus} disabled title="No backend yet">
        Add agent
      </Button>
    </Card>
  );
}

function StrategySynthesisCard({ strategy }) {
  const navigate = useNavigate();
  const { latestRun, active, loading, error } = strategy;

  const goWorkspace = () => navigate("/agents/strategy-synthesis");
  const goInputs = () => navigate("/agents/strategy-synthesis/inputs");

  let badge;
  if (loading) badge = <Spinner size={12} />;
  else if (active)
    badge = (
      <Badge tone="accent">
        <Spinner size={10} /> Running
      </Badge>
    );
  else if (latestRun?.status === "failed") badge = <Badge tone="danger">Last run failed</Badge>;
  else badge = <Badge tone="success">Active</Badge>;

  async function onRun(e) {
    e.stopPropagation();
    try {
      const run = await strategy.startRun();
      navigate(`/agents/strategy-synthesis/runs/${run.id}`);
    } catch (err) {
      alert(err.message || "Couldn't start the run.");
    }
  }

  return (
    <Card accent onClick={goWorkspace} style={{ maxWidth: 720, marginTop: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Sparkles size={18} color={theme.orange} />
        {badge}
      </div>
      <p style={{ fontWeight: 600, fontSize: 15, margin: "0 0 4px" }}>Strategy synthesis and decision</p>
      <p style={{ fontSize: 13, color: theme.textSecondary, margin: "0 0 10px" }}>
        Ranks the committed portfolio, checks capacity and scenarios, and writes a decision brief. Run is always
        available — the brief states what's missing rather than blocking on it.
      </p>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderTop: `1px solid ${theme.border}`,
          marginTop: 12,
          paddingTop: 10,
          gap: 8,
        }}
      >
        <div style={{ minWidth: 0 }}>
          {error ? (
            <p style={{ fontSize: 12, color: theme.danger, margin: 0, display: "flex", alignItems: "center", gap: 4 }}>
              <AlertTriangle size={12} /> {error}
            </p>
          ) : active ? (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>Run in progress…</p>
          ) : latestRun ? (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>
              {latestRun.status === "failed" ? "Last run failed" : "Last run"} · {relativeTime(latestRun.created_at)}
            </p>
          ) : (
            <p style={{ fontSize: 12, color: theme.textMuted, margin: 0 }}>No runs yet</p>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <button
            title="Decision inputs"
            onClick={(e) => {
              e.stopPropagation();
              goInputs();
            }}
            style={{ border: "none", background: "transparent", cursor: "pointer", padding: 4, display: "flex", alignItems: "center" }}
          >
            <SettingsIcon size={15} color={theme.textMuted} />
          </button>
          <Button small icon={active ? undefined : Play} disabled={active} onClick={onRun}>
            {active ? "Running…" : "Run"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
