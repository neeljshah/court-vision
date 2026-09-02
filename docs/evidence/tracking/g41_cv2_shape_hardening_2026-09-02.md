# G41: OpenCV Hough result shape hardening

Date: 2026-09-02

## Scope

OpenCV 4 Hough output is `(N, 1, 4)` while OpenCV 5 may return `(N, 4)`.
Every genuine `HoughLinesP` parser in this worktree now normalizes only the
result layout with `result.reshape(-1, result.shape[-1])`. No Hough threshold,
minimum line length, maximum line gap, contrast, kernel size, or gate changed.

## Premise reproduction

The local `basketball_ai` interpreter (`cv2=4.13.0`) ran `HoughLinesP` on a
zero mask containing one drawn line. It returned shape `(1, 1, 4)` and the
reproduction assertion `found.ndim == 3` passed.

## Enumerated Hough-result parsers (n = 15)

Active parsers:

1. `domains/tennis/tracking/court_lines.py:96`
2. `domains/soccer/tracking/geometry.py:101`
3. `domains/soccer/tracking/keypoints.py:50`
4. `domains/football/tracking/line_probe.py:45`
5. `scripts/platformkit/football_content_gate.py:53`
6. `scripts/platformkit/synthcal/solve.py:50-51`
7. `scripts/platformkit/tennis_camera_lock_measure.py:138`
8. `scripts/platformkit/tennis_metric_probe.py:68`
9. `scripts/platformkit/tracking/football_fieldview.py:68`
10. `scripts/platformkit/tracking/homography_eligibility.py:51`

Retired diagnostic parsers, hardened too so direct invocation cannot reproduce
the layout failure:

11. `scripts/platformkit/_retired/line_detector_ab.py:28`
12. `scripts/platformkit/_retired/tennis_gate_funnel.py:59`
13. `scripts/platformkit/_retired/tennis_resolution_anchor_ab.py:81`
14. `scripts/platformkit/_retired/tennis_threshold_sweep.py:76`
15. `scripts/platformkit/_retired/tennis_vertical_probe.py:42`

The source audit found no Hough invocation in three supplied paths:
`domains/football/tracking/geometry.py`,
`domains/football/tracking/clustering_diagnostic.py`, and
`domains/basketball/tracking/line_calibration.py`. They were not changed.
`domains/soccer/scoreline_engine.py` was not changed; `court_lines.py:221` is
a coordinate bounds check rather than a Hough result and was not changed.

## Fixed-frame before/after count

Corpus source: `C:\Users\neelj\nba-ai-system\data\footage_corpus\tennis__tennis_09.mp4`.
Frame: 6960. Interpreter: local `basketball_ai`, OpenCV 4.13.0.

| Metric | Before | After | Result |
|---|---:|---:|---|
| `court_line_segments(frame)` segment count | 106 | 106 | Equal |
| `detect_court(frame)` gate | `accepted` | `accepted` | Equal |

The only array transformation is a lossless flattening of the singleton middle
dimension for legacy Hough output, so the legacy raw segment ordering and
values reach every downstream parser unchanged.

## Regression test

New per-file test: `tests/domains/tennis/test_court_lines_cv2_shape.py`.
It first exercises installed OpenCV with a zero mask plus one line, then
monkeypatches the Hough call to feed both `(N, 1, 4)` and `(N, 4)` through
`court_line_segments`. The resulting ordered segment arrays are asserted equal.

```text
1 passed in 6.10s
```

Command:

```text
C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/domains/tennis/test_court_lines_cv2_shape.py -q
```

## Verifier-contract section B self-check

- B1: No metric excluded rows; the fixed frame and both parser layouts are named.
- B2: No schema, field, status, or reader changed.
- B3: No gate behavior changed; the fixed-frame gate remains `accepted`.
- B4: No claim or retry path changed.
- B5: No pod files were copied and no pod environment was modified.
- B6: No module moved or retired.
- B7: No render evidence is claimed.
- B8: No fitted residual is used as evidence.
- B9: The headline is the actual Hough segment count on one named frame, not a
  recycled identifier or constant denominator.
- B10: The diff changes only Hough-result layout indexing; all detection and
  gate parameters remain byte-identical.

## NOT VERIFIED

- The local `basketball_ai` environment is OpenCV 4.13.0, not the pod's stated
  OpenCV 4.14.0; the exact 4.14 fixed-frame reproduction was therefore not run.
  The pod was deliberately not accessed or changed.
- The fixed-frame before/after measurement is the required tennis reference
  parser. Site-specific corpus-frame counts for the other 14 parser sites were
  not collected; their OpenCV 4 behavior is covered by the lossless reshape and
  the two-layout parser regression test, not asserted as separate corpus runs.
