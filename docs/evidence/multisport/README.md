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

### teacher_student_minutes

| Metric | Value |
| --- | ---: |
| coverage_pct | 100 |
| diagnosis.embeddings.matched_pairs | 2.57e+04 |
| diagnosis.embeddings.misses.count | 0 |
| diagnosis.embeddings.misses.game_never_in_tracking | 0 |
| diagnosis.embeddings.misses.person_never_in_tracking | 0 |
| diagnosis.embeddings.misses.person_present_different_game | 0 |
| diagnosis.embeddings.pair_coverage_pct | 100 |
| diagnosis.embeddings.target_pairs | 2.57e+04 |
| diagnosis.embeddings.tracking_pairs | 2.57e+04 |
| diagnosis.load.matched_pairs | 2.57e+04 |
| diagnosis.load.misses.count | 0 |
| diagnosis.load.misses.game_never_in_tracking | 0 |
| diagnosis.load.misses.person_never_in_tracking | 0 |
| diagnosis.load.misses.person_present_different_game | 0 |
| diagnosis.load.pair_coverage_pct | 100 |
| diagnosis.load.target_pairs | 2.57e+04 |
| diagnosis.load.tracking_pairs | 2.57e+04 |
| diagnosis.tracking.matched_pairs | 2.57e+04 |
| diagnosis.tracking.misses.count | 0 |
| diagnosis.tracking.misses.game_never_in_tracking | 0 |
| diagnosis.tracking.misses.person_never_in_tracking | 0 |
| diagnosis.tracking.misses.person_present_different_game | 0 |
| diagnosis.tracking.pair_coverage_pct | 100 |
| diagnosis.tracking.target_pairs | 2.57e+04 |
| diagnosis.tracking.tracking_pairs | 2.57e+04 |
| pooled.coverage_pct | 100 |
| pooled.delta | -0.08198 |
| pooled.mae_base | 5.963 |
| pooled.mae_track | 5.881 |
| pooled.verdict | IMPROVED |
| rows_evaluated | 2.57e+04 |
| rows_total | 2.57e+04 |

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
