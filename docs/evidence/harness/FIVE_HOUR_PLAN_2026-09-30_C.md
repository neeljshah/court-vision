# PLAN C -- capture, latency, reliability, automation, quality (Fable planner C, 2026-09-29 ~23:45Z)
Window: ~23:45Z 09-29 to ~04:45Z 09-30. PAPER ONLY. Read-only planner; every number below was read this session.

## Measured this session (the facts the packages rest on)
- HEARTBEAT IS BLIND ON BOTH ROOTS. Tick journal 09-29: heartbeat:state_root = degraded on 11 of 14 ticks and producer_stopped/orphan_writer on the other 2-3; its output says mlb and wnba SILENT (invalid_tail_timestamps, last_write_missing_or_invalid_while_live), every sport DEGRADED on invalid_error_counter:last_adapter_error. But state/mlb/_heartbeat.json at 23:38:19Z is fresh (n_games_live 1, errors 0, last_adapter_error null). Suspected cause, unverified: capture_watchdog.assess (capture_watchdog.py:150-191) samples `now` once at start, so rows or heartbeats written during an 11-20 s read count as future-dated (invalid); a null last_adapter_error counts as a malformed counter. heartbeat:books_root = timed_out (child_timeout at 60 s) on 5 of the last 7 ticks since 20:26Z.
- orphan_writer comes from the tick's own child reaper (paper_desk_process.py:174-175: the child exited while the job object still listed pids). It fired 3 of 28 heartbeat runs, which looks like a transient grandchild.
- Issue queue: 6 P1 + 1 P2. schedule_invalid (S520a); census 09-24/09-25 night_noncanonical_as_of (paper_desk_evidence.py:77-78: as_of != D+1T06:00Z; NO register row); night 09-26 PARTIAL (S501); schedule_missing 09-27/09-28 (past days, cannot be written now); heartbeat:state_root P2 (NO row). The tick status is `refused` on every tick, so a real refusal looks the same as the noise.
- RAM at 23:36Z: 607 MB free. Sweep pytest 898 MB, books runner 691 MB, a lead's ingame_scoreboard_night on a scratch root 473 MB, polymarket 232 MB. The supervisors relaunch only at >= 2000 MB free. The tick checks that a supervisor process exists, so "supervisor alive, child down" reads as capture_present.
- Sweep: 714 of 1150 files done (675 green, 30 red, 3 rss_exceeded, 6 timeout). 13 non-green files are in NO S570-S578 row: ingame_scoreboard_night_e2e, forward_capture_stream_integration, live_shadow_fills_memo, forward_qualification_cross_sport (timeout), odds_provider inplay_kalshi + pinnacle, mcp_server envelope_contract, ops deploy_pathspec, live_edge gpu_dist/joint_dist/joint_v2/tick_replay, live_edge test_shadow (rss).
- FILE COLLISION: capture_scheduler.py has 3 writers: S561 (verified 5d89469c0, cherry-picked by the 08:37Z cron), S598 (h271, capture-latency lead) and S531 (h260, soccer lead). local_state_capture* has 2: S535 (h262) and S594 (planned). Restarts already queued: state2 04:37Z (S490/S494; needs >= 1.5 GB free), books 08:37Z (S561).

## WORK PACKAGES (ranked)
C1 HEARTBEAT TRUTH. Goal: the tick's two heartbeat steps report reality within 15 s.
- Rows: new (next unreserved S601). Executor: NEW Opus RELIABILITY lead, one builder and two Opus verifier tiers.
- Files: scripts/platformkit/ingame/capture_watchdog.py and its test only. Not an S500 file; not human-gated.
- Build: take `now` after the read (or allow a skew equal to the read time); treat a null last_adapter_error as "no error"; bound the books tail read by bytes.
- Construct cases: a writer appending during the run; a null last_adapter_error; a 1 GB shard; a truly stale heartbeat, which must stay SILENT (proves the alarm still fires).
- Time: 2.5 h, first in order. Done: 3 consecutive live ticks log heartbeat:state_root ok and heartbeat:books_root not timed_out; a construct stale root still reads SILENT; the P2 issue closes.
- RAM: the watchdog peak on the real roots is measured with psutil and must stay < 150 MB. Per-file tests only.

C2 RAM WINDOWS FOR TONIGHT'S SCHEDULED EVENTS. Goal: nothing scheduled is refused for low RAM.
- Rows: S490/S494 adoption, the 09-29 night (S500/S501), S561. Executor: the dispatcher plus the quality lead (it owns the sweep). No build.
- Pause the per-file sweep and every lead process over 200 MB in three windows: 04:20Z-04:50Z (state2 restart cron, needs >= 1.5 GB); 05:40Z until nights/2026-09-29.json exists (the one-shot waits for >= 2,700 MiB; a deferral costs a 3 h backoff under S520b); 08:20Z-08:50Z (S561 plus the books restart).
- Time: 0.3 h of attention. Done: no deferred_low_ram row in the 09-30 journal; soccer rows carry state.league and NBA rows carry season_type after the restart; the 09-29 night is COMPLETE, or PARTIAL for a reason other than RAM.

C3 UNTRIAGED SWEEP REDS. Goal: every non-green file has a row and a cause.
- Rows: S579 plus new rows. Executor: the quality lead's next package, after S570-S578.
- Order by night-path risk: ingame_scoreboard_night_e2e, forward_capture_stream_integration, live_shadow_fills_memo, forward_qualification_cross_sport, inplay_kalshi, pinnacle, envelope_contract, deploy_pathspec, then the 5 live_edge files only after 06:00Z (gpu_dist peaks at 968 MB).
- Re-run each file alone on the current master, then label it a stale pin, not hermetic, or a REAL regression.
- Resume the remaining 436 files only between 06:00Z and 18:00Z, with a start gate of >= 2.5 GB free. Add the gate if per_file_test_sweep has none.
- Time: 2.5 h. Done: 13 of 13 mapped with a cause line by 05:30Z. A REAL regression on the night path goes to the dispatcher before 05:40Z.
- RAM: one pytest at a time; skip any file over 500 MB while games are live.

C4 CAPTURE-LATENCY LEAD, NEXT (after S598 and S592 reach verified).
- Ordering is binding. S598 does NOT land on master before the 08:37Z S561 cherry-pick: rebase it onto 5d89469c0 and land it after 08:37Z. S531 lands after S598. S594 builds only after S535 lands.
- C4a: run scratchpad/s563_probe.py at >= 03:30Z on the 09-29 WNBA finals. Then close S563 as not reproduced, or spec the ET-day plus previous-day dates= fix. 0.5 h.
- C4b: read the ESPN play-by-play wallclock for the finished MNF 401872963 (one request), then write the S595 spec. Build tomorrow, before the TNF 10-01 state2 window. 1 h.
- C4c: measure the books runner's trade path per served ticker (request cost, RSS) and write the S597 spec. 0.5 h.
- Spec only: S593 (the push socket is a new long-running process, so OWNER approval is needed), S596 (waits for live NBA), S564 (parked; no consumer reads it).
- Time: about 2 h left on the current rows plus 2 h. Done: S563 closed or spec'd; S595 and S597 specs committed; the collision order recorded in NOW.md.
- RAM: probes stream line by line, capped at 400 MB, and run outside live windows when they are heavy.

C5 FAULT-MATRIX EXTENSION. Rows S588-S590. Executor: the system-test lead's next package, after S582-S584.
- New cases:
  (a) a live writer during the watchdog run: DEFECT before C1, PASS after;
  (b) supervisor alive but child refused by the 2000 MB floor, which the tick reads as capture_present: widen S583 or open a row;
  (c) all three supervisors dead with journals ending on child_start (the OS-sleep signature): one tick at logon relaunches all three;
  (d) the S561 cron cherry-picking onto a master with a conflicting capture_scheduler.py: it must revert cleanly and leave books running.
- Also a night rehearsal on a scratch copy at low RAM: exit 4, then the S520b backoff is observed.
- Time: 3 h. Done: matrix >= 38 cases; every new DEFECT has a row or a FOR note.
- RAM: scratch roots only, each case < 200 MB.

C6 QUEUE HYGIENE AND TICK SPECS FOR THE IMPROVE RUN. Executor: the RELIABILITY lead, after C1. No build in S500 files; the improve run owns them.
- --link every P1: schedule_invalid to S520, night 09-26 to S501, the heartbeat P2 to the C1 row.
- Write specs:
  1. Census 09-24/09-25: an explicit dated legacy_noncanonical exclusion list in paper_desk_config.json with register refs. NOT a rerun: S586 turns any <D>.rN.json into a permanent refusal.
  2. orphan_writer: re-poll the job pids for <= 2 s before declaring an orphan.
  3. schedule_missing for a past day: a terminal close path, with the 09-27/09-28 capture gap noted in the register.
  4. The heartbeat 60 s budget: re-measure after C1 and drop it if C1 makes it moot.
- Post the specs ranked in NOW.md FOR paper-desk-improve, after S520/S521/S585-S587.
- Time: 1.5 h. Done: 0 P1 with row None; 3-4 specs committed.

C7 WHAT SURVIVES THE APP CLOSING. Executor: the RELIABILITY lead. 0.5 h.
- Build an evidence table in NOW.md: duty, host, survives the app closing, survives OS sleep. Sources: schtasks /query /v for CourtVisionPaperDesk (triggers, last result, WakeToRun), list_scheduled_tasks, and the cron list.
- Known: the Windows tick and the supervisors survive the app closing, but the supervisors do NOT survive OS sleep (09-25; 09-29 03:16Z). Session crons die with the session: the heartbeat f2aaebe0 (which also expires 7 days after creation, about 10-06) and the one-shots at 04:37Z and 08:37Z. The desktop tasks run only while the app is open.
- Actions: the dispatcher re-arms or retires the heartbeat before 10-06. A PENDING ADOPTIONS block lists the S490/S494 and S561 confirm checks, so the morning task sees a missed one-shot. OWNER NEEDED: sleep = never on AC and/or WakeToRun on the tick (system settings, owner only).
- Done: every row of the table cites evidence; both asks are in NOW.md.

Executor totals: RELIABILITY lead C1+C6+C7 = 4.5 h; quality lead C3 = 2.5 h, plus C2 pauses; capture-latency lead about 4 h; system-test lead about 1.5 h current plus 3 h.

## Highest-risk failure modes (tonight and 09-30 games)
1. A silent capture loss nobody sees.
   - Cause: a hung child, or a child refused under the 2000 MB floor, reads as capture_present, and both heartbeats already read degraded or timed_out.
   - Guards: C1 plus C5(a)(b). Until C1 lands, the dispatcher's 30-min heartbeat reads each _heartbeat.json last_write_ts age directly, not the watchdog verdict. For OS sleep: C7 owner ask, and C5(c) proves one-tick recovery.
2. RAM starvation of the scheduled work.
   - With 0.6-1.8 GB free, a dead child is not relaunched, the 09-29 night defers into a 3 h backoff, and the 04:37Z adoption skips.
   - Guards: the C2 windows, the C3 sweep start gate, no process over 200 MB except captures from 18:00Z to 06:00Z, live_edge only after 06:00Z.
3. Adoption collisions on the capture files.
   - The 08:37Z cron cherry-picks S561 while S598 and S531 also edit capture_scheduler.py, and S535 and S594 share the state files. A conflicted pick or half-landed code restarted at game time drops books or state2.
   - Guards: the C4 ordering; one restart per capture per window, 06:00Z-16:00Z only; the adoption checklist (first row within 5 min, fresh heartbeat, RSS within +150 MB); C5(d) proves the cron's revert path.
