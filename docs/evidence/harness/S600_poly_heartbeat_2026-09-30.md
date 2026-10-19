# S600 PART A -- polymarket heartbeat_ts at write time (2026-09-30)

Spec docs/evidence/tracking/specs/S600_spec.md incl. AMENDMENT 1. Candidate = uncommitted changes on worktree HEAD `cb1d3be26559929eeea42ba5eb7e7a3c49057d68`. Built inline by the orchestrator (codex down; RAM freezes). Reliability language only.

## Before-condition (measured 2026-09-30 03:59Z, read-only)
polymarket/mlb/_heartbeat.json heartbeat_ts 03:24:16Z (= schedule_pointer_resolved_at = the tick start, polymarket_live_capture.py:197 iso(now), now read at capture_once entry :258) while last_write_ts in the same file was 03:46:37Z and the shard kept growing to 03:59Z: one tick lasts ~22 min (rows_written_tick 3,851; 1,177 markets; ~1,725 requests / 10 min at 3.0 req/s).

## CHANGE
- NEW polymarket_heartbeat.stamp(client, now) -> {heartbeat_ts (write clock), tick_start_ts, tick_duration_s}; a naive / non-datetime clock falls back to the tick start (counted heartbeat:tick_clock_invalid, never a local-time shift); a clock stepped back keeps the write time with duration 0.0 (counted heartbeat:tick_clock_backwards).
- polymarket_live_capture.py: the heartbeat build uses **hb.stamp(client, now) in place of "heartbeat_ts": iso(now) (+1 import line; 297 lines). Every other key, its value and order are unchanged; the restore path is unchanged (the new keys are output-only).

## Consumer audit
- capture_watchdog.py:155-160 is the only reader of the polymarket heartbeat_ts; it wants writer freshness; write time is never after the reader now, so the future-time branch :157 cannot newly fire.
- paper_desk_issue_capture.py:71-91 / :254-259 read last_write_ts, unaffected. No other polymarket heartbeat_ts reader under scripts/ src/ kernel/ domains/.
- The merged pointer fields (pointer_read_at, schedule_pointer_resolved_at) stay tick-start stamps, so heartbeat_ts is now LATER than them by about one tick; no reader compares them.

## Tests (each file alone)
    tests/platformkit/ingame/test_polymarket_heartbeat_ts.py: 9 passed (cases 1-6, the capture_once end-to-end case, case 1b differential, case 3b restore refusals)
    test_polymarket_live_capture.py 18, _json 19, _link 23, _relink 16, _rows 57, _trades 32, test_capture_watchdog.py 105 passed
    Power: with the heartbeat build reverted to iso(now) the new file gives 2 failed, 5 passed (the end-to-end and restore cases).

## MANDATORY DISCLOSURES
1. The measured before-condition above (03:59Z).
2. Write-time stamping removes the tick-long lag, but the heartbeat is still written ONCE per tick: under the paper desk default max_age_s 300 (paper_desk_tick.py:202) a healthy polymarket capture reads STALE for most of a ~22-min tick (case 5 asserts: write+60 s fresh, write+301 s stale). FOLLOW-UP (not built): a mid-tick progress heartbeat or a per-venue polymarket max-age.
3. PART A2 (recorded, not fixed): the ~22-min tick means each polymarket book is revisited only every ~20 min, a freshness problem for any polymarket in-game use; follow-up = served-first ordering like S598, measured before adoption.
4. last_write_ts / last_success_ts semantics unchanged; the kalshi runner heartbeats are untouched (PART B waits for S598).
5. No restart has happened; adoption = one polymarket restart with docs/operations/relaunch_polymarket_2026-09-29.ps1 in a 06:00Z-16:00Z window with no served game within 60 min.

## Inventory

| path | lines | sha256 (LF) |
|---|---|---|
| scripts/platformkit/ingame/polymarket_heartbeat.py | 25 | bfd19a71e1a6b533998e4ff817dbfef0e8bfe27ed54540ccba9b7aeec1da07eb |
| scripts/platformkit/ingame/polymarket_live_capture.py | 297 | df744b25f3494c550e02e45d8bcce52b250478f429ce3fc11db0a781a048d49e |
| tests/platformkit/ingame/test_polymarket_heartbeat_ts.py | 124 | f3a508a7d989f7653427e3b3f704cc93e1bd8a48e3505db36d6840d72997188e |

## NOT VERIFIED
- The live heartbeat after the restart (acceptance: heartbeat_ts within one tick-write interval of last_write_ts).

## VERIFY ROUNDS
- r1 (2026-09-30, code-reading tiers during a RAM window): contract ACCEPT WITH CORRECTIONS (test-only: full-dict check, restore refusals -> cases 1b and 3b added per AMENDMENT 2); adversarial ACCEPT (0 blocking).
