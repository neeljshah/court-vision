// SmallMultiples.tsx -- a facet grid of mini line charts that SHARE ONE scale.
// The whole point: the y-domain (and x-domain) is computed once across every
// facet, so all minis use an identical sx/sy and the comparison is honest --
// two panels at the same height mean the same value. Shared range is declared
// once in the caption (no repeated axes: NYT small-multiples restraint). Each
// facet is direct-titled with its end value in the facet color. Responsive CSS
// grid, pure SVG minis, server-renderable, tokens only, ASCII. Native <title>.

import { Figure } from "./Figure";
import { Pt, niceScale, extent, linear, linePath, seriesColor, sportColor, fmtTick } from "./scale";

export interface Facet {
  name: string;
  points: Pt[];
  color?: string;
}

export interface SmallMultiplesProps {
  facets: Facet[];
  source: string;
  asOf: string;
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  yMin?: number;
  yMax?: number;
  yFormat?: (n: number) => string;
  xFormat?: (n: number) => string;
  refLine?: { y: number; label?: string };
  sportColors?: boolean;
  minWidth?: number;
  verdict?: string;
  meta?: string;
}

const VB_W = 200;
const VB_H = 104;
const INSET = 6;
const TXT = "var(--font-sans)";

export function SmallMultiples(props: SmallMultiplesProps) {
  const {
    facets,
    source,
    asOf,
    title,
    eyebrow,
    subtitle,
    yFormat = fmtTick,
    xFormat = fmtTick,
    refLine,
    sportColors = false,
    minWidth = 190,
    verdict,
    meta,
  } = props;

  // ONE shared domain across every facet -- this is the honest-comparison core.
  const allY = facets.flatMap((f) => f.points.map((p) => p.y));
  const allX = facets.flatMap((f) => f.points.map((p) => p.x));
  if (refLine) allY.push(refLine.y);
  const [xLo, xHi] = extent(allX);
  const yProbe = extent(allY);
  const yS = niceScale(props.yMin ?? yProbe[0], props.yMax ?? yProbe[1], 4);

  const sx = linear(xLo, xHi, INSET, VB_W - INSET);
  const sy = linear(yS.min, yS.max, VB_H - INSET, INSET);

  return (
    <Figure
      source={source}
      asOf={asOf}
      title={title}
      eyebrow={eyebrow}
      subtitle={subtitle}
      verdict={verdict}
      meta={meta}
      note={`shared scale ${yFormat(yS.min)} to ${yFormat(yS.max)} across all ${facets.length} panels`}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(auto-fill, minmax(${minWidth}px, 1fr))`,
          gap: 14,
        }}
      >
        {facets.map((f, i) => {
          const color = f.color || (sportColors ? sportColor(f.name) : undefined) || seriesColor(i);
          const last = f.points[f.points.length - 1];
          return (
            <div
              key={f.name}
              style={{
                border: "1px solid var(--rule)",
                borderRadius: 8,
                background: "var(--paper-raised)",
                padding: "10px 12px 8px",
              }}
            >
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontFamily: TXT, fontWeight: 600, fontSize: 13, color: "var(--ink)" }}>{f.name}</span>
                <span
                  style={{
                    fontFamily: TXT,
                    fontWeight: 600,
                    fontSize: 13,
                    color,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {yFormat(last.y)}
                </span>
              </div>
              <svg
                viewBox={`0 0 ${VB_W} ${VB_H}`}
                width="100%"
                style={{ height: "auto", display: "block", marginTop: 6 }}
                role="img"
                aria-label={`${f.name}: ${yFormat(last.y)} at ${xFormat(last.x)}`}
              >
                {refLine && (
                  <line
                    x1={INSET}
                    x2={VB_W - INSET}
                    y1={sy(refLine.y)}
                    y2={sy(refLine.y)}
                    stroke="var(--ink-3)"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                  />
                )}
                <path
                  d={linePath(f.points, sx, sy)}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                <circle cx={sx(last.x)} cy={sy(last.y)} r={3} fill={color}>
                  <title>{`${f.name}: ${yFormat(last.y)} @ ${xFormat(last.x)}`}</title>
                </circle>
              </svg>
            </div>
          );
        })}
      </div>
    </Figure>
  );
}
