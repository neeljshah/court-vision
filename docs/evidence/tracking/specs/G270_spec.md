GAP G270 | sport wnba | worktree a5 | log g270_implausibility_conditioned_on_position
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` is HUMAN-GATED.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (N=2 is optimal). **Check first, do NOT interrupt a running row, and
EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G267 AND G269 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G267's OWN JACOBIAN TABLE SAYS ITS EXTREME SPEEDS CANNOT COME FROM ON-COURT
PIXEL ERROR, SO THEY MUST COME FROM SOMEWHERE ELSE, AND I HAVE ALREADY REPORTED THE 13.6 PCT HEADLINE.**

G267 measured **4,090 / 29,973 = 0.136** of same-ID steps above 40 ft/s, p99 **700 ft/s**, max
**100,457 ft/s**, and a max inter-detection distance of **3,269 ft on a 94-ft court**. G269 then showed the
13.6 pct is **not** removable by association -- constraining it merely fragmented tracks (98 to 139 ids,
p90 length 841.7 to 526.4).

**But G267 also reported the local image-to-court Jacobian, and it rules out the obvious explanation:**

| court location | local ft/px range |
|---|---|
| near sideline | 0.021--0.056 |
| far sideline | 0.029--0.055 |
| near-baseline midpoint | 0.033--0.079 |
| mid-court | 0.016--0.025 |

**At 0.079 ft/px worst case, even a 100 px jump is about 8 ft. Reaching 100,457 ft/s at 30 fps needs
roughly 3,348 ft in ONE frame.** No on-court pixel error produces that.

**THE HYPOTHESIS: the extreme values come from detections whose IMAGE position is near the homography's
horizon, where the projection is unbounded** -- crowd, stands, scoreboard, bench. A box high in the frame
projects hundreds or thousands of feet away, and a few pixels of movement there yields astronomic court
speed. **A supporting coincidence: G233d measured the in-court fraction at 0.83-0.92, so 8-17 pct of
detections project OUTSIDE the court, which is the same order as the 13.6 pct implausible fraction.**

**THIS MATTERS BECAUSE I HAVE ALREADY REPORTED 13.6 PCT AS AN END-TO-END QUALITY FIGURE.** If it is
dominated by off-court detections being projected at all, **the figure is about which boxes are fed to the
projection, not about tracking quality on players, and my framing needs correcting.**

THE QUESTION: **conditioned on where the detection actually is, where does the implausibility live?**

METHOD:
  1. **Reuse G267's retained boxes, map and span exactly** -- frames 19599-23399, G233d's published map.
     **Do not re-detect** (G241: the detector is non-deterministic, so a fresh pass is not comparable).
     **Reproduce G267's 0.136 baseline first and confirm it matches**; say so if it does not.
  2. **PARTITION THE STEPS, AND REPORT THE IMPLAUSIBLE FRACTION WITHIN EACH PARTITION:**
     **(a)** both endpoints project INSIDE the 94 x 50 ft court;
     **(b)** one endpoint inside, one outside;
     **(c)** both outside.
     **Report the step count and the above-40-ft/s fraction for each, plus p99 and max.**
  3. **ALSO PARTITION BY DISTANCE TO THE HORIZON.** Compute the homography's horizon line in image space
     and report, for each step, the image distance of its box feet from that line. **Report the
     implausible fraction and the local ft/px by horizon-distance band.** **This is the direct test of the
     hypothesis: if implausibility concentrates near the horizon, it is a projection-conditioning effect,
     not a detection or tracking defect.**
  4. **REPORT THE IN-COURT-ONLY FIGURE PROMINENTLY.** If restricting to partition (a) collapses the
     fraction, **that is the number that actually describes tracking quality on plausibly-on-court boxes**,
     and the 13.6 pct describes something else. **Give both, and say plainly which answers which question.**
  5. **DO NOT PRESENT THIS AS A FIX OR AN IMPROVEMENT.** Excluding out-of-court detections is a
     **conditioning choice**, not a repair -- the boxes are still being produced and still projected. Say
     that explicitly. **And an in-court projection can still be the wrong person**: identity remains
     unvalidated everywhere in this programme.
  6. **Do NOT propose a production change, filter, gate or threshold. Do NOT touch `src/`.**
  7. **The population is detector boxes, not authenticated players** -- officials, bench, spectators and
     duplicates included (G225: 19 boxes, 2 visibly on-court people). **Name that denominator; never say
     "players" unqualified.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** (last about
**36,400 MB**, roughly 13.6 GB free). **`dd conv=fsync` probe before writing, STOP and report if it
fails.** **Do NOT delete any corpus source or the two abandoned partials in the bridge directory.** Report
bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one arena, **one draw of a
non-deterministic detector** -- report to three decimals. The map is certified only to about 20 px (G257).
**A low in-court implausible fraction would NOT mean tracking is good** -- it would mean the impossible
steps are concentrated in boxes that should probably never have been projected, which is necessary and
never sufficient. **The horizon analysis assumes the map is right near the horizon, where it is least
constrained and least tested** -- say so.

ACCEPTANCE RULE:
  metric        = the reproduced 0.136 baseline; the implausible fraction, p99 and max within each of the
                  three in/out-of-court partitions with step counts; the implausible fraction and local
                  ft/px by horizon-distance band; and a plain statement of which figure answers which
                  question
  before       = G267 reported 13.6 pct end-to-end implausibility and G269 showed association cannot
                 remove it, while G267's own Jacobian table rules out on-court pixel error as the cause of
                 the extremes
  bar          = NO pass bar. **"Implausibility concentrates near the horizon or off-court" is a FULL
                 SUCCESS and would require me to re-frame the 13.6 pct figure I have already reported.**
                 **"It is spread evenly across in-court steps too" is an equally full success** and would
                 confirm a genuine detection defect. Do not filter, tune, or propose a change.
  n            = 1 clip, 1 shot, 1 map, the step counts per partition you state -- name every denominator
                 in the verdict line, and name the box population, not "players"
  eye check    = none required; commit a court-space scatter of implausible step endpoints if it aids a
                 reader
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained boxes and span,
                  the court model, the coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY),
                  the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g270_implausibility_conditioned_on_position_2026-09-04.md with the
reproduced baseline, the partition table, the horizon-band table, the prominent in-court-only figure, the
explicit statement that conditioning is not a fix, every disk-guard probe with the `du -sm /workspace`
figure, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE
MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
