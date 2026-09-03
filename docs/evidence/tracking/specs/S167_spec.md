GAP S167 | sport all | worktree a15 | log cx_s167_connectivity_followups
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
PREMISE (step 0): the S160 table docs/evidence/CONNECTIVITY_2026-09-04.md carries two misattributed FAILs and two
scope defects (its "Corrections at landing" section names them). Measure each before changing anything:
  (a) L4 signal audit: src/prediction/bet_grades.py is gitignored (.gitignore:408) and absent in this worktree but
      present in the main repo C:/Users/neelj/nba-ai-system (read-only there). Copy that ONE file into this
      worktree at the same path (it is gitignored, so it will not be committed) and re-run the L4 command;
  (b) L8 answer layer: the tools live in scripts/platformkit/mcp_server/artifact_tools.py (harness_health
      reachable, status=no_data); locate system_health (grep the tree) and call both in process;
  (c) L9: count UNIQUE artifact paths cited in docs/PUBLIC_EVIDENCE.md, both markdown links and backticked
      paths, and check existence (state the scope rule once);
  (d) L2: the calibration scoreboard __main__ hard-codes build_calibration_scoreboard(write=True).
LIMIT (step 1): a link that still needs the pod or the ledger is NOT TESTABLE HERE with the reason.
CHANGE (step 2): (d) add an additive --no-write flag to the scoreboard CLI (default behaviour byte-identical;
with the flag it prints the same scoreboard without writing under data/) + one construct test; (a)-(c) are
re-measurements only. Append the four re-quoted rows to the CONNECTIVITY table under a dated section (never
rewrite the landed rows); state the denominator reached; assert 4 rows appended.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = follow-up rows re-quoted / 4, each with command, exit, number, verdict, denominator
  before        = L4 FAIL (misattributed), L8 FAIL (wrong path), L9 23 occurrences, L2 NOT TESTABLE
  bar           = 4/4 re-quoted; L2 measured through --no-write with the printed numbers; 0 fabricated
  n             = 4 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs L8 and L2 (--no-write) verbatim
  must not move = every threshold, the landed CONNECTIVITY rows, data/ (never written), the FWER ledger
NON-TAUTOLOGY: every one of the four is reported, pass or fail.
EVIDENCE: the appended CONNECTIVITY section + docs/evidence/harness/S167_connectivity_followups_2026-09-04.md
(before/after per item, NOT VERIFIED list). ASCII only. Calibration language only.
TEST: one new per-file test for the --no-write flag under tests/platformkit/ops/; run only it and the existing
tests/platformkit/ops/test_s160_connectivity_report.py, one file per command.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
