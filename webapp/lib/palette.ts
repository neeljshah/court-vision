// palette.ts -- the validated six-slot chart palette (docs/research/site/PALETTE_2026-10-20.md).
// Fixed order, never cycled; colour follows the entity (model = slot 1, market = slot 2).
// Dark is its own selected step, not a flip of the light hex. Pages expose these as CSS
// variables --series-1..6 (see app/(analytics)/analytics/calibration/calibration.css).
export const PALETTE = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"],
} as const;

/** Entity -> CSS variable; text never wears these (text tokens only). */
export const SERIES_VAR = {
  model: "var(--series-1)",
  market: "var(--series-2)",
  baseline: "var(--series-3)",
} as const;
