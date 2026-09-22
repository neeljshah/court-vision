GAP S403 | sport all captured | worktree harness-h64 (master-based) | log opus_s403_schedule_game_key
# The prospective schedule writer emits game_key (found by the S390 build: the bridge cannot link a schedule without it)

SINGLE PROBLEM: scripts/platformkit/execution/forward_schedule_writer.py (row S386) writes six-field entries (game_id, ticker, sport,
family, scheduled_start, selected_at) while scripts/platformkit/execution/forward_capture_bridge.py (row S389, lines 80-85) requires a
nonempty game_key per entry to link a scheduled game to its state rows; every game of a writer-produced schedule would therefore be
LINKAGE_INVALID in the daily qualification. For MLB the state capture's key is str(gamePk) == game_id, so the orchestrator patched the
2026-09-22 files by hand before any start; the next date's schedule must carry the key from the writer.

BINDING BEFORE-CONDITION: quote from master (a) forward_schedule_writer.build_schedule(day, sports, books_root, state_root, family,
now=None, *, schedule_source='live', opener=None) -> tuple[list[dict], dict] and the entry construction (its lines 234-235); (b)
forward_capture_bridge.py lines 55-90 (the game_key requirement and linkage); (c) local_state_capture_sources.py game_key provenance per
sport (MLB str(gamePk); ESPN-backed sports the ESPN event id or away@home; soccer league:comp_id; NBA and others espn_event_id); (d)
capture_scheduler.schedule_rows (which keys it validates) and the S362 replay's schedule loader (whether a seventh key is tolerated);
(e) forward_schedule_sources.py (what identifiers each live source yields).

CHANGE (owned files: forward_schedule_writer.py and forward_schedule_sources.py (MODIFIED, additive), tests/platformkit/execution/
test_forward_schedule_writer.py (MODIFIED), memo; the bridge, the scheduler and the replay are NOT edited -- if either refuses a
seventh key, STOP and report it as a spec conflict):
1. Every entry carries game_key, derived per sport exactly as the state capture derives it (quote the provenance and reuse the same
   rule; never invent a key): MLB gamePk; ESPN-backed sports the ESPN event id; a sport whose key cannot be derived from the live
   source gets NO entry and a counted refusal reason game_key_unavailable (never a placeholder). The census file records the key
   source per entry.
2. Tests: real-shaped fixtures for MLB and one ESPN-backed sport produce game_key equal to the state capture's key for the same
   payload (import the state capture's source function and compare); the scheduler's schedule_rows and the replay's loader accept an
   entry with the seventh key (construct tests calling the landed functions); an entry whose key is unavailable is refused and
   counted; the writer's existing tests pass unchanged.
3. Memo docs/evidence/harness/S403_schedule_game_key_2026-09-22.md.

CONTROLS: construct tests only; no network in the builder's run; the orchestrator re-runs the writer live for the next date.
ACCEPTANCE: per-file tests pass; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 17:0xZ; binding; after the Opus build). (a) OWNED FILES extended: tests/platformkit/execution/
test_forward_schedule_sources.py (its espn() helper returns id 'event-id' with competitions id = key, which is not the real ESPN
shape: the fixture pins the wrong id; fix the fixture to id = key) and tests/platformkit/execution/test_forward_schedule_team_set.py
(asserts the six-field entry; add game_key = the gamePk its own link_paths assertion pins), and the NEW companion test file
tests/platformkit/execution/test_forward_schedule_game_key.py (the writer's own test file is at the 300-line rail). Every test in all
four files passes on master after the landing. (b) FINDING recorded: master's forward_schedule_sources._game used the COMPETITION id
for every non-MLB sport while the state capture keys ESPN-backed sports by the EVENT id (local_state_capture_sources.py:122); the
writer now uses the event id; the away@home fallback of the state capture is deliberately not reproduced (an underivable key is a
counted game_key_unavailable refusal with no entry). (c) The orchestrator's hand patch of the 2026-09-22 files already uses the gamePk
(corrected on master at the second patch); the build's read-only observation referred to the first patch.
