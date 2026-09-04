GAP S269 | sport wnba | worktree a15 | log cx_s269_wnba_oncourt_five_lineup_state
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S253 (DONE 4dd9e24eb) and S84 (SCREEN_NULL, NBA). S253's module is named "nba_..." but its
  ONLY source is data/domains/wnba/cdn_backfill (168 WNBA games, 2026-04-25..2026-07-04, per the register row
  itself) -- verified: no NBA CDN archive exists on disk. This row is WNBA, correcting a false "nba" premise per
  contract clause S2. All 85 priced games in wnba_ingame_census (S206, DONE) fall inside S253's 167 qualifying
  games (verified this session: comm -12 of the two id sets returns 85/85). S84's NBA lineup screen was
  SCREEN_NULL (-0.000455, CI [-0.003920,+0.003009], 284 clusters); S206's WNBA Stern-state screen was also
  SCREEN_NULL (brier_candidate 0.154859 vs brier_null 0.155244, CI [-0.000210,+0.000980]) -- a third null here
  would be an expected, valid pattern, not a surprise.
PREMISE (step 0, INFORMATIONAL): print S253's stamps.csv row/game count (expect 5,647 / 167) and S206's scored
  tick/cluster count (expect 16,571 / 75, from wnba_checkpoints_full.parquet + wnba_price_series.parquet); print
  the exact set overlap between stamps.csv game_id and S206's cdn_game_id (expect 85 of 85).
CHANGE (step 1): additive; join S253's per-tick five-man stamps to S206's scored WNBA ticks by (game_id, backward
  as-of: latest stamp at or before the tick's elapsed time). Derive lineup_state = (home starters currently on
  court) minus (away starters currently on court), an integer in [-5,5], purely from S253's stamps -- no new
  rating store. Candidate = S206's null `[1, logit(home_oriented_market)]` plus lineup_state; both arms score
  through scripts/platformkit/foundry/ingame_screen.py's existing walk_forward_feature machinery, S206's
  game-first-date folds, purge, and its existing 1-day settlement embargo (all unchanged). Never write
  data/registry/, never flip a flag; S253's and S206's own artifacts untouched (new dated filenames only).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE, S206 null arm vs lineup_state candidate, on the joined ticks
  before        = S206: brier_null 0.155244 / brier_candidate(Stern) 0.154859, 16,571 ticks / 75 clusters; no
                  lineup term has ever been scored on a WNBA in-game tick
  bar           = the frozen +0.004 bar; SCREEN_NULL is a valid success; every lineup_state cell (-5..+5)
                  reported with its own n, even if empty (ABSENT_BECAUSE)
  n             = the joined ticks (>= 30 game clusters expected from the 85/85 overlap), denominators printed
  eye check     = n/a (S-row); reproduction = verifier reruns the join and scorer and diffs every cell and the
                  pooled delta with CI
  must not move = S253's stamps.csv/summary.json, S206's summary.json and defaults, wnba_checkpoints_full.parquet,
                  wnba_price_series.parquet, the +0.004 bar; backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: report every lineup_state cell including the sparsest; state plainly this is SINGLE-WINDOW (one
  WNBA season, one feature) and that a null result would be a third failed lineup/state addition in a row (S84
  NBA, S206 WNBA Stern term), not proof lineup never matters anywhere.
EVIDENCE: docs/evidence/harness/S269_wnba_oncourt_five_lineup_state_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test recomputing one game's paired loss and its lineup_state values from the archived CSV,
  under 200 MB; run only that file.
REPORT: join overlap, per-cell table, pooled delta + CI, RSS, test line, SHA. No push. NEVER PARK.
