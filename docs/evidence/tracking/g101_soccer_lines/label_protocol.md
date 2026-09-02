# G101 line-census protocol

This protocol is fixed before G101 line review.  The decision set is exactly
the 100 `(clip, source_frame)` pairs in
[`../g91_soccer_landmarks/sample_manifest.json`](../g91_soccer_landmarks/sample_manifest.json):
seed `9102026`, twenty seeded uniform temporal-stratum draws in each of five
clips.  No frame may be added, removed, or substituted.

## Per-frame label rules

A straight line is counted only when a continuous portion of its painted
marking is visibly traceable in the full-resolution G91 render and can be
assigned a semantic pitch-line identity without inferring an off-frame line.
Lines hidden by players, graphics, blur, grass mowing, or the image boundary
are not counted.  The following individual semantic identities are eligible:

- `touchline_near`, `touchline_far`;
- `goal_line_left`, `goal_line_right`;
- `halfway_line`;
- `penalty_area_front_left`, `penalty_area_front_right`;
- `penalty_area_side_left_near`, `penalty_area_side_left_far`,
  `penalty_area_side_right_near`, `penalty_area_side_right_far`;
- `goal_area_front_left`, `goal_area_front_right`;
- `goal_area_side_left_near`, `goal_area_side_left_far`,
  `goal_area_side_right_near`, `goal_area_side_right_far`.

`left` and `right` name the pitch end after orienting the visible field from
the image context; `near` and `far` distinguish the two same-end side lines.
If that end identity is not visually defensible, the line is not counted as a
solver correspondence.  The centre circle is not a straight-line label.  Its
separate `center_circle_visible` flag requires a visibly identifiable arc or
full circle and is used only for the requested formulation discussion.

## Independent-direction rule

Each counted straight line is mapped to a canonical pitch-direction family:
`lengthwise` for touchlines and penalty/goal-area side lines, and `crosswise`
for goal lines, the halfway line, and penalty/goal-area front lines.
`independent_direction_count` is the number of non-empty families (0, 1, or
2), never the raw line count.  Multiple members of one family are parallel or
near-parallel in pitch coordinates and are recorded but do not add a direction.
The curved centre circle supplies no straight-line direction.

## Review and evidence rule

Every G91 frame is reviewed through the five 20-frame contact sheets, with an
individual source render opened whenever line identity is unclear.  The
committed G101 render for each row is a copy of the reviewed G91 source render
with the immutable clip, frame, slot, line labels, direction count, and circle
flag overlaid.  This preserves the visible input and makes each judgement
auditable without regenerating or changing the sample.
