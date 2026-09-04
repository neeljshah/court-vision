# G285b Pass A: marker-blind visible-player foot locating

This is the Pass A protocol for `G285b_spec.md`. It is intentionally limited
to the raw JPEGs and the G284 count-status field used to form the sampling
universe. No G267 measurement record, G270 result, marker render, detector
footpoint, box, or detection count is opened or displayed during Pass A.

## Frame selection

The universe is the 54 `COUNTED` rows in
`docs/evidence/tracking/g284_detector_recall_bound_artifact/per_frame_join.csv`.
Rows were sorted by numeric `source_frame`. Selection is the inclusive,
evenly spaced 15-point index grid
`round_half_away_from_zero(i * 53 / 14)` for `i = 0..14`; it produces the
following source frames and has no head slice:

| i | sorted index | source frame | raw JPEG |
| ---: | ---: | ---: | --- |
| 0 | 0 | 19630 | part_a_000.jpg |
| 1 | 4 | 19879 | part_a_004.jpg |
| 2 | 8 | 20190 | part_a_009.jpg |
| 3 | 11 | 20440 | part_a_013.jpg |
| 4 | 15 | 20689 | part_a_017.jpg |
| 5 | 19 | 20938 | part_a_021.jpg |
| 6 | 23 | 21187 | part_a_025.jpg |
| 7 | 27 | 21499 | part_a_030.jpg |
| 8 | 30 | 21686 | part_a_033.jpg |
| 9 | 34 | 21935 | part_a_037.jpg |
| 10 | 38 | 22247 | part_a_042.jpg |
| 11 | 42 | 22496 | part_a_046.jpg |
| 12 | 45 | 22683 | part_a_049.jpg |
| 13 | 49 | 22994 | part_a_054.jpg |
| 14 | 53 | 23368 | part_a_060.jpg |

## Tiling and locate rule

Each 1920x1080 source JPEG is inspected at native resolution in a 3 columns
by 2 rows grid. Core cells are 640x540 pixels. Each crop extends 80 pixels
past an internal core edge: x ranges are [0, 720), [560, 1360), and
[1200, 1920); y ranges are [0, 620) and [460, 1080). Thus neighbouring
crops overlap by 160 pixels. The overlap makes a player at a seam visible in
both crops; it is logged exactly once by assigning its recorded foot coordinate
to the half-open 640x540 core cell containing that coordinate. The
`core_tile` field in the coordinate CSV is that assignment, not a second
count.

For every visibly on-court player, record one best visual estimate of the
foot/ground-contact coordinate in source-image pixels. Do not record bench,
sideline, crowd, officials, or a player not visibly on the court. `player_id`
is only a within-frame audit ordinal, ordered by core tile (top row then bottom
row, left to right) and then x within the core; it is not an authenticated
identity. This eye locating is the only eye measurement in G285b.

## Predeclared Pass B rule

After all coordinates are committed, arithmetic matching will use Euclidean
source-pixel distance between every recorded visible-player foot and every
G270-on-court G267 footpoint in the same frame. The primary radius is fixed
now at 50 pixels. The sensitivity report will additionally use 25 and 100
pixels. A located player is matched when at least one footpoint lies within the
stated radius; a footpoint is unmatched when it lies outside that radius from
every located foot. No person or footpoint match will be judged by eye.
