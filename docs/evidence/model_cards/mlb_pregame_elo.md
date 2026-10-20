# Model card: MLB pregame moneyline win probability (MOV-Elo)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: MLB pregame MOV-Elo win probability, as scored by `scripts/platformkit/proof_mlb/beat_the_close_ml.py`.
- Version: no version tag recorded; the harness sha256 below pins the code read on 2026-10-20.
- Model family: walk-forward margin-of-victory Elo (`docs/PROOFS.md`, harness table).

## Intended use

- A calibrated pregame home-win probability for MLB games; the MLB moneyline row of
  `docs/QUANT_BRIEF.md` section 1. Calibration and sharpness measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not a starter-aware model: it does not see the starting pitcher (DM memo, plain-English reading).

## Inputs and leak guard

- Inputs: prior game results and run margins (`data/domains/mlb/games.parquet`); close from
  `data/domains/mlb/odds.parquet` as a comparison only.
- Leak guard: the Elo updates AFTER each game's snapshot; scored on the held-out second half;
  the close is never an input (`docs/PROOFS.md`, harness table).

## Training data and period

- MLB 2010-2021 (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 27,983 games in the overlap,
  13,992 held out (DM memo, reproduction check).
- Corpus data card for the pregame MLB corpus: not recorded in
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` (its MLB cards C2/C3 are in-game corpora).

## Validation protocol

- Chronological n // 2 split; game-clustered DM 95 percent interval; date-clustered sensitivity
  (1,170 dates); Shin-devig sensitivity. Verdict rule: MATCHES_CLOSE only if the interval includes 0.
- Memo: `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`.
- Candidate add-on signals (rest, streak, head-to-head, open-to-close capture) scored on two
  corpora (NL and AL) and REJECTED (`docs/PROOFS.md`; `docs/QUANT_BRIEF.md` section 1).

## Measured performance

| As of | Metric | Devig | n | Model | Close | Gap and interval | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-09-24 | Brier | proportional | 13,992 | 0.2429 | 0.2390 | +0.0039, 95% CI [+0.0028, +0.0051], DM p 3.6e-12 | TRAILS_CLOSE (small, measurable) | `docs/QUANT_BRIEF.md` section 1 |

- BSS vs close -0.0165; MDE 0.0016; the gap is 1.6 percent of the close's Brier (DM memo).

## Calibration diagnostics

- MLB reliability curve: `docs/evidence/calibration/` (whether computed on this harness's output:
  not recorded). Per-regime recalibration after-ECE mlb 0.009672 (S212, packet section 3); the
  forecaster S212 recalibrated is not named there, so it is not attributed to this card.

## Known failure modes and limitations

- No starting-pitcher information; the close carries it.
- The 2010-2021 corpus is historical; behaviour on current seasons: not recorded.

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/platformkit/proof_mlb/beat_the_close_ml.py` | 8229 | 66b32c1fae1dbe1d8dc1fd2c02a1ac1e4a6b88eb11a5b4cb9c3ae377f7435d9c | harness (fits at run time; no persisted binary) |

Input corpora sha256 are printed in the DM memo's Inputs table (local-only files).

## Retraction and supersession history

- Before 2026-09-24 the proof page labelled this row MATCH "within sampling noise" using a fixed
  0.005 threshold, not an interval; corrected to TRAILS_CLOSE by the DM recompute (2026-09-24).

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
