# Complete Model Catalog
> Every model the system builds — 80+ models across 8 tiers.
> Organized by data requirement. Everything above a tier requires that tier's data first.
> Last updated: 2026-03-17

---

## Tier 0 — Schedule / Context (No ML, Pure Logic)
Built from schedule_context.py. These aren't models — they're computed features that feed every model.

| Feature | Formula | Feeds |
|---|---|---|
| Rest days | Days since last game | All prop + game models |
| Back-to-back flag | 0 or 1 | Fatigue models |
| 3-in-4 flag | 3 games in 4 days | Fatigue models |
| Travel distance | Arena A → Arena B (miles) | Fatigue models |
| Timezone shift | East to West or West to East | Cognitive fatigue proxy |
| Home / Away | 1/0 | Win prob (+3.2 pts home avg) |
| Altitude flag | Denver / Utah / SA elevated | Visiting team fatigue Q4 |
| Days into road trip | Game 1,2,3,4,5 of road trip | Cumulative fatigue |

---

## Tier 1 — NBA API Only (13 Models) ✅ TRAINED
> Data requirement: 3 seasons NBA API stats + gamelogs. **Complete.**

| # | Model | Algorithm | Target | Key Inputs | Status |
|---|---|---|---|---|---|
| 1 | **Win probability** | XGBoost | P(team wins) | off_rtg, def_rtg, pace, rest, travel, L5/L10/L15 form | ✅ 67.7% acc |
| 2 | **Game total** | XGBoost | Total pts O/U | Both team pace, eFG%, TS%, defensive rtg | ✅ Trained |
| 3 | **Point spread** | XGBoost | Projected margin | All win prob features + home/away | ✅ Trained |
| 4 | **Blowout probability** | XGBoost | P(15+ pt margin) | Win prob features + variance indicators | ✅ Trained |
| 5 | **First half total** | XGBoost | First half pts | Team first-half tendencies from gamelogs | ✅ Trained |
| 6 | **Team pace predictor** | XGBoost | Possessions/game | 3-season pace trends + opponent pace | ✅ Trained |
| 7 | **Points prop** | XGBoost | Player pts tonight | Rolling 5/10/15/20 splits, usage%, matchup def_rtg, pace | ✅ Trained |
| 8 | **Rebounds prop** | XGBoost | Player reb tonight | Reb rate, opp ORB%, pace, lineup | ✅ Trained |
| 9 | **Assists prop** | XGBoost | Player ast tonight | AST%, team pace, playmaking role | ✅ Trained |
| 10 | **3PM prop** | XGBoost | 3-pointers made | 3pt%, C+S% vs off-dribble, opp 3pt defense | ✅ Trained |
| 11 | **Steals prop** | XGBoost | Steals tonight | STL%, opp TO rate, pace | ✅ Trained |
| 12 | **Blocks prop** | XGBoost | Blocks tonight | BLK%, opp paint frequency | ✅ Trained |
| 13 | **Turnovers prop** | XGBoost | Turnovers tonight | TO%, opp pressure tendency, pace | ✅ Trained |

---

## Tier 2 — Shot Charts + NBA API (5 Models) ✅ TRAINED
> Data requirement: 221,866 shots with court coordinates. **Complete.**

| # | Model | Algorithm | Target | Key Inputs | Status |
|---|---|---|---|---|---|
| 14 | **xFG v1** | XGBoost | P(shot made) from location | court_x, court_y, shot_type, distance, zone | ✅ Brier 0.226 |
| 15 | **Shot zone tendency** | Profile lookup | Player's zone distribution | Historical zone frequencies, 42-dim feature vector | ✅ 566 players |
| 16 | **Shot volume by zone** | Regression | Shots from each zone | Usage%, play style, opponent zone defense | ✅ |
| 17 | **Clutch efficiency** | Scoring model | Pts/possession in clutch | Clutch FG%, clutch TS%, shot selection 4Q <5min | ✅ 3 seasons |
| 18 | **Shot creation type** | Classifier | C+S vs off-dribble | Assist rates, dribbles before shot (from PBP) | ✅ |

---

## Tier 2B — Untapped NBA API Endpoints (6 Models) 🔲 Phase 3.5
> Data requirement: Pull hustle, tracking, matchup, synergy endpoints. 1-2 days.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 19 | **Defensive effort score** | Regression | Hustle rating | Deflections, screen assists, contested shots, loose balls |
| 20 | **Ball movement quality** | Regression | Pass → shot quality | Touch time, dribbles before shot, secondary assists |
| 21 | **Screen ROI model** | Regression | Pts created per screen | Screen assists, pts on plays post-screen |
| 22 | **Touch dependency model** | Regression | Pts per touch efficiency | Touch time, pts per touch vs season avg |
| 23 | **Play type efficiency** | Lookup + regression | Pts/possession by play type per player | Synergy PTS/POSS by play type |
| 24 | **Defender zone xFG adjustment** | Feature | Multiplier on xFG v1 | LeagueDashOppPtShot — FG% allowed by zone |

---

## Tier 3 — Historical Data (4 Models) 🔲 Phase 3.5
> Data requirement: Basketball Reference scraper. 3 days.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 25 | **Age curve model** | Polynomial regression | Efficiency decay at age N | 20,000+ player-seasons from BBRef |
| 26 | **Injury recurrence model** | Logistic regression | P(same injury recurs) | Historical injury type, return timeline, load |
| 27 | **Coaching adjustment model** | Pattern matching | Does team change scheme Q3? | Halftime play type distribution shift (BBRef + PBP) |
| 28 | **Historical ref tendency** | Profile lookup | Ref pace / foul rate / home win% | 10+ seasons of ref assignments from BBRef game logs |

---

## Tier 4 — Betting Market Models (6 Models) 🔲 Phase 4.5
> Data requirement: Action Network, OddsPortal, Pinnacle, DraftKings scraping.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 29 | **Sharp money detector** | Classifier | Is line moving on sharp or public? | Reverse line movement: line vs public bet % divergence |
| 30 | **CLV predictor** | Regression | Will this line improve by closing? | Opening vs current vs historical Pinnacle close |
| 31 | **Public fade model** | Rule + historical calibration | When to fade public? | Public % > 75% on one side + historical fade ROI |
| 32 | **Prop correlation model** | Correlation matrix | P(A over) given P(B over) | 3-season gamelog joint distributions |
| 33 | **Same-game parlay optimizer** | Correlation-adjusted pricing | True P(parlay hits) | Correlation matrix for all legs |
| 34 | **Soft book lag model** | Time-series | Minutes until Book X adjusts to Pinnacle move | Historical line movement timestamps |

---

## Tier 5 — Player Lifecycle Models (6 Models) 🔲 Phase 4.5
> Data requirement: BBRef injuries + nba_api + schedule context.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 35 | **DNP predictor** | Logistic regression | P(player sits tonight) | Coach B2B history, player workload, schedule, team record |
| 36 | **Load management predictor** | Historical pattern | P(star sits on B2B) | Coach history × player × team's playoff positioning |
| 37 | **Return-from-injury curve** | Regression | Efficiency at game N post-return | Historical comps by injury type |
| 38 | **Injury risk model** | Survival analysis | P(injury in next 7 days) | Miles run/game (CV), B2Bs, historical pattern, asymmetry |
| 39 | **Breakout predictor** | Anomaly + trend | Sustained usage increase coming? | Usage trend + efficiency + roster opportunity signal |
| 40 | **Contract year model** | Feature flag + historical | Motivation-adjusted performance | Last year of deal + historical contract year effect |

---

## Tier 6 — 20 CV Games: Spatial Models (10 Models) 🔲 Phase 7
> Data requirement: 20 full games with defender distance, spacing, play type from CV tracker.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 41 | **xFG v2** | XGBoost | P(make) with full spatial | court_x/y + defender_distance + shooter_velocity + contest angle + spacing |
| 42 | **Shot selection quality** | Regression | Was it a good decision? | xFG v2 vs league avg for that play type in that situation |
| 43 | **Play type classifier** | CNN / rule-based | ISO/PnR/Post/C+S/Transition | Sequential CV position data — who screened, who moved |
| 44 | **Defensive pressure score** | Regression | Pressure per possession | Closest defender proximity + closing speed (CV) |
| 45 | **Spacing rating** | Geometry | Offensive spread quality | 5-player convex hull area over possession |
| 46 | **Drive frequency predictor** | Regression | How often player attacks paint | Court trajectory toward basket (CV) |
| 47 | **Open shot rate model** | Regression | % of shots with defender >4ft | CV defender distance at shot moment |
| 48 | **Transition frequency model** | Regression | Fast break rate per lineup | Possession start position + time-to-shot |
| 49 | **Off-ball movement score** | Regression | Player activity without ball | Distance traveled per possession off-ball (CV) |
| 50 | **Possession value model** | Chain | Expected pts per possession | xFG v2 + TO rate + FT rate + shot selection |

---

## Tier 7 — 50 CV Games: Volume Models (8 Models) 🔲 Phase 10
> Data requirement: 50 full games processed. Needs game-to-game variance for stable estimates.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 51 | **Fatigue curve** | Polynomial regression | Efficiency decay vs distance + minutes | CV speed baseline vs current speed, Q4 vs Q1 |
| 52 | **Rebound positioning** | Classification | Who wins board given positions at shot | All 10 player positions at shot moment (CV) |
| 53 | **Late-game efficiency** | Regression | Player performance in Q4 vs full game | Q4 possessions + clutch context |
| 54 | **Closeout quality** | Regression | Defender closeout speed → P(open 3) | Defender foot speed at closeout (CV) |
| 55 | **Help defense frequency** | Regression | How often player leaves their man | Off-ball position tracking when drive happens (CV) |
| 56 | **Ball stagnation score** | Regression | Ball movement → better shots? | Possession-level ball movement sequences |
| 57 | **Screen effectiveness** | Regression | Expected pts created per screen | Position outcome tracking post-screen (CV) |
| 58 | **Turnover under pressure** | Regression | TO rate vs defensive pressure | CV pressure score + outcome labels |

---

## Tier 8 — 100 CV Games: Interaction Models (7 Models) 🔲 Phase 10
> Data requirement: 100 full games. Requires sample of specific lineups and matchups.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 59 | **Lineup chemistry** | Regression | 5-man net rating beyond individual stats | CV spatial synergy + on/off splits + minutes together |
| 60 | **Defensive matchup matrix** | Matrix factorization | Player A efficiency vs Defender B | Enough player-on-player matchup volume |
| 61 | **Substitution timing model** | Historical pattern | When coach subs → lineup quality | In-game sub patterns vs game state |
| 62 | **Momentum model** | LSTM / HMM | P(opponent run) from sequence | Sequential possession outcomes |
| 63 | **Foul drawing rate** | Regression | P(trip to line) per drive/shot | Contact frequency + foul call data |
| 64 | **Second chance model** | Regression | Expected pts from offensive rebound | Position at miss + rebound + outcome (CV) |
| 65 | **Pace per lineup** | Regression | Possessions/48 for specific 5-man unit | Enough lineup minutes combination |

---

## Tier 8B — NLP / Sentiment Models (4 Models) 🔲 Phase 9
> Data requirement: Reddit r/nba, Twitter beat reporters, RotoWire RSS, press conferences.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 66 | **Injury report NLP** | BERT classifier | Severity: minor/moderate/serious from text | "questionable (ankle)" vs "out (knee)" text patterns |
| 67 | **Injury news lag model** | Time-series regression | Minutes until book adjusts to injury news | Beat reporter tweet timestamp vs line movement timestamp |
| 68 | **Team chemistry sentiment** | BERT sentiment | Morale direction: improving/stable/declining | Post-game interview + Reddit sentiment trend |
| 69 | **Beat reporter credibility ranker** | Accuracy tracking | Trust score per reporter | Historical report accuracy vs official injury timeline |

---

## Tier 9 — In-Game / Live Models (6 Models) 🔲 Phase 11
> Data requirement: Real-time score feed + running simulator.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 70 | **Live prop updater** | Bayesian update | Full game projection given current halftime stats | Prior (pre-game sim) + halftime box score |
| 71 | **Comeback probability** | Regression | P(team trailing by X with Y min comes back) | Historical patterns + current lineup + momentum |
| 72 | **Garbage time predictor** | Classifier | P(game decided, starters pulled by Q4) | Score margin, time remaining, coach tendency |
| 73 | **Foul trouble model** | Markov chain | P(player fouls out given N fouls at halftime) | Historical foul rates + remaining minutes + coach behavior |
| 74 | **Q4 star usage model** | Regression | Does coach increase usage in close 4th? | Coach history + game state + player fatigue |
| 75 | **Momentum run detector** | HMM | P(team goes on 8-0 run from this state) | Possession sequence + lineup + momentum score |

---

## Tier 10 — Full Stack (7 Models) 🔲 Phase 12 / 16
> Data requirement: 200+ full games + all previous tiers trained.

| # | Model | Algorithm | Target | Key Inputs |
|---|---|---|---|---|
| 76 | **Full possession simulator** | 7-model chain + Monte Carlo | Stat distributions for all players | All 75 models above feeding the chain |
| 77 | **Live win probability LSTM** | LSTM | Real-time P(win) per possession | Possession sequence embedding + score + lineup |
| 78 | **True player impact** | Regression | Spatial on/off adjusted impact | CV spatial on/off + lineup chemistry |
| 79 | **Lineup optimizer** | Combinatorial + regression | Best 5-man unit for tonight's specific matchup | Matchup matrix + chemistry + fatigue |
| 80 | **Prop pricing engine** | Monte Carlo output | Full P(over/under) distribution vs book | Simulator distributions + correlation matrix |
| 81 | **Regression detector** | Rolling z-score | P(shooting luck normalizes next N games) | xFG vs actual FG% divergence window |
| 82 | **Injury impact model** | Lineup chemistry subtraction | Value lost when player X is out | Lineup chemistry → value attribution per player |

---

## The 7-Model Possession Chain (Core Simulator Engine)

These 7 run 10,000 times per game. Every other model feeds one of these as an input.

```
[1] Play Type Selector
    Inputs: lineup + game state + play_type_classifier (M43) + momentum (M62)
    Output: ISO / PnR-BH / PnR-Screen / Post / C+S / Cut / Transition
        ↓
[2] Shot Selector
    Inputs: play type + zone_tendency (M15) + drive_frequency (M46) + spacing (M45)
    Output: who shoots + from what zone
        ↓
[3] xFG Model
    Inputs: shooter + zone + defender_distance + contest_angle + fatigue multiplier
    Uses: xFG v2 (M41) if CV data available, else xFG v1 (M14)
    Output: P(shot made) = 0.0 – 1.0
        ↓
[4] Turnover / Foul Model
    Inputs: pressure_score (M44) + turnover_under_pressure (M58) + foul_drawing (M63)
    Output: P(shot) vs P(TO) vs P(foul draw) per possession
        ↓
[5] Rebound Model
    Inputs: all 10 positions at shot (M52) + team ORB% + spacing (M45)
    Output: who gets rebound if missed
        ↓
[6] Fatigue Model
    Inputs: distance_run (CV) + minutes (box score) + fatigue_curve (M51)
    Output: efficiency multiplier 0.85–1.0
        ↓
[7] Substitution Model
    Inputs: foul_trouble (M73) + fatigue (M51) + score_margin + substitution_timing (M61)
    Output: does coach sub? who comes in?
```

---

## Model Count Summary

| Tier | Models | Requirement | Status |
|---|---|---|---|
| 0 | 8 computed features | None | ✅ |
| 1 | 13 | NBA API (3 seasons) | ✅ Trained |
| 2 | 5 | 221K shot charts | ✅ Trained |
| 2B | 6 | Untapped nba_api endpoints | 🔲 Phase 3.5 |
| 3 | 4 | Basketball Reference | 🔲 Phase 3.5 |
| 4 | 6 | Betting market scrapers | 🔲 Phase 4.5 |
| 5 | 6 | BBRef injuries + schedule | 🔲 Phase 4.5 |
| 6 | 10 | 20 CV games | 🔲 Phase 7 |
| 7 | 8 | 50 CV games | 🔲 Phase 10 |
| 8 | 7 | 100 CV games | 🔲 Phase 10 |
| 8B | 4 | NLP data sources | 🔲 Phase 9 |
| 9 | 6 | Live data feed | 🔲 Phase 11 |
| 10 | 7 | 200 CV games + all above | 🔲 Phase 12/16 |
| **Total** | **90** | | |

---

## Related
- [[Complete Data Sources]] — every input that feeds these models
- [[Prediction Pipeline]] — how all 90 models combine into one prediction
- [[System Architecture]] — technical implementation
