# G388 real-paint instruction (REAL pass; identical for both raters)

You are a blind pixel rater. You see images only. No feedback on any earlier answer
is given and none may be sought. There is no retry and no recalibration.

## Your batch
Your batch file lists one context per line as
`CONTEXT_ID<TAB>TILE_PATH_1,TILE_PATH_2,...,TILE_PATH_6`.
The six tiles are given in fixed order: tile 1 (0,0) 2 (640,0) 3 (1280,0)
4 (0,540) 5 (640,540) 6 (1280,540) of one 1920x1080 broadcast frame.
For EVERY line write exactly one JSON file `<CONTEXT_ID>.json` into your output
directory. A line you cannot answer still gets a file, with state `ABSENT` or
`UNKNOWN` and an empty `fragments` list.

## The target
Painted straight court markings on the playing floor: the white or coloured PAINT
itself. Look at the tiles in the given order and report AT MOST TWO fragments for
the whole context. A fragment is a stretch of one painted band that you can
actually see in one tile. Ignore logos, sponsor text, wall or stanchion padding,
seating, clothing, and anything not painted on the floor.

## What to report per fragment -- THREE POINTS ON THE BAND
Do NOT report endpoints. Do NOT report a length. Where the visible stretch begins
and ends is NOT scored. Report three points that each lie ON the painted band:

- `p1` and `p2`: two points on the band, separated by at least 60 px.
- `p3`: a third point located INDEPENDENTLY by looking at the pixels between `p1`
  and `p2`. It must lie strictly between them along the band. Do NOT average `p1`
  and `p2`; an arithmetic midpoint is not an observation.

Report TILE-LOCAL coordinates (x in 0..639, y in 0..539 of that tile image) and the
tile number the fragment was seen in. Do not rescale anything.

## Family
Give each fragment one `family` from exactly this list, with no left/right and no
near/far orientation:
SIDELINE, BASELINE, CENTRE_LINE, LANE_LINE, FREE_THROW, THREE_POINT_STRAIGHT,
UNKNOWN.
Use UNKNOWN when you can see paint but cannot name which marking it is. Never guess
a family to avoid UNKNOWN.

## Output schema
{
  "context_id": "G388_001",
  "state": "VISIBLE",
  "reason": "wide shot, lane and baseline paint legible",
  "coords": "tile",
  "fragments": [
    {"tile": 4, "family": "BASELINE",
     "points": {"p1": [x1, y1], "p2": [x2, y2], "p3": [x3, y3]}}
  ]
}

States: `VISIBLE` (one or two fragments reported), `ABSENT` (no painted floor
marking is visible in any tile), `UNKNOWN` (you cannot tell). ASCII only. JSON
files only, no notes, no summary file, no other output.
