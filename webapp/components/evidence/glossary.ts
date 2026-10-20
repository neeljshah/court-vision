// glossary.ts -- the Term tooltip texts, copied VERBATIM from docs/GLOSSARY.md (the test
// glossary.test.ts reads that file and fails when an entry here stops matching it). Add a
// term there first, then here. Calibration language only.
export const GLOSSARY_PATH = "docs/GLOSSARY.md";

export const GLOSSARY = {
  "brier": {
    term: "Brier score",
    text: "mean squared error of probabilistic forecasts (lower = sharper).",
  },
  "devigged-close": {
    term: "Devigged close",
    text: "the closing line with the vig removed, i.e. the market's fair probability at the final pre-game price; the comparison forecaster for every pregame-vs-close row (see Devig / Shin devig and Closing line).",
  },
  "crps": {
    term: "CRPS / pinball loss",
    text: "proper scores for full predictive distributions / quantiles.",
  },
  "diebold-mariano": {
    term: "Diebold-Mariano (DM) test",
    text: "a statistical test for whether one forecaster is significantly more accurate than another; used cluster-robust here.",
  },
  "mde": {
    term: "MDE (minimum detectable effect)",
    text: "the smallest Brier gap a row's 95% interval could have resolved, 1.429 x the interval half-width (DM_RECOMPUTE_2026-09-24); a row whose measured gap is below its MDE is underpowered, so MATCHES_CLOSE (underpowered) means \"not resolved\", not parity.",
  },
  "calibration-vs-resolution": {
    term: "Calibration vs resolution (Murphy decomposition)",
    text: "Brier splits into reliability (the calibration error: how far observed frequency sits from the forecast in each bin, fixable by recalibrating) and resolution (how much the forecasts separate outcomes: information that recalibrating cannot manufacture). A market can lead on resolution while both forecasters are calibrated.",
  },
} as const;

export type GlossaryId = keyof typeof GLOSSARY;
export const GLOSSARY_IDS = Object.keys(GLOSSARY) as GlossaryId[];
