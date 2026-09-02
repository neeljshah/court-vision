GAP G104 | sport baseball | worktree a7 | log cx_g104_baseball_reachability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A REACHABILITY census, and it completes a picture. Read
docs/evidence/tracking/g91_soccer_landmarks_2026-09-02.md and
docs/evidence/tracking/g101_soccer_reachable_solve_2026-09-02.md first, and copy their method.
WHY THIS ROW EXISTS. Four sports fail the coordinate contract and have never been quality scored
(G47: baseball 66/93, football 30/42, soccer 15/25, basketball 8/12). Soccer has now been settled
by two rows and the answer was not the one anyone expected:
  - G91: canonical POINT landmarks visible >= 5 in 0/100 frames, >= 4 in 0/100, >= 3 in 34/100.
  - G101: named LINES visible >= 4 in 0/100 frames, and NO frame spans more than two independent
    pitch directions.
Four point correspondences or four independent line constraints are the minimum for a planar
homography, so soccer court_feet is unreachable from this broadcast corpus by any point or line
method, at any detector quality. That is a corpus problem, not a solver problem, and knowing it
stopped a solver from being built. BASEBALL IS THE LARGEST REMAINING BLOCK and has had no
equivalent measurement.
BASEBALL IS GEOMETRICALLY DIFFERENT AND MAY WELL COME OUT THE OTHER WAY, so measure it rather than
assuming the soccer answer generalises:
  - The infield is a 90 ft square with four bases at known positions, plus the pitching rubber at a
    known offset. Those are POINT features, not line intersections, and they are non-periodic and
    individually identifiable -- home plate cannot be confused with second base.
  - The standard broadcast centre-field camera frames the pitcher, batter and plate, and typically
    shows very little of the infield. That is the thing to measure.
  - Baseball parks are NOT dimensionally standard in the outfield, but the infield IS: 90 ft base
    paths and 60 ft 6 in to the rubber are fixed by rule. So an infield-only solve carries far less
    scale uncertainty than the "real pitches vary a few metres" caveat soccer had. Say so if it
    matters to your conclusion.
METHOD, deliberately the same shape as G91 and G101 so the numbers are comparable across sports:
  (a) Seeded, stratified sample of >= 100 frames across the baseball pod clips, drawing from ALL
      THREE feeder labels (mlb, kbo, npb) since they are different broadcasters with different
      camera conventions. State the seed and the per-clip counts. Do not head-slice.
  (b) Per frame, count VISIBLE identifiable point features: home plate, first, second and third
      base, the pitching rubber, plus foul lines and the infield dirt arc if you count lines.
  (c) Report the >= 4, >= 3 and >= 2 point shares, and for any line features the number of
      INDEPENDENT directions, exactly as G101 did. Two parallel foul lines are not two constraints.
  (d) BE ALERT TO A CONFOUND THIS ROW INHERITS: G95 found that four of nine football-labelled clips
      are actually soccer footage, and G99 is auditing the whole corpus for sport mislabels right
      now. If a clip you sample is not baseball, do not label it and do not silently drop it --
      report it, because it is evidence for G99.
  (e) ONE SENTENCE: is baseball court_feet reachable from this corpus, and if so from which camera
      view. If the answer is that only a rare camera angle supports it, quantify how rare -- a
      solve available on 5 pct of frames is a very different asset from one available on 60 pct.
DO NOT build a solver, do not add landmarks to any registry, do not declare a coordinate space for
any clip, and do not change any threshold. This row measures reachability.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame count of visible identifiable baseball point features, and independent
                  line directions, over >= 100 seeded frames
  before        = unmeasured for baseball; soccer measured unreachable by both point and line
                  methods
  bar           = there is NO pass bar. Success is the census measured with the same method as G91
                  and G101 so the sports are comparable, plus the one-sentence answer. "Reachable
                  on the centre-field view only, in N pct of frames" and "not reachable" are both
                  full successes.
  n             = >= 100 seeded frames spanning mlb, kbo and npb clips; state the seed and per-clip
                  counts, and state how many sampled frames turned out not to be baseball
  eye check     = REQUIRED and it is the whole measurement. Commit every frame you judged.
  must not move = every threshold, the coordinate contract, every existing verdict, the G91 and
                  G101 results, and every clip file or label
EVIDENCE: docs/evidence/tracking/g104_baseball_reachability_2026-09-0X.md with the visibility
distribution, the independent-direction count, the one-sentence answer, any non-baseball frames
found, the renders, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g104_baseball_reach/ BEFORE reporting (A7).
CAUTION FROM TODAY: two lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon and seven footage bridge
lanes are live and staging new games while you work.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a7,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
