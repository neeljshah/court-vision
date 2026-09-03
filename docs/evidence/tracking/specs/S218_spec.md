GAP S218 | sport nba (in-game; wnba enumerated too) | worktree aXX | log cx_s218_nba_live_field_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: the API census (docs/research/ingame_api_census_2026-09-04.md) ranks "NBA/WNBA live current-lineup delta"
  first and "NBA/WNBA foul-trouble and timeout-remaining as a first-class polled field" fourth among uncaptured
  fields, and both sit in payloads we already fetch: the CDN boxscore carries team.inBonus, players[].oncourt and
  timeoutsRemaining, and playbyplay carries game.actions[] including substitutions.
PREMISE (step 0): re-measure and print by reading the parsers, not by fetching: the exact field set
  ingame_live_state.live_state returns; the exact field set boxscore_read.parse_cdn_payload emits; and whether any
  archived CDN or ESPN payload exists on disk to test against (name the paths and counts). If a payload archive exists
  nowhere, say so -- that itself is the finding. If any headline is falsified, STOP, FALSIFIED.
LIMIT (step 1): a field that appears in NO archived payload cannot be classified from disk. For each candidate field
  report NO PAYLOAD ON DISK rather than fetching it live; this row makes no network call. If every candidate lands in
  that class, report CLOSED AT LIMIT and name the capture row that would fix it.
CHANGE (step 2): smallest additive change -- one new read-only census module under scripts/platformkit/ingame/ that
  enumerates the candidate fields against the enumerated parsers and emits one table. Census only: no new extraction,
  no feature, no Brier, no charge. Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail
  test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/
  intel/ scripts/team_system/; one store at a time via metadata or one row group, never > 300 MB (the box RAM guard
  kills python over 800 MB); register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = for each candidate field x each enumerated parser, exactly one of KEPT / PRESENT_BUT_DROPPED /
                  ABSENT_FROM_PAYLOAD / NO_PAYLOAD_ON_DISK, with the source line number for every KEPT and
                  PRESENT_BUT_DROPPED cell; denominator = the full field x parser grid, printed
  before        = 0 -- no census of extracted-versus-available fields exists for nba or wnba; the only statement on
                  record is the API census's ranked gaps 1 and 4, which are assertions, not counts
  bar           = 8 of 8 candidate fields (on-court five, substitution event, personal fouls per player, team fouls,
                  inBonus, timeouts remaining, period/clock, running score) classified for both the NBA CDN and the
                  ESPN parser with 0 cells unclassified and a line number on every KEPT cell; a grid that is entirely
                  NO_PAYLOAD_ON_DISK is the expected valid result and closes the row at limit
  n             = 8 fields x the enumerated parsers (CONSTRUCT -- every cell of the grid is enumerated, none sampled)
  eye check     = n/a (S-row); reproduction = the verifier re-reads each cited line number and confirms the class of
                  every cell from the source alone
  must not move = ingame_live_state.py, boxscore_read.py and every parser byte-identical -- this row reads them and
                  changes nothing; no new endpoint constant; backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: enumerate every candidate field including the ones already KEPT (period/clock, running score). A census
  reporting only the missing fields cannot be checked for completeness and would overstate the gap.
EVIDENCE: docs/evidence/harness/S218_nba_live_field_census_2026-09-04.md -- the full field x parser grid with line
  numbers, the payload-archive inventory, a NOT VERIFIED list and the summary JSON (Q9).
TEST: scripts/platformkit/ingame/test_s218_nba_live_field_census.py -- one new per-file test; run only that file.
REPORT: the grid, the count per class, the LIMIT verdict, test line, SHA. Commit by pathspec, no push. NEVER PARK.
