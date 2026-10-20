# Model card: NBA pregame game total (exponentially weighted points model)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: NBA pregame total-points forecast, as scored by `scripts/platformkit/proof_nba/asof_box_accuracy.py`.
- Version: no version tag recorded; the harness sha256 below pins the code read on 2026-10-20.
- Model family: exponentially weighted points-for / points-against ratings (`docs/PROOFS.md`, harness table).

## Intended use

- A pregame point estimate of the game total, scored by RMSE against the closing total line.
- Calibration and sharpness measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not a freshness-aware model: it does not see injuries, scratches or lineups.

## Inputs and leak guard

- Inputs: prior box-score points for and against per team. Exact feature list: not recorded.
- Leak guard: the rating snapshot is taken BEFORE the game's result is folded in; the close is a
  comparison only (`docs/PROOFS.md`, harness table).

## Training data and period

- The NBA 2025-26 odds corpus shared with the moneyline row; 372 games scored
  (`docs/MARKET_EFFICIENCY_PROOF.md` section 1). Exact fit window: not recorded.
- Data card: `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` card C5 covers the NBA pregame corpus.

## Validation protocol

- Walk-forward ratings, held-out second half, RMSE against the closing total
  (`docs/PROOFS.md`; `docs/MARKET_EFFICIENCY_PROOF.md` section 1).
- Interval on the RMSE gap: not recorded. Devig method: not recorded (RMSE row).
- Second corpus: none for this row.

## Measured performance

| As of | Metric | n | Model | Close | Gap | Verdict | Source |
|---|---|---|---|---|---|---|---|
| 2026-07-07 (re-run, unchanged) | RMSE | 372 | 19.17 | 18.11 | +1.06 | BEHIND (freshness) | `docs/QUANT_BRIEF.md` section 1; `docs/MARKET_EFFICIENCY_PROOF.md` sections 1 and 4b |

## Calibration diagnostics

- O/U calibration (ECE / Brier with a Gaussian sigma fit on the first half, applied to the second)
  is produced by `scripts/platformkit/proof_nba/totals_calibration.py` (`docs/PROOFS.md`); its
  numbers are not on the public surface and are not recorded here.

## Known failure modes and limitations

- Trails the close by the freshness the close has (injuries, lineups); an availability feature was
  tested to attribute the gap (`proof_nba/totals_with_availability.py`, `docs/PROOFS.md`).
- No interval on the gap, so the size of the deficit is a point estimate.

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/platformkit/proof_nba/asof_box_accuracy.py` | 11998 | 538111865fe0a417f2b6b391a6879d47053aeec47e2d473e9e6358b2de2bb6b1 | harness (fits at run time; no persisted binary) |

## Retraction and supersession history

- None recorded for this row.
- The full-season NBA spread/total walk-forward read closing-line value of about 0 (KNOWN_LIMITATIONS line 24); no closing-line-value or 'beats the close' reading exists for totals.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
