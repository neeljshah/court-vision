// risk/index.ts -- barrel for the /risk page's components.
//
// The honest UNIT-space RISK view: per-bet risk cards, portfolio risk, and the
// exposure/limits policy. Consumes the FROZEN shared @/lib/api + @/components/depth
// only -- it never edits Nav / lib / tokens / layout. UNITS / probability only;
// NO $ field; descriptive risk; real money DENY (paper only).

export { BestBetsRisk } from "./BestBetsRisk";
export { BestBetRiskCard } from "./BestBetRiskCard";
export { PortfolioRiskPanel } from "./PortfolioRiskPanel";
export { ExposureLimitsPanel } from "./ExposureLimitsPanel";
export { RISK_TERMS } from "./riskTerms";
export {
  betRiskRow,
  qualifyingRows,
  pctOrDash,
  unitsOrDash,
  TIER_FLOORS,
  PROXY_FLOOR_BUMP,
} from "./riskUtils";
export type { BetRiskRow } from "./riskUtils";
