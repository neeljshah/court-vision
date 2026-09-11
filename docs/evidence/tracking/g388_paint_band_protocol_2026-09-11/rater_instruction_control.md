# G388 known-band control instruction (CONTROL pass; identical for both raters)

You are a blind pixel rater. You see images only. No feedback on any earlier answer
is given and none may be sought. There is no retry and no recalibration.

## Your batch
Your batch file lists one control per line as
`CONTROL_ID<TAB>IMAGE_PATH<TAB>TILE_INDEX`.
For EVERY line write exactly one JSON file `<CONTROL_ID>.json` into your output
directory. A line you cannot answer still gets a file, with state `UNKNOWN`.

## The image
Each image is a lossless 640x540 tile of a 1920x1080 broadcast frame. Report
TILE-LOCAL coordinates: x in 0..639 from the left calibration-only, y in 0..539 from the top
calibration-only of the image you are shown. Do not rescale anything.

## The target
Exactly one target: the bright WHITE straight band with a black outline drawn over
the photograph. It is about 240 px long and about 6 px wide.

## What to report -- THREE POINTS ON THE BAND
Do NOT report endpoints. Do NOT report a length. Report three points that each lie
ON the white band, anywhere along it:

- `p1` and `p2`: two points on the band, separated by at least 60 px.
- `p3`: a third point on the band that you locate INDEPENDENTLY by looking at the
  pixels between `p1` and `p2`. It must lie strictly between them along the band.
  Do NOT average `p1` and `p2`; an arithmetic midpoint is not an observation.

Each point must sit on the white paint itself, not on the black outline beside it.
Where the band ends does not matter and is not scored.

If you cannot find the band, use state `UNKNOWN` with an empty `points` list.
Never guess.

## Output schema
{
  "control_id": "G388_C001",
  "state": "VISIBLE",
  "reason": "white band on dark floor",
  "tile": 1,
  "coords": "tile",
  "points": {"p1": [x1, y1], "p2": [x2, y2], "p3": [x3, y3]}
}

ASCII only. JSON files only, no notes, no summary file, no other output.
