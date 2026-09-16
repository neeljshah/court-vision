// Data for the retraction page; lives outside page.tsx because Next only allows the
// documented exports (default, metadata, ...) from a page module.
export type Retraction = {
  id: string;
  status: "withdrawn" | "superseded" | "withdrawn, no replacement";
  withdrawnMeasurement: string;
  defect: string;
  withdrawnOn: string;
  replacement: string;
  evidenceArtifact: string;
  evidenceSourceId: string;
};

export const RETRACTIONS: readonly Retraction[] = [
  {
    id: "pregame-return",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +18.38% pregame return figure computed on a market-following baseline",
    defect: "The evaluation CSV had no prediction column. The grader selected direction from the devigged close, used a fixed conversion unavailable in the recorded source, and tuned filters in sample. That is a market-follow artifact, not a model measurement.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "end-of-third-quarter-brier",
    status: "superseded",
    withdrawnMeasurement: "withdrawn: 0.119 end-of-third-quarter Brier score",
    defect: "Two fourth-quarter-derived features entered a model that was predicting the fourth quarter, and the cited file reported a different figure. The original score therefore contained future information.",
    withdrawnOn: "2026-07-23",
    replacement: "Replacement measurement: leak-free walk-forward end-of-third-quarter Brier score 0.141 (unitless), published in JOB_EVIDENCE_PACKET.md on 2026-07-23.",
    evidenceArtifact: "state_conditioned_calibration.json",
    evidenceSourceId: "state_conditioned_calibration",
  },
  {
    id: "in-play-proxy",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +54.57% / 78.11% in-play accuracy figure measured against a lagged L5 proxy ceiling",
    defect: "The score used an L5 line proxy rather than a real closing reference. It described a soft proxy ceiling, not an externally validated measurement.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "closing-line-movement",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: +8.94pp closing-line movement calculation",
    defect: "The aggregate was circular: it used the same model-unused, devigged-direction corpus to define and grade the movement calculation. The denominator did not provide an independent comparison.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "steals-blocks-overfit",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: steals and blocks training R^2 about 0.79, with leak-free holdout R^2 about 0.06",
    defect: "A leaky grid search inflated the training measurement before the holdout exposed the collapse. Corrective regularization now takes precedence over the stale tuned parameters.",
    withdrawnOn: "2026-07-23",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
  {
    id: "assists-playoffs",
    status: "withdrawn, no replacement",
    withdrawnMeasurement: "withdrawn: assists conclusion after postseason stress testing",
    defect: "The measurement was regime-dependent: it failed in the playoffs, and an in-series play-by-play replay confirmed that the earlier conclusion did not hold there.",
    withdrawnOn: "2026-07-21",
    replacement: "No replacement measurement is published.",
    evidenceArtifact: "fwd_claim_scoreboard.json",
    evidenceSourceId: "fwd_claim_scoreboard",
  },
];
