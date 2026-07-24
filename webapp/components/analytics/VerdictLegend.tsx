// VerdictLegend -- a compact key for the verdict dots scattered across the browse
// grids (home bento, /analytics/browse). The dot encodes confirmed / null /
// not-testable / descriptive / pending, but on a phone there is no hover to reach
// the dot's title -- so the honesty signal reads as decoration without this key.
// Server component, tokens only, ASCII. Reuses VerdictDot so the swatches match.
import type { CSSProperties } from "react";
import { VerdictDot, type Verdict } from "./VerdictDot";

const ITEMS: Array<[Verdict, string]> = [
  ["confirmed", "confirmed"],
  ["null", "null (a finding)"],
  ["not_testable", "not testable"],
  ["descriptive_only", "descriptive"],
  ["pending", "pending"],
];

const row: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "6px 16px",
  fontSize: 12,
  color: "var(--ink-3)",
};
const item: CSSProperties = { display: "inline-flex", alignItems: "center", gap: 6 };

export function VerdictLegend({ style }: { style?: CSSProperties }) {
  return (
    <div role="list" aria-label="Verdict dot key" style={{ ...row, ...style }}>
      {ITEMS.map(([v, l]) => (
        <span role="listitem" key={v} style={item}>
          <VerdictDot verdict={v} />
          {l}
        </span>
      ))}
    </div>
  );
}

export default VerdictLegend;
