# G140 basketball corner pixel targets on G136

## 1. Blind self-agreement (reported first)

The seeded blind re-label contains three of the 17 fixed qualifying source
frames, or ceil(15 percent), selected with `random.Random(13020260903)` from
lexically sorted audit IDs. It has 12 matched physical-corner role pairs.
The independently recomputed coordinate displacement is **median 10.971927
pixels; p90 11.392950 pixels**. The second-pass rows are in
[`g140_corner_targets/blind_relabel_targets.csv`](g140_corner_targets/blind_relabel_targets.csv);
the first-pass coordinates were not opened during that re-label pass.

This is not detector accuracy. It is the observed repeatability of eye-placed
native-pixel targets at this broadcast resolution, and any later corner
detector comparison must not be interpreted as more accurate than this
labelling process can establish.

## 2. Fixed G136 subset and committed targets

G136's complete immutable first-pass census has 210 frames and marks 97 with
four visible paint corners. G136's existing seeded 42-frame re-judge manifest
(seed `13020260903`) contains **17** of those qualifying first-pass frames.
G140 takes all 17 -- it does not draw a replacement sample or re-judge the
census. The result is **68 committed pixel targets** (four retained physical
roles per frame), in
[`g140_corner_targets/corner_pixel_targets.csv`](g140_corner_targets/corner_pixel_targets.csv).

Each target is keyed by `clip`, `source_frame`, and `role`, includes the
native image dimensions and source-decode path, and uses the pre-existing
role vocabulary:

- `paint_near_baseline_left_corner`
- `paint_near_baseline_right_corner`
- `paint_near_free_throw_left_corner`
- `paint_near_free_throw_right_corner`

The selection rule and role convention were fixed in
[`g140_corner_targets/protocol.md`](g140_corner_targets/protocol.md). The
machine-readable counts and self-agreement summary are in
[`g140_corner_targets/summary.json`](g140_corner_targets/summary.json).
All 17 source frames carry their target overlays under
[`g140_corner_targets/renders/`](g140_corner_targets/renders/).

## 3. G136 caveat propagated to every count

The 17-frame / 68-role target set is conditioned on G136's first-pass census,
whose own blinded reachability agreement is **28/42 = 66.7 percent** (Wilson
95 percent interval **51.6 to 79.0 percent**). G136's 97/210 = 46.2 percent
four-corner figure is therefore a caveated census estimate, not a precise
visibility population value. A source frame selected because that census
marked it four-corner-visible may not be judged the same way by another
reviewer. This uncertainty belongs to the target denominator; it is not
silently converted into a detector miss or removed from the fixed set.

## 4. Scope and result

This row creates the previously missing localised target artifact that blocked
G119 and G121. It runs no corner detector, no line detector, no recall or
precision measurement, and no tuning. G119's already specified scoring
procedure can consume this CSV unchanged in a later, separately specified
measurement row.

## Verifier-contract self-check

- **A1:** no code or test was added, so no G140 per-file test exists to rerun.
- **A2:** recomputation from the two CSVs gives 68 unique first-pass role
  keys over 17 unique frames; the 12 blind pairs give median 10.971927 px and
  p90 11.392950 px.
- **A3:** all 17 selected source frames have an overlay; an even four-frame
  cross-set render review used lexical positions 0, 5, 10, and 16 rather than
  a head slice.
- **A4:** `(clip, source_frame, role)` is unique in the target CSV; frame and
  role counts are not recycled.
- **A5:** this is an additive evidence-only CSV schema with no existing code
  reader or production field changed.
- **A6:** this lane uses an explicit-path commit in worktree `a2`; archive
  landing to master and ledger/register updates are verifier work.
- **A7:** every evidence path named in this memo exists at this self-check:
  this memo, protocol, both CSVs, summary, and 17-file render directory.
- **B1:** clear. The fixed existing manifest filter names all 17 frames; no
  difficult target key was omitted from the 68-role set.
- **B2-B6:** clear. No existing schema, reader, gate, lifecycle, module,
  caller, pod file, deployment, detector, or coordinate contract changed.
- **B7:** clear. The selection is the existing shuffled manifest intersection
  and its renders cover every selected frame; review is not a head slice.
- **B8:** clear. No detector is fitted or evaluated against these labels.
- **B9:** clear. The denominator is 68 unique physical-corner role keys from
  17 unique source frames, not recycled IDs.
- **B10:** clear. No threshold, grouping parameter, G136 input, or coordinate
  contract value changed.

## NOT VERIFIED

- Corner-detector recall, precision, tolerance, ranking, or any comparison
  against the line route.
- Any homography, court-feet coordinate output, calibration, tracking result,
  external court-distance validation, or production integration.
- A more precise basketball four-corner visibility rate than G136's caveated
  46.2 percent census estimate.
