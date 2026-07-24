// Bars.tsx -- horizontal ranked bars, the editorial workhorse (mechanism effect
// sizes, model-vs-close deltas). Zero-anchored ALWAYS (a bar that doesn't start
// at zero is a lie), diverging-capable (negatives grow left of a centered zero),
// direct value labels (no legend/axis clutter), verdict-or-categorical color,
// optional 95% CI whisker, 4px rounded value-end. Native <title> hover. Pure
// SVG, server-renderable, tokens only, ASCII.
//
// ponytail: horizontal only -- ranked bars with readable category labels cover
// the mechanism-effect and model-vs-market cases. Add a vertical/column variant
// when a page actually needs columns.

import { Figure } from "./Figure";
import { linear, seriesColor, verdictColor, fmtTick } from "./scale";

export interface BarDatum {
  label: string;
  value: number;
  color?: string;
  verdict?: string;
  ci?: [number, number];
  sub?: string;
}

export interface BarsProps {
  bars: BarDatum[];
  source: string;
  asOf: string;
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  valueFormat?: (n: number) => string;
  unit?: string;
  domainMin?: number;
  domainMax?: number;
  width?: number;
  rowHeight?: number;
  verdict?: string;
  meta?: string;
}

const PAD = { l: 150, r: 64, t: 6, b: 6 };
const TXT = "var(--font-sans)";
const BAR_H = 15;

// A bar rounded ONLY at its value end (baseline end stays square/anchored).
function barPath(x0: number, x1: number, y: number, h: number, r: number): string {
  const dir = x1 >= x0 ? 1 : -1;
  const rr = Math.min(r, Math.abs(x1 - x0), h / 2);
  const xi = x1 - dir * rr;
  const yt = y;
  const yb = y + h;
  return (
    `M${x0},${yt} L${xi},${yt} Q${x1},${yt} ${x1},${yt + rr} ` +
    `L${x1},${yb - rr} Q${x1},${yb} ${xi},${yb} L${x0},${yb} Z`
  );
}

export function Bars(props: BarsProps) {
  const {
    bars,
    source,
    asOf,
    title,
    eyebrow,
    subtitle,
    valueFormat = fmtTick,
    unit,
    width = 720,
    rowHeight = 34,
    verdict,
    meta,
  } = props;

  const vals = bars.flatMap((b) => [b.value, ...(b.ci || [])]);
  const dataMin = Math.min(0, ...vals);
  const dataMax = Math.max(0, ...vals);
  const dMin = props.domainMin ?? dataMin;
  const dMax = props.domainMax ?? dataMax;
  const diverging = dMin < 0;

  const px0 = PAD.l;
  const px1 = width - PAD.r;
  const sx = linear(dMin, dMax, px0, px1);
  const zeroX = sx(0);

  const height = PAD.t + PAD.b + bars.length * rowHeight;

  return (
    <Figure
      source={source}
      asOf={asOf}
      title={title}
      eyebrow={eyebrow}
      subtitle={subtitle}
      verdict={verdict}
      meta={meta}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{ height: "auto", minWidth: 560, display: "block", fontVariantNumeric: "tabular-nums" }}
        role="img"
        aria-label={title || "bar chart"}
      >
        {/* zero baseline (only drawn when it sits inside the plot, i.e. diverging) */}
        {diverging && (
          <line x1={zeroX} x2={zeroX} y1={PAD.t} y2={height - PAD.b} stroke="var(--rule-strong)" strokeWidth={1} />
        )}

        {bars.map((b, i) => {
          const color = b.color || (b.verdict ? verdictColor(b.verdict) : seriesColor(i));
          const y = PAD.t + i * rowHeight + (rowHeight - BAR_H) / 2;
          const vx = sx(b.value);
          const right = b.value >= 0;
          const labelX = right ? Math.max(vx, zeroX) + 8 : Math.min(vx, zeroX) - 8;
          return (
            <g key={b.label}>
              {/* category label */}
              <text
                x={PAD.l - 12}
                y={PAD.t + i * rowHeight + rowHeight / 2 - (b.sub ? 6 : 0)}
                textAnchor="end"
                dominantBaseline="middle"
                fontFamily={TXT}
                fontSize={13}
                fill="var(--ink)"
              >
                {b.label}
              </text>
              {b.sub && (
                <text
                  x={PAD.l - 12}
                  y={PAD.t + i * rowHeight + rowHeight / 2 + 9}
                  textAnchor="end"
                  fontFamily={TXT}
                  fontSize={11}
                  fill="var(--ink-3)"
                >
                  {b.sub}
                </text>
              )}
              {/* the bar */}
              <path d={barPath(zeroX, vx, y, BAR_H, 4)} fill={color} opacity={0.9}>
                <title>{`${b.label}: ${valueFormat(b.value)}${unit ? " " + unit : ""}`}</title>
              </path>
              {/* 95% CI whisker */}
              {b.ci && (
                <g stroke={color} strokeWidth={1.5}>
                  <line x1={sx(b.ci[0])} x2={sx(b.ci[1])} y1={y + BAR_H / 2} y2={y + BAR_H / 2} />
                  <line x1={sx(b.ci[0])} x2={sx(b.ci[0])} y1={y + 2} y2={y + BAR_H - 2} />
                  <line x1={sx(b.ci[1])} x2={sx(b.ci[1])} y1={y + 2} y2={y + BAR_H - 2} />
                </g>
              )}
              {/* direct value label */}
              <text
                x={labelX}
                y={y + BAR_H / 2}
                textAnchor={right ? "start" : "end"}
                dominantBaseline="middle"
                fontFamily={TXT}
                fontSize={13}
                fontWeight={600}
                fill="var(--ink-2)"
              >
                {valueFormat(b.value)}
              </text>
            </g>
          );
        })}
      </svg>
    </Figure>
  );
}
