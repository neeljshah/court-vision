# Data Sources
*Last updated: 2026-03-24*

← [[02 - Model Catalog]] | → [[04 - Pipeline Flow]]

---

## Dataset Status (Audited 2026-03-18)

### NBA API Data (All ✅)

| Dataset | Coverage | File | TTL |
|---------|----------|------|-----|
| Shot charts | 221,866 shots, 569 players, 3 seasons | `data/nba/shot_charts_*.json` | 24h |
| Play-by-play | 3,627 / 3,685 (98.4%) | `data/nba/pbp_*.json` | 24h |
| Player gamelogs | 622 players, 3 seasons | `data/nba/gamelogs_*.json` | 6h |
| Team stats | 30 teams × 3 seasons | `data/nba/team_stats_*.json` | 24h |
| Player base stats | 569 players | `data/nba/player_stats_*.json` | 24h |
| Advanced stats | 569/569 players | `data/nba/advanced_*.json` | 24h |
| Hustle stats | 567/567/535 players | `data/nba/hustle_stats_*.json` | 24h |
| On/off splits | 569/572/539 players | `data/nba/on_off_*.json` | 24h |
| Defender zones | 566/562/530 players | `data/nba/defender_zone_*.json` | 24h |
| Matchup data | 2,269/2,283/2,154 records | `data/nba/matchups_*.json` | 24h |
| Synergy play types | 300 off + 300 def | `data/nba/synergy_*.json` | 24h |
| Clutch scores | 228–255 players/season | `data/nba/clutch_scores_*.json` | 24h |
| Shot dashboard | 559/569 players (real), rest fallback | `data/nba/shot_dashboard_*.json` | 24h |
| Injury report | 126 players (current) | `data/nba/injury_report.json` | 30min |

### External Data (All ✅)

| Dataset | Coverage | File | TTL |
|---------|----------|------|-----|
| BBRef advanced stats | 736/736/680 players | `data/external/bbref_advanced_*.json` | 48h |
| Historical lines | 1,225/1,230/1,230 games | `data/external/historical_lines_*.json` | 7d |
| Player contracts | 523 players, 171 walk-year | `data/external/contracts_2024-25.json` | 7d |
| NBA official injury | Current (CDN JSON) | `data/external/nba_official_injury.json` | 6h |

### CV Tracking Data (Phase F/G Blocker 🔴)

| Metric | Count | Notes |
|--------|-------|-------|
| Full games processed | **0** | **BLOCKER — Phase F/G needed** |
| Game clips processed | 17 | 1–21 second clips only |
| Tracking rows | 29,220 | From short clips |
| Shots detected | 17 | No --game-id enrichment |
| Possessions labeled | 124 | result=NaN (no game-id) |
| Shots with outcomes | 0 | Needs full game processing |

---

## Scrapers — `src/data/`

### NBA API Scrapers

| File | Endpoint | Function |
|------|----------|---------|
| `nba_stats.py` | Multiple | Core NBA API wrapper |
| `nba_tracking_stats.py` | BoxScorePlayerTrackV2, PlayerDashPtShots, etc. | Phase 3.5 tracking data |
| `pbp_scraper.py` | LeagueGameLog + PlayByPlay | 98.4% game coverage |
| `shot_chart_scraper.py` | ShotChartDetail | 221K shots |
| `player_scraper.py` | Multiple — 63 metrics | Self-improving player data loop |
| `lineup_data.py` | LineupStats | Lineup combinations |
| `schedule_context.py` | LeagueSchedule | Rest days, B2B, travel distance |
| `nba_enricher.py` | Multiple | Enriches CV shots with NBA API outcomes |

### External Scrapers

| File | Source | Data |
|------|--------|------|
| `bbref_scraper.py` | Basketball Reference | BPM, VORP, WS/48, injury history |
| `odds_scraper.py` | OddsPortal | Historical closing lines (spread + total) |
| `props_scraper.py` | DraftKings / FanDuel | Current player props (15min TTL) |
| `contracts_scraper.py` | HoopsHype | Salary, years remaining, walk-year flag |
| `injury_monitor.py` | RotoWire RSS + NBA CDN | Injury/lineup feed |
| `news_scraper.py` | ESPN + RotoWire | Headline keyword monitor |
| `beat_reporter_monitor.py` | Twitter/X (social) | Beat reporter credibility system |
| `ref_tracker.py` | BBRef + NBA API | Referee historical tendencies |
| `line_monitor.py` | The Odds API | Opening vs closing line, sharp signal |
| `pinnacle_monitor.py` | Pinnacle | Sharp book lines |
| `action_network.py` | Action Network | Public betting % |

### Not Yet Built (Phase 5)

- `action_network.py` — public betting % → sharp/square detection
- `pinnacle_monitor.py` — Pinnacle sharp lines
- `reddit_monitor.py` — r/nba sentiment (praw)

---

## NBA API Endpoints Used

```python
# Core endpoints (src/data/nba_tracking_stats.py)
BoxScorePlayerTrackV2         # speed, distance, touches per game
PlayerDashPtShots             # contested%, catch-shoot%, pull-up%, defender dist
LeagueDashPtDefend            # FG% allowed by zone (defender zones)
MatchupsRollup                # who guards whom, pts allowed
LeagueHustleStatsPlayer       # deflections, screens, charges
SynergyPlayTypes              # pts/possession by play type (off + def)
LeaguePlayerOnDetails         # on/off net rating splits
VideoEventDetails             # labeled event clip metadata
LeagueGameLog                 # schedule + results
BoxScoreTraditionalV2         # per-player box score
ShotChartDetail               # shot coordinates + outcomes
PlayByPlayV2                  # possession-level event data
TeamPlayerOnOffSummary        # team-level on/off
```

---

## Data Architecture

```
data/
├── models/              # Trained model artifacts
│   ├── win_probability.pkl
│   ├── props_pts.json, props_reb.json ... (7 files)
│   ├── xfg_v1.pkl
│   ├── dnp_model.pkl
│   ├── matchup_model.json
│   └── {load_management, injury_return, injury_risk,
│        breakout_predictor, public_fade, soft_book_lag}.pkl
├── nba/                 # NBA API cache (TTL-managed)
│   ├── shot_charts_{season}.json
│   ├── gamelogs_{season}.json
│   ├── pbp_{game_id}.json
│   ├── hustle_stats_{season}.json
│   ├── on_off_{season}.json
│   ├── defender_zone_{season}.json
│   ├── matchups_{season}.json
│   ├── synergy_{type}_{season}.json
│   ├── shot_zone_tendency.json
│   ├── clutch_scores_{season}.json
│   ├── prop_correlations.json
│   └── scraper_coverage.json
├── external/            # External sources (TTL-managed)
│   ├── bbref_advanced_{season}.json
│   ├── historical_lines_{season}.json
│   ├── contracts_2024-25.json
│   └── nba_official_injury.json
└── tracking/            # Per-game CV output
    └── {game_id}_{date}.csv
```

---

## Rate Limits & Etiquette

- NBA API: **0.8s delay** between requests (enforced in `nba_stats.py`)
- BBRef: **48h TTL** + random 1–3s jitter to avoid blocks
- Props scrapers: **15min TTL** (DK/FD update frequently)
- Historical odds: **7d TTL** (rarely changes)
- Injury report: **30min TTL** (critical for prop accuracy)

---

## Related Notes

- [[01 - System Architecture]] — how data flows into models
- [[02 - Model Catalog]] — which models use which data
- [[04 - Pipeline Flow]] — how to run scrapers
