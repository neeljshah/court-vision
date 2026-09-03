GAP G144 | sport tennis | worktree a6 | log cx_g144_tennis_quality_ceiling
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. Tennis is the only sport that works; this asks how good it actually is.
CONTEXT. Five reachability censuses and eleven basketball rows established that broadcast-footage
calibration is unreachable for soccer (>=4 landmarks in 0/100 frames), football (a third independent
direction in 0/60) and baseball (1/80 = 1.3 pct), and unrecoverable for basketball -- geometry
visible in 46.2 pct of frames, but the line route makes 1 of 84 roles available and a naive corner
detector scores recall 0/68. Tennis is the sole sport reaching court_feet (G47: 0 of 15 contract
rejections), and G142 found NO steerable acquisition driver, so volume is the only lever.
So tennis is where quality actually matters, and nobody has asked how good it is.
THE QUESTION: across every tennis table that REACHES the quality gate, what are the numbers, which
gates do they fail, and what is the realistic ceiling?
  (a) For every gate-eligible tennis table report the full metric row: coverage, det_per_frame,
      median_track_len, oob_pct, ball_valid_pct, zero_step_share, the jump statistic and the
      verdict. State how many pass, how many fail, and which gate each failure lands on.
  (b) RANK the failing gates by how many tables they block. That ranking is the deliverable -- it
      says what to fix first for the one sport that can be fixed at all.
  (c) For the most common failing gate, take 3 tables that fail it and say in one sentence each WHY,
      from the data and from a rendered frame where a render helps. A gate failure with no
      explanation is not actionable.
  (d) STATE THE CEILING HONESTLY: if every fixable failure were fixed, how many tennis tables would
      pass? Note that G118 closed the tennis ball-labelling branch -- neither a written criterion
      (G92/G98: 0 of 109 labels changed) nor temporal context (G102/G118: lower bound 68.1 pct did
      not clear the 75.0 pct bar) moved agreement -- so ball_valid failures are NOT fixable by more
      labelling and must not be counted as if they were.
DO NOT change any threshold, verdict, gate, or the coordinate contract. This row measures and ranks;
moving a bar is a separate adjudication.
ACCEPTANCE RULE:
  metric        = per-table metric rows for gate-eligible tennis tables, plus a ranking of failing
                  gates by tables blocked
  before        = 8 gate-eligible tables system-wide; their tennis quality numbers never collated
  bar           = NO pass bar. Success is the collated table, the ranking, three explained failures
                  and an honest ceiling. "Most failures are not fixable" is a full success.
  n             = every gate-eligible tennis table at your census moment; state it
  eye check     = required for the three explained failures where a frame clarifies the cause
  must not move = every threshold, every verdict, the coordinate contract, and the G118 closure
EVIDENCE: docs/evidence/tracking/g144_tennis_quality_ceiling_2026-09-0X.md with the table, the
ranking, the three explanations, the ceiling, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g144_ceiling/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon is live and seven bridge lanes run under
scripts/platformkit/bridge_keeper.
COMMIT: explicit pathspec only, in a6, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
