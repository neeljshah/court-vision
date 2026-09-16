/* Chart cell ink -- pick the ink a cell fill can actually carry.
   WCAG 2 AA wants 4.5:1 for cell text, and the sequential ramp runs from a pale
   fill to a dark one, so a single ink colour cannot serve every step. The ramp
   endpoints mirror --chart-seq-low / --chart-seq-high in the LIGHT theme of
   app/(analytics)/analytics.css; the dark theme ramp is dark end to end, so its
   stylesheet pins every step to the on-dark ink instead. */

export const CHART_INK_ON_DARK = "#FFFFFF";
export const CHART_INK_ON_LIGHT = "#182630";

const SEQUENTIAL_LOW = "#D9E9E5";
const SEQUENTIAL_HIGH = "#155642";
const SEQUENTIAL_STEPS = 4;

export type CellInk = "light" | "dark";

function channels(hex: string): number[] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16));
}

export function relativeLuminance(hex: string): number {
  const [red, green, blue] = channels(hex).map(value => {
    const scaled = value / 255;
    return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

export function contrastRatio(a: string, b: string): number {
  const [high, low] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

/** color-mix(in srgb, a <weightA>%, b) -- a straight channel blend of the ramp endpoints. */
export function mixHex(a: string, b: string, weightA: number): string {
  const [from, to] = [channels(a), channels(b)];
  return `#${from.map((value, index) => Math.round(value * weightA + to[index] * (1 - weightA)).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
}

export function sequentialFill(step: number): string {
  return mixHex(SEQUENTIAL_LOW, SEQUENTIAL_HIGH, 1 - Math.min(SEQUENTIAL_STEPS, Math.max(0, step)) / SEQUENTIAL_STEPS);
}

/** "light" means light ink on a dark fill; "dark" means dark ink on a light fill. */
export function cellInk(fill: string): CellInk {
  return contrastRatio(fill, CHART_INK_ON_DARK) >= contrastRatio(fill, CHART_INK_ON_LIGHT) ? "light" : "dark";
}

export function sequentialInk(step: number): CellInk {
  return cellInk(sequentialFill(step));
}
