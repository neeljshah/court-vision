# Feature Inventory — All Signals in the Stack

*All ~70 features across 7 classes — API, CV spatial, temporal, market microstructure.*

---

## Summary

| Class | Source | Feature count | Status |
|-------|--------|--------------|--------|
| API box-score | `nba_api` game logs 2018–present | ~20 | Wired |
| API derived | Pace, team total, lineup on/off, ref, altitude, travel | ~12 | Wired |
| CV spatial | defender_distance, spacing_score, fatigue, contest%, isolation | ~8 | Not deployed (`has_cv_data: false` in `cv_lift_report.json`; 29-game 2026-earlier corpus is historical, not in production predictions) |
| CV temporal | Rolling shots/passes/dribbles over 5/10/20-frame windows | ~12 | Wired |
| CV biomechanical | ankle_y, contest_arm_angle, jump_detected, shot arc, pose landmarks | ~6 | Partial |
| Market microstructure | Pinnacle no-vig line, line velocity, steam flag, public% | ~6 | Partial |
| Sentiment / NLP | Injury severity, beat reporter credibility, lineup freshness | ~5 | Partial |

**Total wired features:** ~50 (API + CV temporal). **Partial/planned:** ~27.

---

## Class 1: API Box-Score Features

Source: `nba_api` game logs, Kaggle NBA database, Basketball-Reference.

Computed by [`src/features/feature_engineering.py`](../../src/features/feature_engineering.py) — `add_rolling_features`.

| Feature | Description | Window |
|---------|-------------|--------|
| `pts_game` | Points per game (raw) | Season-to-date |
| `reb_game` | Rebounds per game | Season-to-date |
| `ast_game` | Assists per game | Season-to-date |
| `fg3m_game` | 3-pointers made per game | Season-to-date |
| `tov_game` | Turnovers per game | Season-to-date |
| `blk_game` | Blocks per game | Season-to-date |
| `stl_game` | Steals per game | Season-to-date |
| `min_game` | Minutes per game | Season-to-date |
| `fga_game` | Field goal attempts per game | Season-to-date |
| `fta_game` | Free throw attempts per game | Season-to-date |
| `pts_roll3` | Rolling 3-game points average | 3-game |
| `pts_roll5` | Rolling 5-game points average | 5-game |
| `pts_roll10` | Rolling 10-game points average | 10-game |
| `pts_roll20` | Rolling 20-game points average | 20-game |
| *(same rolling structure for reb, ast, fg3m, tov, blk, stl)* | — | — |
| `pts_std5` | Standard deviation over last 5 games | 5-game |
| `home_pts_avg` | Home/away split — points | Home games only |
| `b2b_flag` | Back-to-back game indicator | — |

**SHAP note:** Team total and pace collectively contribute ~38% of SHAP mass on the pts model. Per-game season averages contribute ~20%. Individual rolling windows add marginal predictive power above the 10-game window.

---

## Class 2: API Derived Features

Computed from combinations of NBA API data and external sources.

| Feature | Description | Source | Status |
|---------|-------------|--------|--------|
| `pace_diff` | Team pace differential vs opponent | NBA API | |
| `vegas_team_total` | Implied team total from game line | Odds API | |
| `opp_drtg_vs_pos` | Opponent defensive rating vs player's position | NBA API LeagueDashPtStats | |
| `lineup_net_rating` | Net rating of typical starting lineup | PBPStats on/off | |
| `altitude_flag` | 1 if game in Denver or SLC | Static lookup | |
| `travel_distance` | Great-circle distance from prior city | Computed | Partial |
| `timezone_cross` | Timezone crossings (direction-aware) | Computed | Planned |
| `days_rest` | Days since last game | NBA schedule | |
| `opp_days_rest` | Opponent days since last game | NBA schedule | |
| `home_flag` | Home vs away | NBA API | |
| `ref_foul_rate` | Historical foul rate for assigned ref | Scraped ref stats | In progress |
| `ref_pace_factor` | Historical pace effect for assigned ref | Scraped ref stats | In progress |
| `contract_year_flag` | Player in final year of contract | Spotrac | Planned |

---

## Class 3: CV Spatial Features

Source: `src/pipeline/unified_pipeline.py` → `src/features/feature_engineering.py`.

These are the moat features — the only features in the stack that are not available to any retail analyst via public data.

| Feature | Description | Unit | Status |
|---------|-------------|------|--------|
| `defender_distance` | Distance to nearest defender at shot release | Meters (court coords) | BUILT |
| `spacing_score` | Convex hull area of 4 off-ball offensive players | m² | BUILT |
| `legs_fatigue` | Cumulative running distance, last 6 min, exp-decayed | m × decay | BUILT |
| `nearest_opponent` | Distance to nearest opponent (any time) | Meters | BUILT |
| `handler_isolation` | Distance from ball-handler to nearest teammate | Meters | BUILT |
| `contest_pct` | Fraction of possession frames with defender within 2m | 0–1 | BUILT |
| `closeout_speed` | Defender velocity toward shooter at catch | m/s | Planned |
| `paint_density` | Players within paint polygon per frame | Count | Planned |
| `transition_flag` | Transition vs half-court possession | Binary | Planned |
| `catch_and_shoot_flag` | Player stationary before shot release | Binary | Planned |
| `off_ball_movement` | Total off-ball player distance per possession | Meters | Planned |
| `shot_release_angle` | Angle of ball trajectory at release | Degrees | Planned |

**SHAP contribution (combined CV spatial):** 31% of mass on pts model. Δ R² over API-only: +0.08.

**Current state (2026-07-15):** `data/output/cv_lift_report.json` reports `has_cv_data: false` — zero games currently have CV features in use for production predictions (confirmed at `src/prediction/prop_pergame.py:204`, SHAP ~= 0.0). The 29-game figure (9 CLEAN + 20 PARTIAL of 75 attempted) is a historical artifact from earlier development, not the current deployment status. CV infrastructure is present but not active; bootstrap CIs on defender_distance/spacing_score from that earlier corpus were wide enough on tail markets to overlap zero at 95%. Retrain at N=80 CLEAN games before reconsidering deployment.

---

## Class 4: CV Temporal Features

Rolling statistics computed from frame-level tracking data within a game.

| Feature | Description | Window |
|---------|-------------|--------|
| `shot_attempts_5f` | Shot attempts in last 5 frames (standardized) | 5-frame (~0.17s) |
| `shot_attempts_10f` | Shot attempts in last 10 frames | 10-frame |
| `shot_attempts_20f` | Shot attempts in last 20 frames | 20-frame |
| `dribbles_5f` | Ball dribble events in last 5 frames | 5-frame |
| `dribbles_10f` | Ball dribble events | 10-frame |
| `pass_events_5f` | Pass events detected in last 5 frames | 5-frame |
| `velocity_avg_5f` | Average player velocity, last 5 frames | 5-frame |
| `velocity_max_5f` | Max player velocity, last 5 frames | 5-frame |
| `ball_height_avg` | Average ball height over last 10 frames | 10-frame |

---

## Class 5: CV Biomechanical Features

Pose-derived features from player skeleton keypoints.

| Feature | Description | Status |
|---------|-------------|--------|
| `ankle_y` | Ankle height at shot release (jump detection proxy) | Partial |
| `contest_arm_angle` | Defender arm angle at shot (contest quality) | Partial |
| `jump_detected` | Binary: player in air at shot release | Partial |
| `shot_arc_angle` | Ball trajectory arc angle (from edge 8) | Planned |
| `release_height` | Estimated release height from pose | Partial |
| `pose_balance_score` | Composite balance metric from pose keypoints | Planned |

---

## Class 6: Market Microstructure Features

Derived from real-time line monitoring.

| Feature | Description | Source | Status |
|---------|-------------|--------|--------|
| `pinnacle_nv_prob` | Pinnacle no-vig probability | Line monitor | Partial |
| `line_velocity` | Points moved per minute since open | Odds API history | Partial |
| `steam_flag` | Binary: steam move detected on this market | Computed | Partial |
| `public_pct_over` | % of public bets on over | Action Network | Partial |
| `line_movement_dir` | Direction of movement since open | Computed | Partial |
| `book_lag_score` | How far behind market consensus this book is | Computed | Planned |

These features enter the pipeline as bet-selector filters rather than model inputs at current stage (Phase 14.7 Pinnacle triangulation gate).

---

## Class 7: Sentiment / NLP Features

| Feature | Description | Source | Status |
|---------|-------------|--------|--------|
| `injury_severity_score` | ML-classified severity from injury report text | Own classifier | Partial |
| `reporter_credibility` | Credibility score for injury source | Curated list | Partial |
| `lineup_freshness` | Hours since lineup was last confirmed | NBA API | Partial |
| `press_conf_sentiment` | Sentiment from pre-game press conference | NLP | Planned |
| `dnp_probability` | Probability of DNP given current injury status | Own model | Partial |

---

## How the Prop Feature Stack Is Built (and what the gate rejected)

The prop feature vector is assembled in order by
`src/prediction/prop_pergame.py::feature_columns()`. The *served* root/q50 model
artifacts slice the first **85 columns**; the full enumerated surface grows past
**~190 columns** once every wired block and the iter-wave additions are counted.
The order is load-bearing - artifacts are sliced positionally, so a re-order is a
silent train/inference parity bug (see the `_BBREF_REORDER_FIX` note below).

### Wired blocks (in emission order)

| Block | Columns | Description |
|-------|---------|-------------|
| Form | `l5_*, l10_*, std_*, ewma_*, prev_*` per form-stat | 5 rolling/EWMA/lag views per stat |
| Schedule | `rest_days, is_home, games_played, days_since_last_game, games_since_long_absence` | basic context |
| Opponent defence | `opp_def_{stat}` for all 7 stats | per-stat defensive factor |
| Travel / fatigue | `is_b2b, is_b3b, miles_traveled, altitude_ft` | rest + travel |
| Play-type freq | `pt_{playtype}_freq` | offensive role mix |
| BBRef advanced | `bbref_{key}` (base) | Basketball-Reference advanced |
| Contracts / ratios | `contract_{key}`, ratio keys | motivation + derived ratios |
| BBRef extra | `bbref_{orb_pct, drb_pct, trb_pct, bpm, ws}` | slots 80-84 (legacy) / 85-89 (fix) |
| Defender matchup | `_DMATCH_KEYS` (7) | wave-2b matchup context |
| Player profile | `_PROF_KEYS` (12) | wave-2b archetype/profile |

### Leak-free walk-forward verdicts per candidate block

Most feature ideas are **rejected** by the walk-forward gate - the gate is built
to refute, and a recorded reject is a success, not a failure. The blocks below are
present in the code as infrastructure but **disabled** because they regressed on
walk-forward (all values from the `prop_pergame.py` cycle comments):

| Candidate block | Verdict | Evidence |
|-----------------|---------|----------|
| Advanced-stat L5/L10/EWMA/prev (~20 cols, 77k rows) | **REJECT** | Even at full coverage, 5/7 stats regress (PTS R^2 -0.0054, TOV -0.0089 worst); form features span the same signal |
| Prior-season player tracking (Drives/Passing/CatchShoot) | **REJECT** | 5/7 stats regress (PTS R^2 -0.0023, AST -0.0064); YoY role change makes prior-season tracking a noisy proxy |
| Officials crew tendency (avg fouls/fta/home_win_pct) | **REJECT** | Single-split MAE wins were a holdout-slice artifact; walk-forward regressed all 7 (PTS +0.0111 WF MAE) |
| PTS `log1p` transform | **REJECT** | Per-fold MAE sign-flipped (-0.021..+0.027); `sqrt`+Huber shipped instead |
| FG3M Huber-on-`log1p` | **SHIP** | Only the 6 log1p stats tested; FG3M cleanly 4/4 folds |
| REB LGB-q50 backend | **SHIP** | XGB-q50 was 3/4 folds (failed dual gate); LGB-q50 4/4 + -0.0051 single-split MAE |
| CV spatial features (all) | **DEFER** | SHAP ~= 0.0 in production today (`cv_lift_report.json: has_cv_data: false`); plumbing complete, lift unproven until the 80-CLEAN-game retrain |

The pattern is the discipline: a single good fold, or a single-split MAE win, is
treated as a selection artifact until **all** walk-forward folds agree. The
`_USE_Q50_STATS` dispatch, the per-stat objective switch (Poisson on raw counts;
squared-error/Huber under `log1p`/`sqrt`), and these rejects are all consequences
of the same gate — see [`../ML_MODELS.md`](../ML_MODELS.md) "How the Prop Models
Work" for the modeling side.

> **Honesty rail.** Feature work here improves *accuracy/calibration*, never a
> demonstrated $ edge. The CV-spatial "moat" is wired in as a future thesis with
> complete plumbing and **zero measured predictive value today** (SHAP ~= 0). Do
> not represent it as a current advantage.

---

## Feature Lineage and Timestamping

Every feature in the store is stamped with its ingestion time. The walk-forward harness uses this timestamp to reconstruct "what was known at tip-off" for any game in the training set:

```python
feature_store.get_features(game_id, as_of=tipoff_timestamp)
```

This prevents any future-game information from leaking into training features — the single most common source of inflated backtest results in sports analytics.

---

*See [model-registry.md](model-registry.md) for which models use which feature classes. See [cv-pipeline.md](../architecture/cv-pipeline.md) for how CV features are computed. See [edge-taxonomy.md](../research/edge-taxonomy.md) for the competitive context of each feature class.*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
