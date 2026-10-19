# S784 diagnosis: books missed_deadlines climb after the S767 relaunch (2026-10-06)

PAPER ONLY. Read-only diagnosis of the live books capture (supervisor pid 4004, child
local_capture_runner pid 28580, child_start 10:49:31Z per supervisor_books.jsonl line 33).
No row allocated (the S784 id in this file name is NOT allocated; NEXT_GAP_ID stays S784), no code change: verdict EXPECTED.

## Verdict: EXPECTED (deadline-window bookkeeping; focus coverage improved)

## 1. Counter semantics are unchanged; the window is not
- The only increment is the `_Deadline` carry at local_capture_runner.py:221 (old code: same
  line 221), raised by `guarded` at :189/:191 when the limiter's next send or a late wake
  reaches `deadline`. Line :182 adds `unscheduled_focus_requests` (0 in the live heartbeat).
- OLD (f2fb0a853:172, :268): deadline = tick entry + 5 s, then `sleep(max(0.5, ...))`, so every
  tick got a full 5 s with an idle limiter and ticks stretched instead (focus gap p50 5.19 s).
- NEW (capture_repoll.py:87-93, runner :176): deadline = max(grid + 5, started + 2.5) on a
  fixed grid with no catch-up sleep. Any overrun of tick N (post-request commit/heartbeat time)
  shortens tick N+1's window by the same amount, so its tail requests are carried and counted.
  With a 15-request plan at 3.0 req/s (budget = rate x 5, capture_scheduler.py:146) there is
  no slack, so most overruns cost a few carried tail requests.

## 2. Focus set: no finished game is held
- Shard tail since 10:49 (mlb/tennis/soccer, <= 16 MiB each): focus_books rows are
  MILSD-MIL/SD (pregame, from 10:49:36Z) and four WTA tickers CHAZHE/JOVSWI (from 10:54:47Z):
  6 unscheduled tickers = capacity 15 x 45 // 100 (capture_scheduler.py:178).
- Scheduled rows enter priority only for start - 120 <= now < start + 3600
  (capture_scheduler.py:122); NYY at TB (00:00Z) and ATL at NO (00:15Z) are past that, and
  priority games evict unscheduled ones (:124-130). LAD at ATL gets priority from 21:58Z.
- Before the restart the old process held yesterday's CWSCLE / NYKPHI / PHXDET in the
  unscheduled fill; that is the old in-memory admission, not the schedule.

## 3. Cadence and the S767 arithmetic
- Focus book inter-row gaps after 10:50Z: p50 5.00 s, p90 5.36 s for all 6 tickers
  (old era 10:20-10:49: p50 5.19, p90 5.59). Every tick carried every focus book (per-tick
  count 2 before 10:54:47, then 6 in every tick); no focus book was ever carried.
- Gaps > 6 s are whole-tick lapses hitting all tickers at once: 10.37 s at 11:00:22-32Z and
  7.44 s at 11:01:18-25Z (host stall; HTTP latency max 0.08-0.14 s per minute throughout).
  The 6.22 s focus_cadence_p50 and the 160 -> 200 climb fall inside that 10:57-11:01 window
  of overrunning ticks (4, 1, 2 ticks per minute with spacing > 5.4 s).
- After 11:02Z: missed_deadlines_total 204 (11:02:27Z) -> 214 (11:06:06Z) -> 214 (11:08:25Z),
  focus_cadence p50 4.79-5.22, p90 4.85-5.24; 12 ticks per minute; requests_by_class sums
  12-15 (fractional shares), n_429 0.
- scheduled_game_cost(2) = 2 x 1.5 + 1 = 4 (capture_repoll.py:9-11): 2 books + 1 repoll of the
  single selected ticker (state["schedule_selected"], capture_scheduler.py:135) + 1 alternating
  trade. Three games = 12 of 15 as the S767 memo states; not over budget.

## 4. Tonight (LAD at ATL)
- Required work (2 books, 1 trade) is at the head of the order; the repoll sits at index 7
  (timed_requests) and waits to started + 2.5 s; repoll_work keeps one reserve slot when room
  > 2, so scheduled ticks plan 14 not 15.
- Residual risk (by design, not fixed): after an overrun >= 2.5 s the deadline equals
  started + 2.5 s and the repoll is carried for that tick (selected-ticker gap 5 s, not lost
  book). Observed rate of such overruns: 2 in 18 min this morning.

## NOT verified
- Which classes were carried per tick (carry list is in-memory only; no per-tick journal).
- The cause of the 10:57-11:01 stalls (host load is the hypothesis, not measured).
- Behavior with the scheduled game live; first live read is 22:00Z.
