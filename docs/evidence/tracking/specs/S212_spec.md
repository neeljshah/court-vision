GAP S212 | sport all | worktree aXX | log cx_s212_regime_key_clean_rerun
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S200 (regime-key OOF leak) CLOSED AT LIMIT 2026-09-04: attempt 2 (a13 9d730e518) built date-group
train-only keys, but the verifier's CLEAN rerun did not reproduce the archive: clean after-ECE nba 0.022205 /
mlb 0.009672 / soccer 0.009192 / tennis 0.016928 vs archived 0.019514 / 0.009282 / 0.009538 / 0.016937
(S200_VERIFY_2026-09-03.md:5). Named causes: a mutable cache at s200_regime_key_oof.py:145 makes results depend
on call order; :209-216 copies reference rows instead of re-running the default path. The published leaked-key
table (nba 0.024843, mlb 0.008077, soccer 0.009302, tennis 0.008403; S05 report) stays PROVISIONAL until this row.
PREMISE (step 0): start from master's landed S200 evidence + the a13 attempt-2 module (cherry-pick 9d730e518 or
copy its files); reproduce the verifier's clean numbers above by running the clean path FIRST in a fresh process.
LIMIT (step 1): if clean and archive still differ after the two corrections, the difference is the finding: name
the line and the mechanism; publish the clean numbers only.
CHANGE (step 2): apply exactly the verifier's two CORRECTIONS: (a) :145 cache an immutable copy and mutate a fresh
list, with a test proving clean-vs-prior-arm call-order invariance (same ECE to 1e-12 in both orders); (b)
:209-216 re-run the default path instead of copying reference rows; regenerate every evidence artifact from a
fresh process; publish ONE current result section (drop the obsolete attempt-1 table and the positional-date
note). Module counts stay within tests/platformkit/test_loc_rail_scope.py (calibration_report.py must not grow;
new helpers <= 300 lines). Never write under data/; never touch the register or ledger; one store at a time.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = after-ECE per sport under date-group train-only regime keys, clean fresh-process run
  before        = archive (leaked key) nba 0.024843 / mlb 0.008077 / soccer 0.009302 / tennis 0.008403
  bar           = the verifier's fresh-process rerun reproduces the memo's four ECE values to <= 1e-9; the
                  call-order test passes in both orders; 1,814 / 39,162 / 25,834 / 41,886 rows, 0 dropped;
                  the memo has exactly one result section; the LOC rail passes
  n             = 4 sports (CONSTRUCT), rows as above
  eye check     = n/a (S-row); reproduction = the verifier re-runs the clean path in a fresh process and diffs
  must not move = the leaked-key archive values (kept as the BEFORE row), every threshold, the FWER ledger
NON-TAUTOLOGY: the memo must show the clean numbers whether they improve or worsen any sport; no sport dropped.
EVIDENCE: docs/evidence/harness/S212_regime_key_clean_rerun_2026-09-04.md + regenerated JSON. ASCII only.
Calibration language only (no dollar, ROI or edge words).
TEST: the row's call-order test file and tests/platformkit/test_loc_rail_scope.py, one at a time.
REPORT: the four clean ECE values with before values, the test lines, SHA. Commit by pathspec, no push. NEVER PARK.
