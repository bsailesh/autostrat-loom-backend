// Capacity utilisation -- the highest-priority exhibit of the three. The
// finding it carries (one bucket over 100% behind a comfortable-looking
// aggregate) has to be visually obvious, not a number in a table: over-
// capacity bars read as over-capacity at a glance, the 100% line is marked,
// and the non-contractable flag is visible per bucket. Report 3's own
// "Capacity analysis" table (Bucket | Demand | Capacity | Utilisation |
// Contractable, plus an Aggregate row) is the exact real shape this parses.
import { AlertTriangle } from "lucide-react";
import { theme } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";

const HEADER_RE = { bucket: /bucket/i, utilisation: /utili[sz]ation/i, contractable: /contractable/i, demand: /demand/i, capacity: /^capacity$/i };

function findCol(headers, re) {
  return headers.findIndex((h) => re.test(h));
}

function parsePercent(text) {
  const m = String(text).replace(/,/g, "").match(/-?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
}

export function detectCapacityUtilisation(table) {
  const { headers, rows } = table;
  const bucketIdx = findCol(headers, HEADER_RE.bucket);
  const utilIdx = findCol(headers, HEADER_RE.utilisation);
  const contractableIdx = findCol(headers, HEADER_RE.contractable);
  if (bucketIdx === -1 || utilIdx === -1 || contractableIdx === -1) return null;
  const demandIdx = findCol(headers, HEADER_RE.demand);
  const capacityIdx = findCol(headers, HEADER_RE.capacity);
  if (!rows.length) return null;

  const buckets = [];
  let aggregate = null;
  for (const row of rows) {
    const name = row[bucketIdx]?.text;
    const utilisation = parsePercent(row[utilIdx]?.text);
    if (!name || utilisation === null) return null; // shape doesn't hold -- fall back to a plain table
    const entry = {
      name,
      utilisation,
      contractable: row[contractableIdx]?.text || "",
      demand: demandIdx >= 0 ? row[demandIdx]?.text : null,
      capacity: capacityIdx >= 0 ? row[capacityIdx]?.text : null,
    };
    if (/aggregate/i.test(name)) aggregate = entry;
    else buckets.push(entry);
  }
  if (!buckets.length) return null;
  return { buckets, aggregate };
}

function contractableBadge(raw) {
  const v = String(raw).replace(/\*/g, "").trim();
  if (/^no\b/i.test(v)) return <Badge tone="warning">Not contractable</Badge>;
  if (/^partial/i.test(v)) return <Badge tone="muted">Partial</Badge>;
  if (/^yes\b/i.test(v)) return <Badge tone="muted">Contractable</Badge>;
  return v ? <Badge tone="muted">{v}</Badge> : null;
}

export function CapacityUtilisationExhibit({ data }) {
  const { buckets, aggregate } = data;
  const maxUtil = Math.max(100, ...buckets.map((b) => b.utilisation));
  const scaleMax = Math.max(120, maxUtil + 10);
  const hundredPct = (100 / scaleMax) * 100;
  const overCapacity = buckets.filter((b) => b.utilisation >= 100);

  return (
    <div
      style={{
        border: `1px solid ${theme.border}`,
        borderRadius: 12,
        padding: "18px 20px 16px",
        margin: "4px 0 20px",
        background: theme.surface,
      }}
    >
      <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: theme.textSecondary, margin: "0 0 4px" }}>
        Capacity utilisation by bucket
      </p>

      {overCapacity.length > 0 && (
        <p style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700, color: theme.danger, margin: "6px 0 16px" }}>
          <AlertTriangle size={15} />
          {overCapacity.length === 1
            ? `${overCapacity[0].name} is over capacity (${overCapacity[0].utilisation}%)`
            : `${overCapacity.length} buckets are over capacity`}
        </p>
      )}

      <div style={{ position: "relative", paddingTop: 6 }}>
        {/* 100% reference line, spanning the full bar stack */}
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 22,
            left: `${hundredPct}%`,
            width: 2,
            background: theme.textPrimary,
            opacity: 0.35,
            zIndex: 1,
          }}
        />
        <span
          style={{
            position: "absolute",
            top: -2,
            left: `${hundredPct}%`,
            transform: "translateX(-50%)",
            fontSize: 10,
            fontWeight: 700,
            color: theme.textSecondary,
            background: theme.surface,
            padding: "0 4px",
          }}
        >
          100%
        </span>

        <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
          {buckets.map((b) => {
            const over = b.utilisation >= 100;
            const fillPct = Math.min(b.utilisation, scaleMax);
            const barColor = over ? theme.danger : theme.orange;
            return (
              <div key={b.name}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>{b.name}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        fontSize: over ? 15 : 13,
                        fontWeight: 700,
                        color: over ? theme.danger : theme.textPrimary,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      {over && <AlertTriangle size={13} />}
                      {b.utilisation}%
                    </span>
                    {contractableBadge(b.contractable)}
                  </span>
                </div>
                <div style={{ position: "relative", height: 16, background: theme.surfaceMuted, borderRadius: 5, overflow: "hidden", border: `1px solid ${theme.border}` }}>
                  {/* Base fill, capped at 100% */}
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: `${(Math.min(fillPct, 100) / scaleMax) * 100}%`,
                      background: barColor,
                    }}
                  />
                  {/* Overage segment beyond 100%, hatched so the excess itself is legible as an amount */}
                  {over && (
                    <div
                      style={{
                        position: "absolute",
                        left: `${hundredPct}%`,
                        top: 0,
                        bottom: 0,
                        width: `${((fillPct - 100) / scaleMax) * 100}%`,
                        background: `repeating-linear-gradient(45deg, ${theme.danger}, ${theme.danger} 4px, #ffffff55 4px, #ffffff55 8px)`,
                      }}
                    />
                  )}
                </div>
                {(b.demand != null || b.capacity != null) && (
                  <p style={{ fontSize: 11, color: theme.textMuted, margin: "3px 0 0" }}>
                    {b.demand} of {b.capacity} used
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {aggregate && (
        <p style={{ fontSize: 11.5, color: theme.textMuted, margin: "18px 0 0", paddingTop: 10, borderTop: `1px solid ${theme.border}` }}>
          Aggregate: {aggregate.utilisation}%{aggregate.demand != null ? ` (${aggregate.demand} of ${aggregate.capacity})` : ""} — shown for
          reference only; the report may caution this figure is misleading. Judge each bucket above, not this line.
        </p>
      )}
    </div>
  );
}
