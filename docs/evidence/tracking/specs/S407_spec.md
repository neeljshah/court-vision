GAP S407 | sport all captured | worktree harness-h76 (master-based) | log opus_s407_terminal_row_midnight
# Terminal row survives midnight (a boundary tick never loses a game's last row)

SINGLE PROBLEM: scripts/platformkit/ingame/local_state_capture.py clears last_state, last_polled, mlb_games, sport_status and
known_games at every UTC day rollover (lines 96-101) and rebuilds state['recovered'] (line 108), but reseeds last_state only
under `if not state.get('initialized')` (line 109), so every rollover after the first begins with an empty last_state. A game
that was live before the boundary and is discovered FINAL after it then fails `if key in last_state or str(game['game_key'])
in mlb_games` (line 136) and is pruned at line 140, and its terminal row never reaches the archive. Separately, the row's
logical date comes from officialDate / localDate (local_state_capture_dates.py:102) while the shard it lands in follows the
receipt UTC day (local_capture_writer.py:119), and the venue's local midnight triggers no reset at all (line 96 compares
iso(now)[:10] only), so a reader holding a 03:00Z row cannot join it to the day it belongs to.

BINDING BEFORE-CONDITION: read on MASTER and quote in the memo -- local_state_capture.py lines 93-112 (the rollover reset and
the initialized-guarded reseed), lines 133-142 (the discovery prune of a final game), lines 186-195 (the recovered / written
bookkeeping and finals.append); local_state_capture_dates.py lines 99-111 (officialDate / localDate resolution);
local_capture_writer.py lines 118-119 (the shard path formatted from the receipt end time). Row S393 in worktree
nba-harness-h52 also edits local_state_capture.py, so quote MASTER and rebase this worktree on master AFTER S393 lands,
before the verifier round. Run tests/platformkit/ingame/test_local_state_capture.py,
tests/platformkit/ingame/test_state_capture_recovery.py and tests/platformkit/ingame/test_local_state_capture_differential.py
one file at a time and quote the pass counts; build the two-tick boundary construct and quote today's counts on master.

CHANGE (owned files: scripts/platformkit/ingame/local_state_capture.py, scripts/platformkit/ingame/local_state_capture_dates.py
and the new tests/platformkit/ingame/test_state_capture_midnight.py and test_state_capture_boundary_dates.py ONLY;
local_capture_writer.py, local_state_capture_io.py and local_state_capture_sources.py are read-only, and
scripts/platformkit/frontend/live_board.py is OUT OF SCOPE for this row and is never edited):
1. ROLLOVER RESEEDS: the rebuild at local_state_capture.py:108 reseeds last_state from the freshly recovered map on EVERY
   rollover using the same non-final filter as lines 110-111, not only when 'initialized' is unset; each rollover that reseeds
   counts rollover_reseeded once (one count per rollover, never per key).
2. TERMINAL ROW BEFORE PRUNE: a game whose key is in last_state OR in state['recovered'] and is discovered FINAL emits its
   final row first and is pruned (line 140, _prune_game at line 48) only after that row is in the tick's rows list; each such
   row counts terminal_row_emitted. A game discovered FINAL that is in NEITHER map was never tracked and is still pruned,
   counting terminal_row_pruned; the boundary tests assert terminal_row_pruned is 0.
3. BOTH DAYS ON THE ROW: master's row already carries the logical date (local_state_capture.py:42, date=item.get('date')) but
   not the day its shard will use. The row gains ONE additive key, shard_day -- the UTC day of response_end_utc, the same value
   local_capture_writer.py:119 formats -- so a 03:00Z row can be joined to its logical date without reparsing. Every other key
   and type is unchanged (a test compares a synthetic row's key set against master's plus shard_day). A row whose two days
   differ counts date_split_rows. A feed with no date at the boundary keeps date null with the existing date_reason
   (local_state_capture_dates.py:100) and still carries shard_day; no date is inferred from the receipt.
4. Tests (new files only): a live-to-final pair of boundary ticks across UTC midnight asserting the terminal row, the counters
   and terminal_row_pruned 0; the same pair across a venue local midnight that is not a UTC midnight; a feed-missing-date
   boundary tick; every case driven in BOTH scoreboard item orders with identical emitted rows; a second rollover asserting
   rollover_reseeded once and last_state repopulated from the recovered map; exactly ONE writer.recover_states call per
   rollover and none inside a tick (S401 AMENDMENT 2(c) stands). tests/platformkit/ingame/test_local_state_capture.py and
   test_local_state_capture_differential.py stay byte-identical to master -- `git diff master --stat` on them is empty, which
   is the identity test, not a raw byte count (S393 AMENDMENT 4(ii)) -- and pass unchanged.
5. Memo docs/evidence/harness/S407_terminal_row_midnight_2026-09-22.md with the quoted master lines and the measured counts.

CONTROLS: PREPARE only; construct tests with injected payloads and a fake clock; no network; never read or write the live
captures under data/cache/ingame_books_local/**, their lock, or any STOP file there (a STOP_STATE construct under pytest's
tmp_path is not a capture STOP file, per S393 AMENDMENT 4(i)); no feature flag is flipped.
ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a
NOT VERIFIED list.

AMENDMENT 1 (2026-09-22 23:0xZ; binding; scope extension from the S393 astra round-10 critique): recovery after a restart
restores the last STATE but not the remembered SCHEDULE (local_state_capture_io.py:161 keeps status / state only), so an archived
feed start B becomes a discovery start A after a restart. This row's scope now includes rebuilding the remembered (start, source)
pair from the shard's last row per game on recovery -- without a network call -- so the S393 remembered-schedule rules hold across
restarts and rollovers; test: two appends, restart after the first, the second refresh emits B with superseded unchanged.
