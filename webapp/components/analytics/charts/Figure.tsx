// Figure.tsx -- the shared editorial frame every analytics chart wears.
// Native <figure>/<figcaption>: the caption is the mandatory source + as_of
// receipt (DESIGN Sec.4 resting style -- verdict dot + mono stamp, quiet, never
// a loud badge). Server-renderable, tokens only, ASCII. Titles are Libre
// Franklin 600 (serif is reserved for editorial headings, DESIGN Sec.11).

import type { ReactNode, CSSProperties } from "react";
import { verdictColor } from "./scale";

export interface FigureProps {
  source: string;
  asOf: string;
  children: ReactNode;
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  /** on-chart honest note, e.g. "y-axis starts at 1500". */
  note?: string;
  /** optional verdict dot on the caption, matching the ReceiptChip resting look. */
  verdict?: string;
  /** extra receipt facts appended after the source, e.g. "n=4732". */
  meta?: string;
}

const cap: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 11.5,
  color: "var(--ink-3)",
  display: "flex",
  alignItems: "center",
  gap: 6,
  marginTop: 12,
  flexWrap: "wrap",
};

export function Figure({
  source,
  asOf,
  children,
  title,
  eyebrow,
  subtitle,
  note,
  verdict,
  meta,
}: FigureProps) {
  return (
    <figure style={{ margin: 0, width: "100%" }}>
      {eyebrow && (
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 700,
            fontSize: 11,
            letterSpacing: "0.13em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
            marginBottom: 6,
          }}
        >
          {eyebrow}
        </div>
      )}
      {title && (
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 600,
            fontSize: 20,
            lineHeight: 1.3,
            color: "var(--ink)",
          }}
        >
          {title}
        </div>
      )}
      {subtitle && (
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: 14,
            lineHeight: 1.45,
            color: "var(--ink-2)",
            marginTop: 4,
            maxWidth: "62ch",
          }}
        >
          {subtitle}
        </div>
      )}
      <div style={{ marginTop: title || subtitle || eyebrow ? 16 : 0 }}>{children}</div>
      {note && (
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: 12,
            color: "var(--ink-3)",
            marginTop: 8,
            fontStyle: "italic",
          }}
        >
          {note}
        </div>
      )}
      <figcaption style={cap}>
        {verdict && (
          <span
            aria-hidden
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: verdictColor(verdict),
              display: "inline-block",
            }}
          />
        )}
        <span>{source}</span>
        <span aria-hidden style={{ color: "var(--rule-strong)" }}>
          &middot;
        </span>
        <span>{asOf}</span>
        {meta && (
          <>
            <span aria-hidden style={{ color: "var(--rule-strong)" }}>
              &middot;
            </span>
            <span>{meta}</span>
          </>
        )}
      </figcaption>
    </figure>
  );
}
