# Session — 2026-03-16 (Loop Improvement Session)

## Summary

A 3-minute cron loop ran 15 improvement cycles (Loops 26–40), each scanning the codebase for the single most impactful weakness and implementing the smallest correct fix, followed by pytest verification. No video processing was run at any point.

**Result: 126 tests (124 pass, 2 skipped), up from 21 tests at session start. Zero regressions across all loops.**

---

## Tracker Current State

### What It Can Do Now

| Capability | Status | Notes |
|---|---|---|
| Person detection | ✅ Production | YOLOv8n, conf=0.5, 10-player + referee slots |
| Kalman tracking | ✅ Production | 6D state [cx,cy,vx,vy,w,h], per-slot filters |
| Hungarian assignment | ✅ Production | Globally optimal, scipy linear_sum_assignment |
| Team classification | ✅ Production | HSV + k-means color per detection |
| Similar-uniform re-ID | ✅ Production | TeamColorTracker, k=2, appearance weight boost |
| Ball tracking | ✅ Production | Hough → CSRT → optical flow fallback |
| Court rectification | ✅ Production | SIFT panorama + 3-tier EMA homography |
| Court drift correction | ✅ Production | White-pixel alignment check every 30 frames |
| Jersey OCR | ✅ Production | EasyOCR dual-pass (normal + inverted), JerseyVotingBuffer |
| Player identity (name) | ✅ Production | Jersey number → NBA roster API lookup |
| Identity persistence | ✅ Production | player_identity_map schema + DB persist |
| Referee filtering | ✅ Production | NaN sentinel, not row removal — analytics clean |
| Re-ID gallery | ✅ Production | 300-frame TTL, jersey-number tiebreaker |
| Kalman fill (1–5 frames) | ✅ Production | Short-gap position interpolation |
| Duplicate suppression | ✅ Production | Same-team proximity dedup, keep fresher track |
| Velocity clamping | ✅ Production | MAX_2D_JUMP=250px guard against noisy homography |
| Event detection | ✅ Production | Shot / pass / dribble (EventDetector) |
| Shot quality scoring | ✅ Production | Zone + isolation + spacing + possession depth |
| Defensive pressure | ✅ Production | ISO + paint + coverage + spacing weighted score |
| Momentum analytics | ✅ Production | Velocity differential, spacing advantage |
| 60+ ML features | ✅ Production | Per-frame: spatial, rolling, event, game-flow |
| Win probability model | ✅ Code ready | XGBoost 26 features — **needs `--train`** |
| Player prop model | ✅ Code ready | pts/reb/ast regressors — **needs `--train`** |
| Game prediction | ✅ Code ready | predict_game(), predict_today() |
| NBA API enrichment | ✅ Production | Play-by-play, shot labels, score context |
| Schedule context | ✅ Production | Rest days, back-to-back, travel distance |
| PostgreSQL schema | ✅ Ready | 9 tables, 2 views — **writes not wired yet** |

### What It Still Needs

| Gap | Impact | Phase |
|---|---|---|
| `--train` the win probability model | 🔴 High — model exists but untrained | Now |
| Enrich 16 games with `--game-id` | 🔴 High — 0 shots labeled; blocks shot quality ML | Now |
| Wire PostgreSQL writes in run_clip.py | 🔴 High — losing tracking history every run | Phase 5 |
| injury_monitor.py | 🔴 High — moves lines 4–6 pts, not in features | Phase 3.5 |
| ref_tracker.py | 🟡 Medium — pace/foul tendencies not in features | Phase 3.5 |
| line_monitor.py (The Odds API) | 🟡 Medium — opening vs closing sharp money signal | Phase 6 |
| Shot clock from video | 🟡 Medium — no shot-clock feature currently | Phase 5 |
| Analytics dashboard | 🔴 High — no visualization yet | Phase 8 |
| Betting dashboard | 🔴 High — no UI for edge detection | Phase 8 |
| FastAPI backend | 🔲 Planned | Phase 7 |
| React frontend | 🔲 Planned | Phase 8 |
| AI chat interface | 🔲 Planned | Phase 9 |
| Live win probability LSTM | 🔲 Needs 200+ labeled games | Phase 10 |
| Real broadcast test clip | 🟡 Medium — only 21% coverage on highlights clip | Next benchmark |

---

## Loop-by-Loop Fixes

### Tracking Fixes

**Loop 26 — `evaluate.py` dead counter**
- `team_imbalance_frames` was always 0 — condition `if teams[tm] == 0` inside `if both_teams_present` is a contradiction
- Fixed: `if min(teams["green"], teams["white"]) < 2`

### Data Pipeline Fixes

**Loop 28 — PBP partial-cache bug** (`nba_enricher.py`)
- `fetch_playbyplay` trusted any cached file — a mid-game cache was frozen forever
- Fixed: only accept cache if `event_type == 13` (period-end) is present

**Loop 29 — Gamelog no TTL** (`player_props.py`)
- Rolling form features used permanently stale gamelog
- Fixed: `_GAMELOG_TTL_HOURS = 24` mtime check

**Loop 31 — avg_rest denominator** (`schedule_context.py`)
- Season openers (rest_days=99) were included in avg_rest calculation, inflating averages
- Fixed: `rested = [g for g in window if g["rest_days"] < 99]`

**Loop 34 — BRK vs BKN** (`schedule_context.py`)
- Brooklyn Nets arena coords keyed as BRK, but NBA API uses BKN — travel distance always 0.0 for BKN games
- Fixed: renamed key to BKN

**Loop 37 — `_get_opp_def_rating` constant** (`player_props.py`)
- Returned hardcoded 113.0 for all opponents unless win_probability training had been run
- Fixed: 3-level lookup — primary cache → secondary abbrev-keyed cache → NBA API fetch + cache

**Loop 38 — player_avgs no TTL** (`player_props.py`)
- `player_avgs_{season}.json` never expired — season averages frozen from first fetch
- Fixed: `_PLAYER_AVGS_TTL_HOURS = 24` mtime check

**Loop 40 — schedule cache no TTL** (`schedule_context.py`)
- Schedule cached permanently — new game-night games never appeared
- Fixed: `_SCHEDULE_TTL_HOURS = 24` passed through new `_load_cache(ttl_hours=)` param

### ML Data Integrity Fixes

**Loop 27 — zero-variance feature** (`win_probability.py`)
- `home_travel_miles` was always 0.0 (home team doesn't travel) — XGBoost would assign it zero weight but it adds noise
- Fixed: removed from FEATURE_COLS → 26 features

**Loop 30 — versioned cache iteration** (`win_probability.py`)
- `_get_last5_wins` iterated over `{"v":2, "rows":[...]}` dict keys instead of rows
- Fixed: `games = payload.get("rows", payload) if isinstance(payload, dict) else payload`

**Loop 32 — rest_days training cap** (`win_probability.py`)
- Training used raw rest_days (up to 99 for season opener) but inference capped at 10
- Fixed: `min(rest_lookup.get(...), 10)` applied during training rows

**Loop 33 — label leakage** (`player_props.py`)
- `train_props` included `season_pts` in pts model features, `season_reb` in reb model, etc.
- Fixed: per-stat feature exclusion — `[c for c in feat_cols if c != f"season_{stat}"]`

**Loop 35 — temporal leakage** (`win_probability.py`)
- `train_test_split` randomly shuffled temporal data — future games leaked into training
- Fixed: chronological 80/20 split by game_date

**Loop 36 — traded player disambiguation** (`player_props.py`)
- Multiple rows per traded player (per-team + TOT); no dedup → random row selected
- Fixed: highest-GP row wins (TOT combined row has most games)

**Loop 39 — team_stats no TTL** (`win_probability.py`)
- `_fetch_team_stats` never refreshed — 14/26 model features (off_rtg, def_rtg, etc.) frozen from first fetch
- Fixed: `_TEAM_STATS_TTL_HOURS = 24` mtime check

---

## Test Suite Growth

| Phase | Tests Before Session | Tests After Session |
|---|---|---|
| test_phase2.py | 26 | **41** |
| test_phase3.py | 21 | **85** |
| **Total** | **47** | **126** |

---

## Known Issues Still Open

| ID | Issue | Status |
|---|---|---|
| ISSUE-008 | No shot clock from video | 🔲 Phase 5 |
| ISSUE-009 | 0 shots enriched | 🔴 Active — need `--game-id` per clip |
| ISSUE-010 | PostgreSQL not wired | 🔴 Active — db.py exists, nothing writes |
| ISSUE-011 | `fetch_game_ids` no TTL | 🟡 Next loop target |
| ISSUE-012 | `_fetch_season_games` stale mid-season | 🟡 Training data concern |

---

## Next Session Priorities

1. `python src/prediction/win_probability.py --train` — model is fully hardened
2. `python src/prediction/win_probability.py --backtest` — validate accuracy
3. Assign game IDs to 16 videos → re-run enrichment → labels for shot quality model
4. Wire `db.py` writes into `run_clip.py`
5. Phase 3.5: `injury_monitor.py`
