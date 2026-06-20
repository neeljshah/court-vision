// depth/index.ts -- barrel for the shared DEPTH + EXPLAIN primitives.
//
// One import point for the in-depth, self-explaining UI primitives consumed by
// the games / how-it-works / system lanes. Consume read-only; this dir is the
// Phase-1 owner of the shared primitives. UNITS / probability only; no $ field.

export { InfoTip } from "./InfoTip";
export type { InfoTipProps } from "./InfoTip";
export { Legend } from "./Legend";
export type { LegendProps, LegendItem } from "./Legend";
export { ProvenanceBadge } from "./ProvenanceBadge";
export type { ProvenanceBadgeProps } from "./ProvenanceBadge";
export { SignalVerdictBadge } from "./SignalVerdictBadge";
export type {
  SignalVerdictBadgeProps,
  SignalVerdict,
} from "./SignalVerdictBadge";
export { UncertaintyBar } from "./UncertaintyBar";
export type { UncertaintyBarProps } from "./UncertaintyBar";
export { MarketSurfaceTable } from "./MarketSurfaceTable";
export type {
  MarketSurfaceTableProps,
  SurfaceRow,
} from "./MarketSurfaceTable";
export { GLOSSARY, GLOSSARY_TERMS, lookupTerm } from "./glossary";
export type { GlossaryEntry } from "./glossary";
