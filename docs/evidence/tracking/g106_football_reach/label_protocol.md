# G106 football reachability label protocol

The decision set is exactly G95's `sample_manifest.json`: global seed `95002`,
12 sorted samples from the interior 90 percent of each of nine clips. G106
does not select, replace, or reorder a frame. The four clips G95 eye-labelled
as soccer are excluded only from football-only headline denominators and are
named in the memo. The retained decision set is the 60 unique
`(clip_ordinal, frame)` rows labelled `football` by G95.

Every retained row was re-reviewed in its committed G95 four-up contact sheet.
The source render is recorded in every `frame_census.csv` row. These sheets
cover all 60 retained frames across their original temporal positions; this is
not a head-slice review.

## Line rules

`yard_stripe`, `hash_mark`, `sideline`, `goal_line`, and `end_line` are named
visible painted-line families. A family is present only when its marking is
visibly traceable in the rendered frame; the G95 per-frame visibility labels
are retained unchanged. `line_family_count` is the count of present named
families, not a correspondence count.

`independent_direction_count` instead counts non-empty field-direction
families. Yard stripes, individual hash marks, goal lines, and end lines are
all `crossfield`; sidelines are `lengthwise`. Parallel stripes or hashes do
not create another direction. Therefore the count is 0, 1, or 2, never the
raw stripe count.

## Point rules

The point columns are deliberately conservative lower bounds, so a visible
repeated mark is not mistaken for a named absolute correspondence.

- `yard_sideline_intersection_points` counts every visibly traceable sampled
  yard-stripe termination on a visible sideline. A stripe that does not reach
  a visible sideline counts zero.
- `identifiable_hash_points_min` is one when at least one individual hash mark
  is independently discernible and zero otherwise. It is a minimum, not an
  estimate of all repeated hash ticks in the frame.
- `goal_end_corner_points` requires a visibly traceable goal-line/end-line
  corner; `pylon_points` requires a visually distinct field pylon. Neither was
  present in this retained sample.

`identifiable_point_lower_bound` is the sum of the four point columns. These
pixel-space points have no asserted absolute field identity. A legible painted
number is carried forward from G95 for aliasing review, but
`absolute_yard_anchor` remains zero: the existing football geometry path
requires a readable number plus nearby directional arrow and independent
scale/field-level proof; this census supplies no such named emitted anchor.
