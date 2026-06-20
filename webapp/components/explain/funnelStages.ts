// funnelStages.ts -- the IN-DEPTH funnel narrative for the How-it-works page.
//
// READ-ONLY framing, synthesized from .planning/product/funnel/COVERAGE.md +
// HIGHEST_LEVEL_SCORECARD.md. This is prose, not numbers: every live figure is
// fetched from the API elsewhere. Each stage expands the one-line lib/api
// FUNNEL_STAGES blurb with what the stage IS and the honest discipline on it.
//
// HONESTY RAILS: markets are efficient; more signals/models != more $ edge; a
// gate REJECT is a SUCCESS kept as VALIDATED SCOUTING, never force-fed; UNITS /
// probability only, NO $ field, never a fabricated edge; vs_close UNPROVEN.

export interface FunnelStageDetail {
  key: string;
  label: string;
  /** One-line essence. */
  essence: string;
  /** What the stage IS, in 2-3 honest sentences. */
  detail: string;
  /** The discipline / honest caveat carried at this stage. */
  discipline: string;
  /** Glossary term keys to surface as InfoTips for this stage (decodable terms). */
  tips?: string[];
}

export const FUNNEL_STAGE_DETAIL: FunnelStageDetail[] = [
  {
    key: "data",
    label: "DATA",
    essence: "Raw game truth, ingested per game across four sports.",
    detail:
      "Computer-vision tracking, box scores and play-by-play, plus keyless ESPN / " +
      "Kalshi / Polymarket odds flow in per game for NBA, MLB and soccer (tennis " +
      "shares the engine). Each sport keeps a NARROW served spine plus a wide rim " +
      "of ingested-but-not-served depth.",
    discipline:
      "The close is a yardstick, never a feature. Season-final aggregates are never " +
      "used as features for an individual game (no future leak).",
    tips: ["devig", "provenance"],
  },
  {
    key: "signals",
    label: "SIGNALS",
    essence: "Hundreds of per-player / per-team signals, each gated leak-free.",
    detail:
      "A signal factory proposes candidate features off the data spine. Every one is " +
      "run through the same leak-free, walk-forward, cross-corpus gate before it can " +
      "touch a prediction. The vast majority REJECT -- markets are efficient.",
    discipline:
      "A REJECT is a SUCCESS, kept as VALIDATED SCOUTING. A rejected signal is NEVER " +
      "force-fed into the model (force-feeding destroys calibration: accuracy != edge).",
    tips: ["edge"],
  },
  {
    key: "models",
    label: "MODELS",
    essence: "Win-prob + prop XGB + MOV-Elo, Shin / Platt calibrated.",
    detail:
      "MOV-Elo win-probability, gradient-boosted prop heads and totals models are " +
      "calibrated with Shin de-vig and Platt scaling so the probabilities mean what " +
      "they say. Calibration -- not raw accuracy -- is the objective.",
    discipline:
      "Calibrated to held-out Brier / BSS, not to in-sample fit. Single-fold lifts are " +
      "treated as selection artifacts until they replicate on independent corpora.",
    tips: ["Brier", "BSS", "calibration"],
  },
  {
    key: "engines",
    label: "ENGINES",
    essence: "A possession Monte-Carlo sim turns one anchor into coherent markets.",
    detail:
      "Each sport's engine (NBA possession MC, MLB run-rate NegBinom, soccer EW-Poisson " +
      "+ Dixon-Coles, tennis point-by-point MC) draws ONE game distribution anchored to " +
      "ONE win-prob, so every served market is coherent by construction.",
    discipline:
      "All served markets derive off the SAME anchored distribution -- moneyline, " +
      "spread/handicap and total cannot disagree with each other.",
    tips: ["probability"],
  },
  {
    key: "prediction",
    label: "ONE PREDICTION",
    essence: "One anchor spines every market for a game.",
    detail:
      "The funnel collapses to a single calibrated prediction per market, with the " +
      "provenance (and any scouting-only signals) surfaced alongside the number rather " +
      "than fed into it.",
    discipline:
      "UNITS / probability only -- NO $ field anywhere. edge_claimed = false. vs_close " +
      "is shown as UNPROVEN wherever it is unproven.",
    tips: ["units", "vs_close", "tier"],
  },
  {
    key: "intelligence",
    label: "INTELLIGENCE",
    essence: "Validation + a person-free concept graph close the loop.",
    detail:
      "The in-game repricer conditions on the pre-game prior (the one MEASURED " +
      "calibration improvement), a person-free Obsidian concept graph records what each " +
      "signal means, and the validation gate re-runs every stage. The self-improve " +
      "ratchet is built and READY but INERT (human-gated OFF).",
    discipline:
      "CLV (a better number than the devigged close, in probability space) is the only " +
      "honest yardstick. Real-money execution is default-DENY; paper mode only.",
    tips: ["CLV", "INERT"],
  },
];
