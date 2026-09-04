GAP G279 | sport wnba | worktree a5 or a6 (whichever frees first) | log g279_speed_threshold_sensitivity
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY): ENTIRELY LOCAL. THERE IS NO POD STEP AND NO DISK GUARD.**
Everything needed is already committed in this worktree at
`docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`
(3,801 frame records, 30,071 detections). **Do NOT call `pod_run`. Do NOT decode any video. Do NOT run
`du -sm /workspace` -- it is irrelevant here and its absence locally is NOT a failure.** **This row is
deliberately pod-free so it can run while both pod lanes are occupied.**

**NO HOLD RULE APPLIES.** This row uses no pod lane. **Start immediately.**

**READ THE LANDED G267, G270 AND G271 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THE MOST-QUOTED NUMBER IN THE PROGRAMME RESTS ON ONE UNTESTED THRESHOLD.**
G267 and G270 report that **13.6 pct of same-ID steps, and 10.5 pct of steps with both endpoints on
court, imply speeds above 40 ft/s and are therefore physically impossible.** That figure appears in the
synthesis, in the evidence packet and in every downstream row. **Nobody has shown how it behaves as the
threshold moves.**

**40 ft/s was chosen as a deliberately conservative bar**: G267 cites an NBA average top speed of
8.09 m/s (26.5 ft/s), and **Usain Bolt's peak of 12.42 m/s is 40.7 ft/s**, so the bar sits at roughly a
world-record sprint. **A bar that conservative can only UNDERSTATE the defect**, and a reader has no way
to see by how much.

THE QUESTION: **how does the implausible-step fraction vary with the speed threshold, and is the headline
figure robust or an artifact of one cut point?**

METHOD:
  1. **Recompute the step population from the committed artifact, and reproduce G267 and G270 EXACTLY
     FIRST.** Consecutive-frame, same-`track_id` steps with both endpoints `finite`. **Report the step
     count and confirm you reproduce the published 13.6 pct all-steps and 10.5 pct both-endpoints-on-court
     figures.** **A mismatch is a significant finding in its own right -- report it and STOP rather than
     proceeding on a population you cannot reproduce.**
  2. **Report the FULL CURVE, not a new headline.** Give the implausible fraction at **20, 25, 26.5, 30,
     35, 40, 45, 50 and 60 ft/s**, for both the all-steps and the both-endpoints-on-court denominators.
     **Include 26.5 ft/s explicitly and label it "NBA average top speed"**, and **label 40.7 ft/s
     "Bolt peak"** wherever it appears.
  3. **Report the underlying distribution so the curve is interpretable**: median, p90, p99, p99.9 and max
     step speed in ft/s, for both denominators.
  4. **STATE ROBUSTNESS PLAINLY IN ONE SENTENCE.** If the fraction changes slowly across the range, the
     headline is robust to the cut point. **If it changes sharply near 40 ft/s, say so directly -- that
     would mean the figure is sensitive to an arbitrary choice and must always be quoted with its
     threshold.**
  5. **DO NOT SELECT A NEW HEADLINE THRESHOLD, AND DO NOT MOVE THE PUBLISHED ONE.** Contract B10 forbids
     moving a bar, and **reporting a curve is the honest alternative to choosing a new cut point.** The
     40 ft/s definition stays exactly where it is; **G267's, G270's and G271's published figures are NOT
     under review and must not be restated as anything other than what they are.**
  6. **A LOWER THRESHOLD WILL PRODUCE A LARGER FRACTION. That is arithmetic, not a new finding, and must
     NOT be presented as a worse defect than G267 reported.** **Explicitly warn the reader against reading
     the 20 or 25 ft/s point as the real error rate**: below about 26.5 ft/s the bar starts excluding
     genuine athletic movement, so those points bound the measurement, not the tracker.
  7. **ALSO REPORT WHAT FRACTION OF STEPS ARE UNMEASURABLE**: non-finite endpoints, and steps excluded by
     the on-court condition. **Name every denominator explicitly** -- the eligible step count, not just
     the numerator.
  8. **Do NOT re-detect, re-associate, re-render or touch `src/`.** No new inference of any kind; this is
     arithmetic on a landed artifact.
  9. **The population is detector boxes, not authenticated players** (G225: 19 boxes, 2 visibly on-court
     people; G273: only 0.597 of retained detections are a player on the court of play). **Name the
     denominator; never say "players" unqualified.** **Note in the memo that G273 means a substantial
     share of these steps are not people at all**, so the curve describes detector-box motion, not player
     motion.

**HONEST LIMITATIONS to state, not discover:** ONE clip, ONE camera shot (source frames 19599-23399), ONE
non-deterministic detector draw, and **one homography whose accuracy was measured at 5 px median / 19 px
p90 on the seed frame only (G252)** -- **map error propagates into every court-space speed and is NOT
included in this curve.** Speeds are computed between consecutive frames at 30 fps, so a one-frame
footpoint jitter of a few pixels produces a large apparent speed; **that is precisely the localisation
instability G272b identified and it is part of what the curve measures.** **This row cannot separate map
error, footpoint jitter, identity swaps and non-person detections from each other** -- G272b and G273
already measured those separately and this row does not revisit them.

ACCEPTANCE RULE:
  metric        = the reproduced G267/G270 figures with the step counts; the nine-point curve for both
                  denominators; the five distribution quantiles for both; the one-sentence robustness
                  statement; the unmeasurable-step accounting; and every denominator named
  before        = 13.6 pct all-steps and 10.5 pct both-endpoints-on-court above 40 ft/s, at a single
                  untested cut point roughly equal to a world-record sprint
  bar           = **NO pass bar and nothing here can fail.** **"The fraction is insensitive to the cut
                  point" strengthens every downstream row.** **"It is highly sensitive" is the more
                  valuable finding and would require the figure always to be quoted with its threshold.**
                  **Do NOT choose a new threshold, do NOT move the published one, and do NOT present a
                  lower-threshold fraction as a bigger defect.**
  n             = 1 clip, 1 shot, the eligible step count you state from 30,071 retained detections --
                  name every denominator in the verdict line, and name the detector-box population
  eye check     = none; this row touches no images and makes no visual judgement
  must not move = the 40 ft/s definition, G267's and G270's published figures, G267's retained records and
                  span, G233d's published map, the court model, the coordinate contract, `src/` and
                  `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g279_speed_threshold_sensitivity_2026-09-04.md with the reproduction
check, the full curve as a table, the quantiles, the robustness sentence, the unmeasurable accounting, and
a NOT VERIFIED list. **The curve must also be committed as a machine-readable file.** **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
