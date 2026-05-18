# Data Sources — Complete Architecture

*Complete data architecture — free tier, paid tier, proprietary CV pipeline.*

---

## Overview

The system draws on four tiers of data: free public sources (cost: $0), cheap paid sources ($10–80/mo), real-time market data (The Odds API), and the proprietary broadcast video pipeline. The broadcast pipeline is the moat; everything else is infrastructure shared with any well-resourced analyst.

---

## Free Tier

| Source | URL | Data | Rate Limits | Status |
|--------|-----|------|-------------|--------|
| `nba_api` Python package | github.com/swar/nba_api | 70+ endpoints: box scores, PBP, tracking aggregates, shot charts (x/y coords), lineup data, on/off splits | ~600 req/min max; cloud IPs get banned — use residential or add delays | Wired |
| PBPStats API | api.pbpstats.com | Possession-level PBP, on/off splits, shooting by zone, lineup combinations | Reasonable | Wired |
| Basketball-Reference | basketball-reference.com | Historical stats 1947–present, advanced metrics, contract data | Rate limit carefully; respect robots.txt | Wired |
| `shufinskiy/nba_data` | github.com/shufinskiy/nba_data | Pre-scraped PBP from stats.nba.com + pbpstats.com, 1996–present. Ready to download | One-time download | Downloaded |
| NBA.com tracking pages | nba.com/stats/players/speed-distance | Speed, distance, touches, closest defender distance (aggregated, not per-possession) | Via `nba_api` LeagueDashPtStats | Wired |
| SportVU 2015-16 | github.com/sealneaward/nba-movement-data | 631 games, raw 25fps XY player + ball coordinates. Only public raw tracking release. | One-time download | Planned (validation use) |
| Kaggle NBA database | kaggle.com/datasets/wyattowalsh/basketball | 64K+ games, 4800+ players, box scores since 1947 | One-time download | Downloaded |
| Kaggle NBA PBP | kaggle.com/datasets/szymonjwiak/nba-play-by-play-data-1997-2023 | Play-by-play 1997–2025 | One-time download | Downloaded |
| Referee assignments | official.nba.com/referee-assignments | Daily ref crew posted ~9am ET | Scrape daily | In progress |
| NBAstuffer referee stats | nbastuffer.com/nba-stats/referee | Game-by-game ref stats, multi-season | Scrapeable | Planned |
| Covers.com referee | covers.com/sport/basketball/nba/referees | Ref O/U records, ATS tendencies | Scrapeable | Planned |
| Basketball-Reference refs | basketball-reference.com/referees | Ref career directory + game stats | Scrapeable | Planned |
| NBA injury reports | nba.com/players/injuries | Mandatory filings 1pm/5pm ET game days | Poll 2×/day | Wired |
| RotoWire injuries | rotowire.com/basketball/injury-report.php | Injury report + status + news | Scrapeable | Wired |
| ESPN injuries | espn.com/nba/injuries | Per-team injury status | Scrapeable | Partial |
| BallDontLie | balldontlie.io | Players, games, stats, standings, injuries | Free tier available | Wired |
| OddsPortal | oddsportal.com | Historical closing lines, odds movement | Scrapeable (rate-limit carefully) | Planned |
| SportsOddsHistory | sportsoddshistory.com | Archived futures, spreads, totals | Scrapeable | Planned |
| The Odds API (free) | the-odds-api.com | Live odds 40+ books, 500 req/mo | 500 req/mo free tier | Wired (free tier) |
| YouTube highlights | youtube.com | 10–20 min highlight clips via yt-dlp + cookies | Gray area; working approach | Wired |
| archive.org | archive.org | Some older full games | Availability varies | Fallback (Pass 2.5) |

---

## Cheap Tier ($10–80/mo)

| Source | URL | Data | Cost | Status |
|--------|-----|------|------|--------|
| The Odds API (paid) | the-odds-api.com | Real-time props across 40+ books, enough for production | $20–80/mo | Production path |
| Cleaning the Glass | cleaningtheglass.com | Garbage-time-filtered stats, lineup combinations, play types | ~$10/mo | Planned |
| BigDataBall | bigdataball.com | Validated PBP + odds combined, per-season | $30–50/season | Planned |
| Colab Pro | colab.research.google.com | T4/A100 GPU access, longer sessions | $10/mo | Used for prototyping |
| Vast.ai GPU | vast.ai | RTX 3090 $0.20–0.30/hr, RTX 4090 $0.28–0.32/hr | Pay-per-use | Used |
| RunPod GPU | runpod.io | RTX 4090 $0.34/hr, A100 $1.39/hr. More reliable than Vast. | Pay-per-use | Active (current 80-game run) |

---

## Proprietary: Broadcast Video Pipeline

The data that cannot be purchased at any price tier.

| Data Type | How Produced | Feature Pipeline |
|-----------|-------------|-----------------|
| Per-frame player positions (court coordinates) | YOLOv8n → SIFT homography → Kalman + Hungarian | `src/tracking/advanced_tracker.py` |
| Player identity per frame | OSNet re-ID + EasyOCR jersey number | `src/tracking/osnet_reid.py` |
| Defender distance at shot release | Distance between shooter and nearest defender in court coords | `src/features/feature_engineering.py` |
| Court spacing (convex hull) | 4 off-ball offensive player positions → hull area | `src/features/feature_engineering.py` |
| Player fatigue (legs) | Cumulative distance last 6 min, exponentially decayed | `src/features/feature_engineering.py` |
| Ball detection and trajectory | YOLOv8n ball class + Kalman smoother | `src/tracking/ball_detect_track.py` |
| Shot attempt detection | Ball trajectory + player pose at release | `src/pipeline/unified_pipeline.py` (EventDetector) |

**Current status:** 29 usable games (9 CLEAN + 20 PARTIAL on quality gate) of 75 attempted. Target: 80 CLEAN (enables retrain of Tier 3–4 models with meaningful spatial features). Full tracking pipeline on single RTX 3090 processes ~20 fps per worker; 4-worker pod completes a game in approximately 2 hours.

See [cv-pipeline.md](../architecture/cv-pipeline.md) for full pipeline architecture. See [runpod-runbook.md](../operations/runpod-runbook.md) for GPU operations.

---

## Research Resources (Free)

| Resource | Use Case |
|----------|----------|
| r/sportsbook | Betting strategy, community signal on limiting and book behavior |
| @cleantheglass, @kirkgoldsberry, @SethPartnow on X | NBA analytics signal |
| arxiv.org (cs.LG, stat.ML) | Latest ML for sports prediction; track quarterly |
| L2M reports (nba.com) | Referee performance data, historical call accuracy |
| Spotrac.com | Contract data for contract-year features (edge 15) |

---

## Data Flow Architecture

```
YouTube / archive.org
        │
        ▼
    yt-dlp download
        │
        ▼
  Ingest queue (SQLite)
        │
        ▼
  unified_pipeline.py
  (YOLO → homography → tracking → features)
        │
        ▼
  data/tracking/*.json     data/events/*.json
        │                        │
        └───────────┬────────────┘
                    ▼
         feature_engineering.py
         (CV features + API features joined on game_id/event_id/player_id)
                    │
                    ▼
              Feature store
              (ingestion timestamps preserved for walk-forward)
                    │
                    ▼
            75 prop models
                    │
                    ▼
          10K-path Monte Carlo
                    │
                    ▼
          Line evaluator (vs Odds API)
                    │
                    ▼
          Kelly sizer → Execution router
```

---

## Data Quality Gates

No CV-derived feature enters a model until:
1. The game produces ≥ 80% valid tracking frames (ball_valid_pct ≥ 80%)
2. Player re-ID assigns consistent identities to ≥ 8 of 10 players across the game
3. Homography error is below threshold (verified against court line keypoints)

Games failing these gates fall back to API-only feature set, which degrades model output but does not break the pipeline.

**Open issue:** `ball_track_suspended` stays True on ~8% of games, causing silent fallback to imputed means for the entire game. Root cause scheduled for triage after the 80-game run completes.

---

## Data Sources by Phase

| Phase | New sources activated |
|-------|-----------------------|
| 0 (Validation) | OddsPortal historical closing lines |
| 1 (Foundation) | SportVU 2015-16 calibration, PBPStats on/off deep pull |
| 2 (Context layer) | NBAstuffer/Covers referee stats, RotoWire RSS |
| 3 (Core engine) | The Odds API paid tier (real-time multi-book) |
| 5 (Market expansion) | Novig/ProphetX APIs, Kalshi API |
| 6 (Intelligence) | Pre-scraped PBP corpus for NBA2Vec training |

---

*See [model-registry.md](../models/model-registry.md) for which models use which data sources. See [data-pipeline.md](../operations/data-pipeline.md) for operational details of the ingest system.*
