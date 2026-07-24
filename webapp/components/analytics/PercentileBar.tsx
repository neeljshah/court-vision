// PercentileBar -- a thin descriptive rank bar under a stat cell (DESIGN: entity
// percentiles). Server component: purely a fill percentage + caption, no
// interactivity, so it ships zero client JS. One neutral accent fill only --
// no good/bad colouring, since "higher" carries no quality judgement here.
export interface PercentileBarProps {
  pct: number; // 0..100, this entity's rank within its pack
  nInPack: number; // pack size the rank was computed against
}

export function PercentileBar({ pct, nInPack }: PercentileBarProps) {
  return (
    <div style={{ marginTop: 6 }}>
      <div
        role="img"
        aria-label={`Higher than ${pct} percent of ${nInPack} entities in this pack`}
        style={{
          height: 4,
          borderRadius: 2,
          background: "var(--rule)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: "var(--accent)",
            borderRadius: 2,
          }}
        />
      </div>
      <div style={{ marginTop: 3, fontSize: 11, color: "var(--ink-3)" }}>
        Higher than {pct}% of {nInPack} in pack
      </div>
    </div>
  );
}

export default PercentileBar;
