# S281 NBA in-game momentum microstructure

## Verdict: NULL

Preregistration: `docs/evidence/harness/S281_ingame_momentum_microstructure_2026-09-04_PREREG.md`
Preregistration SHA-256: `10ddf9f7845b2a63cf02ac30247100b82ec06f8a5ad871978d0ab1c5cea1202b`

## Premise

The verified source columns are `game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue`; `event_key` is NOT FOUND. Five distinct monotonic-tick rows confirmed score and margin construction before scoring (the source is fully enumerated in the summary).

## Brier comparison

| population | recal_null Brier | recal_null plus momentum Brier | improvement (95 pct game-clustered CI) | ticks / games |
|---|---:|---:|---:|---:|
| fresh | 0.145658245 | 0.153373477 | -0.007715231 [-0.009884915, -0.005628992] | 230331 / 1582 |
| stale | 0.000101394 | 0.000657332 | -0.000555938 [-0.000643180, -0.000412784] | 46106 / 1132 |
| pooled | 0.073422184 | 0.077525966 | -0.004103782 [-0.005209973, -0.003056898] | 460365 / 1582 |

Stale-minus-fresh interaction: 0.007159293 [0.005037230, 0.009356471].
The frozen pooled bar is +0.004. This result is NULL; no AHEAD claim is made.

## Method and reconstruction

`run_120s` uses only same-game, strictly prior ticks in the fixed 120-second window; first/no-prior-window ticks receive 0.0. `run_just_ended` uses the fixed absolute run threshold of 6.0. The additive logistic arm receives separate recal_null, run_120s, and run_just_ended terms only.
The unmodified recal_null route left 3302 named seed ticks unavailable. The scorer created 461947 stable per-tick states, then scored 460365 non-first-tick rows through cpcv_evaluate with the shared purge and a symmetric one-day embargo. Both archive losses derive exclusively from identity-matched evaluator records.
The paired CSV contains stable state keys, predictions, outcomes, and both losses; it reconstructs every reported Brier value without a runtime model state. At 93921529 bytes it exceeds the 50 MB evidence limit, so it remains local-only at the gitignored path `docs/evidence/harness/S281_ingame_momentum_microstructure_2026-09-04_state_differentials.csv`. Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; tabular, resolution not applicable). RSS: 1184382976 bytes. Route SHA-256 after the local-only filename correction: `2f3237ecc060fa65b00becdf7916e818c55c8bebceb4cb3d054c9026d13fbdc6`.
Focused test: `python -m pytest tests/platformkit/ingame/test_s281_ingame_momentum_microstructure.py -q -p no:cacheprovider` (run on the pod because the archive test is heavy).

## NOT VERIFIED

- RSS is environment-dependent; no external deployment was verified.

## Contract self-check

- B1: all source ticks are featured; first/no-prior-window ticks are named boundary values, bins are outcome-independent, and no loss-based row is dropped. B2-B6: additive route and artifacts only; no reader, deployment, flag, register, ledger, or data store changed. B7-B9: exhaustive per-tick, game-clustered calculation. B10 and Q3: the +0.004 bar is unchanged.
- Q1: the committed, LF-normalized preregistration seal is named above and was verified before scoring. Q2: no charge, ledger, or K read. Q4: cpcv_evaluate supplies purge and symmetric embargo with one state per scored tick. Q5: no AHEAD claim. Q6: calibration language only. Q7: reproduction replaces eye sampling. Q8: the schema premise was re-measured first. Q9: paired losses and reconstructible route are archived.
