# Integration Windows test run (cxp/integ-2026-10-02)

Union-merge attrs used on append-only ledgers; test-only branch, never to be landed.

| branch | merge | test files | passed | failed | errors | skipped | failure class | one-line cause |
|---|---|---|---|---|---|---|---|---|
| S659 | CLEAN | 4 | 52 | 35 | 0 | 0 |  |  |
| S690 | CLEAN | 8 | 110 | 39 | 8 | 1 |  |  |
| S658 | CLEAN | 4 | 0 | 0 | 0 | 79 |  |  |
| S594 | CLEAN | 2 | 25 | 0 | 0 | 0 |  |  |
| S631 | CLEAN | 1 | 6 | 0 | 0 | 0 |  |  |
| S641-fix | CLEAN | 1 | 11 | 0 | 0 | 0 |  |  |
| S653-S656-fix | CLEAN | 1 | 1 | 1 | 0 | 7 |  |  |
| S660 | CLEAN | 1 | 19 | 7 | 0 | 0 |  |  |
| S663 | CLEAN | 3 | 21 | 0 | 0 | 0 |  |  |
| S664 | CLEAN | 1 | 30 | 2 | 0 | 0 |  |  |
| S695 | CLEAN | 3 | 82 | 2 | 0 | 0 |  |  |
| S666 | CLEAN | 1 | 26 | 0 | 0 | 0 |  |  |
| S667 | CLEAN | 2 | 52 | 0 | 0 | 0 |  |  |
| S668 | CLEAN | 3 | 91 | 1 | 0 | 0 |  |  |
| S669 | CLEAN | 3 | 79 | 1 | 0 | 0 |  |  |
| S670 | CLEAN | 2 | 52 | 0 | 0 | 0 |  |  |
| S698 | CLEAN | 5 | 347 | 0 | 0 | 0 |  |  |
| S671 | CLEAN | 3 | 63 | 1 | 0 | 0 |  |  |
| S672 | CLEAN | 2 | 21 | 0 | 0 | 0 |  |  |
| S674 | CLEAN | 1 | 73 | 1 | 0 | 0 |  |  |
| S675 | CLEAN | 0 | 0 | 0 | 0 | 0 |  |  |
| S676 | CLEAN | 1 | 15 | 2 | 0 | 0 |  |  |
| S677 | CLEAN | 1 | 37 | 0 | 0 | 0 |  |  |
| S678 | CLEAN | 1 | 15 | 1 | 0 | 0 |  |  |
| S679 | CLEAN | 1 | 46 | 0 | 0 | 0 |  |  |
| S682 | CLEAN | 1 | 21 | 1 | 0 | 0 |  |  |
| S683 | CLEAN | 1 | 3 | 8 | 0 | 1 |  |  |
| S684 | CLEAN | 1 | 14 | 1 | 0 | 0 |  |  |
| S685 | CLEAN | 1 | 5 | 0 | 0 | 8 |  |  |
| S686 | CLEAN | 1 | 17 | 1 | 0 | 5 |  |  |
| S687 | CLEAN | 1 | 5 | 5 | 6 | 0 |  |  |
| S688 | CLEAN | 0 | 0 | 0 | 0 | 0 |  |  |
| S689 | CLEAN | 1 | 12 | 0 | 0 | 0 |  |  |
| S691 | CLEAN | 5 | 33 | 13 | 0 | 0 |  |  |
| S692 | CLEAN | 6 | 34 | 19 | 0 | 0 |  |  |
| S693 | CLEAN | 1 | 15 | 2 | 0 | 0 |  |  |
| S694 | CLEAN | 1 | 7 | 0 | 0 | 0 |  |  |
| S696 | CLEAN | 8 | 33 | 34 | 14 | 0 |  |  |
| S697 | CLEAN | 1 | 20 | 4 | 0 | 0 |  |  |
| S699 | CONFLICT  | 9 | 0 | 0 | 0 | 0 |  |  |
| S700 | CLEAN | 13 | 104 | 22 | 0 | 0 |  |  |
| S701 | CLEAN | 4 | 70 | 1 | 0 | 0 |  |  |
| S702 | CLEAN | 8 | 58 | 17 | 0 | 0 |  |  |
| S703 | CLEAN | 2 | 22 | 4 | 0 | 0 |  |  |
| S705 | CLEAN | 2 | 82 | 0 | 0 | 6 |  |  |
| S707 | CLEAN | 10 | 170 | 17 | 0 | 0 |  |  |
| S709 | CLEAN | 1 | 29 | 2 | 0 | 0 |  |  |
| S530 | CLEAN | 2 | 57 | 0 | 0 | 0 |  |  |
| S637 | CLEAN | 5 | 45 | 4 | 0 | 0 |  |  |

(Table counts are first-run counts; every failing file was re-run once and failed again unless noted. Run: 49 ids, ~100 min, one test process at a time. Raw logs: integ_logs/, raw json: integ_raw.json. The failure-class column above is empty; classes are in the next table.)

## Failure class per branch

Root cause worth knowing first: this box has `core.autocrlf=true` (system gitconfig), so every worktree checkout turns LF files into CRLF. That explains most failures: sha256-of-source pins, `code_bad_eol`, `not_canonical` journal lines, `\r` in shell scripts. Checkouts on this box behave the same unless `.gitattributes` pins `eol=lf`.

| branch | class | one-line cause |
|---|---|---|
| S659 | CRLF (suspected) | 35/87 fail; recorder_adopt returns exit 3 (`dirty_tree` refusal, shown explicitly in the identical S690 rig); not proven line by line |
| S690 | CRLF + AV/lock flake | same `dirty_tree` rig failures (39F+8E); allowlist_push "unable to write .git/objects ... Permission denied" (temp-dir lock; corrections file passed on re-run) |
| S658 | skipped (POSIX only) | all 79 tests skipped on Windows; NOT verified here |
| S653-S656-fix | CRLF | `tools/desk_bin/codex` has CR after checkout; test asserts none |
| S660 | symlink privilege + POSIX chmod | WinError 1314 (symlink); `stat.S_IMODE` mode assertions |
| S664, S695 | Windows socket semantics | clock_offset: ConnectionResetError instead of refused/timeout (same 2 tests in both) |
| S668, S671, S686 | CRLF | pinned sha256 of a source file differs under CRLF |
| S669 | POSIX-only call | expects fsync,replace,fsync; Windows skips directory fsync |
| S674, S678, S682, S684 | symlink privilege | WinError 1314 in the symlink-refusal test (1 test each) |
| S676 | Python 3.10 vs 3.11 (suspected) | `...Z` vs `+00:00` isoformat difference |
| S683 | CRLF (suspected) | prereg `UNRULED` extra items: prereg file hash mismatch |
| S687 | missing dependency | `crepes` (requirements-dev-conformal.txt) not installed |
| S691, S692, S696, S700, S702, S707 | CRLF / text-mode write | `JournalCorrupt: not_canonical at line 1` (journal written with CRLF); state_journal asserts exact bytes; recovery tests expect exit 137 (SIGKILL, POSIX-only) got 1; S696/S700/S702/S707 `fixture_night.py` 'random' check also fails. One shared root cause repeated in every branch carrying the S691 tests |
| S693, S703 | CRLF (suspected) | `s693_paper_exec_model` JSON text equal-looking but unequal; S703 reconcile_arm same shape |
| S697 | timing flake | deadman_ping `(t1 - t0) < 1.0` under load (10+ codex lanes running); 4 failures |
| S700 | CRLF | version_registry `code_bad_eol` on strategies.py (explicit EOL check) |
| S701 | genuine logic (unconfirmed) | `TypeError: NoneType < datetime` in family_decay_hardening |
| S709 | path semantics | desk_root absolute-path cases expect raise `not_absolute`; Windows returns ok for POSIX-style paths |
| S637 | data / unclear | progress_ledger "no real funnel verdicts aggregated"; calibration_ledger_replay 'unavailable': likely gitignored data/ absent in worktree |
| S699 | merge anomaly | branch merge returned non-zero at its turn with no conflicted paths listed (merge text not captured). At the end `git merge S699` says "Already up to date" because S700+ contain it; its tests ran inside S700 (test_s699_accounts_restart 4F, test_s699_fix_r1 1F, both not_canonical) |

## FAILURES (trimmed evidence; full text in integ_logs/*.log)

- S659/S690 recorder_adopt*: `assert (3 == 4)`, `assert (3 == 0)`; `AssertionError: ['dirty_tree']`.
- S690 allowlist_push: `git_failed:add:error: unable to write file .git/objects/09/67ef...: Permission denied`.
- S653-S656-fix: `assert b'\r' not in b'#!/bin/sh\r\n# Resolve the Codex binary dynamically...'`.
- S660/S674/S678/S682/S684: `OSError: [WinError 1314] A required privilege is not held by the client`.
- S664/S695: `AssertionError: assert ({'os_error:Co...onResetError'} <= {'refused', 'timeout'}`.
- S668: `assert '9eb2fb6e4e7a...' == 'c...'` (paper_maker.py sha pin). S671, S686 same shape.
- S669: `assert ['fsync', 'replace'] == ['fsync', 'replace', 'fsync']`.
- S687: `ModuleNotFoundError: No module named 'crepes'` (5F + 6E).
- S691..S707 journal: `JournalCorrupt: not_canonical at line 1`; `assert b'{"crc":"936...icker":"c"}\n' == b'{"crc":"936...ker":"c"}\r\n'`; `assert 1 == 137`.
- S700: `RegistryRefused: code_bad_eol: scripts/platformkit/execution/core/strategies.py`.
- S701: `TypeError: '<' not supported between instances of 'NoneType' and 'datetime.datetime'`.
- S709: `assert {('ok', ...)} == {('raise', 'V...ot_absolute')}`.
- S676: `assert '2026-10-02T07:00:01Z' == '2026-10-02T07:00:01+00:00'`.

## SUMMARY

- Fully green on Windows (all collected tests pass): 16 branches: S594, S631, S641-fix, S663, S666, S667, S670, S698, S672, S677, S679, S689, S694, S705 (6 skipped), S530, S685 (8 skipped).
- Not verifiable here: S658 (79/79 POSIX-only tests skipped); S675 and S688 (tests live at scripts/platformkit/eval_gate/test_*.py, outside the tests/ filter, so 0 tests ran; run those files separately).
- Merge conflicts: none (union attrs on ledgers). S699 had a non-zero merge at its turn with no conflicted paths (cause not captured); its content is present via S700.
- Needs a fix (described, not applied), smallest first:
  1. Add `* text=auto eol=lf` (or per-path eol=lf for scripts, journals, JSON, tools/desk_bin/*) to `.gitattributes`, or set autocrlf=input on this box: expected to clear the CRLF family (S653-S656-fix, S668, S671, S686, S700, S693/S703, S683, probably S659/S690). Also have the journal writer open files with `newline="\n"` in order_journal (S691 code): fixes six branches at once.
  2. Symlink tests (S660, S674, S678, S682, S684): skip on WinError 1314 or enable Developer Mode.
  3. POSIX-only assertions: S660 chmod, S669 dir-fsync, S691 exit 137, S709 absolute-path semantics, S664/S695 socket errors: guard by platform or widen the expected set (add ConnectionResetError).
  4. S687: install requirements-dev-conformal.txt (crepes) or skip when absent.
  5. S676: handle 'Z' vs '+00:00' on Python 3.10.
  6. S697: relax the 1.0 s timing bound on a loaded box. S690 allowlist_push: re-run on a quiet box (AV lock).
  7. S701 (looks like a real None-vs-datetime bug) and S637 (needs gitignored data/): investigate.
- Landing note: after the CRLF fix, re-run S659/S690/S691-family first; their failure counts are probably one root cause. The integration branch used merge=union on ledgers, is test-only, and must never be landed.
