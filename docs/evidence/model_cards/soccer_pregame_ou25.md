# Model card: soccer pregame over/under 2.5 goals (Poisson ratings + pooled Platt)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: soccer pregame O/U 2.5 probability, as scored by `scripts/platformkit/proof_soccer/beat_the_close_ou.py`.
- Version: no version tag recorded; the harness sha256 under Receipts pins the code read on 2026-10-20.
- Model family: exponentially weighted Poisson attack/defence ratings with a pooled Platt
  calibration (`docs/PROOFS.md`, harness table; DM memo).

## Intended use and non-use

- Use: a calibrated pregame probability that a match has 3 or more goals; the soccer row of
  `docs/QUANT_BRIEF.md` section 1. Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not a 1X2 model; the corpus carries no 1X2 close (a documented data null, `docs/PROOFS.md`).

## Inputs and data

- Sources: prior match goals and match stats (`data/domains/soccer/matches.parquet`,
  `match_stats.parquet`); close from `odds.parquet` (Pinnacle, per the DM memo) as comparison only.
- Window: soccer 2019-2026 (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 15,115 matches in the
  overlap, 7,558 held out (`docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`, reproduction check).
  Leagues covered: not recorded on this card's sources.
- As-of: corpora read 2026-09-24 (input sha256 in the DM memo's Inputs table; local-only files).

## Method

- The ratings emit a strictly pre-match snapshot; the Platt map is fit on the first half and
  applied to the second (`docs/PROOFS.md`, harness table). Leak assertion pattern:
  [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Chronological n // 2 split. Devig: proportional (primary), Shin (sensitivity); see
  [DEVIG_METHODS.md](../method/DEVIG_METHODS.md).
- Candidate add-on signals (rest, totals form, head-to-head) REJECTED on two corpora or on the
  null-shuffle / Benjamini-Hochberg test (`docs/MARKET_EFFICIENCY_PROOF.md` section 2); two-corpus
  rule: [MULTICORPUS_ACCEPTANCE.md](../method/MULTICORPUS_ACCEPTANCE.md).

## Evaluation

- Paired comparison: model Brier vs devigged-close Brier on the same 7,558 held-out matches.
- Interval method: game-clustered Diebold-Mariano 95 percent interval; date-clustered sensitivity
  (685 dates) and Shin-devig sensitivity (DM memo).

| As of | Devig | n | Model | Close | Gap and 95% CI | MDE | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-09-24 | proportional | 7,558 | 0.2465 | 0.2390 | +0.0076 [+0.0059, +0.0092], DM p 1.1e-19 | 0.0023 | TRAILS_CLOSE | `CANONICAL_FIGURES.json` soccer_ou25_pregame_vs_close |
| 2026-09-24 | Shin (sensitivity) | 7,555 | not recorded | not recorded | same gap, [0.006, 0.0093] | not recorded | TRAILS_CLOSE | `CANONICAL_FIGURES.json` also_ci95 |

- BSS vs close -0.0317; the gap is 3.2 percent of the close's Brier (DM memo). Both intervals
  exclude zero: the close is measurably sharper.

## Known limitations

- Trails a sharp (Pinnacle) close by a small, interval-resolved margin.
- Pooled Platt across leagues; per-league miscalibration is possible. Per-division O/U 2.5
  recalibration is run by `proof_soccer/division_calibration.py` (`docs/PROOFS.md`); its numbers
  are not on the public surface.
- Per-regime after-ECE soccer 0.009192 (S212, packet section 3) names no forecaster, so it is not
  attributed to this card.

## Retractions and corrections

- Correction 2026-09-24 ([retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)):
  before that date the proof page labelled this row "match, within sampling noise" using a fixed
  0.012 threshold, not an interval; corrected to TRAILS_CLOSE by the DM recompute.

## Reproduce

- Private corpus; not reproducible from the public tree. With the corpora:
  `python -m scripts.platformkit.eval_gate.dm_recompute_pregame --json <out.json>`
  (`EVIDENCE.md` section A). Unit test:
  `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q`.

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/proof_soccer/beat_the_close_ou.py` | 8544 | 8868780e8fe1b8e71f936300cc1969630e7d95bb3a5a805e157bc917d29608e7 | 2026-10-20 | harness (fits at run time; no persisted binary) |

- Interval memo: `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` (as of 2026-09-24); its sha256
  is pinned on `nba_pregame_mov_elo.md`.

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
