// Factory for a per-agent exhibit registry. Deliberately not a shared
// singleton -- each agent (marketInsights/exhibits/index.js,
// strategySynthesis/exhibits/index.js) calls this to get its OWN instance
// and registers only its own detectors into it, so one agent's renderer
// module can never be reached, mis-triggered, or broken by another's.
//
// A detector is `{ test(table) => data|null, Component }`. `table` is one
// table found by markdownTable.js's findMarkdownTables: { headers, rows }.
// `test` must return null unless it is fully confident it found *and
// correctly parsed* its target table -- a header-name match alone is not
// enough. On null, that table is left as an ordinary Markdown table for
// reportWorkspace/markdown.jsx's themed `table` renderer -- never ASCII art,
// never a half-rendered exhibit.
import { findMarkdownTables } from "./markdownTable.js";

export function createExhibitRegistry() {
  const detectors = [];
  return {
    register(test, Component) {
      detectors.push({ test, Component });
    },

    // Walks the report body once. Returns an ordered list of segments:
    //   { kind: "markdown", text } | { kind: "exhibit", Component, data }
    // Non-exhibit lines are grouped back into markdown segments so prose
    // around an exhibit renders exactly where it was written.
    resolve(markdown) {
      const lines = (markdown || "").replace(/\r\n/g, "\n").split("\n");
      const tables = findMarkdownTables(markdown);

      // Match each table to the first detector that claims it.
      const matches = []; // { lineStart, lineEnd, Component, data }
      for (const table of tables) {
        for (const { test, Component } of detectors) {
          let data;
          try {
            data = test(table);
          } catch {
            data = null; // a detector must never crash report rendering
          }
          if (data) {
            matches.push({ lineStart: table.lineStart, lineEnd: table.lineEnd, Component, data });
            break;
          }
        }
      }
      matches.sort((a, b) => a.lineStart - b.lineStart);

      const segments = [];
      let cursor = 0;
      let pendingMarkdown = [];
      const flushMarkdown = () => {
        if (pendingMarkdown.length) {
          const text = pendingMarkdown.join("\n").trim();
          if (text) segments.push({ kind: "markdown", text });
          pendingMarkdown = [];
        }
      };
      for (const m of matches) {
        pendingMarkdown.push(...lines.slice(cursor, m.lineStart));
        flushMarkdown();
        segments.push({ kind: "exhibit", Component: m.Component, data: m.data });
        cursor = m.lineEnd + 1;
      }
      pendingMarkdown.push(...lines.slice(cursor));
      flushMarkdown();

      return segments;
    },
  };
}
