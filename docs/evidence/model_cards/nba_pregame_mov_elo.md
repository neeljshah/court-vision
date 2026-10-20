# Model card: NBA pregame moneyline win probability (MOV-Elo)

Register row S674. Every number on this card is transcribed from the source named beside it.
Where a fact is not on record it says "not recorded".

## Name and version

- Name: NBA pregame MOV-Elo win probability, as scored by `scripts/platformkit/proof_nba/ml_accuracy.py`.
- Version: no version tag is recorded; the harness file sha256 below pins the code read on 2026-10-20.
- Model family: margin-of-victory Elo, walk-forward (`docs/PROOFS.md`, harness table).

## Intended use

- A calibrated pregame home-win probability for NBA games, used as the team-strength anchor
  and as the yardstick row "model vs the devigged close" on `docs/QUANT_BRIEF.md` section 1.
- Calibration and sharpness measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not evidence of being sharper than the close: the row cannot tell parity from a deficit of
  the MLB size (underpowered, see below).
- Playoff behaviour of this model: not recorded.

## Inputs and leak guard

- Inputs: prior game results and margins from ESPN box scores
  (`data/domains/basketball_nba/espn_boxscores.parquet`); home flag. Feature list beyond the Elo
  state: not recorded.
- Leak guard: the Elo is updated AFTER each game's snapshot is taken; the close is a comparison
  forecaster only and never a model input (`docs/PROOFS.md`, harness table). Truncation-invariance test for this harness: not recorded (data card C5 inherits the phrase from the retracted full-season backtest line, packet section 3).

## Training data and period

- 743 games in the odds-and-outcome overlap, 2025-10-21 to 2026-05-23; 371 fit (first half),
  372 held out (second half) (`docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`, Task B).
- Close: ESPN odds endpoint, provider priority "ESPN BET" then "DraftKings"; the file carries no
  snapshot timestamp (same memo).
- Data card: `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` card C5. Licence: ESPN row is DECIDE
  (`docs/evidence/LICENCE_LEDGER.md` row 1), so no per-game file is published.

## Validation protocol

- Chronological n // 2 split, walk-forward Elo, 1e-6 clip; scored on the held-out half only.
- Interval: game-clustered Diebold-Mariano 95 percent interval (Student-t, G - 1 df); verdict rule
  applied mechanically: MATCHES_CLOSE only if the interval includes 0.
- Memo: `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`; reproduce with
  `python -m scripts.platformkit.eval_gate.dm_recompute_pregame --json <out.json>`.
- Corpora: one (NBA 2025-26). No second NBA pregame corpus is scored for this row.

## Measured performance

| As of | Metric | n | Model | Close | Gap and interval | Verdict | Source |
|---|---|---|---|---|---|---|---|
| 2026-09-24 | Brier vs Shin-devigged close | 372 | 0.1735 | 0.1666 | +0.0069, 95% CI [-0.0038, +0.0175], DM p 0.20 | MATCHES_CLOSE (CI includes 0; underpowered: MDE 0.0152) | `docs/QUANT_BRIEF.md` section 1; `EVIDENCE.md` section A |
| 2026-09-24 | Brier vs proportional-devig close | 372 | 0.1735 | 0.1672 | gap 0.0063 in the memo's primary table, DM p 0.237 | MATCHES_CLOSE | `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` |

## Calibration diagnostics

- Per-sport reliability curves with bootstrap intervals: `docs/evidence/calibration/` and
  `docs/evidence/calibration-decomposition.md`. Whether those curves are computed on this exact
  harness output: not recorded.
- Per-regime recalibration after-ECE nba 0.022205 (S212, `docs/JOB_EVIDENCE_PACKET.md` section 3);
  the forecaster that S212 recalibrated is not named there, so it is not attributed to this card.

## Known failure modes and limitations

- Underpowered: MDE 0.0152 is more than twice the point gap.
- Freshness: the model does not see injuries or lineups; the close does (`docs/MARKET_EFFICIENCY_PROOF.md` section 1).
- The close source has no snapshot timestamp, so it is not established that the price is the
  closing price rather than the price ESPN served when the cache was written (DM memo, Task B).
- Every candidate add-on signal (rest, back-to-back, travel, altitude, form) was REJECTED; the
  schedule signals sign-flipped across the calendar halves (`docs/QUANT_BRIEF.md` section 1).

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/platformkit/proof_nba/ml_accuracy.py` | 5994 | edb843b52f8b937f7159da9223cd3fdd0242d40e69ecc45309c777709c317d83 | harness (fits the model at run time; no persisted binary) |
| `data/cache/kalshi_complete/own_lines_backtest_nba.json` | 720 | abd45a467175f494fc08d788c601974f934f7eba6cab764899cf3f10f4132707 | aggregate result file, local-only (gitignored) |
| `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` | 9115 | 9428dbe523831ae4f80165340ee5a2c8ff5f35c74d6110cf744dd05b1427d45e | interval memo |

Input corpora sha256 (read 2026-09-24) are printed in the DM memo's Inputs table; the corpora are
local-only.

## Retraction and supersession history

- 2026-09-14 correction (packet section 3): an earlier full-season model-vs-close Brier pair had no
  artifact on disk and did not reproduce; it is retired and not quoted here.
- 2026-09-24 / 2026-10-06: the result file and EVIDENCE.md labelled this row TRAILS_CLOSE while its
  interval included 0; superseded by the DM recompute, verdict MATCHES_CLOSE under the written rule.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
