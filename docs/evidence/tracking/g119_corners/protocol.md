# G119 direct paint-corner proposal protocol

This protocol was recorded before running the G119 proposal generator or
reviewing its output. It reuses the committed G111 `frame_labels.csv` and the
corresponding 220 committed source renders exactly; it does not make a new
sample or alter any G111 visibility label.

## Fixed direct proposal

The proposal is a local Harris response via OpenCV `goodFeaturesToTrack` on a
grayscale, width-640 canonical image: `maxCorners=180`,
`qualityLevel=0.008`, `minDistance=8`, `blockSize=5`, Harris enabled, and
`k=0.04`. The 34-pixel G111 render title band is excluded before the canonical
resize because it is added evidence text rather than court imagery. This route
does not call line detection, grouping, role assignment, or
`line_calibration.py`.

## Preregistered localisation rule

If a committed G111 label provides a target `(x, y)` for a named visible paint
corner, a proposal matches it when its canonical-image Euclidean distance is at
most **16 pixels**. Sixteen pixels is fixed before output review: it is 2.5
percent of the canonical width, allowing a local response to land within the
visibly rasterised intersection rather than exactly on a one-pixel line
crossing. The same scaling applies to every original resolution.

Every named visible role remains in the denominator. The scorer must fail
closed if a visible role lacks a committed coordinate: a detector candidate,
its rank, or a human's post-hoc selection cannot become truth. Thus the
existing G111 visibility roles establish the denominator, while their location
is mandatory to calculate the requested localisation recall.

## Render audit

Diagnostic overlays use slots 2, 7, 12, and 17 from every one of the 11 G111
clips (44 frames total), rather than head frames. Each overlay shows the first
30 ranked local responses, while the raw proposal CSV retains all up to 180
responses per frame.
