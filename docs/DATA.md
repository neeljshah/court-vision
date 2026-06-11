# Data Layer — CourtVision

Sources, ingest pipeline, cache layout, and regeneration commands.

---

## Overview

The data funnel has two independent tracks that merge at the feature layer:

```
Track 1: Broadcast video
    yt-dlp / archive.org / local inbox
        ↓
    src/ingest/fetcher.py  (content-addressed SHA256 store)
        ↓
    src/pipeline/unified_pipeline.py  (YOLO → homography → Kalman+Hungarian → OSNet → EasyOCR)
        ↓
    data/tracking_data.csv  (~$0.10/game CV cost on consumer RTX 4060)

Track 2: Statistical / market data
    nba_api + BBRef + odds scrapers
        ↓
    src/data/  (TTL-cached JSON per source)
        ↓
    src/features/feature_engineering.py
        ↓
    Feature matrix → prop models + win-prob model
```

The two tracks join at `feature_engineering.py`. CV features are wired as
inputs but currently carry SHAP importance ≈ 0 in the production prop models
(the plumbing is complete; the signal is not yet demonstrated).

---

## Track 1: CV Pipeline from Broadcast Video

**Cost benchmark:** ~$0.10–$0.13 per game on a consumer RTX 4060, versus
six- or seven-figure annual contracts for Sportradar or Second Spectrum.
This is the moat thesis: not that broadcast CV is better than optical tracking
today, but that the cost barrier is dramatically lower.

**What the pipeline produces per game:**

| Output | Description |
|---|---|
| Player court coordinates | (x, y) in feet via perspective homography |
| Per-track behavioral fields | spacing, velocity, contested-shot proximity |
| Event detections | shots, fouls, rebounds, turnovers from frame context |
| Player identity | jersey color + re-ID resolution to real NBA player IDs |

**Honest CV status (from `docs/KNOWN_LIMITATIONS.md`):**

- Stable tracker slots: ~5–6 per frame on the calibration clip; reliable
  10-player tracking not yet demonstrated on broadcast footage.
- Player identity: 17,254 rows / 241 games / 252 distinct real NBA player IDs
  in `data/nba_ai.db cv_features`. Per-player CV attribution is ~4% of
  production data.
- Positional accuracy: output via homography; no ground-truth labels exist,
  so MOTA/IDF1/positional-RMSE are not benchmarked — only self-consistency
  gates.
- CV features in prod prop models: SHAP importance ≈ 0 (`cv_lift_report.json:
  has_cv_data = false`). Credible thesis, complete plumbing, no demonstrated
  predictive advantage yet.

**Key CV modules:**

| Module | Role |
|---|---|
| `src/pipeline/unified_pipeline.py` | Orchestrator: video → detections → features |
| `src/tracking/advanced_tracker.py` | 6D Kalman filter + Hungarian assignment |
| `src/tracking/court_detector.py` | HSV masking + HoughLinesP + getPerspectiveTransform |
| `src/tracking/osnet_reid.py` | OSNet omni-scale re-ID (ImageNet-pretrained weights) |
| `src/tracking/color_reid.py` | HSV-histogram appearance model (production) |
| `src/ingest/fetcher.py` | Content-addressed SHA256 video store, multi-source retry |
| `src/ingest/sources.py` | Source registry: youtube / archive.org / nba_condensed / inbox |

**Run the pipeline on a local video:**

```bash
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

Output: `data/tracking_data.csv` + per-frame behavioral fields.

---

## Track 2: Statistical and Market Data

### NBA API (`nba_api` package — free)

All modules live in `src/data/`. Data is TTL-cached as JSON under `data/nba/`.

| Module | Endpoint | Output file | TTL | Coverage |
|---|---|---|---|---|
| `nba_stats.py` | LeagueDashPlayerStats | `player_avgs_{season}.json` | 24 h | 569 active players |
| `player_scraper.py` | PlayerGameLogs | `gamelogs_{season}.json` | 6 h | 622 players, 3 seasons |
| `shot_chart_scraper.py` | ShotChartDetail | `shots_{player_id}_{season}.json` | 24 h | 221,866 shots |
| `pbp_scraper.py` | PlayByPlayV2 | `pbp_{game_id}.json` | 48 h | 3,627 / 3,685 games |
| `nba_tracking_stats.py` | LeagueHustleStatsPlayer | `hustle_stats_{season}.json` | 24 h | 567 players × 3 seasons |
| `nba_tracking_stats.py` | PlayerDashPtShots | `shot_dashboard_all_{season}.json` | 24 h | Shot creation style / defender distance |
| `nba_tracking_stats.py` | LeagueDashPtDefend | `defender_zone_{season}.json` | 24 h | 566 players × 3 seasons |
| `nba_tracking_stats.py` | MatchupsRollup | `matchups_{season}.json` | 24 h | ~2,200 records × 3 seasons |
| `nba_tracking_stats.py` | SynergyPlayTypes | `synergy_offensive/defensive_{season}.json` | 24 h | 300 records × 2 sides |
| `nba_tracking_stats.py` | LeaguePlayerOnDetails | `on_off_{season}.json` | 24 h | 569 players × 3 seasons |

The 291,625-pair player-vs-player matchup matrix (`data/cache/coverage_faced_allseasons.parquet`)
is built from 2,214 raw per-game tracking files across three seasons via
`scripts/intel/build_coverage_allseasons.py`.

### Basketball Reference

**Module:** `src/data/bbref_scraper.py` — TTL 48 h

| Dataset | Output | Coverage |
|---|---|---|
| Advanced stats (VORP, WS/48, BPM, TS%) | `bbref_advanced_{season}.json` | 736 players × 3 seasons |
| Player contracts / walk-year flag | `contracts_2024-25.json` | 523 players (171 walk-year) |

### Contextual and Market Sources

| Module | Source | Output | Notes |
|---|---|---|---|
| `src/ingest/injury_report.py` | NBA official PDF + ESPN RSS | `data/injuries_<date>.json` | 30-min polling |
| `src/ingest/ref_stats.py` | Referee assignment feeds | `data/nba/ref_assignments.json` | pace_tendency, foul_rate_tendency |
| `src/ingest/rest_travel.py` | Static schedule + arena coords | In-memory | rest_days, B2B flag, travel miles |
| `src/ingest/lineup_data.py` | RotoWire scrape | `data/lineups_<date>.json` | Projected starters |
| `src/ingest/vegas_lines.py` | The Odds API + DK direct scraper | `data/lines/<date>.csv` | Live props, 15-min TTL |
| `src/ingest/prop_line_movement.py` | Line-movement monitor | In-memory | Opening vs closing delta |

---

## Intelligence Layer

Beyond the feature matrix, the system maintains an 80-artifact intelligence
layer folded into 690-node Obsidian notes (660 player + 30 team).

| Artifact | Scale | Source |
|---|---|---|
| 291K-pair matchup matrix | 291,625 rows | `data/cache/coverage_faced_allseasons.parquet` |
| Player atlases (28 types) | 660 players | `scripts/intel/` auto-writers |
| Team atlases (16 types) | 30 teams | Same |
| Monte Carlo possession simulation | 10K samples/game | `src/sim/basketball_sim.py` |

The signal catalog is in `vault/Intelligence/_Simulation_Signals.md` (local
only; not in the public repo).

---

## Cache Directory Layout

```
data/
├── nba/                                   # NBA API cache (TTL-managed)
│   ├── gamelogs_{season}.json             # 622 players
│   ├── player_avgs_{season}.json
│   ├── shots_{player_id}_{season}.json    # 221K shots
│   ├── pbp_{game_id}.json                 # 3,627 games
│   ├── hustle_stats_{season}.json
│   ├── on_off_{season}.json
│   ├── defender_zone_{season}.json
│   ├── matchups_{season}.json
│   ├── synergy_offensive_{season}.json
│   ├── synergy_defensive_{season}.json
│   ├── prop_correlations.json             # 508 players, 3,447 pairs
│   ├── injury_report.json                 # Live, 30-min TTL
│   ├── ref_assignments.json
│   └── schedule_{season}.json
│
├── external/                              # Non-NBA-API sources
│   ├── bbref_advanced_{season}.json
│   ├── contracts_2024-25.json
│   └── props_live.json                    # DK/FD props, 15-min TTL
│
├── cache/
│   ├── pregame_oof.parquet                # ~51K held-out player-games, walk-forward OOF
│   ├── coverage_faced_allseasons.parquet  # 291,625-pair matchup matrix
│   └── profiles/                          # per-player signal registry
│
├── models/                                # Trained model weights
│   ├── win_probability.pkl
│   ├── props_pts.json … props_tov.json
│   ├── quantile_pergame_metrics.json       # canonical MAE numbers
│   ├── prop_corr_matrix.json
│   ├── bet_log.json
│   └── clv_log.json
│
└── videos/
    ├── by_sha/                            # content-addressed store (<sha256>.mp4)
    ├── full_games/                        # symlinked named copies
    └── _inbox/                            # drop new clips here for auto-ingest
```

Only `data/seeds/` (SQL seed data) and small model metadata files are
version-controlled. All large data files are gitignored and must be regenerated
locally.

---

## Regenerating Data from Scratch

```bash
# 1. NBA API statistical data
python scripts/ingest_fetch.py --count 80

# 2. Feature matrix
python -m src.features.feature_engineering

# 3. Train prop models
python -m src.prediction.player_props --retrain

# 4. Train win-prob model
python -m src.prediction.win_probability --retrain

# 5. Run CV pipeline on a video (requires GPU recommended)
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

---

## Adding a New Data Source

1. Create `src/data/new_source.py` with the TTL-cache pattern:

```python
def get_data(season: str, force: bool = False) -> dict:
    cache_path = f"data/nba/new_source_{season}.json"
    if not force and cache_fresh(cache_path, ttl_hours=24):
        return json.load(open(cache_path))
    data = fetch_from_api(season)
    json.dump(data, open(cache_path, "w"))
    return data
```

2. Add feature extraction in `src/features/feature_engineering.py`.
3. Wire into `predict_props()` in `src/prediction/player_props.py`.
4. Add test in `tests/`.
5. Retrain: `python -m src.prediction.player_props --retrain`.

---

See also: [docs/BETTING.md](BETTING.md) · [docs/DEMO.md](DEMO.md) ·
[PREDICTIONS_QUICKSTART.md](../PREDICTIONS_QUICKSTART.md)
