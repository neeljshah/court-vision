GAP S256 | sport nba (in-game) | worktree a13 | log cx_s256_nba_sim_engine_vs_line_v3_asof
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S247 CLOSED AT LIMIT (fc0084261): 0/661 archive game clusters had a rates snapshot dated strictly before the
  game. S255 (b559352ed) then built walk-forward as-of snapshots: docs/evidence/harness/S255_asof_rate_snapshot_producer_
  2026-09-04/{player_rate_snapshots.parquet, team_rate_snapshots.parquet, cluster_qualification.csv}; 355/661 clusters
  (53.7065 pct) qualify with player_snapshot_date < game_date AND team_snapshot_date < game_date. This row scores the
  simulator on those 355 clusters. It is the third-arm measurement S216/S247 could not make.
PREMISE (step 0, INFORMATIONAL, NO STOP RULE): re-measure and print: cluster_qualification.csv qualifying count (expect
  355 of 661); archive = 79,554 ticks / 661 games; market 0.142876712852 < recal_null 0.144293050901. Proceed regardless.
LIMIT (step 1): if fewer than 30 qualifying clusters can be joined to BOTH snapshot parquets by (game_id, snapshot
  dates from cluster_qualification.csv), report CLOSED AT LIMIT and score nothing. Print the joined count.
CHANGE (step 2): smallest additive change -- one new module under scripts/platformkit/ingame/ that IMPORTS
  src.sim.fast_sim READ-ONLY (import only; zero bytes changed under src/), builds its per-game rate inputs ONLY from the
  S255 as-of snapshot rows for that game (never from data/cache/team_system/{player_rates,team_rates}), and prices a
  rest-of-game home-win probability on a frozen, evenly spaced tick grid per qualifying game from the _all archive,
  scored against three arms: market, recal_null incumbent, simulator. If fast_sim needs a rate field the snapshots
  lack, print the field name and fill it from the snapshot's league mean for that snapshot date only (name every
  fill). Rails: additive only, nothing renamed; helper <= 300 lines (test_loc_rail_scope.py); never write data/
  (never data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one store at a
  time, never > 300 MB; register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE for the three arms (market, recal_null incumbent, simulator) on the
                  frozen grid, over qualifying joined games only; denominator = the printed scored-tick count
  before        = archive-measured only: market 0.142876712852, recal_null 0.144293050901 on 79,554 ticks / 661
                  games; no simulator number exists on any tick surface today (S216, S247)
  bar           = the frozen +0.004 in-game bar applied to the simulator's improvement over the recal_null
                  incumbent, game-clustered 95 pct CI, on >= 30 game clusters; market's own Brier/ECE reported
                  beside it. SCREEN NULL or BEHIND is the expected valid result and is a SUCCESS
  n             = qualifying joined game clusters (>= 30, <= 355); printed tick count on the frozen grid
  eye check     = n/a (S-row); reproduction = the verifier recomputes Brier, ECE and the CI from the archived
                  per-game paired-loss series alone (Q9) and re-derives the joined count from cluster_qualification.csv
  must not move = every file under src/ byte-identical (assert it and print the check); the three S255 artifacts
                  byte-identical (print sha256 before/after); the S92 archive CSV byte-identical; backtest_fwer.jsonl
                  untouched, K unread; nothing charged, no prereg sealed; the legacy team_system stores unread
NON-TAUTOLOGY: report the sim on every qualifying tick of the frozen grid, including its worst periods; list the 306
  excluded clusters by count and reason (no strictly-prior snapshot); print every league-mean fill by field.
EVIDENCE: docs/evidence/harness/S256_nba_sim_engine_vs_line_v3_asof_2026-09-04.md -- three-arm table, tail table,
  excluded-cluster count, fills, a NOT VERIFIED list, summary JSON and the per-game paired-loss series (Q9).
TEST: scripts/platformkit/ingame/test_s256_nba_sim_engine_v3.py -- one new per-file test; run only that file.
REPORT: three-arm table, improvement, CI, LIMIT verdict, test line, SHA. Commit by pathspec, no push. NEVER PARK.
