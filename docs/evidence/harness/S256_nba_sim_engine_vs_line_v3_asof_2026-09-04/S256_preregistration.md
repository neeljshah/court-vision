# S256 preregistration

Spec: docs/evidence/tracking/specs/S256_spec.md
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9

## Fixed inputs

- Archive: data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv.
- Player snapshot: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet.
- Team snapshot: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet.
- Qualification: docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv.
- The qualified set is every row with qualifies=True after validating that both named snapshot dates are strictly before its game date. No qualified game or selected tick will be removed after pricing.

## Frozen construction

- Select one archive row nearest each elapsed-second target 120, 600, 1080, 1560, 2040, and 2520 per qualified game; ties resolve by smaller ts, then stable archive order. This six-point grid is evenly spaced by 480 seconds and includes every selected grid point.
- For each selected row, use only that game's S255 snapshot dates. Player values join on entity_id and player_snapshot_date; team values are the same-date league mean because the archive contains no team identifier. The module must not open a team-system rate store.
- Fast-simulator fields not supplied by S255 are named in the output. They receive the same-date S255 player free-throw-rate league-mean-derived neutral fill; a player with no row receives that same fill. No other rate source is permitted.
- Construct both teams directly from the archive five-player IDs. The archive has no score state, so the simulator prices the remaining possession sequence from a tied score; this limitation is reported and no market probability enters the simulator arm.
- Set remaining pace from the same-date team-tempo league mean and elapsed fraction. Use 128 fast_sim draws, seed = integer game id modulo 2147483647 plus elapsed-second target, anchor=False, defense=False, dispersion=False, and default-disabled environment flags.

## Fixed evaluation

- Route every selected tick through scripts/platformkit/eval_gate/walkforward.py walk_forward with strict redaction. State features are only the strictly-prior snapshot dates, lineup IDs, elapsed seconds, and snapshot-derived values. The evaluator applies its 48-hour purge and 3-day nonzero embargo.
- Report tick-weighted Brier and 10-bin ECE for market, recal_null, and simulator, over every emitted grid tick. The primary differential is recal_null loss minus simulator loss; the game-clustered 95 percent CI uses scripts/platformkit/eval_gate/dm_test.py.
- The unmodified bar is +0.004 simulator improvement over recal_null, at least 30 game clusters. No AHEAD claim is possible from this single-window measurement; SCREEN_NULL or BEHIND remains a valid result.
- Archive the per-game paired losses, game id, and timestamp, along with the full selected-tick series and summary JSON. Report a period tail table without selecting favorable periods.

## Integrity checks

- Record SHA-256 before and after for the three S255 artifacts and S92 archive; record and assert byte identity for every tracked src/ file.
- Do not write data/, data/registry/, the register, the ledger, or backtest_fwer.jsonl. Do not read legacy team-system stores.

Seal-SHA256: 60e3e1d11af2880f7db2dbf4676470af16af6ecc08c402b4608a358928b51721
