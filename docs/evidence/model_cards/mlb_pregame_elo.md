# Model card: MLB pregame moneyline win probability (MOV-Elo)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: MLB pregame MOV-Elo win probability, as scored by `scripts/platformkit/proof_mlb/beat_the_close_ml.py`.
- Version: no version tag recorded; the harness sha256 under Receipts pins the code read on 2026-10-20.
- Model family: walk-forward margin-of-victory Elo (`docs/PROOFS.md`, harness table).

## Intended use and non-use

- Use: a calibrated pregame home-win probability for MLB games; the MLB moneyline row of
  `docs/QUANT_BRIEF.md` section 1. Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not a starter-aware model; it does not see the starting pitcher (DM memo, plain-English reading).

## Inputs and data

- Sources: prior game results and run margins (`data/domains/mlb/games.parquet`); close from
  `data/domains/mlb/odds.parquet` as a comparison only.
- Window: MLB 2010-2021 (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 27,983 games in the
  overlap, 13,992 held out (`docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`, reproduction check).
- As-of: corpora read 2026-09-24 (input sha256 in the DM memo's Inputs table; local-only files).
- Corpus data card for the pregame MLB corpus: not recorded in
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` (its MLB cards C2/C3 are in-game corpora).

## Method

- The Elo updates AFTER each game's snapshot; scored on the held-out second half; the close is
  never an input (`docs/PROOFS.md`, harness table). Leak assertion pattern:
  [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Chronological n // 2 split. Devig: proportional (primary), Shin (sensitivity); see
  [DEVIG_METHODS.md](../method/DEVIG_METHODS.md).
- Candidate add-on signals (rest, streak, head-to-head, open-to-close capture) were scored on two
  corpora (NL and AL) and REJECTED (`docs/PROOFS.md`; `docs/QUANT_BRIEF.md` section 1); two-corpus
  rule: [MULTICORPUS_ACCEPTANCE.md](../method/MULTICORPUS_ACCEPTANCE.md).

## Evaluation

- Paired comparison: model Brier vs devigged-close Brier on the same 13,992 held-out games.
- Interval method: game-clustered Diebold-Mariano 95 percent interval; date-clustered sensitivity
  (1,170 dates) and Shin-devig sensitivity (DM memo).

| As of | Devig | n | Model | Close | Gap and 95% CI | MDE | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-09-24 | proportional | 13,992 | 0.2429 | 0.2390 | +0.0039 [+0.0028, +0.0051], DM p 3.6e-12 | 0.0016 | TRAILS_CLOSE | `CANONICAL_FIGURES.json` mlb_ml_pregame_vs_close |

- BSS vs close -0.0165; the gap is 1.6 percent of the close's Brier (DM memo). The interval
  excludes zero: the close is measurably sharper.

## Known limitations

- No starting-pitcher information; the close carries it.
- The 2010-2021 corpus is historical; behaviour on current seasons: not recorded.
- Per-regime recalibration after-ECE mlb 0.009672 (S212, packet section 3) names no forecaster,
  so it is not attributed to this card. MLB reliability curve: `docs/evidence/calibration/`
  (whether computed on this harness's output: not recorded).

## Retractions and corrections

- Correction 2026-09-24 ([retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)):
  before that date the proof page labelled this row "match, within sampling noise" using a fixed
  0.005 threshold, not an interval; corrected to TRAILS_CLOSE by the DM recompute.

## Reproduce

- Private corpus; not reproducible from the public tree. With the corpora:
  `python -m scripts.platformkit.eval_gate.dm_recompute_pregame --json <out.json>`
  (`EVIDENCE.md` section A). Unit test:
  `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q`.

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/proof_mlb/beat_the_close_ml.py` | 8229 | 66b32c1fae1dbe1d8dc1fd2c02a1ac1e4a6b88eb11a5b4cb9c3ae377f7435d9c | 2026-10-20 | harness (fits at run time; no persisted binary) |

- Interval memo: `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` (as of 2026-09-24); its sha256
  is pinned on `nba_pregame_mov_elo.md`.

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
