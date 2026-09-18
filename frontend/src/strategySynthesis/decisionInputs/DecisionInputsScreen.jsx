// Settings-style decision inputs screen (Part 6): one section per category
// in agent5_decision_inputs_brief_spec.md, each showing status and, where
// /readiness names a consequence, that consequence inline -- never a bare
// red badge. Run is always enabled elsewhere (the workspace's top bar);
// nothing here gates it.
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, Settings as SettingsIcon } from "lucide-react";
import { api } from "../../api.js";
import { theme } from "../../theme.js";
import { Button, Spinner } from "../../components/atoms.jsx";
import { PageHeader } from "../../components/PageHeader.jsx";
import SectionShell from "./SectionShell.jsx";
import FileSectionCard from "./FileSectionCard.jsx";
import ObjectivesSection from "./sections/ObjectivesSection.jsx";
import ProposalsSection from "./sections/ProposalsSection.jsx";
import FrameworkSection from "./sections/FrameworkSection.jsx";
import ScenariosSection from "./sections/ScenariosSection.jsx";
import ConfigurationSection from "./sections/ConfigurationSection.jsx";
import RulesSection from "./sections/RulesSection.jsx";

export default function DecisionInputsScreen() {
  const navigate = useNavigate();
  const [state, setState] = useState(null); // { readiness, files, buckets, config, proposals } | null while loading
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [readiness, files, buckets, config, proposals, fiscalYears] = await Promise.all([
        api.strategySynthesis.getReadiness(),
        api.strategySynthesis.listFiles(),
        api.strategySynthesis.getBuckets(),
        api.strategySynthesis.getConfig(),
        api.strategySynthesis.getProposals(),
        api.strategySynthesis.getFiscalYears(),
      ]);
      setState({ readiness, files, buckets, config, proposals, fiscalYears });
    } catch (e) {
      setError(e.message || "Couldn't load decision inputs.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <>
        <PageHeader title="Decision inputs" right={<HomeBtn navigate={navigate} />} />
        <div style={{ padding: 32, color: theme.danger, fontSize: 13 }}>{error}</div>
      </>
    );
  }
  if (!state) {
    return (
      <>
        <PageHeader title="Decision inputs" />
        <div style={{ padding: 32 }}>
          <Spinner size={20} />
        </div>
      </>
    );
  }

  const { readiness, files, buckets, config, proposals, fiscalYears } = state;
  const byItem = Object.fromEntries(readiness.map((r) => [r.item, r]));
  const filesByType = Object.fromEntries(files.map((f) => [f.file_type, f]));
  const bucketsReady = buckets.length >= 2;

  const roadmapFile = filesByType.roadmap;
  const roadmapStatus = roadmapFile ? (roadmapFile.validation_status === "invalid" ? "missing" : "set") : "missing";

  return (
    <>
      <PageHeader title="Decision inputs" subtitle="Strategy Synthesis" right={<HomeBtn navigate={navigate} />} />
      <div style={{ padding: "24px 32px", overflowY: "auto" }}>
        <div style={{ maxWidth: 760 }}>
          <SectionShell title="Configuration" status={config.configured ? "set" : "missing"} consequence="Effort unit and fiscal-year labeling will use built-in defaults; no effort bands means effort is reported in raw units only.">
            <ConfigurationSection onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Objectives"
            status={byItem["Objectives"]?.status || "missing"}
            consequence={byItem["Objectives"]?.consequence}
          >
            <ObjectivesSection onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Products and installed base"
            status={byItem["Products / installed base"]?.status || "missing"}
            consequence={byItem["Products / installed base"]?.consequence}
          >
            <FileSectionCard fileType="products_fleet" fileInfo={filesByType.products_fleet} onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Capacity"
            status={byItem["Capacity"]?.status || "missing"}
            consequence={byItem["Capacity"]?.consequence}
          >
            <div style={{ marginBottom: 12 }}>
              <Button small variant="ghost" icon={SettingsIcon} onClick={() => navigate("/agents/strategy-synthesis/inputs/buckets")}>
                Manage capacity buckets ({buckets.length})
              </Button>
            </div>
            {fiscalYears.length > 1 && (
              <p style={{ fontSize: 12, color: theme.warning, margin: "0 0 12px" }}>
                Declared fiscal years: {fiscalYears.join(", ")} -- a run must be told which one to analyze
                (fiscal_year on POST /runs), or it 400s. The Run button asks for one when this happens.
              </p>
            )}
            <FileSectionCard fileType="capacity" fileInfo={filesByType.capacity} bucketsReady={bucketsReady} onChanged={load} />
          </SectionShell>

          <SectionShell title="Roadmap" status={roadmapStatus} consequence="No committed portfolio to rank -- only discovered or proposed candidates would appear, unscored.">
            <FileSectionCard fileType="roadmap" fileInfo={filesByType.roadmap} bucketsReady={bucketsReady} onChanged={load} />

            <p style={{ fontSize: 11, fontWeight: 700, color: theme.textSecondary, textTransform: "uppercase", letterSpacing: 0.4, margin: "22px 0 4px" }}>
              Dependencies
            </p>
            {byItem["Dependencies"] && byItem["Dependencies"].status !== "set" && (
              <p style={{ fontSize: 12, color: theme.textMuted, margin: "0 0 10px" }}>{byItem["Dependencies"].consequence}</p>
            )}
            <FileSectionCard fileType="dependencies" fileInfo={filesByType.dependencies} onChanged={load} />

            <p style={{ fontSize: 11, fontWeight: 700, color: theme.textSecondary, textTransform: "uppercase", letterSpacing: 0.4, margin: "22px 0 4px" }}>
              Financials
            </p>
            {byItem["Financials"] && byItem["Financials"].status !== "set" && (
              <p style={{ fontSize: 12, color: theme.textMuted, margin: "0 0 10px" }}>{byItem["Financials"].consequence}</p>
            )}
            <FileSectionCard fileType="financials" fileInfo={filesByType.financials} onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Proposals"
            status={proposals.length > 0 ? "set" : "missing"}
            consequence="A design partner's own project ideas won't enter the candidate set for scoping."
          >
            <ProposalsSection onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Framework"
            status={byItem["Framework"]?.status || "missing"}
            consequence={byItem["Framework"]?.consequence}
          >
            <FrameworkSection onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Scenarios"
            status={byItem["Scenarios"]?.status || "missing"}
            consequence={byItem["Scenarios"]?.consequence}
          >
            <ScenariosSection onChanged={load} />
          </SectionShell>

          <SectionShell
            title="Rules"
            status={config.rules?.length > 0 ? "set" : "missing"}
            consequence="No business rules applied -- e.g. no minimum effort to rank, no mandatory-never-cut guard."
          >
            <RulesSection onChanged={load} />
          </SectionShell>
        </div>
      </div>
    </>
  );
}

function HomeBtn({ navigate }) {
  return (
    <Button small variant="ghost" icon={ChevronLeft} onClick={() => navigate("/agents/strategy-synthesis")}>
      Workspace
    </Button>
  );
}
