GAP S282 | sport nba (in-game) | worktree a14 | log cx_s282_foul_bonus_regime
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: Maymin, Maymin, Shen, "How Much Trouble is Early Foul Trouble?" J. Quant. Anal. Sports 7(4) 2012, plus
  simulation_methods_2026-09-04.md item A1, name foul/bonus state as a live regime never scored here. S226
  (clutch cell, CLOSED AT LIMIT) found data/cache/inplay_foul_state.parquet (5,010 rows: game_id, period,
  home/away_team_pfs_cum, home/away_max_player_pfs, home/away_starter_fouled_out_indicator, pf_imbalance)
  joined 0/62,465 ticks against nba_checkpoints_full.parquet -- foul_state's game_id is NBA-Stats format
  (0022200001), checkpoints' game_id is ESPN numeric (401704627): a namespace mismatch, not absent data.
PREMISE (step 0, INFORMATIONAL): reprint the three verified column lists (checkpoints; foul_state;
  data/domains/basketball_nba/espn_nba_game_bridge.parquet: event_id ESPN-numeric, game_id NBA-Stats-format).
  Chain checkpoints.game_id == bridge.event_id == bridge.game_id == foul_state.game_id; print first 3 ids on
  every side and the resulting game-cluster count (measured this session: 29 -- one below the rail).
CHANGE (step 1): if the chained join clears 30 clusters, derive a bonus-eligible flag and pf_imbalance as
  additive per-(game_id via bridge, period) features; score
  scripts/platformkit/foundry/ingame_incumbent_nba.apply_incumbent's recal_null plus the foul covariates via
  scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate, purge + symmetric nonzero embargo. If it does not
  clear 30, STOP at PREMISE and report CLOSED AT LIMIT naming the acquisition (an ESPN-keyed foul-state
  capture, or a fuller game_id crosswalk) that would unblock it -- no fit attempted below the rail.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = recal_null-plus-foul-covariates minus recal_null Brier improvement, game-clustered 95 pct
                  CI, computed only if the join clears 30 clusters
  before        = no arm has ever scored inplay_foul_state.parquet; S226 recorded 0/62,465 joined ticks
  bar           = the frozen +0.004 bar; CLOSED AT LIMIT below 30 clusters is the expected valid result
  n             = >= 30 game clusters required to score; the chain is measured at ~29 clusters
  eye check     = n/a (S-row); reproduction = verifier reruns the four-way chain and diffs the count
  must not move = nba_checkpoints_full.parquet, inplay_foul_state.parquet, espn_nba_game_bridge.parquet, the
                  +0.004 bar; nothing charged if CLOSED AT LIMIT
NON-TAUTOLOGY: the chain (checkpoints -> bridge event_id -> bridge game_id -> foul_state) is fixed before any
  count is read; widening the join key to inflate the cluster count is circular and self-rejected. Every
  checkpoint game is classified JOINED or NAMED-EXCLUDED, 0 silently dropped.
EVIDENCE: docs/evidence/harness/S282_foul_bonus_regime_2026-09-04.md + join census CSV + (if scored) summary
  JSON and paired-loss CSV.
TEST: one per-file test reproducing the four-way join count on a small fixture (3 games chained end-to-end,
  1 deliberately broken at each link); if scored, also reproduce one bin's Brier from the archived CSV.
REPORT: join census table, cluster count, verdict, RSS, test line, SHA. No push. NEVER PARK.
