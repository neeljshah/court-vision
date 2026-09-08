# G304 attempt 2 -- PROPOSAL-VERIFY PREREGISTRATION (sealed before any rating)

Row G304, spec section `## VERSION 2026-09-07b (attempt 2: proposal-verify instrument)`.
Sealed by the BUILDER lane in worktree a11 BEFORE any proposal was rated by anyone.
The builder GENERATES proposals and PREPARES rater packets. The builder RATES NOTHING and
DISPATCHES NOTHING. Every clause of the G304 spec above the 2026-09-07b header still binds:
the 60/40/20 counts, the 4/3/3 negative split, the >=4-shot rule, the 240 held-out
correspondences, the >4 px adjudication threshold, the frame-good rule p90 <= 12 px AND
max <= 24 px, and the sealing order. NO BAR MOVES.

This document measures NO registration, NO calibration and NO tracking quality.
It states no boundary claim, no profit claim and no accuracy claim of any kind.

## 1. INPUT FRAMES (fixed before sealing)

63 ELIGIBLE frames, read-only, from the sealed inventories in worktree a4:
  - a4 commit `a6fa18878`, renders `g304_local_renders/` (original 60-row inventory)
  - a4 commit `346b976a3`, renders `g304_local_renders_ext/` (75-row extension)
Eligibility is taken as classified, not re-derived:
  - `nba-track-a3/docs/evidence/tracking/g304_eligibility_sol_2026-09-07.csv` (60 rows, 23 ELIGIBLE)
  - `nba-track-a20/docs/evidence/tracking/g304_eligibility_ext_sol_2026-09-07.csv` (75 rows, 40 ELIGIBLE)
Per arena: Gateway Center Arena 29, Climate Pledge Arena 34. Total 63.
All renders are native 1920x1080. Every proposal coordinate is in native 1920x1080 pixels.
EVERY attempt-1 landmark coordinate is VOID and is shown to no generator and no rater.

## 2. VOCABULARY (15 names) AND MARKING STRUCTURES (6)

    court_corner      : CORNER_NEAR_L, CORNER_NEAR_R, CORNER_FAR_L, CORNER_FAR_R
    lane_boundary     : LANE_BASE_L, LANE_BASE_R, FT_LINE_L, FT_LINE_R
    free_throw_line   : KEY_TOP
    three_point_arc   : THREE_PT_BASE_L, THREE_PT_BASE_R
    midcourt_line     : CENTER_SIDELINE_NEAR, CENTER_SIDELINE_FAR
    center_circle     : CENTER_CIRCLE_TOP, CENTER_CIRCLE_BOTTOM

The structure column is what the ">= 3 distinct marking structures" rule counts.

## 3. PROPOSAL SOURCES -- ALGORITHMIC ONLY, NEVER A RATER

`domains/` and `src/` are READ AND IMPORT ONLY. No edit, no threshold change, no re-tune.
A provider that abstains on a frame simply yields no proposal there; G227 already measured
that abstention and it is not a failure of this row.

  FAMILY `lsd_intersect`
    `domains.basketball.tracking.line_calibration.detect_lsd_segments(frame)` at the module
    default `min_length=60.0`, then `candidate_line_group_details(segments)` at the module
    defaults `angle_deg=5.0, offset_px=18.0`, both at native 1920x1080.
    Pairwise intersections are formed ONLY between two groups whose fitted directions differ
    by >= 25 degrees (near-parallel pairs give vanishing points, not landmarks). An
    intersection is kept only when it lies inside the 1920x1080 frame AND within both parent
    groups' observed extents with a 40 px tolerance. Score = min(parent group support length)
    divided by 1920, clipped to 1.0.

  FAMILY `semantic`
    `domains.basketball.tracking.keypoints.BasketballKeypointProvider().detect(frame)` at its
    module default `min_edge_support=0.16`. Its returned names map to the vocabulary as:
      left_paint_bl -> LANE_BASE_L    left_paint_br -> LANE_BASE_R
      left_paint_tl -> FT_LINE_L      left_paint_tr -> FT_LINE_R
      left_ft_circle, right_ft_circle -> KEY_TOP
    `center_circle` is NOT mapped: the provider returns a circle CENTRE and the vocabulary
    names the circle's top and bottom, so mapping it would propose a knowingly wrong point.
    Score = the provider's own confidence.

  FAMILY `shitomasi`
    Shi-Tomasi corners (`cv2.goodFeaturesToTrack`, maxCorners=80, qualityLevel=0.01,
    minDistance=25) computed on the court-marking mask, defined as HSV value > 170 AND
    saturation < 60, morphologically closed with a 3x3 kernel. This is the third proposal
    family required by the spec. Score = 1 - rank/maxCorners.

## 4. NAMING RULE (a stated hypothesis, not a measurement)

Only the `semantic` family carries provider semantics. For `lsd_intersect` and `shitomasi`
the candidate NAME is assigned by this fixed positional table on the normalised point
(bx = x/1920, by = y/1080), and by nothing else:

    band  = NEAR if by >= 0.66 ; MID if 0.33 <= by < 0.66 ; FAR if by < 0.33
    side  = L if bx < 0.40 ; C if 0.40 <= bx < 0.60 ; R if bx >= 0.60

    (NEAR,L) CORNER_NEAR_L   (NEAR,C) LANE_BASE_L*   (NEAR,R) CORNER_NEAR_R
    (MID ,L) THREE_PT_BASE_L (MID ,C) FT_LINE_L      (MID ,R) THREE_PT_BASE_R
    (FAR ,L) CORNER_FAR_L    (FAR ,C) KEY_TOP        (FAR ,R) CORNER_FAR_R

    * when the frame's eligibility-CSV `visible_structures` names a midcourt line or a
      centre-circle region, the centre column becomes (NEAR,C) CENTER_SIDELINE_NEAR and
      (FAR,C) CENTER_SIDELINE_FAR instead.

THE NAME IS A HYPOTHESIS THE RATER JUDGES. A wrong name produces a REJECT, and that REJECT
is a measurement of this instrument, not a defect to be tuned away. The table is frozen by
this seal and is not revised after any rating is seen.
CENTER_CIRCLE_TOP and CENTER_CIRCLE_BOTTOM are UNREACHABLE by all three families as
specified. That is preregistered here as a known coverage hole, not discovered afterwards.

## 5. PER-FRAME PROPOSAL CAP

CAP = 12 proposals per frame, fixed. Selection is deterministic:
  1. drop any proposal within 5 px of an already-kept proposal carrying the SAME name
     (the higher score survives);
  2. round-robin over distinct names in descending score, so the cap buys vocabulary
     coverage before it buys duplicates of one name;
  3. ties broken by (name, source, x, y) ascending.
63 frames x 12 = 756 proposals maximum. Frames yielding fewer are reported as they fall.

## 6. MARKED-CROP RENDERING

One JPEG per proposal at `g304_proposal_crops/<row_id>/<proposal_id>.jpg`, quality 85:
  - LEFT panel: the NATIVE 160x160 crop centred on the proposed point, unscaled, with a
    1-px cross marker at the exact point;
  - RIGHT panel: a 400x400 context crop centred on the same point, unscaled, with the same
    1-px marker;
  - the candidate NAME and the proposal id are printed on the canvas.
Crops carry NO projection, NO homography, NO detector output, NO score, NO source family
and NO other rater's decision. Frames touching a border are clamped; the marker stays at
the true point.

## 7. THE TWO RATERS

Two INDEPENDENT MODEL raters, DIFFERENT MODELS. Both are MODELS, not humans:
  - RATER A: `gpt-5.6-terra`, codex lane in worktree a3
  - RATER B: `gpt-5.6-sol`,   codex lane in worktree a7
The builder (Claude Opus, worktree a11) is NEITHER RATER and rates nothing. Neither rater
sees the other's decisions, the proposal scores, the source family, or any attempt-1 output.

## 8. BINARY DECISION RULE

For every proposal a rater returns exactly one of ACCEPT or REJECT, never a free coordinate.
A rater MAY add a nudge of at most 8 px (nudge_dx, nudge_dy) with a written reason_code.
  - A nudge without a written justification is DISCARDED and the proposal reverts to the
    unnudged point.
  - Any correction beyond 8 px is a REJECT, not a nudge.
Output schema, one row per proposal:
    row_id, proposal_id, decision (ACCEPT|REJECT), nudge_dx, nudge_dy, reason_code

## 9. AGREEMENT RULE

A LANDMARK EXISTS only where BOTH raters ACCEPT and their nudged points lie within 4 px of
each other; the landmark coordinate is then the MEAN of the two nudged points.
Everything else -- split accept/reject, or both-accept with nudged points more than 4 px
apart -- is a DISAGREEMENT and goes to adjudication under spec clause 1.5.
UNRESOLVED LABELS MEAN INSTRUMENT NOT VALIDATED -- THEY ARE NOT OMITTED FRAMES AND NOT
SUCCESSFUL ABSTENTIONS. AGREEMENT ALONE NEVER ESTABLISHES CORRECTNESS.

## 10. AGREEMENT REPORTING

Cohen's kappa on the binary ACCEPT/REJECT decisions, with EVERY denominator named:
proposals per frame, per arena and in total; accept rate for rater A; accept rate for
rater B; raw agreement; kappa. KAPPA IS A REPORTED FIELD, NEVER A PASS CONDITION, and it
is not a substitute for adjudication.

## 11. FRAME RULE

A frame is E1-READY only with >= 6 ACCEPTED landmarks across >= 3 DISTINCT marking
structures from the table in section 2. A frame with 5 accepted landmarks is SHORT, not
partially good. NO FRAME IS DROPPED: a frame that cannot be filled stays in the manifest
marked UNRESOLVED and counts against the instrument.

## 12. TWO ATTEMPTS MAXIMUM

Attempt 2 is this instrument. If proposal-verify also fails to fill the packet, the row
closes with the achieved yield, the kappa and the annotation burden reported, and
G306-G308 stay blocked. That is a LIMIT statement about the instrument, not a refutation
of any registration route. Human annotation remains a USER DECISION, not an agent one, and
this preregistration does not schedule it.

SEAL SHA256 (LF-normalized bytes above this line): 78f1a4f2b78245ec151bb4ba4e1b690a16efbbdd0aff02ab08d9af4c7bd41335

## AMENDMENT 1 -- SELECTION RULE, MADE BEFORE ANY RATING WAS SEEN

Recorded by the builder in worktree a11. NO PROPOSAL HAD BEEN RATED BY ANYONE WHEN THIS
AMENDMENT WAS MADE, and no rater had been dispatched. The amendment is motivated by a
GENERATOR-SIDE count only -- never by any accept/reject outcome, because none existed.

MEASUREMENT THAT MOTIVATED IT (63 eligible frames, pre-cap, families run independently):
  lsd_intersect  5772 candidates   shitomasi  5040 candidates   semantic  0 candidates
  Under the section 5 rule as originally sealed, the cap kept 35 lsd_intersect and 721
  shitomasi -- 0.6 percent of the LSD family survived.
CAUSE: the two families' scores are not on a comparable scale. `shitomasi` scores start at
0.99 by construction (1 - rank/80) while `lsd_intersect` scores are min(support)/1920 and
sit near 0.1-0.3, so the name round-robin took a Shi-Tomasi corner at the head of nearly
every name bucket. The precise family -- the one whose intersections the per-file test
recovers to 1.76 px on a synthetic court -- was crowded out by the coarser one.

AMENDED SECTION 5 SELECTION (this supersedes the original step 2; steps 1 and 3 stand):
  1. drop any proposal within 5 px of an already-kept proposal carrying the SAME name
     (the higher score survives) -- UNCHANGED;
  2. round-robin over SOURCE FAMILIES first, and within each family round-robin over
     distinct names in descending score, so no family can monopolise the cap;
  3. ties broken by (name, source, x, y) ascending -- UNCHANGED.
CAP stays 12. Every other section of this preregistration is UNCHANGED and still binds.
Scores are NOT renormalised: comparing family scores to each other remains invalid, and the
amended rule simply stops doing it.

The original seal below covers the text above this amendment and remains valid for it.
AMENDED SEAL SHA256 (LF-normalized bytes above this line, includes AMENDMENT 1): 3d60dcda526c14e78b1f1a98ca0c4d4e72c3f928f96fb426f0fac18b4a322696
