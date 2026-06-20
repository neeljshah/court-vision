// games_depth/index.ts -- barrel for the games-lane depth components.
//
// These ENRICH the per-game card + detail view with the shared depth primitives
// (consumed read-only from @/components/depth). UNITS / probability only; no $.

export { CoherentPrediction } from "./CoherentPrediction";
export type { CoherentPredictionProps } from "./CoherentPrediction";
export { GameMarketSurface } from "./GameMarketSurface";
export type { GameMarketSurfaceProps } from "./GameMarketSurface";
export { ValidatedSignalsStrip } from "./ValidatedSignalsStrip";
export type { ValidatedSignalsStripProps } from "./ValidatedSignalsStrip";
export { sportSignals } from "./sportSignals";
export type { SportSignal } from "./sportSignals";
