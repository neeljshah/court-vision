import { RELATED_READING, RETRACTION_CITATIONS, type RelatedReading, type RetractionCitation } from "./citations";

// Data for the retraction page; lives outside page.tsx because Next only allows the
// documented exports (default, metadata, ...) from a page module.
export type Retraction = {
  id: string;
  sport: string;
  status: "withdrawn" | "superseded" | "withdrawn, no replacement";
  withdrawnMeasurement: string;
  defect: string;
  withdrawnOn: string;
  replacement: string;
  citation: RetractionCitation;
  relatedReading: readonly RelatedReading[];
};

export const RETRACTIONS: readonly Retraction[] = [
  {
    id: "pregame-return",
    sport: "NBA",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +18.38% pregame return figure computed on a market-following baseline",
    defect: "The evaluation CSV had no prediction column. The grader selected direction from the devigged close, used a fixed conversion unavailable in the recorded source, and tuned filters in sample. That is a market-follow artifact, not a model measurement.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    citation: RETRACTION_CITATIONS["pregame-return"],
    relatedReading: [RELATED_READING.ledger],
  },
  {
    id: "end-of-third-quarter-brier",
    sport: "NBA",
    status: "superseded",
    withdrawnMeasurement: "withdrawn: 0.119 end-of-third-quarter Brier score",
    defect: "Two fourth-quarter-derived features entered a model that was predicting the fourth quarter, and the cited file reported a different figure. The original score therefore contained future information.",
    withdrawnOn: "2026-07-23",
    replacement: "Replacement measurement: leak-free walk-forward end-of-third-quarter Brier score 0.141 (unitless), published in JOB_EVIDENCE_PACKET.md on 2026-07-23.",
    citation: RETRACTION_CITATIONS["end-of-third-quarter-brier"],
    relatedReading: [RELATED_READING.stateCalibration],
  },
  {
    id: "in-play-proxy",
    sport: "NBA",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +54.57% / 78.11% in-play accuracy figure measured against a lagged L5 proxy ceiling",
    defect: "The score used an L5 line proxy rather than a real closing reference. It described a soft proxy ceiling, not an externally validated measurement.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    citation: RETRACTION_CITATIONS["in-play-proxy"],
    relatedReading: [RELATED_READING.ledger],
  },
  {
    id: "closing-line-movement",
    sport: "NBA",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +8.94pp closing-line movement calculation",
    defect: "The aggregate was circular: it used the same model-unused, devigged-direction corpus to define and grade the movement calculation. The denominator did not provide an independent comparison.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    citation: RETRACTION_CITATIONS["closing-line-movement"],
    relatedReading: [RELATED_READING.ledger],
  },
  {
    id: "steals-blocks-overfit",
    sport: "NBA",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: steals and blocks training R^2 about 0.79, with leak-free holdout R^2 about 0.06",
    defect: "A leaky grid search inflated the training measurement before the holdout exposed the collapse. Corrective regularization now takes precedence over the stale tuned parameters.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    citation: RETRACTION_CITATIONS["steals-blocks-overfit"],
    relatedReading: [RELATED_READING.ledger],
  },
  {
    id: "assists-playoffs",
    sport: "NBA",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: assists conclusion after postseason stress testing",
    defect: "The measurement was regime-dependent: it failed in the playoffs, and an in-series play-by-play replay confirmed that the earlier conclusion did not hold there.",
    withdrawnOn: "2026-07-21",
    replacement: "No replacement measurement is published.",
    citation: RETRACTION_CITATIONS["assists-playoffs"],
    relatedReading: [RELATED_READING.ledger],
  },
];

/** Validated by the page test so a stale or cross-sport citation cannot ship. */
export function validateRetractionCitations(retractions: readonly Retraction[]): void {
  for (const retraction of retractions) {
    const { citation } = retraction;
    if (!citation.sportsCovered.includes(retraction.sport)) {
      throw new Error(`${retraction.id}: evidence does not cover ${retraction.sport}`);
    }
    if (citation.date < retraction.withdrawnOn && !citation.recordsWithdrawal) {
      throw new Error(`${retraction.id}: evidence predates withdrawal without recording it`);
    }
  }
}
