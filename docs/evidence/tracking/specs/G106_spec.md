GAP G106 | sport football | worktree a3 | log cx_g106_football_reachability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A REACHABILITY census that completes a four-sport picture.
Read docs/evidence/tracking/g95_football_calibration_survey_2026-09-02.md,
g91_soccer_landmarks_2026-09-02.md and g101_soccer_reachable_solve_2026-09-02.md first, and use
the same method so the sports stay comparable.
THE PICTURE SO FAR. Four sports fail the coordinate contract and have never been quality scored
(G47: baseball 66/93, football 30/42, soccer 15/25, basketball 8/12).
  - SOCCER is CLOSED AT LIMIT by two rows: point landmarks >= 4 visible in 0/100 frames (G91), named
    lines >= 4 in 0/100 and never more than TWO independent pitch directions (G101). A planar
    homography needs four point correspondences or four independent line constraints, so soccer
    court_feet is unreachable from this broadcast corpus at any detector quality. Corpus problem,
    not solver problem.
  - BASEBALL is being measured right now as G104.
  - BASKETBALL detection recall is being measured as G103.
  - FOOTBALL has G95, which measured yard stripes or hashes visible in 28/108 frames and a LEGIBLE
    painted yard number in only 18/108. That is a visibility survey; it is not yet a reachability
    answer.
THE QUESTION: is football court_feet reachable, and what specifically blocks it? Football is the
interesting case because its geometry is the densest in sport AND the most degenerate.
  - DEGENERACY: yard lines are all mutually PARALLEL. Twenty visible stripes give ONE independent
    direction, not twenty constraints. Sidelines add a second. So football, like soccer, may cap at
    two independent directions no matter how much white paint is on screen. Measure this
    explicitly -- it is the single most likely reason football fails, and counting stripes without
    counting directions would produce an encouraging number that means nothing.
  - ALIASING: even with a good solve, every 5-yard stripe looks like every other, so the solution
    can land a whole number of yards off with perfect residuals. The painted NUMBERS and the
    asymmetric hash spacing are the only things that break the periodicity, and G95 measured a
    legible number in just 18/108 frames. Say what that implies for a solve that must know WHICH
    yard line it is looking at.
METHOD, matching G101:
  (a) REUSE the G95 seeded frames and manifest so the two censuses are commensurable. Do not draw a
      new sample and do not change the seed. State that you reused it and the count you got.
  (b) Per frame count named visible LINE families and, separately, the number of INDEPENDENT
      directions they span. Then count POINT features that are individually identifiable: yard-line
      and sideline intersections, hash marks, goal-line and end-line corners, pylons.
  (c) EXCLUDE the mislabelled clips. G95 found four of the nine football-labelled clips are actually
      soccer footage. Report football-only numbers, state which clips you excluded and why, and
      report the count both ways so the exclusion is auditable. G99 is auditing the whole corpus for
      this right now; if you find a fifth mislabelled clip, report it as evidence for G99.
  (d) ONE SENTENCE: is football court_feet reachable from this corpus, and if so from what view and
      in what share of frames. "Not reachable, and here is the degeneracy that causes it" is a full
      success and it would mean three of four sports are corpus-limited rather than solver-limited,
      which is a finding about the whole programme.
DO NOT build a solver, add landmarks to any registry, declare a coordinate space, or change any
threshold.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame visible line families, INDEPENDENT line directions, and identifiable
                  point features, on football-only frames from the reused G95 sample
  before        = stripes or hashes visible 28/108, legible number 18/108; independent directions
                  never counted; four clips known mislabelled
  bar           = there is NO pass bar. Success is the census measured with the G101 method, the
                  independent-direction count reported, the mislabelled clips excluded and named,
                  and the one-sentence answer.
  n             = the reused G95 frames minus the excluded soccer clips; state both counts exactly
  eye check     = REQUIRED and it is the whole measurement. Commit every frame you judged.
  must not move = the G95 sample and seed, every threshold, the coordinate contract, every existing
                  verdict, and the G91/G101 results
EVIDENCE: docs/evidence/tracking/g106_football_reachability_2026-09-0X.md with the direction count,
the exclusion list, the one-sentence answer, the renders, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g106_football_reach/ BEFORE reporting (A7).
CAUTION FROM TODAY: two lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon and seven footage bridge
lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a3,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
