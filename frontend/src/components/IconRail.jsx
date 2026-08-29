// Persistent navy icon rail — ported from autostrat-loom-dashboard.jsx.
// Nav items route with react-router; the account avatar opens a small logout menu.
import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Home, LayoutGrid, ClipboardList, Plug, Settings as SettingsIcon, LogOut } from "lucide-react";
import { theme } from "../theme.js";
import { useAuth } from "../auth/AuthContext.jsx";

const RAIL_ITEMS = [
  { id: "home", icon: Home, label: "Home", to: "/" },
  { id: "agents", icon: LayoutGrid, label: "Agents", to: "/" },
  { id: "reports", icon: ClipboardList, label: "Enterprise imperatives", to: "/" },
  { id: "sources", icon: Plug, label: "Data sources", to: "/" },
];

export function IconRail() {
  const navigate = useNavigate();
  const location = useLocation();
  const { session, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const onHome = location.pathname === "/";
  const initials = (session?.user_email || "?").slice(0, 2).toUpperCase();

  return (
    <div
      style={{
        width: 60,
        background: theme.navy,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "18px 0",
        flexShrink: 0,
      }}
    >
      <div
        onClick={() => navigate("/")}
        role="button"
        tabIndex={0}
        title="Home"
        style={{
          width: 34,
          height: 34,
          borderRadius: 9,
          background: theme.orange,
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 700,
          fontSize: 13,
          marginBottom: 28,
          cursor: "pointer",
        }}
      >
        AL
      </div>

      {RAIL_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = onHome && item.id === "home";
        return (
          <button
            key={item.id}
            title={item.label}
            onClick={() => navigate(item.to)}
            style={{
              width: 38,
              height: 38,
              borderRadius: 9,
              marginBottom: 8,
              border: "none",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: active ? "rgba(255,255,255,0.14)" : "transparent",
            }}
          >
            <Icon size={18} color={active ? "#fff" : "rgba(255,255,255,0.55)"} />
          </button>
        );
      })}

      <div style={{ flex: 1 }} />

      <button
        title="Settings (not part of this release)"
        onClick={() => navigate("/settings")}
        style={{
          width: 38,
          height: 38,
          borderRadius: 9,
          marginBottom: 12,
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: location.pathname === "/settings" ? "rgba(255,255,255,0.14)" : "transparent",
        }}
      >
        <SettingsIcon size={18} color={location.pathname === "/settings" ? "#fff" : "rgba(255,255,255,0.55)"} />
      </button>

      <div style={{ position: "relative" }}>
        <div
          onClick={() => setMenuOpen((v) => !v)}
          role="button"
          tabIndex={0}
          title={session?.user_email || "Account"}
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: theme.orangeSoft,
            color: theme.orange,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          {initials}
        </div>
        {menuOpen && (
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 40,
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 10,
              boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              padding: 8,
              width: 220,
              zIndex: 20,
            }}
          >
            <p style={{ fontSize: 12, color: theme.textMuted, margin: "2px 8px 6px" }}>
              {session?.user_email}
              <br />
              <span style={{ color: theme.textSecondary }}>
                {session?.tenant_name} · {session?.role}
              </span>
            </p>
            <button
              onClick={() => {
                setMenuOpen(false);
                logout();
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                width: "100%",
                padding: "8px",
                borderRadius: 8,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                fontSize: 13,
                color: theme.textPrimary,
              }}
            >
              <LogOut size={15} color={theme.textSecondary} />
              Sign out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
