// Dependency and exposure map -- which LRUs a flagged component reaches, and
// through which assemblies. The cascade is computed through the matrices
// (results.exposure_table): every assembly containing the part, every LRU
// containing those assemblies, with the all-paths quantity per LRU unit.
//
// Contract: | Component | Assembly | LRU | Qty per LRU unit |
import { theme } from "../../theme.js";

function col(headers, re) {
  return headers.findIndex((h) => re.test(String(h).trim()));
}

export function detectExposureMap(table) {
  const { headers, rows } = table;
  const c = col(headers, /^component$/i), a = col(headers, /^assembly$/i), l = col(headers, /^lru$/i), q = col(headers, /^qty per lru unit$/i);
  if (c === -1 || a === -1 || l === -1 || q === -1 || !rows.length) return null;
  const parts = new Map();
  for (const row of rows) {
    const comp = row[c]?.text, asm = row[a]?.text, lru = row[l]?.text;
    if (!comp || !asm || !lru) return null;
    if (!parts.has(comp)) parts.set(comp, { assemblies: new Map(), lrus: new Map() });
    const p = parts.get(comp);
    if (!p.assemblies.has(asm)) p.assemblies.set(asm, new Set());
    p.assemblies.get(asm).add(lru);
    p.lrus.set(lru, row[q]?.text || "");
  }
  return { parts: [...parts] };
}

const chip = (bg, color) => ({
  display: "inline-block", fontSize: 11.5, padding: "2px 8px", borderRadius: 999, background: bg, color, margin: "2px 4px 2px 0",
  whiteSpace: "nowrap",
});

export function ExposureMapExhibit({ data }) {
  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>Dependency and exposure</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>
          computed through the matrices · every LRU a component reaches, through every assembly
        </span>
      </figcaption>
      {data.parts.map(([comp, p], i) => (
        <div key={comp} style={{ display: "grid", gridTemplateColumns: "150px 1fr 1fr", gap: 12, padding: "10px 14px",
                                 borderTop: i ? `1px solid ${theme.border}` : "none", alignItems: "start" }}>
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: theme.danger }}>{comp}</p>
            <p style={{ margin: "2px 0 0", fontSize: 11, color: theme.textMuted }}>
              {p.assemblies.size} assembl{p.assemblies.size === 1 ? "y" : "ies"} · {p.lrus.size} LRU{p.lrus.size === 1 ? "" : "s"}
            </p>
          </div>
          <div>
            <p style={{ margin: "0 0 3px", fontSize: 10, color: theme.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>Assemblies</p>
            {[...p.assemblies.keys()].map((a) => <span key={a} style={chip(theme.warningBg, theme.warning)}>{a}</span>)}
          </div>
          <div>
            <p style={{ margin: "0 0 3px", fontSize: 10, color: theme.textMuted, textTransform: "uppercase", letterSpacing: 0.4 }}>
              LRUs (qty per unit, all paths)
            </p>
            {[...p.lrus].map(([lru, q]) => <span key={lru} style={chip(theme.dangerBg, theme.danger)}>{lru} × {q}</span>)}
          </div>
        </div>
      ))}
    </figure>
  );
}
