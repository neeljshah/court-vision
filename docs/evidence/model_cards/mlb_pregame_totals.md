# Model card: MLB pregame total runs (run-rate model)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: MLB pregame total-runs forecast, as scored by `scripts/platformkit/proof_mlb/beat_the_close_total.py`.
- Version: no version tag recorded; the harness sha256 below pins the code read on 2026-10-20.
- Model family: per-team run-rate lambdas (`docs/PROOFS.md`, harness table).

## Intended use

- A pregame point estimate of total runs, scored by RMSE against the closing total.
- Calibration and sharpness measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.

## Inputs and leak guard

- Inputs: prior runs scored and allowed per team. Exact feature list: not recorded.
- Leak guard: run-rate lambdas are snapshotted BEFORE the game's result is folded in; RMSE on the
  held-out second half (`docs/PROOFS.md`, harness table).

## Training data and period

- MLB corpus 2010-2021 (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 1,679 games scored
  (`docs/QUANT_BRIEF.md` section 1). Fit window boundaries: not recorded.

## Validation protocol

- Walk-forward lambdas, held-out second half, RMSE against the closing total.
- Interval on the RMSE gap: not recorded. Devig: not recorded (RMSE row).

## Measured performance

| As of | Metric | n | Model | Close | Gap | Verdict | Source |
|---|---|---|---|---|---|---|---|
| 2026-07-07 (re-run, unchanged) | RMSE | 1,679 | 4.72 | 4.44 | +0.28 | BEHIND (freshness) | `docs/QUANT_BRIEF.md` section 1; `docs/MARKET_EFFICIENCY_PROOF.md` section 4b |

- A separate benchmark, pregame total-runs CRPS vs market: 2.9331 vs 2.8808, delta -0.0523
  [-0.1657, 0.0482], n=300, UNDERPOWERED (`EVIDENCE.md` section A,
  `scripts/platformkit/benchmarks/crps_market/last_run_mlb.json`). Whether that benchmark uses this
  same rate model: not recorded.

## Calibration diagnostics

- Distributional check: the CRPS benchmark above. Reliability curve for totals: not recorded.

## Known failure modes and limitations

- Trails the close by freshness (starters, lineups, weather) the close has and this model lacks.
- No interval on the RMSE gap.

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/platformkit/proof_mlb/beat_the_close_total.py` | 7511 | a223475cbce07f6aec121a4fb5257b1f4e807b51df66358e839ba4c712c25f34 | harness (fits at run time; no persisted binary) |
| `scripts/platformkit/benchmarks/crps_market/last_run_mlb.json` | 789 | b9510fd80c166947e9e7b75426320f9ed57543ba80d6d4c006ba384ad3fca47f | CRPS benchmark receipt |

## Retraction and supersession history

- None recorded for this row.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
