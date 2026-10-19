# S812 adversarial tier 2026-10-09 (PAPER ONLY)

Two rounds, Opus subagents, one mutant at a time on the worktree module, restored from pristine copies after each
(scratch C:\Users\neelj\AppData\Local\Temp\claude\s812_scratch\mut.py, mut2.py). Each mutant ran the s812 test file and
test_state_capture_sources.py, one process per file, with the RAM / pump.stop gate before every run.

## Round 1 on 2b48c1233 -- REJECT (test gap, no code defect): 11 of 15 killed
- KILLED: M1 drop report, M3 recorded drops raw, M4 raw at top level, M5 unknown -> pre, M6 "" unmapped, M7 None unmapped,
  M8 mapped string records raw, M9 only tennis wired, M10 only ESPN wired, M11 unmapped raises, M12 fallback live.
- SURVIVED: M13 espn_name reads event status before competition status (real gap); M2 / M14 counter under the wrong sport
  (masked because report() lets get.source override the sport); M15 tennis rows[-1] (equivalent: one status per competition).
- Fix round 1 (60d28a4fe): test_competition_status_is_read_before_the_event_status; the unmapped tests `del get.source`.
  Lead re-ran mut.py M2 M13 M14: all three KILLED.

## Round 2 on 60d28a4fe -- ACCEPT
- M1-M14 KILLED; M15 SURVIVED, confirmed behaviour-equivalent (domains/tennis/ingest_espn.py copies one status per competition
  into both player rows; tennis_poll parses one isolated competition per call).
- New: N2 non-str counted, N5 reason renamed, N6 raw key renamed, N7 status = raw string, N8 double count, N9 raw dropped on
  the nba/wnba path -- KILLED. N1 soccer counted under nba, N3 recorded mutates the input state, N4 case-insensitive lookup -- SURVIVED;
  N1 masked by get.source like M2, N3 equivalent (every caller passes a fresh dict), N4 a test gap.
- No real defect. Count-before-drop (nba_adapter_empty, tennis _identity) is allowed by the spec.

## After round 2 (lead, tests only, no code change)
- test_soccer_extra_time_finals_are_counted_not_pre now `del get.source`; new test_a_case_variant_of_a_mapped_name_is_unmapped.
- mut2.py N1 N4 re-run: N1 KILLED (2 soccer params fail), N4 KILLED (case-variant test fails). s812 file 16 passed 0.70 s.
- Final mutant tally: 24 mutants, 22 KILLED, 2 SURVIVED (M15 and N3), both behaviour-equivalent in production.
