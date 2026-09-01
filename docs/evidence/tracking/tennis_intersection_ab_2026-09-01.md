# Findings - Tennis intersection regression A/B

- `98d5ff5b0` replaced endpoint-derived `far_left` and `service_t` with line
  intersections in `adapter.py` and `court_diagnostics.py`.
- The current worktree is on `e8745dd64`, after camera-lock calibration.
- The prior camera-lock run documented `0/725` fresh solves; this A/B must
  determine whether the acceptance loss predates camera-lock reuse.

## Pod A/B result

Video: `/workspace/nba-ai-system/data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4`

Both arms received 600 `linspace(0, 48047, 600)` indices. Frame 48047 failed
to decode in both arms, leaving the same 599-frame denominator.

| Gate / metric | Endpoint old | Intersection new |
|---|---:|---:|
| lines_none | 6 | 6 |
| orientation | 163 | 163 |
| cluster_count | 329 | 341 |
| cross_ratio | 22 | 18 |
| intersection_none | 0 | 0 |
| depth_order | 28 | 0 |
| find_homography | 0 | 0 |
| far_skew | 1 | 7 |
| bounds | 0 | 4 |
| raw accepts | 50 | 60 |
| native stable solves | 45 | 46 |

Intersection is 1.20 times endpoint raw acceptance, not an endpoint advantage
of at least 5 times. Pre-registered verdict: no measured intersection
regression; no revert.

## Camera-lock zero diagnosis

An exhaustive sequential decode of source frames 3816-4565 with the
intersection snapshot yielded 750 decoded frames and zero raw/stable accepts.
Every frame failed upstream of camera lock: orientation 333, cluster count 391,
cross ratio 13, lines none 12, and far skew 1. The earlier 0/725 therefore
comes from the selected section's lack of raw court acceptance, not from the
camera-lock acceptance path.
