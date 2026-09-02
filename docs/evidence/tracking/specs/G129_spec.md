GAP G129 | sport basketball | worktree a3 | log cx_g129_why_more_candidates_loses_recall
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This chases a COUNTERINTUITIVE result that two rows produced independently. Read
docs/evidence/tracking/g120_fragment_merge_2026-09-02.md and
g123_low_contrast_lines_2026-09-02.md first.
THE ANOMALY. Two preregistered interventions were aimed at the two largest miss buckets in G115's
paint-line recall of 25/68 = 36.76 pct, and BOTH made recall worse:
  - G120, collinear fragment merging, targeting the 14 'split into fragments' misses:
    recall 36.76 -> 35.29 pct, paired precision 5.95 -> 5.49 pct.
  - G123, CLAHE contrast normalisation, targeting the 17 'low contrast' misses:
    recall 36.76 -> 33.82 pct, recovering NONE of the 17, with candidate volume UP 4.4 pct and
    implied all-four co-occurrence down from 1.83 pct to 1.31 pct.
Neither lane adjusted its rule after seeing the result, which is why both numbers can be trusted.
**BOTH INTERVENTIONS ADDED CANDIDATES AND RECALL FELL.** That should not happen. Recall counts how
many VISIBLE true lines have some candidate lying on them; adding candidates can only leave a true
line covered or newly cover it. For recall to DROP, something downstream must be losing true lines
it previously kept, because of the extra material. That mechanism is unknown and it is very likely
the real blocker on basketball calibration -- more so than either bucket the two rows attacked.
CANDIDATE MECHANISMS, and you must distinguish them rather than settle for the first that fits:
  (a) GROUPING. `candidate_line_group_details` groups segments before anything downstream sees them.
      Extra segments may pull a group's fitted direction or position off the true line, so the group
      still exists but no longer lies within the correspondence tolerance. This would show as a
      group whose endpoints moved between runs.
  (b) THE CORRESPONDENCE RULE ITSELF. G93's frozen protocol matches a candidate to a hand-marked
      line within 12 degrees, 12 px perpendicular and a 20 px endpoint extension. If matching is
      one-to-one, or greedy in some order, a spurious nearby candidate can CLAIM a true line and
      leave the real candidate unmatched. Read the frozen runner and establish whether matching is
      one-to-one or many-to-one; if it is greedy, state the ordering.
  (c) A CAP. If any stage keeps only the top-N segments or groups by score or length, extra
      candidates evict true ones. Grep for any such limit and quote it or rule it out.
  (d) NON-DETERMINISM. If the pipeline is order-dependent, the two runs may differ for reasons
      unrelated to the intervention. Re-run the BASELINE twice on the same frames and confirm you
      get 25/68 both times before attributing anything to the interventions. Do this FIRST -- if the
      baseline is not reproducible, nothing else in this row means anything.
METHOD: take the specific true lines that were matched in the G115 baseline and unmatched under G120
or G123, and trace each one through the stages. Name them by clip, frame and role. Do not reason
from aggregates; the aggregate is what is confusing, and the answer is in the individual cases.
DO NOT fix anything, do not change the frozen protocol, the detector parameters, line_calibration.py
or any threshold. This row explains; a fix is a separate row with its own preregistration.
ACCEPTANCE RULE:
  metric        = for each true line lost between baseline and intervention, the stage at which it
                  was lost, aggregated into a mechanism distribution
  before        = two interventions added candidates and reduced recall; mechanism unknown
  bar           = NO pass bar. Success is the baseline reproducibility confirmed FIRST, the lost
                  lines traced individually, and a named mechanism with per-case evidence. "The
                  pipeline is non-deterministic and both results are noise" is a full success and it
                  would invalidate two REJECTs, which is exactly the kind of thing worth finding.
  n             = every true line lost between the baseline and either intervention; state the count
  eye check     = render the lost lines with the baseline candidates and the intervention candidates
                  overlaid, side by side, for at least 5 cases. The mechanism will be visible.
  must not move = the G93/G115 frozen protocol at 98b7d6974, the G84 sample and seed, the G115
                  visibility labels, every detector parameter, line_calibration.py, and every
                  harness threshold
EVIDENCE: docs/evidence/tracking/g129_why_more_candidates_loses_recall_2026-09-0X.md with the
baseline reproducibility check FIRST, the per-line traces, the mechanism distribution, the side-by-
side renders, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g129_mechanism/ BEFORE
reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
