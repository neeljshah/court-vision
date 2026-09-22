GAP S408 | sport all captured | worktree harness-h77 (master-based) | log opus_s408_competition_shape_counters
# Competition-shape counters (a missing, duplicated or emptied competition is counted, never silently dropped)

SINGLE PROBLEM: the pollers in scripts/platformkit/ingame/local_state_capture_sources.py read each event's competitions array
without checking its shape, and the sports disagree about what a bad shape means. An event with no competitions makes
_parse_event return None (scripts/platformkit/frontend/live_board.py:244-246), so the NBA and soccer paths report
event_parse_empty / nba_adapter_empty and `continue` (local_state_capture_sources.py:119-121, 128-130) and the event leaves no
row at all; the NFL and NCAAF path instead takes `(ev.get("competitions") or [{}])[0]` (domains/nfl/ingest_nfl_states.py:176)
and still emits a row, with an empty state and the inferred 'pre' fallback of local_state_capture_sources.py:217. A second
competition on one event is never seen: _status reads index zero (local_state_capture_sources.py:45) and _parse_event reads
comps[0] (live_board.py:247), so a duplicate can archive the other competition's state and start with nothing counted. A
tennis walkover or retirement with no competitors makes the adapter's competitor loop (domains/tennis/ingest_espn.py:148)
return no rows, so local_state_capture_sources.py:172-174 reports tennis_adapter_empty and the match disappears entirely.

BINDING BEFORE-CONDITION: read on MASTER and quote in the memo -- local_state_capture_sources.py lines 44-49 (_status index
zero), 116-140 (the ESPN event loop, the NBA branch and the two empty paths), 167-186 (the tennis grouping / competition
isolation and its empty path), 209-222 (the NFL / NCAAF row build and its status fallback); live_board.py lines 242-247;
domains/nfl/ingest_nfl_states.py:176; domains/tennis/ingest_espn.py:148. Row S393 in worktree nba-harness-h52 also edits
local_state_capture_sources.py, so quote MASTER and rebase this worktree on master AFTER S393 lands, before the verifier
round. Run tests/platformkit/ingame/test_state_capture_sources.py and tests/platformkit/ingame/test_local_state_capture.py one
file at a time, quote the pass counts, and record today's emitted row count for each fixture below.

CHANGE (owned files: scripts/platformkit/ingame/local_state_capture_sources.py, scripts/platformkit/ingame/
local_state_capture_dates.py (its report helper at line 18, only if a new reason name must be registered) and the new
tests/platformkit/ingame/test_state_capture_shapes.py ONLY; domains/nfl/ingest_nfl_states.py and
domains/tennis/ingest_espn.py are read-only, and scripts/platformkit/frontend/live_board.py is OUT OF SCOPE for this row and
is never edited -- the selection below is done in the owned module before _parse_event is called):
1. MISSING COMPETITIONS COUNTED: every poller counts competition_missing once per event whose competitions array is absent or
   empty, and each poller's emitted row count for that event is fixed and asserted: NBA and soccer emit no row (the present
   behaviour, now counted); NFL and NCAAF emit one row whose state is null and whose status is taken from the event's own
   status type name, or null when there is none -- the 'pre' fallback at local_state_capture_sources.py:217 never invents a
   status for a shapeless event. Nothing about the missing competition is inferred.
2. DUPLICATE COMPETITIONS SELECTED BY ID: an event carrying more than one competition counts competition_duplicate once and
   the poller selects the competition whose id equals the event's own id, falling back to the first only when no id matches
   (counted competition_id_unmatched). Selection happens in the owned module by isolating the chosen competition into a
   single-competition copy of the event -- the same isolation the tennis path already performs at
   local_state_capture_sources.py:170 -- so _status (line 45) and _parse_event (live_board.py:247) each see exactly one
   competition and neither module is edited. Both input orders of the two competitions select the same competition.
3. TENNIS WALKOVER AND RETIRED EMITTED: when the tennis adapter returns no rows for an isolated competition
   (local_state_capture_sources.py:172-174) because the competitor loop at domains/tennis/ingest_espn.py:148 saw no
   competitors, the poller emits the row from the competition itself -- game_key `<league>:<competition id>`, status mapped
   through _TENNIS_STATUS (line 179) from the competition's own status type name, state with an empty players list, no winner
   and no name inferred -- and counts competition_walkover or competition_retired by that status name. Any other cause of an
   empty adapter result keeps today's tennis_adapter_empty count and today's row count.
4. Tests (the new file only): one fixture per poller (nba, soccer, nfl, ncaaf, tennis) for the missing-competitions shape and
   one for the duplicate shape, plus a tennis walkover fixture and a tennis retired fixture; each asserts the exact emitted
   row count, the exact counter deltas and the emitted status, in BOTH event orders and BOTH competition orders with identical
   rows; every counter delta equals the count of emitted rows carrying that verdict, or the count of events refused when no
   row is emitted. tests/platformkit/ingame/test_state_capture_sources.py and test_local_state_capture.py stay byte-identical
   to master -- `git diff master --stat` on them is empty, the identity test per S393 AMENDMENT 4(ii) -- and pass unchanged.
5. Memo docs/evidence/harness/S408_competition_shape_counters_2026-09-22.md with the quoted master lines, today's per-fixture
   row counts and the counts after the change.

CONTROLS: PREPARE only; construct tests with injected scoreboard payloads; no network; never read or write the live captures
under data/cache/ingame_books_local/**, their lock, or any STOP file there (a STOP_STATE construct under pytest's tmp_path is
not a capture STOP file, per S393 AMENDMENT 4(i)); no feature flag is flipped.
ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a
NOT VERIFIED list.
