GAP S219 | sport nba (in-game) | worktree aXX | log cx_s219_nba_tail_guard_screen
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: both in-game model sides fail in the same place -- premature confidence on the eventual loser.
PREMISE (step 0): re-measure and print from the archived series, no refit: the S58 trial B tail shares 11.4 pct model
  / 5.6 pct market; the S123 ordering market < recal_null < ladder_base on both S92 corpora; the S86 corpus 465,249
  ticks / 1,593 games; and that foundry/ingame_incumbent_nba.py exists and is default byte-identical (S123). If any
  headline is falsified, STOP, write the memo, commit, report FALSIFIED -- a valid result.
LIMIT (step 1): the guard can only act where the model is confident. Count the game clusters carrying at least one
  tick with abs(p - 0.5) > 0.3 under the S123 incumbent. If fewer than 30 clusters qualify, the guard is unmeasurable
  here and the verdict is CLOSED AT LIMIT. Print that count before any arm table.
CHANGE (step 2): smallest additive change -- screen a FROZEN family of 6 (d_hi in {0.05, 0.10} x d_lo in {0.15, 0.25,
  0.35}) with the confident-side cut FROZEN at 0.3 and never tuned, each member chosen inside the folds of the
  existing outer expanding game-first-date walk-forward, differing from the incumbent ONLY by the clamp. SCREEN side,
  uncharged: no prereg sealed, K never read, _charge_ledger never called. Rails: additive only, nothing renamed;
  helper <= 300 lines (LOC rail test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no
  edits under src/ kernel/ api/ intel/ scripts/team_system/; one store at a time via metadata or one row group, never
  > 300 MB (the box RAM guard kills python over 800 MB); register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per family member and for the inner-selected composite: tick-weighted Brier of the guarded arm, the
                  S123 incumbent and the raw line; the game-clustered improvement over the incumbent with a 95 pct CI
                  and n_eff; ECE for all three; and the loser-tail share above 0.8 for all three; denominator = the
                  printed scored-tick count over the printed clusters
  before        = no tail guard has ever been screened on NBA; the standing anchors are S58 trial B -0.006583
                  [-0.011503, -0.001664] BEHIND the market with tail shares 11.4 pct model vs 5.6 pct market
  bar           = the frozen +0.004 bar applied as written to the composite's improvement over the S123 incumbent,
                  with a game-clustered CI excluding zero AND BH at q 0.05 across the enumerated 6-member family;
                  every member reported including the worst. SCREEN NULL is the expected valid result
  n             = qualifying game clusters (>= 30) and the printed tick count; report clusters per member
  eye check     = n/a (S-row); reproduction = the verifier recomputes the composite improvement, its CI and the three
                  tail shares from the archived per-game paired-loss series alone
  must not move = the frozen confident-side cut 0.3 and the 6-member grid; ingame_screen.BAR 0.004;
                  foundry/ingame_incumbent_nba.py defaults; the S86 corpus CSV; the S58 and S123 artifacts;
                  backtest_fwer.jsonl untouched, K unread; nothing charged
NON-TAUTOLOGY: report all 6 members plus the composite, and report the improvement over ALL scored ticks, not only the
  confident-side ticks the guard touches. Scoring only the clamped ticks would make a clamp beat itself.
EVIDENCE: docs/evidence/harness/S219_nba_tail_guard_screen_2026-09-04.md -- the member table, the BH table, the tail-
  share table, the qualifying-cluster count, a NOT VERIFIED list, summary JSON and the per-game series (Q9).
TEST: scripts/platformkit/ingame/test_s219_nba_tail_guard.py -- one new per-file test; run only that file.
REPORT: the composite improvement and CI, the member table, BH survivors, the tail shares, test line, SHA. Commit by
  pathspec, no push. NEVER PARK.
