// VerdictDot -- honesty as a token (DESIGN_ANALYTICS Sec. 1 + 4).
// A null result renders NEUTRAL slate, never red -- a finding, not a failure.
// Pure presentational; safe in both server and client trees.
import type { CSSProperties } from "react";

export type Verdict =
  | "confirmed"
  | "null"
  | "not_testable"
  | "descriptive_only"
  | "pending";

// Verdict -> graphic color token. Red (--reject) is deliberately NOT here:
// a null is neutral slate, reject/retraction color lives only in that context.
const COLOR: Record<Verdict, string> = {
  confirmed: "var(--confirmed)",
  null: "var(--null)",
  not_testable: "var(--not-testable)",
  descriptive_only: "var(--ink-3)",
  pending: "transparent",
};

const LABEL: Record<Verdict, string> = {
  confirmed: "verdict: confirmed",
  null: "verdict: null result (a finding, not a failure)",
  not_testable: "verdict: not testable",
  descriptive_only: "descriptive only -- no edge claimed",
  pending: "validation pending",
};

export function VerdictDot({
  verdict,
  size = 7,
}: {
  verdict: Verdict;
  size?: number;
}) {
  const style: CSSProperties = {
    width: size,
    height: size,
    borderRadius: "50%",
    display: "inline-block",
    flex: "0 0 auto",
    background: COLOR[verdict],
  };
  // pending = hollow ring (fresh-clone / unvalidated state).
  if (verdict === "pending") {
    style.boxShadow = "inset 0 0 0 1.5px var(--null)";
  }
  return (
    <span role="img" aria-label={LABEL[verdict]} title={LABEL[verdict]} style={style} />
  );
}

export default VerdictDot;
