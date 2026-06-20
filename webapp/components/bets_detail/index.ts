// bets_detail/index.ts -- barrel for the W7 card-detail component dir.
//
// Every component is READ-ONLY for other workstreams. W7 owns this dir.
// UNITS / probability only -- no $ field. Calibration not edge.

export { CardDetailView } from "./CardDetailView";
export type { CardDetailViewProps } from "./CardDetailView";
export { BookMatrixTable } from "./BookMatrixTable";
export type { BookMatrixTableProps } from "./BookMatrixTable";
export { DistributionPanel } from "./DistributionPanel";
export type { DistributionPanelProps } from "./DistributionPanel";
export { RationalePanel } from "./RationalePanel";
export type { RationalePanelProps } from "./RationalePanel";
export { LiveBoxPanel } from "./LiveBoxPanel";
export type { LiveBoxPanelProps } from "./LiveBoxPanel";
export { SettleGradePanel } from "./SettleGradePanel";
export type { SettleGradePanelProps } from "./SettleGradePanel";
