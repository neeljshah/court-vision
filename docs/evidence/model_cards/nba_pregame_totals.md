# Model card: NBA pregame game total (exponentially weighted points model)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: NBA pregame total-points forecast, as scored by `scripts/platformkit/proof_nba/asof_box_accuracy.py`.
- Version: no version tag recorded; the harness sha256 under Receipts pins the code read on 2026-10-20.
- Model family: exponentially weighted points-for / points-against ratings (`docs/PROOFS.md`, harness table).

## Intended use and non-use

- Use: a pregame point estimate of the game total, scored by RMSE against the closing total line.
  Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not a freshness-aware model; it does not see injuries, scratches or lineups.

## Inputs and data

- Sources: prior box-score points for and against per team. Exact feature list: not recorded.
- Window: the NBA 2025-26 odds corpus shared with the moneyline row; 372 games scored
  (`docs/MARKET_EFFICIENCY_PROOF.md` section 1). Exact fit window: not recorded.
- As-of: re-run 2026-07-07, unchanged (`docs/QUANT_BRIEF.md` section 1).
- Data card: `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` card C5 covers the NBA pregame corpus.

## Method

- The rating snapshot is taken BEFORE the game's result is folded in; the close is a comparison
  only (`docs/PROOFS.md`, harness table). Leak assertion pattern:
  [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Walk-forward ratings, held-out second half, RMSE against the closing total.
- Devig: not applicable to a point-total RMSE row (not recorded in the source).
- Second corpus: none for this row.

## Evaluation

| As of | Metric | n | Model | Close | Gap | Interval | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-07-07 | RMSE | 372 | 19.17 | 18.11 | +1.06 | not recorded | none drawn (no interval) | `docs/QUANT_BRIEF.md` section 1; `docs/MARKET_EFFICIENCY_PROOF.md` sections 1 and 4b |

- Paired comparison: model RMSE vs closing-total RMSE on the same games. Interval method and MDE:
  not recorded, so no packet verdict applies. The point gap is in the close's favour; the packet
  reads "totals/ATP trail by more (freshness)". QUANT_BRIEF prints "BEHIND (freshness)"; BEHIND is
  the packet's in-game label, so this card does not reuse it.

## Known limitations

- The point gap is attributed to freshness the close has (injuries, lineups); an availability
  feature was tested to attribute the gap (`proof_nba/totals_with_availability.py`, `docs/PROOFS.md`).
- No interval on the gap, so the size of the deficit is a point estimate.
- O/U calibration (ECE / Brier with a Gaussian sigma fit on the first half) is produced by
  `scripts/platformkit/proof_nba/totals_calibration.py` (`docs/PROOFS.md`); its numbers are not on
  the public surface and are not recorded here.

## Retractions and corrections

- None recorded for this row ([retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)).
- The full-season NBA spread/total walk-forward read closing-line value of about 0
  (`docs/KNOWN_LIMITATIONS.md` line 24); no closing-line-value reading exists for totals.

## Reproduce

- Private corpus; not reproducible from the public tree (the harness reads local-only corpora).

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/proof_nba/asof_box_accuracy.py` | 11998 | 538111865fe0a417f2b6b391a6879d47053aeec47e2d473e9e6358b2de2bb6b1 | 2026-10-20 | harness (fits at run time; no persisted binary) |

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
