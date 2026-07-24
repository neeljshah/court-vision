// ReliabilityDiagram.tsx -- predicted-vs-observed calibration plot (model vs
// market), sibling to Grid/Bars: same Figure frame, same linear()/linePath()
// scale idiom from scale.ts, tokens only, server-renderable, ASCII. Point
// radius scales gently (sqrt, bounded) with bin n so a 26k-row bin doesn't
// visually dominate a 300-row one, but the honest signal stays the LINE (mean_p
// vs mean_y), not the dot size.
//
// ponytail: two series max in practice (model, market) -- legend renders
// inline at the plot's top edge rather than a separate row; add a wrapping
// legend only if a page ever needs 3+ series here.

import { Figure } from "./Figure";
import { linear, linePath, type Pt } from "./scale";

export interface ReliabilityBin {
  mean_p: number;
  mean_y: number;
  n: number;
}

export interface ReliabilitySeries {
  label: string;
  bins: ReliabilityBin[];
  color: string;
}

export interface ReliabilityDiagramProps {
  series: ReliabilitySeries[];
  source: string;
  asOf: string;
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  verdict?: string;
  meta?: string;
  size?: number;
}

const PAD = { l: 46, r: 16, t: 28, b: 40 };
const TXT = "var(--font-sans)";
const TICKS = [0, 0.25, 0.5, 0.75, 1];
const R_MIN = 3;
const R_MAX = 7;

export function ReliabilityDiagram(props: ReliabilityDiagramProps) {
  const { series, source, asOf, title, eyebrow, subtitle, verdict, meta, size = 420 } = props;

  const width = PAD.l + PAD.r + size;
  const height = PAD.t + PAD.b + size;
  const sx = linear(0, 1, PAD.l, PAD.l + size);
  const sy = linear(0, 1, PAD.t + size, PAD.t); // inverted: y=0 at bottom

  const allN = series.flatMap((s) => s.bins.map((b) => b.n));
  const nLo = Math.min(...allN, Infinity);
  const nHi = Math.max(...allN, -Infinity);
  function radius(n: number): number {
    if (!Number.isFinite(nLo) || !Number.isFinite(nHi) || nHi === nLo) return (R_MIN + R_MAX) / 2;
    const t = (Math.sqrt(n) - Math.sqrt(nLo)) / (Math.sqrt(nHi) - Math.sqrt(nLo));
    return R_MIN + t * (R_MAX - R_MIN);
  }

  const ariaLabel = `Reliability diagram: predicted vs observed for ${series.map((s) => s.label).join(" vs ")}`;

  return (
    <Figure source={source} asOf={asOf} title={title} eyebrow={eyebrow} subtitle={subtitle} verdict={verdict} meta={meta}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{ height: "auto", maxWidth: width, display: "block", fontVariantNumeric: "tabular-nums" }}
        role="img"
        aria-label={ariaLabel}
      >
        {/* axes */}
        <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={PAD.t + size} stroke="var(--rule-strong)" strokeWidth={1} />
        <line x1={PAD.l} x2={PAD.l + size} y1={PAD.t + size} y2={PAD.t + size} stroke="var(--rule-strong)" strokeWidth={1} />
        {TICKS.map((t) => (
          <g key={`tx${t}`}>
            <line x1={sx(t)} x2={sx(t)} y1={PAD.t + size} y2={PAD.t + size + 4} stroke="var(--rule-strong)" strokeWidth={1} />
            <text x={sx(t)} y={PAD.t + size + 16} textAnchor="middle" fontFamily={TXT} fontSize={11} fill="var(--ink-3)">{t}</text>
            <line x1={PAD.l - 4} x2={PAD.l} y1={sy(t)} y2={sy(t)} stroke="var(--rule-strong)" strokeWidth={1} />
            <text x={PAD.l - 8} y={sy(t) + 4} textAnchor="end" fontFamily={TXT} fontSize={11} fill="var(--ink-3)">{t}</text>
          </g>
        ))}
        <text x={PAD.l + size / 2} y={height - 4} textAnchor="middle" fontFamily={TXT} fontSize={11.5} fill="var(--ink-2)">
          Predicted probability
        </text>
        <text x={-(PAD.t + size / 2)} y={12} transform="rotate(-90)" textAnchor="middle" fontFamily={TXT} fontSize={11.5} fill="var(--ink-2)">
          Observed frequency
        </text>

        {/* perfect-calibration diagonal */}
        <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--rule-strong)" strokeWidth={1.25} strokeDasharray="4 4" />

        {/* series */}
        {series.map((s, i) => {
          const pts: Pt[] = s.bins.map((b) => ({ x: b.mean_p, y: b.mean_y }));
          return (
            <g key={s.label}>
              <path d={linePath(pts, sx, sy)} fill="none" stroke={s.color} strokeWidth={2} />
              {s.bins.map((b, j) => (
                <circle key={j} cx={sx(b.mean_p)} cy={sy(b.mean_y)} r={radius(b.n)} fill={s.color} stroke="var(--paper)" strokeWidth={1}>
                  <title>{`${s.label}: predicted ${b.mean_p}, observed ${b.mean_y}, n=${b.n}`}</title>
                </circle>
              ))}
              {/* legend, top edge */}
              <g transform={`translate(${PAD.l + i * 150}, 8)`}>
                <rect width={10} height={10} rx={2} fill={s.color} />
                <text x={16} y={9} fontFamily={TXT} fontSize={11.5} fill="var(--ink-2)">{s.label}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </Figure>
  );
}
