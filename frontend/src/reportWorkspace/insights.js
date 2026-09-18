// Pull the structured opening out of a report's Markdown so it can be rendered
// as a dedicated box, and hand back the remaining body for normal rendering.
//
// The agent's output is prose, not JSON, so this is deliberately tolerant: if a
// pattern isn't found we just fall back to rendering everything as Markdown.

const HEADING_RE = /^#{1,6}\s+(.*)$/;

function splitLines(md) {
  return (md || "").replace(/\r\n/g, "\n").split("\n");
}

// Returns { before, section, after } for the first heading whose text matches
// `nameRe`. `section` excludes the heading line itself.
function sliceSection(md, nameRe) {
  const lines = splitLines(md);
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(HEADING_RE);
    if (m && nameRe.test(m[1].trim())) {
      start = i;
      break;
    }
  }
  if (start === -1) return null;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (HEADING_RE.test(lines[i]) || /^-{3,}\s*$/.test(lines[i].trim())) {
      end = i;
      break;
    }
  }
  return {
    before: lines.slice(0, start).join("\n"),
    section: lines.slice(start + 1, end).join("\n").trim(),
    after: lines.slice(end).join("\n"),
    headingText: lines[start].match(HEADING_RE)[1].trim(),
  };
}

// --- leading strap line: **... | Subject: ... | Evidence base: ...** ---
export function liftStrap(md) {
  const lines = splitLines(md);
  let i = 0;
  while (i < lines.length && lines[i].trim() === "") i++;
  const line = (lines[i] || "").trim();
  const m = line.match(/^\*\*(.+?)\*\*$/);
  if (m && /subject:|evidence base|synthesis date|research date/i.test(m[1])) {
    return { strap: m[1].trim(), body: [...lines.slice(0, i), ...lines.slice(i + 1)].join("\n") };
  }
  return { strap: null, body: md };
}

// --- Governing Insight (Report 1) ---
const SCQA_KEYS = ["Situation", "Complication", "Question", "Answer"];

export function extractGoverningInsight(md) {
  const sliced = sliceSection(md, /governing insight/i);
  if (!sliced) return null;
  const { section, before, after } = sliced;

  const parts = {};
  for (const key of SCQA_KEYS) {
    const re = new RegExp(
      `\\*\\*${key}\\.?\\*\\*\\s*([\\s\\S]*?)(?=\\n\\s*\\*\\*(?:${SCQA_KEYS.join("|")})\\b|$)`,
      "i"
    );
    const m = section.match(re);
    if (m) parts[key.toLowerCase()] = cleanInline(m[1]);
  }

  const found = SCQA_KEYS.filter((k) => parts[k.toLowerCase()]);
  if (found.length < 2) {
    // Couldn't parse the four lines — show the raw section text instead.
    return { raw: section, parts: null, body: joinBody(before, after) };
  }
  return { raw: null, parts, body: joinBody(before, after) };
}

// --- Key Insights (Reports 2–9) ---
export function extractKeyInsights(md) {
  const sliced = sliceSection(md, /key insights?/i);
  if (!sliced) return null;
  const { section, before, after } = sliced;

  const bullets = [];
  for (const rawLine of section.split("\n")) {
    const bm = rawLine.match(/^\s*[-*]\s+(.*)$/);
    if (!bm) {
      // continuation of the previous bullet
      if (bullets.length && rawLine.trim()) bullets[bullets.length - 1].text += " " + rawLine.trim();
      continue;
    }
    const { text, level } = stripConfidence(bm[1].trim());
    bullets.push({ text: cleanInline(text), level });
  }

  if (bullets.length === 0) return { bullets: null, raw: section, body: joinBody(before, after) };
  return { bullets, raw: null, body: joinBody(before, after) };
}

// --- helpers ---

function joinBody(before, after) {
  return [before.trim(), after.trim()].filter(Boolean).join("\n\n").trim();
}

// Remove a confidence tag from the start or end of a Key Insights bullet and
// return the level it carried (or null).
function stripConfidence(text) {
  let level = null;
  let t = text;

  // start: **[High]** ...   or   **High —** ...
  const startRe = /^\*\*\[?\s*(high|medium|med|low)\b[^\]*]*\]?\.?\*\*[\s:—–-]*/i;
  const sm = t.match(startRe);
  if (sm) {
    level = norm(sm[1]);
    t = t.slice(sm[0].length);
  }

  // end: *(Confidence: High ...)*   ·   (Confidence: High)   ·   — **High**
  const endRes = [
    /[\s—–-]*\*?\(?\s*confidence[:\s]+(high|medium|med|low)\b[^)*]*\)?\*?\s*$/i,
    /[\s—–-]*\*\*\(?\s*(high|medium|med|low)\b[^)*]*\)?\*\*\s*$/i,
    /\s*\((high|medium|med|low)\b[^)]*\)\s*$/i,
  ];
  for (const re of endRes) {
    const em = t.match(re);
    if (em) {
      if (!level) level = norm(em[1]);
      t = t.slice(0, em.index).trim();
      break;
    }
  }

  if (!level) {
    const anyRe = /\bconfidence[:\s]+(high|medium|med|low)\b/i;
    const am = t.match(anyRe);
    if (am) level = norm(am[1]);
  }
  return { text: t.trim(), level };
}

function norm(w) {
  const l = w.toLowerCase();
  if (l.startsWith("med")) return "Medium";
  return l[0].toUpperCase() + l.slice(1);
}

// Trim wrapping bold/italic markers and stray leading punctuation from a lifted
// fragment so it reads cleanly as plain text in the box.
function cleanInline(s) {
  return (s || "")
    .replace(/\s+/g, " ")
    .replace(/^[\s—–\-:]+/, "")
    .replace(/^\*\*(.+?)\*\*$/, "$1")
    .replace(/^\*(.+?)\*$/, "$1")
    .trim();
}
