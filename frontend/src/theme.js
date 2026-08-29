// Design system — carried over verbatim from autostrat-loom-dashboard.jsx.
// Do not tweak these values ad hoc; they're the agreed palette/scale.
export const theme = {
  navy: "#1B2A4A",
  navyLight: "#2E4370",
  orange: "#E8703A",
  orangeSoft: "#FDEEE7",
  bg: "#F7F5F1",
  surface: "#FFFFFF",
  surfaceMuted: "#FBFAF7",
  border: "#E6E2D8",
  textPrimary: "#20242E",
  textSecondary: "#6B6459",
  textMuted: "#9C9587",
  success: "#2F8F58",
  successBg: "#E7F5EC",
  warning: "#B8791E",
  warningBg: "#FBF0DE",
  danger: "#C4462D",
  dangerBg: "#FBEAE6",
};

// The reference file uses a Segoe UI stack; the briefing calls the agreed scale
// "IBM Plex-style", and the marketing site loads IBM Plex Sans — so IBM Plex is
// primary here with the reference's stack as fallback.
export const FONT =
  "'IBM Plex Sans', 'Segoe UI', ui-sans-serif, system-ui, -apple-system, sans-serif";
export const MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace";

// Confidence tag -> palette. Green / amber / red per the briefing.
export function confidenceTone(level) {
  const l = String(level || "").toLowerCase();
  if (l.startsWith("high")) return { bg: theme.successBg, color: theme.success, label: "High" };
  if (l.startsWith("med")) return { bg: theme.warningBg, color: theme.warning, label: "Medium" };
  if (l.startsWith("low")) return { bg: theme.dangerBg, color: theme.danger, label: "Low" };
  return { bg: theme.surfaceMuted, color: theme.textMuted, label: String(level || "") };
}
