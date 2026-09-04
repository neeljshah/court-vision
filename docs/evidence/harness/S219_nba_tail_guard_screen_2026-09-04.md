# S219 NBA tail guard screen (2026-09-04)

## Verdict: SCREEN NULL

The composite fails the frozen +0.004 Brier bar against the S123 `ladder_base` incumbent. Its game-clustered interval is below zero. This is an uncharged calibration screen: no preregistration, K read, charge, register write, or ledger call occurred.

## Inputs and premise remeasurement

Fresh process inputs, opened one at a time: `docs/evidence/harness/neff_requote_2026-09-04/restored_sources/s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv`, 314,075 bytes; and `data/cache/inplay_odds/nba_checkpoints_full.parquet`, 2,829,826 bytes, one row group, 465,249 ticks, 1,593 games.

Before screening, the restored S58 archive reproduced its documented one-sided `max_loser_wp` premise: model 81 / 711 (0.113924, 11.3924 pct) and market 40 / 711 (0.056259, 5.6259 pct). The exact denominator is the 711 `y == 0` eventual-loser game ticks; S43 counts `p > 0.8` on that side only. No model was fit or refit. The limit count is 1,345 games with an incumbent probability strictly outside [0.2, 0.8], exceeding 30.

## ATTEMPT 2: frozen rail and selection correction

`CONFIDENT_CUT` remains exactly 0.3. The strict predicate is `p > 0.5 + 0.3` or `p < 0.5 - 0.3`, so literal 0.8 and 0.2 stay non-confident with no tolerance adjustment.

Meta-selection uses S233's landed `scripts/platformkit/eval_gate/cpcv_engine.py:_blocked_indices` with its symmetric nonzero one-day calendar embargo. Each outer fold selects only from earlier OOF rows after that purge; the guard asserts no selected row date lies inside an embargoed scored-row date.

| fold | pre-purge selection ticks | embargoed | after purge | scored ticks |
|---|---:|---:|---:|---:|
| F1 | 0 | 0 | 0 | 80,259 |
| F2 | 80,259 | 3,554 | 76,705 | 75,563 |
| F3 | 155,822 | 1,695 | 154,127 | 77,853 |
| F4 | 233,675 | 2,663 | 231,012 | 75,904 |
| F5 | 309,579 | 0 | 309,579 | 77,415 |

All arms score 306,735 ticks from 1,056 game clusters. Inner selections are F2/F3/F4 `hi_0.10_lo_0.25` and F5 `hi_0.10_lo_0.35`.

| member | Attempt 1 improvement / CI | Attempt 2 improvement / CI |
|---|---|---|
| hi_0.05_lo_0.15 | -0.133071 / [-0.136795, -0.129347] | -0.133071 / [-0.136795, -0.129347] |
| hi_0.05_lo_0.25 | -0.131947 / [-0.135470, -0.128424] | -0.131947 / [-0.135470, -0.128424] |
| hi_0.05_lo_0.35 | -0.131878 / [-0.135375, -0.128382] | -0.131878 / [-0.135375, -0.128382] |
| hi_0.10_lo_0.15 | -0.104072 / [-0.107219, -0.100925] | -0.104072 / [-0.107219, -0.100925] |
| hi_0.10_lo_0.25 | -0.102948 / [-0.105885, -0.100011] | -0.102948 / [-0.105885, -0.100011] |
| hi_0.10_lo_0.35 | -0.102879 / [-0.105789, -0.099970] | -0.102879 / [-0.105789, -0.099970] |
| composite | -0.102920 / [-0.105850, -0.099991] | -0.102920 / [-0.105850, -0.099991] |

## Attempt 2 member metrics

Triplets are guard / incumbent / market. Brier and ECE are tick-weighted. Tail share is the fraction of scored game paths with a probability above 0.8 on the eventual losing side.

| member | Brier | improvement / 95 pct CI / n_eff | ECE | tail share |
|---|---:|---:|---:|---:|
| hi_0.05_lo_0.15 | 0.209637 / 0.076566 / 0.075787 | -0.133071 / [-0.136795, -0.129347] / 4651.2 | 0.320616 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |
| hi_0.05_lo_0.25 | 0.208513 / 0.076566 / 0.075787 | -0.131947 / [-0.135470, -0.128424] / 5127.3 | 0.311802 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |
| hi_0.05_lo_0.35 | 0.208444 / 0.076566 / 0.075787 | -0.131878 / [-0.135375, -0.128382] / 5212.9 | 0.310710 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |
| hi_0.10_lo_0.15 | 0.180638 / 0.076566 / 0.075787 | -0.104072 / [-0.107219, -0.100925] / 4537.9 | 0.284092 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |
| hi_0.10_lo_0.25 | 0.179514 / 0.076566 / 0.075787 | -0.102948 / [-0.105885, -0.100011] / 5064.9 | 0.275277 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |
| hi_0.10_lo_0.35 | 0.179445 / 0.076566 / 0.075787 | -0.102879 / [-0.105789, -0.099970] / 5165.9 | 0.274186 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |
| composite | 0.179486 / 0.076566 / 0.075787 | -0.102920 / [-0.105850, -0.099991] / 5094.1 | 0.275006 / 0.005146 / 0.006979 | 0.000000 / 0.238636 / 0.209280 |

All six fixed-member p-values have BH q=0.05 status under direction-blind arithmetic. The composite's selected fixed members have that status, but its own bar/CI/BH decision is false because -0.102920 is below +0.004 and the CI lower endpoint is negative. The verdict is derived from this composite decision, not from all members passing.

## Reproduction and route identity

- Summary: `docs/evidence/harness/S219_nba_tail_guard_screen_2026-09-04_summary.json`.
- Per-game paired series: `docs/evidence/harness/S219_nba_tail_guard_screen_2026-09-04_per_game_paired_losses.csv`. Its 7,392 rows are seven arms by 1,056 game clusters. Every row stores three loss sums, `tail_guard`, `tail_incumbent`, `tail_market`, and corresponding `max_loser_probability_*` fields. The harness independently reconstitutes tail means and asserts them equal to the summary values.
- Route SHA-256: S219 harness `ECDF3E48644503A8E3D637DC60A469E4B33158597BA45018E5367A86B73DBB52`.

## NOT VERIFIED

- One NBA capture window only; this null is not a multi-corpus calibration result.
- No production caller exists and no feature flag changed.
- The S58 remeasurement validates the tail premise only; it does not alter S58's existing calibration conclusion.

## Tests

`python -m pytest scripts/platformkit/ingame/test_s219_nba_tail_guard.py -q -p no:cacheprovider`: 1 passed in 4.46s.

`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider`: 1 passed in 2.26s.
