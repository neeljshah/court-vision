# G161 Rally-View Census

## Result

The local reference clip was sampled at 300 seeded, evenly spaced frame indices. The first pass labeled 113 of 300 frames `RALLY_VIEW`: 37.67% (Wilson 95% CI 32.37% to 43.27%). The clip's rally-view coverage is therefore far below 0.90. This record does not propose lowering that bar.

The estimate is compatible with the prior independent-clip reference in `g34_view_share_and_denominator_2026-09-02.md`: 125 of 300 (41.7%, Wilson 95% CI 36.2% to 47.3%). The two intervals overlap.

## Fixed sampling and label rule

`PROTOCOL.md` was fixed before first-pass review. The source is the local `data/videos/reference/tennis.mp4` frame extent 0 through 28772. Seed `16120260903` selected phase 56 in a 95/96-frame systematic spacing. `sample_manifest.csv` contains all 300 ordinal/index pairs; first index 56, last index 28733. This is a whole-clip systematic sample, not a head slice.

The exact label rule, including treatment of replays, closeups, crowd shots, scoreline overlays, and serve preparation, is quoted in `PROTOCOL.md`. The local video was opened and sequentially decoded to the sample's final frame while producing the review material; no remote host or pod was used.

## Labels and blind re-label agreement

`labels_pass1.csv` contains all 300 first-pass labels and was flushed in 30-row chunks. `pass2_selection.csv` selects source ordinals 1, 7, ..., 295 (50 frames, evenly spaced every sixth first-pass sample). The second pass used label-free renders and did not open the first-pass label file before labels were written to `labels_pass2_blind.csv` in two 25-row chunks.

The second pass agreed with the first in 49 of 50 frames: 98.0% (Wilson 95% CI 89.50% to 99.65%). The one disagreement is frame 1206: first pass `RALLY_VIEW`, blind pass `NOT_RALLY`. This is same-rater repeat agreement, not independent validation.

## Rally-normalised recomputation

The rally denominator is estimated from the sample share over the 28,773-frame exact clip: 10,837.8 frames (95% CI 9,314.4 to 12,451.0). The fixed G152b local numerators are 2,597 declaration frames and 1,350 distinct geometry-usable frames. Dividing those counts by the estimated rally denominator gives:

| Measure | Estimate | 95% interval |
| --- | ---: | ---: |
| Declaration coverage among rally-view frames | 23.96% | 20.86% to 27.88% |
| Geometry-usable coverage among rally-view frames | 12.46% | 10.84% to 14.49% |

These intervals propagate only the Wilson uncertainty of the sampled rally denominator (the G152b numerators are treated as fixed audit counts). Neither rate is close to 0.90.

## Representative renders

Eight renders, selected at source ordinals 1, 44, 87, 130, 173, 216, 259, and 300, cover the labeled set from beginning to end. Five are `NOT_RALLY`, satisfying the required non-rally examples. They are stored in `renders/`.

## Verifier Contract section B self-check

| Check | Self-check |
| --- | --- |
| B1, circular metric | Pass. Labels are view classifications; they did not use declaration or geometry outputs. |
| B2, schema/reader change | Pass. Evidence CSVs only; no production schema or reader changed. |
| B3, missingness treated as bad | Pass. `NOT_RALLY` is a camera-view label, not a failure label. |
| B4, reclaim loop | Pass. This census makes no eligibility or reclaim decision. |
| B5, pod pre-verification/deploy | Pass. Local file only; no SSH, pod access, deployment, or feature flag action. |
| B6, orphan production module | Pass. No production module was added. |
| B7, head-slice sampling | Pass. Seeded systematic whole-clip sample, 95/96-frame gaps. |
| B8, self-fit presented as independent | Pass. The same-rater repeat is labeled agreement only, not independent validation. |
| B9, degenerate denominator | Pass. 113 rally labels out of 300 with a reported Wilson interval. |
| B10, threshold moved | Pass. The 0.90 bar is unchanged and plainly missed. |

## Verification

No production code was added, so no pytest target was applicable. No full pytest run was made. The local integrity check verified 300 unique manifest indices, matching first-pass coverage, 50 unique blind-pass indices, a 49/50 label agreement count, and eight evidence renders.
