// Grid.tsx -- a heatmap grid ("what the model sees": state-conditioned cells).
// Sequential warm ramp by default, diverging ramp for signed values. null cells
// render NEUTRAL parchment -- a no-data finding, NEVER red (DESIGN Sec.1). Cell
// values are printed on the cell (direct labels, no legend), with text contrast
// chosen from the fill's luminance. 2px surface gap between cells. Pure SVG,
// server-renderable, tokens only, ASCII. Native <title> hover.
//
// ponytail: values sit on the cells, so no separate ramp-key legend -- the
// numbers are the legend. Add a ramp key only if a page ever hides cell labels.

import { Figure } from "./Figure";
import { seqColor, divColor, luminance, fmtTick } from "./scale";

export interface GridProps {
  rows: string[];
  cols: string[];
  /** values[row][col]; null = no data (renders neutral, never red). */
  values: (number | null)[][];
  source: string;
  asOf: string;
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  domain?: [number, number];
  diverging?: boolean;
  valueFormat?: (n: number) => string;
  cellLabels?: boolean;
  width?: number;
  cellHeight?: number;
  verdict?: string;
  meta?: string;
  /** SVG min render width before the Figure frame scrolls it. Default 560 keeps
   *  wide grids legible; a small few-column grid can pass a phone-fitting value
   *  (~340) so its row labels never scroll off-screen. */
  minWidth?: number;
}

const PAD = { l: 128, r: 16, t: 30, b: 8 };
const TXT = "var(--font-sans)";
const GAP = 2;

export function Grid(props: GridProps) {
  const {
    rows,
    cols,
    values,
    source,
    asOf,
    title,
    eyebrow,
    subtitle,
    diverging = false,
    valueFormat = fmtTick,
    cellLabels = true,
    width = 720,
    cellHeight = 40,
    verdict,
    meta,
    minWidth = 560,
  } = props;

  const flat = values.flat().filter((v): v is number => v != null && Number.isFinite(v));
  const lo = props.domain ? props.domain[0] : Math.min(...(flat.length ? flat : [0]));
  const hi = props.domain ? props.domain[1] : Math.max(...(flat.length ? flat : [1]));
  const maxAbs = Math.max(Math.abs(lo), Math.abs(hi), 1e-9);
  const span = hi - lo || 1;

  const cellW = (width - PAD.l - PAD.r) / cols.length;
  const height = PAD.t + PAD.b + rows.length * cellHeight;

  function fill(v: number): string {
    return diverging ? divColor(v / maxAbs) : seqColor((v - lo) / span);
  }

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
        style={{ height: "auto", minWidth, display: "block", fontVariantNumeric: "tabular-nums" }}
        role="img"
        aria-label={title || "heatmap"}
      >
        {/* column headers */}
        {cols.map((c, j) => (
          <text
            key={`c${j}`}
            x={PAD.l + j * cellW + cellW / 2}
            y={PAD.t - 10}
            textAnchor="middle"
            fontFamily={TXT}
            fontSize={11}
            fontWeight={600}
            fill="var(--ink-3)"
          >
            {c}
          </text>
        ))}

        {rows.map((r, i) => (
          <g key={`r${i}`}>
            {/* row header */}
            <text
              x={PAD.l - 12}
              y={PAD.t + i * cellHeight + cellHeight / 2}
              textAnchor="end"
              dominantBaseline="middle"
              fontFamily={TXT}
              fontSize={12}
              fill="var(--ink)"
            >
              {r}
            </text>
            {cols.map((_, j) => {
              const v = values[i]?.[j] ?? null;
              const x = PAD.l + j * cellW + GAP / 2;
              const y = PAD.t + i * cellHeight + GAP / 2;
              const w = cellW - GAP;
              const h = cellHeight - GAP;
              if (v == null || !Number.isFinite(v)) {
                return (
                  <g key={j}>
                    <rect x={x} y={y} width={w} height={h} rx={3} fill="var(--paper-tint)" stroke="var(--rule)" strokeWidth={1}>
                      <title>{`${r} / ${cols[j]}: no data`}</title>
                    </rect>
                    <text
                      x={x + w / 2}
                      y={y + h / 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontFamily={TXT}
                      fontSize={11}
                      fill="var(--ink-3)"
                    >
                      &ndash;
                    </text>
                  </g>
                );
              }
              const bg = fill(v);
              // Cell fills are FIXED hex (theme-blind ramp), so the label ink must be
              // too: var(--ink) flips near-white in dark and vanishes on the light cells.
              const ink = luminance(bg) > 0.62 ? "#1A1714" : "#FBF7EF";
              return (
                <g key={j}>
                  <rect x={x} y={y} width={w} height={h} rx={3} fill={bg}>
                    <title>{`${r} / ${cols[j]}: ${valueFormat(v)}`}</title>
                  </rect>
                  {cellLabels && (
                    <text
                      x={x + w / 2}
                      y={y + h / 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontFamily={TXT}
                      fontSize={12}
                      fontWeight={500}
                      fill={ink}
                    >
                      {valueFormat(v)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        ))}
      </svg>
    </Figure>
  );
}
