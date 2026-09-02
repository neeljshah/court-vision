GAP G55 | sport all | worktree a4 | log cx_g55_timeout_budget
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. MEASURE FIRST. Do NOT simply raise the number.
PREMISE (step 0, reproduce it): the daemon job timeout is set BELOW the time a real tennis run
needs. A 2700 s budget landed 2026-09-01 09:49 UTC. The daemon ledger shows tennis_06 through
tennis_09 each killed TWICE at about 2700 s with rows=0, while every healthy tennis run took
4,827-8,773 s. No healthy tennis run would survive the current 2700 s budget, nor the later
3600 s one. Reproduce this from the pod ledger yourself (the daemon ledger jsonl under /workspace)
and print the killed rows and the healthy run durations you found. If the ledger path in this spec
is wrong, FIND it and say where it actually is -- a previous lane reported the named path absent
and then stopped, which wasted the run.
LIMIT (step 1): a timeout kill currently leaves behind a thin or empty table that is
indistinguishable from an honest empty result. That is why this interacts with G50 (a tiny table
still reports coverage 1.0) and G42 (a rows=0 table looks like a tracking failure rather than a
scheduling one). The limit is that the ledger cannot currently express "this run was killed".
MEASURE (step 2), in this order and do not skip to the fix:
  (a) Report the DISTRIBUTION of completed run times per sport, with n, median, p95 and max, and
      alongside each run its decoded frames and source resolution (the G56 denominators are now in
      the ledger -- use them). A duration without a denominator is not interpretable.
  (b) Report the relationship between run time and clip length or decoded frames. If run time is
      roughly linear in decoded frames, say so with the fitted slope AND state plainly that a
      per-clip budget derived from frames is preferable to one global constant.
  (c) Only then PROPOSE a budget, derived from the measured distribution, and state what fraction
      of historical healthy runs it would have killed. Proposing is where you stop.
CHANGE (step 3), ADDITIVE ONLY and strictly limited: make a timeout kill write an explicit
TIMEOUT verdict into the ledger row, so a killed run is never again mistaken for an empty result.
Do NOT change the timeout value itself in this row -- that is a threshold change and it needs
adjudication. Write the proposed value in the memo, not in the code.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the fraction of killed runs that are identifiable AS killed from the ledger alone
  before        = 0.0 (a killed run and an honest empty run are byte-indistinguishable)
  bar           = 1.0 on newly written rows, with every existing ledger field unchanged in name and
                  meaning, AND the measured duration distribution reported per sport with n
  n             = every run in the ledger; state the count. Do not sample a ledger you can read
                  in full.
  eye check     = n/a (a scheduling and schema question). Reproduction = the killed rows and the
                  duration table printed in the memo.
  must not move = the timeout value, every harness threshold, every existing ledger field, and the
                  daemon done-definition landed as G15b
NON-TAUTOLOGY: do not measure "healthy run duration" over only the runs that completed under the
CURRENT budget -- that is conditioning on the outcome you are trying to characterise and it will
make any budget look adequate by construction (contract B1). Use the runs from BEFORE the 2700 s
budget landed, and say explicitly which window you drew from.
EVIDENCE: docs/evidence/tracking/g55_timeout_budget_2026-09-0X.md with the reproduced killed rows,
the per-sport duration distribution with denominators, the frames-versus-time relationship, the
proposed budget with its would-have-killed fraction, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ the ledger. No scp, no deploy, no daemon restart, never kill anything -- the daemon and
a live tennis measurement are running.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token. Take it in docs/evidence/SHARED_MODULE_TOKEN.md
before editing (edit that file alone, commit it alone, push -- the push is the lock) and RELEASE it
by pushing the release too. A previous lane pushed its acquire and left the release unpushed, which
looks to everyone else like the token is still held.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
