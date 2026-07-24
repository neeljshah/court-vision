// GapEntropyChart.tsx -- dual small-multiple line (inline SVG, DESIGN tokens).
//
// Two stacked mini line-plots sharing an x (game-time checkpoint): the top
// plot is mean |model_prob - market_prob| gap (amber --s-model); the bottom is
// mean Bernoulli entropy in bits (blue --s-market). Source: market_convergence.
// Pure presentational server component -- no deps, no recharts, no hooks. Sits
// inside a <Panel>/InstrumentPanel; caller supplies head + receipt chip. ASCII.

export interface GapEntropyPoint {
  t: number; // game-time checkpoint (inning / minute-bucket)
  gap: number; // mean |model - market| prob, 0..1
  entropy: number; // mean Bernoulli entropy, bits (0..1, log2)
}

export interface GapEntropyChartProps {
  series: GapEntropyPoint[];
  width?: number;
  height?: number;
}

const PAD = { l: 34, r: 10, t: 8, b: 20 };

// One mini line-plot: values in [0,1] on a shared x-domain. Returns an <svg>.
function LinePlot({
  pts,
  color,
  yLabel,
  width,
  height,
  xMin,
  xMax,
}: {
  pts: { x: number; v: number }[];
  color: string;
  yLabel: string;
  width: number;
  height: number;
  xMin: number;
  xMax: number;
}) {
  const plotW = width - PAD.l - PAD.r;
  const plotH = height - PAD.t - PAD.b;
  const span = xMax - xMin || 1;
  const px = (x: number) => PAD.l + ((x - xMin) / span) * plotW;
  const py = (v: number) => PAD.t + (1 - Math.max(0, Math.min(1, v))) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  const d = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${px(p.x).toFixed(1)},${py(p.v).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${yLabel} over game time`}
      className="max-w-full"
    >
      {ticks.map((t) => (
        <g key={t}>
          <line
            x1={PAD.l}
            y1={py(t)}
            x2={PAD.l + plotW}
            y2={py(t)}
            stroke="hsl(var(--border))"
            strokeWidth={1}
          />
          <text
            x={PAD.l - 6}
            y={py(t) + 3}
            textAnchor="end"
            fill="hsl(var(--faint))"
            className="font-data"
            style={{ fontSize: 9 }}
          >
            {t.toFixed(2).slice(1)}
          </text>
        </g>
      ))}
      {pts.length > 1 && <path d={d} fill="none" stroke={color} strokeWidth={2} />}
      {pts.map((p, i) => (
        <circle key={i} cx={px(p.x)} cy={py(p.v)} r={3} fill={color}>
          <title>{`t=${p.x}: ${p.v.toFixed(3)}`}</title>
        </circle>
      ))}
      <text
        x={PAD.l + 2}
        y={PAD.t + 9}
        fill="hsl(var(--faint))"
        className="microlabel"
        style={{ fontSize: 9 }}
      >
        {yLabel}
      </text>
    </svg>
  );
}

export function GapEntropyChart({
  series,
  width = 360,
  height = 240,
}: GapEntropyChartProps) {
  if (!series || series.length === 0) {
    return (
      <span className="font-data text-[10px] text-faint">
        no convergence checkpoints for this corpus
      </span>
    );
  }
  const sorted = series.slice().sort((a, b) => a.t - b.t);
  const xMin = sorted[0].t;
  const xMax = sorted[sorted.length - 1].t;
  const each = Math.floor(height / 2);

  return (
    <div className="flex flex-col gap-1">
      <LinePlot
        pts={sorted.map((p) => ({ x: p.t, v: p.gap }))}
        color="hsl(var(--s-model))"
        yLabel="MEAN GAP |MODEL-MARKET|"
        width={width}
        height={each}
        xMin={xMin}
        xMax={xMax}
      />
      <LinePlot
        pts={sorted.map((p) => ({ x: p.t, v: p.entropy }))}
        color="hsl(var(--s-market))"
        yLabel="MARKET ENTROPY (BITS)"
        width={width}
        height={each}
        xMin={xMin}
        xMax={xMax}
      />
      <p className="microlabel text-faint">GAME-TIME CHECKPOINT ({xMin} to {xMax})</p>
    </div>
  );
}
