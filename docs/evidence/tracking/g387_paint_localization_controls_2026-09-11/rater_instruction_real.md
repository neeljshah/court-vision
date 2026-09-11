# G387 blind native-tile localization instruction (REAL pass; identical for both raters)

You annotate basketball broadcast still frames from PIXELS ONLY. You have NO access
to any detector, extractor, stroke, court template, matrix, old label, or the other
rater's work, and you must not look for any. Do not retry, recalibrate, or revise.

## Your batch
Your batch file lists one context per line as
`OPAQUE_ID<TAB>CONTEXT_PATH<TAB>TILE1 TILE2 TILE3 TILE4 TILE5 TILE6`.
For EVERY line write exactly one JSON file `<OPAQUE_ID>.json` into your output
directory. Do not skip a line. Write nothing else.

## Geometry
The context image is 1920x1080. The six tiles are lossless 640x540 crops of it,
no rescaling, with fixed NATIVE offsets:
tile1 (0,0) tile2 (640,0) tile3 (1280,0) tile4 (0,540) tile5 (640,540) tile6 (1280,540).
NATIVE x = tile_x + offset_x, NATIVE y = tile_y + offset_y. Report NATIVE integers only,
0 <= x <= 1920 and 0 <= y <= 1080. Work on the tiles; the context is for orientation.

## What to report
At most TWO straight PAINTED court markings that you can actually see. For each one:
- `physical_marking_id`, used at most once per context, exactly one of:
  SIDELINE_NEAR, SIDELINE_FAR, BASELINE_LEFT, BASELINE_RIGHT, CENTRE_LINE,
  LANE_LINE_LEFT_NEAR, LANE_LINE_LEFT_FAR, LANE_LINE_RIGHT_NEAR, LANE_LINE_RIGHT_FAR,
  FREE_THROW_LINE_LEFT, FREE_THROW_LINE_RIGHT, THREE_POINT_STRAIGHT_LEFT_NEAR,
  THREE_POINT_STRAIGHT_LEFT_FAR, THREE_POINT_STRAIGHT_RIGHT_NEAR,
  THREE_POINT_STRAIGHT_RIGHT_FAR, OTHER_STRAIGHT_1..OTHER_STRAIGHT_6
- `endpoints`: the two ends of the LONGEST contiguous VISIBLE segment of that marking.
  A tie is broken topmost, then leftmost. Occlusion (player, official, graphic, blur)
  ENDS the segment: never bridge it, never infer a court template, never extrapolate.
- `midpoint`: an interior point you locate INDEPENDENTLY by looking at the paint
  near the middle of that segment. Do not compute the average of your endpoints.
Curved markings (three-point arc, centre circle, restricted-area arc) are NOT straight
markings. Report only straight markings.

## State
Every context gets exactly one `state`:
- `VISIBLE` with 1 or 2 markings;
- `ABSENT` with an empty list when you are confident no straight painted marking is visible;
- `UNKNOWN` with an empty list when you genuinely cannot tell.
`reason` is one short ASCII phrase. Uncertainty must be recorded, never guessed away.

## Output schema
{
  "opaque_id": "G387_001",
  "state": "VISIBLE",
  "reason": "two lane lines legible in tile5",
  "displayed": {"tile_width": 640, "tile_height": 540},
  "markings": [
    {"physical_marking_id": "SIDELINE_NEAR", "tile": 5,
     "endpoints": [[x1,y1],[x2,y2]], "midpoint": [mx,my]}
  ]
}
ASCII only. JSON files only, no notes, no summary file.
