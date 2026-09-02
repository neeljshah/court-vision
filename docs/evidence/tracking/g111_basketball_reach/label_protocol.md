# G111 basketball reachability label protocol

This protocol was written before the G111 sample was rendered or reviewed.
It defines an eye-judged visibility census only, not a detector or solver.

## Unit and retention

The unit is one unique seeded `(clip, source_frame)` pair. Every draw remains
in the denominator, including close-ups, graphics, replays, crowd shots, and
frames with zero identifiable court features. No row may be removed or
replaced after the draw.

## Point features

Count only a named court landmark whose location can be discerned in the
source frame, not a merely plausible extrapolation from a short line segment.
Each distinct physical location counts once. The permitted names are:

- `paint_<half>_<baseline|free_throw>_<left|right>_corner` for a discernible
  paint-rectangle corner, including its two visibly meeting boundary lines.
- `free_throw_circle_<half>_<left|right>_intersection` for a distinct
  free-throw-circle/line intersection; it is not a paint corner.
- `three_point_<half>_<left|right>_baseline_endpoint` and
  `three_point_<half>_apex` for a clearly visible three-point arc landmark.
- `centre_circle_<left|right|top|bottom>_cardinal` for a visible centre-circle
  cardinal point, only when the half-court orientation is identifiable.
- `court_<half>_<left|right>_corner` for a visible regulation court corner.

If perspective, player occlusion, crop, floor reflection, logo art, or image
quality prevents a confident named location, do not count it. A line crossing
without a known landmark role is not a point feature.

## Straight-line directions

Record the visible named straight lines (for example `paint_near_baseline`,
`paint_near_free_throw`, `paint_near_left_side`, `paint_near_right_side`,
`near_sideline`, or `half_court_line`). Count independent directions by image
orientation family: parallel named lines are one family. The three-point arc
and centre circle are recorded in `visible_curves` but contribute zero to the
straight-line direction count; they are nonlinear evidence, not invented
straight directions.

## Review procedure

Review every tile in the per-clip contact sheets. Open the corresponding
full-resolution render whenever the tile does not make the landmark identity
clear. Record `point_features`, `visible_lines`, `visible_curves`,
`independent_directions`, and a concise judgment note for every frame.
