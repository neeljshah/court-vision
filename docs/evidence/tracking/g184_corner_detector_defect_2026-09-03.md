# G184: tennis corner-detector rejection diagnosis

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A3, A7, B1-B10, Q8). Diagnosis only: no production source, threshold, gate, solver constant, coordinate contract, bar, or verdict changed.

The additive, read-only observer is `scripts/platformkit/tracking/g184_corner_detector_defect.py`; its focused test is `scripts/platformkit/tracking/test_g184_corner_detector_defect.py`. The complete per-frame artifact is [g184_observation.json](g184_corner_detector_defect/g184_observation.json): 350 records, both contrast attempts, observed gate values, source identity, eligible denominator, and A3 position. The source-specific JSON files are retained alongside it.

## Q8 premise first

Before writing the observer, I decoded raw `docs/evidence/demo/tennis.mp4` sequentially through frame 149. It is 720 x 1280; unchanged `TennisAdapter.detect_court_corners` returned `None`, and direct `detect_court(frame)` returned `horizontal_roles`. This reproduces G182b's premise without using its burned-in render.

## Chain and reject inventory

`detect_court_corners` delegates directly to the corner path:

```python
# domains/tennis/tracking/adapter.py:116-122
def detect_court_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
    return detect_court(frame)[1]
```

`detect_court` tries the unchanged contrasts 45 then 60. An accepted attempt returns; otherwise the production return gate is the **last** attempt's first reject.

```python
# domains/tennis/tracking/court_lines.py:245-261
for contrast in TOPHAT_CONTRASTS:
    segments = court_line_segments(frame, contrast=contrast)
    if not segments:
        gate = "no_hough_lines"
        continue
    court, gate = select_court_lines(segments, shape)
    if court is None:
        continue
    corners, gate = solve_corners(court, shape)
    if corners is not None:
        return court, corners, "accepted"
return None, None, gate
```

For the requested distribution, `first_attempt_gate` is the first explicit reject in contrast 45. Every record also preserves `terminal_gate`, the existing contrast-60 final return. Frame 149 is `horizontal_roles` on both attempts, so the located gate is unambiguous.

| Gate | Explicit reject predicate / unchanged threshold |
|---|---|
| `no_hough_lines` | `HoughLinesP` is `None`; Hough threshold 45, minimum length `max(40, width // 12)`, max gap 20, at current contrast. |
| `insufficient_oriented_lines` | Horizontal `< 2` or vertical `< 2`; horizontal means `abs(dx) >= 1.5 * abs(dy)`, vertical `abs(dy) > abs(dx)`. |
| `vertical_cluster_count` | Horizontal clusters `< 4` or vertical clusters `< 5`. The gate name covers both predicates. |
| `cross_ratio` | Across-court `_match`: position count below 5 or above 14, or no combination with max cross-ratio deviation `<= 0.05`. |
| `horizontal_roles` | Each 5/4/4-role template rejects on count below its arity or above 14, no subset inside every dynamic role window, or max cross-ratio deviation `> 0.05`. One template must match. |
| `depth_order` | A required intersection is `None`, or strict `far_left_y < service_y < near_left_y` fails. |
| `homography` | `cv2.findHomography(...) is None`. |
| `skew` | `depth <= 0.0` or far y difference `> 0.25 * depth`. |
| `image_bounds` | Any coordinate `< -5`, x `> width + 5`, or y `> height + 5`. |
| `far_right_consistency` | Observed far/right is `None`, or distance from prediction `> 0.02 * width`. |

The observer mirrors control flow only in its measurement process, then asserts its terminal gate against a second untouched `detect_court(frame)` call. It does not monkeypatch the module under test.

## Frame 149: first failing gate

**`horizontal_roles` is the first failing gate.** Both contrasts pass orientation, cluster count, and the across-court cross-ratio match. The failure is the role-window predicate, not the 0.05 cross-ratio tolerance. No solver gate was reached, so later values are correctly recorded as unreached rather than invented.

| Contrast | Gate / observed value | Threshold | Result |
|---:|---|---|---|
| 45 | orientation: 51 horizontal, 27 vertical | both >= 2 | pass |
| 45 | clusters: 9 horizontal, 7 vertical | horizontal >= 4; vertical >= 5 | pass |
| 45 | across: closest max deviation 0.0039217361 | <= 0.05 | pass |
| 45 | **roles: 6 candidate rows; 0 window-eligible combinations for each 5/4/4 template** | >= 1 matching subset, <= 0.05 | **reject** |
| 60 | orientation: 39 horizontal, 26 vertical | both >= 2 | pass |
| 60 | clusters: 6 horizontal, 7 vertical | horizontal >= 4; vertical >= 5 | pass |
| 60 | across: closest max deviation 0.0052654118 | <= 0.05 | pass |
| 60 | **roles: 3 candidate rows; template arities 5, 4, 4; 0 window-eligible combinations** | count >= 5/4/4 and >= 1 match | **reject** |

Thus a raw frame known to carry the full court is rejected because the selected horizontal evidence does not occupy any full legal role-window subset. This is a real one-frame detector limitation. It does not show that the detector is generally broken.

## Required first-failure distributions

Demo is exhaustive: all 150 decoded source frames, indices 0..149. The pod population is the committed G182 set of 26,113 unique source frames with `enough_corners=false`. Its 200 observation positions are inclusive `floor(linspace(0, 26112, 200))`, with all resulting indices in the JSON. This is A3 even sampling, not a head slice.

Every row names its eligible denominator. Pod entries are counts in the fixed observation sample relative to the 26,113 named eligible frames, not an estimated full-population rate.

| Population / first-attempt gate | Observed records / eligible denominator |
|---|---:|
| demo: `vertical_cluster_count` | 121 / 150 |
| demo: `horizontal_roles` | 14 / 150 |
| demo: `cross_ratio` | 10 / 150 |
| demo: `skew` | 4 / 150 |
| demo: `insufficient_oriented_lines` | 1 / 150 |
| G182 corner-loss: `insufficient_oriented_lines` | 100 / 26,113 |
| G182 corner-loss: `far_right_consistency` | 49 / 26,113 |
| G182 corner-loss: `vertical_cluster_count` | 34 / 26,113 |
| G182 corner-loss: `horizontal_roles` | 10 / 26,113 |
| G182 corner-loss: `skew` | 3 / 26,113 |
| G182 corner-loss: `cross_ratio` | 2 / 26,113 |
| G182 corner-loss: `image_bounds` | 1 / 26,113 |
| G182 corner-loss: `no_hough_lines` | 1 / 26,113 |

The primary distribution is spread. `vertical_cluster_count` is pooled-modal (155 of 350 observed records), but the demo's modal gate is vertical clusters while the pod sample's modal gate is orientation insufficiency. Therefore the evidence supports an imperfect detector and a located frame-149 defect, not one gate failing nearly every frame.

For transparency, terminal contrast-60 outcomes are in the JSON too: demo `vertical_cluster_count` 106, `insufficient_oriented_lines` 26, `horizontal_roles` 18 (each / 150); pod `insufficient_oriented_lines` 116, `far_right_consistency` 44, `horizontal_roles` 18, `vertical_cluster_count` 18, `no_hough_lines` 2, `cross_ratio` 1, `skew` 1 (each / 26,113).

## Modal-gate eye check

The pooled modal decision set has 155 `vertical_cluster_count` first-attempt records. Ordering demo source frame ascending, then pod A3 eligible position ascending, inclusive positions 0, 38, 77, 115, and 154 select these raw renders. **A human sees all four doubles corners in none of the five.**

| Pool position / eligible denominator | Source frame | Render | Eye observation |
|---:|---|---|---|
| 0 / 155 | demo 1 | [render](g184_corner_detector_defect/renders/demo_frame_00001_modal_vertical_cluster_count.jpg) | Crowd close-up; no corners. |
| 38 / 155 | demo 45 | [render](g184_corner_detector_defect/renders/demo_frame_00045_modal_vertical_cluster_count.jpg) | Crowd close-up; no corners. |
| 77 / 155 | demo 88 | [render](g184_corner_detector_defect/renders/demo_frame_00088_modal_vertical_cluster_count.jpg) | Player close-up; no corners. |
| 115 / 155 | demo 126 | [render](g184_corner_detector_defect/renders/demo_frame_00126_modal_vertical_cluster_count.jpg) | Player close-up; no corners. |
| 154 / 155 | pod 27,555 | [render](g184_corner_detector_defect/renders/pod_frame_27555_modal_vertical_cluster_count.jpg) | Player close-up; no corners. |

Demo frames were decoded from the raw MP4 (which itself contains pre-existing demo overlays); no G182b diagnostic render was used for the frame-149 measurement. The pod render was decoded from the read-only pod MP4.

## Environment and self-check

Local demo sources: adapter SHA-256 `f7687c5646dfa3f9a8206d1559238941020b6f5828d28c160e11426699a2bac9`; court-lines SHA-256 `0f0f3fa393c8a58320fe352d43ddb673fab515200b7cd8a4dd8fa5ec2f51bbe0`. Pod sources: adapter `c7314449ddccc9f27868ea5a20dbbe8458c96d9a4678b9597dc4b585708fcc58`; court-lines `799c1bf247f76d0579f78278b3f413f8f32791b158fb359e8db935909bd0c19b`; OpenCV 5.0.0. The sources differ, so distributions remain separate. The observer was process-only stdin on the pod; no remote file write, copy, daemon/keeper action, restart, kill, or deployment occurred.

- **A7:** memo, observer, test, JSON artifact, source JSON, and five linked renders are existence-checked before commit.
- **B1:** all 150 demo frames and all 200 fixed pod positions are retained; the full pod eligible set is named.
- **B2-B6:** clear: no production schema/control-flow/claim-loop/deployment/module move changed.
- **B7:** clear: demo exhaustive; pod and eye-check selections are inclusive, evenly spaced over named sets.
- **B8-B9:** clear: direct gate observation on unique source frames, no fitted residual or recycled denominator.
- **B10:** clear: observer imports constants and changes no threshold, solver, bar, coordinate contract, or verdict.

## NOT VERIFIED

- Any remedy, altered role window, threshold, contrast, Hough parameter, solver constant, coordinate contract, bar, or verdict.
- Full human geometry labels for all 26,113 pod corner-loss frames, or a rate of full-court detector misses in either corpus.
- Cross-environment equivalence; the source hashes differ.
- Downstream tracking, calibration, coverage, prediction, or operational effects.
