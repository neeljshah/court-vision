# results/

Committed artifacts read by the evidence pages. Nothing here is a betting-edge, ROI or dollar claim.

| File | What it is | Where it is cited |
|---|---|---|
| `winprob_walk_forward_results.json` | NBA win probability, 3-fold walk-forward: Brier 0.1930 (std 0.0084), n=1,473; no market baseline in the artifact | EVIDENCE.md section A |
| `holdout_metrics.csv`, `holdout_metrics.png` | LEGACY small-sample placeholder from an early prop-model smoke run (480 holdout rows, 2,400 training rows). Superseded by the production-model chronological holdout in docs/JOB_EVIDENCE_PACKET.md section 3 (20,354 player-games: PTS MAE 4.83, REB 1.92, AST 1.39, FG3M 0.89). Do not quote the CSV's numbers; it is kept because this repository supersedes artifacts by adding the correction, not by deleting the record | superseded |
| `STATUS.md` | the 2026-07 status note from the same smoke run; historical | historical |

The reliability diagrams and CLV plots an earlier version of this page promised were never produced
here: the computer-vision ingest program that would have fed them is paused, and the forward paper
series has zero weeks collected (docs/GO_LIVE_GATES.md). Calibration curves with intervals live on the
analytics site (https://neeljshah.github.io/court-vision/analytics/calibration/) and under
docs/evidence/calibration/.
