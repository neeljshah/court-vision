# G138 locked review protocol

This protocol was written before the G138 renders were viewed.  The decision
set is the 42 rows in `../g137_scale/qualifying_frames.csv`; all have four
claimed roles in G137.  The review subset is the 21 rows in
`review_selection.csv`, produced by `random.Random(137092026).sample` from
the lexical `(clip, frame_index)` ordering of that decision set.  The original
G137 seed is reused and the selected rows are not replaced.

For each rendered frame and each claimed role:

- `claimed_correct` is true only when the coloured assigned group visibly
  follows that named, physical painted court line.  A broadcast graphic,
  player/background edge, court border, basket/shot-clock structure, or a
  line of the wrong physical role is false.
- `available_from_stable_groups` is true only when that named painted role is
  visibly present and one of the thin grey G134-stable candidate groups follows
  it.  It is deliberately independent of which candidate the assigner chose.
- `unavailable_reason` names why a role is not available: `not_in_view`,
  `not_visibly_discernible`, `visible_but_no_stable_candidate`, or blank when
  available.  The four values are mutually exclusive at role level.

The visual unit is one unique `(clip, frame_index, role)` row.  Every selected
frame will have its claims drawn in colour and its G134 stable groups drawn in
thin grey.  The review is measurement, not a new detector or grouping run:
the existing G137 frame identities, G134 grouping, detector parameters,
thresholds, line calibration module, and coordinate contract remain frozen.
