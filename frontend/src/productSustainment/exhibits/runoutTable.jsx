// Runout table -- the primary exhibit. Matches the customer's own
// component table: on hand, open POs, supplier quantities, runout year and
// month, end inventory by year, risk type, lifecycle status, affected LRUs.
// Filterable by component, LRU, product line, program, lifecycle status and
// runout year.
//
// Every number here is computed by product_sustainment/compute.py and
// written into the report by code (results.py), never by the model. The
// header contract is results.RUNOUT_TABLE_FIXED_HEADERS + "End YYYY" columns.
//
// `RunoutTableView` is also used for the run's FULL table (GET
// /runs/{id}/runout), since reports carry only the most urgent rows.
import { useMemo, useState } from "react";
import { theme, FONT } from "../../theme.js";
import { Badge } from "../../components/atoms.jsx";

const REQUIRED = ["Component", "Runout", "LTB status", "Affected LRUs", "On hand"];

const STATUS_TONE = { Critical: "danger", Watch: "warning", OK: "success" };

function num(raw) {
  const n = Number(String(raw ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function lruList(cell) {
  return String(cell || "")
    .replace(/\s*\(\+\d+ more[^)]*\)\s*$/, "")
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s && s !== "—");
}

export function detectRunoutTable(table) {
  const { headers, rows } = table;
  const idx = Object.fromEntries(headers.map((h, i) => [h.trim(), i]));
  if (!REQUIRED.every((h) => h in idx) || !rows.length) return null;
  const years = headers.map((h) => h.trim().match(/^End (\d{4})$/)).filter(Boolean).map((m) => m[1]);
  const get = (row, h) => (h in idx ? row[idx[h]]?.text ?? "" : "");
  const parsed = [];
  for (const row of rows) {
    const component = get(row, "Component");
    if (!component) return null;
    const runout = get(row, "Runout");
    const y = runout.match(/(\d{4})$/);
    parsed.push({
      component,
      level: get(row, "Level"),
      description: get(row, "Description"),
      on_hand: num(get(row, "On hand")),
      from_higher_level_stock: num(get(row, "From higher-level stock")),
      open_po: num(get(row, "Open POs")),
      supplier_qty: num(get(row, "Supplier qty (not counted)")),
      counted_supply: num(get(row, "Counted supply")),
      supplier_on_order: num(get(row, "Supplier on order")),
      supplier_wip: num(get(row, "Supplier WIP")),
      runout,
      runout_year: y ? Number(y[1]) : null,
      ltb_status: get(row, "LTB status"),
      quantity_required: num(get(row, "Qty required")),
      risk_type: get(row, "Risk type"),
      lifecycle_status: get(row, "Lifecycle status"),
      affected_lrus: lruList(get(row, "Affected LRUs")),
      lru_cell: get(row, "Affected LRUs"),
      product_lines: get(row, "Product lines"),
      programs: get(row, "Programs"),
      end_inventory: Object.fromEntries(years.map((yr) => [yr, num(get(row, `End ${yr}`))])),
    });
  }
  return { rows: parsed, years, caption: "Component runout" };
}

const fmt = (n) => (n === null || n === undefined ? "—" : n.toLocaleString());

function Select({ label, value, options, onChange }) {
  return (
    <label style={{ fontSize: 11, color: theme.textMuted, display: "flex", flexDirection: "column", gap: 2 }}>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
              style={{ fontFamily: FONT, fontSize: 12, padding: "3px 5px", border: `1px solid ${theme.border}`, borderRadius: 4, maxWidth: 160 }}>
        <option value="">All</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

const splitList = (s) => String(s || "").split(",").map((x) => x.trim()).filter((x) => x && x !== "—");

export function RunoutTableView({ rows, years, caption, note }) {
  const [f, setF] = useState({ text: "", lru: "", line: "", program: "", lifecycle: "", year: "" });
  const set = (k) => (v) => setF((prev) => ({ ...prev, [k]: v }));

  const options = useMemo(() => {
    const uniq = (xs) => [...new Set(xs)].sort();
    return {
      lru: uniq(rows.flatMap((r) => r.affected_lrus)),
      line: uniq(rows.flatMap((r) => splitList(r.product_lines))),
      program: uniq(rows.flatMap((r) => splitList(r.programs))),
      lifecycle: uniq(rows.flatMap((r) => splitList(r.lifecycle_status))),
      year: uniq(rows.map((r) => r.runout_year).filter(Boolean).map(String)),
    };
  }, [rows]);

  const shown = rows.filter((r) =>
    (!f.text || `${r.component} ${r.description}`.toLowerCase().includes(f.text.toLowerCase())) &&
    (!f.lru || r.affected_lrus.includes(f.lru)) &&
    (!f.line || splitList(r.product_lines).includes(f.line)) &&
    (!f.program || splitList(r.programs).includes(f.program)) &&
    (!f.lifecycle || splitList(r.lifecycle_status).includes(f.lifecycle)) &&
    (!f.year || String(r.runout_year) === f.year)
  );

  const th = { padding: "6px 8px", textAlign: "left", fontWeight: 600, color: theme.textMuted, whiteSpace: "nowrap", fontSize: 11 };
  const td = { padding: "6px 8px", whiteSpace: "nowrap", fontSize: 12 };

  return (
    <figure style={{ margin: "18px 0", border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.surface, overflow: "hidden" }}>
      <figcaption style={{ padding: "10px 14px", borderBottom: `1px solid ${theme.border}`, background: theme.surfaceMuted }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{caption}</span>
        <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 8 }}>
          computed by the platform · {shown.length.toLocaleString()} of {rows.length.toLocaleString()} shown
        </span>
        {note && <p style={{ margin: "4px 0 0", fontSize: 11, color: theme.textMuted }}>{note}</p>}
      </figcaption>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: "10px 14px", borderBottom: `1px solid ${theme.border}` }}>
        <label style={{ fontSize: 11, color: theme.textMuted, display: "flex", flexDirection: "column", gap: 2 }}>
          Component
          <input value={f.text} onChange={(e) => set("text")(e.target.value)} placeholder="Search"
                 style={{ fontFamily: FONT, fontSize: 12, padding: "3px 6px", border: `1px solid ${theme.border}`, borderRadius: 4 }} />
        </label>
        <Select label="LRU" value={f.lru} options={options.lru} onChange={set("lru")} />
        <Select label="Product line" value={f.line} options={options.line} onChange={set("line")} />
        <Select label="Program" value={f.program} options={options.program} onChange={set("program")} />
        <Select label="Lifecycle status" value={f.lifecycle} options={options.lifecycle} onChange={set("lifecycle")} />
        <Select label="Runout year" value={f.year} options={options.year} onChange={set("year")} />
      </div>
      <div style={{ overflowX: "auto", maxHeight: 560, overflowY: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead style={{ position: "sticky", top: 0, background: theme.surface }}>
            <tr>
              {["Component", "On hand", "From cards/LRUs", "Open POs", "On order", "WIP", "Counted supply", "Supplier qty (not counted)", "Runout", "LTB status",
                "Qty required", ...years.map((y) => `End ${y}`), "Risk", "Lifecycle", "Affected LRUs"].map((h) => <th key={h} style={th}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={`${r.component}-${i}`} style={{ borderTop: `1px solid ${theme.border}`, background: i % 2 ? theme.surfaceMuted : theme.surface }}>
                <td style={td}>
                  <strong>{r.component}</strong>
                  {r.description && <span style={{ color: theme.textMuted }}> · {r.description}</span>}
                </td>
                <td style={td}>{fmt(r.on_hand)}</td>
                <td style={td}>{fmt(r.from_higher_level_stock)}</td>
                <td style={td}>{fmt(r.open_po)}</td>
                <td style={td}>{fmt(r.supplier_on_order)}</td>
                <td style={td}>{fmt(r.supplier_wip)}</td>
                <td style={{ ...td, fontWeight: 600 }} title="Exactly what the runout depletes">{fmt(r.counted_supply)}</td>
                <td style={{ ...td, color: theme.textMuted }} title="Reported, not counted as available">{fmt(r.supplier_qty)}</td>
                <td style={{ ...td, fontWeight: 600, color: r.runout_year ? theme.textPrimary : theme.textMuted }}>{r.runout}</td>
                <td style={td}><Badge tone={STATUS_TONE[r.ltb_status] || "muted"}>{r.ltb_status || "—"}</Badge></td>
                <td style={td}>{fmt(r.quantity_required)}</td>
                {years.map((y) => {
                  const v = r.end_inventory[y];
                  return <td key={y} style={{ ...td, color: v !== null && v < 0 ? theme.danger : theme.textPrimary }}>{fmt(v)}</td>;
                })}
                <td style={td}>{r.risk_type || "—"}</td>
                <td style={td}>{r.lifecycle_status || "—"}</td>
                <td style={{ ...td, whiteSpace: "normal", minWidth: 160 }}>{r.lru_cell || r.affected_lrus.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ margin: 0, padding: "8px 14px", fontSize: 11, color: theme.textMuted, borderTop: `1px solid ${theme.border}` }}>
        Negative year-end positions are shortfalls. Quantities required cover demand through the end of the supplied
        forecast horizon, not necessarily end of life.
      </p>
    </figure>
  );
}

export function RunoutTableExhibit({ data }) {
  return <RunoutTableView rows={data.rows} years={data.years} caption={data.caption} />;
}

// API rows (GET /runs/{id}/runout) -> the same shape the view takes.
export function rowsFromApi(apiRows) {
  return apiRows.map((r) => ({
    ...r,
    end_inventory: r.end_inventory || {},
    lru_cell: (r.affected_lrus || []).join(", "),
  }));
}
