GAP S252 | sport tennis (in-game) | worktree aXX | log cx_s252_tennis_point_feed_decision
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S215 CLOSED AT LIMIT: 0 recoverable tennis point-level state rows keyless. ingame_api_census_2026-09-04.md
  names paid/unofficial feeds with no cost/cadence/terms comparison anywhere on disk. DECISION row: no code.
PREMISE (step 0): re-measure and print: S215 price series tennis_price_series.parquet 1,854,100 rows / 986 distinct
  event_key, class counts PRE_MATCH 1,851,294 / IN_PLAY_JOINED 0 / IN_PLAY_NO_STATE 2,806 / POST_MATCH 0 /
  UNRESOLVED_KEY 0; the three state families (tennis_states, tennis_gamestate, tennis_setdetail) x {atp,wta} all
  carry 0 tick-joinable timestamp columns, recoverable rows = 0; ingame_api_census names Sportradar Tennis (Live
  Summaries, Live Timelines, Live Timelines Delta, Live Probabilities -- coverage TIER-DEPENDENT per match),
  Enetpulse and Data Sports Group (subscription, pricing unsourced), livetennisapi.com and tennis-api.com
  (unofficial REST+WebSocket, pricing unsourced). If falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): count how many of the 4 named feed candidates have a SOURCED (cited, not repo-memory-only) price
  or terms figure found this pass. Report the count; a count of 0 SOURCED is a valid, expected result and every
  cost cell in the brief is then labelled UNSOURCED, not blank -- this does not stop the row.
CHANGE (step 2): smallest additive change -- one new file docs/research/organization-sprint/
  S252_tennis_point_level_feed_decision_2026-09-04.md enumerating each of the 4 feed candidates against 5 fixed
  columns (cost, cadence, terms/ToS, minimum viable capture, sourced-or-unsourced flag), ending in a one-page
  recommendation naming either one feed to pursue or explicit "no feed recommended" with reasoning. Zero code
  under src/ kernel/ api/ intel/ scripts/team_system/; no capture script is built; register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = feed rows enumerated x 5 fixed columns filled, out of the exhaustive 4-candidate set named in
                  S215 and ingame_api_census_2026-09-04.md
  before        = no cost/cadence/terms comparison table for tennis point-level feeds exists anywhere on disk;
                  S215 measured 0 recoverable state rows keyless
  bar           = all 4 named candidates appear as rows; all 5 columns filled per row (UNSOURCED is a valid fill,
                  a blank cell is not); the brief ends with exactly one recommendation line
  n             = 4 (CONSTRUCT, exhaustive over the named candidates)
  eye check     = n/a (S-row); reproduction = the verifier re-opens the brief and counts rows and filled columns
  must not move = S215 summary JSON/CSV byte-identical; ingame_api_census_2026-09-04.md byte-identical (read-only
                  sources, not edited by this row)
NON-TAUTOLOGY: every named candidate appears even if its cell is UNSOURCED; dropping an unfavorable candidate to
  make the recommendation look cleaner is circular -- report REJECT yourself.
EVIDENCE: docs/evidence/harness/S252_tennis_point_feed_decision_2026-09-04.md -- the same brief content plus a
  reproduction note and a NOT VERIFIED list.
TEST: tests/platformkit/test_s252_tennis_feed_brief.py -- asserts the brief file exists and its table parses to
  exactly 4 rows with all 5 columns filled; one new per-file test, run only it.
REPORT: the 4x5 table, the recommendation, test line, SHA. Commit by pathspec, no push. NEVER PARK.
