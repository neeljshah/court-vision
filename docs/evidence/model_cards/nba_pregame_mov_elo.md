# Model card: NBA pregame moneyline win probability (MOV-Elo)

Register row S674. Every number on this card is transcribed from the source named beside it;
where a fact is not on record it says "not recorded".

- Name: NBA pregame MOV-Elo win probability, as scored by `scripts/platformkit/proof_nba/ml_accuracy.py`.
- Version: no version tag is recorded; the harness sha256 under Receipts pins the code read on 2026-10-20.
- Model family: margin-of-victory Elo, walk-forward (`docs/PROOFS.md`, harness table).

## Intended use and non-use

- Use: a calibrated pregame home-win probability for NBA games, used as the team-strength anchor
  and as the yardstick row "model vs the devigged close" on `docs/QUANT_BRIEF.md` section 1.
  Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not evidence of being sharper than the close; the row cannot tell parity from a deficit
  of the MLB size (underpowered, see Evaluation).
- Playoff behaviour of this model: not recorded.

## Inputs and data

- Sources: prior game results and margins from ESPN box scores
  (`data/domains/basketball_nba/espn_boxscores.parquet`); home flag. Feature list beyond the Elo
  state: not recorded.
- Close: ESPN odds endpoint, provider priority "ESPN BET" then "DraftKings"; the file carries no
  snapshot timestamp (`docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`, Task B).
- Window: 743 games in the odds-and-outcome overlap, 2025-10-21 to 2026-05-23; 371 fit (first
  half), 372 held out (second half) (DM memo, Task B).
- As-of: corpora read 2026-09-24 (input sha256 in the DM memo's Inputs table; files are local-only).
- Data card: `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md` card C5. Licence: ESPN row is DECIDE
  (`docs/evidence/LICENCE_LEDGER.md` row 1), so no per-game file is published.

## Method

- Walk-forward Elo: the rating is updated AFTER each game's snapshot is taken; the close is a
  comparison forecaster only and never a model input (`docs/PROOFS.md`, harness table). Leak
  assertion pattern: [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Chronological n // 2 split, 1e-6 clip; scored on the held-out half only.
- Devig: Shin (primary) and proportional (sensitivity); see [DEVIG_METHODS.md](../method/DEVIG_METHODS.md).
- Truncation-invariance test for this harness: not recorded (data card C5 inherits the phrase from
  the retired full-season backtest line, packet section 3).
- Corpora: one (NBA 2025-26). No second NBA pregame corpus is scored for this row, so the
  two-corpus rule of [MULTICORPUS_ACCEPTANCE.md](../method/MULTICORPUS_ACCEPTANCE.md) is not met.

## Evaluation

- Paired comparison: model Brier vs devigged-close Brier on the same 372 held-out games.
- Interval method: game-clustered Diebold-Mariano 95 percent interval (Student-t, G - 1 df).

| As of | Devig | n | Model | Close | Gap and 95% CI | MDE | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| 2026-09-24 | Shin | 372 | 0.1735 | 0.1666 | +0.0069 [-0.0038, +0.0175], DM p 0.20 | 0.0152 | MATCHES_CLOSE (underpowered) | `CANONICAL_FIGURES.json` nba_ml_pregame_vs_close_shin |
| 2026-09-24 | proportional | 372 | 0.1735 | 0.1672 | +0.0063 [-0.0042, +0.0168], DM p 0.237 | 0.015 | MATCHES_CLOSE (underpowered) | `CANONICAL_FIGURES.json` nba_ml_pregame_vs_close_proportional |

- Reading: both intervals include zero, so we cannot tell whether the model trails the close;
  MDE 0.0152 is more than twice the point gap.

## Known limitations

- Underpowered: a deficit the size of the MLB moneyline row could not be detected at n=372.
- Freshness: the model does not see injuries or lineups; the close does
  (`docs/MARKET_EFFICIENCY_PROOF.md` section 1).
- The close source has no snapshot timestamp, so it is not established that the price is the
  closing price rather than the price ESPN served when the cache was written (DM memo, Task B).
- Every candidate add-on signal (rest, back-to-back, travel, altitude, form) was REJECTED; the
  schedule signals sign-flipped across the calendar halves (`docs/QUANT_BRIEF.md` section 1).
- Per-regime recalibration after-ECE nba 0.022205 (S212, packet section 3) names no forecaster,
  so it is not attributed to this card. Reliability curves: `docs/evidence/calibration/`;
  whether they are computed on this exact harness output: not recorded.

## Retractions and corrections

- 2026-09-14 correction (packet section 3; [retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)):
  an earlier full-season model-vs-close Brier pair had no artifact on disk and did not reproduce;
  it is retired and not quoted here.
- 2026-09-24 / 2026-10-06 correction: the result file and EVIDENCE.md labelled this row
  TRAILS_CLOSE while its interval included 0; corrected by the DM recompute to MATCHES_CLOSE under
  the written rule (`docs/JOB_EVIDENCE_PACKET.md`, "Corrected 2026-10-06").

## Reproduce

- Private corpus; not reproducible from the public tree. With the corpora:
  `python -m scripts.platformkit.eval_gate.dm_recompute_pregame --json <out.json>`
  (`EVIDENCE.md` section A; DM memo). Unit test:
  `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q`.

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/proof_nba/ml_accuracy.py` | 5994 | edb843b52f8b937f7159da9223cd3fdd0242d40e69ecc45309c777709c317d83 | 2026-10-20 | harness (fits at run time; no persisted binary) |
| `data/cache/kalshi_complete/own_lines_backtest_nba.json` | 720 | abd45a467175f494fc08d788c601974f934f7eba6cab764899cf3f10f4132707 | 2026-10-20 | aggregate result file, local-only (gitignored) |
| `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` | 9115 | 9428dbe523831ae4f80165340ee5a2c8ff5f35c74d6110cf744dd05b1427d45e | 2026-09-24 | interval memo |

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
