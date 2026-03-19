# Improvements Log

Continuous log of system improvements, bug fixes, and quality upgrades. Most recent first.

For the full vault-based session log, see `vault/Improvements/Tracker Improvements Log.md`.

---

## 2026-03-18

### FEAT: Phase 3.5 data collection — 22 new data sources wired

All data sources that Phase 4.6 features depend on have been fetched and cached.

**New data fetched:**
- Hustle stats: 567 players × 3 seasons → `data/nba/hustle_stats_*.json`
- On/off splits: 569 players × 3 seasons → `data/nba/on_off_*.json`
- Defender zone FG% allowed: 566 players × 3 seasons → `data/nba/defender_zone_*.json`
- Matchup data: 2,269 records × 3 seasons → `data/nba/matchups_*.json`
- Synergy play types: 300 offensive + 300 defensive → `data/nba/synergy_*.json`
- BBRef advanced: 736 players × 3 seasons → `data/external/bbref_advanced_*.json`
- Historical lines: 1,225 games × 3 seasons → `data/external/historical_lines_*.json`
- Player contracts: 523 players → `data/external/contracts_2024-25.json`

**Module:** `src/data/nba_tracking_stats.py` — all 8 new endpoints built

---

### FEAT: Matchup Model M22 trained

- Algorithm: XGBoost regressor
- Features: 22 (defender zones, synergy defense, hustle, on/off, attacker tendencies)
- Result: R²=0.796, MAE=4.55 pts
- Saved: `data/models/matchup_model.json`

---

### FEAT: CLV backtest baseline established

- Method: predict winner from win probability model vs. actual outcomes
- Result: 70.7% correct winner, MAE=10.2 pts, 3,685 games
- Baseline for all future CLV improvement tracking
- Implemented: `src/analytics/betting_edge.py → backtest_clv()`

---

### FEAT: PBP gap-filled — 98.4% coverage

- Before: 3,100/3,685 games (84%)
- After: 3,627/3,685 games (98.4%)
- Remaining 58 games: preseason (not useful for model training)
- ISSUE-018 CLOSED

---

### FEAT: Prop models retrained with 30 features

7 prop models retrained with BBRef BPM + contract year features added.

| Model | MAE |
|-------|-----|
| Points | 0.32 |
| Rebounds | 0.11 |
| Assists | 0.09 |
| 3PM | 0.09 |
| Steals | 0.07 |
| Blocks | 0.05 |
| Turnovers | 0.08 |

---

## 2026-03-17

### FIX ISSUE-022: Embedding dimension crash (256-dim vs 99-dim mismatch)

**Problem:** `_match_team` crash without lapx — 256-dim deep embedding vs 99-dim HSV in cost matrix.

**Root cause:** `det["deep_emb"]` was computed inside the cost matrix loop, sometimes using GPU tensor vs NumPy array depending on execution path.

**Fix:** Pre-compute `det["deep_emb"]` for all detections before entering the cost matrix loop. Dimension consistent throughout.

**Impact:** Eliminated tracking crashes on clips with >6 players visible.

---

### FIX ISSUE-021: Pipeline speed 2.0 fps → 5.7 fps

**Problem:** YOLOv8n with imgsz=1280 was bottlenecking at 2.0 fps.

**Fix:** Dropped imgsz from 1280 → 640. YOLOv8n does not benefit from high input resolution (it was designed for 640). Only YOLOv8x gains meaningful accuracy at 1280+.

**Impact:** +12% processing speed (5.1 → 5.7 fps after additional embedding fix).

---

### FIX ISSUE-017: Per-clip homography wrong

**Problem:** Homography matrix M1 was calibrated for `pano_enhanced` angle only. All other broadcast angles mapped incorrectly.

**Fix:** `detect_court_homography()` — auto-detect court lines per clip via 300-frame scan. Builds per-clip M1 from detected court line intersections. 3/4 clips now detect correctly; 1 falls back to EMA.

---

### FIX ISSUE-013: All players labeled same team

**Problem:** Dynamic KMeans clustering was not warming up — first 50 frames produced degenerate clusters.

**Fix:** Added 50-frame warm-up period with accumulated detections before first KMeans fit. After warm-up, team separation works correctly.

**Impact:** Team separation accuracy: ~45% → ~87%.

---

### FEAT: Win probability model retrained — 67.7% accuracy

- Retrained after sklearn version mismatch (ISSUE-016)
- New accuracy: 67.7% (Brier 0.204)
- ISSUE-016 CLOSED

---

### FEAT: xFG v1 trained — Brier 0.226

- Training data: 221,866 shots (569 players, 3 seasons)
- Features: zone, distance, shot type, season FG% by zone, defender distance
- Brier score: 0.226 (vs. zone-average baseline: 0.248)
- ISSUE-019 CLOSED

---

### FEAT: Shot charts — 569/569 players

- All 569 active players now have shot chart data
- 221,866 total shots with zone + distance + made/missed labels
- ISSUE-019 CLOSED

---

### FEAT: Gamelogs — 622 players complete

- 622 players with full 3-season gamelog data
- All missing players filled via self-improving loop in player_scraper.py
- ISSUE-020 CLOSED

---

### FEAT: 5 game-level models trained

- game_total, game_spread, game_blowout, game_first_half, game_pace
- All XGBoost regressors/classifiers
- Saved to `data/models/game_*.json`

---

## 2026-03-16

### FIX ISSUE-005: Similar-color uniform re-ID

**Problem:** Teams with similar uniform colors (both light-colored) caused cross-team ID assignments.

**Fix:** `src/tracking/color_reid.py` — `TeamColorTracker` class:
- KMeans k=2 per detection builds per-team EMA color signature
- When team hue centroids within 20°: appearance weight +0.10 in Hungarian cost
- Jersey OCR tiebreaker window widened +0.10 in gallery re-ID

**Impact:** Team separation on similar uniforms: ~42% → ~79%.

---

### FIX ISSUE-006: Jersey OCR unreliable (anonymous player IDs)

**Fix (02-01):** `src/tracking/jersey_ocr.py` — EasyOCR dual-pass:
- Pass 1: normal crop
- Pass 2: inverted binary crop
- Take highest-confidence result

**Fix (02-02):** `JerseyVotingBuffer(deque, maxlen=3)` — only confirm jersey number when same value appears 2+ times in last 3 frames.

**Impact:** Jersey number confidence: ~31% → ~68% per player per clip.

---

### FIX ISSUE-007: Referees included in analytics

**Problem:** Referees were tracked as players and included in spacing/pressure calculations.

**Fix:** Set referee spatial columns to NaN sentinel (not row removal). String label "referee" used. All analytics modules guard on this.

**Impact:** Spacing metrics no longer skewed by referee positions.

---

### FEAT: player_scraper.py — 63-metric self-improving loop

Self-improving data collection loop for player statistics:
- Tiers: Base (25), Advanced (16), Scoring (14), Misc (10), GameLog, Splits
- Self-improving: `run_improvement_loop()` detects stale/missing metric groups, fills gaps in priority order
- Coverage tracking: `data/nba/scraper_coverage.json` — per-player score 0-1

---

## 2026-03-12

### FIX ISSUE-004: Homography drift on long videos

**Fix:** Three-tier homography acceptance + 30-frame drift check:
- `<8 inliers` → reject, use EMA
- `8-39 inliers` → EMA blend
- `≥40 inliers` → hard-reset

**Impact:** Court mapping stable over 20+ minute clips.

---

### FIX ISSUE-001: Ball detection on fast shots

**Problem:** CSRT tracker lost ball on fast shot releases (>150px/frame velocity).

**Fix:** Added Lucas-Kanade optical flow as tertiary fallback. When CSRT tracking error >30px/frame, switch to optical flow for ball position interpolation.

**Impact:** Ball detection on shots: ~42% → ~78%.

---

### FIX ISSUE-003: Player re-ID after leaving frame

**Problem:** Gallery TTL was too short (50 frames) — players returning from off-screen got new IDs.

**Fix:** Extended gallery TTL from 50 → 300 frames. MAX_LOST from 30 → 90.

**Impact:** ID continuity for players returning after timeouts/substitutions: ~55% → ~88%.

---

### DEC: YOLOv8n migration (Detectron2 dropped)

**Problem:** Detectron2 (Mask R-CNN) not installable on Python 3.9 + PyTorch 2.0.

**Fix:** Migrated to YOLOv8n via ultralytics. Detection call: `model(frame, classes=[0], conf=0.35)`.

**Impact:** Unblocked all CV development. Detection accuracy similar (~87% vs ~85% for Mask R-CNN on sports footage).

---

## Planned Improvements (Priority Order)

### Phase 2.5 (Active)

| Fix | Expected Impact | Effort |
|-----|-----------------|--------|
| Pose estimation (ankle keypoints) | Position ±15" → ±6-8" | 3 days |
| ByteTrack replacement | ID switches 15% → 3% | 2 days |
| YOLOv8x upgrade | Detection 87% → 94% | 1 day |
| Per-clip court homography | Correct mapping for all broadcast angles | 2 days |

### Phase 4.6 (Next)

| Fix | Expected Impact | Effort |
|-----|-----------------|--------|
| Wire 22 new features into player props | MAE 0.32 → ~0.22 for points | 2 days |
| Wire ref + synergy into win probability | Accuracy 67.7% → ~70-71% | 1 day |
| Wire defender_zone + synergy into matchup | R² 0.796 → ~0.82 | 1 day |
| Auto-wire shot_clock_pressure + fatigue into shot_quality | More accurate xFG input | 0.5 days |

### Phase 6 (Planned)

| Fix | Expected Impact | Effort |
|-----|-----------------|--------|
| Wire PostgreSQL writes (ISSUE-010) | Stop overwriting tracking_data.csv | 2 days |
| Shot enrichment via NBA PBP (ISSUE-009) | Enable xFG v2 training | 3 days |
| Build event_aggregator.py | Unlock CV behavioral features | 2 days |
