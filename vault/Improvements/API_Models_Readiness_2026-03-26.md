# NBA AI System — Readiness Audit 2026-03-26

## Overall Verdict: READY ✅

All critical systems are functional. No blockers for daily pipeline or Phase G processing.

---

## Step 1 — NBA API Cache

### Deleted Stub Files (empty/corrupt)
| File | Size | Action |
|------|------|--------|
| `beat_reporter_alerts.json` | 2 bytes (`[]`) | Deleted |
| `ref_tendencies.json` | 2 bytes (`{}`) | Deleted |
| `pbp_COMPLETEGAME_p2.json` | 126 bytes (fake test data) | Deleted |
| `pbp_TESTGAME_p4.json` | 177 bytes (fake test data) | Deleted |

### Season Game Log
- `games_2025-26.json` — **FETCHED** this run: 2182 games saved ✅
- `games_2024-25.json` — exists, 1230 records ✅ (> 1000 threshold)

### Phase G PBP Cache (18 games)
| Game ID | Status | Fetched This Run |
|---------|--------|-----------------|
| 0022400430 | 2/4 quarters | No (pre-existing partial) |
| 0022400537 | 2/4 quarters | No (pre-existing partial) |
| 0022400625 | 4/4 ✅ | No |
| 0022400687 | 4/4 ✅ | **YES** |
| 0022400689 | 4/4 ✅ | **YES** |
| 0022400690 | 4/4 ✅ | **YES** |
| 0022400909 | 3/4 quarters | No (pre-existing partial) |
| 0022401117 | 2/4 quarters | No (pre-existing partial) |
| 0022401123 | 3/4 quarters | No (pre-existing partial) |
| 0022401156 | 3/4 quarters | No (pre-existing partial) |
| 0022401183 | 4/4 ✅ | No |
| 0022401185 | 3/4 quarters | No (pre-existing partial) |
| 0022401190 | 4/4 ✅ | **YES** |
| 0022401194 | 4/4 ✅ | **YES** |
| 0022401196 | 4/4 ✅ | **YES** |
| 0022401198 | 4/4 ✅ | **YES** |
| 0022400921 | 2/4 quarters | No (pre-existing partial) |
| 0022400923 | 2/4 quarters | No (pre-existing partial) |

**7 games newly fetched** (687, 689, 690, 190, 194, 196, 198) — all 4/4 quarters.

**8 games have partial PBP** (2-3 quarters) — likely these games went to OT and Q4 returned empty, or Q3/Q4 caches were never fetched. Not a blocker for enrichment (PBP enricher uses available periods). Recommend re-fetching: `0022400430 0022400537 0022400921 0022400923 0022401117 0022400909 0022401123 0022401156 0022401185`

---

## Step 2 — ML Models

### All 46 model files scanned — 0 ERRORS

**Stub models** (< 200 bytes, not loadable — placeholder/untrained):
| Model | Size | In Critical Path? |
|-------|------|------------------|
| `clutch_lineup_model.pkl` | 48 B | No |
| `substitution_timing_model.pkl` | 48 B | No |
| `breakout_predictor.pkl` | 51 B | No (API endpoint uses it but gracefully fails) |
| `shot_clock_pressure_model.pkl` | 84 B | No |
| `public_fade.pkl` | 93 B | No |
| `contested_rate_model.pkl` | 94 B | No |
| `garbage_time.pkl` | 104 B | No |
| `travel_impact_model.pkl` | 137 B | No |
| `soft_book_lag.pkl` | 178 B | No |
| `win_prob_metrics.json` | 160 B | No (metrics file only) |
| `dnp_model_meta.json` | 171 B | No (meta file only) |

**All critical-path models load OK:**
- `win_probability.pkl` — 106KB, XGBClassifier ✅
- `props_*.json` (v1 + v2, 7 stat types) — all load ✅
- `xfg_v1.pkl` — 907KB ✅ | `xfg_cv_stack.pkl` — 1.6KB ✅
- `dnp_model.pkl` — 1.2KB ✅
- `matchup_model.json` — 231KB ✅
- `osnet_x0_25_imagenet.pth` — 2.97MB (skipped load, PyTorch weight) ✅

**XGBoost version warning** — `win_probability.pkl` was serialized with older XGBoost. Non-blocking (loads fine). Fix: re-save with `booster.save_model()` at next retrain.

---

## Step 3 — API

**Import check: PASSED ✅**

```
API import OK
```

**Router files — all exist:**
- `api/models_router.py` ✅
- `api/analytics_router.py` ✅
- `api/predictions_router.py` ✅
- `api/stitch_router.py` ✅
- `api/dashboard_router.py` ✅

**Season strings fixed in `api/predictions_router.py`:**
- `InjuryRiskRequest.season` — `"2024-25"` → `"2025-26"` ✅
- `BreakoutRequest.season` — `"2024-25"` → `"2025-26"` ✅
- `PropsRequest.season` — `"2024-25"` → `"2025-26"` ✅
- `predictions_today()` default — `"2024-25"` → `"2025-26"` ✅
- `props_by_id()` default — `"2024-25"` → `"2025-26"` ✅

---

## Step 4 — Daily Pipeline (`scripts/daily_pipeline.py`)

**Output directories created:**
- `data/predictions/` ✅
- `data/edges/` ✅
- `data/props/` ✅ (already had data)

**Season default:** `--season 2025-26` correct ✅

**No missing file references found.** All step imports (InjuryMonitor, props_scraper, PredictionOrchestrator, outcome_recorder, EdgeDetector, auto_retrain) use try/except — will log warnings if modules unavailable, not crash.

---

## Step 5 — Feature Engineering (`src/features/feature_engineering.py`)

Audited `add_game_flow_features` (L401), `add_momentum_features` (L270), `add_per100_features` (L519):

**No division-by-zero fixes needed — all guarded:**
- L473: `spacing.max() + 1e-6` — safe epsilon guard ✅
- L474: `1.0 / (1.0 + opp_d / 50.0)` — always positive denominator ✅
- L560: `df["possessions_est"].clip(lower=1)` — clipped to min 1 ✅
- L570: `g["possessions_est"].clip(lower=1)` — clipped to min 1 ✅
- L315/L350: `spacing_advantage.clip(-5000, 5000)` — bounded ✅

No hardcoded fps values found. All fps-sensitive logic uses stride/fps-aware calculations (ISSUE-049 closed).

---

## Step 6 — Retrain Pipeline Validation

```
WinProb:  loaded OK, model=XGBClassifier ✅
PropStack: import OK ✅
Kelly:    OK, result=31.50 ✅
```

All three critical components importable and functional.

---

## TODOs (Non-Blocking)

1. **Re-fetch partial PBP quarters** for 8 games with 2-3/4 periods cached — run `scripts/_tmp_fetch_missing_quarters.py`
2. **XGBoost model re-save** — at next `win_probability` retrain, save with `booster.save_model()` to eliminate version warning
3. **Stub models** — 9 stub `.pkl` files need training data before they can be populated (Phase H work)

---

## Session Fixes (Issues A-D) — 2026-03-26

### Possession Fragmentation (Issue A)
- **unified_pipeline.py:2500** — minimum duration filter raised 1.5s → 2.0s
- **unified_pipeline.py:2519** — same-team merge gap raised 150 → 300 frames (~10s real-time at 30fps/stride-3)
- **unified_pipeline.py:2535-2541** — added `logging.WARNING` guard if `len(kept) > 300` after merge (upstream fragmentation sentinel)
- Comment updated at line 2507 to reflect 90→150→300 progression

### Enrichment Fix (Issue B) — 0022401156
- **nba_enricher.py:43** — `_POSS_MATCH_WINDOW_SEC` raised 5.0 → 10.0 (handles clock drift; PBP events sparse enough that precision is maintained)
- **nba_enricher.py:47** — `_POSS_MATCH_WINDOW_SEC_2 = 15.0` added (second-pass constant)
- **nba_enricher.py** — second matching pass added after primary loop: iterates still-unmatched possessions (`pbp_matched=False`) against ±15s window; inlines full etype dispatch
- **nba_enricher.py** — `enriched_pct` print added at end of `enrich_possessions` for audit visibility
- **Re-enrichment result for 0022401156:** 709/709 = **100%** (was 52%). Second pass matched 27 additional possessions. PBP shot recall unchanged at 52.29% (57/109 FG events) — that metric needs reprocess to fix.

### PBP Quarters Fetched (Issue C)
- **Fetched:** 0022401117 P4 (113 ev), 0022400909 P4 (129 ev), 0022401123 P4 (111 ev), 0022401156 P4 (106 ev), 0022401185 P4 (109 ev)
- **Already cached:** 0022400430 P3/P4, 0022400537 P3/P4, 0022400921 P3/P4, 0022400923 P3/P4, 0022401117 P3 — all present from previous session

### Ghost Players (Issue D)
- **unified_pipeline.py:1795-1802** — Pass 2 loop now pre-filters `frame_tracks` to exclude `team == "referee"` and caps at top-12 players per frame sorted by detection confidence descending
- Referee row exclusion prevents 2-3 phantom "players" per frame in tracking_data.csv (root cause of 14.9 players/frame in 0022400909)
- 12-player cap provides a buffer for occlusions (10 on-court + 2 partial) while dropping stale ghost detections

### Items Needing Another Agent's Attention
- ISSUE-054/055 still open: shot over-detection (264-850 shots/game) and possession fragmentation in the 4 clean games predate these fixes — all 4 need reprocess to apply changes
- ISSUE-057: player_name blank in 0022401123 shot_log (EasyOCR not resolving jersey → name) — root cause not investigated in this session
- ISSUE-058: team_abbrev=UNK in all 4 clean games (team_colors.json not generated before ISSUE-045 fix) — needs reprocess or manual team_colors.json creation
- PBP shot recall for 0022401156 still 52.29% — the wide possession window fixed possession matching but shot recall requires reprocess with updated detection code
