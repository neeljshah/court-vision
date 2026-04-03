# Session 30 Strategic Plan
**Date:** 2026-03-31 | **Branch:** master

---

## 1. Current State

**Data:** 5 games have real tracking data (0022400625=32K, 0022401183=35K, 0022401185=40K, 0022401123=11K, 0022401175=7K rows). ~20 game directories contain identical template data (2,689 or 5,161 rows each — artifacts from cleanup commit `7b46b3c`). No videos exist on disk (all .mp4 files removed during cleanup). The 0022401185 game is the most complete (40K tracking + 23K features + 148 shots + 432 possessions).

**Blockers:**
- **Ball detection critical** (ISSUE-065): 30% valid on 0022401175, only 2 shots in 212 min
- **Team abbrev broken** (ISSUE-066): 7.8% filled despite jersey_name_map.json present
- **No video files on disk**: cleanup commit removed all .mp4s; reprocessing requires re-download
- **Template pollution**: 20+ game dirs contain identical template CSVs, polluting aggregations

**Models:** 60+ models trained (win_prob, 7 props, xFG v1, DNP, matchup, game models, betting infra). All trained on NBA API data only — none use CV spatial features yet (the core moat, ISSUE-006).

**Gamelogs:** 2022-23: 539 players, 2024-25: 526 players, 2025-26: 405 players. Decent coverage but 2024-25 incomplete (526/~600).

---

## 2. Missing Pieces

### Code That Doesn't Exist
- **Possession Simulator** (Phase 8): The 10K Monte Carlo loop is unbuilt. Models exist individually but aren't chained.
- **CV-to-Model wiring** (ISSUE-006): `defender_distance`, `spacing_advantage`, `handler_isolation` collected in tracking CSVs but never feed into props/win_prob/xFG models.
- **Visualization / Dashboard** (Phase 14): `frontend/` has a Vite scaffold but no functional charts/pages.
- **AI Chat** (Phase 15): Not started.
- **Live prediction** (Phase 11): No WebSocket, no real-time pipeline.

### Scripts Incomplete
- `scripts/retrain_all.py` — needs update to include CV features once wired
- `scripts/daily_pipeline.py` — doesn't process CV data
- `scripts/audit_phase_g.py` — compares CV shots vs ground truth but not validated end-to-end

### Manual Processes That Should Be Automated
- Game video download → tracking → enrichment is multi-step manual (`fetch_games.py` → `run_phase_g.py` → manual checks)
- Template/corrupt game directory cleanup is manual
- Gamelog download monitoring (stalled at ~526/600 for 2024-25)
- Model retraining after new data — no trigger/schedule

### Data Disorganization
- **Template pollution**: 20+ game dirs with identical 2,689/5,161-row CSVs inflate game counts
- **No season separation**: All games flat under `data/games/` — no `2024-25/` vs `2025-26/` structure
- **Pano files for deleted/corrupt games** still in `resources/panos/`
- **Stale game_results/**: Only 6 JSON summaries for 30+ game dirs
- **data/nba/**: 1,470 gamelogs but no index/manifest to know what's missing

---

## 3. Execution Plan

### Phase 1: Clean Up Data (code-only, no GPU)
**Goal:** Remove template pollution, establish honest data baseline.

```bash
# Step 1: Identify and remove template game directories
# Template games have md5 9ffc2e8ec268a61d13e89ecbb31e9dd8 (2689/5161 rows)
# or 118be897bdabbc56b8696588204413cf (27652 rows — fake full games)
# Keep ONLY: 0022400625, 0022401183, 0022401185, 0022401123, 0022401175
# and named dirs (atl_ind_2025, etc.)

# Step 2: Create a manifest of real vs template data
python -c "
import os, hashlib
for d in sorted(os.listdir('data/games')):
    p = f'data/games/{d}/tracking_data.csv'
    if os.path.isfile(p):
        h = hashlib.md5(open(p,'rb').read()).hexdigest()
        rows = sum(1 for _ in open(p))
        print(f'{d}  rows={rows}  md5={h[:8]}')
"

# Step 3: Move template dirs to data/games/_templates/ (recoverable)
mkdir -p data/games/_templates
# Move each confirmed template dir
```

**Success:** `data/games/` contains only real tracked games. Manifest file created.
**Tokens:** ~5K

### Phase 2: Fix Ball Detection (ISSUE-065) — Code Analysis Only
**Goal:** Diagnose why ball detection drops to 30% and only 2 shots in 212 min.

```bash
# Read the event detector to understand shot detection logic
# Check stride/FPS handling in ball tracking path
# Check YOLO confidence threshold (currently 0.30 from ISSUE-029)
# Compare 0022401185 (148 shots, 40K rows) vs 0022401175 (2 shots, 7K rows)
```

**Key files to inspect:**
- `src/tracking/ball_detect_track.py` — YOLO ball detection, confidence thresholds
- `src/tracking/event_detector.py` — shot detection logic (direction threshold, debounce)
- `src/pipeline/unified_pipeline.py` — stride/FPS configuration passed to detectors

**Success:** Root cause identified, fix committed, tested on existing data.
**Tokens:** ~15K

### Phase 3: Fix Team Abbrev (ISSUE-066) — Code Fix
**Goal:** Wire team abbreviation resolution so >90% rows get real NBA abbreviations.

```bash
# Debug _resolve_team_names() and _court_side_team_map() in unified_pipeline.py
# Check why jersey_name_map.json is present but not resolving
# Fix and test on 0022401175 data (no video needed — just re-run enrichment)
```

**Success:** `team_abbrev` >90% filled on re-enrichment of existing games.
**Tokens:** ~10K

### Phase 4: Wire CV Features Into Models (ISSUE-006 — Core Moat)
**Goal:** Make spatial features actually influence predictions.

**Sub-steps:**
1. **A-3 from accuracy plan:** Roll `nearest_opponent` into `defender_dist_mean_{30,90,150}`, `defender_dist_min_{90}`, `contested_fraction_{90}`
2. **A-1:** Roll `acceleration` into `acceleration_mean_{30,90,150}`, `acceleration_std_{90}`
3. **A-4/A-5:** Roll `off_ball_distance` and `paint_count` into windowed features
4. **Wire into `player_props.py`**: Add CV features to training feature list
5. **Wire into `win_probability.py`**: Add team-level CV aggregates
6. **Retrain with new features** on existing 5 real games + full gamelog data

**Success:** Props model uses >=5 CV-derived features. R² improves or stays flat (not worse).
**Tokens:** ~30K (largest phase)

### Phase 5: Feature Engineering Completions (Accuracy Plan Block A)
**Goal:** Implement remaining accuracy plan items that don't need new video data.

Items feasible now (no new CV data needed):
- **A-7:** ELO ratings from 3 seasons of game results
- **A-8:** Opponent defensive trajectory (last-10 rating trend)
- **A-6:** Replace shot_quality_proxy with actual xFG v1 model call
- **A-2:** Fatigue index (needs dist_traveled which exists in tracking data)

**Success:** Features added, tests pass, retrain shows metric change.
**Tokens:** ~25K

### Phase 6: Reprocess Existing Data (GPU required)
**Goal:** Re-run enrichment on 5 real games with all code fixes applied.

```bash
# Re-enrich (no video needed, just reprocess CSVs):
for game in 0022400625 0022401183 0022401185 0022401123 0022401175; do
    PYTHONIOENCODING=utf-8 python scripts/run_phase_g.py --game-ids $game --frames 1 --skip-tracking
done
```

**Success:** All 5 games have >80% enrichment rate, team_abbrev >90%, updated features.csv with new rolling features.
**Tokens:** ~10K

---

## 4. Dependency Graph

```
Phase 1 (cleanup)          ─── independent, do first
    │
Phase 2 (ball detect fix)  ─── independent of Phase 1
    │
Phase 3 (team abbrev fix)  ─── independent of Phase 2
    │
Phase 4 (CV→model wiring)  ─── depends on Phase 3 (needs team_abbrev for features)
    │                          ─── partially depends on Phase 2 (ball features)
Phase 5 (feature eng)      ─── parallel with Phase 4 (A-7, A-8 are independent)
    │                          ─── A-6 depends on Phase 4 concepts
    │
Phase 6 (reprocess)        ─── depends on Phases 2, 3, 4, 5 (all fixes applied)
```

**Can run in parallel:**
- Phase 1 + Phase 2 + Phase 3 (all independent code analysis/fixes)
- Phase 4 + Phase 5-partial (ELO + opp trajectory are independent of CV wiring)

**External blockers:**
- **No video files on disk** — reprocessing from raw video requires re-download (yt-dlp). Enrichment-only reprocessing works on existing CSVs.
- **GPU memory** — full game tracking needs RTX 4060 8GB, one game at a time
- **2024-25 gamelogs** — stalled at 526/~600. Props retrain ideally wants full set.

---

## 5. Token Budget

| Phase | Est. Tokens | Model | Notes |
|-------|-------------|-------|-------|
| Phase 1 — Cleanup | ~5K | Sonnet | Simple file ops, no analysis needed |
| Phase 2 — Ball detect | ~15K | Opus | Debugging requires deep code reasoning |
| Phase 3 — Team abbrev | ~10K | Sonnet | Targeted fix, clear scope |
| Phase 4 — CV wiring | ~30K | Opus | Cross-module integration, careful design |
| Phase 5 — Feature eng | ~25K | Opus | Multiple new features, testing |
| Phase 6 — Reprocess | ~10K | Sonnet | Run scripts, validate output |
| **Total** | **~95K** | Mix | Fits in one long session |

No phase exceeds 50K. Phase 4 is the largest but well-bounded.

**Recommended split:** Phases 1-3 in first half (cleanup + fixes). Phases 4-5 in second half (new capabilities). Phase 6 at end (validation).

---

## 6. Success Metrics

| Phase | Done When | Confirmation File/Output |
|-------|-----------|--------------------------|
| Phase 1 | Only 5 real game dirs + named dirs remain | `data/games/` directory listing |
| Phase 2 | Ball detection root cause found + fix committed | `pytest tests/` passes + code diff |
| Phase 3 | team_abbrev >90% on test re-enrichment | Re-enriched CSV column stats |
| Phase 4 | Props model trains with CV features, R² ≥ 0.93 | `data/models/props_*_v3.json` exists |
| Phase 5 | ELO ratings generated, 4+ new features in feature_engineering.py | `data/nba/elo_ratings.json` + pytest |
| Phase 6 | All 5 games re-enriched with updated pipeline | `data/phase_g_metrics.csv` updated |

**Fallbacks:**
- Phase 2 fails → skip ball detection, focus on spatial features (which work at 96%)
- Phase 4 R² drops → keep v2 models, investigate feature interactions
- Phase 6 crashes → re-enrich one game at a time, check memory
- Gamelog download stalled → retrain props on 2022-23 + partial 2024-25 (1,065 players)

---

## 7. Strategic Assessment

**The honest truth:** CLAUDE.md reports 5 clean games and 194K+ rows for 0022400430, but disk reality is different. The cleanup commit stripped most real tracking data. Only ~126K real tracking rows exist across 5 games. The 20+ template directories create an illusion of more data.

**Highest ROI action this session:** Phase 4 (CV→model wiring). The spatial features that exist in 0022401185 (40K rows, 23K features) and 0022400625 (32K rows, 819K features) are the competitive moat. Wiring them into predictions is more valuable than collecting more games.

**What to defer:**
- New game video download/processing (no videos on disk, would consume entire session)
- Frontend/dashboard (Phase 14 — no users yet)
- Possession simulator (Phase 8 — needs more CV data to be meaningful)
- Live prediction (Phase 11 — premature)
