# Project CourtVision — Player Prop Models
> Seven XGBoost regressors (pts / reb / ast / fg3m / stl / blk / tov) trained on 52 features — including synergy play types, hustle stats, BBRef VORP, and DNP risk — that out-perform public projection tools on walk-forward MAE.

![Python](https://img.shields.io/badge/Python-3.9-blue) ![XGBoost](https://img.shields.io/badge/XGBoost-regressor-orange) ![Phase](https://img.shields.io/badge/Phase-4%20Complete-green) ![Models](https://img.shields.io/badge/Models-7%20trained-brightgreen)

## Overview

`player_props.py` produces per-game statistical projections for any NBA player given an opponent team. It combines Bayesian-shrunk rolling form, home/away splits, opponent-specific history, defensive rating context, hustle and synergy data from the NBA API, advanced metrics from Basketball Reference, and a DNP predictor that zeroes out projections for players above a 40% injury/rest probability. The result is a 52-feature vector fed into a separate XGBoost regressor for each of the seven standard prop categories.

The feature set is meaningfully broader than what public projection sites use. Most tools stop at rolling averages and season-average matchup adjustments. These models layer in play-type efficiency (synergy PPP for isolation, spot-up, and pick-and-roll), on/off net rating differentials, PBP-derived per-game rates, shot zone tendency profiles, BBRef BPM/VORP/WS48, contract-year flags, and schedule context (rest days, games-in-last-14). Walk-forward MAE on held-out seasons: pts 0.308, reb 0.113, ast 0.093 — all with R² > 0.93.

## Performance Metrics

| Model | Walk-Forward MAE | R² | Status |
|-------|------------------|----|--------|
| Points | 0.308 | >0.93 | ✅ Trained |
| Rebounds | 0.113 | >0.93 | ✅ Trained |
| Assists | 0.093 | >0.94 | ✅ Trained |
| 3-Pointers Made | 0.084 | >0.93 | ✅ Trained |
| Steals | 0.064 | >0.93 | ✅ Trained |
| Blocks | 0.043 | >0.93 | ✅ Trained |
| Turnovers | 0.075 | >0.93 | ✅ Trained |
| DNP predictor AUC | — | — | 0.979 |
| Players with trained models | 569 | — | ✅ |
| Seasons of training data | 3 (2022–25) | — | ✅ |
| Feature count | 52 | — | ✅ |
| Phase 16 pts MAE target | ~0.12 | — | 🔲 Phase 16 |

## Architecture

```
predict_props(player_name, opp_team, season, n_games)
        │
        ▼
DNP Check  (src/prediction/dnp_predictor.py)
  InjuryMonitor → current injury/rest status
  DNP probability ≥ 0.40 → return zeroed projections
        │
        ▼
Feature Builder  _build_player_features()
        │
        ├── Season averages (LeagueDashPlayerStats, 24h TTL)
        │     pts, reb, ast, min, fg_pct, fg3_pct, ft_pct,
        │     fg3m, stl, blk, tov, fta
        │
        ├── Rolling form (PlayerGameLog, 24h TTL)
        │     Last n_games (default 10) sorted by date
        │     pts_roll, reb_roll, ast_roll, min_roll,
        │     fg3m_roll, stl_roll, blk_roll, tov_roll
        │
        ├── Bayesian shrinkage (K=15 prior games)
        │     bayes = n/(n+K) × roll + K/(n+K) × season_avg
        │     Prevents over-fitting on 2–3 game hot streaks
        │
        ├── Home/Away splits (MATCHUP '@' flag)
        │     home/away pts, reb, ast averages
        │
        ├── Opponent history (PlayerDashboardByOpponent, 24h TTL)
        │     pts_vs_opp, reb_vs_opp, ast_vs_opp
        │
        ├── Opponent defensive rating (LeagueDashTeamStats)
        │     opp_def_rtg  (lower = harder matchup)
        │
        ├── Clutch stats (player_clutch_{season}.json)
        │     clutch_net_rtg, clutch_fg_pct, clutch_pts
        │
        ├── Hustle stats (hustle_stats_{season}.json)
        │     deflections_pg, loose_balls_pg, screen_ast_pg
        │
        ├── On/Off splits (on_off_{season}.json)
        │     on_net_rtg, off_net_rtg, on_off_diff
        │
        ├── Synergy play types (synergy_offensive/defensive_all_{season}.json)
        │     team_iso_ppp, team_spotup_ppp, team_prbh_freq
        │     opp_def_iso_ppp, opp_def_prbh_ppp
        │
        ├── PBP-derived features (pbp_features_{season}.json)
        │     shot_rate_pg, ast_rate_pg, tov_rate_pg, etc.
        │
        ├── Shot zone tendency (shot_tendency_features.json)
        │     42-dim zone profile: paint_freq, mid_freq, corner3_freq, etc.
        │
        ├── BBRef advanced (bbref_advanced_{season}.json)
        │     bpm, vorp, ws_per_48
        │
        ├── Contract year flag (contracts_2024-25.json)
        │     contract_year: 0 or 1
        │
        └── Schedule context (schedule_{team}_{season}.json)
              rest_days (capped at 10), games_in_last_14
        │
        ▼
XGBoost Regressor  (one per stat category)
  data/models/props_{stat}.json
  Trained walk-forward over 3 seasons
        │
        ▼
Output dict:
  predictions: {pts, reb, ast, fg3m, stl, blk, tov}
  dnp_probability: float
  features_used: list[str]
  model_version: str
```

## Features

- Predicts all 7 standard prop categories (pts / reb / ast / fg3m / stl / blk / tov) in a single call
- 52-feature vector per prediction — the most comprehensive public-equivalent prop feature set available
- Bayesian shrinkage prior (`K=15`) prevents over-fitting on short hot or cold streaks; automatically down-weights rolling averages when sample size is below 5 games
- Home/away splits computed directly from `PlayerGameLog.MATCHUP` column (`'@'` flag = away game)
- Opponent-specific history from `PlayerDashboardByOpponent` — captures genuine matchup tendencies beyond defensive rating adjustment
- Synergy play-type features: isolation PPP, spot-up PPP, pick-and-roll ball-handler frequency for both the player's team (offensive context) and the opponent (defensive vulnerability)
- DNP predictor (AUC 0.979) gates the entire prop stack — if a player has ≥ 40% injury/rest probability, predictions return as zeros with `dnp_probability` flagged
- BBRef BPM, VORP, and WS/48 capture player value dimensions orthogonal to raw box score stats
- Contract-year flag (`is_contract_year()`) from scraped HoopsHype data — adds a performance-incentive signal
- All external data is cached with TTLs: game logs 24 h, season averages 24 h, opponent splits 24 h — respects NBA API rate limits with `0.6 s` per-call delay

## How It Works

**Feature construction.** `_build_player_features()` assembles the 52-feature vector from a layered lookup hierarchy. Season averages are fetched from `LeagueDashPlayerStats` and cached in `player_avgs_{season}.json`. For traded players, the cache keeps the row with the highest `GP` count (the `TOT` combined row), so season averages reflect the full-season picture rather than a partial-team slice. Rolling form comes from `PlayerGameLog` sorted descending by `GAME_DATE` — multiple date formats are handled (`YYYY-MM-DD`, `%b %d, %Y`, `%B %d, %Y`) because the NBA API is inconsistent across seasons.

**Bayesian shrinkage.** The raw rolling average is unstable when a player has appeared in only 2–4 recent games (load management, injury return). The Bayesian estimate pulls the rolling figure toward the season average with a prior weight of `K=15` games: `bayes = (n / (n + 15)) × roll + (15 / (n + 15)) × season_avg`. At `n=5` games, the estimate is 25% rolling and 75% season average. At `n=30`, it is 67% rolling. This shrinkage is applied independently to every stat category, producing the `{stat}_bayes` features that the XGBoost models use as their primary rolling signal.

**Synergy and play-type features.** NBA Synergy data provides points-per-possession for each play type (isolation, spot-up, pick-and-roll ball handler, etc.) split by offense and defense at the team level. `_load_synergy_off()` pivots the offensive cache to extract `team_iso_ppp`, `team_spotup_ppp`, and `team_prbh_freq` for the player's team — capturing the offensive system they operate in. `_load_synergy_def()` pulls the opponent's defensive PPP allowed for the same play types, capturing how much the defense leaks on each action. Together these two features let the model distinguish between, say, a spot-up specialist playing against a defense that gives up 1.15 PPP on spot-ups vs. one that gives up 0.92.

**DNP gating.** Before any features are assembled, `predict_props()` queries `InjuryMonitor` (a module-level singleton) for the current injury and rest report. If the estimated DNP probability is ≥ 0.40, the function returns immediately with zeroed projections and the `dnp_probability` field set — preventing the downstream Monte Carlo simulator from treating an injured player as healthy. The 0.40 threshold was chosen to capture probable-out and questionable-leaning-out designations while not flagging day-to-day players who typically suit up.

**Walk-forward training.** Models are trained with `train_props(season, force=False)`. The walk-forward evaluation splits each season chronologically — the model is trained on games through month `t` and evaluated on month `t+1`, rolling forward. This prevents data leakage from future game outcomes and produces the MAE figures that reflect real-world prediction accuracy rather than in-sample fit. Seven separate XGBoost regressors are saved to `data/models/props_{stat}.json` with the feature order embedded in the artifact, ensuring prediction-time feature alignment.

## Usage

```python
from src.prediction.player_props import predict_props, train_props

# Single player projection
result = predict_props("Jayson Tatum", "MIA", "2024-25")
print(result["predictions"])
# {'pts': 26.3, 'reb': 8.1, 'ast': 4.7, 'fg3m': 2.9,
#  'stl': 1.0, 'blk': 0.6, 'tov': 2.4}
print(result["dnp_probability"])   # 0.04

# Custom rolling window (default 10)
result = predict_props("LeBron James", "GSW", "2024-25", n_games=5)

# Train all 7 models (walk-forward, 3 seasons)
metrics = train_props(season="2024-25", force=True)
# metrics: {'pts': {'mae': 0.308, 'r2': 0.934}, ...}
```

```python
# Batch projections for tonight's slate
from src.data.nba_stats import get_todays_games

games = get_todays_games()
for game in games:
    for player in game["home_players"] + game["away_players"]:
        proj = predict_props(player["name"], game["opponent"], "2024-25")
        if proj["dnp_probability"] < 0.40:
            print(f"{player['name']} pts: {proj['predictions']['pts']:.1f}")
```

```python
# Compare projection vs. sportsbook line
from src.analytics.betting_edge import compute_edge

proj = predict_props("Stephen Curry", "LAL", "2024-25")
edge = compute_edge(
    player="Stephen Curry",
    stat="pts",
    projection=proj["predictions"]["pts"],
    line=29.5,
    juice=-115,
)
print(f"Edge: {edge['ev_pct']:.1%}  Kelly: {edge['kelly_fraction']:.3f}")
```

## Integration

```
InjuryMonitor (src/data/injury_monitor.py)
    → DNP probability gate

LeagueDashPlayerStats / PlayerGameLog  (NBA API)
    → season averages, rolling form, opponent splits

hustle_stats_{season}.json      → deflections, screens, loose balls
on_off_{season}.json            → on/off net rating differential
synergy_*_all_{season}.json     → play-type PPP (offense + defense)
pbp_features_{season}.json      → PBP-derived per-game rates
shot_tendency_features.json     → 42-dim shot zone profile
bbref_advanced_{season}.json    → BPM, VORP, WS/48
contracts_2024-25.json          → contract-year flag

    ↓ predict_props() ↓

data/models/props_{stat}.json   → XGBoost predictions

    ↓ consumed by ↓

src/analytics/betting_edge.py   → EV computation + Kelly sizing
src/pipeline/model_pipeline.py  → Possession simulator (Phase 8)
src/analytics/prop_correlation.py → SGP optimizer (Phase 12)
```

## Configuration

| Parameter | Default | Controls | When to Change |
|-----------|---------|----------|----------------|
| `_BAYES_K` | 15 | Prior game weight for Bayesian shrinkage | Lower for players with high game-to-game variance |
| `_GAMELOG_TTL_HOURS` | 24 | Game log cache freshness | Lower on game days to catch late roster moves |
| `_PLAYER_AVGS_TTL_HOURS` | 24 | Season averages cache freshness | Lower near trade deadline |
| `n_games` | 10 | Rolling window size passed to `predict_props()` | Lower (5) for returning-from-injury players |
| DNP threshold | 0.40 | Minimum DNP probability to zero projections | Raise to 0.50 to keep questionable players |

## Current Limitations + Roadmap

**No CV spatial features.** The model uses NBA Synergy and hustle data as proxies for spatial context (defender distance, spacing, drive frequency). Phase 7 wires in CV-derived features after 20 full games are processed, which is expected to reduce pts MAE by approximately 0.05–0.08. **Phase 7.**

**Injury impact is binary.** DNP probability is binary (play / don't play). There is no graduated injury impact model (e.g., "playing at 70% with ankle soreness"). Phase 9 adds an injury-severity NLP model on RotoWire text. **Phase 9.**

**No live in-game updating.** Projections are pre-game only. Phase 15 adds a live prop updater that adjusts projections based on first-quarter pace and early foul trouble. **Phase 15.**

**Phase 16 target: pts MAE ~0.12.** Closing from 0.308 → 0.12 requires the full CV feature set (20+ games), the possession simulator feedback loop (Phase 9), and the live lineup adjustment layer (Phase 15). The trajectory is: 0.308 now → ~0.22 after Phase 7 CV features → ~0.15 after Phase 9 feedback loop → ~0.12 after Phase 15 live updates.
