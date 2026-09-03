GAP S215 | sport tennis (in-game) | worktree aXX | log cx_s215_tennis_inplay_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: tennis is recorded as having no in-play close (MODEL_QUALITY_PROGRAM section 2, "NO in-play close on disk"),
  yet tennis_price_series.parquet holds 1,854,100 rows (metadata 2026-09-04) and two artifacts disagree on its event
  count: S81:52 says 1,864, S80:79 says 986.
PREMISE (step 0): re-measure and print via ParquetFile(path).metadata and a single row group only: the store's row
  count, its distinct event count, and which of 1,864 / 986 that reproduces (or neither); the 1,255 / 1,237 / 18
  grade-store figures; and that no tennis state table carries a tick-joinable timestamp. If any headline is falsified,
  STOP, write the memo, commit, report FALSIFIED -- a valid result.
LIMIT (step 1): count IN_PLAY ticks that can receive ANY as-of state (set or game score) from tennis_states__{atp,wta}
  / tennis_gamestate__* / tennis_setdetail__* at or before the tick. The expected honest answer is 0, in which case
  the row is CLOSED AT LIMIT on the state side and delivers only the price-side denominator.
CHANGE (step 2): smallest additive change -- one new read-only census module under scripts/platformkit/ingame/,
  reusing the S214 classification shape (do not fork it if S214 has landed; import it). Census only: no Brier, no arm,
  no prereg, no charge. Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail test_loc_rail_scope.py);
  never write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/;
  one store at a time via metadata or one row group, never > 300 MB (the box RAM guard kills python over 800 MB);
  register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = every row classified into exactly one of PRE_MATCH / IN_PLAY_JOINED / IN_PLAY_NO_STATE / POST_MATCH
                  / UNRESOLVED_KEY with 0 unclassified and 0 interpolated states; plus denominator = every row of the
                  store
  before        = 0 rows classified; the two published event counts (1,864 and 986) disagree and neither is a measured
                  in-play count
  bar           = all 1,854,100 rows classified with 0 unclassified, the event-count disagreement resolved with the
                  measured number and its reason, and the recoverable-state count printed; a recoverable count of 0 is
                  the expected valid result and closes the state side at limit
  n             = every row of the store (CONSTRUCT -- exhaustive classification, no sampling); print the row and
                  resolved-event counts
  eye check     = n/a (S-row); reproduction = the verifier recomputes the five class counts and the resolved event
                  count from the archived per-event summary alone
  must not move = tennis_states__* and ingame_grade/tennis byte-identical; the INGAME_SIGNAL_PROGRAM rank-8 verdict is
                  not edited, only supplemented; backtest_fwer.jsonl untouched, K unread; nothing charged
NON-TAUTOLOGY: report all five classes including UNRESOLVED_KEY, and report the price-side denominator even when the
  state side is 0; reporting only joinable rows would make the sport look scorable.
EVIDENCE: docs/evidence/harness/S215_tennis_inplay_census_2026-09-04.md -- the class table, the event-count
  adjudication, the state-join attempt table, a NOT VERIFIED list, summary JSON and per-event summary CSV (Q9).
TEST: scripts/platformkit/ingame/test_s215_tennis_inplay_census.py -- one new per-file test; run only that file.
REPORT: the class counts, the adjudicated event count, the recoverable-state count, the LIMIT verdict, test line, SHA.
  Commit by pathspec, no push. NEVER PARK.
