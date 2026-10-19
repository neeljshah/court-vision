# S640 cloud result -- 2026-09-30

Row: S640 (governance test landmine). Branch: `cloud/S640-2026-09-30` (commits 18449aaa,
ca7c368d, ba35cc66 on trunk a60dcb09). Spec + AMENDMENT 1: `docs/evidence/harness/S640_spec_2026-09-30.md`.
Machine: cloud clone, Python 3.11.15 (plus a Py3.10.20 venv for the laptop's interpreter).

## Status: BUILT, VERIFIED (ACCEPT WITH CORRECTIONS x2, corrections applied). Not landed.

## Premise (Q8, measured before any edit)
CONFIRMED. The unfixed test calls `RG.main([])` -> `run_all(ledger_path=None)`, and the self-heal
pre-pass rewrites the DEFAULT CLV ledger. Measured in a scratch `git archive` export of a60dcb09
(outside the clone) with a planted `data/frontend/clv_ledger.jsonl` of two identical
`(bet_id B1, open)` rows. Under the test's exact redirects (envelope + scoreboard only), `main()`
returned 0 and rewrote the ledger 2 -> 1 rows (sha256 1575c221... -> 8699c2ea...), leaving
`clv_ledger.jsonl.selfheal.bak`. The other 10 tests were not hermetic either. Every `run_all` call
reaches the realmoney eligibility read (the real ledger plus `data/frontend/grade_summary.json`)
and the loop ledger `.planning/loop/ledger.jsonl`. Mutation M1 below lists all 8 real paths.
The unfixed test file was never run in the clone.

## Change (test-side only; governance/ and scripts/ are byte-identical to a60dcb09)
- `tests/governance/test_run_governance.py` (300 LOC): autouse fixture `_hermetic` redirects the
  8 defaults into tmp_path: RG._DEFAULT_ENVELOPE/_DEFAULT_SCOREBOARD, clv_ledger.DEFAULT_LEDGER,
  clv_ledger_io.DEFAULT_LEDGER, clv_ledger_sanity._default_ledger,
  pm_trading.realmoney_gate.DEFAULT_SUMMARY_PATH, pkl_integrity.MODEL_REGISTRY_PATH,
  improve_ledger_reconcile._DEFAULT_LEDGER. It also unsets GOVERNANCE_REALMONEY_SECRET and runs
  EVERY test under the filesystem guard; teardown fails the test on any path outside tmp_path.
  Six construct tests were added; the 11 existing tests are unchanged (the diff only adds lines).
- `tests/governance/_s640_fs_guard.py` (130 LOC, new): one audit hook per process plus a wrapped
  `os.stat` (and `pathlib._NormalAccessor.stat` on Py3.10).
  - Records: open, rename, remove, mkdir, rmdir, truncate, chmod, link, symlink, utime,
    sqlite3.connect, listdir, scandir, shutil.*, and subprocess.
  - Compares paths after `realpath`. A WRITE outside tmp_path raises PermissionError before the
    syscall.
  - The only allowed reads outside tmp_path are module files (.py/.pyc/.pyd/.so) under sys.path
    roots.

## Tests (one file per process)
| command | result |
|---|---|
| `python3 tools/desk_bin/run_files.py . tests/governance/test_run_governance.py` (Py3.11) | 17 passed |
| `<venv py3.10>/bin/python -m pytest tests/governance/test_run_governance.py -q -p no:cacheprovider` | 17 passed |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py` | 1 passed |

Acceptance bar: 17/17 pass. The spec's bar said 15; the two extra cases are verifier-requested
negative controls, and the bar was not lowered. On final code ba35cc66, Py3.11:
- M1 (all 8 redirects removed) turns BOTH `test_s640_main_touches_nothing_outside_tmp` and
  `test_s640_main_heals_the_redirected_default_ledger` red, and the guard BLOCKED the real-ledger
  write.
- M2 (`_note` no-op) turns the three guard negative controls red.
- abspath instead of realpath turns the symlink control red.
- dropping the scandir events or `os.rename` turns the scandir/rename control red.

`git status --short --ignored data .planning` was empty after every run. The clone has only a
tracked `data/` skeleton; `data/frontend` never existed and nothing was created.

## Verifier tiers (independent Opus sub-agents; the builder did not verify itself)
- Pre-build critic: REVISE, 11 items, all folded into AMENDMENT 1.
- CONTRACT tier (A/B/Q + spec): **ACCEPT WITH CORRECTIONS**. It reproduced 15/15 on 3.10 and 3.11
  and reproduced M1 and M2. It found no diff under governance/ or scripts/, no removed assertion,
  LOC and ASCII OK, and Q7 exhaustive (a plugin traced every default read). Correction: this memo
  was missing (A7). It is now written.
- ADVERSARIAL tier (27 mutants + probes): **ACCEPT WITH CORRECTIONS**. All 8 single-redirect
  mutants went red. Survivors:
  - scandir event removed, rename event removed: FIXED by a new control.
  - the fixture's teardown assert removed: open, see below.
  - heal-test assertions deleted: expected when a test's own asserts are removed.
  - the delenv of the realmoney secret: the variable is unset here.

  Probe: a write through a symlink inside tmp_path went to the outside file. FIXED with realpath
  and a new control. sqlite, subprocess, link, symlink and utime were unguarded: FIXED (blocked).
  Neither is on the governance call graph.
- Corrections re-checked by the builder only (17/17 plus the mutants above). No third
  sub-agent pass was run.

## NOT VERIFIED
- The Windows recorder / laptop box. Not run there. Reasoned from the tiers' review:
  - normcase and the resolved tmp root cover drive-letter case and 8.3 short names.
  - On Windows with Py3.12+, `os.path.exists`/`isfile` skip `os.stat`, so those READS go
    unrecorded. Writes are still blocked.
  - The symlink control SKIPS on hosts without the symlink privilege.
- Behaviour against a REAL populated `data/frontend/clv_ledger.jsonl`. The clone has none; the
  premise was shown on a planted scratch copy only.
- Guard blind spots, documented in its docstring: os.lstat, os.access, network I/O. The guard is
  process-global, so other threads' I/O is also caught.
- The fixture's own teardown assertion has no mutation-killing test. Only
  `test_s640_main_touches_nothing_outside_tmp` repeats that check explicitly, and only for main().
- A test module that star-imports these tests does not get `_hermetic` (underscore name).

## Follow-ups for the landing session (not done on this branch per routine rules)
- `docs/operations/cloud/desk-sweep.prompt.txt:20` still says to SKIP this file; update it when
  this lands.
- The register row and DESK_STATE.md are not edited here.

PORTABLE: yes (pure-Python test; Py3.10 and Py3.11 verified; Windows reasoned, not run).

## Windows landing re-verify (laptop, Py3.10.20, CLOUD-LANDER, 2026-09-30)
- Run ONLY from a fresh worktree (nba-harness-clS640 = master 728bc6e27 + this branch's diff),
  so RG._REPO_ROOT is the worktree, which has no data/frontend at all.
- First run: 1 failed, 15 passed, 1 skipped. The failure was a Windows-only TEST defect:
  test_s640_guard_records_and_blocks_real_paths compared the raw str(path) with the guard's
  normcased (lower-case) paths; the guard itself recorded and blocked both paths correctly.
  Landing fix: those two asserts now normcase the expected path (test-only, as the scandir
  control already does). Not re-reviewed by a verifier tier.
- After the fix: 16 passed, 1 skipped (symlink control: no symlink privilege, as predicted
  above); test_loc_rail_scope.py 1 passed.
- Real ledger proof: sha256 of the main checkout's data/frontend/clv_ledger.jsonl was
  f492d8fea427ac0e6ea2dada4b8a6dbfe3e092e81579305419b11f64f432c521 before the first run and
  after both runs (size and mtime unchanged too).
- contract_preflight: vocab FAIL on test_run_governance.py is PRE-EXISTING (the same hits on
  master's copy; the file is the honesty-gate test and carries the banned words as fixtures);
  the other three paths: zero FAIL lines. Landed by hand, not by land_row.sh, for that reason
  and because the governance file must not run from the main checkout.
