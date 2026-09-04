GAP S253 | sport nba (in-game) | worktree a17 | log cx_s253_nba_oncourt_five_cdn_subs
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S218 attempt 2b (a16, S218_nba_live_field_census_2026-09-04.md) measured on_court_five
  ABSENT_FROM_PAYLOAD 0/2,008 ESPN payloads, PRESENT_BUT_DROPPED 168/168 CDN boxscore payloads (parser drops it);
  substitution_event PRESENT_BUT_DROPPED 168/168 CDN playbyplay siblings + 1,606/1,610 ESPN summaries
  (ingame_live_state.py:469). Only raw CDN archive on disk: data/domains/wnba/cdn_backfill, 168 boxscore.json +
  168 playbyplay.json pairs, 2026-04-25..2026-07-04; no NBA-specific CDN archive exists (unblocks S225/S229/S245).
PREMISE (step 0): re-measure and print: 168 boxscore.json/playbyplay.json game-id pairs under
  data/domains/wnba/cdn_backfill; count how many boxscore.json payloads carry a period-1 five-vs-five starting
  state and how many playbyplay.json payloads carry >=1 substitution action. If falsified, STOP, write memo,
  commit, report FALSIFIED.
LIMIT (step 1): of the 168 pairs, count games where the starting five plus the substitution sequence closes
  without an unresolved gap (no tick with != 5 players either side). If fewer than 30 qualify, CLOSED AT LIMIT.
CHANGE (step 2): one new additive module under scripts/platformkit/ingame/ (e.g. nba_oncourt_five_from_cdn_subs.py)
  plus one per-file test, that seeds the starting five from each boxscore.json and replays playbyplay.json
  substitutions in wallclock order to emit a per-tick (period, clock, five ids per team) stamp. Rails: additive
  only, nothing renamed; helper <= 300 lines (test_loc_rail_scope.py); never write data/ (never data/registry/);
  no flag on; no edits under src/ kernel/ api/ intel/ scripts/team_system/; one store at a time, never > 300 MB;
  register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = coverage of archived game-ticks receiving a complete five-per-team stamp; denominator = every
                  substitution-bounded tick across the qualifying games (printed count)
  before        = 0 (no derivation module exists; S218 established only payload presence, not a derived stamp)
  bar           = >= 95 pct of ticks in qualifying games carry a complete (5,5) stamp with 0 duplicate-on-court
                  violations and 0 substitution in/out imbalance, over >= 30 game clusters
  n             = qualifying game clusters (>= 30), capped at 168; printed tick count on the derived table
  eye check     = n/a (S-row); reproduction = the verifier recomputes the stamp and all three consistency checks
                  from the archived boxscore.json/playbyplay.json pairs alone, plus a >= 30-game spot check of
                  summed per-player on-court ticks against that game's own boxscore.json minutes field
  must not move = the 168+168 archive files byte-identical; boxscore_read.py / ingame_live_state.py unedited
NON-TAUTOLOGY: report coverage over every qualifying game, including any where the sibling playbyplay route was
  unreadable; name excluded games and the exact reason, never drop them from the denominator to inflate coverage.
EVIDENCE: docs/evidence/harness/S253_nba_oncourt_five_from_cdn_subs_2026-09-04.md -- coverage table, consistency
  table, minutes spot-check table, excluded-game count, NOT VERIFIED list, summary JSON, derived table under
  docs/evidence/harness/S253_nba_oncourt_five_from_cdn_subs_2026-09-04/ as csv/parquet if < 2 MB else sha256+rows.
TEST: scripts/platformkit/ingame/test_s253_nba_oncourt_five_from_cdn_subs.py -- one new per-file test; run only it.
REPORT: coverage pct, consistency tallies, minutes spot-check, excluded-game count, LIMIT verdict, test, SHA.
  Commit by pathspec, no push. NEVER PARK.
