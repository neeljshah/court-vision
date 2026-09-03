# G140 target-labelling protocol

## Fixed decision set

The only decision set is the intersection of G136's immutable seeded
42-frame `g130_recensus/rejudge_selection_manifest.json` (seed `13020260903`)
and its immutable first-pass rows with `visible_paint_corners >= 4`. It has 17
unique source frames. This is a filter of an existing seed and manifest, not a
new draw or a visibility re-judgement.

## Pixel targets

Each first-pass target is a native-source pixel coordinate at the visibly
meeting painted boundaries of the near paint rectangle. Role strings retain
the pre-existing G136/G111 vocabulary:

- `paint_near_baseline_left_corner`
- `paint_near_baseline_right_corner`
- `paint_near_free_throw_left_corner`
- `paint_near_free_throw_right_corner`

`left` and `right` are the physical lane sides when standing on the near
baseline and looking toward centre court; they are not assigned by image x
order. No detector output, line segment, fitted geometry, or extrapolated
intersection is an input to this labelling pass.

## Blind self-agreement

The blind relabel set is three of the 17 unique selected frames, which is
ceil(15 percent of 17), sampled before the second pass with
`random.Random(13020260903).sample(lexically_sorted_audit_ids, 3)`. Its frame
IDs are recorded in `blind_relabel_targets.csv`; the second-pass coordinates
were made from the source frames without opening the first-pass target CSV.

## Census caveat

The decision set inherits G136's 28/42 (66.7 percent) blind reachability
agreement. Thus its selection is a census-conditioned candidate denominator,
not a claim that all 17 frames are certainly four-corner-visible to another
reviewer. G140 retains every fixed frame and every four-role key rather than
dropping a difficult coordinate after inspection.
