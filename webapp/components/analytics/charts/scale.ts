// scale.ts -- shared, pure chart helpers for the analytics (Reading Room) charts.
// No JSX, no deps, no hooks: safe in server components. Colors follow DESIGN
// Sec.1: categorical hues are FIXED HEX (chosen to read on ivory AND espresso,
// so they do NOT shift by theme), while structural/verdict colors use the
// analytics CSS vars (theme-aware). ASCII only.

export interface Pt {
  x: number;
  y: number;
}

// -- domain / ticks ---------------------------------------------------------

export function extent(vals: number[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of vals) {
    if (!Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === Infinity) return [0, 1];
  return [lo, hi];
}

// "Nice number" rounding (Heckbert). round=true snaps to a pleasant step.
function niceNum(range: number, round: boolean): number {
  const exp = Math.floor(Math.log10(range || 1));
  const frac = range / Math.pow(10, exp);
  let nf: number;
  if (round) {
    nf = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;
  } else {
    nf = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  }
  return nf * Math.pow(10, exp);
}

export interface NiceScale {
  min: number;
  max: number;
  ticks: number[];
}

// A rounded axis domain + evenly spaced ticks. Honest by construction: the
// returned min/max are what the axis should actually span, and every tick is
// labeled by the caller so a non-zero baseline is always visible.
export function niceScale(min: number, max: number, count = 5): NiceScale {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    const c = Number.isFinite(min) ? min : 0;
    return { min: c - 1, max: c + 1, ticks: [c - 1, c, c + 1] };
  }
  const range = niceNum(max - min, false);
  const step = niceNum(range / Math.max(1, count - 1), true);
  const nmin = Math.floor(min / step) * step;
  const nmax = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  // guard the loop against float drift with a half-step epsilon
  for (let v = nmin; v <= nmax + step * 0.5; v += step) {
    ticks.push(Math.round(v / step) * step);
  }
  return { min: nmin, max: nmax, ticks };
}

// -- linear map -------------------------------------------------------------

export function linear(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const span = d1 - d0 || 1;
  return (v) => r0 + ((v - d0) / span) * (r1 - r0);
}

// -- path builders ----------------------------------------------------------

export function linePath(pts: Pt[], sx: (x: number) => number, sy: (y: number) => number): string {
  if (!pts.length) return "";
  return pts
    .map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`)
    .join(" ");
}

export function areaPath(
  pts: Pt[],
  sx: (x: number) => number,
  sy: (y: number) => number,
  baseY: number
): string {
  if (!pts.length) return "";
  const up = pts.map((p) => `${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`).join(" L");
  const x0 = sx(pts[0].x).toFixed(2);
  const x1 = sx(pts[pts.length - 1].x).toFixed(2);
  return `M${up} L${x1},${baseY.toFixed(2)} L${x0},${baseY.toFixed(2)} Z`;
}

// band between a lo and hi series (shared x), for a CI ribbon.
export function bandPath(
  lo: Pt[],
  hi: Pt[],
  sx: (x: number) => number,
  sy: (y: number) => number
): string {
  if (!lo.length || !hi.length) return "";
  const top = hi.map((p) => `${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`).join(" L");
  const bot = [...lo]
    .reverse()
    .map((p) => `${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`)
    .join(" L");
  return `M${top} L${bot} Z`;
}

// -- palettes (DESIGN Sec.1) ------------------------------------------------

// Categorical: fixed hex, assigned in order, NEVER cycled past 7 (a would-be 8th
// series folds into "Other" / small multiples per the dataviz non-negotiable).
export const CATEGORICAL = [
  "#1D5C7A", // slate
  "#C6852B", // ochre
  "#1E6B45", // green
  "#A6412F", // brick
  "#6A5A8C", // plum
  "#3E7C8C", // teal
  "#8A8078", // neutral
];

export const SPORT: Record<string, string> = {
  nba: "#1D5C7A",
  mlb: "#1E6B45",
  soccer: "#6A5A8C",
  tennis: "#C6852B",
};

export function seriesColor(i: number): string {
  return CATEGORICAL[i % CATEGORICAL.length];
}

export function sportColor(name: string): string | undefined {
  return SPORT[name.trim().toLowerCase()];
}

// Verdict semantics use CSS vars so they track the theme. null is NEUTRAL slate,
// never red (DESIGN Sec.1). reject/retracted is the ONLY red, retraction-only.
export const VERDICT: Record<string, string> = {
  confirmed: "var(--confirmed)",
  null: "var(--null)",
  not_testable: "var(--not-testable)",
  descriptive: "var(--ink-3)",
  descriptive_only: "var(--ink-3)",
  pending: "var(--ink-3)",
  reject: "var(--reject)",
};

export function verdictColor(v?: string): string {
  if (!v) return "var(--accent)";
  return VERDICT[v.trim().toLowerCase()] || "var(--accent)";
}

// -- ramps (fixed hex, read on both grounds) --------------------------------

function toRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function lerpHex(a: string, b: string, t: number): string {
  const [ar, ag, ab] = toRgb(a);
  const [br, bg, bb] = toRgb(b);
  const c = (x: number, y: number) => Math.round(x + (y - x) * Math.max(0, Math.min(1, t)));
  const hx = (n: number) => n.toString(16).padStart(2, "0");
  return `#${hx(c(ar, br))}${hx(c(ag, bg))}${hx(c(ab, bb))}`;
}

// Sequential warm ramp, cream -> espresso brown. t in [0,1].
export function seqColor(t: number): string {
  return lerpHex("#F3E4C6", "#7A4E12", t);
}

// Diverging ramp, "vs close, not edge": brick (neg) <-> parchment (0) <-> slate.
export function divColor(t: number): string {
  // t in [-1,1]; 0 is the neutral midpoint.
  if (t >= 0) return lerpHex("#EFE7D8", "#1D5C7A", t);
  return lerpHex("#EFE7D8", "#A6412F", -t);
}

// Rough perceived luminance (0..1) to pick readable text on a filled cell.
export function luminance(hex: string): number {
  const [r, g, b] = toRgb(hex);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

// -- number formatting ------------------------------------------------------

// Compact axis-tick label: trims trailing zeros, keeps small decimals honest.
export function fmtTick(n: number): string {
  if (!Number.isFinite(n)) return "";
  if (n === 0) return "0";
  const abs = Math.abs(n);
  const digits = abs >= 100 ? 0 : abs >= 1 ? 1 : abs >= 0.01 ? 3 : 4;
  return Number(n.toFixed(digits))
    .toString()
    .replace(/\.0+$/, "");
}
