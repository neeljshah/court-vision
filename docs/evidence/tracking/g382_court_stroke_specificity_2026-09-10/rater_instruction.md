# G382 blind marking-trace instruction (identical for both raters)

You are annotating basketball broadcast still frames. You have NO access to any
detector, extractor, stroke, score, or another rater's work, and you must not
look for any. Work only from the image pixels.

## Your batch
Your batch file lists one sheet per line as `OPAQUE_ID<TAB>ABSOLUTE_PATH`.
For EVERY line, open the image and write exactly one JSON file to your output
directory named `<OPAQUE_ID>.json`. Do not skip a line. Do not write anything else.

## Image
Every sheet is 1920 wide by 1080 high. All coordinates are native integer pixels
with 0 <= x <= 1920 and 0 <= y <= 1080.

## What to trace
`painted_markings` = every PAINTED STRAIGHT line marking of the basketball court
that you can actually see in this image. Trace the outline of the visible painted
BAND (not a centreline) as a polygon of 4 or more points.
Curved markings (the three-point arc, the centre circle, the restricted-area arc)
are NOT straight markings; do not trace them. Trace only the straight portions.
If no painted straight court marking is visible at all, use an empty list.

`physical_marking_id` must be exactly one value from this closed list, used at
most once per image:
SIDELINE_NEAR, SIDELINE_FAR, BASELINE_LEFT, BASELINE_RIGHT, CENTRE_LINE,
LANE_LINE_LEFT_NEAR, LANE_LINE_LEFT_FAR, LANE_LINE_RIGHT_NEAR,
LANE_LINE_RIGHT_FAR, FREE_THROW_LINE_LEFT, FREE_THROW_LINE_RIGHT,
THREE_POINT_STRAIGHT_LEFT_NEAR, THREE_POINT_STRAIGHT_LEFT_FAR,
THREE_POINT_STRAIGHT_RIGHT_NEAR, THREE_POINT_STRAIGHT_RIGHT_FAR,
OTHER_STRAIGHT_1, OTHER_STRAIGHT_2, OTHER_STRAIGHT_3, OTHER_STRAIGHT_4,
OTHER_STRAIGHT_5, OTHER_STRAIGHT_6

## What to mask
`mask_regions` covers the NON-court content. Label is exactly one of
STANDS, LED, SCORE_BUG, OTHER, UNREADABLE:
- STANDS: crowd, seating, spectators.
- LED: illuminated advertising boards and ribbon displays.
- SCORE_BUG: the broadcast score or clock graphic overlay.
- OTHER: players, officials, benches, floor logos, tunnels, equipment, walls.
- UNREADABLE: regions too blurred, dark or motion-smeared to judge.
Cover as much of the image as you can judge. Pixels you leave uncovered are
recorded as UNKNOWN, which is correct when you truly cannot tell.

## Hard geometry rule
No polygon may overlap any other polygon in the same file - not two painted
markings, not two mask regions, not a painted marking and a mask region.
Where two markings meet, stop each polygon short of the intersection.

## Exact output schema
{
  "frame_key": "<OPAQUE_ID>",
  "image": {"width": 1920, "height": 1080},
  "painted_markings": [
    {"physical_marking_id": "SIDELINE_NEAR", "polygon": [[x,y],[x,y],[x,y],[x,y]]}
  ],
  "mask_regions": [
    {"label": "STANDS", "polygons": [[[x,y],[x,y],[x,y],[x,y]]]}
  ]
}

Write only JSON files. No notes, no summary file, no commentary in the files.
