GAP G286 | sport wnba | worktree a5 | log g286_what_is_at_the_footpoint
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO DECODE, NO DISK GUARD, NO HOLD RULE. START IMMEDIATELY.**
The pod is saturated by five or more peer lanes; this row is built to need none of it. Committed inputs:
  - frames: `docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a/frames/` (1920x1080)
  - located player feet: `docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv`
  - G267 footpoints: `g267_court_space_physical_plausibility_artifact/g267_measurement.json`

**READ THE G273-VS-G285b-RECONCILED AND DETECTION-DEFECT-DECOMPOSED LEDGER ROWS FIRST.**

**WHY THIS ROW EXISTS -- WE KNOW THE DETECTOR IS BADLY LOCALISED AND WE DO NOT KNOW WHAT IT IS POINTING AT.**
Measured from committed data over 15 frames, 112 detections split two ways:
  - **33 / 112 = 0.295** have **no** player anywhere in a 512x640 crop centred on them.
  - **79 / 112 = 0.705** do have a player there, **but the footpoint sits a median 172.4 px from that
    player's feet** (p25 79.0, p75 253.6, max 387.7; only 0.101 within 50 px).

**A median error of more than a body length is not noise -- it is a systematic behaviour with a cause.**
The vertical component is the clue: the detector footpoint is **lower in the image** than the located feet
in **12 of 15** frames, by a per-frame median of **+147 px**, while median x agrees closely (880.5 against
899.0). **That is consistent with a bounding box extending well below the player's feet, but nobody has
looked.**

THE QUESTION: **when a player is nearby but the footpoint is not on their feet, what is the footpoint
actually on?**

METHOD:
  1. **TAKE THE 79 "PLAYER PRESENT" DETECTIONS** -- those with a located player inside a 512x640 crop
     centred on the footpoint. **Recompute that set yourself from the committed inputs and confirm you get
     79; report your number if it differs.**
  2. **RENDER EACH AS A CROP CENTRED ON THE FOOTPOINT**, 512x640 at full source resolution, **matching
     G273's crop exactly so the two rows are comparable.** Mark **two** things distinctly: the **detector
     footpoint** at the centre, and the **located player's feet**. **State the marker styles.** **Both
     points are inside the crop by construction**, so the judgement scale matches the tolerance -- that is
     the fix for what broke G285.
  3. **CLASSIFY BLIND IN A RANDOMISED ORDER, COMMITTING THE ORDER AND VERDICTS BEFORE UN-BLINDING.**
     Categories, and they are about **what lies under the footpoint marker**:
     **(a) THE LOCATED PLAYER'S FEET** -- the marker is on them after all;
     **(b) THE LOCATED PLAYER'S BODY, NOT THEIR FEET** -- torso, head, or above the feet;
     **(c) BARE COURT OR FLOOR** -- below, beside or away from the player, nothing on it;
     **(d) A DIFFERENT PERSON** than the located one;
     **(e) SOMETHING ELSE** -- describe it in a free-text field;
     **(f) CANNOT JUDGE.**
     **Keep (f) separate and never merge it.**
  4. **REPORT THE SIX COUNTS AND FRACTIONS.** **(c) dominant would point at box geometry -- a box
     extending below the player onto the floor.** **(d) dominant would point at assignment, and would mean
     my nearest-neighbour matching mislabelled which player the detection belongs to, which would make the
     172 px figure an overestimate.** **(b) dominant would point at the footpoint convention.** **Say
     which reading the counts support, and say it plainly.**
  5. **ALSO RECORD THE DIRECTION** of the offset for each crop -- is the footpoint above, below, left or
     right of the located feet? **Report the distribution.** It should corroborate or contradict the
     +147 px downward signal measured arithmetically.
  6. **Do NOT re-detect, do NOT re-locate players, do NOT touch `src/`, and propose no filter, threshold,
     gate or retrain.** Do not move any bar.

**LIMITS to state:** 15 frames of ONE shot of ONE clip, ONE labeller, one non-deterministic detector draw.
**The located feet are a human estimate**, so category (a) verdicts are a check on that estimate as much
as on the detector. **The nearest-neighbour pairing may be wrong** -- that is exactly what category (d)
tests, so a high (d) count is a finding about my method, not about the tracker, and **I want it reported
that way.** **Per G278 the span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078):
NOT clip-wide.** **A footpoint is not a box**; this row observes what is at a point, and can only infer
box geometry, never measure it.

ACCEPTANCE RULE:
  metric        = the recomputed 79-detection set; the crop and marker policy; the committed randomised
                  order and verdicts; the six counts and fractions with (f) separate; the offset-direction
                  distribution; and a plain statement of which mechanism the counts support
  before        = 0.705 of detections have a player nearby but sit a median 172.4 px from that player's
                  feet, with a +147 px downward vertical signal and no idea what the footpoint is on
  bar           = **NO pass bar.** **(c) dominant is a box-geometry finding. (d) dominant is a finding
                  about MY matching method and would revise the 172 px figure downward. (b) dominant is a
                  convention finding. A large (f) would mean the crops cannot answer it.** **All are full
                  successes; I want whichever is true.** Do not tune, do not re-pair, do not move a bar.
  n             = 1 clip, 1 shot, 15 frames, 79 classified detections, 1 labeller -- name every
                  denominator in the verdict line, and name the detector-box population
  eye check     = the blind classification IS the measurement, at a scale where both points are visible in
                  one crop -- **say that this is the fix for the scale fault that invalidated G285**
  must not move = G285b's sealed located coordinates, G284's sealed counts, G273's counts and crop policy,
                  G267's records, G278's frames, every threshold and verdict, `src/` and `domains/`
EVIDENCE: `docs/evidence/tracking/g286_what_is_at_the_footpoint_2026-09-04.md` with the set recomputation,
the crop policy, committed order and verdicts, every crop, the six counts, the direction distribution, the
mechanism statement, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE
MEMO.**
TEST: one per-file test for any harness added, pasted. **NEVER a full pytest.**
COMMIT: explicit pathspec, no push, report the sha. **Commit verdicts before un-blinding; make EVERY
commit before you finish.** ASCII stdout. **NEVER PARK.**
