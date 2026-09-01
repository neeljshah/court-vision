# SynthCal Wave 7 render-and-look

## Inputs

- Checkpoint: `data/models/synthcal_tennis.pt` (v1, synthetic-only).
- Video: `tennis__tennis_nyYk2nPZAwY_720p.mp4`, 1280x720 at 50 fps.
- Sample: twenty uniformly distributed decoded real frames, frame IDs and raw
  confidence outputs in `synthcal_overlays/predictions.json`.

## Visual result: A - appearance gap

The model has no useful court/no-court discrimination and its heatmap maxima
are not attached to tennis-court geometry. On a wide, unobstructed court view,
many maxima are in the stands, broadcast graphics, the players, and equipment
rather than on their named line intersections. On close-up/crowd shots the
same approximately 0.5-0.7 confidences persist, even though no court geometry
is visible. This is an appearance/domain failure, not evidence that a
correspondence or downstream solver refinement can correct it.

Three representative examples:

- [Wide court: wrong maxima in stands/player regions](synthcal_overlays/synthcal_v1_02_f05531.jpg)
- [Non-court close-up: confident false landmarks](synthcal_overlays/synthcal_v1_05_f12928.jpg)
- [Partially obstructed court: false landmarks survive](synthcal_overlays/synthcal_v1_09_f22791.jpg)

The full twenty-frame visual record is in `synthcal_overlays/`, including a
contact sheet. This diagnosis authorizes exactly one bounded appearance-focused
refinement; it does not authorize any harness, solver, or production change.
