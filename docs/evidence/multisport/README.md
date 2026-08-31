<!-- GENERATED: scripts/platformkit/evidence_page.py -->

# Multi-sport evidence

| Sport | Games | Pass rate | Coverage median | Det/frame median | Track median | Ball valid median | Jump p95 median | OOB median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

## Honest limitations

- No failing metrics were reported.

## Models

Walk-forward/calibration reports are recorded below when present.

### nfl_game_model

| Metric | Value |
| --- | ---: |
| disclaimer | Evaluation only; no betting edge or ROI is claimed. |

### teacher_student_points

| Metric | Value |
| --- | ---: |
| coverage_pct | 100 |
| diagnosis.matched_pairs | 957 |
| diagnosis.misses.count | 230 |
| diagnosis.misses.game_never_in_tracking | 0 |
| diagnosis.misses.person_never_in_tracking | 15 |
| diagnosis.misses.person_present_different_game | 215 |
| diagnosis.pair_coverage_pct | 80.62 |
| diagnosis.target_pairs | 1187 |
| diagnosis.tracking_pairs | 2.57e+04 |
| pooled.coverage_pct | 100 |
| pooled.delta | None |
| pooled.mae_base | 6.609 |
| pooled.mae_track | None |
| pooled.verdict | INVALID (features) |
| rows_evaluated | 779 |
| rows_total | 779 |

### wp_oos_20260831T205014Z

| Metric | Value |
| --- | ---: |
| generated_at | 20260831T205014Z |
| sports.KXMLBGAME.tick_count | 1.58e+05 |
| sports.KXMLBGAME.walk_forward_isotonic.fold_count | 5 |
| sports.KXMLBGAME.walk_forward_isotonic.note | ONLY OOS DELTAS COUNT; no isotonic model is scored on its fit ticks. |
| sports.KXMLBGAME.walk_forward_isotonic.pooled.brier_after | 0.2281 |
| sports.KXMLBGAME.walk_forward_isotonic.pooled.brier_before | 0.2363 |
| sports.KXMLBGAME.walk_forward_isotonic.pooled.delta | 0.008243 |
| sports.KXMLBGAME.walk_forward_isotonic.pooled.test_ticks | 1.342e+05 |
| sports.KXWCGAME.tick_count | 6649 |
| sports.KXWCGAME.walk_forward_isotonic.fold_count | 5 |
| sports.KXWCGAME.walk_forward_isotonic.note | ONLY OOS DELTAS COUNT; no isotonic model is scored on its fit ticks. |
| sports.KXWCGAME.walk_forward_isotonic.pooled.brier_after | 0.2226 |
| sports.KXWCGAME.walk_forward_isotonic.pooled.brier_before | 0.3084 |
| sports.KXWCGAME.walk_forward_isotonic.pooled.delta | 0.0858 |
| sports.KXWCGAME.walk_forward_isotonic.pooled.test_ticks | 4963 |
| store | C:\Users\neelj\nba-ai-system\data\cache\ingame_grade_joined |

No betting edge or ROI is claimed; these are calibration and model-evaluation records only.
