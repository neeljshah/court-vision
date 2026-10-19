# Fault-matrix root-cause result - 2026-10-06

BUILT: the reproduced nine failures are stale cases, class (a). After fixture
corrections, all 42 tests pass, including the unchanged S585/S586/S587 defect pins.
Machine: local Windows laptop; serial, paper-only construct tests, no network.
Worktree: C:/Users/neelj/wt-fix-faultmatrix, fix/faultmatrix-2026-10-06.
Base commit: 1b05887a1. No production modules changed and no commits made.

Paths below are relative to the worktree. `ops/` means scripts/platformkit/ops/;
`execution/` means scripts/platformkit/execution/.

| Case | Class | Commit moving the contract | Code evidence and correction |
| --- | --- | --- | --- |
| 7 | (a) STALE CASE | S715 2bb5711da; S736 8aa6eb0c6; adoption aa8b4b586 | execution/schedule_d1.py:221 and ops/schedule_recovery.py:52 require successful fetch receipts. ops/paper_desk_scope.py:23 selects dated sports; execution/schedule_d1.py:196 requires their archive directories. ops/system_fault_cases_night_b.py:213 now supplies OK/200; :238 creates roots for configured sports. All midnight/DST dates, four writes, and probe checks remain. |
| 8 | (a) STALE CASE | S526 a37e11ed4 and bce4a0101 | execution/paper_night.py:215 loads the admission declaration; execution/paper_night_admission.py:49 and :102 use a common night floor. The old 2,000,000,000-byte fixture exceeded the 1,282,965,504-byte floor. ops/system_fault_cases_night.py:16 now injects 1,000,000,000 bytes. Deferral receipt, no terminal record, retry, no backoff, and once-only checks remain. |
| 14 | (a) STALE CASE | S492 0d2d5a196; S469 96727df01 | execution/ingame_scoreboard_night.py:38 registers the October 3 seal; execution/ingame_scoreboard_amendment.py:72 includes the NFL identity. The September 30 seal mismatched three current implementation files before fault injection. ops/system_fault_cases_night.py:198 now uses October 3 and all seven current identities. Control succeeds, then the same identity tamper refuses amendment_mismatch without output. All receipt/refusal checks remain. |
| 17 | (a) STALE CASE | S715 2bb5711da | execution/schedule_d1.py:221 rejects the incomplete injected fetch receipts. ops/system_fault_cases_night2.py:33 now supplies OK/200 for both zero-event and mixed-day fixtures. Existing zero rows, NFL row, off-day alarms, no publication, night, and census checks remain. Equivalent fixture correction landed in offday test under 12bbea873. |
| 19 | (a) STALE CASE | S717 cc139a165 | ops/paper_desk_tick.py:267 returns 3 for counted refusals. ops/system_fault_cases_tick2.py:132 expects exactly [3, 0], preserving all seven corruption variants and live/replayed attention checks, including the original future-stamp allowance. |
| 20 | (a) STALE CASE | S717 cc139a165 | ops/paper_desk_tick.py:267 changes counted configuration refusals to exit 3. ops/system_fault_cases_tick2_b.py:115 now checks 3; every independent-step, scanner, and unparseable-config exit-2 check remains. |
| 23 | (a) STALE CASE | S715 2bb5711da and 8d2c620f3 | Shared receipt correction restores initial publication. ops/schedule_recovery.py:22 adds persistent schedule_publication.lock. ops/system_fault_cases_night2.py:241 now requires exactly the pointer and that lock, still rejecting extra files. All corruption injections remain; the sole failed check is still reported_outside_d1_window (S587), exactly as pinned. |
| 24 | (a) STALE CASE | S526 a37e11ed4 and bce4a0101 | Same admission change as case 8; ops/system_fault_cases_night2_b.py:22 now injects 1,000,000,000 bytes. Complete rerun, exclusive output, unchanged bytes, partial night, and deferred-night exclusion checks remain. |
| 32 | (a) STALE CASE | S715 2bb5711da | ops/system_fault_cases_night_b.py:213 successful-fetch fields restore the schedule retry in ops/system_fault_cases_night2_b.py:243. Admission deferral, exact child count, RSS kill, ongoing-RAM kill, child death, markers, journal, and census retry checks remain. |

S754 fef67ec7e adds today's recovery step at ops/paper_desk_tick.py:239;
it explains the extra schedule_recovery call in case 20, not the exit-code failure.
The existing injected child seam handles it; no recovery expectation was relaxed.
S502/S778/S779/S767 were not needed to explain the reproduced nine failures.
No new class (b) production defect or class (c) case defect was established.
S587 remains a known production defect; its test remains pinned to DEFECT.

Pin checks before editing: git grep -n <basename> -- tests/ for all six case
modules found no applicable pinned/sha256/must_not_move/LOC/byte constraints.
Module-name import survey found only test_system_fault_matrix.py; the reference
in test_paper_desk_issue_offday.py is explanatory prose, not an import.
No test files, verdict pins, or production files were edited.
Read-only peer review found no blockers. Changed Python files remain at
243/288/300/300/210/259 lines respectively; ASCII and LF checks pass.
Targeted git diff --check passes.

Test commands and observed summaries (three full-file invocations, two executed):

1. `python -m pytest tests/platformkit/ops/test_system_fault_matrix.py -q -p no:cacheprovider --basetemp=.rt-fm-tmp/a`
   First invocation: forty-two setup errors in 1.92 seconds because the scratch
   parent .rt-fm-tmp did not exist. Created that directory inside this worktree.
2. `python -m pytest tests/platformkit/ops/test_system_fault_matrix.py -q -p no:cacheprovider --basetemp=.rt-fm-tmp/a`
   Baseline: nine failed, thirty-three passed in 114.08 seconds; exactly the
   reported cases 7, 8, 14, 17, 19, 20, 23, 24, and 32 failed.
3. `python -m pytest tests/platformkit/ops/test_system_fault_matrix.py -q -p no:cacheprovider --basetemp=.rt-fm-tmp/b`
   After corrections: forty-two passed in 114.11 seconds. Known defect rows
   18, 23, and 28 retained their exact pinned failed-check sets.

No additional importing test files were found, so no additional tests were run.
Generated scratch roots were removed after the tests completed.

NOT VERIFIED: production capture or deployment; real network fetches; the full
suite; correction of the known S585/S586/S587 defects; model calibration quality.
These are harness results only, not a change to model calibration.

BUILT - files changed: scripts/platformkit/ops/system_fault_cases_night.py, scripts/platformkit/ops/system_fault_cases_night_b.py, scripts/platformkit/ops/system_fault_cases_night2.py, scripts/platformkit/ops/system_fault_cases_night2_b.py, scripts/platformkit/ops/system_fault_cases_tick2.py, scripts/platformkit/ops/system_fault_cases_tick2_b.py, docs/evidence/harness/RT_faultmatrix_result_2026-10-06.md.
