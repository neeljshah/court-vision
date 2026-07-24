"use client";
// Receipt -- the honesty brand, restyled for the Reading Room (DESIGN Sec. 4).
// Resting: a QUIET inline mono stamp (verdict dot + as_of), never a loud badge.
// Hover / focus / touch: a popover with the measurement label, source_artifact
// path, n, corpus, and a "what does verified mean?" link to /analytics/the-loop
// (the shipped discipline surface -- leak-free gate, ledger, honesty exhibit; the
// standalone /analytics/method page in the spec was never built).
import { useEffect, useRef, useState, type CSSProperties } from "react";
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
  // Enlarge the touch target without shifting layout: the padding grows the hit
  // box to ~44px wide / ~24px tall, the matching negative margin cancels the
  // occupied space so neighbours don't move (DESIGN core interaction, mobile).
  padding: "6px 3px",
  margin: "-6px -3px",
  borderRadius: 4,
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
  maxWidth: "min(300px, calc(100vw - 24px))",
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
  // right-anchor the popover when it would run off the right screen edge.
  const [flip, setFlip] = useState(false);
  // open upward when it would drop off the bottom (receipts low in the viewport).
  const [up, setUp] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const wrapRef = useRef<HTMLSpanElement>(null);

  // Dismiss on any tap/click outside the wrapper. iOS Safari never focuses a
  // <button> on tap, so onBlur/focusout never fires there -- without this, a
  // touch user's popover has no way to close but re-tapping the same stamp, and
  // tapping a different receipt would stack a second popover on top. pointerdown
  // covers mouse + touch + pen; the hover/keyboard paths above are untouched.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);
  // Quiet resting token: prefer as_of, else value, else the artifact basename.
  const resting = r.asOf || r.value || basename(r.sourceArtifact);
  const dashed = r.verdict === "not_testable";

  // ponytail: decide the anchor side/vertical from the trigger's viewport rect on
  // open. 312 = maxWidth 300 + 12px gutter; ~200 = the popover's tallest realistic
  // height. No live measure of the popover itself.
  function openPop() {
    const r = btnRef.current?.getBoundingClientRect();
    setFlip(!!r && r.left + 312 > window.innerWidth);
    // flip up only when it would overflow the bottom AND there is room above, so a
    // receipt near the top of the page never opens off the top.
    setUp(!!r && r.bottom + 200 > window.innerHeight && r.top > 200);
    setOpen(true);
  }

  return (
    <span
      ref={wrapRef}
      style={{ position: "relative", display: "inline-block" }}
      // Handlers live on the wrapper (owns both trigger and popover) so keyboard
      // focus can move INTO the popover's link without the blur closing it first.
      // No onFocus opener: a pointer tap focuses the button (Android), which an
      // onFocus-open would then have the button's onClick toggle straight shut
      // (first-tap-dead). Keyboard opens via Enter/Space -> the button's onClick.
      onMouseEnter={openPop}
      onMouseLeave={() => setOpen(false)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <button
        ref={btnRef}
        type="button"
        style={{
          ...stamp,
          // text-decoration (not border-bottom) so the hint stays tight to the text
          // now that the button carries 6px of hit-slop padding. Every stamp gets a
          // quiet dotted underline so it reads as tappable on touch (no hover to
          // reveal it); not_testable keeps its louder caution-colored DASHED rule so
          // the two stay distinguishable.
          ...(dashed
            ? { textDecoration: "underline dashed", textDecorationColor: "var(--not-testable)", textUnderlineOffset: 2 }
            : { textDecoration: "underline dotted", textDecorationColor: "var(--rule-strong)", textUnderlineOffset: 2 }),
        }}
        aria-expanded={open}
        aria-label={`Receipt: ${r.label || r.verdict} for ${resting}`}
        onClick={() => (open ? setOpen(false) : openPop())}
      >
        <VerdictDot verdict={r.verdict} />
        {resting}
      </button>
      {open ? (
        <span
          // Not role="tooltip": this popover is a toggletip/disclosure -- it holds
          // an interactive link (below), which an ARIA tooltip must never contain.
          // The trigger's aria-expanded carries the open/closed state instead.
          style={{
            ...pop,
            ...(flip ? { left: "auto", right: 0 } : null),
            ...(up ? { top: "auto", bottom: "calc(100% + 6px)" } : null),
          }}
        >
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
