# S256 attempt 1c sample-scale preregistration

Spec: docs/evidence/tracking/specs/S256_spec.md
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9
Machine: local worktree C:/Users/neelj/nba-track-a18; this bounded local sample avoids any pod transfer before ACCEPT (B5).

## Fixed inputs

- Archive: data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv (38,630,145 bytes).
- Player snapshot: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet (565,095 bytes).
- Team snapshot: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet (22,677 bytes).
- Qualification: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv (36,282 bytes).
- The full premise is 355 qualifying clusters of 661 and 79,554 archive ticks. Qualification is re-derived by requiring both named snapshot dates strictly before game_date.

## Frozen sample

- Seed: 2561001. Sort the 355 qualifying game identifiers lexicographically, call NumPy default_rng(2561001).choice(..., size=30, replace=False), then sort the chosen identifiers lexicographically. The chosen whole-game clusters are: 401809798, 401810022, 401810042, 401810056, 401810130, 401810156, 401810179, 401810183, 401810233, 401810249, 401810253, 401810255, 401810386, 401810388, 401810398, 401810410, 401810533, 401810539, 401810541, 401810549, 401810570, 401810628, 401810663, 401810771, 401810811, 401810831, 401810930, 401810966, 401810972, 401836800.
- This is 30 whole game clusters and 180 ticks: nearest archive row at six frozen evenly-spaced elapsed targets 120, 600, 1080, 1560, 2040, and 2520 seconds per selected game. Ties use smaller ts then stable archive order. No selected tick is removed after simulator pricing.
- The 30-game scale is fixed to hold the sequential, single-store local simulation below 600 MB process RSS; peak RSS is printed and asserted below that cap.

## Frozen scoring

- Every selected state is priced by the callback through scripts/platformkit/eval_gate/cpcv_engine.py cpcv_evaluate with n_groups=8, n_test_groups=1, strict redaction, imported 48-hour same-team and matchup purge, and a symmetric three-calendar-day embargo. Each state key must occur exactly once in the callback output.
- Report tick-weighted Brier and 10-bin ECE for market, recal_null, and simulator. Compare recal_null loss minus simulator loss with the shared game-clustered 95 percent CI. The unchanged bar is +0.004, with 30 clusters. SCREEN NULL or BEHIND is valid. No full-corpus claim is made.
- Inputs to the simulator are the selected row's ten lineup IDs, elapsed time, and only S255 snapshot values dated strictly before the game. The archive does not contain a score state, so the simulator prices a tied score rest-of-game sequence; market and recal_null are never passed to the simulator callback.
- Missing fast-simulator rate fields are filled only by the player ft_rate_q50 league mean for the selected row's player snapshot date, with each field and date-value count recorded. Team tempo uses team_tempo_z's league mean for the named team snapshot date. A missing player receives that same player-date mean.

## Required artifacts and integrity

- Write only NEW _sample result names: S256_selected_tick_series_sample.csv, S256_per_game_paired_loss_series_sample.csv, S256_summary_sample.json, S256_run_stdout_sample.txt, S256_run_stderr_sample.txt, and the S256 evidence memo.
- The Q9 series holds game, cluster_id, timestamp, n_ticks, recal_null loss, simulator loss, and their paired difference. The focused test recomputes one selected game's paired loss from the full selected-tick series and asserts denominator 180 under 200 MB.
- Print SHA-256 before and after for the S255 inputs and S92 archive, assert tracked src/ bytes unchanged, list all snapshot league-mean fills, and do not read legacy team-system stores. No register, ledger, data path, or backtest_fwer.jsonl is touched.
- Any current-worktree artifact derived on a pod is superseded and is not evidence for attempt 1c. The successor is a separate full 355-cluster pod row after this local trial lands; no module bytes will reach a pod before ACCEPT.

Seal-SHA256: 66abcb1f75d2be05479e2a9d991c9d76e56829a13b9b0b99198a0584732a6bfe
