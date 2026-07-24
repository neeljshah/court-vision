"use client";
// Receipt -- the honesty brand, restyled for the Reading Room (DESIGN Sec. 4).
// Resting: a QUIET inline mono stamp (verdict dot + as_of), never a loud badge.
// Hover / focus / touch: a popover with the measurement label, source_artifact
// path, n, corpus, and a "what does verified mean?" link to /analytics/the-loop
// (the shipped discipline surface -- leak-free gate, ledger, honesty exhibit; the
// standalone /analytics/method page in the spec was never built).
import { useState, type CSSProperties } from "react";
import Link from "next/link";
import { VerdictDot, type Verdict } from "./VerdictDot";

export interface ReceiptData {
  value?: string; // the number this receipt stamps (optional)
  label?: string; // measurement label, e.g. CONFIRMED_LOCAL / descriptive_only
  sourceArtifact: string; // committed artifact path
  asOf?: string; // e.g. 2026-04-12
  n?: number; // sample size, when known
  corpus?: string; // corpus name, when known
  verdict: Verdict;
}

function basename(p: string): string {
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

const stamp: CSSProperties = {
  border: 0,
  background: "transparent",
  padding: 0,
  margin: 0,
  font: "inherit",
  fontFamily: "var(--font-mono)",
  fontSize: "11.5px",
  color: "var(--ink-3)",
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  cursor: "help",
  lineHeight: 1.3,
  verticalAlign: "baseline",
};

const pop: CSSProperties = {
  position: "absolute",
  left: 0,
  top: "calc(100% + 6px)",
  zIndex: 40,
  minWidth: 220,
  maxWidth: 300,
  background: "var(--paper-raised)",
  border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-card, 10px)",
  boxShadow: "var(--shadow-raise)",
  padding: "12px 14px",
  fontFamily: "var(--font-sans)",
  fontSize: 13,
  color: "var(--ink-2)",
  lineHeight: 1.5,
  textAlign: "left",
  cursor: "auto",
};

const path: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "11.5px",
  color: "var(--ink-3)",
  wordBreak: "break-all",
  display: "block",
  marginTop: 6,
};

export function Receipt(r: ReceiptData) {
  const [open, setOpen] = useState(false);
  // Quiet resting token: prefer as_of, else value, else the artifact basename.
  const resting = r.asOf || r.value || basename(r.sourceArtifact);
  const dashed = r.verdict === "not_testable";

  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        style={{
          ...stamp,
          ...(dashed
            ? { borderBottom: "1px dashed var(--not-testable)", paddingBottom: 1 }
            : null),
        }}
        aria-expanded={open}
        aria-label={`Receipt: ${r.label || r.verdict} for ${resting}`}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      >
        <VerdictDot verdict={r.verdict} />
        {resting}
      </button>
      {open ? (
        <span role="tooltip" style={pop}>
          {r.label ? (
            <strong
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                color: "var(--ink)",
                fontWeight: 500,
                letterSpacing: "0.02em",
              }}
            >
              {r.label}
            </strong>
          ) : null}
          {r.value ? (
            <span style={{ display: "block", marginTop: 4 }}>
              value <b style={{ color: "var(--ink)" }}>{r.value}</b>
            </span>
          ) : null}
          {r.n != null || r.corpus ? (
            <span style={{ display: "block", marginTop: 4, color: "var(--ink-3)" }}>
              {r.n != null ? `n=${r.n}` : ""}
              {r.n != null && r.corpus ? " / " : ""}
              {r.corpus || ""}
            </span>
          ) : null}
          <span style={path}>{r.sourceArtifact}</span>
          {r.asOf ? (
            <span style={{ ...path, marginTop: 2 }}>as_of {r.asOf}</span>
          ) : null}
          <Link
            href="/analytics/the-loop"
            style={{
              display: "inline-block",
              marginTop: 8,
              fontSize: 12,
              fontWeight: 600,
              color: "var(--accent)",
            }}
          >
            What does verified mean?
          </Link>
        </span>
      ) : null}
    </span>
  );
}

export default Receipt;
