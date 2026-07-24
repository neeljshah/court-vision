// ReliabilityBins.tsx -- calibration diagram (inline SVG, DESIGN tokens only).
//
// Predicted probability (x) vs observed frequency (y), against the 45-degree
// perfect-calibration ideal (faint dashed). Model bins render amber
// (--s-model), market bins blue (--s-market); a bin's row count n shows on
// hover via a native <title> (the only interactivity DESIGN allows).
//
// Pure presentational server component: no deps, no recharts, no hooks. Sits
// inside a <Panel>; caller supplies the PanelHead + receipt chip. ASCII only.

export interface ReliabilityBin {
  p: number; // mean predicted prob in the bin (0..1)
  y: number; // observed frequency in the bin (0..1)
  n: number; // rows in the bin (hover detail; not fabricated)
  source: "model" | "market";
}

export interface ReliabilityBinsProps {
  bins: ReliabilityBin[];
  width?: number;
  height?: number;
}

const PAD = { l: 34, r: 10, t: 10, b: 26 };

const SRC_COLOR: Record<ReliabilityBin["source"], string> = {
  model: "hsl(var(--s-model))",
  market: "hsl(var(--s-market))",
};

export function ReliabilityBins({
  bins,
  width = 260,
  height = 260,
}: ReliabilityBinsProps) {
  const plotW = width - PAD.l - PAD.r;
  const plotH = height - PAD.t - PAD.b;
  // x,y in [0,1] -> pixel space; y inverted (0 at bottom).
  const px = (p: number) => PAD.l + Math.max(0, Math.min(1, p)) * plotW;
  const py = (v: number) => PAD.t + (1 - Math.max(0, Math.min(1, v))) * plotH;

  if (!bins || bins.length === 0) {
    return (
      <span className="font-data text-[10px] text-faint">
        no calibration bins for this surface
      </span>
    );
  }

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const bySource = (s: ReliabilityBin["source"]) =>
    bins
      .filter((b) => b.source === s)
      .slice()
      .sort((a, b) => a.p - b.p);

  const line = (pts: ReliabilityBin[]) =>
    pts
      .map((b, i) => `${i === 0 ? "M" : "L"}${px(b.p).toFixed(1)},${py(b.y).toFixed(1)}`)
      .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="calibration diagram: predicted probability vs observed frequency"
      className="max-w-full"
    >
      {/* grid + axis ticks */}
      {ticks.map((t) => (
        <g key={`g${t}`}>
          <line
            x1={px(t)}
            y1={PAD.t}
            x2={px(t)}
            y2={PAD.t + plotH}
            stroke="hsl(var(--border))"
            strokeWidth={1}
          />
          <line
            x1={PAD.l}
            y1={py(t)}
            x2={PAD.l + plotW}
            y2={py(t)}
            stroke="hsl(var(--border))"
            strokeWidth={1}
          />
          <text
            x={px(t)}
            y={height - 8}
            textAnchor="middle"
            fill="hsl(var(--faint))"
            className="font-data"
            style={{ fontSize: 9 }}
          >
            {t.toFixed(2).slice(1)}
          </text>
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

      {/* perfect-calibration ideal */}
      <line
        x1={px(0)}
        y1={py(0)}
        x2={px(1)}
        y2={py(1)}
        stroke="hsl(var(--faint))"
        strokeWidth={1}
        strokeDasharray="3 3"
      />

      {/* per-source polyline + dots */}
      {(["market", "model"] as const).map((s) => {
        const pts = bySource(s);
        if (pts.length === 0) return null;
        return (
          <g key={s}>
            {pts.length > 1 && (
              <path d={line(pts)} fill="none" stroke={SRC_COLOR[s]} strokeWidth={2} />
            )}
            {pts.map((b, i) => (
              <circle
                key={`${s}${i}`}
                cx={px(b.p)}
                cy={py(b.y)}
                r={4}
                fill={SRC_COLOR[s]}
              >
                <title>{`${s}: predicted ${b.p.toFixed(3)}, observed ${b.y.toFixed(3)}, n=${b.n}`}</title>
              </circle>
            ))}
          </g>
        );
      })}

      {/* axis microlabels */}
      <text
        x={PAD.l + plotW / 2}
        y={height - 18}
        textAnchor="middle"
        fill="hsl(var(--faint))"
        className="microlabel"
        style={{ fontSize: 9 }}
      >
        PREDICTED
      </text>
    </svg>
  );
}
