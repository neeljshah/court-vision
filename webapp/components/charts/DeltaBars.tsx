// DeltaBars.tsx -- signed model-minus-market delta with a 95% CI whisker,
// centered on zero. One row per call; the scoreboard maps its rows over it.
//
// Sign conventions differ across the scoreboard (Brier vs CRPS, and which side
// is "good" flips by metric), so the bar is NOT read by raw sign. It is colored
// by the row's recorded VERDICT and the exact signed value is always printed by
// the caller. The bar shows magnitude; the whisker shows the 95% CI. A whisker
// that straddles the centered zero line is the visual for "not distinguishable"
// (UNDERPOWERED) -- DESIGN sec.4: the honest whisker crossing zero is the point.
//
// Per-row self-normalized: cross-unit magnitudes (Brier ~0.008 vs CRPS ~1.8) are
// not comparable, so each bar is scaled to its own CI/point extent. Pure SVG,
// tokens only, no deps, no hooks -- server-renderable. ASCII only.

export interface DeltaBarsProps {
  delta: number;
  ci: [number, number];
  verdict: string;
  width?: number;
  height?: number;
}

function verdictColor(v: string): string {
  if (v.startsWith("MODEL_SHARPER")) return "hsl(var(--success))";
  if (v.startsWith("MARKET_SHARPER")) return "hsl(var(--danger))";
  return "hsl(var(--faint))";
}

export function DeltaBars({
  delta,
  ci,
  verdict,
  width = 132,
  height = 18,
}: DeltaBarsProps) {
  const [lo, hi] = ci;
  // ponytail: self-normalize to this row's own extent; a shared cross-unit scale
  // would be dishonest (Brier and CRPS deltas are not comparable magnitudes).
  const ext = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(delta), 1e-9);
  const cx = width / 2;
  const half = cx - 5;
  const x = (v: number) => cx + (v / ext) * half;
  const midY = height / 2;
  const color = verdictColor(verdict);
  const barX0 = Math.min(cx, x(delta));
  const barW = Math.max(Math.abs(x(delta) - cx), 0.5);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`delta ${delta}, 95% CI ${lo} to ${hi}, ${verdict}`}
      className="max-w-full"
    >
      {/* centered zero line */}
      <line x1={cx} y1={2} x2={cx} y2={height - 2} stroke="hsl(var(--border))" strokeWidth={1} />
      {/* signed magnitude bar */}
      <rect x={barX0} y={midY - 3} width={barW} height={6} fill={color} opacity={0.35} />
      {/* 95% CI whisker with end caps */}
      <line x1={x(lo)} y1={midY} x2={x(hi)} y2={midY} stroke={color} strokeWidth={1.5} />
      <line x1={x(lo)} y1={midY - 3} x2={x(lo)} y2={midY + 3} stroke={color} strokeWidth={1.5} />
      <line x1={x(hi)} y1={midY - 3} x2={x(hi)} y2={midY + 3} stroke={color} strokeWidth={1.5} />
      {/* point estimate */}
      <circle cx={x(delta)} cy={midY} r={2.4} fill={color} />
      <title>{`delta ${delta}  CI [${lo}, ${hi}]  ${verdict}`}</title>
    </svg>
  );
}
