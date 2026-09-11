# G387 known-position control instruction (CONTROL pass; identical for both raters)

This pass uses the IDENTICAL clicking protocol as the real pass. No feedback on any
earlier answer is given and none may be sought. Do not retry or recalibrate.

## Your batch
Your batch file lists one image per line as `OPAQUE_ID<TAB>IMAGE_PATH`. For EVERY
line write exactly one JSON file `<OPAQUE_ID>.json` into your output directory.

## Geometry
Each image is a lossless 640x540 native tile of a 1920x1080 broadcast frame. Its
fixed NATIVE offset is given by its tile index: 1 (0,0) 2 (640,0) 3 (1280,0)
4 (0,540) 5 (640,540) 6 (1280,540). The image file name does NOT give the index;
determine it from the batch line field `TILE_INDEX` when present, otherwise report
TILE-LOCAL coordinates and set `"coords": "tile"`.

## What to report
Exactly one target: the bright WHITE straight band with a black outline that is drawn
over the photograph. It is a single straight band about 240 px long. Report:
- `endpoints`: its two ends, in the order left-to-right; if it is vertical, top-to-bottom.
- `midpoint`: an interior point on the band that you locate INDEPENDENTLY by looking at
  the band near its middle. Do not average the endpoints.
If you cannot find the band, use state `UNKNOWN` with an empty list. Never guess.

## Output schema
{
  "opaque_id": "G387_001",
  "state": "VISIBLE",
  "reason": "white band on dark floor",
  "coords": "tile",
  "markings": [{"physical_marking_id": "CONTROL_BAND", "tile": 0,
                "endpoints": [[x1,y1],[x2,y2]], "midpoint": [mx,my]}]
}
ASCII only. JSON files only, no notes, no summary file.
