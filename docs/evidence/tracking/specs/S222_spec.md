GAP S222 | sport all (in-game) | worktree a16 | log cx_s222_refresh_layer_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: the in-game engine is conditioned by more than live feeds. Four regularly-refreshed classes feed it through
  as-of joins -- play-by-play archives (pbp_states_*, pbp_foul_states_*, possession_states_*), Statcast pitch grain
  (mlb_pitch_states__2022..2026, whose velocity trend within a start is a pitcher-state signal), workload and fatigue
  (bullpen_relief_chains.parquet, pitch counts, rest), and lineup minutes (team_system/player_rates.parquet).
PREMISE (step 0): re-measure and print via ParquetFile(path).metadata and at most one row group per file -- never a
  whole store, the box RAM guard kills any python over 800 MB: for each enumerated refresh table, its row count, its
  min and max date, and its builder module. Reproduce the bullpen figure (last date 2026-07-02, 8 rows over 2 teams).
  If any headline is falsified, STOP, write the memo, commit, report FALSIFIED -- a valid result.
LIMIT (step 1): for each table, check whether foundry/asof_supply declares an as-of rule for it. A table with no
  declared rule cannot enter a leak-free join and is reported UNDECLARED. If every table is UNDECLARED or STALE, the
  refresh layer cannot condition anything today and the verdict is CLOSED AT LIMIT -- report it and wire nothing.
CHANGE (step 2): smallest additive change -- one new read-only census module under scripts/platformkit/ingame/ that
  enumerates the refresh tables and emits one table. Census only: nothing is wired, no feature is built, no join is
  created, no Brier is computed, no charge. Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail
  test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/
  intel/ scripts/team_system/; one store at a time via metadata or one row group, never > 300 MB (the box RAM guard
  kills python over 800 MB); register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per enumerated refresh table: rows, min and max date, staleness in days against the latest tick date
                  of the sport's in-play corpus, declared-as-of YES/NO with the asof_supply line number, and joined-
                  to-a-tick YES/NO with the joining module named; denominator = the enumerated table list
  before        = 0 -- no refresh-layer census exists; the only datum on record is S119's bullpen finding (last date
                  2026-07-02, 8 rows over 2 teams) and S81:54's note that the pitch tables join to no price
  bar           = every enumerated table reported with all six columns and 0 cells left blank; at least one table
                  classified STALE with its exact end date and staleness in days; 0 tables wired, joined or modified
                  by this row. A census in which every table is UNDECLARED is the expected valid result
  n             = the enumerated refresh-table count (CONSTRUCT -- every table in the four classes is listed and
                  classified, none sampled); print the list before the table
  eye check     = n/a (S-row); reproduction = the verifier recomputes each staleness figure from the archived summary
                  JSON and the cited asof_supply line numbers alone
  must not move = foundry/asof_supply.py and every builder byte-identical; no parquet written or rewritten; the S119
                  and S81 artifacts; ingame_screen.BAR 0.004; backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: enumerate every table in all four classes, including the ones that are fresh and already declared.
EVIDENCE: docs/evidence/harness/S222_refresh_layer_census_2026-09-04.md -- the six-column table, the class list, the
  staleness ranking, a NOT VERIFIED list and the summary JSON (Q9).
TEST: scripts/platformkit/ingame/test_s222_refresh_layer_census.py -- one new per-file test; run only that file.
REPORT: the table, which sources are STALE or UNDECLARED, the LIMIT verdict, test line, SHA. Commit by pathspec, no
  push. NEVER PARK.
