# ML Models — NBA AI System

Complete catalog of all 90 models across 7 tiers. Models are built in tier order — each tier requires more data than the previous.

---

## Model Status Summary

| Tier | Models | Data Required | Status |
|---|---|---|---|
| 1 | 13 | NBA API (3 seasons) | ✅ Trained |
| 2 | 5 | 221K shot charts | ✅ Trained |
| 2B | 6 | Untapped nba_api endpoints | 🔲 Phase 3.5 |
| 3 | 4 | Basketball Reference | 🔲 Phase 3.5 |
| 4 | 6 | Betting market scrapers | 🔲 Phase 4.5 |
| 5 | 6 | BBRef injuries + schedule | 🔲 Phase 4.5 |
| 6 | 10 | 20 CV full games | 🔲 Phase 7 |
| 7 | 8 | 50 CV full games | 🔲 Phase 10 |
| 8 | 7 | 100 CV full games | 🔲 Phase 10 |
| 8B | 4 | NLP data (Reddit/news) | 🔲 Phase 9 |
| 9 | 6 | Live data feed | 🔲 Phase 11 |
| 10 | 7 | 200 CV full games | 🔲 Phase 12/16 |

---

## Tier 1 — NBA API Models (Trained ✅)

All 13 models trained on NBA API data only. No video required.

### M1 — Win Probability (Pre-Game)

| | |
|---|---|
| **File** | `src/prediction/win_probability.py` |
| **Model** | `data/models/win_probability.pkl` |
| **Algorithm** | XGBoost classifier |
| **Features** | 27 team-level features |
| **Accuracy** | 69.1% (walk-forward backtest, 3 seasons) |
| **Brier Score** | 0.203 |
| **Train command** | `python src/prediction/win_probability.py --train` |

**27 features:**
- Home/away team offensive rating, defensive rating, net rating, pace
- eFG%, TS%, TOV%, ORB%, FTR
- Rest days (home + away), back-to-back flags
- Travel distance (miles, home + away)
- Recent form (last 5/10 game win%)
- Head-to-head history (3-season)
- Synergy isolation PPP (home + away)

---

### M2–M6 — Game-Level Models

| Model | Target | File |
|---|---|---|
| M2 — Total | Points over/under | `data/models/game_total.json` |
| M3 — Spread | Point differential | `data/models/game_spread.json` |
| M4 — Blowout | P(margin > 20) | `data/models/game_blowout.json` |
| M5 — First Half | First half total | `data/models/game_first_half.json` |
| M6 — Pace | Possessions per 48 | `data/models/game_pace.json` |

All use same 27 team-level features as win probability. XGBoost regressor (total/spread/pace) or classifier (blowout).

---

### M7–M13 — Player Prop Models

| Model | Target | MAE | R² | File |
|---|---|---|---|---|
| M7 — Points | pts/game | 0.308 | 0.934 | `data/models/props_pts.json` |
| M8 — Rebounds | reb/game | 0.113 | 0.942 | `data/models/props_reb.json` |
| M9 — Assists | ast/game | 0.093 | 0.951 | `data/models/props_ast.json` |
| M10 — 3PM | fg3m/game | 0.084 | 0.938 | `data/models/props_fg3m.json` |
| M11 — Steals | stl/game | 0.064 | 0.928 | `data/models/props_stl.json` |
| M12 — Blocks | blk/game | 0.043 | 0.931 | `data/models/props_blk.json` |
| M13 — Turnovers | tov/game | 0.075 | 0.934 | `data/models/props_tov.json` |

All metrics from walk-forward validation. All R² > 0.93.

**57 input features:**
- Season average (Bayesian-shrunk) for each stat
- Rolling L5, L10, L20 averages
- Home/away split
- vs-opponent history (3-season)
- Opponent defensive rating, pace, eFG% allowed
- BBRef VORP, WS/48, BPM
- On/off net rating differential
- Synergy PPP (ISO, P&R handler, spot-up)
- Hustle deflections/g, screen assists/g
- Contested shot %, pull-up %, catch-and-shoot %, avg defender dist
- Shot zone rates (paint, corner 3, above-break 3, mid)
- DNP risk score (from M-DNP model)
- Injury flag, rest days, B2B flag, travel miles
- Contract year flag, cap hit %
- Q4 shot rate, Q4 pts share, comeback pts/g
- Referee pace/FTA tendencies
- Matchup FG% allowed, sharp detector adjustment

**Prediction flow:**
```python
from src.prediction.player_props import predict_props

result = predict_props("Jayson Tatum", opp_team="MIL", season="2024-25")
# Returns:
{
    "player": "Jayson Tatum",
    "dnp_risk": 0.03,
    "projections": {
        "pts": {"projection": 27.4, "line": 26.5, "edge": "over"},
        "reb": {"projection": 8.1, "line": 8.0, "edge": "over"},
        "ast": {"projection": 4.8, "line": 4.5, "edge": "over"},
        ...
    }
}
```

---

## Tier 2 — Shot Chart Models (Trained ✅)

Require 221K shot chart coordinates from NBA API.

### M14 — xFG v1 (Expected Field Goal %)

| | |
|---|---|
| **File** | `src/prediction/xfg_model.py` |
| **Model** | `data/models/xfg_v1.pkl` |
| **Algorithm** | XGBoost classifier |
| **Training data** | 221,866 shots (3 seasons) |
| **Brier Score** | 0.226 |
| **Features** | Shot zone, distance, angle, shot type, quarter, score diff |

**Phase 7 upgrade (xFG v2):** Adds closeout speed, shot clock at release, fatigue penalty, contest arm angle from CV data. Target Brier: 0.200.

---

### M15 — Shot Zone Tendency

| | |
|---|---|
| **File** | `src/prediction/shot_zone_tendency.py` |
| **Output** | `data/nba/shot_zone_tendency.json` |
| **Coverage** | 566 players |
| **Features** | 42-dim zone distribution vector |

Per-player zone tendency profile: paint%, corner 3%, above-break 3%, mid-range%, free throws%. Used by shot selector in the possession simulator.

---

### M16 — Shot Volume Predictor

Predicts number of shot attempts per game given lineup, matchup, and minutes projection.

---

### M17 — Clutch Efficiency

| | |
|---|---|
| **Output** | `data/nba/clutch_scores_{season}.json` |
| **Coverage** | 228–255 qualified players per season |
| **Definition** | Performance when game within 5 pts in final 5 min |

---

### M18 — Shot Creation Type

Classifies each player's primary shot creation method: ISO-heavy, C&S specialist, spot-up, pull-up creator. Feeds into play type selection in the simulator.

---

## Tier 2B — Untapped NBA API Models (🔲 Phase 3.5)

### M19 — Defensive Effort Rating

Built from hustle stats: deflections/g, contested shots/g, screen assists/g, loose ball recoveries/g. Predicts defensive contribution independent of box score.

### M20 — Ball Movement Quality

Built from player tracking: touches, front court touches, paint touches, pass frequency. Identifies high-touch players vs off-ball specialists.

### M21 — Screen ROI

Uses Synergy screen assist data + hustle screen assists to quantify how much offense a screener generates per screen set.

### M22 — Touch Dependency

How much a player's stats depend on touches (high-touch = more volatile prop). From `BoxScorePlayerTrackV2` touch time/game.

### M23 — Play Type Efficiency (Ground Truth)

Synergy PPP by play type per player: ISO efficiency, P&R ball handler efficiency, spot-up efficiency. Ground truth for simulator play type selector.

### M24 — Defender Zone xFG Adjustment

From `LeagueDashPtDefend`: each player's FG% allowed by zone. Adjusts xFG prediction based on specific defender.

---

## Tier 3 — Basketball Reference Models (🔲 Phase 3.5)

### M25 — Age Curve Model

Uses BBRef 10+ season dataset to model efficiency trajectory by age and position. Inputs: age, position, physical profile (height/wingspan). Output: projected efficiency decay rate.

### M26 — Injury Recurrence Model

Uses BBRef historical injury log (games missed per injury type, 10+ seasons). Predicts P(re-injury within 30 games of return) by injury type and player age.

### M27 — Coaching Adjustment Model

Tracks how coaches change rotations after trades, injuries, or losing streaks. Uses BBRef coaching records + historical lineup data.

### M28 — Extended Referee Tendency

Combines nba_api referee data with BBRef historical game logs to compute long-term referee tendencies: pace effect, foul inflation, home win% adjustment.

---

## Tier 4 — Betting Market Models (🔲 Phase 4.5)

### M29 — Sharp Money Detector

Classifies line movements as sharp vs public action:
- Reverse line movement: line moves against public bet% = sharp signal
- Steam detection: rapid movement across multiple books = syndicate
- Input: opening line, current line, public bet%, money%, Pinnacle benchmark
- Output: sharp signal score [0, 1], confidence reduction on opposing side

Currently wired as a heuristic with 20% confidence reduction. Phase 4.5 trains a proper classifier on historical outcomes.

### M30 — CLV Predictor

Predicts whether a bet will be better or worse at closing than current:
- Opening line movement pattern → trained XGBoost
- Features: book_type, time_to_game, current_steam_direction, market_consensus
- Output: predicted CLV delta (positive = bet now, negative = wait)

### M31 — Public Fade Model

When public bet% > 75% on one side + historical fade ROI is positive for this bet type → fade signal. Trained on 3 seasons of Action Network data vs outcomes.

### M32 — Prop Correlation Matrix

| | |
|---|---|
| **Output** | `data/nba/prop_correlations.json` |
| **Coverage** | 508 players, 3,447 lineup pairs |
| **Use** | SGP adjustment, parlay optimizer |

Captures joint distributions: P(A over) given P(B over). Adjusts same-game parlay true probability from independence assumption to correlated reality.

### M33 — SGP Optimizer

Uses M32 correlation matrix to compute true joint probability for same-game parlays. Books assume independence — this finds legs where correlation works in your favor.

### M34 — Soft Book Lag

Models minutes between Pinnacle line move and DraftKings/FanDuel adjustment. Historical distribution per market type. Edge window: first N minutes after sharp book moves.

---

## Tier 5 — Player Lifecycle Models (🔲 Phase 4.5)

### M-DNP — DNP Predictor ✅ (Already Built)

| | |
|---|---|
| **File** | `src/prediction/dnp_predictor.py` |
| **Model** | `data/models/dnp_model.pkl` |
| **Algorithm** | LogisticRegression |
| **ROC-AUC** | **0.979** |
| **Threshold** | ≥ 0.4 risk → flag as DNP, skip prop prediction |

Features: B2B flag, games_in_last_14, coach's historical rest rate, player age, injury history, season record, schedule strength.

### M35 — Load Management Predictor

Star player B2B rest probability — coach-specific:
- Some coaches rest stars > 33 years old on all B2Bs (Pop, Rivers)
- Others never rest (regular season priority coaches)
- Features: star_age, coach_id, road_B2B_flag, season_record, playoff_seed
- Threshold: if P(rest) > 0.40, flag and propagate to lineup models

### M36 — Return-from-Injury Efficiency Curve

Per injury type, how does performance recover over games 1/2/3/5/10 post-return?
- Ankle sprains: ~90% efficiency by game 3
- Hamstring: ~75% by game 5, full by game 10
- Requires BBRef injury history + post-return gamelogs

### M37 — Injury Risk Model

P(injury in next 7 days) per player:
- Phase 2.5+: CV speed vs baseline (fatigue indicator)
- Phase 4.5: B2B count, minutes in last 14 days, historical injury pattern
- BBRef injury recurrence by injury type

### M38 — Breakout Predictor

Sustained usage increase signal — identifies players whose role is expanding:
- Trend: usage rate up 3+ percentage points over 10 games
- Efficiency: TS% holding or improving
- Opportunity: teammate injury / trade / rotation change
- Output: P(sustained breakout vs regression)

### M39 — Contract Year Effect

Last year of deal → historical performance lift by position:
- Guards: +1.8 pts, +0.4 ast (historical BBRef)
- Forwards: +1.2 pts, +0.3 reb
- Centers: +0.8 pts, +0.5 reb
- Interaction with player age: peaks at 26–29, minimal >32

### M40 — Roster Opportunity Model

When a star is DNP, books scramble. This model identifies who absorbs the usage:
- Sources: on/off splits (who plays more when X is out?), historical lineups, synergy plays
- Output: `{player_id, usage_absorption_pct, minutes_gain, pts_boost}`
- First-game edge: maximum window — books price replacements at baseline

---

## Tier 6 — CV Behavioral Models (🔲 Phase 7 — Requires 20 games)

### M41 — xFG v2 (Full Spatial)

Upgrade from xFG v1 with CV-derived features:
- `closeout_speed_allowed` — defender closing distance per frame
- `shot_clock_at_shot` — seconds remaining when shot released
- `fatigue_penalty` — efficiency decay from cumulative minutes
- Target Brier score: 0.200 (vs 0.226 for v1)

### M42 — Play Type Classifier

Classifies each possession as:
- Isolation, Pick-and-Roll (ball/roll), Spot-up, Cut, Transition, Post-up, Hand-off
- Uses CV event data: screen_set, drive, cut, pass sequence, ball movement
- Ground truth: Synergy play type labels for training
- Target: 85%+ classification accuracy

### M43 — Defensive Pressure → Possession Outcome

- Input: pressure_score, spacing, ball_handler_quality, shot_clock
- Output: P(score) / P(turnover) / P(foul)
- Requires labeled CV possessions with NBA PBP outcomes

### M44 — Spacing Rating

Convex hull area of 5-man unit → scoring efficiency:
- Low spacing: < 200 ft² → drives collapse defense
- High spacing: > 280 ft² → open 3s, pick-and-roll efficiency

### M45 — Drive → FTA Model

CV-detected drives → P(foul drawn) based on:
- Drive speed, paint penetration depth, body contact angle

### M46 — Box-Out Rebound Model

Crash angle + speed at rebound event → P(rebound captured):
- Uses CV event: `box_out` from EventDetector
- Improves simulator rebound step from pure size-based to spatial

### M47 — Closeout Suppression

Defender closeout speed → opponent FG% adjustment:
- Fast closeout (>15 ft/s) → -8% FG adjustment
- Lazy closeout (<8 ft/s) → +5% FG adjustment

### M48 — Prop Retrain (with CV Features)

All 7 prop models retrained with CV behavioral features added:
- `drives_per_36`, `box_out_rate`, `off_ball_distance_per_36`
- `closeout_speed_allowed`, `paint_touches_per_36`
- Expected pts MAE: 0.22 → ~0.18

### M49 — Shot Selection Quality

Rates the quality of each shot attempt vs alternatives available:
- Good shot: xFG > 0.55 or better than average possession value
- Forced shot: shot clock < 5s or xFG < 0.40
- Per-player profile: % of shots that are good vs forced

### M50 — Off-Ball Movement Rating

Total distance run + cuts + relocations per 36 minutes:
- High off-ball movers: more catch-and-shoot opportunities
- Feeds into shot selector model

---

## Tier 7 — Volume Models (🔲 Phase 10 — Requires 50–100 games)

### M51 — Fatigue Curve

Per-player efficiency decay vs cumulative minutes:
- Each player has a unique fatigue profile
- High-mileage players (guards) decay faster
- CV: speed vs baseline each game

### M52 — Rebound Positioning

Full spatial model: crash angle + speed → rebound probability:
- 3D extension: height prior from NBA bio data
- Contest radius: wingspan as proxy for reach

### M53 — Lineup Chemistry

5-man unit synergy beyond net rating:
- Spacing compatibility (all 5 stretch vs 0 stretch)
- Screen ROI of each screener for each ball handler
- Transition outlet combinations

### M54 — Matchup Matrix

Full player-vs-player efficiency grid:
- 500+ matchup pairs from 100 games
- CV-derived: defender closes from which angle, how fast

### M55 — Late-Game Efficiency

Clutch factor calibration model:
- P(player is on floor in clutch)
- Clutch efficiency vs regular efficiency delta

### M56 — Closeout Quality

Defender's average closeout speed and angle per game → opponent FG%:
- Quantifies defensive effort independent of team scheme

### M57 — Help Defense Frequency

Rotation rate per possession by player:
- High rotation → reduces driving lanes for opponent
- CV: how often player moves to ball when not guarding it

### M58 — Ball Stagnation Risk

When pass rate drops below threshold → turnover probability increases:
- CV: dribble count before pass/shot
- High dribble count + tight defense → turnover elevation

---

## Tier 8B — NLP Models (🔲 Phase 9)

### M66 — Injury Report NLP

Text severity score from official NBA injury report + RotoWire:
- "Questionable" + "knee soreness" → 25% DNP probability
- "Out" + "hamstring" + "2-3 weeks" → out for 10–15 games
- Training data: ProSportsTransactions historical injury reports + outcomes

### M67 — Injury News Lag

Time from news publication to book line adjustment:
- Per sportsbook, per injury type
- Median lag: 22 minutes for stars, 45 minutes for role players
- Edge window: bet before line moves

### M68 — Team Chemistry Sentiment

Reddit r/nba + beat reporter RSS → team chemistry signal:
- Locker room conflict → usage redistribution risk
- Trade deadline uncertainty → performance variance spike

### M69 — Beat Reporter Credibility

Scores each reporter's historical accuracy on lineup news:
- High credibility reporters get 3× weight in news signal
- Low credibility (clickbait accounts) get 0.1× weight

---

## Tier 9 — Live Models (🔲 Phase 11)

### M70 — Live Prop Updater

In-game prop adjustment based on live box score:
- Player at 14 pts in Q3 with book line of 24.5 → recalculate
- Incorporates fatigue and foul trouble

### M71 — Comeback Probability

P(team overcomes deficit by X points) given:
- Score margin, time remaining, lineup, possession

### M72 — Garbage Time Predictor

P(game enters garbage time) in next 10 possessions:
- When true, star props compress → under edges

### M73 — Foul Trouble Model

P(player fouls out) given current foul count + minutes + matchup:
- Adjusts prop projection for limited minutes risk

### M74 — Q4 Star Usage Model

Predicts usage distribution in crunch time:
- Some stars dominate ball in Q4 (isolation → foul drawing)
- Others become role players in coach's system

### M75 — Momentum Run Model

P(scoring run of X+ points in next Y possessions):
- Uses CV momentum features + box score run data

---

## Tier 10 — Full Stack Models (🔲 Phase 12/16)

### M76 — Full Possession Simulator

The 7-model chain described in ARCHITECTURE.md. Core engine for all stat distributions.

### M77 — Live Win Probability LSTM

LSTM on possession sequence (hidden dim 256, 3 layers):
- Input: possession outcome + game state (score, time, lineup, fatigue)
- Output: win probability after each possession
- Updates via WebSocket in real-time
- Requires 200+ full games for training

### M78 — True Player Impact

Causal impact estimate (not just correlation) using:
- On/off splits + CV spatial quality adjustment
- Separates player quality from lineup quality

### M79 — Lineup Optimizer

DFS and betting lineup optimization:
- Correlation-adjusted expected value per player
- Salary constraints (DFS) or correlated leg selection (SGP)

### M80 — Prop Pricing Engine

Full probability distribution → price calibration:
- Does our distribution match market-implied distribution?
- Identifies where books are systematically over/under-priced

### M81 — Regression Detector

Players shooting significantly above/below xFG:
- Expected to mean-revert
- Strong under signal if consistently over xFG with similar shot quality

### M82 — Injury Impact Model

Full lineup ripple effect when a player is injured:
- Who gets the minutes? (from M40)
- How does spacing change?
- How does pace and play type distribution shift?
- Full re-simulation with updated lineup

---

## The 7-Model Possession Chain (Simulator Core)

```
[1] Play Type    → What kind of possession is this?
[2] Shot Selector → Who shoots? From where?
[3] xFG          → P(make) given shooter + zone + spatial context
[4] TO / Foul    → Does it end in turnover or foul instead?
[5] Rebound      → Who gets the board if missed?
[6] Fatigue      → How does fatigue affect efficiency this possession?
[7] Substitution → Does the coach sub based on foul/fatigue/score?

× 10,000 simulations per game
= Full box score probability distribution per player
```

Each model improves independently as more games are processed. At 200 games, all 7 chain models are optimally trained.
