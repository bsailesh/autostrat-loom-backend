import { confidenceTone } from "../theme.js";

// Small inline pill: High = green, Medium = amber, Low = red (per the briefing).
export function ConfidenceTag({ level, size = "sm" }) {
  const t = confidenceTone(level);
  const pad = size === "xs" ? "1px 6px" : "2px 8px";
  const fs = size === "xs" ? 10 : 11;
  return (
    <span
      style={{
        display: "inline-block",
        padding: pad,
        borderRadius: 999,
        fontSize: fs,
        fontWeight: 700,
        letterSpacing: 0.3,
        background: t.bg,
        color: t.color,
        whiteSpace: "nowrap",
        verticalAlign: "baseline",
      }}
    >
      {t.label || "—"}
    </span>
  );
}

// Matches the confidence phrasings the agent actually emits inside **bold**:
//   [High]  ·  High  ·  Confidence: High.  ·  [High — corroborated]  ·  High/Medium
// Returns the level word ("High"/"Medium"/"Low") or null.
export function matchConfidence(text) {
  if (typeof text !== "string") return null;
  const s = text.trim();
  const m = s.match(/^(?:\[?\s*)?(?:confidence[:\s]+)?(high|medium|med|low)\b/i);
  if (!m) return null;
  // Guard against false positives like "Highly concentrated ..." — only treat it
  // as a tag when the bold span is short and tag-like.
  if (s.length > 40) return null;
  return m[1].toLowerCase().startsWith("med") ? "Medium" : m[1][0].toUpperCase() + m[1].slice(1).toLowerCase();
}
