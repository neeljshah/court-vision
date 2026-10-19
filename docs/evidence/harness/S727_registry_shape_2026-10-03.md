# S727 registry E produced-receipt shape (2026-10-03)

## What changed
`_registry` in scripts/platformkit/ops/paper_desk_issue_checks.py now accepts the produced arm-E receipt the s476 writer emits (scripts/platformkit/execution/registry_scorer_e_night.py:189 state produced, :197 complete). A record with no status key and state produced reads PASS when complete is the boolean true; otherwise it is flagged "produced receipt complete is not true" and reads UNKNOWN. Every record with a status key takes the old path unchanged. Five lines added; the file is now under three hundred lines.

## Cases (tests/platformkit/ops/test_paper_desk_issue_registry_shape.py, twelve cases)
- Real-shape produced receipt (top-level keys and types copied from the 10-02 receipt, rows empty): PASS, no flag.
- Produced with complete false, absent, the string "true", or the integer one: UNKNOWN plus the new flag.
- Neither shape (three variants): UNKNOWN plus "status missing or invalid".
- REFUSED config_not_effective before the policy date: PASS; REFUSED other reason: FAIL; status OK: PASS; REFUSED plus state produced: FAIL.

## Power
With the master version of the module restored in the worktree, five of the twelve cases fail (the real-shape case and the four incomplete-produced cases, all reading the old "status missing or invalid"); the other seven pass on both.

## Per-file test runs (worktree, one file at a time)
The new file plus eighteen existing files that use the issue scan all pass: capture_fix fifteen, checks sixty-seven, checks_fix twenty-one, cli_fix twenty-one, fix2 twenty-four, fix3 twenty-two, ledger_fix ten, ledger_s642 twenty-two, link_s605 twenty-nine, offday sixty-three, registry_shape twelve, supervisor fifty-eight, supervisor_a2 seven, tick forty, issues sixty-one, issues_cli forty, legacy_nights twenty-eight, s521_expiry twenty-seven, schedule_ack thirty-four.

## Real-receipt probe (read-only, main checkout evidence, no --write)
| day | before | after |
|---|---|---|
| 2026-09-26 | PASS | PASS |
| 2026-09-29 | PASS | PASS |
| 2026-09-30 | UNKNOWN (unreadable, size cap, S718) | UNKNOWN (same) |
| 2026-10-02 | UNKNOWN (status missing or invalid) | PASS, no flag |

## Round 1 and corrections 1b
Contract tier and adversarial tier both ACCEPT WITH CORRECTIONS, no blocking finding; fourteen mutants, twelve killed, two survived (case-insensitive state; status-is-None in place of the status-key test). The module is unchanged by the corrections. Two cases were added to the neither-shape set (state "Produced"; state produced with status null), so the file now has fourteen cases; each survivor now fails exactly one case on the worktree module (restored after).
- Lifecycle: the issue is triaged to S727, so the first scan with the write flag after landing moves it to closed_pending_landing; it closes on the first scan after the register cell reads LANDED with a sha.
- Noise: the caller policy looks back seven days, so one off-day or capture gap with no schedule file makes the following produced receipts incomplete, each raising its own flag; off-day logic is not consulted; a strict subset of what master flagged. Follow-up row at landing.
- Content: PASS means arm E did not refuse and its window was complete, not that the receipt holds scored ticks (10-02 has zero games and zero scored ticks); for_night is not compared with the file's day.

## NOT VERIFIED
- Issue 3469576400d24953 closing on the next scan with --write (no --write was run).
- The 09-30 receipt under this check (it stays unreadable until S718).
