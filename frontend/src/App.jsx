import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import { IconRail } from "./components/IconRail.jsx";
import { EmptyPanel } from "./components/atoms.jsx";
import { Spinner } from "./components/atoms.jsx";
import { theme } from "./theme.js";
import LoginPage from "./auth/LoginPage.jsx";
import SignupPage from "./auth/SignupPage.jsx";
import HomeDashboard from "./home/HomeDashboard.jsx";
import ConfigureScope from "./marketInsights/ConfigureScope.jsx";
import Workspace from "./marketInsights/Workspace.jsx";
import MarketInsightsEntry from "./marketInsights/MarketInsightsEntry.jsx";
import { Settings as SettingsIcon } from "lucide-react";

function FullPageLoader() {
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: theme.bg }}>
      <Spinner size={22} />
    </div>
  );
}

function RequireAuth() {
  const { isAuthed, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <FullPageLoader />;
  if (!isAuthed) return <Navigate to="/login" replace state={{ from: location }} />;
  return (
    <div style={{ display: "flex", height: "100%", minHeight: 640 }}>
      <IconRail />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <Outlet />
      </div>
    </div>
  );
}

function GuestOnly({ children }) {
  const { isAuthed, ready } = useAuth();
  if (!ready) return <FullPageLoader />;
  if (isAuthed) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
      <Route path="/signup" element={<GuestOnly><SignupPage /></GuestOnly>} />

      <Route element={<RequireAuth />}>
        <Route index element={<HomeDashboard />} />
        <Route path="/agents/market-insights" element={<MarketInsightsEntry />} />
        <Route path="/agents/market-insights/scope" element={<ConfigureScope />} />
        <Route path="/agents/market-insights/workspace" element={<Workspace />} />
        <Route path="/agents/market-insights/runs/:runId" element={<Workspace />} />
        <Route path="/agents/market-insights/runs/:runId/reports/:reportId" element={<Workspace />} />
        <Route
          path="/settings"
          element={
            <div style={{ padding: "40px 32px" }}>
              <EmptyPanel
                icon={SettingsIcon}
                title="Settings aren't part of this release"
                note="Profile, team, billing, data sources and AI-model settings have their own designs and land in a later phase."
              />
            </div>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
