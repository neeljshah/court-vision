# Wave 6E clustering diagnosis

## Input identity gate

The requested staged 1080p Giants-Jets section could not be reproduced on the
live pod. At the time of this run, the named staged file reported `1280x720`
via `ffprobe`, not 1920x1080. The bounded 120-position diagnostic therefore
measured 120 decoded samples, 55 field views, 55 LSD survivors, zero uniform
yard families, and 55 numeral candidates. It is not an after-table for the
reported 1080p run (118 decoded, 68 field, 68 LSD, 0 yard, 68 numeral).

## Ten-frame trace

The diagnostic saved ten JSON traces and five-plus overlays outside the repo
under the diagnostic work directory. On its first field frame (source frame
485), the stages were:

| Stage | Measured value |
| --- | ---: |
| Raw LSD segments | 1,955 |
| Length survivors | 50 (minimum 106.667 px) |
| Largest 8 degree angle group | 38 |
| Merged fitted lines | 26 (8 px merge threshold) |
| Uniform yard family | 0 |

The first cross-ratio was 2.365, versus 1.333 plus or minus 0.133. The overlay
shows that the largest angle group includes the ESPN lower-third and frame
borders. Thus the exact killing criterion is
`field_gates.py:88`: every consecutive quadruple must lie within the 10 percent
cross-ratio tolerance. It correctly rejects the contaminated candidate family;
the fixed 8 px merge at `geometry.py:148` is not the observed killer.

## Result

No clustering acceptance rule was relaxed. A general fix needs a repeatable
field-ROI/paint-support candidate extractor plus robust consensus selection,
then the same 1920x1080 input must be restored and remeasured. The line-DLT,
NFL 6-ft scale, adapter, and frozen-harness gates remain uninvoked.
