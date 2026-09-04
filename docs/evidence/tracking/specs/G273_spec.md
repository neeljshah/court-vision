GAP G273 | sport wnba | worktree a5 | log g273_detector_precision_blind_sample
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (N=2 is optimal per G200/G216). **Check first, do NOT interrupt a running
row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G267, G271, G272b MEMOS AND THE G272b-CATEGORY-A-CORRECTION LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- THE DEFECT IS NAMED BUT ITS SIZE IS UNKNOWN, AND THE 50 PCT FIGURE IS FROM A
BIASED SUBSAMPLE.**
G272b blind-classified 48 box-jump steps and found **24 of 48 (0.500) show NOT A PERSON in one or both
crops** -- the largest category, ahead of footpoint localisation (14/48) and identity swaps (9/48).
**So the leading defect is that things which are not people are being detected and tracked at all.**

**But jump steps are exactly where non-people would be over-represented**, so 50 pct is not the detector's
error rate. **Nobody has measured what fraction of ALL detections are people.** G225 is the only nearby
evidence and it is one frame: **19 raw boxes yielding 2 visibly on-court people.**

**THIS ROW MEASURES THE DETECTOR'S PRECISION, WHICH THIS PROGRAMME HAS NEVER HAD**, and it makes the 50
pct interpretable: **if say 10 pct of all detections are non-people but 50 pct of jump steps involve one,
non-people are hugely over-represented in jumps and are plausibly causing them. If 45 pct of ALL detections
are non-people, the detector is simply imprecise and jumps are incidental.** Those are different problems.

THE QUESTION: **what fraction of retained detections are actually people, and where are they?**

METHOD:
  1. **Reuse G267's retained records and span** (frames 19599-23399, one pre-cut shot). **Do not
     re-detect** -- G241 established the detector is non-deterministic, so a fresh pass breaks
     comparability with G267, G269-G272b.
  2. **SAMPLE ALL DETECTIONS UNIFORMLY, NOT JUMP STEPS.** Take **at least 60** retained detections drawn
     evenly across the span and across frames -- **say exactly how you sampled and how many distinct frames
     and ids it covers.** **This sample must NOT be conditioned on speed, on jumps, or on anything
     downstream** -- that is the whole point.
  3. **Render each as a footpoint-centred crop at full resolution**, using G272b's technique: **the crop is
     centred on the retained bottom-centre footpoint, NO bounding box is drawn or inferred** (G267 retained
     no box extents). State the crop size and why.
  4. **CLASSIFY BLIND IN RANDOMISED ORDER, COMMITTING THE ORDER AND VERDICTS IN THEIR OWN COMMIT BEFORE
     UN-BLINDING**, as G255, G257, G260 and G272b did. Categories fixed here:
     **(a) PLAYER on the court of play;
     (b) PERSON, but not a player in play -- official, coach, bench, photographer, spectator;
     (c) NOT A PERSON -- floor marking, equipment, scoreboard, graphic, shadow, artifact;
     (d) CANNOT JUDGE.**
     **Keep (d) separate and never merge it.**
  5. **REPORT THE FOUR COUNTS AND FRACTIONS.** **(a) is the detector's useful yield; (b)+(c) together are
     the boxes that should arguably never enter tracking.** Report both groupings explicitly.
  6. **COMPARE TO G272b's JUMP-STEP RATE AND STATE THE OVER-REPRESENTATION PLAINLY.** If the all-detection
     non-person rate is far below G272b's 50 pct, **say that non-people are concentrated in jumps**; if it
     is comparable, **say the detector is imprecise generally and jumps are not special.** **Do not assert
     causation either way** -- G271 and G267 both correctly refused to, and a correction tonight came from
     a category that fused observation with inference.
  7. **ALSO REPORT WHERE EACH CLASS SITS**, in image coordinates and in projected court coordinates, so a
     reader can see whether non-people cluster in identifiable regions. **Report it descriptively; do NOT
     propose a spatial filter, threshold or gate** -- G269 showed how easily a filter fakes an improvement.
  8. **Do NOT propose any production change; do NOT touch `src/`; do NOT re-detect or re-associate.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- the scope
the 50 GB quota is enforced on, last about **36,400 MB** with roughly 13.6 GB free, and **note that a peer
session now writes compute scratch under `/workspace/wt`, which a subtree measurement cannot see.**
**`dd conv=fsync` probe before writing, STOP and report if it fails.** **Crops are the bulk -- keep them
modest and report committed bytes.** **Do NOT delete any corpus source or the two abandoned partials in the
bridge directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one arena, **one labeller**, one draw of
a non-deterministic detector. **60+ of ~30,071 is a sample** -- give its size and spread and do not present
fractions as exact. **A footpoint-centred crop is not the detector's box**: it shows the neighbourhood the
detection claimed, not the extent it claimed, so a "not a person" verdict means nothing person-like is at
that location. **Category (b) is a judgement about role, not identity**, and courtside people are often
ambiguous -- expect (d) to be non-trivial and do not suppress it. Eye-label reliability in this programme
has never cleared 80 pct blind agreement on four measured criteria, though those were geometric rather than
categorical.

ACCEPTANCE RULE:
  metric        = the sampling description with frame and id coverage; the committed randomised order and
                  blind verdicts with the ordering statement; counts and fractions for (a)-(d) with (d)
                  separate and the (b)+(c) grouping stated; the comparison against G272b's 50 pct jump-step
                  rate with an explicit over-representation statement; and the image and court positions by
                  class
  before       = G272b found 50 pct of box-jump steps involve a non-person, but jump steps are a biased
                 subsample and the detector's precision has never been measured; G225's single frame gave
                 19 boxes for 2 visibly on-court people
  bar          = NO pass bar. **A low all-detection non-person rate would show non-people are concentrated
                 in jumps and is a full success.** **A high rate would show the detector is imprecise
                 generally, which is an equally full success and a bigger problem.** Do not filter, tune,
                 propose a threshold, or assert causation.
  n            = 1 clip, 1 shot, the sample size and coverage you state, 1 labeller -- name every
                 denominator in the verdict line
  eye check    = the blind classification IS the measurement, and it is a coarse categorical judgement, not
                 the sub-pixel geometric one G257 bounded at 20 px
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained records and
                  span, the court model, the coordinate contract, `src/` and `domains/` (READ and IMPORT
                  ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g273_detector_precision_blind_sample_2026-09-04.md with the sampling
description, the committed blind order and verdicts, every crop, the four counts with groupings, the
over-representation comparison, the positional breakdown, every disk-guard probe with the
`du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md
ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
