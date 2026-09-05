# G288: Description of G287 graphic and floor footpoint crops

## Verdict

ACCEPT, descriptive refinement only.  The selected G287 categories match the
committed verdicts exactly: 13 D (broadcast graphic or score ticker) and 17 C
(bare court or floor), for 30/72 selected detector-box observations.  Both
selected categories had blank original `detail` fields.

The G287 graphic category is overlay furniture: all 13/13 D footpoints are D1
overlays, so the spatial-histogram reasoning that inferred court-surface
decoration was wrong for this fixed sample.

The C breakdown is C1 plain unmarked court 14/17, C2 painted line or arc 1/17
(0.059), C3 painted floor decoration 1/17, C4 outside-court floor 0/17, and C5
cannot tell 1/17.  C2 is not a material share in this 17-observation C subset:
it is one footpoint only.  D is D1 overlay 13/13, D2 court-surface decoration
0/13, D3 physical courtside object 0/13, and D4 cannot tell 0/13.

The denominators are 30 selected detector-box observations (17 C and 13 D)
from G287's fixed 72 detector-box observations, one shot of one clip, one
detector draw, and one labeller.  They are not authenticated players.  This is
the same labeller as G273 and G287, so it is descriptive refinement rather
than independent validation.

## Inputs and local execution

Everything ran locally in `C:\Users\neelj\nba-track-a5`.  No pod, decode,
re-detection, re-render, re-sampling, re-cropping, `src/`, or `domains/` path
was touched.  The committed G287 verdict input was
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g287_unconditioned_footpoint_content_artifact\blind_verdicts.csv`
(1,494 bytes, SHA-256
`7df58afc23e26429f8b91ef1b09a9a48bb14846dd91119f7135e0b1aa066c637`).

The 30 JPEGs opened for this pass are the exact committed files under
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g273_detector_precision_blind_sample_artifact\blind_renders\`.
Their individual full paths, byte sizes, SHA-256 values, and native dimensions
are in
`docs/evidence/tracking/g288_describe_graphic_and_floor_crops_artifact/input_manifest.csv`:
1,546,820 bytes total, all 512x640.  The refinement rows are in
`docs/evidence/tracking/g288_describe_graphic_and_floor_crops_artifact/refined_rows.csv`;
the additive summary is
`docs/evidence/tracking/g288_describe_graphic_and_floor_crops_artifact/measurement_summary.json`.

The additive local validation route is
`scripts/platformkit/tracking/g288_describe_graphic_and_floor_crops.py`
(6,287 bytes, SHA-256
`81a86f6e622fcfac91b92865fbcf3e0b28f27ebcbd14b21938daa27a34f77c90`).
It selects G287's complete 17 C and 13 D sets; rejects any changed original
category, missing or duplicate selected row, incompatible subtype, or blank
G288 free text; and writes the summary and input manifest.

## Per-crop descriptive refinement

G287 categories below are reproduced unchanged.  Every row has a new short
description of the point at the centre cross, not a claim about what a
detector box contained.

| G287 order | JPEG | Unchanged category | Refined point category | Free text |
| ---: | --- | --- | --- | --- |
| 2 | blind_070.jpg | D | D1 | Centre cross is on the ESPN score strip and bonus indicator. |
| 3 | blind_022.jpg | C | C1 | Centre cross is on plain grey playing-court surface above the overlay. |
| 4 | blind_054.jpg | D | D1 | Centre cross is on the ESPN score strip over the spectators. |
| 6 | blind_057.jpg | C | C1 | Centre cross is on unmarked black painted playing-court surface. |
| 7 | blind_040.jpg | C | C2 | Centre cross is on the white midcourt line. |
| 16 | blind_007.jpg | C | C1 | Centre cross is on plain grey playing-court surface. |
| 19 | blind_004.jpg | D | D1 | Centre cross is on the lower ESPN score and clock strip. |
| 20 | blind_043.jpg | C | C1 | Centre cross is on plain reflective grey court near the sideline. |
| 23 | blind_008.jpg | C | C1 | Centre cross is on plain grey playing-court surface inside the arc. |
| 25 | blind_017.jpg | D | D1 | Centre cross is on the Indiana score panel in the lower overlay. |
| 28 | blind_024.jpg | D | D1 | Centre cross is on the Indiana score panel in the lower overlay. |
| 31 | blind_005.jpg | C | C1 | Centre cross is on plain grey playing-court surface above the overlay. |
| 32 | blind_045.jpg | D | D1 | Centre cross is on the lower ESPN promotional ticker. |
| 34 | blind_037.jpg | D | D1 | Centre cross is on the lower ESPN matchup ticker. |
| 35 | blind_028.jpg | C | C1 | Centre cross is on plain grey playing-court surface. |
| 41 | blind_035.jpg | D | D1 | Centre cross is on the lower ESPN promotional ticker. |
| 46 | blind_036.jpg | D | D1 | Centre cross is on the Indiana score panel in the lower overlay. |
| 47 | blind_006.jpg | C | C1 | Centre cross is on plain reflective grey court near the sideline. |
| 49 | blind_030.jpg | C | C5 | Centre cross appears on a seated spectator rather than a floor feature. |
| 54 | blind_026.jpg | C | C1 | Centre cross is on plain grey playing-court surface beside the paint. |
| 58 | blind_053.jpg | C | C1 | Centre cross is on plain grey court inside the sideline. |
| 60 | blind_011.jpg | C | C1 | Centre cross is on unmarked black painted playing-court surface. |
| 62 | blind_027.jpg | D | D1 | Centre cross is on the lower ESPN score and clock strip. |
| 63 | blind_038.jpg | D | D1 | Centre cross is on the Atlanta score and clock strip. |
| 65 | blind_034.jpg | C | C1 | Centre cross is on unmarked black painted playing-court surface. |
| 67 | blind_056.jpg | C | C1 | Centre cross is on plain grey playing-court surface beside the paint. |
| 68 | blind_015.jpg | C | C1 | Centre cross is on plain grey playing-court surface beside the paint. |
| 70 | blind_061.jpg | D | D1 | Centre cross is on the Indiana score panel in the lower overlay. |
| 71 | blind_060.jpg | C | C3 | Centre cross is on painted Indiana floor lettering in the lane. |
| 72 | blind_046.jpg | D | D1 | Centre cross is on the lower ESPN promotional ticker. |

## Label stability observation

`blind_030.jpg` remains G287 category C without alteration.  At full crop
resolution its centre cross appears to meet a seated spectator's head rather
than a floor feature, so it is recorded as C5 and as one descriptive
label-stability observation; it is not silently reclassified.

## Limits and NOT VERIFIED

- This is 30 crops from one shot of one clip and one detector draw, reviewed by
  one labeller who also labelled G273 and G287.  It is not independent
  validation or inter-labeller reliability.
- A footpoint is a point.  This pass says what the centre cross appears to be
  on, never what a bounding box contained.
- Per G278, this span is measurably friendlier than the clip: 0.836 against
  0.656, p = 0.0078.  It is not clip-wide.
- Not verified: replication across clips, shots, detector draws, arenas,
  sports, or labellers; the reason G287 labels were assigned; any detector-box
  extent; any population rate beyond the selected rows; any causal link from
  the single C2 line point to calibration; and any filter, threshold, gate,
  retrain, or production change.

## Verifier-contract self-check

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`.  B1: all 30
members of the named 17 C plus 13 D selection are retained, including C5 and
zero-count subtypes.  B2-B6: only additive evidence and a local reader were
added; no schema reader, lifecycle, deployment, move, or production path
changed.  B7: the selection is the full G287 C/D decision set, not a head
slice.  B8: no fit or residual is claimed.  B9: every unit is one selected
detector-box observation, not a player identity.  B10: no threshold, gate, or
bar exists or moved.  Q does not apply.  The new route is 155 lines and the
focused test is 55 lines, below the 300-line rail; A12 requires no allowlist
change.

```text
python -m pytest scripts/platformkit/tracking/test_g288_describe_graphic_and_floor_crops.py -q -p no:cacheprovider
2 passed
```
