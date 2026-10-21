# Model card: MLB pregame total runs (run-rate model)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: MLB pregame total-runs forecast, as scored by `scripts/platformkit/proof_mlb/beat_the_close_total.py`.
- Version: no version tag recorded; the harness sha256 under Receipts pins the code read on 2026-10-20.
- Model family: per-team run-rate lambdas (`docs/PROOFS.md`, harness table).

## Intended use and non-use

- Use: a pregame point estimate of total runs, scored by RMSE against the closing total.
  Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.

## Inputs and data

- Sources: prior runs scored and allowed per team. Exact feature list: not recorded.
- Window: MLB corpus 2010-2021 (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 1,679 games scored
  (`docs/QUANT_BRIEF.md` section 1). Fit window boundaries: not recorded.
- As-of: re-run 2026-07-07, unchanged (`docs/QUANT_BRIEF.md` section 1).

## Method

- Run-rate lambdas are snapshotted BEFORE the game's result is folded in; RMSE on the held-out
  second half (`docs/PROOFS.md`, harness table). Leak assertion pattern:
  [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Devig: not applicable to a point-total RMSE row (not recorded in the source).

## Evaluation

| As of | Metric | n | Model | Market | Gap and interval | Verdict | Source |
|---|---|---|---|---|---|---|---|
| 2026-07-07 | RMSE vs closing total | 1,679 | 4.72 | 4.44 | +0.28; interval not recorded | none drawn (no interval) | `docs/QUANT_BRIEF.md` section 1 |
| recorded receipt | CRPS vs market, pregame total runs | 300 | 2.9331 | 2.8808 | -0.0523 [-0.1657, 0.0482] | UNDERPOWERED | `EVIDENCE.md` section A; `last_run_mlb.json` |

- RMSE row: interval method and MDE not recorded, so no packet verdict applies; the point gap is
  in the close's favour (the packet reads "totals/ATP trail by more (freshness)"). QUANT_BRIEF
  prints "BEHIND (freshness)"; BEHIND is the packet's in-game label, so it is not reused here.
- CRPS row: the interval includes zero, so we cannot tell. Whether that benchmark uses this same
  rate model: not recorded.

## Known limitations

- The point gap is attributed to freshness (starters, lineups, weather) the close has and this
  model lacks.
- No interval on the RMSE gap. Reliability curve for totals: not recorded.

## Retractions and corrections

- None recorded for this row ([retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)).

## Reproduce

- Private corpus; not reproducible from the public tree. The CRPS receipt is a recorded artifact
  (`RECEIPTS.md` row); regenerating it needs the private corpora.

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/proof_mlb/beat_the_close_total.py` | 7511 | a223475cbce07f6aec121a4fb5257b1f4e807b51df66358e839ba4c712c25f34 | 2026-10-20 | harness (fits at run time; no persisted binary) |
| `scripts/platformkit/benchmarks/crps_market/last_run_mlb.json` | 789 | b9510fd80c166947e9e7b75426320f9ed57543ba80d6d4c006ba384ad3fca47f | 2026-10-20 | CRPS benchmark receipt |

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
