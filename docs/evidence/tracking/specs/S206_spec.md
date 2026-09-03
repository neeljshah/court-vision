GAP S206 | sport wnba (in-game) | worktree aXX | log cx_s206_wnba_ingame_first_score
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: wnba_ingame_census_2026-09-04.md, verbatim: "WNBA in-play ticks with an action-derived as-of state | 0 |
18,650" and "The before value is the established S80/S82 closed evidence: no settled WNBA ticks in a state-joined
store". It is the only sport with a settled, priced, state-joined in-game corpus never scored; 85 game clusters vs
MLB's 41-88. Candidate arm = item 5 (Stern 1994) of docs/research/model_quality_methods_2026-09-04.md, one free sigma.
PREMISE (step 0): re-measure and print: 18,650 joined ticks over 85 intersect games; in-play denominator 186,736;
in-span 19,456 (10.42 pct); state age median 15 s, p90 132 s, 0 above 300 s; 84 of 85 games at or above 100 in-span
ticks; settlement resolves 98 of 98 priced events. If falsified, STOP, memo, commit, FALSIFIED.
LIMIT (step 1): after the tier's train floor and a game-first-date purge, count SCORED ticks and clusters. Under 30
clusters, report CLOSED AT LIMIT with the count and the market-vs-model table only -- never lower the floor or widen
the window.
CHANGE (step 2): smallest additive change -- run the EXISTING machinery (foundry/ingame_screen.py: BAR,
assert_tick_asof, walk_forward_feature) on the WNBA joined ticks as ingame_screen_soccer.py did for its third sport.
Two arms on identical rows and folds: null = [1, logit(market)], candidate = null + the single Stern term. Additive
only, nothing renamed; helper <= 300 lines within test_loc_rail_scope.py; never write data/; no flag on; no edits in
src/ kernel/ api/ intel/ scripts/team_system/; one store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = Brier improvement of candidate over null with a game-clustered DM 95 pct CI and n_eff, plus ECE and
                  the 10-bin reliability table for market, null and candidate; denominator = the printed scored-tick
                  count over the printed game clusters
  before        = 0 -- no WNBA in-game tick has ever been scored (census line quoted above); no WNBA Brier, ECE or
                  reliability number exists in docs/evidence
  bar           = the frozen +0.004 bar applied AS WRITTEN to improvement over the null, on >= 30 clusters, the
                  market's own Brier and ECE beside both arms, and the as-of guard passing at 8 EVENLY spaced probes.
                  A SCREEN NULL and a model BEHIND the market are expected valid results
  n             = the scored tick count over >= 30 game clusters; print both, and the unscored remainder of the
                  186,736
  eye check     = n/a (S-row); reproduction = the verifier recomputes Brier, ECE and the DM CI for all three series
                  from the archived per-tick paired-loss CSV alone
  must not move = foundry/ingame_screen.py BAR and every eval_gate threshold; the three census artifacts
                  byte-identical; backtest_fwer.jsonl untouched, K unread; no prereg sealed, no charge
NON-TAUTOLOGY: all 186,736 in-play ticks stay in the reported denominator; the 167,280 unjoined and every tick the
floor or purge removes are counted and named. A Brier on fresh-state ticks only, with the excluded set unnamed, is
circular -- REJECT.
EVIDENCE: docs/evidence/harness/S206_wnba_ingame_first_score_2026-09-04.md -- three-series table, both reliability
tables, fold table, exclusion accounting, NOT VERIFIED list, summary JSON and the per-tick paired-loss CSV (Q9).
TEST: scripts/platformkit/foundry/test_s206_wnba_ingame.py -- one new per-file test; run only that file.
REPORT: scored ticks and clusters, the three Briers, the improvement and CI, test line, SHA. Commit by pathspec, no
push. NEVER PARK.
