# Model Universe — Master Index

The complete index of every model CourtVision can build. **350 models across 16 domains.**

Supersedes the 90-model roadmap in `docs/ML_MODELS.md` / `Complete Model Catalog`.
End goal: the most advanced sports-intelligence AI. Every model earns its place — even a +0.005 R² lift on one prop is kept, because edges compound.

Status: ✅ built · ⚙️ partial / needs data · 🔲 planned
This is a **plan only** — nothing here is built yet beyond the ✅ rows. Build loop: `docs/models/BUILD_PROMPT.md`.

Mirror of the Obsidian note `vault/Models/Model Universe.md` (vault is gitignored; this is the git-tracked copy).

---

## How To Read This

- **ID** — stable `Mxxx` handle. Never renumber; new models append.
- **Layer** — where it sits in the stack (see Connection Map). L0=feature, L1=atomic, L2=possession chain, L3=aggregation, L4=meta, L5=betting, L6=live.
- **Data** — minimum data requirement. `API`=nba_api, `BBRef`=Basketball Reference, `Shots`=shot charts, `CVn`=n CV-tracked games, `Mkt`=betting market feed, `News`=NLP sources, `Live`=real-time feed, `Sched`=schedule context, `PBP`=play-by-play.
- A model is only as good as the tier below it. Build bottom-up.

---

## The Connection Map — 7 Layers

```
L0  FEATURES        schedule context · box scores · shot charts · CV tracking
                    · betting lines · injury news · play-by-play
                         │  (feature_engineering.py → 65+ features)
                         ▼
L1  ATOMIC MODELS   props · shot models · context multipliers · lifecycle
                    · officiating · coaching · spatial/CV · team/lineup
                         │  each predicts ONE quantity from L0 features
                         ▼
L2  POSSESSION      [1]play-type → [2]shot-select → [3]xFG → [4]TO/foul
    CHAIN           → [5]rebound → [6]fatigue → [7]substitution
    (7-model loop)  every L1 model feeds one of these 7 nodes
                         │  runs 10,000×/game
                         ▼
L3  AGGREGATION     Monte Carlo rollup → player stat distributions
                    + game outcome models (win/spread/total/quarters)
                         │
                         ▼
L4  META            stacking · isotonic calibration · conformal intervals
                    · quantile · regime detection · drift · uncertainty
                         │  corrects & bounds L3 output
                         ▼
L5  BETTING         edge detection → pricing engine → Kelly sizing
                    → portfolio guard → CLV tracking → parlay optimizer
                         │  compares calibrated probs vs market lines
                         ▼
L6  LIVE            Bayesian/LSTM updaters re-run L3→L5 each possession
                    with real-time score + lineup state

CROSS-CUTTING:
  NLP/sentiment (Domain L) ──feeds──▶ L1 lifecycle + L5 news-lag
  Market models (Domain K) ──feeds──▶ L5 edge + L4 book-bias
  Simulation/ratings (Domain O) ─────▶ wraps L2→L3, attributes value
```

**Rule of dependency:** L(n) may only consume outputs of L(n-1) and below. The possession chain (L2) is the spine — 90% of L1 models exist to sharpen one of its 7 nodes.

---

## Domain A — Game Outcome (27 models) · Layer L3

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M001 | Win probability | P(home wins) | XGBoost clf | API | ✅ |
| M002 | Point spread | Final margin | XGBoost reg | API | ✅ |
| M003 | Game total | Total points | XGBoost reg | API | ✅ |
| M004 | First-half total | 1H points | XGBoost reg | API | ✅ |
| M005 | Second-half total | 2H points | XGBoost reg | API | ✅ |
| M006 | Q1 total | Q1 points | XGBoost reg | API | 🔲 |
| M007 | Q2 total | Q2 points | XGBoost reg | API | 🔲 |
| M008 | Q3 total | Q3 points | XGBoost reg | API | 🔲 |
| M009 | Q4 total | Q4 points | XGBoost reg | API | 🔲 |
| M010 | First-half spread | 1H margin | XGBoost reg | API | 🔲 |
| M011 | Quarter spreads (×4) | Per-quarter margin | XGBoost reg | API | 🔲 |
| M012 | Home team total | Home points | XGBoost reg | API | ⚙️ |
| M013 | Away team total | Away points | XGBoost reg | API | ⚙️ |
| M014 | Blowout probability | P(margin>15) | XGBoost clf | API | ✅ |
| M015 | Overtime probability | P(game→OT) | Logistic | API | ✅ |
| M016 | Double-OT probability | P(2+ OT) | Logistic | API | 🔲 |
| M017 | Game pace | Possessions | XGBoost reg | API | ✅ |
| M018 | Highest-scoring quarter | argmax quarter | Multiclass | API | 🔲 |
| M019 | Margin variance | Game volatility σ | Quantile reg | API | 🔲 |
| M020 | Both teams 100+ | P(both ≥100) | Logistic | API | 🔲 |
| M021 | Largest lead | Max lead size | Quantile reg | API | 🔲 |
| M022 | Lead changes count | # lead changes | Poisson reg | PBP | 🔲 |
| M023 | Wire-to-wire | P(one team leads throughout) | Logistic | PBP | 🔲 |
| M024 | Game competitiveness index | Closeness score | Regression | PBP | 🔲 |
| M025 | Final margin distribution | Full margin PMF | Monte Carlo | API+L2 | ⚙️ |
| M026 | Race to 20 points | P(home first to 20) | Logistic | PBP | 🔲 |
| M027 | No-vig fair line | Devigged win/spread/total | Analytic | Mkt | 🔲 |

---

## Domain B — Player Props (48 models) · Layer L3

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M028 | Points prop | Player PTS | XGBoost reg | API | ✅ |
| M029 | Rebounds prop | Player REB | XGBoost reg | API | ✅ |
| M030 | Assists prop | Player AST | XGBoost reg | API | ✅ |
| M031 | 3PM prop | 3-pointers made | XGBoost reg | API | ✅ |
| M032 | Steals prop | Player STL | XGBoost reg | API | ✅ |
| M033 | Blocks prop | Player BLK | XGBoost reg | API | ✅ |
| M034 | Turnovers prop | Player TOV | XGBoost reg | API | ✅ |
| M035 | FGM prop | Field goals made | XGBoost reg | API | 🔲 |
| M036 | FGA prop | Field goal attempts | XGBoost reg | API | 🔲 |
| M037 | FTM prop | Free throws made | XGBoost reg | API | 🔲 |
| M038 | FTA prop | Free throw attempts | XGBoost reg | API | 🔲 |
| M039 | 3PA prop | 3-point attempts | XGBoost reg | API | 🔲 |
| M040 | OREB prop | Offensive rebounds | XGBoost reg | API | 🔲 |
| M041 | DREB prop | Defensive rebounds | XGBoost reg | API | 🔲 |
| M042 | Minutes prop | Minutes played | XGBoost reg | API | ⚙️ |
| M043 | Personal fouls prop | Fouls committed | Poisson reg | API | 🔲 |
| M044 | Plus-minus prop | Player +/- | XGBoost reg | API | ⚙️ |
| M045 | PRA prop | PTS+REB+AST | Joint sim | API+L2 | ⚙️ |
| M046 | PR prop | PTS+REB | Joint sim | API+L2 | 🔲 |
| M047 | PA prop | PTS+AST | Joint sim | API+L2 | 🔲 |
| M048 | RA prop | REB+AST | Joint sim | API+L2 | 🔲 |
| M049 | Stocks prop | STL+BLK | Joint sim | API+L2 | 🔲 |
| M050 | Double-double | P(DD) | Logistic | API+L2 | 🔲 |
| M051 | Triple-double | P(TD) | Logistic | API+L2 | 🔲 |
| M052 | First basket scorer | P(player scores 1st) | Multiclass | PBP | 🔲 |
| M053 | First team to score | P(home scores 1st) | Logistic | PBP | 🔲 |
| M054 | Anytime FG made | P(≥1 FG) | Logistic | API | 🔲 |
| M055 | Anytime 3PM | P(≥1 three) | Logistic | API | 🔲 |
| M056 | 20-point game | P(PTS≥20) | Logistic | API+L2 | 🔲 |
| M057 | 30-point game | P(PTS≥30) | Logistic | API+L2 | 🔲 |
| M058 | 40-point game | P(PTS≥40) | Logistic | API+L2 | 🔲 |
| M059 | 10-rebound game | P(REB≥10) | Logistic | API+L2 | 🔲 |
| M060 | 10-assist game | P(AST≥10) | Logistic | API+L2 | 🔲 |
| M061 | 5+ threes game | P(3PM≥5) | Logistic | API+L2 | 🔲 |
| M062 | Q1 points prop | Player Q1 PTS | XGBoost reg | PBP | 🔲 |
| M063 | First-half points prop | Player 1H PTS | XGBoost reg | PBP | 🔲 |
| M064 | DK fantasy points | DraftKings score | Joint sim | API+L2 | 🔲 |
| M065 | FD fantasy points | FanDuel score | Joint sim | API+L2 | 🔲 |
| M066 | Player to record a stat | P(≥1 STL/BLK) | Logistic | API | 🔲 |
| M067 | Points-in-paint prop | Paint scoring | XGBoost reg | Shots | 🔲 |
| M068 | Fast-break points prop | Transition PTS | XGBoost reg | PBP | 🔲 |
| M069 | Second-chance points prop | Putback PTS | XGBoost reg | PBP | 🔲 |
| M070 | Points off turnovers prop | PTS off TO | XGBoost reg | PBP | 🔲 |
| M071 | Bench points prop | Team bench PTS | XGBoost reg | API | 🔲 |
| M072 | Starter points prop | Team starter PTS | XGBoost reg | API | 🔲 |
| M073 | Player game-high | P(team scoring leader) | Multiclass | API+L2 | 🔲 |
| M074 | Usage-conditional projection | Stats given usage% | Hierarchical reg | API | ⚙️ |
| M075 | Minutes-conditional projection | Per-36 → projected | Regression | API | ⚙️ |

---

## Domain C — Shot-Level (22 models) · Layer L1

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M076 | xFG v1 | P(make) from location | XGBoost | Shots | ✅ |
| M077 | xFG v2 (defender) | P(make) + defender dist | XGBoost | CV20 | ⚙️ |
| M078 | xFG v3 (full spatial) | P(make) + contest angle + velocity | XGBoost | CV50 | 🔲 |
| M079 | Shot selection quality | Was it a good shot? | Regression | Shots+CV | ⚙️ |
| M080 | Shot type classifier | 2pt/3pt/FT/dunk | Multiclass | Shots | ✅ |
| M081 | Shot zone tendency | Player zone distribution | Profile | Shots | ✅ |
| M082 | Shot volume by zone | Attempts per zone | Regression | Shots | ✅ |
| M083 | Shot creation type | C+S vs off-dribble | Classifier | PBP | ✅ |
| M084 | Contested shot classifier | Is shot contested? | XGBoost clf | CV20 | ✅ |
| M085 | Contest rate model | % shots contested | Regression | CV20 | ✅ |
| M086 | Shot clock pressure | Difficulty vs clock | Regression | PBP | ✅ |
| M087 | Expected points per shot | xPTS per attempt | Regression | Shots | 🔲 |
| M088 | Dunk probability | P(attempt is dunk) | Logistic | CV20 | 🔲 |
| M089 | Putback probability | P(OREB→putback) | Logistic | CV20 | 🔲 |
| M090 | And-one probability | P(make + foul) | Logistic | PBP | 🔲 |
| M091 | Heat-check detector | P(low-quality shot after make) | Classifier | PBP | 🔲 |
| M092 | Shot difficulty index | Composite difficulty 0-100 | Regression | CV20 | 🔲 |
| M093 | Catch-shoot vs pull-up split | Shot mix classifier | Classifier | API | 🔲 |
| M094 | Corner-three propensity | P(three is corner) | Logistic | Shots | 🔲 |
| M095 | Rim finish model | P(make at rim) | XGBoost | CV20 | 🔲 |
| M096 | Mid-range efficiency | Mid-range FG% | Regression | Shots | 🔲 |
| M097 | Free-throw make model | P(FT make) | Beta-binomial | API | 🔲 |

---

## Domain D — Possession / Play-Type (17 models) · Layer L2 (chain spine)

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M098 | Play-type selector | ISO/PnR/Post/C+S/Cut/Transition | Multiclass | PBP+CV | ⚙️ |
| M099 | Play-type classifier (CV) | Play type from positions | CNN/rule | CV20 | 🔲 |
| M100 | Shot selector | Who shoots, from where | Conditional | API+CV | ⚙️ |
| M101 | Possession outcome | Shot/TO/foul/end | Multiclass | PBP | ⚙️ |
| M102 | Possession value (xPPP) | Expected pts/possession | Chain | All L1 | ⚙️ |
| M103 | Turnover model | P(TO) per possession | Logistic | PBP | ⚙️ |
| M104 | Foul-draw model | P(shooting foul drawn) | Logistic | PBP | ✅ |
| M105 | Free-throw trip model | P(possession→FTs) | Logistic | PBP | 🔲 |
| M106 | Transition trigger | P(possession is transition) | Logistic | PBP | 🔲 |
| M107 | Early-offense detector | Shot in first 7s | Classifier | PBP | 🔲 |
| M108 | Late-clock scramble | Broken-play model | Classifier | CV20 | 🔲 |
| M109 | Inbound play model | Outcome of inbound set | Multiclass | CV20 | 🔲 |
| M110 | End-of-quarter possession | Last-shot scenario | Conditional | PBP | 🔲 |
| M111 | Dead-ball vs live-ball | Possession-start classifier | Classifier | PBP | 🔲 |
| M112 | Possession-length model | Seconds used | Regression | PBP | 🔲 |
| M113 | Pass-count model | Passes before shot | Poisson | CV20 | 🔲 |
| M114 | Possession transition matrix | State→state Markov | Markov | PBP | 🔲 |

---

## Domain E — Spatial / CV Tracking (27 models) · Layer L1

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M115 | Spacing rating | 5-player convex hull area | Geometry | CV20 | ⚙️ |
| M116 | Defender distance | Closest defender ft | CV measure | CV20 | ✅ |
| M117 | Closeout quality | Closeout → P(open 3) | Regression | CV20 | ⚙️ |
| M118 | Closeout speed | Defender ft/s on closeout | CV measure | CV50 | 🔲 |
| M119 | Screen effectiveness | Pts created per screen | Regression | CV20 | ⚙️ |
| M120 | Screen navigation | Defender screen-nav skill | Regression | CV50 | 🔲 |
| M121 | Drive frequency | Drives per game | Regression | CV20 | ⚙️ |
| M122 | Drive success | P(drive→score) | Logistic | CV20 | 🔲 |
| M123 | Off-ball movement score | Distance off-ball/possession | CV measure | CV20 | ⚙️ |
| M124 | Gravity score | How much defense a player pulls | Regression | CV50 | 🔲 |
| M125 | Help-defense frequency | How often leaves man | Regression | CV20 | ⚙️ |
| M126 | Rotation speed | Defensive rotation ft/s | CV measure | CV50 | 🔲 |
| M127 | Rebound positioning | Who wins board from positions | Logistic | CV20 | ⚙️ |
| M128 | Box-out effectiveness | Box-out → rebound won | Regression | CV50 | 🔲 |
| M129 | Contest angle | Angle of shot contest | CV measure | CV20 | 🔲 |
| M130 | Paint touches | Touches inside paint | CV measure | CV20 | 🔲 |
| M131 | Rim deterrence | Shots altered near rim | Regression | CV50 | 🔲 |
| M132 | On-ball pressure | Pressure on ball-handler | Regression | CV20 | ✅ |
| M133 | Ball stagnation score | Ball movement → shot quality | Regression | CV20 | ⚙️ |
| M134 | Court coverage | Defensive area covered | Geometry | CV50 | 🔲 |
| M135 | Defensive stance quality | Stance/positioning score | Classifier | CV100 | 🔲 |
| M136 | Transition speed | Team ft/s in transition | CV measure | CV50 | 🔲 |
| M137 | Cutting frequency | Off-ball cuts per game | CV measure | CV50 | 🔲 |
| M138 | Spacing-advantage model | Offense vs defense spread delta | Geometry | CV20 | ⚙️ |
| M139 | Pass-lane risk | P(pass intercepted) | Logistic | CV50 | 🔲 |
| M140 | Defensive matchup tracker | Who guards whom | Assignment | CV20 | ⚙️ |
| M141 | Velocity/fatigue baseline | Per-player speed baseline | CV measure | CV20 | ⚙️ |

---

## Domain F — Player Lifecycle / Availability (22 models) · Layer L1

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M142 | DNP predictor | P(player sits) | Logistic | API+Sched | ✅ |
| M143 | Load management | P(star rests B2B) | Pattern | API+Sched | ✅ |
| M144 | Injury risk | P(injury in 7d) | Survival | CV+Hist | ✅ |
| M145 | Injury return curve | Efficiency at game N back | Regression | BBRef | ✅ |
| M146 | Injury severity classifier | Minor/moderate/serious | Classifier | News | ✅ |
| M147 | Injury recurrence | P(same injury recurs) | Logistic | BBRef | 🔲 |
| M148 | Minutes projection | Expected minutes | Regression | API | ⚙️ |
| M149 | Minutes floor | Guaranteed minimum | Regression | API | ✅ |
| M150 | Minutes ceiling | Realistic maximum | Quantile reg | API | 🔲 |
| M151 | Rotation predictor | P(in rotation) | Classifier | API | ✅ |
| M152 | Starter probability | P(starts tonight) | Logistic | API+News | 🔲 |
| M153 | Breakout predictor | Sustained usage rise | Anomaly+trend | API | ✅ |
| M154 | Decline detector | Sustained efficiency drop | Anomaly+trend | API | 🔲 |
| M155 | Age curve | Efficiency decay at age N | Polynomial | BBRef | ✅ |
| M156 | Contract-year quantifier | Motivation adjustment | Feature+hist | BBRef | ✅ |
| M157 | Rookie progression curve | Rookie game-N efficiency | Regression | BBRef | 🔲 |
| M158 | Trade impact model | Performance post-trade | Regression | BBRef | 🔲 |
| M159 | Role-change detector | Detect new on-court role | Anomaly | API | 🔲 |
| M160 | Conditioning ramp | Efficiency early-season | Regression | API | 🔲 |
| M161 | Rest-of-season projection | ROS stat line | Regression | API | 🔲 |
| M162 | Workload fatigue index | Cumulative load score | CV+Sched | CV20 | ⚙️ |
| M163 | Return-to-form timeline | Games until baseline post-injury | Regression | BBRef | 🔲 |

---

## Domain G — Context Multipliers (19 models) · Layer L1

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M164 | Rest-day multiplier | Pts multiplier by rest | Regression | Sched | ✅ |
| M165 | Back-to-back adjustment | B2B stat multipliers | Regression | Sched | ✅ |
| M166 | 3-in-4 fatigue | Density fatigue multiplier | Regression | Sched | 🔲 |
| M167 | Travel impact | Travel-distance adjustment | Regression | Sched | ✅ |
| M168 | Timezone-shift model | Circadian penalty | Regression | Sched | 🔲 |
| M169 | Altitude model | Q4 fatigue at elevation | Regression | Sched | ✅ |
| M170 | Home/away splits | Venue stat splits | Profile | API | ✅ |
| M171 | Road-trip fatigue | Cumulative road-trip penalty | Regression | Sched | 🔲 |
| M172 | Schedule-density model | Games-in-N-days load | Regression | Sched | 🔲 |
| M173 | Day vs night game | Tip-time performance effect | Regression | Sched | 🔲 |
| M174 | National-TV game effect | Spotlight performance shift | Regression | Sched | 🔲 |
| M175 | Revenge-game model | Post-trade/loss motivation | Feature+hist | News | 🔲 |
| M176 | Lookahead/trap-game | Letdown-spot detector | Classifier | Sched | 🔲 |
| M177 | Division/rivalry game | Rivalry intensity effect | Feature | Sched | 🔲 |
| M178 | Season-segment model | Early/mid/late-season form | Regression | API | 🔲 |
| M179 | Playoff-seeding stakes | Urgency/effort multiplier | Regression | API | ✅ |
| M180 | Tank detector | P(team tanking) | Classifier | API+News | 🔲 |
| M181 | Holiday/marquee game | Special-game performance | Feature | Sched | 🔲 |
| M182 | Crowd/attendance effect | Home-edge by attendance | Regression | API | 🔲 |

---

## Domain H — Team / Lineup (17 models) · Layer L1→L2

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M183 | Lineup chemistry | 5-man net-rtg delta | Regression | CV100 | ⚙️ |
| M184 | Lineup offense rating | 5-man ORtg | Regression | API+CV | 🔲 |
| M185 | Lineup defense rating | 5-man DRtg | Regression | API+CV | 🔲 |
| M186 | On/off splits | Player on/off impact | Regression | API | ⚙️ |
| M187 | Substitution timing | When coach subs | Pattern/clf | CV100 | ⚙️ |
| M188 | Matchup matrix | Player A vs Defender B | Matrix factorization | CV100 | ⚙️ |
| M189 | Lineup optimizer | Best 5 for tonight | Combinatorial | API+CV | 🔲 |
| M190 | Lineup pace | Possessions/48 per unit | Regression | CV100 | 🔲 |
| M191 | Bench-unit model | Bench-lineup output | Regression | API | 🔲 |
| M192 | Closing-lineup predictor | Q4 lineup forecast | Classifier | API | 🔲 |
| M193 | 2-man pairing synergy | 2-player net-rtg lift | Regression | API+CV | 🔲 |
| M194 | Positional matchup model | Position-vs-position edge | Regression | API | 🔲 |
| M195 | Cross-matchup assignment | Defensive assignment forecast | Assignment | CV20 | ⚙️ |
| M196 | Lineup variance | Output volatility per unit | Quantile reg | API | 🔲 |
| M197 | Team off-rtg model | Team offensive rating | XGBoost reg | API | ✅ |
| M198 | Team def-rtg model | Team defensive rating | XGBoost reg | API | ✅ |
| M199 | Team-total normalizer | Reconcile player→team totals | Constraint solver | API | ✅ |

---

## Domain I — Officiating (11 models) · Layer L1

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M200 | Ref crew tendency | Crew foul/pace profile | Profile | BBRef | ✅ |
| M201 | Ref foul-rate model | Fouls called/game | Regression | BBRef | ✅ |
| M202 | Ref pace effect | Pace shift by crew | Regression | BBRef | 🔲 |
| M203 | Ref home-bias model | Home win% by crew | Regression | BBRef | ✅ |
| M204 | Ref total effect | Total points shift by crew | Regression | BBRef | 🔲 |
| M205 | Tech/ejection rate | P(tech) by crew | Logistic | BBRef | 🔲 |
| M206 | Replay-review frequency | Reviews per game | Poisson | PBP | 🔲 |
| M207 | Star-treatment model | Foul-call bias for stars | Regression | PBP | 🔲 |
| M208 | Makeup-call detector | P(compensating call) | Classifier | PBP | 🔲 |
| M209 | Crew-chief vs umpire effect | Role-weighted crew profile | Regression | BBRef | 🔲 |
| M210 | Ref assignment predictor | Which crew tonight | Multiclass | BBRef | 🔲 |

---

## Domain J — Coaching (13 models) · Layer L1

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M211 | Timeout-usage model | When coach calls TO | Pattern | PBP | 🔲 |
| M212 | ATO efficiency | Pts after timeout | Regression | PBP | 🔲 |
| M213 | Coach-challenge model | Challenge use + success rate | Logistic | PBP | 🔲 |
| M214 | Scheme-adjustment (Q3) | Does team change scheme? | Pattern | PBP+CV | 🔲 |
| M215 | Rotation-depth model | How deep coach goes | Regression | API | 🔲 |
| M216 | Hack-a strategy detector | P(intentional fouling) | Classifier | PBP | 🔲 |
| M217 | Intentional-foul timing | When to foul late | Pattern | PBP | 🔲 |
| M218 | Pace-philosophy model | Coach pace tendency | Profile | API | 🔲 |
| M219 | Late-game shot coaching | Coach's clutch shot mix | Profile | PBP | 🔲 |
| M220 | Defensive-scheme classifier | Zone/switch/drop/ICE | Multiclass | CV50 | 🔲 |
| M221 | Playoff-adjustment model | Coach scheme shift in playoffs | Pattern | PBP | 🔲 |
| M222 | Minutes-distribution model | How coach allocates minutes | Regression | API | ⚙️ |
| M223 | Garbage-time pull model | When starters get pulled | Classifier | PBP | ✅ |

---

## Domain K — Betting Market (25 models) · Layer L5

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M224 | Sharp-money detector | Sharp vs public line move | Classifier | Mkt | ⚙️ |
| M225 | CLV predictor | Will line improve by close? | Regression | Mkt | ⚙️ |
| M226 | Public-fade model | When to fade public | Rule+calib | Mkt | ✅ |
| M227 | Line-origination model | Where the opener comes from | Regression | Mkt | 🔲 |
| M228 | Opening-line predictor | Forecast the opener | Regression | Mkt | 🔲 |
| M229 | Closing-line predictor | Forecast the close | Regression | Mkt | 🔲 |
| M230 | Steam-move detector | Coordinated sharp move | Classifier | Mkt | 🔲 |
| M231 | Reverse-line-movement | RLM signal | Classifier | Mkt | ✅ |
| M232 | Soft-book lag model | Minutes until book adjusts | Time-series | Mkt | ✅ |
| M233 | Hold/vig analyzer | Book hold % per market | Analytic | Mkt | 🔲 |
| M234 | Arbitrage detector | Cross-book arb opportunity | Analytic | Mkt | 🔲 |
| M235 | Middle-opportunity model | Middling window detector | Analytic | Mkt | 🔲 |
| M236 | Prop correlation matrix | Joint P(A,B) over | Correlation | API | ✅ |
| M237 | Same-game parlay optimizer | True P(parlay hits) | Corr-adjusted | API | ✅ |
| M238 | Alt-line EV model | +EV on alt totals | Regression | Mkt | ✅ |
| M239 | Alt-line ladder | Alt-line odds matrix | Lookup | Mkt | ✅ |
| M240 | Book-bias detector | Is book mispricing? | Classifier | Mkt | ✅ |
| M241 | Limit-change signal | Limit move = sharp signal | Classifier | Mkt | 🔲 |
| M242 | Market-consensus fair value | No-vig consensus prob | Analytic | Mkt | ⚙️ |
| M243 | Line-shopping optimizer | Best book per bet | Optimizer | Mkt | 🔲 |
| M244 | Futures pricing model | Season-long futures fair value | Monte Carlo | API | 🔲 |
| M245 | Derivative-market pricing | Quarters/halves/team-totals fair value | Monte Carlo | API+L2 | 🔲 |
| M246 | Promo/boost EV model | EV of book promos & boosts | Analytic | Mkt | 🔲 |
| M247 | Bet-timing model | Optimal moment to place bet | Time-series | Mkt | 🔲 |
| M248 | Market-efficiency scorer | How sharp is this market? | Regression | Mkt | 🔲 |

---

## Domain L — NLP / Sentiment / News (15 models) · Layer L1 cross-cut

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M249 | Injury-report NLP | Severity from report text | BERT clf | News | ⚙️ |
| M250 | Injury-news lag model | Minutes until book reacts | Time-series | News+Mkt | 🔲 |
| M251 | Beat-reporter credibility | Trust score per reporter | Accuracy track | News | ⚙️ |
| M252 | Team-chemistry sentiment | Morale direction | BERT sentiment | News | 🔲 |
| M253 | Social-sentiment momentum | Fan-sentiment trend | Sentiment ts | News | 🔲 |
| M254 | Press-conference signal | Coach-quote intent extraction | NLP extract | News | 🔲 |
| M255 | Lineup-news detector | Detect starting-lineup news | NER+clf | News | 🔲 |
| M256 | Trade-rumor impact | Performance under rumor | Regression | News | 🔲 |
| M257 | Coach-hot-seat model | P(coach fired) effect | Classifier | News | 🔲 |
| M258 | Motivation/narrative detector | Storyline-driven motivation | NLP | News | 🔲 |
| M259 | News-source latency ranker | Which source breaks first | Ranking | News | 🔲 |
| M260 | Reddit r/nba sentiment | Community sentiment index | Sentiment | News | 🔲 |
| M261 | Beat-reporter tweet classifier | Actionable vs noise | Classifier | News | 🔲 |
| M262 | Injury-status resolver | Questionable→play/sit prob | Classifier | News | 🔲 |
| M263 | Rumor-vs-fact classifier | Confirmed vs speculative news | Classifier | News | 🔲 |

---

## Domain M — Live / In-Game (18 models) · Layer L6

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M264 | Live win probability | Real-time P(win) | LSTM | Live | ⚙️ |
| M265 | Live prop updater | Bayesian full-game projection | Bayesian | Live | ⚙️ |
| M266 | Live total updater | In-game total revision | Bayesian | Live | 🔲 |
| M267 | Live spread updater | In-game spread revision | Bayesian | Live | 🔲 |
| M268 | Momentum-run detector | P(8-0 run from state) | HMM | Live+PBP | ✅ |
| M269 | Comeback probability | P(trailing team comes back) | Regression | Live | 🔲 |
| M270 | Foul-trouble model | P(fouls out given N fouls) | Markov | Live | ✅ |
| M271 | Garbage-time predictor | P(starters pulled by Q4) | Classifier | Live | ✅ |
| M272 | Q4 star-usage model | Usage spike in close 4th | Regression | Live | 🔲 |
| M273 | Live pace updater | In-game pace revision | Bayesian | Live | 🔲 |
| M274 | Next-possession scorer | P(next possession scores) | Logistic | Live+PBP | ✅ |
| M275 | Fourth-quarter collapse | P(blown lead) | Regression | Live | 🔲 |
| M276 | Clutch-performance live | Clutch-time efficiency live | Regression | Live | 🔲 |
| M277 | In-game injury detector | Detect injury from feed/CV | Anomaly | Live+CV | 🔲 |
| M278 | Live substitution predictor | Next sub forecast | Classifier | Live | 🔲 |
| M279 | Timeout-impact live | Pts swing after TO | Regression | Live | 🔲 |
| M280 | Live xPTS tracker | Running expected score | Chain | Live+L2 | 🔲 |
| M281 | End-of-game scenario model | Final-minute decision tree | Tree/sim | Live | 🔲 |

---

## Domain N — Meta / Ensemble / Calibration (23 models) · Layer L4

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M282 | Prop stacking meta (×7) | Residual correction per stat | Ridge | API | ✅ |
| M283 | Prop calibration (×7) | P(over) isotonic calibration | Isotonic | API | ✅ |
| M284 | Win-prob calibration | Win-prob isotonic calibration | Isotonic | API | ✅ |
| M285 | Conformal prediction intervals | Distribution-free intervals | Conformal | API | ⚙️ |
| M286 | Quantile-regression props | Full quantile fan per stat | Quantile reg | API | ⚙️ |
| M287 | Regime detector | Detect distribution shift | Changepoint | API | ⚙️ |
| M288 | Model-drift detector | Per-model drift alarm | PSI/KS test | API | 🔲 |
| M289 | Uncertainty estimator | Predictive σ per prop | Ensemble var | API | ⚙️ |
| M290 | Ensemble router | Pick best model per context | Meta-clf | API | ⚙️ |
| M291 | Hierarchical pooling | Player→position→league shrinkage | Hierarchical Bayes | API | ⚙️ |
| M292 | Multitask props head | Joint multi-stat learner | Multitask NN | API | ⚙️ |
| M293 | Segment calibrator | Calibrate by player segment | Isotonic/segment | API | ⚙️ |
| M294 | Model-confidence scorer | Trust score per prediction | Meta-reg | API | 🔲 |
| M295 | Stacked super-ensemble | Blend all base learners | Stacking | API | 🔲 |
| M296 | Bayesian model averaging | Weight models by evidence | BMA | API | 🔲 |
| M297 | Feature-importance monitor | Track SHAP drift | SHAP | API | 🔲 |
| M298 | Backtester engine | Historical CLV/ROI replay | Simulation | API+Mkt | ✅ |
| M299 | Prediction tracker | Log + score every prediction | Tracking | API | ✅ |
| M300 | Out-of-sample validator | Walk-forward CV harness | CV harness | API | ✅ |
| M301 | Anomaly/outlier filter | Reject bad input rows | Isolation forest | API | 🔲 |
| M302 | Prior-blending model | Blend season vs recent priors | Bayesian | API | ✅ |
| M303 | Cold-start model | New-player projection | Comp-based | BBRef | 🔲 |
| M304 | Meta-label model | P(this signal is profitable) | Meta-labeling | API+Mkt | 🔲 |

---

## Domain O — Simulation / Ratings (17 models) · Layer L3 wrap

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M305 | Full possession simulator | Per-player stat PMFs | 7-model MC chain | All | ⚙️ |
| M306 | Prop pricing engine | P(over/under) vs book | Monte Carlo | L3 | ✅ |
| M307 | Game pricing engine | Win/spread/total fair value | Monte Carlo | L3 | ⚙️ |
| M308 | Joint correlated simulator | Correlation-aware joint sim | Copula MC | L3 | 🔲 |
| M309 | Scenario simulator | What-if game scenarios | MC | L3 | 🔲 |
| M310 | What-if injury simulator | Re-sim with player out | MC | L3 | 🔲 |
| M311 | True player impact | Spatial on/off adjusted value | Regression | CV100 | 🔲 |
| M312 | Regression-to-mean detector | P(luck normalizes) | Rolling z-score | API | ✅ |
| M313 | Injury-impact model | Value lost when X out | Chemistry subtraction | CV100 | ⚙️ |
| M314 | Strength-of-schedule adjuster | SOS-adjusted ratings | Iterative | API | 🔲 |
| M315 | Opponent-adjusted RAPM | Regularized adjusted +/- | Ridge RAPM | API | 🔲 |
| M316 | Bayesian player rating | Latent skill posterior | Bayesian | API | 🔲 |
| M317 | Elo team rating | Dynamic team Elo | Elo | API | 🔲 |
| M318 | Plus-minus predictor | Player +/- forecast | Regression | API | ✅ |
| M319 | Beneficiary cascade | Who benefits from injury | Classifier | API | ✅ |
| M320 | Usage-redistribution model | Usage reallocation when X out | Constraint solver | API | ⚙️ |
| M321 | Player style embedding | Latent style vector | Autoencoder | API | 🔲 |

---

## Domain P — Advanced / Research / Edge (29 models) · mixed layers

| ID | Model | Predicts | Algorithm | Data | Status |
|----|-------|----------|-----------|------|--------|
| M322 | Expected assist (xAST) | P(pass→made FG) | XGBoost | CV50 | 🔲 |
| M323 | Passing-network centrality | Player network importance | Graph | CV50 | 🔲 |
| M324 | Rim-protection model | Rim DFG% allowed | Regression | CV50 | 🔲 |
| M325 | Perimeter-defense model | 3pt DFG% allowed | Regression | CV50 | 🔲 |
| M326 | Switchability score | Defender position versatility | Regression | CV100 | 🔲 |
| M327 | Foul-out cascade | Chain effects of foul-outs | Simulation | Live | 🔲 |
| M328 | FT streak/variance model | FT% hot/cold variance | Beta-binomial | API | 🔲 |
| M329 | Clutch-gene quantifier | Clutch over/under-performance | Regression | API | ✅ |
| M330 | Fatigue-adjusted projection | Stats adjusted for fatigue | Chain | CV20 | ⚙️ |
| M331 | 2nd-night-of-B2B model | B2B-2 specific decay | Regression | Sched | 🔲 |
| M332 | Garbage-time stat inflation | Discount garbage-time stats | Regression | PBP | 🔲 |
| M333 | Blowout minutes redistribution | Minutes shift in blowouts | Regression | PBP | 🔲 |
| M334 | Opponent game-plan predictor | Likely defensive game-plan | Multiclass | CV100 | 🔲 |
| M335 | Defensive-coverage classifier | Coverage type per possession | Multiclass | CV50 | 🔲 |
| M336 | Shot heat-map generator | Per-player xFG heat surface | KDE/CNN | Shots | 🔲 |
| M337 | Team style embedding | Latent team-style vector | Autoencoder | API | 🔲 |
| M338 | Pace-control model | Who dictates game pace | Regression | PBP | 🔲 |
| M339 | Hot-hand model | True hot-hand effect size | Bayesian | PBP | ⚙️ |
| M340 | Shooting-luck separator | Skill vs variance in FG% | Mixed model | Shots | ✅ |
| M341 | Free-throw-rate model | FTr per player | Regression | API | 🔲 |
| M342 | Foul-drawing-rate model | Fouls drawn per drive | Regression | PBP | ✅ |
| M343 | Second-chance model | xPTS from OREB | Regression | CV100 | ⚙️ |
| M344 | Pace-per-lineup model | Possessions/48 per unit | Regression | CV100 | 🔲 |
| M345 | Coaching-matchup model | Coach A vs Coach B history | Profile | BBRef | 🔲 |
| M346 | Possession-momentum carry | Does momentum persist? | HMM | PBP | ⚙️ |
| M347 | Late-game-execution model | Clutch-possession quality | Regression | PBP | 🔲 |
| M348 | Travel-recovery model | Recovery rate post-travel | Regression | Sched | 🔲 |
| M349 | Schedule-spot edge model | Composite situational edge | Ensemble | Sched | 🔲 |
| M350 | Counterfactual replay model | Re-grade decisions vs optimal | Simulation | PBP+L2 | 🔲 |

---

## Build Phasing — Priority Order

Build bottom-up. Each phase unlocks the next. **Do not skip data tiers.**

| Phase | Focus | Models | Gate |
|-------|-------|--------|------|
| **P1** | Finish API-only props & game models | M006-M013, M035-M075 (quarter/derivative/combo props) | nba_api only — buildable NOW |
| **P2** | Officiating + context multipliers | M166-M182, M202-M210 | BBRef scraper |
| **P3** | Betting market layer | M224-M248 | Market feed (Action/Pinnacle/DK) |
| **P4** | NLP / news layer | M249-M263 | News scrapers (Reddit/X/RotoWire) |
| **P5** | 20 CV games — spatial L1 | M077, M099, M115-M141 | 20 tracked games |
| **P6** | 50 CV games — volume L1 | M078, M118-M137, M322-M335 | 50 tracked games |
| **P7** | 100 CV games — interaction | M183-M196, M311-M313, M343-M344 | 100 tracked games |
| **P8** | Coaching models | M211-M222 | PBP + CV50 |
| **P9** | Live / in-game (L6) | M264-M281 | Real-time feed |
| **P10** | Meta / ensemble hardening | M285-M304 | All L1-L3 stable |
| **P11** | Simulation & ratings | M305-M321 | 200+ games + all tiers |
| **P12** | Research / edge models | M322-M350 remainder | Everything above |

**Buildable today (no new data):** ~70 models in P1 + the planned-status API/Shots/PBP rows scattered across domains.

---

## Count Summary

| Domain | Models | Built ✅ | Partial ⚙️ | Planned 🔲 |
|--------|--------|---------|-----------|------------|
| A — Game Outcome | 27 | 7 | 3 | 17 |
| B — Player Props | 48 | 7 | 5 | 36 |
| C — Shot-Level | 22 | 7 | 2 | 13 |
| D — Possession/Play-Type | 17 | 1 | 5 | 11 |
| E — Spatial/CV | 27 | 3 | 9 | 15 |
| F — Player Lifecycle | 22 | 9 | 3 | 10 |
| G — Context | 19 | 6 | 0 | 13 |
| H — Team/Lineup | 17 | 3 | 5 | 9 |
| I — Officiating | 11 | 3 | 0 | 8 |
| J — Coaching | 13 | 1 | 1 | 11 |
| K — Betting Market | 25 | 6 | 3 | 16 |
| L — NLP/Sentiment | 15 | 0 | 2 | 13 |
| M — Live/In-Game | 18 | 4 | 2 | 12 |
| N — Meta/Ensemble | 23 | 7 | 9 | 7 |
| O — Simulation/Ratings | 17 | 4 | 4 | 9 |
| P — Advanced/Research | 29 | 3 | 5 | 21 |
| **TOTAL** | **350** | **~81** | **~58** | **~211** |

~81 built (matches the ~96 artifacts incl. v1/v2 + calibration files). ~269 models still to build.

---

## Related
- `docs/ML_MODELS.md` — current trained-artifact reference
- `docs/models/model-registry.md` — artifact manifest
- `docs/models/feature-inventory.md` — the 65+ L0 features feeding every model
- `docs/models/BUILD_PROMPT.md` — the executable build loop
