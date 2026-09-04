# S277 NBA in-game market staleness, attempt 2

## Verdict: NULL

Preregistration: `docs/evidence/harness/S277_ingame_market_staleness_prereg_2026-09-04_attempt2.md`
Preregistration SHA-256: `5cb04bba07a94ca0372bc2d5e8d2af65bd759d093c1c446e9eed76da1b90d7df`

## Premise

The re-run schema is `game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue`; `state_age_s` and `event_key` are NOT FOUND.
Across the full 465,249-tick archive, 1,593 first ticks are named exclusions. The in-scope age distribution has p50 600.000000000 s and p90 7739.000000000 s; fresh has 232157 ticks/1593 games and stale has 46285 ticks/1138 games before incumbent availability.

## Brier comparison

| population | market Brier (95 pct game-clustered CI) | recal_null Brier (95 pct game-clustered CI) | improvement (95 pct game-clustered CI) | ticks / games |
|---|---:|---:|---:|---:|
| fresh | 0.144400687 [0.137456796, 0.151526101] | 0.145658245 [0.138651193, 0.152889897] | -0.001257558 [-0.002563684, -0.000086578] | 230331 / 1582 |
| stale | 0.000091732 [0.000000363, 0.000254743] | 0.000101394 [0.000000704, 0.000281501] | -0.000009662 [-0.000026535, 0.000000788] | 46106 / 1132 |
| pooled | 0.072786008 [0.069055661, 0.076719279] | 0.073422184 [0.069695586, 0.077344106] | -0.000636176 [-0.001282024, -0.000047153] | 460365 / 1582 |

Stale-minus-fresh interaction: 0.001247896 [0.000074233, 0.002549025].
The frozen stale bar is +0.004. This result is NULL.

## Method and reconstruction

The unmodified `apply_incumbent(..., "recal_null")` route produced 461947 evaluator records per arm. 1582 surviving first ticks are excluded before the 460365-row score because they have no prior market price; 3302 seed ticks have no out-of-fold recal_null and remain named, not silently filled.
PASS: 461947 per-tick states; market/recal split-y-key records identical. Each record is one stable `game_id + tick timestamp` state; `cpcv_evaluate` ran once per arm with shared purge and symmetric one-day embargo, and both archived losses were derived only from its returned records.
Every full-grid tick has exactly one staleness assignment: 1593 first-tick exclusions, 232157 fresh, 185214 middle, and 46285 stale. Pooled includes fresh, middle, and stale without a loss-based drop.
The paired CSV stores each scored tick's game cluster, timestamp, both evaluator probabilities, and both evaluator-derived losses so the Brier values can be recomputed without the source archive.
Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; tabular, resolution not applicable). RSS before/after: 218603520 / 1146163200 bytes. Route SHA-256: `7f5666e3514265c03bfc25c47a6abcff140043b8102fba1bd4867e24367cf281`.
Focused test: `python -m pytest scripts/platformkit/ingame/test_s277_ingame_market_staleness.py -q -p no:cacheprovider`.

## NOT VERIFIED

- RSS is machine- and run-dependent; the recorded values are diagnostic, not a reproducibility claim.
- No external deployment was performed or verified.

## Contract self-check

- B1: all full-grid ticks have a named bin or first-tick exclusion; seed rows are separately counted. B2-B6: additive files only, with no changed readers, deployment, or removed module. B7-B9: exhaustive game-clustered records, not a sampled head slice. B10: the +0.004 bar is unchanged.
- Q1: the preregistration and staged-byte seal are named above. Q2: no charge and no ledger or K read. Q3: the frozen bar is unchanged. Q4: two identity-matched per-tick CPCV evaluator runs supply purge, symmetric embargo, and every archived loss. Q5: no AHEAD claim. Q6: calibration language only. Q7: S-row reproduction replaces eye sampling. Q8: the archive premise was re-measured before scoring. Q9: the paired differential archive is committed beside the summary.
