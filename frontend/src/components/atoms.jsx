// Shared visual atoms — ported from autostrat-loom-dashboard.jsx.
// Behaviour additions kept minimal: Button gains `type` + `href` support.
import { theme, FONT } from "../theme.js";

export function Badge({ children, tone = "muted" }) {
  const tones = {
    success: { bg: theme.successBg, color: theme.success },
    warning: { bg: theme.warningBg, color: theme.warning },
    danger: { bg: theme.dangerBg, color: theme.danger },
    muted: { bg: theme.surfaceMuted, color: theme.textMuted, border: `1px solid ${theme.border}` },
    accent: { bg: theme.orangeSoft, color: theme.orange },
  };
  const t = tones[tone] || tones.muted;
  return (
    <span
      style={{
        fontSize: 11,
        padding: "3px 9px",
        borderRadius: 999,
        background: t.bg,
        color: t.color,
        border: t.border || "none",
        fontWeight: 600,
        letterSpacing: 0.2,
        whiteSpace: "nowrap",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
      }}
    >
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  small,
  disabled,
  icon: Icon,
  type = "button",
  style,
  title,
}) {
  const base = {
    fontFamily: FONT,
    fontSize: small ? 12 : 13,
    fontWeight: 600,
    padding: small ? "5px 10px" : "8px 16px",
    borderRadius: 8,
    cursor: disabled ? "default" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    border: "1px solid transparent",
    opacity: disabled ? 0.55 : 1,
    transition: "opacity 0.15s",
  };
  const variants = {
    default: { background: theme.surface, color: theme.textPrimary, border: `1px solid ${theme.border}` },
    primary: { background: theme.orange, color: "#fff" },
    danger: { background: theme.surface, color: theme.danger, border: `1px solid ${theme.dangerBg}` },
    ghost: { background: "transparent", color: theme.textSecondary },
  };
  return (
    <button
      type={type}
      title={title}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{ ...base, ...variants[variant], ...style }}
    >
      {Icon && <Icon size={small ? 13 : 14} />}
      {children}
    </button>
  );
}

export function Card({ children, style, accent, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: theme.surface,
        borderRadius: 14,
        border: accent ? `2px solid ${theme.orange}` : `1px solid ${theme.border}`,
        padding: "16px 18px",
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function EmptyPanel({ icon: Icon, title, note, action }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", padding: "40px 4px", maxWidth: 440 }}>
      {Icon && (
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: theme.orangeSoft,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 14,
          }}
        >
          <Icon size={20} color={theme.orange} />
        </div>
      )}
      <p style={{ fontWeight: 600, fontSize: 15, margin: "0 0 6px", color: theme.textPrimary }}>{title}</p>
      {note && <p style={{ fontSize: 13, color: theme.textSecondary, margin: 0, lineHeight: 1.5 }}>{note}</p>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  );
}

export function Spinner({ size = 13, color }) {
  return (
    <>
      <span
        style={{
          display: "inline-block",
          width: size,
          height: size,
          border: `2px solid ${color || theme.orange}`,
          borderTopColor: "transparent",
          borderRadius: "50%",
          animation: "loom-spin 0.9s linear infinite",
        }}
      />
      <style>{`@keyframes loom-spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
