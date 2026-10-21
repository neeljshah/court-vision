# Model card: ATP tennis pregame match-win probability (Elo + Platt)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: ATP pregame match-win probability, as scored by `scripts/platformkit/proof_tennis/beat_the_close_ml.py`.
- Version: no version tag recorded; the harness sha256 under Receipts pins the code read on 2026-10-20.
- Model family: walk-forward player Elo with a Platt map fit on strictly prior rows (`docs/PROOFS.md`).

## Intended use and non-use

- Use: a calibrated pregame probability that player 1 wins an ATP match; the tennis row of
  `docs/QUANT_BRIEF.md` section 1. Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not a WTA model; WTA calibration is handled by separate harnesses (`docs/PROOFS.md`, tennis table).

## Inputs and data

- Sources: prior match results per player. Exact feature list (surface, etc.): not recorded.
- Window: ATP corpus (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 7,374 matches scored. Date
  span: not recorded.
- As-of: re-run 2026-07-07, unchanged (`docs/QUANT_BRIEF.md` section 1).

## Method

- Never uses winner order; predicts P(p1 wins) on the symmetric p1_id < p2_id ordering; Elo
  walk-forward; Platt on strictly prior rows; the close is comparison only (`docs/PROOFS.md`,
  harness table). Leak assertion pattern:
  [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Devig method: not recorded ([DEVIG_METHODS.md](../method/DEVIG_METHODS.md) lists the methods in use).
- Candidate add-on signals (fatigue, surface, head-to-head) REJECTED on two corpora or the
  null-shuffle / Benjamini-Hochberg test (`docs/MARKET_EFFICIENCY_PROOF.md` section 2); two-corpus
  rule: [MULTICORPUS_ACCEPTANCE.md](../method/MULTICORPUS_ACCEPTANCE.md).

## Evaluation

| As of | Metric | n | Model | Close | Gap | Interval | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-07-07 | Brier | 7,374 | 0.2177 | 0.2028 | +0.0149 | not recorded | none drawn (no interval) | `docs/QUANT_BRIEF.md` section 1; `docs/MARKET_EFFICIENCY_PROOF.md` sections 1 and 4b |

- Paired comparison: model Brier vs close Brier on the same matches. Interval method and MDE: not
  recorded, so no packet verdict applies. The point gap is in the close's favour; the packet reads
  "totals/ATP trail by more (freshness)". QUANT_BRIEF prints "BEHIND (freshness)"; BEHIND is the
  packet's in-game label, so this card does not reuse it.

## Known limitations

- Largest point gap of the pregame Brier rows (+0.0149 against +0.0039 to +0.0076,
  `docs/QUANT_BRIEF.md` section 1); ATP closes are very efficient (`docs/PROOFS.md` line 65).
- No interval on the gap.
- No joined in-game tennis corpus is possible from the capture stores (defect D20,
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md`); this card covers pregame only.
- Per-regime after-ECE tennis 0.016928 (S212, packet section 3) names no forecaster, so it is not
  attributed to this card. Tennis reliability curve: `docs/evidence/calibration/` (whether computed
  on this harness: not recorded).

## Retractions and corrections

- None recorded for this row ([retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)).

## Reproduce

- Private corpus; not reproducible from the public tree (the harness reads local-only corpora).

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/proof_tennis/beat_the_close_ml.py` | 6901 | 0e0b9d6216e9ecbab124cb5ee2c8f3a6a569eba797c03f29ebf65f3e12331e6a | 2026-10-20 | harness (fits at run time; no persisted binary) |

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
