GAP G227 | sport ncaa_basketball / wnba | worktree a3 | log g227_keypoint_provider_probe
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. `domains/` is READ
and IMPORT only -- **import `BasketballKeypointProvider`, do not edit it.** Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G211 is measuring per-frame cost there. Everything is
committed: the 17 frames under `docs/evidence/tracking/g130_recensus/source_decodes/` and the labels at
`docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`.

**WHY THIS ROW EXISTS -- IT IS THE LAST UNTESTED IN-REPO CALIBRATION CANDIDATE, AND THE TWO CHEAP ONES
CLOSED TONIGHT.**
  - **G217**: the fitter and court model contribute ZERO error; all of the oracle's **28.841316 px**
    median max-corner error is DETECTED LINE GEOMETRY, with selected lines missing their labelled
    corners by **median 10.234792 px**. Detection accuracy is the lever.
  - **G224 (CLOSED AT LIMIT)**: the tennis top-hat evidence transfer **roughly doubles** the error
    (oracle 1/17 at 28.841316 px -> 0/17 at 60.048887 px). Retired.
  - **G223 (ACCEPT)**: the selected-line error is **SCATTER, not bias** -- every role straddles zero,
    angle and offset both present with neither dominating, and corner error does not track shallowness
    (rank association -0.1225). **No deterministic correction exists.** Retired.
  - **G205 / G208 / G210b / G214**: LSD, M-LSD and the untruncated search all score **0/17**, against an
    oracle bound of 1/17.

**EVERY ONE OF THOSE ROWS SCORED THE SAME FAMILY: line segments, grouped, intersected.**
**`domains/basketball/tracking/keypoints.py` holds a DIFFERENT approach that has NEVER been scored.**
`BasketballKeypointProvider` does not use line-segment intersection at all: it runs Canny, extracts
contours, reduces them with `approxPolyDP` to **four-sided quadrilaterals**, keeps only quads whose area
exceeds `0.006 * width * height` and whose shortest side exceeds `0.15 * height` -- **excluding scorebugs
by physical image scale rather than by any harness threshold** -- scores them with `_line_support`, takes
the highest-confidence quad as the painted lane, and **names its corners by BASELINE ADJACENCY, which
its own docstring contrasts with "never Hough-line order".** Its module docstring says it "intentionally
emits no landmark for a line simply because it is the nth Hough segment", which is precisely the failure
mode G205 exhibited at ~1,928 proposals per frame.

**CONTEXT THAT CHANGES WHAT A NULL RESULT MEANS -- G68D, landed 2026-09-02.** A human-labelled census
of **1,650 sampled decoded tiles across 11 basketball clips** found paint **PAINT_SOLVABLE in
1,029/1,650 = 62.36 pct, Wilson 95 pct [0.6000, 0.6467]**, spread throughout every clip, with a further
**207/1,650 = 12.55 pct COURT_NO_PAINT** (a court view whose paint was not fittable). **So human
judgement says a fittable paint is present in roughly SIX frames in TEN, while automatic search scores
0/17 and even the detected-line oracle reaches only 1/17.** **The 1/17 figure is therefore a property of
the LSD-intersection pipeline, NOT a ceiling imposed by the footage.** That gap is the reason this row
is worth running rather than a reason to expect failure.

**IF YOU SCORE 0/17, THE MOST USEFUL THING YOU CAN ADD IS WHICH GATE REJECTED.**
`scripts/platformkit/basketball_gate_funnel.py` already exists for exactly this -- its docstring says it
"replays its actual paint gates on real frames and counts the first one that rejects each frame" and
reports landmark co-occurrence, "which answers whether a partial paint can furnish a four-point solve".
**Reuse it rather than writing your own funnel**, and report the first-rejecting-gate distribution over
the 17 frames beside your score. A 0/17 with a named dominant gate is far more actionable than a bare 0.

THE QUESTION: **does `BasketballKeypointProvider` propose the four paint corners on the 17 labelled
frames, scored by exactly the same protocol as every prior row?**

**A DISCREPANCY THE ORCHESTRATOR FOUND THAT YOU MUST HANDLE EXPLICITLY, NOT DISCOVER LATE.**
`scripts/platformkit/calibration/keypoint_calib.py:20-29` defines `CANONICAL_LANDMARKS["basketball"]`
with the paint spanning **y = 17.0 to y = 33.0, i.e. a 16 ft lane**, on a 94 x 50 ft court with 19 ft
depth. **That is the WNBA/NBA lane width.** But G196's `court_points_for_sport` uses a **per-league**
width -- **NCAA 12 ft, WNBA 16 ft** -- and **8 of the 17 construct frames are NCAA**. **So this module's
canonical model is the WRONG LANE WIDTH for roughly half the construct.** **Report NCAA and WNBA frames
SEPARATELY, and say whether the mismatch plausibly explains any NCAA failure.** **Do NOT edit
`keypoint_calib.py` to fix it** -- measure with it as it is, and if you want to show what a corrected
width would do, do it as a clearly-labelled SECONDARY arm in your own harness, never as the headline.

METHOD:
  1. **Score with G205's `score_frame` and `TOLERANCE_PX = 12.0`, both unchanged**, exactly as G205,
     G208, G210b, G214, G217 and G224 did, so this number is commensurable with all of them. **Do not
     write a new scorer.**
  2. **Map the provider's named landmarks to G140's four roles explicitly and state the mapping**, with
     its `file:line` basis. G140's roles are the near baseline left/right and near free-throw left/right
     paint corners; the provider emits names like `left_paint_bl`/`left_paint_tr`. **A wrong mapping
     would silently manufacture a null result, so state it and sanity-check it on one frame before
     scoring all 17.**
  3. **One fixed configuration across all 17 frames, declared BEFORE you see results.** `min_edge_support`
     defaults to 0.16; if you vary it, declare the small set in advance and report every value. **No
     per-frame tuning** -- that would break commensurability with every prior row.
  4. **Report: frames with all four roles within 12 px over 17; per-corner recall over 68; proposals per
     frame; and the NCAA/WNBA split.** **Proposals per frame is first-class** -- G205's ~1,928/frame is
     unusable however good recall gets, and this provider should produce very few by construction, so
     **a low proposal count with zero recall is a different and more informative failure than a high
     one.** Say which you got.
  5. **Report how often it finds NO paint quad at all.** `_paint` returns `None` when nothing survives
     the area, side-length and support filters. **"It abstains on N of 17 frames" is a distinct and
     useful outcome from "it proposes and misses", and the two must not be merged.**
  6. **Do NOT tune the filters to make it fire more often, do NOT lower the 12 px threshold, and do NOT
     add a candidate after seeing results.**

**HONEST LIMITATIONS to state, not discover:** 17 frames is a small exhaustive construct and the same one
every calibration row uses, so this measures those frames and not a rate. G140's p90 label repeatability
is **11.39 px**, so the 12 px threshold sits at the label-noise floor and a pass shows a candidate
proposes something roughly right, not production accuracy. Resolutions are MIXED -- 12 at 1920x1080, 4 at
1280x720, 1 at 640x360 -- and this provider's filters are expressed as FRACTIONS of frame dimensions, so
they scale, but `Canny(50, 150)` and the `perimeter < 120.0` cutoff are ABSOLUTE; **say how you handled
that and do not silently let the 640x360 frame fail on a fixed pixel perimeter.**

ACCEPTANCE RULE:
  metric        = frames with all four roles within 12 px over 17; per-corner recall over 68; proposals
                  per frame; abstention count; NCAA and WNBA reported separately
  before        = five rows have scored the line-segment family at 0/17 real and 1/17 oracle;
                  `BasketballKeypointProvider` exists in the repo, takes a structurally different
                  approach, and has never been scored
  bar           = **>= 1 of 17 would be the first non-oracle success in this programme.** **0 of 17,
                  taken with G205, G208, G210b, G214, G223 and G224, would close the in-repo classical
                  route AT LIMIT** and is a FULL SUCCESS -- it would say the next step must be labelling
                  or a trained model (which must cite G31), not another classical probe. Do not tune, do
                  not lower the bar, do not add a candidate after seeing results.
  n             = 17 frames (CONSTRUCT, exhaustive) x 4 roles = 68 label points
  eye check     = render the provider's proposed quad and named corners against the labels on 5 evenly
                  spaced frames; render the closest frame even if every frame scores 0
  must not move = every threshold, `min_edge_support` beyond a pre-declared set, the 12 px protocol,
                  G205's scorer contract, `CANONICAL_LANDMARKS`, the court model, the coordinate
                  contract, every bar and verdict, `src/` (READ ONLY), `domains/` (READ and IMPORT
                  ONLY), the pod (DO NOT USE IT), the corpus
EVIDENCE: docs/evidence/tracking/g227_keypoint_provider_probe_2026-09-04.md with the declared
configuration, the landmark-to-role mapping and its basis, the per-frame table, the NCAA/WNBA split, the
abstention count, proposals per frame, the renders, an explicit treatment of the 16 ft versus 12 ft lane
mismatch and of the absolute-pixel filters on mixed resolutions, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
