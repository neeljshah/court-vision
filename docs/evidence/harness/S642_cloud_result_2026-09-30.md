# S642 cloud result -- 2026-09-30 (desk-improve routine, Opus, Ubuntu cloud clone)

Row: S642 (issue ledger replay: one refused issue event dropped its whole scan batch, so one bad
persisted row poisoned every later batch). Branch: `cloud/S642-2026-09-30` from trunk a60dcb09a.
Spec: docs/evidence/harness/S642_spec_2026-09-30.md (body + AMENDMENT 1 critic + AMENDMENT 2 builder).
Register row and DESK_STATE.md NOT edited on this branch (routine override 3); status lives here.
Operations language only.

## Verdicts

| Tier | Agent | Verdict |
|---|---|---|
| Pre-build critique (astra) | independent Opus sub-agent | REVISE, 11 items -> all folded as AMENDMENT 1 |
| CONTRACT (A, B1-B10, Q1-Q8 + spec) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS |
| ADVERSARIAL (probes, fuzz, mutants) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS |

Corrections applied (no re-verify needed: tests-only additions plus this memo):
- CONTRACT 1 (A7): this memo did not exist at verification time; it now exists.
- CONTRACT 2: the 17 `test_system_fault_matrix.py` failures are NOT all `ctypes.WinDLL`: 9 `No module
  named _winapi`, 2 `ctypes.WinDLL`, 2 `KeyError: 'live_guard'`, 4 assertion-only. The FAILED set is
  identical on trunk a60dcb09a and the branch (17 failed / 25 passed each; diff clean). Pre-existing, not S642.
- ADVERSARIAL 1-2: mutants M9 (poison only the issue id) and M12 (poisoned lines not added to
  `skipped`) survived. Added C12 and C13 (x2); both mutants now turn red (M9: 1 red, M12: 2 red).

## Before / after (recover() 5-tuple, construct 3-batch ledger; A = ram_low/a, B = ram_low/b)

| Ledger | trunk a60dcb09a | branch |
|---|---|---|
| B refused (row "S60") in batch 2 and 3 | A count 1, B count 1, last = batch 1, bad 6 | A count 3, B count 1, last = batch 3, bad 2 |
| B refused in batch 2 only | A 3, B 3, last = batch 3, bad 3 | A 3, B 3, last = batch 3, bad 1 |

Both recomputed independently by the CONTRACT tier with its own script (A2).

## What changed

`scripts/platformkit/ops/paper_desk_issue_ledger.py` recover() only (257 -> 270 lines):
- a content failure (event name, validate_issue, id mismatch, Key/TypeError) is skipped and counted
  in bad once; it poisons its str event id and str issue id for the rest of that batch (earlier
  lines of that id are moved into bad too), so no intermediate snapshot is folded;
- structural failures (seq/batch clock) still drop the whole batch; torn, wrong-size, clock and
  txn-change drops count every unfolded line exactly once (subtract `skipped`);
- a batch with count > 0 and no foldable line drops exactly as before (keeps the existing
  `test_damaged_schema_batch_refused` contract, AMENDMENT 2).
New test: `tests/platformkit/ops/test_paper_desk_issue_ledger_s642.py` (22 cases, CONSTRUCT).

Readers whose output changes (intended, A1.7): `paper_desk_issues.py` scan() diagnostic
`ledger_bad_lines` (:56) and the stale_clock print (:204) now report per-line counts; `last`
advances on batches that used to drop, so the stale_clock gates (:203, :213) can refuse a
--write the old code accepted when now lies between the old and new `last`.

## Tests (one file per process, `python3 -m pytest tests/platformkit/ops/<file> -q`, branch)

| File | Result |
|---|---|
| test_paper_desk_issue_ledger_s642.py | 22 passed (trunk code: 12 of the first 19 fail) |
| test_paper_desk_issue_ledger_fix.py | 10 passed |
| test_paper_desk_issue_link_s605.py | 29 passed |
| test_paper_desk_issues.py | 61 passed |
| test_paper_desk_issues_cli.py | 40 passed |
| test_paper_desk_issue_fix2.py | 24 passed |
| test_paper_desk_issue_fix3.py | 22 passed |
| test_paper_desk_issue_cli_fix.py | 21 passed |
| test_paper_desk_issue_tick.py | 40 passed |
| test_paper_desk_issue_supervisor.py | 58 passed |
| test_paper_desk_issue_offday.py | 63 passed |
| test_loc_rail_scope.py | 1 passed (CONTRACT tier) |
| test_system_fault_matrix.py | 17 failed / 25 passed, identical set on trunk (Windows-only, see above) |

Mutation: 16 mutants by the ADVERSARIAL tier. 13 killed, 2 survived and are now killed by
C12 and C13, and M15 is equivalent (txn=None forces the reset). Fuzz: seed 642 x 5000 and seed
20260930 x 3000 against an independent reference model, 0 violations and 0 uncaught exceptions.
The CONTRACT tier ran 4000 more randomised ledgers: 0 mismatches on the branch, 2044 on trunk.

## NOT VERIFIED

- The read-only probe on a COPY of the real ledger (`data/cache/paper_desk/issues/issues.jsonl`)
  is not verified: the cloud clone has no data/. A laptop session should run recover() on a copy
  before and after and confirm the 5-tuple is identical today (no refused lines expected).
- The Windows tick / supervisor paths that call the scanner are not verified here (WINDOWS).
- `test_system_fault_matrix.py` cannot go green on Ubuntu, so the fault-matrix ledger cases
  (tick2_b torn/garbage/duplicate) are only covered by reading: they use structural variants and
  a `>= 1` check, so they are unaffected.

PORTABLE: yes (code and tests); landing by a laptop session.

## NEW GAP candidates (for the orchestrator; ids are not allocated here)

- recover(): a deeply nested JSON line (about 100000 `[`) raises an uncaught RecursionError that
  aborts the whole replay. Trunk has the same behaviour, so this is not caused by S642.
- Coverage only: C3 has no case for an event missing its `id` or `issue` key. It takes the same
  except path and no fault was found.

## Windows landing re-verify (laptop, Py3.10.20, CLOUD-LANDER, 2026-09-30)
- Worktree nba-harness-clS642 = master da7737089 + this branch's diff (the ledger module had not
  moved on master since a60dcb09a). All twelve ops files above plus test_loc_rail_scope.py run
  one per process: every count matches the table above, and test_system_fault_matrix.py is
  GREEN on Windows (42 passed), so the fault-matrix NOT VERIFIED item is cleared.
- Real-ledger copy probe (clears the first NOT VERIFIED item): the real issues.jsonl
  (182 lines, sha256 7f2c9c8c...) was copied to a scratchpad and recover() run on the COPY with
  master's module and with this branch's module, at now = wall clock and at 2100-01-01. Both
  5-tuples are IDENTICAL (32 issues, same state hash, seq 182, same last, bad 0, future 0);
  the original file's sha256 was unchanged afterwards. As expected: no refused lines today.
- Adoption: the 30-minute tick reads this module fresh from master at its next run; with
  bad 0 today, its output is unchanged.
- The tick / supervisor call paths themselves were not run (no tick was started).
