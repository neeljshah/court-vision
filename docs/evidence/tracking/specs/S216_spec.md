GAP S216 | sport nba (in-game) | worktree aXX | log cx_s216_nba_sim_engine_vs_line
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: the possession Monte Carlo (src/sim/basketball_sim.simulate_game, and the CUDA-batched
  src/sim/fast_sim.simulate_game_fast) has never priced an in-play tick.
PREMISE (step 0): re-measure and print: no module under scripts/platformkit/ imports src.sim (print the grep with its
  file list); the S86 corpus 465,249 ticks / 1,593 games / 2024-10-22..2026-06-13; foundry/ingame_incumbent_nba.py
  exists and is default byte-identical (S123); and the S123 ordering market < recal_null < ladder_base reproduces from
  the archived series. If falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): the sim is parameterised from data/cache/team_system/{player_rates,team_rates}. Count how many of the
  1,593 games have a rates snapshot dated STRICTLY BEFORE the game date. If fewer than 30 game clusters qualify the
  engine cannot be priced leak-free here: report CLOSED AT LIMIT and score nothing.
CHANGE (step 2): smallest additive change -- one new module under scripts/platformkit/ingame/ that IMPORTS
  src.sim.fast_sim READ-ONLY (import only; zero bytes changed under src/) and prices a rest-of-game home-win
  probability on a frozen, evenly spaced tick grid per qualifying game, scored against the line and against the S123
  incumbent. Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail test_loc_rail_scope.py); never write
  data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one store at
  a time via metadata or one row group, never > 300 MB (the box RAM guard kills python over 800 MB); register and
  ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE for three arms (sim, S123 incumbent, raw line) plus the share of lost
                  games with p > 0.8 on the eventual loser for each arm; game-clustered improvement over the incumbent
                  with a 95 pct CI and n_eff; denominator = the printed scored-tick count
  before        = no sim number exists on any tick surface; the standing anchors are S58 trial B halftime -0.006583
                  [-0.011503, -0.001664] BEHIND the market, the S123 ordering, and S99's BEHIND on MLB
  bar           = the frozen +0.004 in-game bar applied as written to the sim's improvement over the S123 incumbent,
                  with a game-clustered CI, on >= 30 game clusters; the market's own Brier and ECE and all three tail
                  shares reported beside it. SCREEN NULL or BEHIND is the expected valid result
  n             = qualifying game clusters (>= 30) and the printed tick count on the frozen grid
  eye check     = n/a (S-row); reproduction = the verifier recomputes the improvement, its CI and the three tail
                  shares from the archived per-game paired-loss series alone
  must not move = every file under src/ byte-identical (assert it and print the check); ingame_screen.BAR 0.004;
                  foundry/ingame_incumbent_nba.py defaults; the S86 corpus CSV; backtest_fwer.jsonl untouched, K
                  unread; nothing charged, no prereg sealed
NON-TAUTOLOGY: report the sim on every qualifying tick of the frozen grid, including the periods where it is worst,
  and name the games excluded for want of an as-of rates snapshot with their count.
EVIDENCE: docs/evidence/harness/S216_nba_sim_engine_vs_line_2026-09-04.md -- the three-arm table, the tail table, the
  excluded-game count, a NOT VERIFIED list, summary JSON and the per-game paired-loss series (Q9).
TEST: scripts/platformkit/ingame/test_s216_nba_sim_engine.py -- one new per-file test; run only that file.
REPORT: the three-arm table, the improvement and CI, the tail shares, the LIMIT verdict, test line, SHA. Commit by
  pathspec, no push. NEVER PARK.
