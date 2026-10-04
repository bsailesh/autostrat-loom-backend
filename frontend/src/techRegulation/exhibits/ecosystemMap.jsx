// Technology ecosystem map -- the most work of the four exhibits, and
// deliberately the least clever. A simple layered layout in inline SVG: no
// force simulation, no graph library (the briefing rules one out), and no
// randomness, so the same evidence always draws the same picture.
//
// Two detectors, because the report emits two tables and the registry
// resolves one table at a time:
//   nodes  | Node | Node type | Role | Evidence | Confidence |
//   edges  | From | To | Relationship | Evidence | Confidence |
//
// The edges table draws the graph (it carries the relationships and their
// evidence, and nodes are derived from From/To). The nodes table renders as
// a typed roster. Every edge carries its own evidence because an edge on a
// map reads as verified fact.
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";

// Column order for the layered layout, upstream to downstream.
const TYPE_LAYERS = [
  "university",
  "research institution",
  "government",
  "programme",
  "investor",
  "startup",
  "tier supplier",
  "oem",
];

function col(headers, re) {
  return headers.findIndex((h) => re.test(h));
}

function typeKey(raw) {
  const v = String(raw || "").toLowerCase().trim();
  return TYPE_LAYERS.find((t) => v.includes(t)) || "other";
}

// ---------------------------------------------------------------------------
// Nodes table -- a typed roster
// ---------------------------------------------------------------------------

export function detectEcosystemNodes(table) {
  const { headers, rows } = table;
  const nodeIdx = col(headers, /^node$/i);
  const typeIdx = col(headers, /^node type$/i);
  if (nodeIdx === -1 || typeIdx === -1 || !rows.length) return null;

  const roleIdx = col(headers, /^role$/i);
  const evidenceIdx = col(headers, /^evidence/i);
  const confidenceIdx = col(headers, /^confidence/i);

  const nodes = [];
  for (const row of rows) {
    const name = row[nodeIdx]?.text;
    if (!name) return null;
    nodes.push({
      name,
      type: typeKey(row[typeIdx]?.text),
      typeRaw: row[typeIdx]?.text || "",
      role: roleIdx >= 0 ? row[roleIdx]?.text || "" : "",
      evidence: evidenceIdx >= 0 ? row[evidenceIdx]?.text || "" : "",
      confidence: confidenceIdx >= 0 ? row[confidenceIdx]?.text || "" : "",
    });
  }
  return { nodes };
}

export function EcosystemNodesExhibit({ data }) {
  const { nodes } = data;
  const byType = TYPE_LAYERS.concat("other")
    .map((t) => ({ type: t, members: nodes.filter((n) => n.type === t) }))
    .filter((g) => g.members.length);

  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>Ecosystem participants</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>{nodes.length} identified</span>
      </figcaption>
      <div style={{ padding: "4px 14px 12px" }}>
        {byType.map((group) => (
          <div key={group.type} style={{ marginTop: 10 }}>
            <p
              style={{
                margin: "0 0 4px",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.5,
                textTransform: "uppercase",
                color: theme.textMuted,
              }}
            >
              {group.type}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {group.members.map((n, i) => (
                <div key={i} style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 8, fontSize: 12 }}>
                  <span style={{ fontWeight: 600, color: theme.textPrimary }}>{n.name}</span>
                  {n.role && <span style={{ color: theme.textSecondary }}>{n.role}</span>}
                  {n.confidence && <Badge tone="muted">{n.confidence}</Badge>}
                  {n.evidence && (
                    <span style={{ fontSize: 11, color: theme.textMuted, flexBasis: "100%" }}>{n.evidence}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </figure>
  );
}

// ---------------------------------------------------------------------------
// Edges table -- the graph itself
// ---------------------------------------------------------------------------

export function detectEcosystemEdges(table) {
  const { headers, rows } = table;
  const fromIdx = col(headers, /^from$/i);
  const toIdx = col(headers, /^to$/i);
  const relIdx = col(headers, /^relationship$/i);
  if (fromIdx === -1 || toIdx === -1 || relIdx === -1 || !rows.length) return null;

  const evidenceIdx = col(headers, /^evidence/i);
  const confidenceIdx = col(headers, /^confidence/i);

  const edges = [];
  for (const row of rows) {
    const from = row[fromIdx]?.text;
    const to = row[toIdx]?.text;
    if (!from || !to) return null;
    edges.push({
      from,
      to,
      relationship: row[relIdx]?.text || "",
      evidence: evidenceIdx >= 0 ? row[evidenceIdx]?.text || "" : "",
      confidence: confidenceIdx >= 0 ? row[confidenceIdx]?.text || "" : "",
    });
  }
  return { edges };
}

const W = 820;
const NODE_H = 26;
const V_GAP = 10;
const COL_W = 196;
const PAD_Y = 14;

function layout(edges) {
  // Column 0 = anything that is only ever a source; column 2 = anything only
  // ever a target; column 1 = everything that is both (the connectors). A
  // crude but stable three-band layering that needs no simulation and no
  // node-type table.
  const sources = new Set(edges.map((e) => e.from));
  const targets = new Set(edges.map((e) => e.to));
  const all = [...new Set([...sources, ...targets])];

  const band = (n) => (sources.has(n) && targets.has(n) ? 1 : targets.has(n) ? 2 : 0);
  const columns = [[], [], []];
  for (const n of all.sort()) columns[band(n)].push(n);

  const pos = new Map();
  const colX = [10, 10 + COL_W + 110, 10 + 2 * (COL_W + 110)];
  columns.forEach((names, ci) => {
    names.forEach((name, ri) => {
      pos.set(name, { x: colX[ci], y: PAD_Y + ri * (NODE_H + V_GAP), col: ci });
    });
  });
  const height = PAD_Y * 2 + Math.max(1, ...columns.map((c) => c.length)) * (NODE_H + V_GAP);
  return { pos, columns, height };
}

export function EcosystemEdgesExhibit({ data }) {
  const { edges } = data;
  const { pos, height } = layout(edges);

  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>Ecosystem relationships</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>
          {edges.length} evidenced {edges.length === 1 ? "relationship" : "relationships"}
        </span>
      </figcaption>

      <div style={{ overflowX: "auto", padding: "6px 10px" }}>
        <svg width={W} height={height} role="img" aria-label="Technology ecosystem relationships">
          {edges.map((e, i) => {
            const a = pos.get(e.from);
            const b = pos.get(e.to);
            if (!a || !b) return null;
            const x1 = a.x + COL_W;
            const y1 = a.y + NODE_H / 2;
            const x2 = b.x;
            const y2 = b.y + NODE_H / 2;
            const mid = (x1 + x2) / 2;
            return (
              <g key={i}>
                <path
                  d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                  fill="none"
                  stroke={theme.border}
                  strokeWidth={1.5}
                />
                <title>
                  {e.from} → {e.to}: {e.relationship}
                  {e.evidence ? ` (${e.evidence})` : ""}
                </title>
              </g>
            );
          })}

          {[...pos.entries()].map(([name, p]) => (
            <g key={name}>
              <rect
                x={p.x}
                y={p.y}
                width={COL_W}
                height={NODE_H}
                rx={4}
                fill={p.col === 1 ? theme.orangeSoft : theme.surfaceMuted}
                stroke={p.col === 1 ? theme.orange : theme.border}
              />
              <text x={p.x + 8} y={p.y + NODE_H / 2 + 3.5} fontSize={11} fill={theme.textPrimary}>
                {name.length > 28 ? `${name.slice(0, 27)}…` : name}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Every edge in full. The picture shows structure; this carries the
          evidence, which is what makes an edge legitimate at all. */}
      <ul style={{ listStyle: "none", margin: 0, padding: "4px 14px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
        {edges.map((e, i) => (
          <li key={i} style={{ fontSize: 12, display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 6 }}>
            <span style={{ fontWeight: 600, color: theme.textPrimary }}>{e.from}</span>
            <span style={{ color: theme.textMuted }}>→</span>
            <span style={{ fontWeight: 600, color: theme.textPrimary }}>{e.to}</span>
            <span style={{ color: theme.textSecondary }}>{e.relationship}</span>
            {e.confidence && <Badge tone="muted">{e.confidence}</Badge>}
            {e.evidence && (
              <span style={{ fontSize: 11, color: theme.textMuted, flexBasis: "100%" }}>{e.evidence}</span>
            )}
          </li>
        ))}
      </ul>
    </figure>
  );
}
