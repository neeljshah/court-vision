GAP S247 | sport nba (in-game) | worktree a13 | log cx_s247_nba_sim_engine_vs_line_v2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S216 stopped twice: attempt 1 on store visibility, attempt 2 (S216_..._2026-09-04.md) FALSIFIED because the
  program-memo premise (465,249 ticks / 1,593 games) does not match the archive actually on disk. This re-issue
  quotes ONLY the archive-measured numbers and removes the stop rule so the lane proceeds regardless.
PREMISE (step 0, INFORMATIONAL, NO STOP RULE): re-measure and print, then proceed to Step 1 regardless of result:
  s92_nba_lineup_dynamic_2026-09-03_all.csv = 79,554 ticks / 661 games / 2024-10-25..2026-04-06; market Brier
  0.142876712852 < recal_null 0.144293050901 < ladder_base 0.146849530547 (order CONFIRMED, S216 attempt 2); the
  _rated.csv companion = 33,713 ticks / 284 games, market 0.144100776926 / recal_null 0.146842905353 / ladder_base
  0.153323943143. Do NOT quote 465,249/1,593 as the corpus; that program-memo figure is falsified. No FALSIFIED stop
  applies to this step -- log the numbers and continue.
LIMIT (step 1): the sim needs data/cache/team_system/{player_rates,team_rates}. Count how many of the 661 all-archive
  games have a rates snapshot dated STRICTLY BEFORE the game date. If fewer than 30 game clusters qualify, report
  CLOSED AT LIMIT and score nothing.
CHANGE (step 2): smallest additive change -- one new module under scripts/platformkit/ingame/ that IMPORTS
  src.sim.fast_sim READ-ONLY (import only; zero bytes changed under src/) and prices a rest-of-game home-win
  probability on a frozen, evenly spaced tick grid per qualifying game from the _all archive, scored against three
  arms: market, recal_null incumbent, simulator. Rails: additive only, nothing renamed; helper <= 300 lines
  (test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/
  intel/ scripts/team_system/; one store at a time, never > 300 MB; register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE for the three arms (market, recal_null incumbent, simulator) on the
                  frozen grid, over qualifying games only; denominator = the printed scored-tick count
  before        = archive-measured only: market 0.142876712852, recal_null 0.144293050901 on 79,554 ticks / 661
                  games (2024-10-25..2026-04-06); no simulator number exists on any tick surface today
  bar           = the frozen +0.004 in-game bar applied to the simulator's improvement over the recal_null
                  incumbent, game-clustered 95 pct CI, on >= 30 game clusters; market's own Brier/ECE reported
                  beside it. SCREEN NULL or BEHIND is the expected valid result
  n             = qualifying game clusters (>= 30), capped at 661; printed tick count on the frozen grid
  eye check     = n/a (S-row); reproduction = the verifier recomputes Brier, ECE and the CI from the archived
                  per-game paired-loss series alone (Q9)
  must not move = every file under src/ byte-identical (assert it and print the check); recal_null incumbent
                  defaults; the two S92 archive CSVs byte-identical; backtest_fwer.jsonl untouched, K unread;
                  nothing charged, no prereg sealed
NON-TAUTOLOGY: report the sim on every qualifying tick of the frozen grid, including its worst periods, and name the
  games excluded for want of an as-of rates snapshot with their count.
EVIDENCE: docs/evidence/harness/S247_nba_sim_engine_vs_line_v2_2026-09-04.md -- three-arm table, tail table if any,
  excluded-game count, a NOT VERIFIED list, summary JSON and the per-game paired-loss series (Q9).
TEST: scripts/platformkit/ingame/test_s247_nba_sim_engine_v2.py -- one new per-file test; run only that file.
REPORT: three-arm table, improvement, CI, LIMIT verdict, test line, SHA. Commit by pathspec, no push. NEVER PARK.
