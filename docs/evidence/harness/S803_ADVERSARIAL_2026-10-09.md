# S803 adversarial verifier (tier 2) -- 2026-10-09 (PAPER ONLY)

## Round 1 on 312ebe19a: REJECT
18 mutants: 13 killed, 3 non-equivalent survivors, 2 equivalent.
- M2 (success filter dropped): survived. No test had a refusal key equal to a success label.
- M15 (capture not P1): survived. No capture-step row in any test.
- M18 (step guard dropped): survived. No test had an empty or non-str step.
- M16 (PASS-close for a non-open issue): equivalent. The ledger ignores a PASS for a non-open issue.
- M17 (malformed key falls through): equivalent. "" is benign.

Real defects:
1. paper_desk_limits.bound_row compacts any journal row over 4 KiB to refusals {journal_row_externalized: 1}. That hid the real keys and opened noise P1 issues on real nights.
2. Unknown step families used the tick rules, while classification() calls them attention.

Contract tier on 312ebe19a: ACCEPT (V1-V8, premise reproduced).

## Fix round 1 = c2ccdc79b
- Externalized rows are read through their detail file. A missing or unreadable detail keeps the key, failing closed.
- An unknown family has no benign keys.
- Two new tests kill M2, M15 and M18 and cover the detail read.

## Round 2 on c2ccdc79b: ACCEPT
| id | mutant | result |
|---|---|---|
| M1 | benign filter dropped | killed |
| M2 | success filter dropped | killed |
| M3 | future-row skip removed | killed |
| M4 | latest hit max to min | killed |
| M5 | PASS-close loop disabled | killed |
| M6 / M7 | malformed counters dropped | killed |
| M8 | subject separator / to : | killed (6 tests) |
| M9 | owner map emptied | killed |
| M10 | severity always P2 | killed |
| M11 | today's journal only | killed |
| M12 | guard hook removed | killed (6 tests) |
| M15 | capture not P1 | killed |
| M18 | step guard dropped | killed |
| a | detail read dropped | killed |
| b / b2 | exact-equality condition removed or loosened | equivalent |
| c | unreadable detail drops the row | killed |
| d | unknown-family branch dropped | killed |
| e | detail path without the CACHE prefix | killed |

b and b2 are equivalent because bound_row is the only writer of detail_path, and it always pairs detail_path with exactly that refusals dict.

Advisory, not blocking:
- D1: detail_path is not confined to journal_details/, and detail_sha256 is not checked.
- D2: a detail whose refusals is a list or null is counted and skipped, rather than keeping the externalized key.

The final git status in the worktree was clean. Contract tier on c2ccdc79b: ACCEPT, V1-V10. V10 was checked against the real 10-05 and 10-06 externalized rows.
