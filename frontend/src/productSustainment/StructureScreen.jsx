// Product structure: the three part masters, the two BOM matrices, and the
// derived picture after upload.
//
// The derived picture is the point of this screen. The BOM is many-to-many
// at both joins, and a dangling or missing link silently removes demand, so
// after every upload it shows how many LRUs, assemblies and components there
// are -- and how many parts have NO DEMAND PATH. That last number is the one
// that catches a bad matrix.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Button, Spinner } from "../components/atoms.jsx";
import { theme } from "../theme.js";
import { BackLink, TierBanner, UploadCard } from "./common.jsx";
import { MASTERS, MATRICES } from "./reportMeta.js";
import { RowsEditor, SectionCard } from "./RowsEditor.jsx";

const LOADERS = Object.fromEntries(MASTERS.map((m) => [m.which, () => api.productSustainment.getMaster(m.which)]));
const SAVERS = Object.fromEntries(MASTERS.map((m) => [m.which, (rows) => api.productSustainment.putMaster(m.which, rows)]));

function Stat({ label, value, warn }) {
  return (
    <div style={{ minWidth: 120 }}>
      <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: warn ? theme.danger : theme.navy }}>{value}</p>
      <p style={{ margin: 0, fontSize: 11.5, color: theme.textMuted }}>{label}</p>
    </div>
  );
}

function DerivedPicture({ summary }) {
  if (!summary) return <Spinner size={14} />;
  const noPath = summary.parts_without_demand_path || [];
  return (
    <div style={{ border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, padding: "14px 16px", marginBottom: 18 }}>
      <p style={{ margin: "0 0 10px", fontSize: 12, fontWeight: 700, color: theme.textSecondary, textTransform: "uppercase", letterSpacing: 0.5 }}>
        Derived structure
      </p>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <Stat label="LRUs" value={summary.lrus} />
        <Stat label="Level 1 assemblies" value={summary.level1} />
        <Stat label="Level 2 components" value={summary.level2} />
        <Stat label="LRU → Level 1 links" value={summary.lru_level1_edges} />
        <Stat label="Level 1 → Level 2 links" value={summary.level1_level2_edges} />
        <Stat label="Parts with no demand path" value={noPath.length} warn={noPath.length > 0} />
      </div>
      {noPath.length > 0 && (
        <p style={{ margin: "10px 0 0", fontSize: 12, color: theme.danger, display: "flex", gap: 6, lineHeight: 1.5 }}>
          <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>
            No LRU reaches these through the matrices and none has direct demand, so none can get a runout date:{" "}
            {noPath.slice(0, 40).join(", ")}
            {noPath.length > 40 ? ` … and ${noPath.length - 40} more` : ""}. Check the matrices if any of these should be
            in use.
          </span>
        </p>
      )}
    </div>
  );
}

export default function StructureScreen() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [files, setFiles] = useState({});
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, r, f] = await Promise.all([
        api.productSustainment.getSummary(),
        api.productSustainment.getReadiness(),
        api.productSustainment.listFiles(),
      ]);
      setSummary(s);
      setReadiness(r);
      setFiles(Object.fromEntries((f || []).map((x) => [x.file_type, x])));
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load the structure.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const bom = (readiness?.items || []).find((i) => i.key === "bom");

  return (
    <div style={{ padding: "28px 32px 48px", overflowY: "auto", background: theme.bg, flex: 1 }}>
      <div style={{ maxWidth: 1040 }}>
        <BackLink to="/agents/product-sustainment" label="Back to the agent" />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>Product structure</h1>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: theme.textSecondary, maxWidth: 720, lineHeight: 1.55 }}>
              Three levels — LRU, Level 1 assembly, Level 2 component — joined many-to-many at both levels. A component's
              depletion comes from every LRU that uses it, through every assembly, so the matrices are what the runout
              calculation rests on.
            </p>
          </div>
          <Button icon={ArrowRight} onClick={() => navigate("/agents/product-sustainment/data")}>
            Inventory, demand and risk
          </Button>
        </div>
        {error && <p style={{ fontSize: 12, color: theme.danger }}>{error}</p>}
        {readiness && (
          <div style={{ margin: "18px 0" }}>
            <TierBanner readiness={readiness} showMissing={false} />
          </div>
        )}

        <DerivedPicture summary={summary} />

        <h2 style={{ fontSize: 15, fontWeight: 700, margin: "6px 0 10px" }}>Part masters</h2>
        <p style={{ margin: "0 0 10px", fontSize: 12, color: theme.textSecondary }}>
          Declare the ids first: matrix headers and row labels must resolve to them, and a reference that resolves to
          nothing is rejected rather than silently dropping demand.
        </p>
        {MASTERS.map((m) => (
          <SectionCard key={m.which} title={m.title} blurb="">
            <RowsEditor fields={m.fields} load={LOADERS[m.which]} save={SAVERS[m.which]} onSaved={load} />
          </SectionCard>
        ))}

        <h2 style={{ fontSize: 15, fontWeight: 700, margin: "18px 0 10px" }}>BOM matrices</h2>
        {bom?.consequence && (
          <p style={{ margin: "0 0 10px", fontSize: 12, color: theme.warning, display: "flex", gap: 6 }}>
            <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} /> <span><strong>If left empty:</strong> {bom.consequence}</span>
          </p>
        )}
        {MATRICES.map((m) => (
          <UploadCard
            key={m.which}
            title={m.title}
            blurb={`${m.blurb} An edge list (one row per relationship) is also accepted.`}
            templateKey={m.which}
            file={files[`matrix:${m.which}`]}
            onUpload={async (f) => {
              const out = await api.productSustainment.uploadMatrix(m.which, f);
              setSummary(out.summary);
              await load();
            }}
          />
        ))}
      </div>
    </div>
  );
}
