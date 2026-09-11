# G396 known-band control instruction (identical for every rater)

You are a blind pixel rater. You see images only. There is no retry.

## Your batch

Your batch file lists one control per line as
`CONTROL_ID<TAB>IMAGE_PATH<TAB>TILE_INDEX<TAB>OFFSET_X<TAB>OFFSET_Y<TAB>DISPLAY_WIDTH<TAB>DISPLAY_HEIGHT`.

For EVERY line write exactly one JSON file `<CONTROL_ID>.json` into your output
directory. A line you cannot answer still gets a file, with state `UNKNOWN`.
Open and look at every listed image, one at a time. Never open a contact sheet.

## The image

Each image is a lossless `DISPLAY_WIDTH` x `DISPLAY_HEIGHT` (640 x 540) crop of a
1920 x 1080 broadcast frame. `OFFSET_X` and `OFFSET_Y` are the integer position of
that crop inside the 1920 x 1080 frame. Do not rescale anything.

Report TILE-LOCAL coordinates: x in 0..639 counted rightward from the left side of
the image you opened, y in 0..539 counted downward from the top side of the image
you opened. Also report the NATIVE coordinates, which are exactly
`native_x = x + OFFSET_X` and `native_y = y + OFFSET_Y`.

Report the width and height you actually observed when you opened the file.

## The target

Exactly one target: the bright WHITE straight band with a black outline drawn over
the photograph. It is about 240 px long and about 6 px wide. Its position inside
the image is different for every control; never assume it is centred.

## What to report -- THREE POINTS ON THE BAND

Do NOT report endpoints. Do NOT report a length. Report three points that each lie
ON the white band, anywhere along it:

- `p1` and `p2`: two points on the band, separated by at least 60 px.
- `p3`: a third point on the band that you locate INDEPENDENTLY by looking at the
  pixels between `p1` and `p2`. It must lie strictly between them along the band.
  Do NOT average `p1` and `p2`; an arithmetic midpoint is not an observation.

Each point must sit on the white paint itself, not on the black outline beside it.
Where the band stops does not matter and is not scored.

If you cannot find the band, use state `UNKNOWN` with an empty `points` object.
Never guess.

## Output schema

```
{
  "control_id": "G396_PRACTICE_001",
  "state": "VISIBLE",
  "reason": "white band on dark floor",
  "opened_path": "C:/.../G396_PRACTICE_001.png",
  "opened_width": 640,
  "opened_height": 540,
  "tile": 3,
  "offset": [1280, 0],
  "coords": "tile",
  "points": {"p1": [x1, y1], "p2": [x2, y2], "p3": [x3, y3]},
  "native_points": {"p1": [X1, Y1], "p2": [X2, Y2], "p3": [X3, Y3]}
}
```

ASCII only. JSON files only, no notes, no summary file, no other output.

## Frozen rater-side correction (exactly one, recorded before qualification)

none requested
