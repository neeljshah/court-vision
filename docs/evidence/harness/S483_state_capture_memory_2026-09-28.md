# S483 state capture memory and descendant sampler

Historical construct verdict (preceding FIX LANE 1d): ACCEPT for the local construct contract after AMENDMENT 1 / FIX LANES 1a and 1b; 23 / 23 cases pass. No adoption claim. Machine: local Windows worktree C:/Users/neelj/nba-harness-h136, construct and supplied fixture only. Current master inventory base: bc3cae4c70b20a0fa4e99b8e08c797b003e5b67e. Original dispatch / C20 oracle base: 1dfce38cfac814af528cddac0924ab7c7889dfe7. Recovery oracle: 6edce1f9d40c2b7a5390d7170f49aac482a7fdbf, blob d3cb258951d2d8023aa26159517ba81f5d8f2fd5 (asserted before execution). Metric: passing enumerated cases / 23; bar 23 of 23; n = 23 (CONSTRUCT); eye check n/a.

## FIX LANE 1d: STOPPED - failure outside the S483 sampler

Verdict: STOPPED under the explicit instruction to stop if the traceback is outside S483. The malformed-schedule child failed at `scripts/platformkit/execution/ingame_scoreboard_night.py:162`, in `os.replace(temporary, a.out)`, with a Windows sharing violation. This file is identical to master after LF normalization; identity and SHA-256 are in `s483_fix1d/failing_source_identity.json`. The traceback contains no sampler frame. The process holding the file lock is NOT VERIFIED; this evidence does not identify that process or establish why the lock was held.

Machine: local Windows, `C:/Users/neelj/nba-harness-h136`. No other worktree was edited. Full output is retained under `docs/evidence/harness/s483_fix1d/`.

| Execution | Count and outcome |
|---|---|
| Requested isolated malformed-schedule reproduction | 60/60 passed, one pytest process per invocation |
| Diagnostic baseline full file | 1/1 passed; 14 tests |
| Injected sampler exception constructs before hardening | 12/12 failed (deliberate regression proof) |
| Exploratory hardening first full sampler run | 53 passed |
| Four S483 files, once each after adding receipt equivalence | recovery 18, growth 8, tennis 4, sampler 55; 85 passed |
| Requested 30 full-file repetitions | STOPPED after attempt 6: 5/6 passed; 83 tests passed, 1 failed; 24 not run |
| Contract preflight | Not run: external-cause stop instruction took precedence |

The 12 constructs injected NoSuchProcess, AccessDenied, and ZombieProcess into the child constructor, child memory read, descendant enumeration, and descendant memory read. The exploratory change passed all 55 sampler tests, including existing parent-only checks, two new landed-receipt equivalence checks, and sampled-lower-bound disclosure. It did not resolve the observed failure. Once the full child traceback established the external failure site, all three exploratory sampler/test changes were removed. `discarded_hardening.patch` preserves that experiment for review only; it is NOT a proposed landing. Existing S483 candidate source and tests are retained; all three restored files match the original candidate inventory SHA-256 values (`s483_fix1d/restored_candidate_hashes.json`). No scoreboard implementation or malformed-schedule test was changed by FIX LANE 1d.

Commands: isolated invocations used `python -m pytest tests/platformkit/execution/test_paper_night_scoreboard_step.py::test_malformed_served_schedule_real_module_refuses_schedule_rows -q -p no:cacheprovider -rA`. Full-file diagnostic invocations used `python -m pytest tests/platformkit/execution/test_paper_night_scoreboard_step.py -q -p no:cacheprovider -rA -p docs.evidence.harness.s483_fix1d.capture_child`, with `S483_RUN=validation_01` through `validation_06`. The diagnostic plugin duplicates each child's output descriptor and reads it after the test, preserving the full child traceback after the supervisor closes its temporary log. It does not replace child output or change assertions. Logs `reproduce_01.log` through `reproduce_60.log`, `baseline_full.log`, `validation_01.log` through `validation_06.log`, `construct_before.log`, `construct_after.log`, and `s483_*.log` preserve full pytest output. The full failing child output is `validation_06_test_malformed_served_schedule_real_module_refuses_schedule_rows_child_0.log`.

Full child traceback from full-file attempt 6:

```text
Traceback (most recent call last):
  File "C:\Users\neelj\AppData\Local\Programs\Python\Python310\lib\runpy.py", line 196, in _run_module_as_main
    return _run_code(code, main_globals, None,
  File "C:\Users\neelj\AppData\Local\Programs\Python\Python310\lib\runpy.py", line 86, in _run_code
    exec(code, run_globals)
  File "C:\Users\neelj\nba-harness-h136\scripts\platformkit\execution\ingame_scoreboard_night.py", line 167, in <module>
    raise SystemExit(main())
  File "C:\Users\neelj\nba-harness-h136\scripts\platformkit\execution\ingame_scoreboard_night.py", line 162, in main
    os.replace(temporary, a.out)
PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'C:\\Users\\neelj\\AppData\\Local\\Temp\\pytest-of-neelj\\pytest-10417\\test_malformed_served_schedule0\\outputs\\scoreboard\\tmpctw4ae6c' -> 'outputs\\scoreboard\\2026-09-22.json'
```

The corresponding full pytest output (`validation_06.log`) reports:

```text
>       assert row["exit_code"] == 0
E       assert 1 == 0

tests\platformkit\execution\test_paper_night_scoreboard_step.py:243: AssertionError
1 failed, 13 passed in 13.47s
```

NOT VERIFIED: the lock holder, a fix for the scoreboard replace failure, 30/30 full-file passes, and contract_preflight. No claim is made that sampler hardening fixes this flake. No commit, deployment, registry write, or flag change occurred.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX LANE 1c: legacy snapshot race assertion

Only test_legacy_budget_through_main_steps_none_three_steps in tests/platformkit/execution/test_paper_night_scoreboard_step.py changed. Each step requires type(processes_already_exited) is int and membership in {0, 1}; all other normalized snapshot keys still compare exactly, including row counts and key presence. The frozen fixture and shared normalization helper are unchanged. Comments and setup statements were compacted inside that same function to retain 300 lines. AST comparison confirms all other module nodes are unchanged. All 14 pre-existing candidate Python paths in the inventory retain their session-start SHA-256 hashes; no implementation edit occurred.

Exact before/after lines (git diff, line numbers in hunk headers):

```diff
diff --git a/tests/platformkit/execution/test_paper_night_scoreboard_step.py b/tests/platformkit/execution/test_paper_night_scoreboard_step.py
index 6a2dc8b34..876f708b6 100644
--- a/tests/platformkit/execution/test_paper_night_scoreboard_step.py
+++ b/tests/platformkit/execution/test_paper_night_scoreboard_step.py
@@ -84,18 +84,13 @@ def _low_ceiling_template(tmp_path):
 
 
 def test_legacy_budget_through_main_steps_none_three_steps(tmp_path, monkeypatch):
-    # Case 1, AMENDMENT 2(e): a legacy budget through the REAL main(steps=
-    # None) end-to-end -- accepted, exactly 3 steps, scoreboard absent, and
-    # byte-identical (timing stripped, root replaced) to a frozen snapshot
-    # of the PRE-CHANGE (master) implementation, not hand-authored names.
+    # Case 1: frozen legacy snapshot; only the process-exit race may vary after normalization.
     template_path, template = _low_ceiling_template(tmp_path)
     monkeypatch.setattr(night, "DEFAULT_BUDGET", template_path)
     legacy = dict(template, ceiling_bytes={k: template["ceiling_bytes"][k] for k in night.NAMES})
     legacy["producer_args"] = {k: v for k, v in template["producer_args"].items()
                                 if k not in steps_mod.NEW_PRODUCER_KEYS}
-    legacy_path = tmp_path / "legacy.json"
-    write(legacy_path, legacy)
-    archive_fixture(tmp_path, legacy)
+    legacy_path = tmp_path / "legacy.json"; write(legacy_path, legacy); archive_fixture(tmp_path, legacy)
     monkeypatch.setattr(night.importlib.util, "find_spec", lambda _: object())
     calls = _fake_children(monkeypatch)
     argv = ["--date", DAY, "--as-of", AS_OF, "--repo-root", str(tmp_path), "--budget", str(legacy_path)]
@@ -104,7 +99,12 @@ def test_legacy_budget_through_main_steps_none_three_steps(tmp_path, monkeypatch
     assert code == 0 and payload["status"] == "COMPLETE"
     assert [s["name"] for s in payload["steps"]] == FROZEN_LEGACY_NAMES
     assert len(calls) == 3; expected = json.loads(json.dumps(CASE1_SNAPSHOT["steps"])); argv = expected[1]["argv"]
-    argv[argv.index("--out"):argv.index("--out")] = ["--as-of", AS_OF, "--night-date", DAY]; assert _normalize_rows(payload["steps"], tmp_path) == expected
+    argv[argv.index("--out"):argv.index("--out")] = ["--as-of", AS_OF, "--night-date", DAY]
+    actual = _normalize_rows(payload["steps"], tmp_path)
+    for row, frozen in zip(actual, expected):
+        assert type(row["processes_already_exited"]) is int and row["processes_already_exited"] in {0, 1}
+        frozen["processes_already_exited"] = row["processes_already_exited"]
+    assert actual == expected
     _assert_fresh_digests(tmp_path, payload["steps"])  # digest checked freshly, not pinned
 
 
```

Command for each of 20 consecutive, separate invocations:
`python -m pytest tests/platformkit/execution/test_paper_night_scoreboard_step.py -q -p no:cacheprovider`

Full-file result: 19/20 passing invocations, 279 passed tests and 1 failed test. The authorized legacy snapshot test passed 20/20. Run 16 failed in test_malformed_served_schedule_real_module_refuses_schedule_rows at line 243: assert row["exit_code"] == 0 observed 1. That test was not edited. A 20/20 full-file pass is NOT VERIFIED. No extra repetitions were substituted for the failed run.

| Run | Result |
|---|---|
| 1 | 14 passed in 7.05s; exit 0 |
| 2 | 14 passed in 7.23s; exit 0 |
| 3 | 14 passed in 7.03s; exit 0 |
| 4 | 14 passed in 7.04s; exit 0 |
| 5 | 14 passed in 7.09s; exit 0 |
| 6 | 14 passed in 6.89s; exit 0 |
| 7 | 14 passed in 6.98s; exit 0 |
| 8 | 14 passed in 6.83s; exit 0 |
| 9 | 14 passed in 6.88s; exit 0 |
| 10 | 14 passed in 7.09s; exit 0 |
| 11 | 14 passed in 7.98s; exit 0 |
| 12 | 14 passed in 8.16s; exit 0 |
| 13 | 14 passed in 8.85s; exit 0 |
| 14 | 14 passed in 7.23s; exit 0 |
| 15 | 14 passed in 7.71s; exit 0 |
| 16 | 1 failed, 13 passed in 8.37s; exit 1 |
| 17 | 14 passed in 8.43s; exit 0 |
| 18 | 14 passed in 8.03s; exit 0 |
| 19 | 14 passed in 7.71s; exit 0 |
| 20 | 14 passed in 8.32s; exit 0 |

Four S483 files, once each, using `python -m pytest <one path> -q -p no:cacheprovider`:

| File | Result |
|---|---|
| tests/platformkit/ingame/test_local_state_recovery.py | 18 passed in 3.98s; exit 0 |
| tests/platformkit/ingame/test_local_state_recovery_growth.py | 8 passed in 25.58s; exit 0 |
| tests/platformkit/ingame/test_tennis_start_strip.py | 4 passed in 9.59s; exit 0 |
| tests/platformkit/execution/test_paper_night_tree_sampler.py | 41 passed in 1.67s; exit 0 |

S483 total: 71 passed, 0 failed. Combined lane executions: 350 passed, 1 failed. Prior-lane regression results below remain historical; this lane did not rerun every paper-night file.

Contract preflight result: 9/9 PASS (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication). Command: `python -m scripts.platformkit.tracking.contract_preflight --paths <14 pre-existing NOT EQUAL Python paths from the inventory> tests/platformkit/execution/test_paper_night_scoreboard_step.py docs/evidence/harness/S483_state_capture_memory_2026-09-28.md --base master --spec docs/evidence/tracking/specs/S483_spec.md`. Checked 16 files including this memo.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## Binding before-condition

The historical probe archive was committed at a974296f27c0790f2c614921e6c088ad3de4cb25 (a974296f2), under `docs/evidence/harness/s483_probes/`; all 20 files are present in this fast-forwarded worktree. The earlier d0230333b commit omitted the ignored probe files; a974296f2 supplied them. They are archived observations, never rerun by this lane. Their hashes and sizes appear below.

Before-condition citations (each `.py` companion is preserved beside its output):
- [s483_hours_out.txt](s483_probes/s483_hours_out.txt): zero rows before the 15:21:36Z child start, first NBA row 15:21:37.996607Z.
- [s483_sample_out.txt](s483_probes/s483_sample_out.txt): commits at lines 8, 201, 379 (16:17:41, 16:20:56, 16:23:55Z); 195/179 s intervals and post-commit private 436 MiB, RSS 89-90 MiB; peak_wset 722,337,792 B throughout.
- [s483_tennis_probe_out.txt](s483_probes/s483_tennis_probe_out.txt): 50/100/200 matches, landed peaks 16,297,371/58,229,947/216,649,524 B versus stripped 417,519/799,228/1,605,140 B; landed wall 10.03/44.66/179.61 s.
- [s483_recovery_probe_out.txt](s483_probes/s483_recovery_probe_out.txt) and [s483_recovery_wall_out.txt](s483_probes/s483_recovery_wall_out.txt): 506 keys, 5,000/20,000 rows, peaks 20,947,638/83,567,253 B, wall 0.116/0.504 s.
- [s483_sizes_out.txt](s483_probes/s483_sizes_out.txt): 2026-09-23 totals 448,341,444 B/615,542 rows, zero multi-row identities in all listed shards. Approximately 2.5 GB rollover memory remains an extrapolation, never measured.
- [s483_lineup_probe_out.txt](s483_probes/s483_lineup_probe_out.txt): zero lineup blocks in 1,000/1,687 MLB rows.
- [s483_control_out.txt](s483_probes/s483_control_out.txt): no-tennis control, pid 23036, created 17:00:09Z; exact memory/cadence numbers below.
- [s483_m0_out.txt](s483_probes/s483_m0_out.txt) and [s483_m0_landed_out.txt](s483_probes/s483_m0_landed_out.txt): 496 rows/393,003 B fixture; landed 462/478 recovered keys at the two cutoffs.

Premise correction: the spec's observed approximately 520 MiB swing was per tick, not startup recovery: that child recovered zero rows. Tennis copied tournament groupings into every match before canonical JSON serialization. Recovery retention is real but latent. The spec's (vi) no-tennis control reports pid 23036, RSS 99,315,712 B, peak 100,188,160 B, private 442,970,112 B, CPU 0.5 percent and heartbeat gaps 4.99-5.02 s after the 17:00:09Z relaunch. These observations are supported by the copied historical control output; this lane did not reproduce the live measurement.

## Implementation and evidence boundaries

The pinned dispatch base's local_state_capture_io.py:122-131 recover_states remains byte-identical. Recovery mirrors the landed per-row checks and refusal precedence, with a SQLite receipt identity spool. Differential equality uses the asserted pinned blob; tennis uses an identity patch of strip_unshared_groupings as its oracle. R5's three departures are excluded from R1: non-string sports are parse refusals; visible receipts outside int64 seconds plus whole nanoseconds are timestamp refusals; spool failures count recovery_spool_errors and raise recovery_spool_failed. T1 is deliberately conservative: deep or non-plain groupings retain quadratic cost. Recovery flatness concerns rows per game; tennis flatness concerns matches per tournament. The sampler adds descendants' current RSS and is a sampled lower bound. Post-exit memory remains parent-only. A burst between polls is explicitly unobserved.

The expected cadence change from approximately 180-195 s toward 5-7 s can increase tennis output: 729 draw matches each roughly 7 s is approximately 375,000 rows/hour. Shard bytes, spool bytes, rollover work and S479 state inputs grow with that rate. The spec's 25 us per landed parse and two parses per clean row predict roughly 30 s for 615,542 rows, and minutes for millions. These are predictions, not measurements. The Opus-tier measurement of the candidate's own C15 growth case is approximately 89 us per row, approximately 16x the landed per-row cost. At that measured rate, 615,542 rows imply approximately 55 s; a busy tennis day with millions of rows could exceed the 180 s rollover bar. Those scaled times are extrapolations, not measured rollovers. Named follow-up: tennis emit-on-change, to reduce repeated draw-match rows. The rollover reread remains intact. mlb_lineup_ledger's two-day rows_by_key and the lifetime adapter_failures list and S481 WNBA registration are unchanged. Adoption requires the orchestrator's M1 owner-visible relaunch after landing; this lane never relaunches capture.

LF fixture pattern, already supplied on the base:
`tests/platformkit/ingame/fixtures/s483_state_midnight/** text eol=lf`.
No additional JSON seal or fixture path is introduced.

## AMENDMENT 1: exact before/after double edits

Only the following doubles changed in the three landed test files. All existing assertions and fixtures remain unchanged. Five process cases share ONE `Proc` definition, so the nine case-level edits occupy five source locations. `Q` below is the unchanged expression `budget["ceiling_bytes"]["qualification"] + 1`.

| Case / file under tests/platformkit/ | Before | After |
|---|---|---|
| 1. execution/test_paper_night_deadline.py:121, legacy snapshot | `lambda pid: _FIXED_PEAK` | `lambda pid, row: _FIXED_PEAK` |
| 2. execution/test_paper_night_inputs_e2e.py:35, memory kill | `lambda pid: Q` | `lambda pid, row: Q` |
| 3. execution/test_paper_night_inputs_e2e.py:50, counted diagnostic | `lambda pid: Q` | `lambda pid, row: Q` |
| 4. execution/test_paper_night_inputs_e2e.py:75-76, reservation | `def sample(pid)`; fallback `real_sample(pid)` | `def sample(pid, row)`; fallback `real_sample(pid, row)` |
| 5. ops/test_s479_ram_probe.py:45, race=none | `Proc` has no `children` | `def children(self, recursive=True): return []` |
| 6. ops/test_s479_ram_probe.py:45, race=child_exit | `Proc` has no `children` | Same shared method as case 5 |
| 7. ops/test_s479_ram_probe.py:45, race=child_timeout | `Proc` has no `children` | Same shared method as case 5 |
| 8. ops/test_s479_ram_probe.py:45, race=stack_exit | `Proc` has no `children` | Same shared method as case 5 |
| 9. ops/test_s479_ram_probe.py:45, race=unrelated_exit | `Proc` has no `children` | Same shared method as case 5 |

C20 assertions added ONLY to the S483 sampler test file: extract the actual updated `Proc` from the landed test file and compare `_sample_peak(pid, row)` to the parent-only `_sample_peak` loaded from the immutable dispatch base. All five races are checked at ticks 0/2 for PIDs 1/2/3: equal peaks or matching NoSuchProcess, with no added diagnostic key. The four changed sampler stubs are compared to their pinned-base definitions with both reservation branches exercised. All nine parametrizations pass. The original C20 numeric boundary checks and legacy snapshot byte-equality assertion also pass. No implementation changed during FIX LANE 1a; SHA-256 equality is checked against session-start contents.

## Per-case and regression results

C1 PASS; C2 PASS; C3 PASS; C4 PASS; C5 PASS; C6 PASS. C7 PASS; C8 PASS; C9 PASS; C10 PASS; C11 PASS; C12 PASS. C13 PASS; C14 PASS; C15 PASS; C16 PASS; C17 PASS; C18 PASS; C19 PASS. C20 PASS: all nine authorized double cases and their explicit parent-only equivalence checks pass. C21 PASS through poll_step and the RAM probe; C22 PASS; C23 PASS. The historical before-condition is cited from the committed probe archive at a974296f2.

Every pytest invocation used `python -m pytest <one path> -q -p no:cacheprovider`. C14/C15 output was exposed with -rP; C19 with -s. No suite invocation occurred. All results below are the final recorded run per file, not a sum across repeated runs. FIX LANE 1a reran exactly the three previously failing files, four S483 files, and the LOC rail: 144 passed, 0 failed. FIX LANE 1b reran the four S483 files and all 14 other paper-night files in this table, each separately. Remaining rows are retained prior-lane results. Combined latest-per-file inventory: 1,560 passed, 1 failed.

| Test path (under tests/platformkit/) | Passed | Failed |
|---|---:|---:|
| ingame/test_local_state_capture.py | 19 | 0 |
| ingame/test_state_capture_io.py | 198 | 0 |
| ingame/test_state_capture_recovery.py | 25 | 0 |
| ingame/test_state_capture_commit.py | 11 | 0 |
| ingame/test_state_capture_sources.py | 240 | 0 |
| ingame/test_local_state_capture_schedule.py | 367 | 0 |
| ingame/test_local_state_capture_differential.py | 5 | 0 |
| ingame/test_state_capture_fix_1q.py | 183 | 0 |
| ingame/test_state_capture_fix_1s.py | 9 | 0 |
| ingame/test_mlb_lineup_state.py | 18 | 0 |
| ingame/test_mlb_lineup_state_1c.py | 15 | 0 |
| ingame/test_mlb_lineup_state_1d.py | 4 | 0 |
| ingame/test_mlb_lineup_state_1e.py | 19 | 0 |
| ingame/test_mlb_lineup_state_1f.py | 16 | 0 |
| ingame/test_mlb_lineup_state_1g.py | 6 | 0 |
| ingame/test_mlb_lineup_state_1h.py | 7 | 0 |
| ingame/test_wnba_registration.py | 45 | 0 |
| ingame/test_wnba_registration_books.py | 4 | 0 |
| ingame/test_wnba_registration_e2e.py | 12 | 0 |
| test_loc_rail_scope.py | 1 | 0 |
| execution/test_paper_night_tree_sampler.py | 41 | 0 |
| execution/test_paper_night.py | 39 | 0 |
| execution/test_paper_night_deadline.py | 20 | 0 |
| execution/test_paper_night_deadline_1b.py | 9 | 0 |
| execution/test_paper_night_deadline_1c.py | 3 | 0 |
| execution/test_paper_night_scoreboard_step.py | 13 | 1 |
| execution/test_paper_night_scoreboard_step_1c.py | 4 | 0 |
| execution/test_paper_night_scoreboard_step_1d.py | 2 | 0 |
| execution/test_paper_night_scoreboard_step_1e.py | 1 | 0 |
| execution/test_paper_night_inputs.py | 40 | 0 |
| execution/test_paper_night_inputs_e2e.py | 10 | 0 |
| execution/test_paper_night_scratch.py | 19 | 0 |
| execution/test_paper_night_steps.py | 50 | 0 |
| execution/test_paper_night_steps_1d.py | 25 | 0 |
| execution/test_paper_night_steps_1e.py | 8 | 0 |
| ops/test_s479_ram_probe.py | 42 | 0 |
| ingame/test_local_state_recovery.py | 18 | 0 |
| ingame/test_local_state_recovery_growth.py | 8 | 0 |
| ingame/test_tennis_start_strip.py | 4 | 0 |

Prior-lane CLI --help passed: local_state_capture, paper_night, s479_ram_probe, and s483_memo_facts (including inventory and facts subcommands). FIX LANE 1a C14 peaks new 5000/20000 = 96,399,360/97,177,600 B, delta 778,240 B < 16,777,216 B. Landed power check 103,555,072/133,615,616 B, delta 30,060,544 B (not the spec's expected roughly 60 MB). C15 new spool 16,384/2,879,488 B, wall 0.458428/1.775892 s; landed wall 0.028773/0.131193 s. C15 keys100/1000: peak 93,962,240/95,682,560 B, wall 0.013487/0.088556 s, spool 16,384/16,384 B. C15 block1/729: peak 93,859,840/95,682,560 B, wall 0.003792/0.068391 s, spool 16,384/16,384 B. C19 peaks100/400 = 840,931/3,185,338 B; ratio 3.787870824122312 <= 5; peak400 <= 16 MiB. C19 landed25/50 = 1,958,948/6,732,474 B; ratio 3.4367803535366943 >= 3. These are generated-construct measurements. Recovery has slower construct wall time; only the specified memory bar is asserted. Small spools can retain pages in the bounded cache. C21 sustained construct asserts candidate >=67108864 B, parent-only <50331648 B, KILLED ceiling_exceeded, two killed processes and zero survivors. Its exact candidate peak was not retained; this rerun printed landed_peak=16,666,624 B. The CR-only text-cookie defect and unwrapped SQLite fetch failure were fixed and tested. Prior-lane preflight: 9 / 9 PASS: vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication. Command: python -m scripts.platformkit.tracking.contract_preflight --paths <the 11 owned Python files plus this memo> --base master --spec docs/evidence/tracking/specs/S483_spec.md. The prior inventory used the original dispatch SHA; FIX LANE 1b regenerates it against the full current master SHA below. The original dispatch and recovery oracle remain pinned for differential tests. FIX LANE 1a contract_preflight: 9 / 9 PASS after correcting a historical timestamp token caught by the prose vocabulary check and restoring the pinned recover_states line-span citation required by the literal threshold check. Command: `python -m scripts.platformkit.tracking.contract_preflight --paths <14 NOT EQUAL Python paths in the inventory below> docs/evidence/harness/S483_state_capture_memory_2026-09-28.md --base master --spec docs/evidence/tracking/specs/S483_spec.md`. Session-start/current SHA-256 checks confirm all 15 inspected implementation/helper files are byte-identical. SHA: NOT CREATED (sandbox); files ready for lane_commit


FIX LANE 1b: the four S483 files pass 18 / 8 / 4 / 41 tests respectively (71 passed, 0 failed). The 14 additional paper-night files total 243 passed, 1 failed; combined this session: 314 passed, 1 failed (latest run per file). Commands: `python -m pytest <one path> -q -p no:cacheprovider`; growth also used `-rP`, tennis `-s`, and the failed file was rerun with `-vv --tb=long`. Environment: Windows, Python 3.10.0, pytest 9.0.2. No implementation or test edits in FIX LANE 1b.

S484 changed `scripts/platformkit/execution/paper_night_inputs.py` upstream in 2bdaf902e8e9c8720700706080d95b77c8f6bb39. It is EQUAL to current master bc3cae4c70b20a0fa4e99b8e08c797b003e5b67e in the regenerated inventory. On that base the paper-night input suites pass: test_paper_night_inputs.py 40, test_paper_night_inputs_e2e.py 10; test_paper_night.py also passes 39. The broader paper-night run is not wholly passing here: test_paper_night_scoreboard_step.py::test_legacy_budget_through_main_steps_none_three_steps fails twice with only processes_already_exited differing (actual 0, frozen snapshot 1 for qualification and week). Its other 13 tests pass. This memo records the observed failure rather than carrying forward the earlier all-pass claim; the text-only lane leaves it for follow-up.

FIX LANE 1b growth rerun: C14 candidate peaks 95,797,248 / 97,259,520 B at 5,000 / 20,000 rows (delta 1,462,272 B); landed 103,788,544 / 133,451,776 B (delta 29,663,232 B). C15 candidate wall 0.4145445 / 1.6789854 s, landed 0.0260233 / 0.1235160 s; spool 16,384 / 2,879,488 B. C19 candidate peaks 840,931 / 3,185,338 B (ratio 3.787870824122312); landed 1,959,001 / 6,732,474 B (ratio 3.4366873727986866). The Opus-tier 89 us/row disclosure above is the prior review measurement; these rerun timings do not establish a live rollover time.

FIX LANE 1b contract_preflight: 9 / 9 PASS over the same 14 NOT EQUAL Python paths plus this memo, with `--base bc3cae4c70b20a0fa4e99b8e08c797b003e5b67e --spec docs/evidence/tracking/specs/S483_spec.md`. Master advanced during this lane only by docs/evidence/tracking/specs/S474_spec.md; the exercised source and tests are unchanged from worktree HEAD a974296f27c0790f2c614921e6c088ad3de4cb25. Current master source inventory and the facts block were regenerated from the helper; the committed probe archive was verified without running it. SHA: NOT CREATED (sandbox); files ready for lane_commit

## Reproduced inventory

`python -m scripts.platformkit.ops.probes.s483_memo_facts inventory <all paths printed below>`; LF-normalized byte identities against current master, pinned above. The emitted dispatch_base field now names that inventory base.
The memo is excluded from its own inventory. No test pins mutable module lengths.

```text
dispatch_base=bc3cae4c70b20a0fa4e99b8e08c797b003e5b67e
recovery_oracle=6edce1f9d40c2b7a5390d7170f49aac482a7fdbf
scripts/platformkit/ingame/local_state_recovery.py NOT EQUAL resolution=n/a
  candidate sha256=e24040aa4d3884ae668d65cab54287c17ff5985a6e7030fbb40b3c55421b274d bytes=7812 lines=177
  base ABSENT
scripts/platformkit/ingame/local_state_capture_io.py NOT EQUAL resolution=n/a
  candidate sha256=9444790894c9ee44c7de1a7bdc64e3f3ca17c687604a1e123f6632b42cabda47 bytes=16983 lines=299
  base sha256=a7376bf5dabf86d4afc5484f4e48e810489b3f7fd0412e8c842e2023605fa616 bytes=17137 lines=300
scripts/platformkit/ingame/local_state_capture_sources.py NOT EQUAL resolution=n/a
  candidate sha256=7eb4570c7d01ee25a3b3f14b2a0117636dcf2be24f3439544640eb157ce5b2ce bytes=20825 lines=300
  base sha256=42d928f76750d22b9ed6ac4e58f3886fe233b10557fb0a205d69b3ac5ebedbce bytes=20773 lines=300
scripts/platformkit/execution/paper_night_peak.py NOT EQUAL resolution=n/a
  candidate sha256=aeb136c88f08264304105cc471e329348f89f9fb1c6b8c172bdfdd021b9b486a bytes=3094 lines=75
  base sha256=54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de bytes=2378 lines=52
scripts/platformkit/execution/paper_night.py NOT EQUAL resolution=n/a
  candidate sha256=eb5ce154888d8ab9b6be35c2cbaae1d038f11708e86290d191c770a7ad2304f3 bytes=15558 lines=291
  base sha256=4416bdefb76c8253eef887c34d609a68c6e9289b9d0125010ca5a50f8d69583c bytes=15507 lines=291
scripts/platformkit/ops/probes/s479_ram_probe.py NOT EQUAL resolution=n/a
  candidate sha256=cae9526046ad3b7f103aacf7019ea3e61c20b09172e8005db2d4ea4bf8bb8280 bytes=15534 lines=300
  base sha256=a7aa3cb01a09a231756123572d3e333506a306218b8ccec5a5ac162f631ea295 bytes=15467 lines=300
scripts/platformkit/ops/probes/s483_memo_facts.py NOT EQUAL resolution=n/a
  candidate sha256=1144d3b2a8ca8e642a617f1dbc5b343c1debf074af0d11be8556f95dcbed61ea bytes=4785 lines=114
  base ABSENT
tests/platformkit/ingame/test_local_state_recovery.py NOT EQUAL resolution=n/a
  candidate sha256=efe5263701b1ebf702f736b52dc3f90791dd6a411a09662c33dbd3aac6597c29 bytes=12984 lines=255
  base ABSENT
tests/platformkit/ingame/test_local_state_recovery_growth.py NOT EQUAL resolution=n/a
  candidate sha256=052aa659b03f5a501323e6d9709b9ad85748d4cb7487efb0bedaba66a29ae370 bytes=11053 lines=232
  base ABSENT
tests/platformkit/ingame/test_tennis_start_strip.py NOT EQUAL resolution=n/a
  candidate sha256=533c84bc78f264d24b0157dcc42013e6416584d1b4a09c420c769c6624ccdb7f bytes=9011 lines=216
  base ABSENT
tests/platformkit/execution/test_paper_night_tree_sampler.py NOT EQUAL resolution=n/a
  candidate sha256=bf3e5ebe571eecc04e49f36abd79efa3137baadeadfee34d5eb1f9f7388ea4fd bytes=11896 lines=252
  base ABSENT
scripts/platformkit/ingame/local_state_capture.py EQUAL resolution=n/a
  candidate sha256=60eac7412421886563f269691e4ad92b76df6d32be3267a44cf207d84f82000b bytes=17858 lines=300
  base sha256=60eac7412421886563f269691e4ad92b76df6d32be3267a44cf207d84f82000b bytes=17858 lines=300
scripts/platformkit/ingame/local_state_capture_commit.py EQUAL resolution=n/a
  candidate sha256=847653b56d193be64896a0f454c883ea0bfa9494d7b54d8a62211460b5c1e872 bytes=4267 lines=83
  base sha256=847653b56d193be64896a0f454c883ea0bfa9494d7b54d8a62211460b5c1e872 bytes=4267 lines=83
scripts/platformkit/ingame/local_state_capture_dates.py EQUAL resolution=n/a
  candidate sha256=e86df18af4ced4d28796d9a11f706aebaae689c661dcdffedf1743c193c71475 bytes=5400 lines=117
  base sha256=e86df18af4ced4d28796d9a11f706aebaae689c661dcdffedf1743c193c71475 bytes=5400 lines=117
scripts/platformkit/ingame/local_capture_writer.py EQUAL resolution=n/a
  candidate sha256=ef36aff93500d7c9c71d5de8bd21deea811eb2131a0e242e09af32f65c4a5c2e bytes=9737 lines=226
  base sha256=ef36aff93500d7c9c71d5de8bd21deea811eb2131a0e242e09af32f65c4a5c2e bytes=9737 lines=226
scripts/platformkit/ingame/local_capture_client.py EQUAL resolution=n/a
  candidate sha256=349829a07b1781afdee3c3bc0dd31f08cf9a57d93a20a33a1a7ce8336cb6cb7c bytes=7366 lines=168
  base sha256=349829a07b1781afdee3c3bc0dd31f08cf9a57d93a20a33a1a7ce8336cb6cb7c bytes=7366 lines=168
scripts/platformkit/ingame/mlb_lineup_seam.py EQUAL resolution=n/a
  candidate sha256=1c313e6e0093f78a7470cde0b8b820dbb391098efcdab249a57398d321277e04 bytes=3270 lines=62
  base sha256=1c313e6e0093f78a7470cde0b8b820dbb391098efcdab249a57398d321277e04 bytes=3270 lines=62
scripts/platformkit/ingame/mlb_lineup_ledger.py EQUAL resolution=n/a
  candidate sha256=3e6045ebc18f2f9a0a13ebd33d8c67ce025dc5a1405017ce64a12fc3293bb46f bytes=13511 lines=238
  base sha256=3e6045ebc18f2f9a0a13ebd33d8c67ce025dc5a1405017ce64a12fc3293bb46f bytes=13511 lines=238
scripts/platformkit/ingame/mlb_lineup_state.py EQUAL resolution=n/a
  candidate sha256=1ba4d5076c5e4386e2e4b07008146dc43c536457451d01f1ec86a07359c4b3a0 bytes=14570 lines=239
  base sha256=1ba4d5076c5e4386e2e4b07008146dc43c536457451d01f1ec86a07359c4b3a0 bytes=14570 lines=239
scripts/platformkit/ingame/nba_state_enrichment.py EQUAL resolution=n/a
  candidate sha256=be46b4ecc694ee3d8bd4add0a96bf130ea7ef733a520894dd852e9abd1596fdb bytes=2933 lines=57
  base sha256=be46b4ecc694ee3d8bd4add0a96bf130ea7ef733a520894dd852e9abd1596fdb bytes=2933 lines=57
scripts/platformkit/ingame/wnba_state.py EQUAL resolution=n/a
  candidate sha256=57445a5cf35a249fd72058ade5a01b1224b14e61bf2a76fcf0c8997443ddd90f bytes=1729 lines=39
  base sha256=57445a5cf35a249fd72058ade5a01b1224b14e61bf2a76fcf0c8997443ddd90f bytes=1729 lines=39
scripts/platformkit/ops/capture_supervisor.py EQUAL resolution=n/a
  candidate sha256=c139b08d385079e7fd2b43552795c2ca50d6838db869fb93d61c6d769755c2c3 bytes=15250 lines=299
  base sha256=c139b08d385079e7fd2b43552795c2ca50d6838db869fb93d61c6d769755c2c3 bytes=15250 lines=299
scripts/platformkit/execution/paper_night_inputs.py EQUAL resolution=n/a
  candidate sha256=4163a4ed8217b9eedb67965cb0b49161594b0b1ab7078bc182b110638d159da9 bytes=9358 lines=171
  base sha256=4163a4ed8217b9eedb67965cb0b49161594b0b1ab7078bc182b110638d159da9 bytes=9358 lines=171
scripts/platformkit/execution/paper_night_deadline.py EQUAL resolution=n/a
  candidate sha256=df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b bytes=14592 lines=293
  base sha256=df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b bytes=14592 lines=293
scripts/platformkit/execution/paper_night_steps.py EQUAL resolution=n/a
  candidate sha256=3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 bytes=14942 lines=293
  base sha256=3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 bytes=14942 lines=293
scripts/platformkit/execution/paper_night_lock.py EQUAL resolution=n/a
  candidate sha256=1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa bytes=1069 lines=33
  base sha256=1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa bytes=1069 lines=33
scripts/platformkit/execution/paper_night_scratch.py EQUAL resolution=n/a
  candidate sha256=8364798a87d109f0cc672acacb2045a0356c9ca12eb0642a1925aa7efb63b43f bytes=3432 lines=80
  base sha256=8364798a87d109f0cc672acacb2045a0356c9ca12eb0642a1925aa7efb63b43f bytes=3432 lines=80
scripts/platformkit/execution/paper_night_budget.json EQUAL resolution=n/a
  candidate sha256=83d2eb3defef596eaf16bbb9caa5befedcf74b8ab543dafc97e330bf94e3d03b bytes=1505 lines=25
  base sha256=83d2eb3defef596eaf16bbb9caa5befedcf74b8ab543dafc97e330bf94e3d03b bytes=1505 lines=25
scripts/platformkit/ops/forward_qualification_daily.py EQUAL resolution=n/a
  candidate sha256=ada413a1665516303cc2d3de35088d7888a05dd2238c084c40d6e0431797a15e bytes=15212 lines=300
  base sha256=ada413a1665516303cc2d3de35088d7888a05dd2238c084c40d6e0431797a15e bytes=15212 lines=300
tests/platformkit/execution/test_paper_night_deadline.py NOT EQUAL resolution=n/a
  candidate sha256=05f1a7f436cc4e256d5e45ade249955b3c0272e3b1888ea5e8ea1770a3f96149 bytes=15815 lines=299
  base sha256=3d28704d5c2826aafe8351c8e1a6871616a6e72ed71ed764dec500c5fb4002d6 bytes=15810 lines=299
tests/platformkit/execution/test_paper_night_inputs_e2e.py NOT EQUAL resolution=n/a
  candidate sha256=7133f170efa2429f52bb933459e20c28b42a428de02307da7509e59e1979cc4a bytes=14501 lines=288
  base sha256=b94a1404fffb95d86a84262056fac535e65f7990afc30fd556434c5047f15bde bytes=14481 lines=288
tests/platformkit/ops/test_s479_ram_probe.py NOT EQUAL resolution=n/a
  candidate sha256=e33e3ab8b1ff4571c9d5ca8b5a5d7dd3a89b078211d7a86428509262f365bf2e bytes=15438 lines=274
  base sha256=77e03b2fe6dfc7ea7390c38cf2398e5650004fcc8da730b80c34625f4c71bc25 bytes=15384 lines=273
```

## Historical probe inventory

Current checkout raw-byte identities are regenerated below; git core.autocrlf=true accounts for checkout line endings. All 20 files match committed master after LF normalization. No probe executed or edited. These historical files are outside the Python/memo preflight path list.

```text
docs/evidence/harness/s483_probes/s483_control.py bytes=1476 sha256=628b10f1ec755f042616d2d369f93a75c9f2dd8c350905c600a143171fa898e5 resolution=n/a
docs/evidence/harness/s483_probes/s483_control_out.txt bytes=503 sha256=db1ebc6bacc025b9a238e3f12ee85145033d141f609c6415710c641355c1484c resolution=n/a
docs/evidence/harness/s483_probes/s483_hours.py bytes=1309 sha256=56ac393304a7605414dd74cc5eb379f6fec316759c67bc8de6f0086ad25dfaab resolution=n/a
docs/evidence/harness/s483_probes/s483_hours_out.txt bytes=1159 sha256=8db4695264ffdf7e9fcf42cd332ef1599d7860762de632ad66e2428ab4d3fb47 resolution=n/a
docs/evidence/harness/s483_probes/s483_lineup_probe.py bytes=1516 sha256=a09f695b9f11e0d711feeab9a5e1a1f92112d258f0fdf324496a0e757ce0f366 resolution=n/a
docs/evidence/harness/s483_probes/s483_lineup_probe_out.txt bytes=210 sha256=b1a2a4a9b414eba45d0cdbeaf873b8fd329008266125922c0b21f9e117946dfb resolution=n/a
docs/evidence/harness/s483_probes/s483_m0.py bytes=1982 sha256=78a07ed5afb9bc3d02ded662943bb317ec582365d8f6f05f40b4d76b62a944e8 resolution=n/a
docs/evidence/harness/s483_probes/s483_m0_landed.py bytes=864 sha256=6209a13e4b99009f5e286e0cc18f5293bc0c5b3b72c54b858948897644822dc8 resolution=n/a
docs/evidence/harness/s483_probes/s483_m0_landed_out.txt bytes=252 sha256=83b79be4415670719957271316bfce809cf76d0af179bd797ef168d7cad4af11 resolution=n/a
docs/evidence/harness/s483_probes/s483_m0_out.txt bytes=647 sha256=c0c7e5d6c72f84638b793b9b02f318eb8c4cbdac388b1dc20c653418685f9d84 resolution=n/a
docs/evidence/harness/s483_probes/s483_recovery_probe.py bytes=3526 sha256=b7b726b6c7ff4c5e6ce41620b779a130e46ee64a1b25fad8628760dabc0ddff3 resolution=n/a
docs/evidence/harness/s483_probes/s483_recovery_probe_out.txt bytes=182 sha256=8683a70af30b87142f8124d2c71c6e5649de23551ca3597766f9bb60d4c8409c resolution=n/a
docs/evidence/harness/s483_probes/s483_recovery_wall.py bytes=1124 sha256=0f4096a5bf6b843e334b251218eb7bdb542d9d553041c6e504c452a59e54acea resolution=n/a
docs/evidence/harness/s483_probes/s483_recovery_wall_out.txt bytes=128 sha256=a6115e016c776b98ceceb8d229cddee3dfd70fd343ea6b8189a6f774a67c1970 resolution=n/a
docs/evidence/harness/s483_probes/s483_sample.py bytes=1073 sha256=118ad91ff0b0c49a6a98098d89f00e2017e357642a3e7a6022b872208661bfa2 resolution=n/a
docs/evidence/harness/s483_probes/s483_sample_out.txt bytes=44590 sha256=b418962cffbbd23e3c27d0c8bb0bb7c1972b0309ad8e48f6cc6e23b6e0a4bcaf resolution=n/a
docs/evidence/harness/s483_probes/s483_sizes.py bytes=1757 sha256=aec9c5c350715c556e98617a3ca55f334a3491bb3da7f5cf3ff70fe72b6c2326 resolution=n/a
docs/evidence/harness/s483_probes/s483_sizes_out.txt bytes=2128 sha256=a92e51505e2ca43c3ddb6b6712640414eb44f5a50c3f4151f8c6d4dda68ea1e0 resolution=n/a
docs/evidence/harness/s483_probes/s483_tennis_probe.py bytes=4941 sha256=66f2a6739e877504afa3c495c1a78f247f084247dd1c25c24a1fc0156144f386 resolution=n/a
docs/evidence/harness/s483_probes/s483_tennis_probe_out.txt bytes=709 sha256=a1ea6abc3a7e97893c9d6b56c1c68a9c04b2efa58202523f90e07ef10ff55787 resolution=n/a
```

## Reproduced facts

`python -m scripts.platformkit.ops.probes.s483_memo_facts facts` (verbatim; stale C20 and missing-probe disclosures removed in FIX LANE 1b):

```text
cases_enumerated=23 bar=23 n=23 (CONSTRUCT)
C1: empty shards, sport repetition and zoneless now
C2: ordered per-row refusals
C3: nanosecond as-of and UTC day boundaries
C4: exact receipt identities and last equal location
C5: duplicate, NaN and conflicted receipt state machine
C6: receipt, sport and key ordering
C7: ASCII chunk and shard read failures
C8: R5 type and representability departures
C9: spool failures and capture retry
C10: cleanup and stale spool sweep
C11: interleaved active and lockless spool ownership
C12: sealed midnight rows and recovered tick bytes
C13: fresh producer and consumer capture processes
C14: recovery row-count flatness and landed power check
C15: receipt-block, key, wall and spool growth constructs
C16: tennis differential schedules and selection
C17: tennis conservative fallback
C18: tennis capture tick bytes
C19: tennis flatness and landed power check
C20: parent-only sampler equivalence and regressions
C21: sustained descendant tree and termination
C22: denied and vanished process samples
C23: missed burst sampled lower bound
tests/platformkit/ingame/fixtures/s483_state_midnight/state/mlb/2026-09-25.jsonl rows=13 bytes=14653 sha256=93444f1177771171c3a00c5861f9e679b35ff5c7818a54554198a673f9926758 resolution=n/a
tests/platformkit/ingame/fixtures/s483_state_midnight/state/nba/2026-09-25.jsonl rows=1 bytes=2054 sha256=ccbf32e9860d9ae047f736daf155ed96e512de67be5f028d3c4bf9ec0ba4e816 resolution=n/a
tests/platformkit/ingame/fixtures/s483_state_midnight/state/ncaaf/2026-09-26.jsonl rows=18 bytes=18708 sha256=380a8207ada5dda9e46d2122312463e625b695816b55c43c61aac5146aed08a4 resolution=n/a
tests/platformkit/ingame/fixtures/s483_state_midnight/state/nfl/2026-09-26.jsonl rows=16 bytes=16586 sha256=eddb71b42b71a1c0648f46df30dbaf3827f05e776fb1e188629126c4aa9d84a3 resolution=n/a
tests/platformkit/ingame/fixtures/s483_state_midnight/state/tennis/2026-09-25.jsonl rows=448 bytes=341002 sha256=a3d7e2211d0d7651716089a23194c31027f893c39a04806e727197a08a7cfbce resolution=n/a
fixture_total rows=496 bytes=393003 sha256=2384402a7b6565105b4cbadb403d2a8529144bb0759f54cd8736f27c0f50f69f (sorted path concatenation, LF)
NOT VERIFIED
- No live capture, archive, network, pod or adoption was exercised.
- M1 startup, midnight rollover, cadence and memory bars need owner relaunch.
- No busy-day cadence, millions-of-rows rollover or disk capacity measurement.
- Deep or non-plain tennis groupings retain the landed quadratic cost.
- The descendant sampler can miss bursts between samples and after parent exit.
- C21 exercises poll_step and the RAM probe, not the complete paper_night._run route.
- The unchanged MLB lineup two-day map and adapter failure list remain unbounded.
```

## NOT VERIFIED

- A fully passing paper-night regression set is not verified: FIX LANE 1d reproduced the malformed-schedule failure at ingame_scoreboard_night.py:162 (Windows sharing violation during os.replace), outside the S483 sampler; stopped after 5/6 full-file passes.
- No live capture, archive, network, pod or adoption was exercised.
- M1 startup, midnight rollover, cadence and memory bars need owner relaunch.
- No busy-day cadence, millions-of-rows rollover or disk capacity measurement.
- Deep or non-plain tennis groupings retain the landed quadratic cost.
- The descendant sampler can miss bursts between samples and after parent exit.
- C21 exercises poll_step and the RAM probe, not the complete paper_night._run route.
- The unchanged MLB lineup two-day map and adapter failure list remain unbounded.
