GAP G299 | sport wnba | worktree a3 | log g299_static_track_share
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO GPU, NO DECODE, NO DISK GUARD, NO HOLD RULE. START
IMMEDIATELY.** Committed inputs, already in your worktree:
`docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json` and
`docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv`. **Reuse
`scripts/platformkit/tracking/verifier_footpoint_analyses.py` for loading and for `steps()`; do not
redefine a step.**

**READ FIRST:** the G281 memo and ledger row, the G289 memo and ledger row, and the G287/G288 memos.
**This row has NO eye labels: do not open any blind verdict file.**

**WHY THIS ROW EXISTS -- THE ONE HEALTHY-LOOKING AXIS MAY BE HEALTHY FOR THE WRONG REASON.**
G281 measured **identity purity 0.935 at one second** and the programme has since called identity "the
healthy axis" and pointed at detection as the defect. **But G286/G287 measured that only about 0.44 of
footpoints are on a player at all and 0.181 sit on broadcast overlay furniture, which G288 confirmed 13/13
as score bugs and lower-third tickers.** **Overlay furniture is FIXED IN SCREEN SPACE. A track id locked
onto a score bug never changes identity, never swaps, and would score as PERFECTLY PURE while being
completely useless.** **So a high purity number is exactly what a corpus full of furniture tracks would
produce, and nobody has checked how much of the purity is that.**
Supporting signal already in hand: G289 found **1,228 of 29,973 steps have ZERO image displacement**, and
the verifier measured their median court movement at **0.0016 ft** -- numerical noise. **Something in this
corpus is not moving.**

THE QUESTION: **what share of detections, and of track ids, belong to tracks that barely move in the
image -- and how does that compare with the purity claim?**

METHOD:
  1. **PER TRACK ID, over its retained observations, report image-space motion**: the total path length in
     pixels, the bounding-box diagonal of all its footpoints, the median step displacement, and the
     observation count. **Report the DISTRIBUTION of these across ids, not just a threshold count.**
  2. **CLASSIFY IDS AS ESSENTIALLY STATIC BY A DECLARED, ARBITRARY CUT and SAY IT IS ARBITRARY** --
     suggested: at least 20 observations AND a footpoint bounding-box diagonal below 25 px. **Report the
     result at THREE cuts (say 10, 25 and 50 px) so a reader can see the sensitivity, and do NOT pick the
     cut that gives the most interesting number.**
  3. **REPORT, AT EACH CUT, WITH THE ELIGIBLE DENOMINATOR NAMED EVERY TIME**: how many ids are static of
     how many eligible ids, and **what share of ALL retained detections those static ids account for**.
     **The detection share is the number that matters -- a handful of static ids could carry a large share
     of observations, or a large number could carry almost none, and only the share tells you which.**
  4. **CROSS THE STATIC IDS AGAINST THE IMAGE BANDS.** The verifier measured detection share by row band:
     top strip 0.0008, score-bug band (y 90-300) 0.036, lower-third band (y 850-980) 0.318, bottom strip
     0.0006. **Report where the static ids sit.** **BE CAREFUL: the lower-third band is ALSO where the near
     court is, so a high static share there is NOT by itself evidence of furniture** -- the verifier
     already withdrew one claim for exactly that error. **State that caveat and do not repeat it.**
  5. **ANSWER IN ONE SENTENCE WITH NUMBERS: what share of retained detections belong to essentially static
     ids?** **A LARGE share means G281's purity is substantially measuring tracks that never move, the
     "identity is healthy" framing is misleading, and I want that said plainly and will correct the
     landed documents. A SMALL share means purity is measuring real tracks and the framing survives. BOTH
     ARE FULL SUCCESSES.**
  6. **DO NOT RECOMPUTE OR RE-RUN G281's PURITY.** You do not have its per-track labels and you must not
     invent them. **This row measures MOTION, and it can only say what fraction of the population is
     static -- it CANNOT attribute a share of the 0.935 to furniture.** **Say that limit explicitly rather
     than implying you have decomposed purity.**
  7. **Propose NO filter, threshold, gate, retrain or production change. Do NOT touch `src/`. Do NOT move
     any bar. Do NOT change any landed count or artifact.**

**HONEST LIMITATIONS to state, not discover:** **STATIC IS NOT THE SAME AS FURNITURE.** A player standing
still, a track that lives entirely during a held camera, or a short id in a static shot will all look
static, and **this row has NO image evidence and NO eye check to tell them apart** -- say so, and say that
naming furniture would need crops this row does not render. **The camera moves**, so screen-fixed overlay
graphics are static in image space while the court is not; that is the signal being used and it is
indirect. ONE clip, ONE span (19599-23399), ONE draw of a NON-DETERMINISTIC route (G241: 808 of 1,201
records differed). **Per G278 the span is measurably friendlier than the clip (0.836 against 0.656,
p = 0.0078), so nothing here may be quoted clip-wide.** The population is detector-box observations, not
authenticated players.

ACCEPTANCE RULE:
  metric        = per-id motion distributions; the static classification at three declared arbitrary cuts;
                  at each cut the static-id count over eligible ids AND the share of all retained
                  detections they carry, with denominators named; the image-band cross-tab with the
                  near-court caveat stated; and the one-sentence answer
  before        = identity purity 0.935 at one second is called the healthy axis, while 0.181 of
                  footpoints sit on screen-fixed overlay furniture that would score as perfectly pure, and
                  the overlap has never been measured
  bar           = **NO pass bar.** **A large static share makes the "identity is healthy" framing
                  misleading and I will correct the landed documents. A small share means the framing
                  survives. Either is a full success and I want whichever is true stated bluntly.**
  n             = 30,071 retained detections, 29,973 steps, the track ids in one clip, one span, one draw
                  -- name every denominator in the verdict line and name the detector-box population
  eye check     = NONE. Arithmetic on committed coordinates, with no image evidence and no ground truth.
                  **Say that, and say it is why this row cannot name furniture.**
  must not move = G281's purity and counts; G289's steps.csv and partition; G267's retained records and
                  span; G287's and G288's verdicts; `steps()` and its definition; every threshold and
                  verdict; `src/` and `domains/` (READ and IMPORT ONLY)
EVIDENCE: `docs/evidence/tracking/g299_static_track_share_2026-09-04.md` with the motion distributions, the
three-cut table, the detection shares, the band cross-tab, the one-sentence answer, and a NOT VERIFIED
list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7). **Do
NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: a per-file test for the harness, pasted -- **pin that the static cut is applied to the footpoint
bounding-box diagonal and that ids below the minimum observation count are excluded from the eligible
denominator rather than counted as non-static.** **NEVER a full pytest.** **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
