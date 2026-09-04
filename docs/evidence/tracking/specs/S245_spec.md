GAP S245 | sport nba (in-game) | worktree aXX | log cx_s245_ingame_live_boxscore_update
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: no store on disk carries a 5-man on-floor stamp keyed to period+clock, so lineup-grain live
box score is BLOCKED. possession_states_{2024_25,2025_26} (30,383 / 30,199 rows, seconds_remaining,
pace, run_diff) and garbage_time_segments (1,226,606 rows, is_garbage_time per tick) give game-grain
state. This row is scoped to game-state-conditioned REMAINING-game distributions, not lineup ones.
PREMISE (step 0): confirm possession_states_* and garbage_time_segments row counts/columns live;
confirm no lineup store joins to them at clock grain (grep every parquet under data/intelligence/
and data/cache/ for on_floor|lineup_id together with a clock/period column; report the search and
its result).
LIMIT (step 1): if a partial-game observed box score is not available as-of any mid-game tick for a
sample of games, report CLOSED AT LIMIT naming the gap; never synthesize partials from season avgs.
CHANGE (step 2): additive only -- new module scripts/platformkit/ingame_boxscore_update.py: given a
game state (elapsed time, margin, garbage-time flag, current partial box score), reprice each active
player's REMAINING-game pts/reb/ast quantile distribution (minutes-remaining x rate, S241/S242's
models scaled by time-remaining fraction) vs the naive unconditional-remaining baseline.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or
ledger; no edits under src/ kernel/ api/ intel/ scripts/team_system/ or token-gated eval_gate
modules; new helpers <= 300 lines.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = CRPS of the remaining-game distribution, state-conditioned vs naive, at >= 3
      evenly spaced checkpoints per game (end Q1, half, end Q3)
  before        = 0 remaining-game box-score distributions exist at any mid-game checkpoint; only
      pregame (S241/S242) and final (S243) exist
  bar           = the state-conditioned CRPS reported beside naive's at every checkpoint with a
      game-clustered CI; garbage-time games reported as their own partition, never merged silently
  n             = >= 30 game clusters per checkpoint
  eye check     = n/a (S-row); reproduction = the verifier reruns fresh-process at the same
      checkpoints and diffs the CRPS table
  must not move = possession_states_* and garbage_time_segments (read-only); every threshold
NON-TAUTOLOGY: checkpoints are fixed before scoring, not chosen post-hoc; a checkpoint where the
state-conditioned arm loses to naive is reported, not dropped.
EVIDENCE: docs/evidence/harness/S245_ingame_live_boxscore_update_2026-09-04.md plus the per-
checkpoint CRPS table split by garbage-time partition. ASCII only, calibration language only; a
NULL result is a success.
TEST: one new per-file test (a synthetic mid-game state with a known garbage-time flag routes to the
correct partition; CRPS on a fixture matches closed-form), run only that file.
REPORT: the lineup-join search result, per-checkpoint CRPS table by partition, test line, SHA.
Commit by pathspec, no push. NEVER PARK.
