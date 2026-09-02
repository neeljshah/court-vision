# G93 measurement protocol (fixed before candidate review)

This protocol applies only to the 33-frame G84 selection in
`../g84_candidate_quality/selection.json` (seed `84092026`). No detector,
candidate-group, calibration, or harness setting is changed.

## Hand truth and denominator

For each frame, the reviewer records each physical paint-line role as visible
or not visible before assigning a detection outcome. The roles are `baseline`,
`free_throw`, `lane_left`, and `lane_right`, where left/right are in image
coordinates. A line that is off-frame or fully occluded is not visible and is
excluded from the recall denominator. Every visible line has two hand-marked
image endpoints on its discernible painted-line center.

## Fixed correspondence rule

A candidate group is a detection of a visible hand-marked line only when all
three conditions below hold. Candidate endpoints come exclusively from
`detect_lsd_segments(image, 28.0)` followed by
`candidate_line_group_details(..., 5.0, 10.0)`.

1. Its undirected image angle differs from the hand-marked line by at most
   12 degrees.
2. Its midpoint is at most 12 pixels perpendicular distance from the
   hand-marked line's supporting line.
3. The midpoint's projection onto the hand-marked segment lies from 20 pixels
   before its first endpoint through 20 pixels past its second endpoint.

This permits a returned fragment to count, but does not let a parallel line
elsewhere on the court count. The rule is fixed before inspecting candidate
overlays or assigning detected/missed outcomes.

## Fixed miss-reason vocabulary

Every missed visible line receives exactly one of: `low_contrast`,
`occluded_partial`, `too_short`, `merged_with_neighbour`,
`split_into_fragments`, `painted_over_by_court_logo`, or `other`. The reason
describes why no returned group met the fixed correspondence rule; it is not a
detector-tuning recommendation.
