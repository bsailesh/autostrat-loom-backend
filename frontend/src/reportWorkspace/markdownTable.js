// Finds GFM pipe tables in raw Markdown text -- the shared primitive every
// agent's exhibit detectors are built on (see exhibitRegistry.js). The
// agent's output is prose with real Markdown tables, not JSON, so this is
// deliberately line-based and tolerant, matching insights.js's own approach
// to parsing agent prose rather than a strict grammar.

function splitLines(md) {
  return (md || "").replace(/\r\n/g, "\n").split("\n");
}

const ROW_RE = /^\s*\|?(.+?)\|?\s*$/;
const SEPARATOR_RE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function splitCells(line) {
  const m = line.match(ROW_RE);
  const inner = m ? m[1] : line;
  // Split on unescaped pipes.
  return inner.split(/(?<!\\)\|/).map((c) => c.trim());
}

function isTableRow(line) {
  return line.includes("|") && line.trim().length > 0;
}

function parseCell(raw) {
  const boldMatch = raw.match(/^\*\*(.+)\*\*$/);
  if (boldMatch) return { text: boldMatch[1].trim(), bold: true, raw };
  return { text: raw.trim(), bold: false, raw };
}

// Returns every table found, each as:
//   { lineStart, lineEnd, headers: string[], rows: Cell[][] }
// lineStart/lineEnd are inclusive 0-based line indices into splitLines(md),
// so a caller can reconstruct "before"/"between"/"after" text around them.
export function findMarkdownTables(md) {
  const lines = splitLines(md);
  const tables = [];
  let i = 0;
  while (i < lines.length - 1) {
    if (isTableRow(lines[i]) && SEPARATOR_RE.test(lines[i + 1])) {
      const headers = splitCells(lines[i]);
      let j = i + 2;
      const rows = [];
      while (j < lines.length && isTableRow(lines[j])) {
        rows.push(splitCells(lines[j]).map(parseCell));
        j++;
      }
      tables.push({ lineStart: i, lineEnd: j - 1, headers, rows });
      i = j;
    } else {
      i++;
    }
  }
  return tables;
}

export { splitLines };
