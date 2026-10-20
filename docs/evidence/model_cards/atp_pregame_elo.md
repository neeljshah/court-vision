# Model card: ATP tennis pregame match-win probability (Elo + Platt)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: ATP pregame match-win probability, as scored by `scripts/platformkit/proof_tennis/beat_the_close_ml.py`.
- Version: no version tag recorded; the harness sha256 below pins the code read on 2026-10-20.
- Model family: walk-forward player Elo with a Platt map fit on strictly prior rows (`docs/PROOFS.md`).

## Intended use

- A calibrated pregame probability that player 1 wins an ATP match; the tennis row of
  `docs/QUANT_BRIEF.md` section 1. Calibration and sharpness measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not a WTA model: WTA calibration is handled by separate harnesses (`docs/PROOFS.md`, tennis table).

## Inputs and leak guard

- Inputs: prior match results per player. Exact feature list (surface, etc.): not recorded.
- Leak guard: never uses winner order; predicts P(p1 wins) on the symmetric p1_id < p2_id
  ordering; Elo walk-forward; Platt on strictly prior rows; the close is comparison only
  (`docs/PROOFS.md`, harness table).

## Training data and period

- ATP corpus (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 7,374 matches scored. Date span: not recorded.

## Validation protocol

- Walk-forward Elo and walk-forward Platt, scored on held-out matches. Interval on the gap: not
  recorded. Devig method: not recorded.
- Candidate add-on signals (fatigue, surface, head-to-head) REJECTED on two corpora or the
  null-shuffle / Benjamini-Hochberg test (`docs/MARKET_EFFICIENCY_PROOF.md` section 2).

## Measured performance

| As of | Metric | n | Model | Close | Gap | Verdict | Source |
|---|---|---|---|---|---|---|---|
| 2026-07-07 (re-run, unchanged) | Brier | 7,374 | 0.2177 | 0.2028 | +0.0149 | BEHIND (freshness) | `docs/QUANT_BRIEF.md` section 1; `docs/MARKET_EFFICIENCY_PROOF.md` sections 1 and 4b |

## Calibration diagnostics

- Tennis reliability curve: `docs/evidence/calibration/` (whether computed on this harness: not
  recorded). Per-regime after-ECE tennis 0.016928 (S212, packet section 3); the forecaster S212
  recalibrated is not named there.

## Known failure modes and limitations

- Largest Brier gap of the pregame Brier rows (+0.0149 against +0.0039 to +0.0076, QUANT_BRIEF section 1); ATP closes are very efficient (PROOFS.md line 65).
- No interval on the gap.
- No joined in-game tennis corpus is possible from the capture stores (defect D20,
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md`); this card covers pregame only.

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/platformkit/proof_tennis/beat_the_close_ml.py` | 6901 | 0e0b9d6216e9ecbab124cb5ee2c8f3a6a569eba797c03f29ebf65f3e12331e6a | harness (fits at run time; no persisted binary) |

## Retraction and supersession history

- None recorded for this row.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
