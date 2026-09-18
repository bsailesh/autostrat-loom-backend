// Dependency graph -- Report 5's "Project | Prerequisites | Blocks |
// Parallel-safe | Basis" table as a simple layered node/edge diagram. Kept
// deliberately plain (no graph library, straight-line edges, fixed grid
// layout computed arithmetically) -- this exhibit matters less than
// capacity utilisation.
import { theme } from "../../theme.js";

const NONE_RE = /^(—|-|none|n\/a)?$/i;

function splitList(text) {
  if (!text) return [];
  return text
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s && !NONE_RE.test(s))
    .map((s) => s.replace(/\s*\(.*\)$/, "")); // "P-08 (partial)" -> "P-08"
}

export function detectDependencyGraph(table) {
  const { headers, rows } = table;
  const projectIdx = headers.findIndex((h) => /^project/i.test(h));
  const prereqIdx = headers.findIndex((h) => /prerequisite/i.test(h));
  const blocksIdx = headers.findIndex((h) => /block/i.test(h));
  if (projectIdx === -1 || prereqIdx === -1 || blocksIdx === -1) return null;
  if (!rows.length) return null;
  const parallelIdx = headers.findIndex((h) => /parallel/i.test(h));
  const basisIdx = headers.findIndex((h) => /basis/i.test(h));

  const nodes = [];
  for (const row of rows) {
    const key = row[projectIdx]?.text;
    if (!key) return null;
    nodes.push({
      key,
      prerequisites: splitList(row[prereqIdx]?.text),
      blocks: splitList(row[blocksIdx]?.text),
      parallelSafe: parallelIdx >= 0 ? row[parallelIdx]?.text : null,
      basis: basisIdx >= 0 ? row[basisIdx]?.text : null,
    });
  }

  // Iterative topological layering. Anything still unresolved after N
  // passes is a cycle (or references a project outside this table) --
  // dumped into a trailing layer rather than looping forever.
  const layerOf = {};
  const keys = nodes.map((n) => n.key);
  for (let pass = 0; pass < keys.length + 1; pass++) {
    let progressed = false;
    for (const n of nodes) {
      if (layerOf[n.key] !== undefined) continue;
      const relevant = n.prerequisites.filter((p) => keys.includes(p));
      if (relevant.length === 0) {
        layerOf[n.key] = 0;
        progressed = true;
      } else if (relevant.every((p) => layerOf[p] !== undefined)) {
        layerOf[n.key] = 1 + Math.max(...relevant.map((p) => layerOf[p]));
        progressed = true;
      }
    }
    if (!progressed) break;
  }
  const unresolved = keys.filter((k) => layerOf[k] === undefined);
  if (unresolved.length) {
    const maxLayer = Math.max(-1, ...Object.values(layerOf));
    unresolved.forEach((k) => (layerOf[k] = maxLayer + 1));
  }

  const layers = [];
  for (const n of nodes) {
    (layers[layerOf[n.key]] ||= []).push(n);
  }

  return { nodes, layers, cyclic: unresolved };
}

const NODE_W = 168;
const NODE_H = 60;
const COL_GAP = 56;
const ROW_GAP = 18;

export function DependencyGraphExhibit({ data }) {
  const { nodes, layers, cyclic } = data;
  const positions = {};
  layers.forEach((layerNodes, colIdx) => {
    layerNodes.forEach((n, rowIdx) => {
      positions[n.key] = {
        x: colIdx * (NODE_W + COL_GAP),
        y: rowIdx * (NODE_H + ROW_GAP),
      };
    });
  });
  const width = layers.length * (NODE_W + COL_GAP) - COL_GAP;
  const height = Math.max(...layers.map((l) => l.length)) * (NODE_H + ROW_GAP) - ROW_GAP;

  const edges = [];
  for (const n of nodes) {
    for (const p of n.prerequisites) {
      if (positions[p] && positions[n.key]) edges.push({ from: p, to: n.key });
    }
  }

  return (
    <div style={{ margin: "4px 0 20px" }}>
      <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: theme.textSecondary, margin: "0 0 12px" }}>
        Dependency graph
      </p>
      <div style={{ position: "relative", width, height: Math.max(height, NODE_H), overflowX: "auto" }}>
        <svg width={width} height={Math.max(height, NODE_H)} style={{ position: "absolute", top: 0, left: 0, overflow: "visible" }}>
          <defs>
            <marker id="dep-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" fill={theme.textMuted} />
            </marker>
          </defs>
          {edges.map((e, i) => {
            const from = positions[e.from];
            const to = positions[e.to];
            const x1 = from.x + NODE_W;
            const y1 = from.y + NODE_H / 2;
            const x2 = to.x;
            const y2 = to.y + NODE_H / 2;
            const midX = (x1 + x2) / 2;
            return (
              <path
                key={i}
                d={`M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`}
                fill="none"
                stroke={theme.textMuted}
                strokeWidth={1.5}
                markerEnd="url(#dep-arrow)"
              />
            );
          })}
        </svg>
        {nodes.map((n) => {
          const pos = positions[n.key];
          const inCycle = cyclic.includes(n.key);
          return (
            <div
              key={n.key}
              style={{
                position: "absolute",
                left: pos.x,
                top: pos.y,
                width: NODE_W,
                height: NODE_H,
                border: `1px solid ${inCycle ? theme.warning : theme.border}`,
                background: theme.surface,
                borderRadius: 8,
                padding: "6px 10px",
                boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
              }}
            >
              <p style={{ fontSize: 12.5, fontWeight: 700, color: theme.textPrimary, margin: 0 }}>{n.key}</p>
              {n.basis && /infer/i.test(n.basis) && (
                <p style={{ fontSize: 10, color: theme.warning, margin: "2px 0 0" }}>Inferred — confirm</p>
              )}
              {n.parallelSafe && /^no/i.test(n.parallelSafe) && (
                <p style={{ fontSize: 10, color: theme.textMuted, margin: "2px 0 0" }}>Not parallel-safe</p>
              )}
              {inCycle && <p style={{ fontSize: 10, color: theme.warning, margin: "2px 0 0" }}>Unresolved order</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
