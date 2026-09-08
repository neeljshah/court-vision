# G304 attempt 2 -- RATER INSTRUCTIONS (binary verification only)

You are ONE of two independent model raters for tracking row G304, attempt 2. The other
rater is a DIFFERENT model working the same crops in a different worktree. You will never
see the other rater's decisions, and you must not look for them.

Your task is BINARY VERIFICATION. YOU DO NOT LOCATE ANYTHING. A previous attempt asked two
models to locate landmarks on crops and they disagreed by hundreds of pixels; that is why
this attempt hands you a point that is already placed and asks only whether it is right.

## WHAT YOU ARE GIVEN

`docs/evidence/tracking/g304_crop_manifest_2026-09-07.csv` in worktree a11, columns:
    row_id, proposal_id, landmark_name, crop_path
Each `crop_path` is one JPEG. READ THE CROP IMAGES. Rate every row of the manifest.

Each crop shows the SAME point twice, with a red 1-px cross marker on it:
  - LEFT panel  : a 160x160 native-resolution crop, unscaled;
  - RIGHT panel : a 400x400 native-resolution context crop, unscaled;
  - the top-left text gives the proposal id and the CANDIDATE LANDMARK NAME.

## THE ONLY QUESTION YOU ANSWER

    Is the red marker sitting on the court landmark named in the label?

The candidate name is a MACHINE HYPOTHESIS. It is frequently wrong, and saying so is the
point of this row. REJECT is a correct, valuable answer and there is no target accept rate.

## THE 15-NAME VOCABULARY

    CORNER_NEAR_L, CORNER_NEAR_R     sideline-baseline corners on the near (camera) side
    CORNER_FAR_L, CORNER_FAR_R       sideline-baseline corners on the far side
    LANE_BASE_L, LANE_BASE_R         where the two lane boundaries meet the baseline
    FT_LINE_L, FT_LINE_R             where the two lane boundaries meet the free-throw line
    KEY_TOP                          the top of the key: free-throw line at the arc apex
    THREE_PT_BASE_L, THREE_PT_BASE_R where the three-point line meets the baseline
    CENTER_SIDELINE_NEAR/FAR         where the midcourt line meets the near / far sideline
    CENTER_CIRCLE_TOP/BOTTOM         the far / near extreme of the centre circle

## DECISION RULE

For every manifest row return exactly ONE of:
  - `ACCEPT` -- the marker is on the named landmark.
  - `REJECT` -- it is not, OR the named landmark is not visible in this crop, OR it is
    occluded by a player, OR the correct position is more than 8 px from the marker.
You MAY add a nudge of AT MOST 8 px in each axis (`nudge_dx`, `nudge_dy`, integer pixels,
positive dx is right, positive dy is down) when the marker is on the right feature but
slightly off. A NUDGE WITHOUT A WRITTEN `reason_code` IS DISCARDED and the proposal reverts
to the unnudged point. ANY correction beyond 8 px is a REJECT, not a nudge.
Leave `nudge_dx` and `nudge_dy` as `0` when you do not nudge.

`reason_code` is ONE token from this closed list, and nothing else:
    ON_LANDMARK        accepted as placed
    NUDGED             accepted after a nudge of <= 8 px (required whenever you nudge)
    WRONG_FEATURE      marker is on some other court feature
    NOT_VISIBLE        the named landmark is not in this crop
    OCCLUDED           the landmark is behind a player, a shadow or a graphic
    NOT_A_LINE         marker is on floor glare, a logo, a shoe or crowd texture
    OFF_BY_TOO_MUCH    right feature, but the correct point is more than 8 px away

## OUTPUT SCHEMA -- EXACTLY THESE SIX COLUMNS, ONE ROW PER PROPOSAL

    row_id, proposal_id, decision, nudge_dx, nudge_dy, reason_code

Write a CSV with that header and one row for every manifest row, in manifest order, to
`docs/evidence/tracking/g304_ratings_<your-model-name>_2026-09-07.csv` in YOUR OWN worktree.
Commit it there by explicit pathspec. Do not write into a11 and do not push.

## RULES YOU MUST NOT BREAK

- NO SPATIAL PROSE. Do not describe where a line runs, estimate a coordinate, discuss
  camera angle or geometry, or write any narrative about the court. The six columns are
  your entire output. Free-form spatial description is what failed in attempt 1.
- DO NOT LOCATE. Never emit a coordinate. The nudge is the only positional output you have
  and it is capped at 8 px.
- Do not read `g304_proposals_2026-09-07.csv`, any attempt-1 artifact, any other rater's
  output, or any homography, projection or detector result. They would prime you.
- Rate EVERY row. Skipping a row is not an abstention; it leaves the row UNRESOLVED and it
  counts against the instrument.
- Judge each proposal on its own. Do not make a frame's proposals agree with each other.
- ASCII only. No pushing. Never use `--force`.

## WHAT HAPPENS TO YOUR ANSWERS

A landmark is recorded only where BOTH raters ACCEPT and their nudged points lie within
4 px of each other. Everything else goes to adjudication. Inter-rater agreement will be
reported as Cohen's kappa; kappa is a reported field and NEVER a pass condition, and
agreement between raters never by itself establishes that a point is correct.
