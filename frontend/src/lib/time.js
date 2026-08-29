// Backend timestamps come as naive UTC ISO strings (e.g. "2026-08-28T18:58:58").
// Parse them as UTC and render a short relative label.
export function parseUtc(iso) {
  if (!iso) return null;
  const hasTz = /[zZ]|[+-]\d\d:?\d\d$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
}

export function relativeTime(iso) {
  const d = parseUtc(iso);
  if (!d) return "";
  const secs = Math.round((Date.now() - d.getTime()) / 1000);
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString();
}

export function absoluteTime(iso) {
  const d = parseUtc(iso);
  return d ? d.toLocaleString() : "";
}

export function elapsedSince(iso) {
  const d = parseUtc(iso);
  if (!d) return "";
  const secs = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}
