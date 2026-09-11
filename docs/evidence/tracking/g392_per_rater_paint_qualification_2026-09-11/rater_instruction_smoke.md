# G392 plumbing fixture (UNSCORED -- no rating, no geometry)

This is a permissions and image-access test only. Nothing here is scored and
nothing here is a control.

Your batch file lists one line as
`FIXTURE_ID<TAB>IMAGE_PATH<TAB>TILE_INDEX<TAB>OFFSET_X<TAB>OFFSET_Y<TAB>DISPLAY_WIDTH<TAB>DISPLAY_HEIGHT`.

Open the listed image. Then write exactly one JSON file `<FIXTURE_ID>.json` into
your output directory with this schema:

```
{
  "fixture_id": "G392_SMOKE",
  "opened": true,
  "opened_path": "C:/.../file.png",
  "opened_width": 640,
  "opened_height": 540,
  "offset": [OFFSET_X, OFFSET_Y],
  "note": "plumbing only"
}
```

Do not report any coordinate of anything drawn in the image. Do not rate.
ASCII only. One JSON file, no notes, no summary file, no other output.
