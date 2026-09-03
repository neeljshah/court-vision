GAP S199 | sport wnba | worktree a14 | log cx_s199_wnba_state_ceiling
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/wnba_ingame_census_2026-09-04.md:82 (with its _summary.json and _per_game.csv),
verbatim: "- No state can be recovered for the 167,280 ticks outside cached play-by-play wallclock spans."
PREMISE (step 0): re-measure and print, from the census memo + summary JSON: intersect_games 85;
intersect_inplay_ticks 186,736; joined_ticks 18,650; inside_pbp_span_ticks 19,456 (10.42 pct);
outside_pbp_span_ticks 167,280; pbp 168 games / 84,143 actions, all 84,143 carrying timeActual, score, clock
and period, wallclock 2026-04-25T19:03:10Z..2026-07-04T04:31:59Z; per-game in-span median 250, p90 274; state
age median 15 s, p90 132 s, 0 of 18,650 above 300 s; checkpoint states 504 rows = 3 per game on 168 games.
If any headline is falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): before changing anything, classify all 186,736 in-play ticks against their own game's pbp span
into PRE_FIRST_ACTION / JOINED / INTERIOR_GAP (in span, more than 300 s from any action) / POST_LAST_ACTION and
print the four counts plus the per-game table. A POST_LAST_ACTION state is KNOWN only where that game's final
score and period resolve from the linescore bridge; count those separately. If the recoverable count (JOINED
plus POST_LAST_ACTION with a known final) does not exceed 18,650, report CLOSED AT LIMIT. Do not fix.
CHANGE (step 2): the smallest additive change -- one new module under scripts/platformkit/ingame/ that adds a
tick_state_class column and a boundary-clamped (NEVER interpolated) state for POST_LAST_ACTION ticks, written
to a NEW parquet carrying the full wnba_checkpoints_full column set. wnba_wallclock_join.py, asof_join.py and
the existing 18,650 joined rows stay byte-identical; any new helper module is <= 300 lines and stays inside
tests/platformkit/test_loc_rail_scope.py counts. Read one store at a time; never write under data/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = in-play WNBA moneyline ticks carrying a labelled state class, and separately the recoverable
                  subset (JOINED plus POST_LAST_ACTION with a known final), over the FIXED denominator
                  186,736 ticks on the 85 intersect games
  before        = 18,650 of 186,736 (9.99 pct) joined; 0 of 186,736 classified
  bar           = 186,736 of 186,736 classified into exactly one class, 0 unclassified and 0 interpolated
                  states; recoverable count strictly greater than 18,650; per-class and per-game counts
                  recomputable from the new parquet alone
  n             = 85 (games/clusters, >= 30)
  eye check     = n/a (S-row); reproduction = the verifier reloads the new parquet, recounts the four classes
                  against 186,736, and re-derives the per-game spans from the pbp JSON
  must not move = asof_join.py max_staleness_s 300.0; wnba_wallclock_join.py and wnba_checkpoints_full.parquet
                  byte-identical; data/cache/eval_gate/backtest_fwer.jsonl untouched with K unread
NON-TAUTOLOGY: the denominator stays 186,736, no tick is dropped, and POST_LAST_ACTION is reported SEPARATELY
and never folded into the state-joined headline. Raising the share by relabelling ticks whose state is unknown
is circular -- report REJECT yourself. CENSUS only: no Brier, no prereg, no charge, no register/ledger edit.
EVIDENCE: docs/evidence/harness/S199_wnba_state_ceiling_2026-09-04.md -- before/after table, the four class
counts, the 85-row per-game table, a NOT VERIFIED list, and a summary JSON copied under docs/evidence/.
TEST: scripts/platformkit/ingame/test_s199_wnba_state_classes.py -- one new per-file test; run only that file.
REPORT: class counts, recoverable count, diff stat, test line, SHA. Commit by pathspec, no push. NEVER PARK.
