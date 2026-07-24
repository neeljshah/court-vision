// Line.tsx -- editorial line chart. One or many series, direct end-labels (no
// legend box, DESIGN mandate), recessive horizontal gridlines only, honest
// labeled y-axis (every tick printed so a non-zero baseline is always visible),
// optional CI ribbon and a labeled reference line ("vs close, not edge").
// Pure SVG, server-renderable, tokens only, ASCII. Native <title> = zero-JS
// hover tooltips.

import { Figure } from "./Figure";
import {
  Pt,
  niceScale,
  extent,
  linear,
  linePath,
  bandPath,
  seriesColor,
  fmtTick,
} from "./scale";

export interface LineSeries {
  name: string;
  points: Pt[];
  color?: string;
  dashed?: boolean;
}

export interface LineProps {
  series: LineSeries[];
  source: string;
  asOf: string;
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  yMin?: number;
  yMax?: number;
  yFormat?: (n: number) => string;
  xFormat?: (n: number) => string;
  xTicks?: number[];
  band?: { lo: Pt[]; hi: Pt[]; color?: string };
  refLine?: { y: number; label: string };
  markers?: boolean;
  width?: number;
  height?: number;
  verdict?: string;
  meta?: string;
}

const PAD = { l: 46, r: 104, t: 14, b: 34 };
const TXT = "var(--font-sans)";

export function Line(props: LineProps) {
  const {
    series,
    source,
    asOf,
    title,
    eyebrow,
    subtitle,
    yFormat = fmtTick,
    xFormat = fmtTick,
    band,
    refLine,
    markers,
    width = 720,
    height = 320,
    verdict,
    meta,
  } = props;

  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  if (band) allY.push(...band.lo.map((p) => p.y), ...band.hi.map((p) => p.y));
  if (refLine) allY.push(refLine.y);
  const allX = series.flatMap((s) => s.points.map((p) => p.x));
  const [xLo, xHi] = extent(allX);
  const yProbe = extent(allY);
  const yS = niceScale(props.yMin ?? yProbe[0], props.yMax ?? yProbe[1], 5);

  const px0 = PAD.l;
  const px1 = width - PAD.r;
  const py0 = height - PAD.b;
  const py1 = PAD.t;
  const sx = linear(xLo, xHi, px0, px1);
  const sy = linear(yS.min, yS.max, py0, py1);

  const xt = props.xTicks ?? niceScale(xLo, xHi, 5).ticks.filter((t) => t >= xLo && t <= xHi);

  // direct end-labels, de-collided top-to-bottom with a min gap
  const ends = series
    .map((s, i) => {
      const last = s.points[s.points.length - 1];
      return { name: s.name, color: s.color || seriesColor(i), y: sy(last.y) };
    })
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
  }

  const nonZero = yS.min !== 0 && !series.every((s) => s.points.every((p) => p.y >= 0 && p.y <= 1));

  return (
    <Figure
      source={source}
      asOf={asOf}
      title={title}
      eyebrow={eyebrow}
      subtitle={subtitle}
      verdict={verdict}
      meta={meta}
      note={nonZero ? `y-axis spans ${yFormat(yS.min)} to ${yFormat(yS.max)}, not zero-based` : undefined}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{ height: "auto", display: "block", fontVariantNumeric: "tabular-nums" }}
        role="img"
        aria-label={title || "line chart"}
      >
        {/* horizontal gridlines + y tick labels (no vertical grid: NYT restraint) */}
        {yS.ticks
          .filter((t) => t >= yS.min && t <= yS.max)
          .map((t) => (
            <g key={`y${t}`}>
              <line
                x1={px0}
                x2={px1}
                y1={sy(t)}
                y2={sy(t)}
                stroke="var(--rule)"
                strokeWidth={1}
              />
              <text
                x={px0 - 8}
                y={sy(t)}
                textAnchor="end"
                dominantBaseline="middle"
                fontFamily={TXT}
                fontSize={11}
                fill="var(--ink-3)"
              >
                {yFormat(t)}
              </text>
            </g>
          ))}

        {/* x tick labels */}
        {xt.map((t) => (
          <text
            key={`x${t}`}
            x={sx(t)}
            y={py0 + 18}
            textAnchor="middle"
            fontFamily={TXT}
            fontSize={11}
            fill="var(--ink-3)"
          >
            {xFormat(t)}
          </text>
        ))}

        {/* CI ribbon behind the lines */}
        {band && (
          <path d={bandPath(band.lo, band.hi, sx, sy)} fill={band.color || "var(--accent)"} opacity={0.12} />
        )}

        {/* reference line (dashed) with a direct right-label */}
        {refLine && (
          <g>
            <line
              x1={px0}
              x2={px1}
              y1={sy(refLine.y)}
              y2={sy(refLine.y)}
              stroke="var(--ink-3)"
              strokeWidth={1}
              strokeDasharray="4 4"
            />
            <text
              x={px1 + 6}
              y={sy(refLine.y)}
              dominantBaseline="middle"
              fontFamily={TXT}
              fontSize={11}
              fill="var(--ink-3)"
            >
              {refLine.label}
            </text>
          </g>
        )}

        {/* series */}
        {series.map((s, i) => {
          const color = s.color || seriesColor(i);
          return (
            <g key={s.name}>
              <path
                d={linePath(s.points, sx, sy)}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray={s.dashed ? "5 4" : undefined}
              />
              {markers &&
                s.points.map((p, j) => (
                  <circle key={j} cx={sx(p.x)} cy={sy(p.y)} r={2.6} fill={color}>
                    <title>{`${s.name}: ${yFormat(p.y)} @ ${xFormat(p.x)}`}</title>
                  </circle>
                ))}
              {/* emphasized end dot */}
              <circle
                cx={sx(s.points[s.points.length - 1].x)}
                cy={sy(s.points[s.points.length - 1].y)}
                r={3.4}
                fill={color}
              />
            </g>
          );
        })}

        {/* direct end-labels (no legend) */}
        {ends.map((e) => (
          <text
            key={e.name}
            x={px1 + 8}
            y={e.y}
            dominantBaseline="middle"
            fontFamily={TXT}
            fontSize={12}
            fontWeight={600}
            fill={e.color}
          >
            {e.name}
          </text>
        ))}
      </svg>
    </Figure>
  );
}
