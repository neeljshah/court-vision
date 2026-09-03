# G141 direct corner proposal and scoring protocol

## Fixed input and denominator

The only scored input is G140's unchanged
`../g140_corner_targets/corner_pixel_targets.csv`: 68 unique
`(clip, source_frame, role)` target keys on 17 fixed source frames. Every
target row remains in the denominator. Source images are resolved only through
each row's committed `source_decode` path. No G140 target, G136 census,
detector or grouping parameter, threshold, coordinate contract, or
`line_calibration.py` input is modified.

## Preregistered tolerance

The native-image Euclidean match tolerance is **12.0 pixels**. This is fixed
before G141 output is generated. G140 independently measured a 10.971927 px
median and 11.392950 px p90 blind re-labelling displacement. A tolerance below
roughly 11 px would score target-placement noise rather than the proposal, so
12.0 px is the smallest whole-pixel tolerance above that p90 floor. It will
not be changed after measurement.

## Fixed simple proposal

The proposal is OpenCV Harris `goodFeaturesToTrack` on the full native source
image after BGR-to-grayscale conversion. It is a local corner response only:
it has no learned component and does not call a line detector, line grouping,
role assigner, homography, `line_calibration.py`, or any production module.

- `maxCorners=100`
- `qualityLevel=0.01`
- `minDistance=10` native pixels
- `blockSize=5`
- `useHarrisDetector=True`
- `k=0.04`

The generic local proposals are not role-labelled. A target is available when
at least one proposal is within 12.0 px. Per-role recall is therefore measured
against the named G140 target roles without inventing a role mapping. Proposal
precision counts every proposal once and marks it true only when it is within
12.0 px of any committed target in its own source frame; repeated nearby
proposals remain precision false or true individually and are never removed.

Recall and precision Wilson intervals use z=1.959963984540054. The
like-for-like availability count is the number of detected G140 target roles
out of 68, directly comparable in unit type to G138's available role units.

## Render selection

Renders are fixed before output review. Lexically sorted G140 audit IDs at
positions `0, 3, 5, 8, 10, 13, 16` are rendered, spanning the complete
17-frame decision set instead of taking a head slice. Each overlay shows all
100-or-fewer local proposals and all four committed targets.

## Scale context

The measurement records, for every frame, the 12 px conversion along each
labelled baseline-to-free-throw side using that side's committed 19-foot paint
depth. This is descriptive scale context only; it is not a court-coordinate
output, calibration, or a detector input.
