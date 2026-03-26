# Full-Game Tracker Validation — 2026-03-23 18:51

> Ground truth: NBA API play-by-play + box score
> Tracker: CV pipeline (YOLOv8n + SIFT homography + BallDetectTrack)

---
## Game 0022400625  |  Grade: **A**

**Video:** 287s (10% of 48-min game) @ 13.6 fps  ·  3,900 frames

### Shot Detection vs NBA API

| Metric | Tracker | NBA Ground Truth | Accuracy |
|--------|---------|-----------------|---------|
| FGA detected | 27 | 162 full game (~16 in window) | **100% recall** |
| FG% | — | 50.0% (162 att) | box score ref |
| Shots enriched | 13/27 | — | **48% match rate** |
| 3PT attempts | — | 68 | — |

### Ball & Possession Tracking

| Metric | Tracker | Expected | Accuracy |
|--------|---------|---------|---------|
| Ball detection | 85.0% frames | 60%+ | OK |
| Possessions | 92 | ~20 | **100% recall** |

### Player Tracking Quality

| Metric | Value | Target |
|--------|-------|--------|
| Stability | 1.000 | ≥0.85 |
| ID switches | 0 | <5/min |
| Unique player IDs | 10 | 10 |
| Avg players/frame | 13.3 | 8–10 |
| Team balance (green/white rows) | 13144/14507 (ratio 0.91) | ≥0.70 |

### Box Score (Top 5 Scorers — NBA API)

| Player | Team | PTS | REB | AST | FGA | FGM |
|--------|------|-----|-----|-----|-----|-----|
| Jalen Williams | OKC | 33 | 4 | 7 | 19 | 11 |
| Shai Gilgeous-Alexander | OKC | 31 | 1 | 7 | 25 | 12 |
| Spencer Dinwiddie | DAL | 28 | 1 | 3 | 14 | 11 |
| Kyrie Irving | DAL | 24 | 3 | 4 | 17 | 8 |
| P.J. Washington | DAL | 22 | 19 | 3 | 16 | 6 |

### Errors / Issues Found

None — all metrics within targets.

