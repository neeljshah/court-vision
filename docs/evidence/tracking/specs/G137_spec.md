GAP G137 | sport basketball | worktree a3 | log cx_g137_qualifying_frame_scale
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This gives an underpowered test the sample size it needed. Read
docs/evidence/tracking/g135_end_to_end_solve_2026-09-02.md and
g134_grouping_stability_2026-09-02.md first.
WHERE THIS SITS. G134 took basketball paint-line recall from 25/68 = 36.76 pct to 30/68 = 44.12 pct
at 25/25 baseline-match survival, by stabilising the grouping stage that four earlier rows had been
unknowingly fighting. G135 then looked for frames where all four paint roles are detected, so a
homography could be solved, and found 0 of 30. That is NOT a refutation: at 44.12 pct the implied
all-four co-occurrence is 3.79 pct, so 30 frames predict 1.14 and P(observe 0) = 0.321. The frozen
30-frame sample is simply too small to test solvability.
THE TASK: count qualifying frames at a sample size that can answer the question.
  (a) Draw a SEEDED sample of >= 200 frames across all basketball pod clips. State the seed and
      per-clip counts. Do not head-slice. You MAY include the 30 frozen G84 frames but report them
      separately, since they are a PAINT_SOLVABLE-selected slice and are positively biased.
  (b) Run detection with G134's stable grouping plus union, and count frames where all four paint
      ROLES are detected and role-assigned. Report the qualifying rate with a Wilson 95 pct
      interval, and compare it against the 3.79 pct the independence model predicts.
  (c) TEST THE INDEPENDENCE ASSUMPTION, because it is load-bearing and probably wrong. The four
      lines are likely POSITIVELY correlated: a frame showing the paint well shows all four, one
      that does not shows none. Report the observed joint distribution -- how many frames have 0, 1,
      2, 3 and 4 roles detected. If that distribution is bimodal rather than binomial, say so; it
      would mean co-occurrence is HIGHER than 3.79 pct and solvable frames are commoner than the
      independent model predicts.
  (d) NO HAND-LABELLING IS REQUIRED FOR THE COUNT and you should not add any. A detection count
      needs no ground truth. But state explicitly that a frame counted here is one where the
      detector CLAIMS four roles, not one where four roles are verified correct. Those are
      different, and the second is what a solve actually needs.
  (e) If qualifying frames exist, hand at least 5 forward for a solve attempt but do NOT solve here.
      G135 already defines that measurement, including external validation against a real-world
      distance not used in the solve. Keeping the count and the solve in separate rows is what keeps
      the count honest.
DO NOT tune anything, change any detector or grouping parameter, modify line_calibration.py, touch
the frozen protocol, declare court_feet, or change any threshold.
ACCEPTANCE RULE:
  metric        = qualifying all-four-role frame rate over >= 200 seeded frames, Wilson 95 pct
                  interval, plus the 0/1/2/3/4-role joint distribution
  before        = 0 of 30 qualifying, with P(0) = 0.321 under a 3.79 pct independent model
  bar           = NO pass bar. Success is the count at adequate n with its interval, and the
                  independence assumption tested against the observed joint distribution. A
                  qualifying rate near zero at n >= 200 WOULD be decisive and is a full success, as
                  it would say the recall gain does not convert into solvable frames.
  n             = >= 200 seeded frames; state the seed, the per-clip counts, and the G84-overlap
                  count separately
  eye check     = open at least 5 qualifying frames and confirm the four claimed roles look like the
                  real paint lines. A count of frames where the detector claims four WRONG lines is
                  worse than useless, because it would send a solve row chasing noise.
  must not move = every detector and grouping parameter, line_calibration.py, the frozen protocol at
                  98b7d6974, the G84 sample and seed, every harness threshold, and the coordinate
                  contract
EVIDENCE: docs/evidence/tracking/g137_qualifying_frame_scale_2026-09-0X.md with the seed, the
qualifying rate and interval, the joint distribution, the independence assessment, the eye-checked
frames, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g137_scale/ BEFORE reporting
(A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
