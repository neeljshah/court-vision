# Data Sources and Pipeline — NBA AI System

Every data source, collection method, cache TTL, current status, and what it feeds into.

---

## Data Collection Architecture

All data is pulled on-demand with smart TTL caching — no manual refresh needed. Stale cache triggers automatic re-fetch at next access.

```
src/data/
├── nba_stats.py              # LeagueDashPlayerStats, TeamStats
├── nba_enricher.py           # Shot outcome enrichment via PBP matching
├── nba_tracking_stats.py     # PlayerDashPtShots, Hustle, Synergy, Matchups
├── player_scraper.py         # 63-metric self-improving scraper
├── pbp_scraper.py            # PlayByPlayV2 — 3,627 games scraped
├── shot_chart_scraper.py     # ShotChartDetail — 221K shots
├── bbref_scraper.py          # Basketball Reference VORP/WS/BPM/injuries
├── injury_monitor.py         # RotoWire RSS + NBA official PDF
├── odds_scraper.py           # OddsPortal historical closing lines
├── props_scraper.py          # DraftKings/FanDuel live props (15min TTL)
├── ref_tracker.py            # Referee historical tendencies
├── line_monitor.py           # Opening vs closing line, sharp signal
├── contracts_scraper.py      # HoopsHype salary + walk-year flag
├── news_scraper.py           # ESPN headline keyword monitor
├── schedule_context.py       # Rest days, B2B, travel distance
├── lineup_data.py            # 5-man units, on/off splits
└── game_matcher.py           # Match CV game to NBA game_id
```

---

## NBA API Sources (`nba_api` package — free)

### LeagueDashPlayerStats

**Module:** `nba_stats.py`
**Output:** `data/nba/player_avgs_{season}.json`
**TTL:** 24 hours
**Coverage:** All active players (569 as of 2024-25)
**Contents:** pts, reb, ast, stl, blk, tov, min, fg%, 3pt%, ft%, ts_pct, usg_pct, off_rtg, def_rtg, net_rtg

---

### PlayerGameLogs

**Module:** `player_scraper.py`
**Output:** `data/nba/gamelogs_{season}.json`
**TTL:** 6 hours
**Coverage:** 622 players scraped (3 seasons)
**Contents:** Per-game box score for every game played. 24 columns including pts, reb, ast, fg%, plus_minus, min, home/away, opp_team.

**Self-improving loop:**
```bash
python src/data/player_scraper.py --loop --max 100
# Detects stale/missing metric groups, fills gaps in priority order:
# Advanced → Scoring → Misc → Base → GameLog → Splits
```

---

### ShotChartDetail

**Module:** `shot_chart_scraper.py`
**Output:** `data/nba/shots_{player_id}_{season}.json`
**TTL:** 24 hours
**Coverage:** 221,866 shots (569 players × 3 seasons)
**Contents:** court_x, court_y, shot_type, shot_zone, action_type, shot_distance, shot_made_flag, period, game_clock, score_margin

Used to train: xFG v1 (M14), shot zone tendency (M15), clutch efficiency (M17)

---

### PlayByPlayV2

**Module:** `pbp_scraper.py`
**Output:** `data/nba/pbp_{game_id}.json`
**TTL:** 48 hours
**Coverage:** 3,627 / 3,685 games (98.4%)

**Contents per event:**
- `eventmsgtype` — shot, foul, rebound, turnover, substitution, etc.
- `player1_id`, `player2_id`, `player3_id`
- `pctimestring` — game clock at event
- `scoremargin` — score margin at event
- `description` — text description (used for NLP models in Phase 9)

**PBP-derived features (computed in `pbp_features.py`):**
- `q4_shot_rate` — shot attempts in Q4 per minute
- `q4_pts_share` — % of team pts in Q4
- `fta_rate_pbp` — free throw attempts per possession
- `foul_drawn_rate_pbp` — fouls drawn per possession
- `comeback_pts_pg` — pts scored when team is down 5+

---

### LeagueHustleStatsPlayer

**Module:** `nba_tracking_stats.py`
**Output:** `data/nba/hustle_stats_{season}.json`
**TTL:** 24 hours
**Coverage:** 567 players × 3 seasons
**Contents:** `deflections`, `screen_assists`, `contested_shots`, `loose_balls_recovered`, `charges_drawn`, `box_outs`

Used in: props feature vector (deflections/g, screen_assists/g, contested_shots/g)

---

### PlayerDashPtShots

**Module:** `nba_tracking_stats.py`
**Output:** `data/nba/shot_dashboard_all_{season}.json`
**TTL:** 24 hours
**Contents:** `contested_shot_pct`, `catch_and_shoot_pct`, `pull_up_pct`, `avg_defender_distance`, `touch_time`, `dribbles_before_shot`

Used in: props feature vector (4 features). Identifies shot creation style and difficulty level.

---

### LeagueDashPtDefend

**Module:** `nba_tracking_stats.py`
**Output:** `data/nba/defender_zone_{season}.json`
**TTL:** 24 hours
**Coverage:** 566 players × 3 seasons
**Contents:** FG% allowed by zone (restricted area, in-the-paint, mid-range, 3pt) per defender

Used in: matchup model, xFG v2 (defender zone adjustment)

---

### MatchupsRollup

**Module:** `nba_tracking_stats.py`
**Output:** `data/nba/matchups_{season}.json`
**TTL:** 24 hours
**Coverage:** 2,269 records (2024-25), 2,283 (2023-24), 2,154 (2022-23)
**Contents:** offender_id, defender_id, time, pts, fg%, field_goals_attempted

Used in: matchup model (M22), props feature vector (matchup_fg_allowed)

---

### SynergyPlayTypes

**Module:** `nba_tracking_stats.py`
**Output:** `data/nba/synergy_offensive_{season}.json`, `data/nba/synergy_defensive_{season}.json`
**TTL:** 24 hours
**Coverage:** 300 offensive + 300 defensive records (2024-25)
**Play types:** Isolation, P&R Ball Handler, P&R Roll Man, Post-Up, Spot-Up, Cut, Off Screen, Hand-Off, Transition
**Contents:** `ppp` (pts per possession), `fg_pct`, `freq` (% of possessions)

Used in: props feature vector (ISO PPP, PnR PPP, spot-up PPP), win prob model (team ISO PPP)

---

### LeaguePlayerOnDetails / TeamPlayerOnOffSummary

**Module:** `nba_tracking_stats.py`
**Output:** `data/nba/on_off_{season}.json`
**TTL:** 24 hours
**Coverage:** 569 players × 3 seasons
**Contents:** `on_off_net_rtg_diff` — how much better/worse the team plays with this player on vs off

Used in: props feature vector (on/off diff — true impact rating)

---

## Basketball Reference Sources

**Module:** `bbref_scraper.py`
**TTL:** 48 hours

### Advanced Stats (VORP / WS / BPM)

**Output:** `data/external/bbref_advanced_{season}.json`
**Coverage:** 736 players × 3 seasons

| Metric | Description | Model Use |
|---|---|---|
| VORP | Value over replacement player | Props pts/reb/ast models |
| WS/48 | Win shares per 48 minutes | Player impact quantification |
| BPM | Box plus/minus | Matchup model |
| TS% | True shooting % | Shot quality baseline |

### Player Contracts

**Module:** `contracts_scraper.py`
**Output:** `data/external/contracts_2024-25.json`
**Coverage:** 523 players (171 walk-year)
**Contents:** `salary`, `years_remaining`, `cap_hit_pct`, `walk_year_flag`

Walk-year flag wired into props feature vector. Historical: contract-year players average +1.2–1.8 pts/g above projection.

---

## Betting Market Sources

### Historical Closing Lines

**Module:** `odds_scraper.py`
**Output:** `data/external/historical_lines_{season}.json`
**Coverage:** 1,225–1,230 games × 3 seasons (actual margins from NBA API — real closing lines via OddsPortal planned Phase 3.5)
**TTL:** 7 days

Used in: CLV backtest baseline. Note: current implementation uses actual game margins as a proxy. Phase 3.5 replaces with real historical closing lines from OddsPortal for true CLV.

### Live Props

**Module:** `props_scraper.py`
**Output:** `data/external/props_live.json`
**TTL:** 15 minutes
**Sources:** DraftKings, FanDuel (Phase 3.5: adds Pinnacle)
**Contents:** `player_name`, `stat`, `line`, `over_odds`, `under_odds`

Feeds into: `find_edges()` in `betting_edge.py` — compares model projection to live line, outputs edge %.

---

## Live Data Feeds

### Injury Monitor

**Module:** `injury_monitor.py`

| Source | Polling Frequency | Contents |
|---|---|---|
| RotoWire RSS | Every 30 minutes | Injury news, lineup changes, player returns |
| NBA official injury PDF | Every 6 hours (5pm ET) | Official probability (Questionable/Doubtful/Out) |

Output: `data/nba/injury_report.json`

The 30-minute polling creates a 15–60 minute edge window when injury news breaks and books haven't fully adjusted props.

---

### Referee Tracker

**Module:** `ref_tracker.py`
**Output:** `data/nba/ref_assignments.json`
**TTL:** 24 hours (updated when official assignments released, ~day before)

**Historical tendencies computed:**
- `pace_tendency` — how many extra/fewer possessions vs league avg
- `foul_rate_tendency` — FTA per possession vs league avg
- `home_win_pct_influence` — how often home team wins with this ref
- `t_flag_rate` — technical fouls per game (team chemistry impact)

Fed into: win probability model (referee features), props model (ref_fta_tendency)

---

### Schedule Context

**Module:** `schedule_context.py`
**No API calls** — static arena coordinates + schedule lookup

**Computed:**
- `rest_days` — days since last game per team
- `back_to_back_flag` — game is second of B2B
- `travel_miles` — great circle distance between arenas
- `days_into_season` — schedule fatigue proxy
- `games_in_last_14` — load management signal

---

## Data Status (As of 2026-03-19)

| Dataset | Count | Status |
|---|---|---|
| Player gamelogs | 622 players, 3 seasons | ✅ |
| Shot chart coordinates | 221,866 shots | ✅ |
| Play-by-play | 3,627 / 3,685 games | ✅ |
| Advanced stats | 569 / 569 players | ✅ |
| Hustle stats | 567 × 3 seasons | ✅ |
| On/off splits | 569 × 3 seasons | ✅ |
| Defender zone FG% | 566 × 3 seasons | ✅ |
| Matchup data | 2,200+ records × 3 seasons | ✅ |
| Synergy play types | 600 records | ✅ |
| BBRef VORP / WS48 | 736 × 3 seasons | ✅ |
| Historical closing lines | 1,225+ games × 3 seasons | ✅ |
| Player contracts | 523 players | ✅ |
| PlayerDashPtShots | 3 seasons | 🔲 Phase 3.5 (scraper built) |
| BBRef 10-season history | 2014–present | 🔲 Phase 3.5 |
| Real historical closing lines | OddsPortal 15yr | 🔲 Phase 3.5 |
| Action Network public % | Live + historical | 🔲 Phase 3.5 |
| Live player prop odds | DK / FD (scraper built) | 🔲 Wire to betting engine |
| CV tracking (full games) | 0 / target 20 | 🔲 Phase 6 |
| CV shots enriched | 0 | 🔲 Phase 6 |

---

## Cache Directory Layout

```
data/
├── nba/                                # NBA API cache
│   ├── gamelogs_{season}.json          # 622 players
│   ├── player_avgs_{season}.json       # Season stat averages
│   ├── shots_{player_id}_{season}.json # 221K shots
│   ├── pbp_{game_id}.json              # 3,627 PBP files
│   ├── hustle_stats_{season}.json      # Deflections, screens, etc.
│   ├── on_off_{season}.json            # On/off splits
│   ├── defender_zone_{season}.json     # FG% allowed by zone
│   ├── matchups_{season}.json          # Who guards whom
│   ├── synergy_offensive_{season}.json
│   ├── synergy_defensive_{season}.json
│   ├── shot_zone_tendency.json         # 566 player zone profiles
│   ├── prop_correlations.json          # 508 players, 3447 pairs
│   ├── clutch_scores_{season}.json     # 228–255 players
│   ├── injury_report.json              # Live, 30min TTL
│   ├── ref_assignments.json            # Daily referee assignments
│   └── schedule_{season}.json
│
├── external/                           # External sources
│   ├── bbref_advanced_{season}.json    # VORP, WS48, BPM
│   ├── historical_lines_{season}.json  # Closing lines
│   ├── contracts_2024-25.json          # Salary + walk-year
│   └── props_live.json                 # DK/FD props (15min TTL)
│
├── models/                             # Trained model files
│   ├── win_probability.pkl
│   ├── props_pts.json
│   ├── props_reb.json
│   ├── props_ast.json
│   ├── props_fg3m.json
│   ├── props_stl.json
│   ├── props_blk.json
│   ├── props_tov.json
│   ├── game_total.json
│   ├── game_spread.json
│   ├── game_blowout.json
│   ├── game_first_half.json
│   ├── game_pace.json
│   ├── matchup_model.json
│   ├── dnp_model.pkl
│   ├── xfg_v1.pkl
│   └── win_prob_metrics.json           # Training metrics
│
└── games/                              # Per-game tracking outputs
    ├── cavs_celtics_2025/
    ├── bos_mia_2025/
    └── [16 game directories]
```

---

## Adding a New Data Source

1. Create `src/data/new_source.py` with TTL cache pattern:
```python
def get_data(season: str, force: bool = False) -> dict:
    cache_path = f"data/nba/new_source_{season}.json"
    if not force and cache_fresh(cache_path, ttl_hours=24):
        return json.load(open(cache_path))
    data = fetch_from_api(season)
    json.dump(data, open(cache_path, "w"))
    return data
```

2. Add feature extraction in `src/features/feature_engineering.py`
3. Wire into `predict_props()` in `src/prediction/player_props.py`
4. Add test in `tests/test_phase3.py`
5. Retrain all prop models with `python src/prediction/player_props.py --train`
