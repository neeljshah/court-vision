GAP S388 | sport all captured | worktree harness-h48 (master-based) | log cx_s388_scheduler_from_schedule
# Focus admission comes from the prospective schedule (design: ASTRA_ROUND14 row 4; measured in the S375 smoke)

SINGLE PROBLEM: the landed scheduler (row S375) admits focus games by "live first, then earliest expected expiration". In the
2026-09-22 01:00Z smoke that rule filled the two available focus slots with two late MLB games and gave the live, qualifying-
relevant NFL game NO snapshot at all. At the anonymous rate the focus set is about two games, so which two must be the games the
prospective schedule (row S386) names -- otherwise no scheduled game can ever meet the frozen 5 s book-age bar.

BINDING BEFORE-CONDITION: read scripts/platformkit/ingame/capture_scheduler.py on master (plan_tick, the focus admission order,
the drop and re-admission rules) and quote them; `grep -n "schedule" scripts/platformkit/ingame/capture_scheduler.py` returns
nothing. Read the schedule JSON shape from scripts/platformkit/execution/forward_replay.py (--schedule: game_id, ticker, sport,
family, scheduled_start, selected_at) and, if landed by then, scripts/platformkit/execution/forward_schedule_writer.py.

CHANGE (owned files: capture_scheduler.py, local_capture_runner.py, NEW scripts/platformkit/ingame/forward_capture_profile.json,
tests/platformkit/ingame/test_capture_scheduler.py, memo; edit no other capture module):
1. `--schedule <json>` on the runner (optional; absent = today's behaviour, so the switch is additive): the scheduler receives the
   list at startup and re-reads it at most once per 60 s (a changed file is logged with its SHA-256; a malformed file is refused and
   the previous list kept, counted). ADMISSION PRIORITY: (a) scheduled games whose window [scheduled_start, scheduled_start + 3600 s)
   is open or opens within 120 s, in scheduled_start order, both sides of the game; (b) then the existing live-then-expiration
   order for spare capacity. A scheduled game is never dropped by the capacity rule; the three-slow-ticks drop still applies and is
   recorded with the reason and the game id; a scheduled game that cannot be admitted for lack of capacity is counted as
   `scheduled_not_admitted` per tick (a strict int the daily report will read). Deterministic: same inputs, same plan.
2. forward_capture_profile.json: the declared profile the forward series runs under -- focus tick 5 s, reservation TTL 5 s, focus
   share 45 percent, maximum scheduled games per hour 2, the anonymous rate ceiling 3 requests per second -- read by the runner
   and echoed (with its SHA-256) into the heartbeat so a qualification report can prove which profile was live.
3. Heartbeat adds: scheduled_games_total, scheduled_admitted, scheduled_not_admitted, profile_sha256 (strict ints / string).
4. Tests: a scheduled game preempts a live unscheduled game with an earlier expiration; both sides admitted together; window opening
   within 120 s admitted; a scheduled game outside its window is not admitted; malformed schedule keeps the previous list and
   counts; re-read at most once per 60 s (injected clock); scheduled_not_admitted counted when capacity is one game and two are
   scheduled; determinism under shuffled input; every landed capture test file still passes unchanged; --no-scheduler and a missing
   --schedule keep today's plan byte-for-byte.
5. Memo docs/evidence/harness/S388_scheduler_from_schedule_2026-09-22.md incl. the side-by-side smoke command for the orchestrator.

CONTROLS: construct tests only, no network, never touch a running capture or its output root. ACCEPTANCE: per-file tests pass one
at a time; --help works; <= 300 LOC per file; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-22; binding; after the first verifier round). (a) A NEW helper module scripts/platformkit/ingame/
capture_schedule_loader.py (<= 300 LOC) is an owned file: it holds the schedule loading / re-read / hash logic so that the edit to
local_capture_runner.py is confined to the schedule / profile integration and every unrelated runner line stays byte-for-byte
(the verifier will diff). (b) Sticky MEMBERSHIP and per-tick SERVICE are separate: when capacity falls, admitted games stay members
and the heartbeat reports, per tick, scheduled_admitted = games that received their focus requests this tick and
scheduled_not_admitted = scheduled member games that did not, so the two never sum above the schedule. (c) A scheduled game whose
selected side is not discovered, or whose winner series is incomplete, is excluded from BOTH scheduled and fallback admission and
counted scheduled_market_unavailable; a game is never captured one-sided.

