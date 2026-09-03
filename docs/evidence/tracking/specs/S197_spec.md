GAP S197 | sport all | worktree main | log cx_s197_ledger_sha_annotate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S191 (closed at limit) shipped docs/evidence/harness/ledger_sha_trace_2026-09-04.md + the audit utility
that flags every RESULTS_LEDGER data line with no token resolving to a commit (git cat-file) and no
`uncommitted:` token: 66 of 390 lines. Lanes may never edit the ledgers, so the annotation is DELEGATED to this
main-repo lane by the orchestrator: you may edit docs/evidence/RESULTS_LEDGER_SYSTEM.md ONLY by APPENDING a
` | landed:<sha>` token (or ` | uncommitted:<reason>`) to the END of each flagged line; no other character of any
line may change; never reorder, delete or rewrite lines; never touch docs/evidence/HARNESS_GAPS_2026-09-03.md;
NEVER run git add / commit / push (the orchestrator commits by pathspec); never write under the data directory.
PREMISE (step 0): re-run the S191 utility (its command is in the S191 memo) and confirm the 66/390 count and the
exact line numbers today (master may have gained lines since; state the denominator reached).
LIMIT (step 1): a line whose landing commit cannot be found by `git log -S"<distinctive phrase>" --oneline` over
the line's own text, nor by its S-id in a commit subject (`git log --oneline --grep="<SID>"`), gets
` | uncommitted:no landing commit found (S197)` -- an honest label, never a guessed sha.
CHANGE (step 2): for each flagged line find the landing commit (prefer the commit whose subject carries the
line's S-id and verdict word; else git log -S on a distinctive 40-char phrase of the line) and append the token;
re-run the utility; write the memo docs/evidence/harness/S197_ledger_sha_annotate_2026-09-04.md with a table
(line no, S-id, token appended, how found) and the before/after counts.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = untraceable data lines / data lines, by the S191 utility
  before        = 66 / 390 (re-measured today)
  bar           = 0 untraceable: every flagged line carries either a resolvable landed:<sha> (git cat-file -e
                  passes and the commit touches the ledger or the row's files) or an honest uncommitted: label;
                  0 lines otherwise changed (a diff of the ledger shows only appended tokens)
  n             = the flagged-line count (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the utility and spot-checks 8 tokens
  must not move = every other character of the ledger, the register, the FWER ledger, every threshold
NON-TAUTOLOGY: an `uncommitted:` label counts only when both lookups failed; the memo lists each such line.
EVIDENCE: the memo + the utility's after-run output. ASCII only. Calibration language only.
TEST: run only the S191 utility's own test file (named in the S191 memo) if one exists.
REPORT: print before/after counts and the number of uncommitted: labels. NO COMMIT. NEVER PARK.
