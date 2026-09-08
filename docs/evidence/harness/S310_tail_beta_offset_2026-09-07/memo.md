# S310 tail beta-offset calibration screen

Verdict: CLOSED_AT_LIMIT

Preregistration: `docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg.md`

Preregistration SHA-256: `0b7ed9caa1bdb0e08b34fbf81fd19a7266cd00c2f6f86f1cdca4b5ba8cefafbd`

Supplement: `docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg_supplement.md`

Supplement SHA-256: `4f9898cf09f46f91253286ba2ccd8047813b46fbd920bf6ad81b4740dc10a904`

Corrected supplement: `docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg_supplement_corrected.md`

Corrected supplement SHA-256: `aaecd6956b75c305118a24b0156510e79cd483c1875e42ebd1afff704c5f0e00`

Sign convention: improvement equals baseline loss minus candidate loss; positive means candidate better.

| population | baseline log loss | candidate log loss | log-loss improvement 95 pct CI | Brier improvement 95 pct CI | game clusters |
|---|---:|---:|---|---|---:|
| low | 0.099290493 | 0.103380344 | -0.004089851 [-0.018882212, +0.005967350] | -0.000170521 [-0.000772329, +0.000262794] | 557 |
| high | 0.123486240 | 0.127690441 | -0.004204200 [-0.007379012, +0.001553461] | -0.000335411 [-0.000565462, +0.000072711] | 718 |
| tail | 0.113579822 | 0.117737205 | -0.004157383 [-0.010714071, +0.001495545] | -0.000267901 [-0.000569351, +0.000048318] | 1267 |
| global | 0.458163609 | 0.458524706 | -0.000361098 [-0.000917634, +0.000123317] | -0.000023269 [-0.000049503, +0.000003889] | 1593 |

Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; 465249 rows; tabular, resolution not applicable).
Columns: row_index, game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue. First three game ids: 401704627, 401704627, 401704627.
Grain (supplement amendment 1): one state per game_id, period and floor(game_clock_s / 30); 465249 source rows become 117964 evaluator states over 1593 game clusters.
Binding premise remeasured on this grain: raw 0.01-0.05 contains 4420 states across 570 game clusters and 26 positive-outcome clusters (tick grain: 9226, 649, 29).
The low/high bin results are descriptive only; no separate bin conditional proposal is made, so Holm has no claimed-bin family to adjust.
The S272 trainable-tail oracle cap 0.002534 remains a precision limit, not a global result.

## Corrections applied at landing

Applied by the lander from `docs/evidence/harness/S310_VERIFY_2026-09-08.md` (verified: codex-sol, contract A/B/Q):

1. Input metadata reported 117964 rows, which is the evaluator-state count and not the source-row count. Line 26 above and `summary.json` `input.rows` now read 465249 source rows; `grain.states` stays 117964.
2. The lane appended a row to `docs/evidence/RESULTS_LEDGER_SYSTEM.md` although preregistration line 17 forbids lane ledger writes. That row was not carried from the candidate diff. The landing appends the verifier's proposed ledger row, and the lane's row text as a second row attributed to the lane.
3. Master lacked `tests/platformkit/test_s310_tail_beta_offset.py`, so the contract A1 master rerun was unavailable at verification time. This landing adds that test file and runs it on master.

## NOT VERIFIED

- The grain change itself: results are not comparable tick-for-tick with the original all-tick design, and the global guard denominator no longer contains the settled terminal snapshots.
- Independent-corpus replication.
- Any deployment, flag, registry, ledger, or global calibration claim.
