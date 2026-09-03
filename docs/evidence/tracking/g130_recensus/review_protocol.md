# G130 Basketball Paint-Corner Review Protocol

This protocol was written before G130 sampling or any frame judgement. Every
frame is decoded read-only from its named source clip at the recorded zero-based
frame index. G111 labels and its pre-rendered images are not inputs to this
review.

## Operational rule

A visible paint corner is credited only when the two painted boundary lines of
the same physical lane rectangle visibly meet at that corner in the source
frame. The four eligible corners are the two baseline/lane-side intersections
and the two free-throw-line/lane-side intersections. Credit no inferred,
extended, occluded, graphic, or unrelated-court intersection. A frame is
`reachable` exactly when all four eligible corners are independently visible.

## Boundary cases

1. If a player obscures the meeting point while portions of both lines remain
   visible on either side, record no corner: continuation is an inference.
2. If the baseline and one lane side visibly meet but the free-throw line is
   out of frame, credit the visible baseline corner only; the frame is not
   reachable.
3. If television graphics, glare, a logo, or a three-point arc creates an
   apparent crossing without both painted lane-boundary segments meeting,
   credit no paint corner.
4. If all four intersections of one lane rectangle are plainly visible even
   though players cover non-intersection portions of a line, credit all four
   when each meeting point itself remains visible.

## Blinding

First-pass decisions are recorded before creating the re-judgement selection.
The second pass is presented in a separately seeded shuffled order and its
review table contains no first-pass label column. Comparison is performed only
after both decision files are complete.
