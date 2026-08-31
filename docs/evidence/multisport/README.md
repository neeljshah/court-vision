<!-- GENERATED: scripts/platformkit/evidence_page.py -->

# Multi-sport evidence

| Sport | Games | Pass rate | Coverage median | Det/frame median | Track median | Ball valid median | Jump p95 median | OOB median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [baseball](baseball.md) | 2 | 0% | 1 | 2 | 371.5 | 0 | 49.29 | 0 |
| [basketball](basketball.md) | 3 | 33% | 0.406 | 9.69 | 3326 | 0.8592 | 0 | 0 |
| [soccer](soccer.md) | 1 | 0% | 0 | 2.45 | 1 | 0 | 51.73 | 0 |
| [tennis](tennis.md) | 4 | 0% | 1 | 2 | 9005 | 0 | 18.5 | 0 |

## Honest limitations

- baseball/kbo_01: ball_valid 0.00 < 0.1
- baseball/kbo_01: jump_p95 46.2 > 10.0
- baseball/npb_01: ball_valid 0.00 < 0.1
- baseball/npb_01: jump_p95 52.4 > 10.0
- basketball/test720_4MoMewm2j-o: coverage 0.07 < 0.9
- basketball/wnba_kangps_g2: coverage 0.41 < 0.6
- soccer/soccer_wc22_bra_cro: coverage 0.00 < 0.85
- soccer/soccer_wc22_bra_cro: ball_valid 0.00 < 0.2
- soccer/soccer_wc22_bra_cro: jump_p95 51.7 > 8.0
- tennis/tennis_03: ball_valid 0.00 < 0.2
- tennis/tennis_03: jump_p95 40.2 > 8.0
- tennis/tennis_04: ball_valid 0.00 < 0.2
- tennis/tennis_04: jump_p95 14.1 > 8.0
- tennis/tennis_uso25_thompson_moutet: ball_valid 0.00 < 0.2
- tennis/tennis_uso25_thompson_moutet: jump_p95 22.9 > 8.0
- tennis/tennis_uso25_zhang_bencic: ball_valid 0.00 < 0.2

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
