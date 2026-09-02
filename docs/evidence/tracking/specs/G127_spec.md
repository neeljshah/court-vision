GAP G127 | sport all | worktree a5 | log cx_g127_partial_table_salvage
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This asks whether real output discarded by an obsolete threshold is worth
recovering. Read docs/evidence/tracking/g124_header_only_cause_2026-09-02.md first.
THE CORRECTION CHAIN THAT PRODUCED THIS ROW, worth following because each step narrowed the claim:
  - G100 censused the pod ledger, quoted the CURRENT code where `thin` is the non-timeout branch
    with `graded is None`, and reported 165 thin / 50 timeout / 183 tracked / 3 corrupt.
  - G105 sized the adapter-path thin population at 145,702 seconds = 40.47 job-hours and reported
    **0 confirmed recoverable**, on the basis of opened cases that were header-only.
  - G124 then found the historical rows were written under an OLDER definition, rows <
    `MIN_TRACKING_ROWS = 500`. Of 157 readable thin records: **85 recorded ZERO rows, 4 recorded 1-4
    rows, and 68 recorded 5-499 rows**, none 500 or more.
So 68 jobs produced REAL tracking output and were labelled thin purely by a threshold that no longer
exists. G105's zero-recoverable finding was true of the header-only subset it opened and is not
wrong; it simply did not describe the whole bucket. G124 was explicit that this narrows rather than
inflates the claim, and this row must keep that discipline.
THE QUESTION: are any of those 68 partial tables actually USABLE, and if so how many?
  (a) The bar is not "has rows". G80 requires **MIN_FRAMES_FOR_METRICS = 30** before any metric is
      computed at all, and a table under that returns verdict INSUFFICIENT_DATA with nulled metric
      fields. Rows are not frames -- a table with 400 rows across 8 frames is still insufficient. So
      compute FRAMES per table, not rows, and report the frame distribution across all 68.
  (b) Run the CURRENT harness over each of the 68 and report the verdict distribution: how many are
      INSUFFICIENT_DATA, how many reach a real verdict, how many are coordinate-contract rejections,
      and how many would be jump-gate eligible. That last number is the one that matters: G109
      counted only 8 eligible tables in the whole system, and G107 could not settle the jump
      statistic question because the eligible denominator was too small.
  (c) DO NOT re-run tracking and do not re-adjudicate anything into the ledger. Score the existing
      artefacts read-only and report what they would yield. Changing a stored verdict is an
      adjudication the orchestrator makes, not a lane.
  (d) STATE THE HONEST CEILING. Even if some of the 68 clear 30 frames, a 5-to-499-row table is
      short, and a short table can pass a gate for the wrong reason -- G80 exists precisely because
      degenerate tables produced plausible-looking numbers. Say clearly how many of your usable
      count are near the 30-frame floor, because those are the ones a later row should distrust.
  (e) CHECK SOURCE RETENTION for any table you call usable, using the G116 method. G116 measured
      overall retention at 73/199 = 36.68 pct. A usable table with no surviving source is a number
      nobody can re-check, and four measurements died of that today.
DO NOT change any threshold, the coordinate contract, the rung ladder, the daemon, or any stored
verdict. NEVER KILL ANYTHING ON THE POD -- the track daemon, its keeper, seven bridge lanes and
other sessions' processes are live.
ACCEPTANCE RULE:
  metric        = of the 68 partial tables, the frame distribution and the current-harness verdict
                  distribution, including how many would be jump-gate eligible
  before        = 68 tables with 5-499 rows discarded by an obsolete 500-row threshold; usability
                  never assessed
  bar           = NO pass bar. Success is all 68 scored read-only against the current harness, the
                  frame distribution reported separately from rows, and the eligible count stated.
                  "None of them clear 30 frames" is a full success and closes the question for good.
  n             = all 68; state the count you actually find, since G124 read 157 of 158 records
  eye check     = not required for the arithmetic, but OPEN at least 3 of any tables you call usable
                  and confirm the content matches the row count. G100 found three thin outputs
                  header-only by looking, and a label believed without one look is how 165 rows went
                  unexamined for weeks.
  must not move = every threshold, MIN_FRAMES_FOR_METRICS, the coordinate contract, the daemon,
                  every stored verdict, and the ledger
EVIDENCE: docs/evidence/tracking/g127_partial_table_salvage_2026-09-0X.md with the frame
distribution, the verdict distribution, the eligible count, the near-floor caveat, the source
retention check, and a NOT VERIFIED list. Commit derived tables under
docs/evidence/tracking/g127_salvage/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, strictly.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
SHARED MODULE: track_daemon.py and tracking_harness.py are under the token; READ them, do not change
them.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
