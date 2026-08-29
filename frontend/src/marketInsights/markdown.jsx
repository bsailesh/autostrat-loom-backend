import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { theme, MONO } from "../theme.js";
import { ConfidenceTag, matchConfidence } from "../components/ConfidenceTag.jsx";

// Flatten a react-markdown children array to plain text.
function nodeText(children) {
  if (children == null) return "";
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(nodeText).join("");
  if (children.props) return nodeText(children.props.children);
  return "";
}

const SO_WHAT_RE = /^\s*(?:[—–-]\s*)?so\s*what\b[:.\s—–-]*/i;

function SoWhat({ children }) {
  return (
    <span
      style={{
        display: "inline",
        color: theme.orange,
        fontStyle: "italic",
      }}
    >
      <span style={{ fontWeight: 700, fontStyle: "normal" }}>→ </span>
      {children}
    </span>
  );
}

// react-markdown v9 passes a `node` prop to every component; each renderer below
// destructures it out so it never reaches a DOM element.
const components = {
  h1: ({ node, ...p }) => <h2 style={{ fontSize: 20, fontWeight: 700, margin: "26px 0 10px", color: theme.textPrimary }} {...p} />,
  h2: ({ node, ...p }) => <h2 style={{ fontSize: 17, fontWeight: 700, margin: "24px 0 8px", color: theme.textPrimary }} {...p} />,
  h3: ({ node, ...p }) => <h3 style={{ fontSize: 14.5, fontWeight: 700, margin: "18px 0 6px", color: theme.textPrimary }} {...p} />,
  h4: ({ node, ...p }) => <h4 style={{ fontSize: 13, fontWeight: 700, margin: "14px 0 4px", color: theme.textSecondary }} {...p} />,
  p: ({ node, ...p }) => <p style={{ fontSize: 13.5, lineHeight: 1.65, margin: "0 0 12px", color: theme.textPrimary }} {...p} />,
  ul: ({ node, ...p }) => <ul style={{ margin: "0 0 12px", paddingLeft: 20 }} {...p} />,
  ol: ({ node, ...p }) => <ol style={{ margin: "0 0 12px", paddingLeft: 20 }} {...p} />,
  li: ({ node, ...p }) => <li style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 5px", color: theme.textPrimary }} {...p} />,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer noopener" style={{ color: theme.orange, textDecoration: "underline" }}>
      {children}
    </a>
  ),
  hr: () => <hr style={{ border: "none", borderTop: `1px solid ${theme.border}`, margin: "20px 0" }} />,
  blockquote: ({ node, ...p }) => (
    <blockquote
      style={{
        margin: "0 0 12px",
        padding: "6px 0 6px 14px",
        borderLeft: `3px solid ${theme.border}`,
        color: theme.textSecondary,
        fontStyle: "italic",
      }}
      {...p}
    />
  ),

  // Confidence tags land inside **bold** in the agent's output.
  strong: ({ children }) => {
    const level = matchConfidence(nodeText(children));
    if (level) return <ConfidenceTag level={level} />;
    return <strong style={{ fontWeight: 700 }}>{children}</strong>;
  },

  // "so what" implications land inside *italics*.
  em: ({ children }) => {
    const text = nodeText(children);
    if (SO_WHAT_RE.test(text)) {
      return <SoWhat>{text.replace(SO_WHAT_RE, "")}</SoWhat>;
    }
    return <em style={{ fontStyle: "italic" }}>{children}</em>;
  },

  // Exhibits: the agent emits TAM/SAM/SOM as an ASCII diagram in a fenced block,
  // and Harvey Balls / trend tables / the 3-column format as GFM tables. Render
  // the fenced block as a proper figure, and tables with themed chrome.
  // Fenced block: pull the raw text out of the inner <code> so the inline-`code`
  // renderer below never applies to block content (react-markdown v9 dropped the
  // `inline` prop, so this is the reliable split).
  pre: ({ children }) => {
    const codeEl = Array.isArray(children) ? children[0] : children;
    const text = codeEl && codeEl.props ? nodeText(codeEl.props.children) : nodeText(children);
    return (
      <div style={{ overflowX: "auto", margin: "0 0 16px" }}>
        <pre
          style={{
            fontFamily: MONO,
            fontSize: 12,
            lineHeight: 1.5,
            background: theme.surfaceMuted,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            padding: "12px 14px",
            margin: 0,
            color: theme.textPrimary,
            whiteSpace: "pre",
          }}
        >
          {text}
        </pre>
      </div>
    );
  },
  code: ({ children }) => (
    <code
      style={{
        fontFamily: MONO,
        fontSize: 12,
        background: theme.surfaceMuted,
        border: `1px solid ${theme.border}`,
        borderRadius: 5,
        padding: "1px 5px",
      }}
    >
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div style={{ overflowX: "auto", margin: "0 0 16px", border: `1px solid ${theme.border}`, borderRadius: 10 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>{children}</table>
    </div>
  ),
  thead: ({ node, ...p }) => <thead style={{ background: theme.surfaceMuted }} {...p} />,
  tbody: ({ node, ...p }) => <tbody {...p} />,
  tr: ({ node, ...p }) => <tr {...p} />,
  th: ({ node, ...p }) => (
    <th
      style={{
        textAlign: "left",
        fontWeight: 700,
        padding: "8px 10px",
        borderBottom: `1px solid ${theme.border}`,
        color: theme.textSecondary,
        whiteSpace: "nowrap",
      }}
      {...p}
    />
  ),
  td: ({ node, ...p }) => (
    <td style={{ padding: "8px 10px", borderBottom: `1px solid ${theme.border}`, verticalAlign: "top", lineHeight: 1.5 }} {...p} />
  ),
};

export function ReportMarkdown({ children }) {
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {children || ""}
    </Markdown>
  );
}

export { nodeText };
