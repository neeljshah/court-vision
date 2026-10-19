GAP S727 | ops (registry E health reader: produced-receipt shape) | worktree nba-harness-s727 | builder Opus (row agent)
# A produced arm-E receipt (state produced, complete true, no status key) reads PASS in the issue scan instead of being flagged unreadable
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q (S-row). Citations read on master 57fe60eaa. Operations language only; paper only.
WHERE THIS ROW RUNS: construct tests on tmp_path plus one read-only probe of the main checkout's arm-E receipts; nothing is written outside the worktree.

BEFORE (measured):
- scripts/platformkit/ops/paper_desk_issue_checks.py:75-77 (master) `if not isinstance(record.get("status"), str): _bad(ctx, path, "status missing or invalid"); return "UNKNOWN"`.
- Writer scripts/platformkit/execution/registry_scorer_e_night.py:189 `receipt = dict(schema='s476.1', state='produced', ...` and :197 `complete=counts['complete']`; no status key on the produced path. :93 sets `complete=True`; :97 and :114 set it False when a window schedule is absent or invalid.
- Same writer :249 `dict(schema='s476.1', state='config_not_effective', status='REFUSED', rows=[], ...` is the only status the writer emits.
- Real receipts (main checkout, read-only): 09-26 and 09-29 carry status REFUSED, state config_not_effective; 09-30 and 10-02 carry state produced, complete true (bool), no status. 10-02 is 28879 bytes; 09-30 is over the 2 MiB read cap (row S718, not this row).
- Effect: issue 3469576400d24953 (scan_input_unreadable, registry_e/2026-10-02.json: status missing or invalid) and arm_refused e:2026-10-02 reads UNKNOWN.

CHANGE (OWNED: scripts/platformkit/ops/paper_desk_issue_checks.py `_registry` only, file stays under 300 lines; NEW tests/platformkit/ops/test_paper_desk_issue_registry_shape.py):
1. A record with NO status key and state == "produced": complete is True (bool) reads PASS; anything else flags bad with "produced receipt complete is not true" and reads UNKNOWN.
2. Every other record goes through the existing status path unchanged.
Decision on incomplete produced receipts: NOT a pass. complete false means a window schedule was absent or invalid (:97, :114), so the receipt is not evidence that arm E covered the whole window; it is flagged with its own message and reads UNKNOWN.

MUST NOT MOVE: Context.read and the 2 MiB cap (paper_desk_issue_common.py), every other function in paper_desk_issue_checks.py, the REFUSED / config_not_effective policy reread, the arm_refused emit in _night, the writer.

CASES (through check() on tmp_path, as test_paper_desk_issue_checks.py builds its Context):
- C1 real-shape produced receipt (top-level keys and value types of the real 10-02 receipt, rows empty) reads PASS, no unreadable flag.
- C2 state produced with complete false, absent, the string "true", or the integer one: UNKNOWN plus the new flag.
- C3 neither shape (no status and no state; state other with complete true; non-string status): UNKNOWN plus "status missing or invalid".
- C4 REFUSED config_not_effective before the policy effective date reads PASS; REFUSED for another state reads FAIL; status OK reads PASS; status REFUSED with state produced reads FAIL (status wins).
- C5 every existing test file that imports the issue scan passes unchanged.

ACCEPTANCE RULE: C1 to C5 pass per file; with the edit reverted C1 and C2 fail; the read-only probe reads 10-02 PASS with no flag and 09-29 PASS (unchanged).

DISCLOSURES: a produced receipt that also carries a status key takes the status path (the writer never emits both). The S544 must-not-move fixture pins this file's hash, but only at S544 landing (skipped otherwise) and is already stale on master.

NOT VERIFIED: the issue closing on the next scan with --write (no --write was run); the 09-30 receipt (unreadable until S718).

AMENDMENT 1 (2026-10-03; round 1 outcome, adjudication, corrections 1b)
(a) Round 1 on a7ec4c7f8: contract tier ACCEPT WITH CORRECTIONS; adversarial tier ACCEPT WITH CORRECTIONS (fourteen mutants, twelve killed, two survived: case-insensitive state, and status-is-None in place of the status-key test); no blocking finding. Dispatcher adjudication: the module edit stays exactly as it is; corrections 1b are tests, spec and memo only, with no further verifier round.
(b) Tests: C3 gains state "Produced" with complete true, and state produced with complete true and status null; both read UNKNOWN with "status missing or invalid" and kill the two survivors (power shown on the worktree module, restored after). real_shape() claims only top-level keys and types.
(c) LIFECYCLE: issue 3469576400d24953 is triaged to S727, so the first scan with the write flag after landing moves it to closed_pending_landing; it becomes closed on the first scan after the register cell reads LANDED with a sha.
(d) DISCLOSURE, noise: the caller policy looks back seven days, so one day with an absent or invalid schedule file (an off-day or a capture gap) makes the following produced receipts incomplete, and each raises its own "produced receipt complete is not true" issue. The scanner's off-day logic is not consulted by this check. This is a strict subset of what master flagged (master flagged every produced receipt). Follow-up row allocated at landing.
(e) DISCLOSURE, content: a PASS means only that arm E did not refuse and its window was complete. It does not mean the receipt holds scored ticks (the 10-02 receipt has zero games and zero scored ticks in its summary), and the check does not compare for_night with the file's day.
(f) NOT VERIFIED stays as above.
