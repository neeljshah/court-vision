---
phase: "02"
plan: "03"
subsystem: analytics
tags: [referee-filtering, feature-engineering, shot-quality, REQ-08]
dependency_graph:
  requires: ["02-00"]
  provides: ["compute_spatial_features public API", "referee-clean shot DataFrame"]
  affects: ["src/features/feature_engineering.py", "src/analytics/shot_quality.py"]
tech_stack:
  added: []
  patterns: ["referee guard via team != 'referee' mask", "NaN sentinel for excluded rows"]
key_files:
  created: []
  modified:
    - src/features/feature_engineering.py
    - src/analytics/shot_quality.py
    - tests/test_phase2.py
decisions:
  - "Use NaN sentinel (not row removal) for referee spatial columns — preserves CSV completeness"
  - "Guard uses string label 'referee' not team_id==2 — matches tracker output schema"
  - "compute_spatial_features() is a post-load guard, not a recompute — spatial values from pipeline are retained for non-referee rows"
metrics:
  duration: "2m 41s"
  completed: "2026-03-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 2 Plan 03: Referee Filtering — Spatial Metrics and Shot Quality Summary

**One-liner:** Referee row exclusion via NaN guard in feature_engineering.py and team-filter in shot_quality.py, preventing referee positions from corrupting ML spatial features.

## What Was Built

Two targeted fixes to stop referee positions (team == "referee") from corrupting analytics:

1. **`compute_spatial_features(df)`** — new public function in `feature_engineering.py`. Accepts any tracking DataFrame and nulls out `team_spacing`, `nearest_opponent`, `nearest_teammate`, `paint_count_own`, `paint_count_opp` for referee rows. Non-referee rows are unaffected. `run()` now calls this before the rolling feature pass.

2. **shot_quality.py shot filter** — the shots DataFrame construction now guards with `df["team"] != "referee"` in addition to `df["event"] == "shot"`. Prevents referee "shot" misclassifications from entering the scoring pipeline.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| TDD RED | Add failing tests for referee exclusion in test_phase2.py | bd4b09a |
| Task 1 GREEN | compute_spatial_features() with referee NaN guard | 2ea220a |
| Task 2 GREEN | Referee filter in shot_quality.py shots DataFrame | 1485882 |

## Verification

```
conda run -n basketball_ai pytest tests/test_phase2.py::TestRefereeExcludedFromSpacing tests/test_phase2.py::TestRefereeExcludedFromPressure -v
```

All 5 tests pass:
- `TestRefereeExcludedFromSpacing::test_referee_excluded_from_spacing` PASSED
- `TestRefereeExcludedFromSpacing::test_compute_spatial_features_importable` PASSED
- `TestRefereeExcludedFromSpacing::test_no_referee_no_change` PASSED
- `TestRefereeExcludedFromPressure::test_referee_excluded_from_pressure` PASSED
- `TestRefereeExcludedFromPressure::test_non_referee_shots_unchanged` PASSED

## Decisions Made

1. **NaN sentinel, not row removal** — referee rows stay in the output DataFrame for completeness. Downstream code that expects all rows (e.g., CSV exports) won't see missing frames. Spatial columns are NaN so ML pipelines can filter naturally.

2. **String label "referee", not team_id == 2** — the tracker uses string team labels in CSV output. Using the SQL integer ID would break the analytics modules which consume CSVs, not the database.

3. **compute_spatial_features as post-load guard** — the spatial values (team_spacing etc.) are computed in unified_pipeline.py during tracking. feature_engineering.py consumes the pre-computed values from CSV. This function is a correctness guard applied after load, ensuring any referee rows that slipped through tracking have their spatial columns zeroed out. It does not recompute from positions.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED
