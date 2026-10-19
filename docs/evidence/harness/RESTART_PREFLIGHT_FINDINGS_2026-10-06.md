# Books restart preflight: three false refusals (2026-10-06) -- S783

PAPER ONLY. Read-only diagnosis by the morning landing lead. Code: scripts/platformkit/ops/restart_preflight.py,
scripts/platformkit/ops/capture_supervisor_lock.py, scripts/platformkit/ops/paper_desk_start.py.

`relaunch_books_2026-10-03.ps1 -RowSha a44e0b7b5c735785dbf5568e4a911144db488908 -DryRun` REFUSED at 09:28:54Z
(dispatcher re-ran read-only at 10:44Z: same) with {boot_mismatch: 1, game_started_or_near: 2, process_unknown: 1}.
Each refusal is an artifact of the check, not of the machine:

1. boot_mismatch. boot_id = time.time() - GetTickCount64()/1000 (capture_supervisor_lock.default_query) and
   _boot_matches compares int(a) == int(b). The lock recorded 1791238157.3445802 at launch (22:10Z 10-05, boot 22:09Z).
   Now the same expression reads 1791238155.193018 (10:4xZ 10-06): 2.15 s lower. Cause: the wall clock moved, not
   the boot. System log (Kernel-General id 1): svchost (w32time) stepped the clock by -1,295 ms at 22:56:06Z 10-05,
   plus slewing since. Same boot: supervisor 11380 and child 23512 are alive and their native start times equal the
   lock exactly (1791238249.4949303 / 1791238249.618847). Any wall-clock correction after a launch fails this check
   until the next reboot.
2. game_started_or_near (x2). eligibility() refuses every row of docs/evidence/forward/schedules/<today>_maker_forward.json
   with scheduled_start - now <= 3600 s; a PAST start satisfies that too. 10-06 rows: KXMLBGAME-26OCT052000NYYTB
   00:00Z and KXNFLGAME-26OCT05ATLNO 00:15Z (both finished ~10 h earlier) and LAD at ATL 22:00Z (not near). Any UTC day
   whose schedule holds an evening-US game (00:xxZ) therefore refuses the restart all day.
3. process_unknown. inventory() refuses a row with no cmdline whose name is empty or contains python. pid 188 is
   Windows "Secure System" (VBS, protected): psutil name() returns '' and cmdline() raises AccessDenied, so it is
   counted on every Windows box with VBS on. It is not a Python process. Identity (pid + start_time) of 11380 / 23512
   matched exactly; no rounding problem there.

## PROPOSED fix (not built; owner/next lane)
- Boot: _boot_matches tolerates |a - b| <= 5 s (a reboot moves boot_id by minutes or more), or compare the boot from
  the Windows event-log boot record / GetTickCount64 at lock time instead of wall-derived boot_id.
- Games: count a row as near only when -(qualification window, 3600 s + margin) < start - now <= 3600 s, i.e. treat a
  game whose window ended (or a settled row) as not near.
- Process: skip rows with empty name and AccessDenied when pid is a known protected system process (Secure System,
  Registry, System Idle, System), or require name to be readable AND contain python before counting process_unknown.
- Identity: keep pid + native start_time; accept |delta| <= 2 s if a future seam rounds.
- Tests: one construct each (clock step -1.3 s keeps match; past 00:00Z row not near; nameless AccessDenied pid not
  counted) in a new tests/platformkit/ops/test_s783_preflight_artifacts.py.

## Adoption used today
Because all three are artifacts, the dispatcher directed adoption through the tick's own recreate path
(STOP_books, wait for the supervisor and child to exit, remove STOP, one tick). Result is in DESK_STATE section 3
and the S767 register row.
