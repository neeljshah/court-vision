// MurphyBars.tsx -- Murphy / Brier decomposition (inline SVG, DESIGN tokens).
//
// Brier = reliability - resolution + uncertainty. Three horizontal bars,
// shared scale, direct-labelled values (tabular mono) -- direction ink follows
// meaning: reliability lower-is-better (danger), resolution higher-is-better
// (success), uncertainty is the irreducible baseline (faint). This is a
// descriptive decomposition, not an edge claim; the caption states so.
//
// Pure presentational server component: no deps, no recharts, no hooks. Sits
// inside a <Panel>; caller supplies the PanelHead + receipt chip. ASCII only.

export interface MurphyBarsProps {
  reliability: number;
  resolution: number;
  uncertainty: number;
  digits?: number;
  width?: number;
  height?: number;
}

interface Row {
  label: string;
  value: number;
  color: string;
  note: string;
}

const LABEL_W = 96;
const PAD = { l: 8, r: 52, t: 10, b: 8 };
const ROW_H = 30;
const BAR_H = 12;

export function MurphyBars({
  reliability,
  resolution,
  uncertainty,
  digits = 4,
  width = 320,
  height = 3 * ROW_H + PAD.t + PAD.b,
}: MurphyBarsProps) {
  const rows: Row[] = [
    { label: "RELIABILITY", value: reliability, color: "hsl(var(--danger))", note: "lower better" },
    { label: "RESOLUTION", value: resolution, color: "hsl(var(--success))", note: "higher better" },
    { label: "UNCERTAINTY", value: uncertainty, color: "hsl(var(--faint))", note: "baseline" },
  ];

  const barMax = width - LABEL_W - PAD.l - PAD.r;
  const scaleMax = Math.max(reliability, resolution, uncertainty, 1e-9);
  const bx = (v: number) => (Math.max(0, v) / scaleMax) * barMax;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Murphy decomposition: reliability, resolution, uncertainty"
      className="max-w-full"
    >
      {rows.map((r, i) => {
        const y = PAD.t + i * ROW_H;
        const barY = y + (ROW_H - BAR_H) / 2;
        const x0 = PAD.l + LABEL_W;
        const w = bx(r.value);
        return (
          <g key={r.label}>
            <text
              x={PAD.l}
              y={barY + BAR_H - 2}
              fill="hsl(var(--faint))"
              className="microlabel"
              style={{ fontSize: 9 }}
            >
              {r.label}
            </text>
            {/* track */}
            <rect
              x={x0}
              y={barY}
              width={barMax}
              height={BAR_H}
              fill="hsl(var(--surface-2))"
            />
            {/* value bar, 2px rounded data-end */}
            <rect x={x0} y={barY} width={w} height={BAR_H} rx={2} fill={r.color}>
              <title>{`${r.label.toLowerCase()} = ${r.value.toFixed(digits)} (${r.note})`}</title>
            </rect>
            <text
              x={width - PAD.r + 6}
              y={barY + BAR_H - 1}
              fill="hsl(var(--foreground))"
              className="font-data tabular"
              style={{ fontSize: 11 }}
            >
              {r.value.toFixed(digits)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
