# Model card: soccer pregame over/under 2.5 goals (Poisson ratings + pooled Platt)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: soccer pregame O/U 2.5 probability, as scored by `scripts/platformkit/proof_soccer/beat_the_close_ou.py`.
- Version: no version tag recorded; the harness sha256 below pins the code read on 2026-10-20.
- Model family: exponentially weighted Poisson attack/defence ratings with a pooled Platt
  calibration (`docs/PROOFS.md`, harness table; DM memo).

## Intended use

- A calibrated pregame probability that a match has 3 or more goals; the soccer row of
  `docs/QUANT_BRIEF.md` section 1. Calibration and sharpness measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not a 1X2 model: the corpus carries no 1X2 close (a documented data null, `docs/PROOFS.md`).

## Inputs and leak guard

- Inputs: prior match goals and match stats (`data/domains/soccer/matches.parquet`,
  `match_stats.parquet`); close from `odds.parquet` (Pinnacle, per the DM memo) as comparison only.
- Leak guard: the ratings emit a strictly pre-match snapshot; the Platt map is fit on the first
  half and applied to the second (`docs/PROOFS.md`, harness table).

## Training data and period

- Soccer 2019-2026 (`docs/MARKET_EFFICIENCY_PROOF.md` section 4b); 15,115 matches in the overlap,
  7,558 held out (DM memo, reproduction check). Leagues covered: not recorded on this card's sources.

## Validation protocol

- Chronological n // 2 split; game-clustered DM 95 percent interval; date-clustered sensitivity
  (685 dates); Shin-devig sensitivity. Memo: `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`.
- Candidate add-on signals (rest, totals form, head-to-head) REJECTED on two corpora or on the
  null-shuffle / Benjamini-Hochberg test (`docs/MARKET_EFFICIENCY_PROOF.md` section 2).

## Measured performance

| As of | Metric | Devig | n | Model | Close | Gap and interval | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-09-24 | Brier | proportional | 7,558 | 0.2465 | 0.2390 | +0.0076, 95% CI [+0.0059, +0.0092], DM p 1.1e-19 | TRAILS_CLOSE (small, measurable) | `docs/QUANT_BRIEF.md` section 1 |

- BSS vs close -0.0317; MDE 0.0023; the gap is 3.2 percent of the close's Brier (DM memo).

## Calibration diagnostics

- Per-division O/U 2.5 recalibration (ECE improvement) by `proof_soccer/division_calibration.py`
  (`docs/PROOFS.md`); its numbers are not on the public surface. Per-regime after-ECE soccer
  0.009192 (S212, packet section 3); the forecaster S212 recalibrated is not named there.

## Known failure modes and limitations

- Trails a sharp (Pinnacle) close by a small, interval-resolved margin.
- Pooled Platt across leagues; per-league miscalibration is possible (see the division recalibration).

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/platformkit/proof_soccer/beat_the_close_ou.py` | 8544 | 8868780e8fe1b8e71f936300cc1969630e7d95bb3a5a805e157bc917d29608e7 | harness (fits at run time; no persisted binary) |

Input corpora sha256 are printed in the DM memo's Inputs table (local-only files).

## Retraction and supersession history

- Before 2026-09-24 the proof page labelled this row MATCH "within sampling noise" using a fixed
  0.012 threshold, not an interval; corrected to TRAILS_CLOSE by the DM recompute (2026-09-24).

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
