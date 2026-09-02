GAP G73 | sport all | worktree a5 | log cx_g73_job_budget
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This IMPLEMENTS an already-adjudicated decision. Implement it;
do not re-open it and do not extend it.
THE ADJUDICATION (orchestrator, 2026-09-02, recorded in the G55 register row): raise the global job
budget in track_daemon.py to **12,000 s**. Derivation, so the number is not a magic constant:
roughly 1.37x the largest observed healthy completion of 8,773 s, taken from the PRE-BUDGET window
of the ledger (the rows before the first 2,700 s kill), NOT from runs that survived the current
budget -- fitting to survivors would be circular, which is why the G55 lane correctly refused to
propose a number at all.
WHY: the current 3,600 s budget sits BELOW the p95 of four sports and below tennis's MEDIAN of
7,513.5 s. Measured pre-budget: tennis n=6 median 7,513.5 / p95 8,723.5 / max 8,773; football n=33
p95 6,023 / max 6,581; soccer n=15 p95 4,806 / max 5,365; baseball n=63 p95 4,011 / max 5,481. So
it is not a safety valve, it is a systematic killer -- it is why G42 saw tennis collapse to rows=0,
and why G71's rejected-code window contained no tennis tables at all. Read
docs/evidence/tracking/g55_timeout_budget_2026-09-02.md first.
THE HEADROOM IS DELIBERATE and you should say so in the memo: the pre-budget window contains only
runs that COMPLETED, so 8,773 s is a LOWER BOUND on legitimate duration, not a ceiling.
IMPLEMENT:
  (a) Change the budget to 12,000 s in track_daemon.py, as a NAMED CONSTANT with a comment giving
      its provenance in one sentence and stating that it is TEMPORARY -- to be replaced by a
      per-clip frame-derived budget once G56's denominator-bearing ledger rows accumulate. A magic
      number with no stated provenance is exactly how the 2,700 s budget survived unexamined.
  (b) Nothing else changes. This is a SCHEDULING budget, not a quality gate: no harness threshold
      moves, no report field changes, no verdict changes.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the budget value, and the count of historical ledger rows that would be killed
                  by it
  before        = 3,600 s (and 2,700 s before that), which would kill every healthy tennis run
  bar           = the constant is 12,000 s with its provenance in a comment; the G55 TIMEOUT
                  verdict still fires when a job exceeds it (prove with a test); NO harness
                  threshold, report field or verdict changes; and you report how many of the 397
                  historical rows would have been killed at 12,000 s -- the answer should be zero
                  for healthy completions, and if it is not, report that rather than adjusting
  n             = all 397 ledger rows for the would-have-been-killed count
  eye check     = n/a (a scheduling constant). Reproduction = the before/after value and the
                  killed-count, both printed in the memo.
  must not move = every harness threshold, every report field, every verdict, and the G15b daemon
                  done-definition
NON-TAUTOLOGY: do not validate the new budget by checking that runs which completed under it
complete under it. The check is against the PRE-BUDGET duration distribution, which is the only
sample not conditioned on the budget.
DURABILITY (A7): commit the killed-count computation under docs/evidence/tracking/g73_job_budget/
BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g73_job_budget_2026-09-0X.md with the before/after value, the
provenance sentence, the would-have-been-killed count over all 397 rows, the test output, and a
NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy, no scp, no daemon restart, never kill anything -- another session has live
processes there and the daemon is 24/7. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push except the token. Report the sha.
SHARED MODULE: track_daemon.py is under the token. Take it in
docs/evidence/SHARED_MODULE_TOKEN.md (edit that file alone, commit it alone, push -- the push is
the lock) and PUSH THE RELEASE when you report. It is currently free.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
