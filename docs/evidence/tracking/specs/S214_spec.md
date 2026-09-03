GAP S214 | sport soccer (in-game) | worktree aXX | log cx_s214_soccer_inplay_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S117 closed soccer in-game AT LIMIT on corpus size -- 9,003 ticks / 51 games, usable 29 games / 3,658 ticks,
  and only 163 ticks over 2 game clusters actually scored.
PREMISE (step 0): re-measure and print via ParquetFile(path).metadata only: both stores' row counts and their distinct
  event counts; that neither file is read by any module (print the grep with its file list); and the S117 scored
  figures 9,003 / 51 / 29 / 3,658 / 163 / 2. If any headline is falsified, STOP, write the memo, commit, report
  FALSIFIED -- a valid result.
LIMIT (step 1): count how many IN_PLAY ticks can receive an as-of state from the existing soccer state tables
  (soccer_states__*, soccer_shotstates__*, soccer_cardstates__*) on their own join key, with the state strictly at or
  before the tick. If the recoverable count spans <= 29 usable game clusters -- S117's own figure -- the census has
  bought nothing and the verdict is CLOSED AT LIMIT.
CHANGE (step 2): smallest additive change -- one new read-only census module under scripts/platformkit/ingame/ that
  classifies rows and emits a table plus the classified per-event summary. Census only: no Brier, no arm, no prereg,
  no charge. Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail test_loc_rail_scope.py); never write
  data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one store at
  a time via metadata or one row group, never > 300 MB (the box RAM guard kills python over 800 MB); register and
  ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = every row of both stores classified into exactly one of PRE_MATCH / IN_PLAY_JOINED /
                  IN_PLAY_NO_STATE / POST_MATCH / UNRESOLVED_KEY, with 0 unclassified and 0 interpolated states, plus
                  state age p50 / p90 / share above 300 s for the JOINED class; denominator = every row
  before        = 0 -- neither store has ever been read; the only soccer in-game denominator on record is S117's 163
                  scored ticks over 2 game clusters
  bar           = all rows of both stores classified with 0 unclassified, and a recoverable count (IN_PLAY_JOINED)
                  printed with its game-cluster count; a recoverable count of 0, or one spanning <= 29 clusters, is
                  the expected valid result and closes the row at limit
  n             = every row of both stores (CONSTRUCT -- exhaustive classification, no sampling); print the row and
                  event counts each store actually contributed
  eye check     = n/a (S-row); reproduction = the verifier recomputes the five class counts and the state-age
                  quantiles from the archived per-event summary alone
  must not move = the S117 artifact and its verdict; ingame_grade/soccer_intl stores byte-identical; ingame_screen BAR
                  0.004; backtest_fwer.jsonl untouched, K unread; nothing charged
NON-TAUTOLOGY: report all five classes with their counts, including UNRESOLVED_KEY.
EVIDENCE: docs/evidence/harness/S214_soccer_inplay_census_2026-09-04.md -- the class table per store, the state-age
  table, the join-key resolution table, a NOT VERIFIED list, summary JSON and the per-event summary CSV (Q9).
TEST: scripts/platformkit/ingame/test_s214_soccer_inplay_census.py -- one new per-file test; run only that file.
REPORT: the class counts, the recoverable count and its clusters, the LIMIT verdict, test line, SHA. Commit by
  pathspec, no push. NEVER PARK.
