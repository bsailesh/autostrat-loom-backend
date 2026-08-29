import { theme, FONT } from "../theme.js";

export function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: theme.bg,
        fontFamily: FONT,
        padding: 24,
      }}
    >
      <div style={{ width: "100%", maxWidth: 380 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
          <div
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
            }}
          >
            AL
          </div>
          <span style={{ fontWeight: 700, fontSize: 15 }}>AutoStrat Loom</span>
        </div>

        <div
          style={{
            background: theme.surface,
            border: `1px solid ${theme.border}`,
            borderRadius: 14,
            padding: "24px 22px",
          }}
        >
          <p style={{ fontWeight: 700, fontSize: 18, margin: "0 0 4px" }}>{title}</p>
          {subtitle && <p style={{ fontSize: 13, color: theme.textSecondary, margin: "0 0 18px" }}>{subtitle}</p>}
          {children}
        </div>

        {footer && <div style={{ marginTop: 16, fontSize: 13, color: theme.textSecondary }}>{footer}</div>}
      </div>
    </div>
  );
}

export function TextInput({ label, type = "text", value, onChange, placeholder, autoFocus, autoComplete }) {
  return (
    <label style={{ display: "block", marginBottom: 14 }}>
      <span style={{ fontSize: 12, color: theme.textMuted, display: "block", marginBottom: 5 }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        style={{
          width: "100%",
          fontFamily: FONT,
          fontSize: 14,
          padding: "9px 11px",
          borderRadius: 8,
          border: `1px solid ${theme.border}`,
          background: "#fff",
          color: theme.textPrimary,
          outline: "none",
        }}
      />
    </label>
  );
}

export function FormError({ children }) {
  if (!children) return null;
  return (
    <p
      style={{
        background: theme.dangerBg,
        color: theme.danger,
        fontSize: 12.5,
        borderRadius: 8,
        padding: "8px 10px",
        margin: "0 0 14px",
      }}
    >
      {children}
    </p>
  );
}
