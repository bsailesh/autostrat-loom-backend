// Inventory, pipeline, demand, risk, alternates, lead times, fleet,
// maintenance and configuration -- each with a template and validation --
// plus the knowledge assessment, which is a form because no file exists for
// a judgement.
import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Button } from "../components/atoms.jsx";
import { theme } from "../theme.js";
import { BackLink, TierBanner, UploadCard } from "./common.jsx";
import { DATA_FILES, KNOWLEDGE_FIELDS } from "./reportMeta.js";
import { RowsEditor, SectionCard } from "./RowsEditor.jsx";

const loadKnowledge = () => api.productSustainment.getKnowledge();
const saveKnowledge = (rows) => api.productSustainment.putKnowledge(rows);

export default function DataScreen() {
  const navigate = useNavigate();
  const [readiness, setReadiness] = useState(null);
  const [files, setFiles] = useState({});
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, f] = await Promise.all([api.productSustainment.getReadiness(), api.productSustainment.listFiles()]);
      setReadiness(r);
      setFiles(Object.fromEntries((f || []).map((x) => [x.file_type, x])));
      setError("");
    } catch (e) {
      setError(e.message || "Couldn't load the data files.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byKey = Object.fromEntries((readiness?.items || []).map((i) => [i.key, i]));

  return (
    <div style={{ padding: "28px 32px 48px", overflowY: "auto", background: theme.bg, flex: 1 }}>
      <div style={{ maxWidth: 1040 }}>
        <BackLink to="/agents/product-sustainment/structure" label="Back to product structure" />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>Inventory, demand and risk</h1>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: theme.textSecondary, maxWidth: 720, lineHeight: 1.55 }}>
              Each upload replaces that file's data. Any error rejects the whole file and keeps what was there before;
              warnings never block.
            </p>
          </div>
          <Button icon={ArrowRight} onClick={() => navigate("/agents/product-sustainment/evidence")}>
            Reliability evidence
          </Button>
        </div>
        {error && <p style={{ fontSize: 12, color: theme.danger }}>{error}</p>}
        {readiness && (
          <div style={{ margin: "18px 0" }}>
            <TierBanner readiness={readiness} />
          </div>
        )}

        {DATA_FILES.map((d) => (
          <UploadCard
            key={d.type}
            title={d.title}
            blurb={d.blurb}
            templateKey={d.type}
            asOf={d.asOf}
            item={d.readiness ? byKey[d.readiness] : undefined}
            file={files[d.type]}
            onUpload={async (f, asOf) => {
              await api.productSustainment.uploadFile(d.type, f, asOf);
              await load();
            }}
          />
        ))}

        <SectionCard
          title="Knowledge and capability assessment"
          item={byKey.knowledge}
          blurb="Where specialised repair or diagnostic knowledge sits with few people, or tooling and test equipment are being discontinued. A judgement only you can make — no data source produces it, and the agent will not infer it from headcount or age."
        >
          <RowsEditor fields={KNOWLEDGE_FIELDS} load={loadKnowledge} save={saveKnowledge} onSaved={load} />
        </SectionCard>
      </div>
    </div>
  );
}
