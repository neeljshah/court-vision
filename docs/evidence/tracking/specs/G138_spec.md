GAP G138 | sport basketball | worktree a2 | log cx_g138_paint_role_assigner
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This targets the blocker G137 just named. Read
docs/evidence/tracking/g137_qualifying_frame_scale_2026-09-02.md and
g134_grouping_stability_2026-09-02.md first.
WHAT G137 ESTABLISHED, and it invalidated a model the orchestrator was reasoning
from. Scaled to 215 scored frames across 18 clips (seed 137092026):
  - four-role detector claims **42/215 = 19.53 pct** [14.79, 25.35],
  - joint distribution **173 / 0 / 0 / 0 / 42** for 0/1/2/3/4 roles -- not ONE frame has 1, 2 or 3
    roles, so assignment is ALL-OR-NONE and structurally cannot evidence line co-occurrence,
  - and **all five** evenly spaced qualifying renders FAILED the eye check, so the frames it claims
    do not show four real paint lines.
So the chain from per-line recall to solvable frames was never valid: the orchestrator computed
all-four co-occurrence as recall^4 (1.83 pct, then 3.79 pct after G134) on an independence
assumption the assigner makes meaningless. G134's per-line recall gain (25/68 -> 30/68 at 25/25
baseline survival) is unaffected -- it was measured against hand-marked visible lines and never used
role assignment.
THE QUESTION: what does the paint role assigner actually do, and can it be made to emit a PARTIAL,
CORRECT assignment instead of an all-or-none, frequently-wrong one?
  (a) READ the assigner and quote its logic. G75 landed paint role assignment
      (g75_paint_role_assignment); find the code it added and establish exactly why the output is
      all-or-none. Quote it; do not infer from the distribution.
  (b) MEASURE ITS CORRECTNESS on the frames it claims. Take the 42 qualifying frames from G137 --
      reuse its seed and manifest, do not draw new ones -- and for a seeded subset of at least 15,
      judge by eye how many of the four claimed roles actually lie on the correct physical line.
      Report the per-role correctness rate with Wilson 95 pct intervals. G137 looked at five and all
      five failed; this establishes whether that was representative.
  (c) MEASURE WHAT IS AVAILABLE. On the same frames, how many roles COULD be assigned correctly
      from the lines G134's stable grouping actually detects? That gap -- available versus assigned
      -- is the size of the prize, and it is the number that says whether fixing the assigner is
      worth anything at all.
  (d) DIAGNOSE the all-or-none behaviour into one of: a hard requirement for all four before
      emitting anything; a fallback that fabricates missing roles from the ones found; or a
      geometric solve that only returns on a complete set. These have very different fixes, and (b)
      distinguishes the second from the others -- fabricated roles would be wrong in a
      characteristic way.
  (e) RECOMMEND, do not implement. If the fix is to emit partial assignments with per-role
      confidence, say so and say what would consume them. Do NOT change the assigner in this row:
      a change here needs its own preregistration and its own before/after, and this row is the
      before.
DO NOT change any detector or grouping parameter, line_calibration.py, the frozen protocol at
98b7d6974, the G84 sample, the G115 labels, any threshold, or the coordinate contract.
BE CAREFUL WITH THE HEADLINE NUMBER: 19.53 pct is a rate of CLAIMS, not of correct assignments, and
G137 already found five of five wrong. Do not report it as reachability, and do not let it appear
anywhere near the 46.2 pct [39.6, 52.9] geometric reachability figure from G136, which is a
different quantity measured a different way.
ACCEPTANCE RULE:
  metric        = per-role correctness of claimed assignments on >= 15 seeded qualifying frames,
                  with Wilson intervals; plus the count of roles that COULD have been assigned
                  correctly from detected lines on those same frames
  before        = 42/215 = 19.53 pct claims, distribution 173/0/0/0/42, five of five eye-checked
                  frames wrong
  bar           = NO pass bar. Success is the assigner logic quoted, its correctness measured, the
                  available-versus-assigned gap reported, and the all-or-none cause named. "The
                  assigner is wrong and there is nothing available to assign either" is a full
                  success and would close the basketball line route for good.
  n             = >= 15 of G137's 42 qualifying frames, seeded from its manifest; state the seed
  eye check     = REQUIRED and it is the measurement. Commit every frame you judged with the
                  claimed roles drawn on it.
  must not move = the G137 sample, seed and manifest, the G134 grouping result, line_calibration.py,
                  every detector parameter, every threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g138_paint_role_assigner_2026-09-0X.md with the quoted logic, the
correctness table, the available-versus-assigned gap, the named cause, the renders, and a NOT
VERIFIED list. Commit under docs/evidence/tracking/g138_assigner/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon is live and seven footage
bridge lane workers are running under scripts/platformkit/bridge_keeper.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
