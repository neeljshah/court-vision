GAP G47 | sport all | worktree a9 | log cx_g47_contract_rejection_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the NEW A7 clause;
self-check every line of section B before you report. DIAGNOSIS FIRST. Do not "fix" the contract.
PREMISE (step 0, reproduce it): 119 of 187 pod harness reports (63.6 pct) fail on
`coordinate_contract` and NOTHING else -- not one of them carries a second failure head. By sport:
baseball 66/93, football 30/42, soccer 15/25, basketball 8/10. Those clips were never scored for
tracking QUALITY at all: the contract rejected them before coverage, oob, jump or ball_valid could
say anything about them.
IMPORTANT -- the reports live on the POD, not in your worktree. A lane earlier today declared a
premise falsified after searching locally and finding a small unrepresentative subset. Measured on
the pod 2026-09-02: 201 reports carry `jump_p95`. Read the pod (READ-ONLY) for every denominator,
state the glob you counted over, and report what you actually find rather than inheriting 187.
LIMIT (step 1): a contract rejection and a quality failure are DIFFERENT verdicts, and today they
are reported as one. That makes the program's own headline misleading in both directions: it looks
like tracking quality is failing for 5 of 8 sports when in fact quality was never measured there,
and a genuine quality problem hiding behind a contract rejection is invisible.
MEASURE (step 2), and this is the whole deliverable:
  (a) For each of the 119, extract the SPECIFIC contract failure reason string, not just the head.
      Group the reasons into causes and report counts per cause per sport, with a stated
      denominator for each. If a reason string is uninformative, say so -- that is itself a finding
      about the contract's diagnostics.
  (b) For each cause, say whether it is (i) a producer defect (the adapter emits rows that do not
      declare their coordinate space, or declare it wrongly), (ii) a legitimate rejection (the rows
      really are unusable), or (iii) a contract defect (the rows are fine and the check is wrong).
      Justify each assignment with a concrete row example, quoted.
  (c) State how many of the 119 would be SCORABLE if their single named cause were fixed -- that
      is the number that says whether this row is worth acting on, and it is the point of the
      exercise.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the cause distribution over contract-only rejections, per sport
  before        = 119 of 187 rejected on coordinate_contract with no cause breakdown at all
  bar           = THERE IS NO PASS BAR. This row succeeds by producing an exhaustive, reproducible
                  cause breakdown with denominators. "Most of them are legitimate rejections" is a
                  perfectly good answer and would close the row.
  n             = all contract-only rejections you find; none sampled, none skipped
  eye check     = for any cause you assign to (iii) contract defect, you MUST show the rows and
                  argue why they are fine. Asserting the contract is wrong without showing the data
                  is exactly the error this program keeps catching.
  must not move = the coordinate contract itself, every harness threshold, and every verdict. This
                  row changes NOTHING in code. If a fix is warranted, name it and let the
                  orchestrator allocate an id -- lanes never invent gap ids.
NON-TAUTOLOGY: do not count a cause by grepping for the string you expect. Enumerate the distinct
reason strings first, print the full distinct list with counts, and THEN group. A grep for an
expected cause finds only what you already believed (B1).
REPORTING CONSEQUENCE, state it in one sentence at the top of the memo: whether the program's
"zero pass" headline may still be quoted as a tracking-quality statement, and for which sports it
may not.
DURABILITY (A7): copy the extracted reason table under docs/evidence/ before you report. Three
lanes today were blocked by evidence that existed only in /tmp or only on the pod.
EVIDENCE: docs/evidence/tracking/g47_contract_rejection_census_2026-09-0X.md with the reproduced
counts, the distinct reason list, the cause grouping per sport with denominators, the
would-be-scorable number, the quoted row examples, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. No scp, no deploy, no daemon restart, never kill anything -- the daemon and a live
tennis measurement are running.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a9,
no push. Report the sha.
SHARED MODULE: none, because this row changes no code. If you find yourself editing
tracking_harness.py or the contract, STOP -- you have left the scope of this row.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
