# Edge Taxonomy — 164 Enumerated Edges

*Every identified source of systematic edge in NBA prop and game-line markets, grouped by origin: information (data collection), model (how you think), execution (how you act), and structural (the market itself).*

---

## Overview

The 164 edges are organized into four categories. Within each, three waves: foundation edges, second-wave extensions, and third-wave deep/long-tail signals.

Counts by category:
- **I. Information** — 87 edges (1–18, 38–62, 91–129)
- **II. Model** — 27 edges (19–25, 63–72, 130–139)
- **III. Execution** — 32 edges (26–32, 73–82, 140–154)
- **IV. Structural** — 23 edges (33–37, 83–90, 155–164)

Edges compound. CV pipeline (1–9, 38–49, 91–114) feeds simulator (19), which enables SGP/joint pricing (20, 34, 84). News-ingestion infrastructure (28, 58, 59, 72, 128, 141) powers every news-window execution edge. Multi-book API (26) powers all routing edges. Build foundations once; harvest dozens of dependents.

---

## Category I: Information Edges — You See What Others Can't

### CV-Derived Spatial Features (Edges 1–9)

The primary moat. Sportsbooks price player props using box-score models. The gap between spatial reality and box-score summary is the exploitable inefficiency.

| # | Name |
|---|------|
| 1 | Defender distance distributions |
| 2 | Court spacing — convex hull |
| 3 | Closeout speed on shooters |
| 4 | Paint density per possession |
| 5 | Transition vs half-court classification |
| 6 | Catch-and-shoot vs off-dribble detection |
| 7 | Off-ball movement quality |
| 8 | Shot trajectory / release angle |
| 9 | Pick-and-roll detection |

---

**Edge 1 — Defender Distance Distributions**

Not "open vs contested" — the full continuous distribution of defender distance at shot release, per player, per matchup. FG% varies dramatically by closest-defender distance; Blackport's research identifies this as the most influential variable in shot outcome prediction beyond shot distance alone. The CV pipeline extracts this post-homography in court coordinates. No retail data source ships it.

- **Academic backing:** Blackport et al. (SportVU-era), reproduced in NBA.com Closest Defender dataset (aggregated only)
- **What it predicts:** FG% above/below expected given volume; conditional over/under probability on points
- **SHAP contribution:** Combined CV spatial features = 31% of mass on pts model; Δ R² = +0.08 over API-only baseline

---

**Edge 2 — Court Spacing: Convex Hull of Offensive Players**

Convex hull area of 4 off-ball offensive players per possession, normalized to half-court dimensions. 5-out spacing vs traditional 4-out-1-in has measurable impact on drive efficiency and kick-out 3P opportunities. Derived trivially from existing tracking homography.

- **What it predicts:** 3PM opportunities, paint touches, assist likelihood, defender compression
- **Build path:** Already wired; quality improves with N=80 games

---

**Edge 3 — Closeout Speed on Shooters**

Defender velocity vector toward ball-handler after kick-out pass, in km/h. Slow closeout → open 3P. Fast closeout → contested pull-up or reversal. Second Spectrum's "contest quality" metric reproduced from broadcast.

- **What it predicts:** Per-player 3P% above/below expectation given shot volume; 3PM prop edge
- **Implementation:** Velocity from consecutive frame positions of closest defender at catch point

---

**Edge 4 — Paint Density Per Possession**

Count of players within paint polygon per frame, averaged over possession. High paint density suppresses drives, reduces FTAs, shifts shots to perimeter.

- **What it predicts:** FTA rate, points-in-paint vs perimeter split, drive efficiency
- **Implementation:** Paint polygon constant in court coordinates post-homography; trivial count

---

**Edge 5 — Transition vs Half-Court Classification**

Binary: if all 5 offensive players cross half-court within N seconds of possession start, transition. Transition possessions have higher pace, higher scoring efficiency, different shot-type distributions.

- **What it predicts:** Pace; PPP projection; all counting stats in fast-break matchups
- **Implementation:** Rule-based on player positions at frame T and frame T+N

---

**Edge 6 — Catch-and-Shoot vs Off-Dribble Detection**

Ball-handler stationary (velocity < threshold) for N frames before release? C&S carry significantly higher FG% than off-dribble; effect varies by player.

- **What it predicts:** Per-player FG% by shot type; points model calibration
- **Implementation:** Velocity thresholding over 5-10 frames pre-release

---

**Edge 7 — Off-Ball Movement Quality**

Total distance traveled by non-ball-handlers per possession. High movement correlates with active schemes that create open looks.

- **What it predicts:** Scheme quality; open-shot generation rate; C&S points opportunities
- **Implementation:** Sum of Euclidean distances per player per possession for all non-handler tracks

---

**Edge 8 — Shot Trajectory / Release Angle**

Parabolic curve fit to ball trajectory on shot attempts. Release angle 45–55° optimal; entry angle <32° is flat with lower rim tolerance.

- **What it predicts:** FG% independent of defender distance; complements edge 1
- **Academic backing:** Haralick et al. on trajectory reconstruction; 2024 arxiv on shot arc from broadcast
- **Implementation:** Faster R-CNN ball segmentation + Kalman smoother + parabola fit in court coordinates

---

**Edge 9 — Pick-and-Roll Detection**

Spatial-temporal detection of screen-setting. PnR is the most common NBA play type; scheme classification enables PnR-specific outcome models.

- **What it predicts:** Ball-handler vs roller scoring opportunity split
- **Academic backing:** TacticExpert (arXiv:2503.10722, 2025)
- **Implementation:** v1 rule-based convergence; v2 STGNN on labeled sequences

---

### CV-Derived Spatial Features — Second Wave (Edges 38–49)

Second-wave signals from the same pipeline via derived geometry, sequence analysis, and event detection.

| # | Name |
|---|------|
| 38 | Defender matchup mismatch (height/wingspan) |
| 39 | Screen quality classification |
| 40 | Help-defense rotation speed |
| 41 | Offensive rebound positioning at shot release |
| 42 | Pass network topology |
| 43 | Touches and time-of-possession per player |
| 44 | Pick-and-roll coverage classification |
| 45 | Shot clock state at attempt |
| 46 | Driving hand and direction tendencies |
| 47 | Off-ball cut detection (backdoor, flare, flex) |
| 48 | Foul-drawing technique markers |
| 49 | Free-throw routine consistency |

---

**Edge 38 — Defender Matchup Mismatch.** Closest defender per possession × roster height/wingspan delta. Switch-induced mismatches are highest-EV scoring opportunities in modern NBA offenses. *Predicts:* player FG% lift on weak matchups. *Implementation:* roster table + nearest-defender assignment + delta features.

**Edge 39 — Screen Quality.** Velocity and contact angle of screen-setter relative to defender path. Hard legal screens free ball-handler significantly more than soft/moving screens. *Predicts:* PnR ball-handler scoring; roller assist credit; FTA from drives. *Implementation:* convergence detection + setter velocity at contact + defender displacement.

**Edge 40 — Help-Defense Rotation Speed.** Speed at which help defender rotates after gap collapse determines whether drive ends in layup, FTA, kick-out 3, or turnover. *Predicts:* drive efficiency; kick-out 3PA; defensive FT rate. *Implementation:* detect drive event + identify nearest help + measure velocity vector.

**Edge 41 — Offensive Rebound Positioning.** Position of each offensive player vs rim at moment of release. Pre-release inside-paint position predicts OREB. *Predicts:* per-player OREB props; second-chance points. *Implementation:* snapshot positions at detected release; distance-to-rim per player.

**Edge 42 — Pass Network Topology.** Per-possession directed graph of passes. Network metrics (betweenness, edge density) predict assist distribution and scheme. *Predicts:* per-player assist props; ball-handler usage. *Implementation:* detect pass events from ball trajectory; aggregate per game.

**Edge 43 — Touches & Time-of-Possession.** Per-player ball-holding frames, dribbles, possession durations. CV-derived version of NBA.com tracking stats. *Predicts:* usage rate (direct); assist opportunity; TOV risk. *Implementation:* ball-tracker proximity assignment per frame.

**Edge 44 — PnR Coverage Classification.** Classify PnR defensive coverage: drop, hedge, switch, blitz, ICE. *Predicts:* ball-handler vs roller scoring split; corner-3 generation. *Implementation:* rule-based classifier on defender positions at contact.

**Edge 45 — Shot Clock State at Attempt.** OCR broadcast shot clock; tag every shot. Late-clock shots (<7s) harder; early-clock (>18s) easier. *Predicts:* FG% conditional on possession length. *Implementation:* extend EasyOCR to shot clock region.

**Edge 46 — Drive Hand & Direction.** Direction of each drive (left/right/middle) and finishing hand. Defenses force weak-hand finishes. *Predicts:* drive FG% conditional on matchup; FTA from forcing. *Implementation:* horizontal velocity sign + pose for hand (v2).

**Edge 47 — Off-Ball Cut Detection.** Sudden acceleration of off-ball player toward basket while handler is engaged elsewhere. *Predicts:* catch-and-finish opportunities; assists for the passer. *Implementation:* velocity spikes in off-ball tracks correlated with handler engagement.

**Edge 48 — Foul-Drawing Technique Markers.** Rip-throughs, pump-fakes, post engagement that draws contact. Trae Young / Harden historical foul-draws. *Predicts:* FTA rate; points via FTM; foul trouble on defenders. *Implementation:* pose/action classification on shooting sequences.

**Edge 49 — FT Routine Consistency.** Pre-shot routine duration and stance variance. Consistent routines hit higher long-run; disrupted routines (post-timeout, late game) miss more. *Predicts:* FT% in specific situations; clutch FT props. *Implementation:* segment pre-shot routine; measure duration and pose variance.

---

### CV-Derived — Third Wave: Action Sets, Player State, Broadcast Signals (91–114)

Beyond geometry: scheme/set classification, player physical state, audio extraction, bench/coach cameras. Books cannot easily replicate these from data feeds.

| # | Name |
|---|------|
| 91 | DHO (dribble handoff) detection |
| 92 | Set recognition: Horns, Spain, stagger, floppy, zoom |
| 93 | Inbound play recognition (BLOB / SLOB) |
| 94 | End-of-quarter heave detection |
| 95 | ATO (after-timeout) play classification |
| 96 | Player fatigue from movement entropy |
| 97 | Gait abnormality / limp detection |
| 98 | Mid-game tape / brace / sleeve addition |
| 99 | Pre-game shootaround shot-making rate |
| 100 | Zone vs man defense identification |
| 101 | Defensive stance quality |
| 102 | Help-side rotation pattern |
| 103 | Switch vs stick choice on screens |
| 104 | Hedge / drop / blitz coverage parameters |
| 105 | Bonus state tracking per quarter |
| 106 | Hack-a-shooter strategic fouling detection |
| 107 | Coach's challenge usage signal |
| 108 | Take-foul / clear-path rate late game |
| 109 | And-1 / continuation probability per drive |
| 110 | Buzzer-beater attempt detection |
| 111 | Crowd noise audio extraction |
| 112 | Announcer urgency / hype score |
| 113 | Bench engagement / morale proxy |
| 114 | Coach demeanor signals |

**Edge 91 — DHO Detection.** Ball-handler reverse-pivot into screener-receiver with ball exchange. DHO efficiency varies by pair. *Predicts:* receiver scoring upside. *Implementation:* ball-tracker proximity + reverse-pivot pose detection.

**Edge 92 — Set Recognition.** Classify recognizable sets — Horns (two screens at top), Spain (back-screen on roller's defender), stagger, floppy, zoom (DHO + screen). *Predicts:* which player benefits; matchup-specific +EV. *Implementation:* STGNN on labeled set sequences.

**Edge 93 — Inbound Play Recognition.** BLOB and SLOB plays are heavily scripted; ATO scoring well above league average. *Predicts:* inbound-play points; specific player spikes. *Implementation:* detect dead-ball state + inbounder position; classify action.

**Edge 94 — End-of-Quarter Heaves.** Last-second 3PA from 30+ feet have near-zero make rate but inflate 3PA. *Predicts:* 3PM under (heaver still misses), 3PA over. *Implementation:* shot/game clock OCR; flag attempts in final 3s from beyond mid-court.

**Edge 95 — ATO Play Classification.** After-timeout plays are coached calls with elevated scoring expectation. *Predicts:* immediate post-TO possession; coaching quality. *Implementation:* detect TO state from graphic; track next possession.

**Edge 96 — Movement-Entropy Fatigue.** Lateral velocity, jump height, movement smoothness decline with fatigue. *Predicts:* Q4 FG% decline; defensive lapses. *Implementation:* kinematic stats per minutes-played bucket.

**Edge 97 — Gait Abnormality / Limp.** Pose-estimation leg-angle asymmetry. Players returning from leg injury show subtle asymmetry box scores miss. *Predicts:* upcoming DNP / performance decline. *Implementation:* RTMPose or OpenPose on player crops; asymmetry metric.

**Edge 98 — Mid-Game Tape Addition.** Broadcast shows trainer attending to player at bench. Adding tape/brace mid-game indicates discomfort. *Predicts:* second-half decline; potential exit. *Implementation:* visual diff of player appearance between quarters.

**Edge 99 — Shootaround Shot-Making Rate.** Pre-game warmup broadcast 30+ minutes before tip. Make rate correlates weakly but consistently with game shooting. *Predicts:* FG% deviation from baseline. *Implementation:* track makes/attempts in pregame footage.

**Edge 100 — Zone vs Man Defense.** Defender position clustering distinguishes zone (fixed-area) from man (player-tracking). Zone compresses paint, opens 3PA. *Predicts:* shot type distribution; 3PM rate. *Implementation:* position clustering per defensive possession.

**Edge 101 — Defensive Stance Quality.** Active stance (bent knees, hands up) vs passive (upright). Active defenders contest more, generate steals. *Predicts:* defensive stat output; matchup difficulty. *Implementation:* pose classification per player per possession.

**Edge 102 — Help-Side Rotation Pattern.** Aggressive help rotates early (opens 3s); conservative stays home (allows drives). *Predicts:* 3PA generation against aggressive-help teams. *Implementation:* off-ball defender position vs weak-side offensive players.

**Edge 103 — Switch vs Stick on Screens.** Defending pair chooses switch or stick. Switch creates mismatches (edge 38); stick creates rotation needs. *Predicts:* downstream matchup distribution. *Implementation:* detect defender-target reassignment after screen contact.

**Edge 104 — PnR Coverage Parameters.** Beyond edge 44's classification, measure drop depth, hedge angle, blitz timing. *Predicts:* ball-handler vs roller scoring split. *Implementation:* extend edge 44 with continuous parameter extraction.

**Edge 105 — Bonus State Tracking.** Team foul count per quarter from broadcast graphic. Once in bonus (4+), every shooting foul = 2 FTAs. *Predicts:* FTA spike; strategy shift to drives. *Implementation:* count fouls per team per quarter.

**Edge 106 — Hack-a-Shooter Detection.** Strategic intentional fouling on poor FT shooters (Shaq, Drummond, Simmons era). *Predicts:* FTA spike for targeted player; deflated team total. *Implementation:* detect off-ball intentional fouls on specific players.

**Edge 107 — Coach's Challenge Usage.** One challenge per game. Early use = panic / matchup-dependent. *Predicts:* momentum shift; FT differential. *Implementation:* detect challenge from broadcast graphic.

**Edge 108 — Take-Foul / Clear-Path Rate.** End-game intentional fouls to stop clock. Some teams foul earlier, some delay. *Predicts:* end-of-game pace; FTA distribution. *Implementation:* identify intentional fouls + game state.

**Edge 109 — And-1 / Continuation Probability.** Per-player foul-while-finishing rate. Some players are systematic and-1 generators. *Predicts:* points-per-attempt above expected; FTA + FGM combos. *Implementation:* aggregate and-1s per player by drive type.

**Edge 110 — Buzzer-Beater Detection.** Last 1–2s of quarter — attempts from anywhere. Volume spike not always priced into 3PA. *Predicts:* 3PA inflation at quarter ends for ball-handlers. *Implementation:* shot + game clock OCR.

**Edge 111 — Crowd Noise Audio.** Broadcast crowd noise (dB) is continuous home-advantage signal. *Predicts:* in-game momentum; home Q4 FG%. *Implementation:* audio extraction from broadcast; rolling dB level.

**Edge 112 — Announcer Urgency.** Voice pitch and rate spike on critical moments. Informal hype score. *Predicts:* clutch-moment density; closeness correlation. *Implementation:* prosody features; pitch tracking.

**Edge 113 — Bench Engagement.** Standing, towel-waving, animated reactions = engaged team. *Predicts:* second-half effort and counting stats. *Implementation:* bench-camera detection + pose classification.

**Edge 114 — Coach Demeanor.** Timeout frequency, sideline pacing, body posture. Early timeouts = panic. *Predicts:* in-game strategy adjustments. *Implementation:* coach-camera detection + posture/timeout tracking.

---

### Context Features (Edges 10–18)

Free, underused, high signal. Data ingestion, no CV required.

| # | Name |
|---|------|
| 10 | Referee foul rates and pace impact |
| 11 | Travel fatigue index |
| 12 | Denver altitude adjustment |
| 13 | Lineup-dependent usage redistribution |
| 14 | Load management / rest prediction |
| 15 | Contract year effect |
| 16 | NBA2Vec player embeddings |
| 17 | SportVU 2015-16 calibration dataset |
| 18 | Venue-specific and situational effects |

---

**Edge 10 — Referee Foul Rates and Pace Impact**

NBA posts daily ref crew assignments at official.nba.com/referee-assignments ~9am ET. NBAstuffer and Basketball-Reference carry multi-season ref stats: PF rate, FTA rate, pace impact, home/away tendency. Oregon State study found significant foul-calling biases; 2025 J. Sports Econ paper analyzed L2M data near spread.

**Timing edge:** Props posted before ref assignments. At 9am announcement, lines have not fully adjusted. Window: 10–20 minutes.

- **What it predicts:** FTA rate, pace, total points
- **Data sources:** `official.nba.com/referee-assignments`, `nbastuffer.com/nba-stats/referee`
- **Implementation:** Morning scrape; ref ID → historical foul/pace stats → model features

---

**Edge 11 — Travel Fatigue Index**

Beyond binary B2B flag. Continuous index: great-circle flight distance, timezone crossing magnitude/direction (westward harder), arrival time vs game time, days since last rest day, 7-day cumulative density. West Coast teams playing early-window East games consistently underperform.

- **What it predicts:** All counting stats; guard scoring/assists most sensitive
- **Implementation:** `geopy.distance.great_circle` + timezone offsets + density rolling sum

---

**Edge 12 — Denver Altitude Adjustment**

Denver: .652 all-time home win%, .350 away (.302 delta) — largest in NBA history. Altitude reduces oxygen density; effect peaks in Q3–Q4. Sportico confirmed after controlling for quality; ESPN documented during 2023 Finals.

- **What it predicts:** Visiting decay in second half; Nuggets home overs
- **Implementation:** Binary visit-Denver flag; optional continuous altitude weight (SLC also elevated)

---

**Edge 13 — Lineup-Dependent Usage Redistribution**

When key player ruled out, usage redistributes per teammates' on/off data. PBPStats API provides splits. Usage redistribution model computes new shares for any subset of absences.

**Timing edge:** Late scratches 30–60min pre-game. Books adjust over 5–15 min. Your model recomputes in seconds.

- **Data sources:** PBPStats API, NBA injury reports
- **Implementation:** Offline lookup table per player-pair-team; online recompute on scratch

---

**Edge 14 — Load Management / Rest Prediction**

Predictive signals for unannounced rest: minutes trend last 7 games, schedule density (3-in-4, 4-in-6), player age, injury history, Player Participation Policy constraints, playoff seeding position.

Predict rest day 6–12 hours pre-announcement → every player line stale, every teammate's prop reprices upward.

- **Academic backing:** arXiv:2603.26935 (2026) on healthy-worker survivor effect in NBA rest modeling
- **Implementation:** Binary classifier on historical rest decisions

---

**Edge 15 — Contract Year Effect**

Players in final contract year statistically perform differently. Salary data public (spotrac, bball-reference). Boolean "contract year" flag. Effect sign varies by player type.

- **Implementation:** Annual lookup; flag last-year-of-deal players

---

**Edge 16 — NBA2Vec Player Embeddings**

Word2Vec-style embeddings trained on 3.5M+ PBP sequences. 8-dim vectors with emergent positional roles. Similar embeddings → similar play.

- **Academic backing:** arXiv:2302.13386
- **Uses:** Lineup quality scoring; counterfactual simulation; rookie cold-start; trade impact prior

---

**Edge 17 — SportVU 2015-16 Calibration Dataset**

Only public NBA tracking release: 631 games at 25fps. github.com/sealneaward/nba-movement-data. Validate broadcast CV against ground truth.

- **Method:** For any 2015-16 game runnable through CV, compare defender distance, spacing vs SportVU; quantify error → calibrate
- **Why it matters:** Determines whether CV features are signal or noise at the precision computed

---

**Edge 18 — Venue-Specific and Situational Effects** `PARTIAL`

Already partially wired: home court (residual from neutral-site expected), road B2B vs home B2B asymmetry, 3+ days rest delta, playoff vs regular season, early vs late season.

---

### Context Features — Second Wave (Edges 50–62)

| # | Name |
|---|------|
| 50 | NBA matchup data — who guards whom |
| 51 | Foul-trouble probability modeling |
| 52 | Garbage-time / blowout probability |
| 53 | Lineup overlap minutes |
| 54 | Coach rotation patterns |
| 55 | Days-since-trade / integration period |
| 56 | Coaching matchup history |
| 57 | New-coach in-season transition |
| 58 | Injury report word parsing |
| 59 | Beat reporter latency monitor |
| 60 | Crew chief experience tier |
| 61 | L2M (Last Two Minute) report mining |
| 62 | Venue-specific foul bias |

**Edge 50 — NBA Matchup Data.** NBA.com publishes player-vs-player matchups: defensive possessions, partial possessions, points allowed. Books underweight defender-specific quality. *Predicts:* FG% conditional on likely defender. *Implementation:* `stats.nba.com/stats/leagueseasonmatchups`; predict primary defender from lineups.

**Edge 51 — Foul-Trouble Probability.** Early fouls → fewer minutes → fewer stats. Inputs: PF/36 history, opponent style (drive-heavy attracts fouls), ref crew (edge 10). *Predicts:* minutes → counting stats. *Implementation:* Poisson process with context-conditional rate.

**Edge 52 — Garbage-Time / Blowout Probability.** Blowouts sit starters in Q4; bench plays. *Predicts:* starter unders in Q4-heavy props; bench overs. *Implementation:* blowout probability from simulator into minutes redistribution.

**Edge 53 — Lineup Overlap Minutes.** 5-man unit minutes from PBPStats. High-overlap units have chemistry; new units regress toward team mean. *Predicts:* net rating → pace → counting stats. *Implementation:* per-lineup minutes aggregation from PBPStats.

**Edge 54 — Coach Rotation Patterns.** Each coach has substitution signature: when starters sit, bench-unit length, garbage-time discipline. *Predicts:* per-player minutes; bench usage. *Implementation:* aggregate sub timestamps per coach per season.

**Edge 55 — Days-Since-Trade.** Traded players underperform first ~10 games while integrating. Books partially price but discount too small. *Predicts:* counting-stat regression first 10 games. *Implementation:* flag in transactions feed; decay multiplier.

**Edge 56 — Coaching Matchup History.** H2H coach records; scheme matchups (drop coverage vs heavy PnR offense). *Predicts:* pace; total points; PnR scoring. *Implementation:* H2H coach-pair outcomes; scheme tags per coach.

**Edge 57 — New-Coach In-Season Transition.** Mid-season fires + interims produce scheme volatility. Historical team data no longer reflects identity. *Predicts:* increased prediction error first ~10 games. *Implementation:* trigger on transactions; reweight recent + widen intervals.

**Edge 58 — Injury Report Word Parsing.** "Questionable" plays at different rates per team. *Predicts:* P(plays | status word). *Implementation:* scrape NBA report daily; empirical probability table per team-status-player.

**Edge 59 — Beat Reporter Latency Monitor.** Beat reporters break news minutes before official. Curated list per team on X. *Predicts:* direction of lineup-induced moves before they happen. *Implementation:* Twitter API + per-reporter latency stats.

**Edge 60 — Crew Chief Experience Tier.** Crew chief specifically anchors call patterns. Rookie chiefs (1–3 yrs) have higher variance and home-bias. *Predicts:* FT discrepancy; home scoring lift; T-foul rate. *Implementation:* tag crew chief from assignments.

**Edge 61 — L2M Report Mining.** NBA publishes Last Two Minute reports detailing every call/no-call in close games. Per-ref accuracy and bias far more granular than season stats. *Predicts:* end-game FT discrepancy; clutch foul patterns. *Implementation:* scrape L2M PDFs; aggregate per-ref.

**Edge 62 — Venue-Specific Foul Bias.** Per-venue FT discrepancy (home FTA − away FTA) over many seasons. SLC and CLE historically lead. *Predicts:* home FTA and points; ref-conditional adjustment. *Implementation:* aggregate FT differential per venue.

---

### Context — Third Wave: Motivation, Distraction, Reporting Sources (115–129)

Player-state and information-network signals not visible in box scores. Most are scrape-and-flag features.

| # | Name |
|---|------|
| 115 | Revenge game vs former team |
| 116 | Hometown / birth-city game |
| 117 | National TV effort spike |
| 118 | Trade rumor distraction period |
| 119 | Coach on hot seat instability |
| 120 | Late-season tanking signals |
| 121 | Playoff seeding motivation |
| 122 | Pre-trade-deadline showcasing |
| 123 | Post-trade gel period |
| 124 | Personal life events |
| 125 | Practice attendance reports |
| 126 | Player social media sentiment |
| 127 | Podcast appearance scheme leaks |
| 128 | Insider reporter latency (Woj / Shams) |
| 129 | Local vs national market scrutiny |

**Edge 115 — Revenge Games.** Player vs former team within 2 seasons of trade — historical lift in usage and scoring. *Implementation:* transactions feed + opponent matchup; 2-season flag.

**Edge 116 — Hometown Games.** Player playing in birth city. Family-in-attendance effort lift. *Implementation:* birthplace lookup + venue.

**Edge 117 — National TV Effort.** ESPN / TNT / ABC games show small but consistent star counting-stat lift. *Implementation:* broadcast schedule + star flag.

**Edge 118 — Trade Rumor Distraction.** Player named in active rumors within 7 days. Slight decline. *Implementation:* news feed for player + "trade"; decay function.

**Edge 119 — Coach Hot Seat.** Public job pressure → tighter or more desperate schemes; volatile rotations. *Implementation:* monitor hot-seat reporting; reduce rotation-pattern confidence.

**Edge 120 — Tanking Signals.** Last 15 games for non-playoff teams. Young players extended; vets sit. *Implementation:* date + standings flag.

**Edge 121 — Playoff Seeding Fights.** Last 10 games with seed implications. High motivation for chasers; opposite for locked-in. *Implementation:* magic-number flag.

**Edge 122 — Pre-Deadline Showcasing.** Trade-block players in 30 days pre-deadline get showcase usage. *Implementation:* trade rumor + deadline proximity.

**Edge 123 — Post-Trade Gel Period.** First 10 games on new team — reinforces edge 55. *Implementation:* cross-reference edge 55.

**Edge 124 — Personal Life Events.** Births, bereavement, marriage announcements via social media. Performance variance increases. *Implementation:* social media monitor for life events.

**Edge 125 — Practice Attendance.** Beat reporters publish (limited rotation, full practice, missed). Missed = increased questionable-tag probability. *Implementation:* practice report scraping.

**Edge 126 — Player Social Media Sentiment.** Frustrated quotes, motivational posts. *Implementation:* sentiment on player accounts; spike detection.

**Edge 127 — Podcast Scheme Leaks.** Players discuss specific actions/matchups on podcasts; coaching staff scouts. *Implementation:* podcast transcription + entity extraction (rare but high-signal).

**Edge 128 — Insider Reporter Latency.** Woj and Shams break news 3–10 min before official. Standard sharp baseline. *Implementation:* X API streaming on @wojespn, @ShamsCharania.

**Edge 129 — Market Scrutiny Gap.** Big-market teams (LAL, NYK, BOS) get disproportionate book attention; small-market teams (MEM, OKC, UTA, IND, MIN) have softer prop pricing. *Implementation:* market-size flag per team-game.

---

## Category II: Model Edges — You Think About the Problem Differently

### Distribution Pricing and Adaptive Models (Edges 19–25)

| # | Name |
|---|------|
| 19 | Full probability distributions |
| 20 | Joint stat distributions for SGP pricing |
| 21 | Regime detection |
| 22 | Bayesian in-season updating |
| 23 | Adversarial book model |
| 24 | Counterfactual simulation |
| 25 | RL-optimized bet timing |

---

**Edge 19 — Full Probability Distributions, Not Point Estimates**

Every retail tool predicts a number. The possession simulator generates a distribution. `P(pts > 27.5) = 52%` is weak; `P = 62%` with tight CI is strong. Distributions price any threshold — mainline, alternates, SGP legs.

- **Required calibration:** Platt scaling or isotonic regression on 152K prop residuals. See [calibration.md](../models/calibration.md).

---

**Edge 20 — Joint Stat Distributions for SGP Pricing**

For multi-leg SGP: run simulator for ALL legs simultaneously; extract joint probability. Compare to book's formulaic correlation discount. `P(all legs | sim)` > `P(all legs | book SGP price)` = +EV.

- **Implementation:** Pass multi-leg spec to simulator; record fraction of 10K paths hitting all legs; compare to no-vig book SGP price

---

**Edge 21 — Regime Detection**

Players' roles change mid-season. Season-trained models don't reflect current reality. Triggers: trade, teammate injury, coaching change, lineup shift, return from injury.

- **Implementation:** Monitor transactions + lineups for triggers; exponential decay on historical weight post-trigger; widen intervals until N=threshold

---

**Edge 22 — Bayesian In-Season Updating**

Prior: pre-season model. Posterior: Bayesian update each game. Posterior improves faster than book recalibration (books manage too many markets).

- **Approach:** Conjugate Normal-Normal priors on player skill; update mean and variance each game; shrink toward prior early, release after ~15 games

---

**Edge 23 — Adversarial Book Model**

Model how each book sets and adjusts. Poll every 5–10 min open-to-tip. Features: which books lead price discovery (Circa, BetCRIS in US), lag times, movement speed per book. Predict line direction before it happens; bet pre-adjustment.

Also: steam moves — see edge 29.

---

**Edge 24 — Counterfactual Simulation**

NBA2Vec embeddings + simulator: "what would Player X's stats look like if Y was on the floor instead of Z?" Trade-deadline application: find historical players with similar embeddings who made same transition; use their delta as prior.

Books reprice slowly after trades. Counterfactual gives early estimate better than mean-reversion.

---

**Edge 25 — RL-Optimized Bet Timing**

Heuristic: bet at open (best CLV) and lineup confirmation. RL: agent decides timing given current line, model confidence, time to tip, expected movement.

- **Academic backing:** ICAART 2024 — XGBoost + RL for dynamic wager placement
- **Approach:** Conservative Q-Learning (offline RL on historical movement)
- **Expected:** 0.5–1% CLV from optimal timing

---

### Modeling Architecture — Second Wave (Edges 63–72)

| # | Name |
|---|------|
| 63 | Variance prediction (heteroscedastic μ and σ) |
| 64 | Quantile regression / conformal prediction |
| 65 | Mixture models for bimodal performance |
| 66 | Hierarchical Bayesian partial pooling |
| 67 | Hot-hand / streakiness modeling |
| 68 | Live-state conditional EV |
| 69 | Lineup-graph GNN |
| 70 | PBP-sequence transformer |
| 71 | Multi-task joint training |
| 72 | LLM injury-text sentiment |

**Edge 63 — Variance Prediction.** Predict σ as well as μ. Some games high-variance (foul-trouble, blowout risk); others stable. Heteroscedastic gives correct tail probabilities. *Implementation:* second model with σ target.

**Edge 64 — Quantile Regression / Conformal.** Direct prediction of distribution quantiles or calibrated intervals via conformal. Bypasses distributional assumptions. *Implementation:* LightGBM with quantile loss; or conformal wrapper.

**Edge 65 — Mixture Models.** Bimodal distributions: dominant-game mode + quiet-game mode with low between-density. GMM captures; single-Gaussian misprices the trough. *Implementation:* fit per-player GMM on residuals.

**Edge 66 — Hierarchical Bayesian Partial Pooling.** Shrink player estimates toward team/position means; data-determined weights. Rookies pool more; vets less. *Implementation:* PyMC or numpyro hierarchical model.

**Edge 67 — Hot-Hand / Streakiness.** Real and small. EWMA over recent games captures it; book's window too long. *Implementation:* tune EWMA decay via CV.

**Edge 68 — Live-State Conditional EV.** For live betting (edge 73): conditional EV given live game state. Simulator reset from current point recomputes faster than book. *Implementation:* simulator state-reset endpoint.

**Edge 69 — Lineup-Graph GNN.** 5 players as nodes, edges weighted by shared minutes. GNN produces lineup quality embeddings capturing complementarity. *Implementation:* PyTorch Geometric on lineup-game outcomes.

**Edge 70 — PBP-Sequence Transformer.** PBP as token sequence; transformer predicts next event. Context-aware possession outcomes beyond Markov assumption. *Implementation:* sequence model on PBP corpus.

**Edge 71 — Multi-Task Joint Training.** Jointly train all 7 prop models with shared trunk. Counting stats correlated through minutes/pace; multi-output learns correlations for free. *Implementation:* multi-output XGBoost or shared-trunk NN with per-prop heads.

**Edge 72 — LLM Injury-Text Sentiment.** Beat reporter tweets and presser quotes contain qualitative signal not in structured fields. LLM extraction maps to play probability. *Implementation:* Claude with few-shot examples of injury text → did-play outcome.

---

### Modeling — Third Wave: Advanced Statistical & Decision-Theoretic (130–139)

| # | Name |
|---|------|
| 130 | Negative binomial for counting stats |
| 131 | Mixed-effects (player + game random effects) |
| 132 | Kalman filter on rolling player skill |
| 133 | Stacked ensembles with meta-learner |
| 134 | Latent class regression (player archetypes) |
| 135 | Causal forests / double ML |
| 136 | Contextual bandits for bet selection |
| 137 | Inverse RL on book's pricing function |
| 138 | Counter-detection bet sizing game theory |
| 139 | CLV-as-target meta-model |

**Edge 130 — Negative Binomial.** Poisson assumes mean = variance; counting stats overdisperse. NB allows extra variance parameter → better tail probabilities. *Implementation:* fit NB per player.

**Edge 131 — Mixed-Effects Models.** Hierarchical with both player random effects and game-level random effects (capturing pace, blowout, ref crew). *Implementation:* lme4 or PyMC.

**Edge 132 — Kalman Filter on Skill.** Player skill as latent state; observations are noisy measurements. Smooth time-varying skill estimates. *Implementation:* state-space model with skill as hidden state.

**Edge 133 — Stacked Ensembles.** Combine XGBoost + LightGBM + NN + linear via meta-learner on out-of-fold predictions. *Implementation:* stacked generalization with proper CV.

**Edge 134 — Latent Class Regression.** Players cluster into archetypes (3-and-D, primary handler, stretch big). Class-specific coefficients. *Implementation:* GMM clustering on season stats; conditional regression.

**Edge 135 — Causal Forests / Double ML.** Treatment effects (teammate absence on player). Double ML reduces confounding bias. *Implementation:* econml or doubleml.

**Edge 136 — Contextual Bandits for Selection.** Each market is an arm; features describe state; bandit balances exploration (new books, markets) vs exploitation. *Implementation:* LinUCB or Thompson sampling with feature context.

**Edge 137 — Inverse RL on Book Pricing.** Assume book rational; observe its prices; infer the model it must be using. Then exploit deviations. *Implementation:* MaxEnt IRL on price-feature pairs.

**Edge 138 — Counter-Detection Bet Sizing.** Kelly-optimal too aggressive if it triggers limits. Stackelberg game: book leader (sets detection threshold), bettor follower (sets size). *Implementation:* dynamic program with limit-probability state.

**Edge 139 — CLV-as-Target Meta-Model.** Train meta-model to predict CLV directly. CLV is forward-looking truth; predicting it sharper than the book reveals which features are alpha. *Implementation:* per-bet CLV log; regression on bet features.

---

## Category III: Execution Edges — You Act Faster and Cheaper

### Routing, Timing, News Speed (Edges 26–32)

| # | Name |
|---|------|
| 26 | Multi-book line shopping |
| 27 | Opening line capture |
| 28 | Injury/lineup news speed |
| 29 | Steam move detection |
| 30 | Cross-venue arbitrage |
| 31 | Account rotation |
| 32 | P2P exchange market making |

---

**Edge 26 — Multi-Book Line Shopping** `PARTIAL — 1 week`

Same prop differs 1–2 points across DK, FD, MGM, Caesars, bet365. Always buy best number. Research: 1–3% ROI vs single-book. At 5–12% vig, this is the difference between profitable and unprofitable.

- **Implementation:** The Odds API normalizes across ~40 books in one call ($20–80/mo)

---

**Edge 27 — Opening Line Capture**

Props posted 12–24 hours pre-tip, often 6am ET. Opening lines have max error; sharp money hasn't corrected. Research: 24+ hr pre-game bets average +1.2% CLV; final-hour bets −0.5%.

- **Implementation:** 6am polling; compare to model; flag +EV; queue for placement

---

**Edge 28 — Injury/Lineup News Speed**

Mandatory reports: 1pm and 5pm ET. Late scratches: any time up to 30min pre-game. Books adjust over 5–15 min; your model recomputes in seconds.

**Window:** 5–15 min per major injury. Multiple events per week.

- **Data sources:** NBA official report, RotoWire, beat reporters on X
- **Implementation:** Poll official 2×/day; RotoWire RSS; X monitor for credible reporters

---

**Edge 29 — Steam Move Detection**

Sharp accounts hit multiple books simultaneously → rapid cross-book movement. Detect by monitoring 5+ books every 30–60s; flag when 3+ move same direction within 60s. Bet direction of steam at slower books.

- **Weight:** Steam directional but not always correct; weight by own model's directional agreement

---

**Edge 30 — Cross-Venue Arbitrage**

Same event priced such that betting both sides guarantees profit. Example: sportsbook -110/-110 vs Kalshi 54/46. Sportsbook over vs Kalshi under = risk-free arb.

- **Limitation:** Windows close in minutes; must be automated

---

**Edge 31 — Account Rotation**

Track heat per book (count, win rate, velocity, prop concentration). Auto-rotate to cooler books. Pattern variations: vary timing, sizes, occasional mainlines for recreational appearance.

See [account-longevity.md](../strategy/account-longevity.md).

---

**Edge 32 — P2P Exchange Market Making**

On Novig and ProphetX, post lines rather than match. Set prices where model has edge on both sides. No account limiting — you are the maker.

- **Requirement:** Calibrated model, sufficient bankroll for meaningful lines, low variance for edge realization

---

### Execution — Second Wave (Edges 73–82)

| # | Name |
|---|------|
| 73 | Live in-game betting |
| 74 | Quarter / half-time mini-totals |
| 75 | Bonus / promo / boost economics |
| 76 | Reverse line movement detection |
| 77 | Round-robin SGP construction |
| 78 | Cross-market hedging |
| 79 | Half-point buying at fair price |
| 80 | DFS-prop cross-platform arbitrage |
| 81 | Cash-out / buyout exploitation |
| 82 | Data-feed latency arbitrage |

**Edge 73 — Live In-Game Betting.** Live lines update slower than the game. Simulator reset + re-simulate from any point produces fair value faster. Best moments: after sudden run, foul-trouble starter sits, Q3 end. *Implementation:* game-state subscription + simulator reset.

**Edge 74 — Quarter / Half-Time Mini-Totals.** Lower-attention markets. Books model as fractions of full game, ignoring intra-game variance, rotation timing, pace differential by quarter. *Implementation:* simulator emits quarter-by-quarter natively.

**Edge 75 — Bonus / Promo / Boost Economics.** Signup bonuses, profit boosts, free bets, no-sweats, odds boosts. Free bets convert at 60–80% face. Profit-boost on +EV markets compounds directly. *Implementation:* heat score + promo routing; conversion-strategy table.

**Edge 76 — Reverse Line Movement.** Line moves opposite public betting volume — sharp money on unpopular side. Stronger sharp signal than raw movement. *Implementation:* public bet % feed (Action Network); flag RLM divergence.

**Edge 77 — Round-Robin SGP Construction.** Given N +EV legs, construct all 2-of-N and 3-of-N SGPs. Book's formulaic correlation discount fails on positively-correlated legs → doubly +EV. *Implementation:* enumerate combinations; surface top-EV.

**Edge 78 — Cross-Market Hedging.** Props correlated with game-line markets. Joint Kelly across correlated markets, not market-by-market. *Implementation:* joint distribution from simulator; portfolio Kelly with correlation matrix.

**Edge 79 — Half-Point Buying.** Books offer alternate juice for half-points (O27.5 at -110 vs O27.0 at -130). When the price for the half-point < fair value, buy. *Implementation:* distribution-derived half-point fair price; compare to alt-juice menu.

**Edge 80 — DFS-Prop Arbitrage.** DraftKings runs both DFS and sportsbook. DFS salaries imply different projections than props. Divergences usually mean the prop side lags. *Implementation:* scrape DFS salaries; back out implied points; compare.

**Edge 81 — Cash-Out / Buyout.** Sportsbooks offer cash-out at current implied minus margin. When offer > model's fair value of remaining ticket: take. *Implementation:* live ticket pricing.

**Edge 82 — Data-Feed Latency Arb.** NBA official feed, broadcast (5–10s delayed), sportsbook in-game all have different latency. Where sportsbook is slowest, live betting is latency arb. *Implementation:* lowest-latency PBP subscription + live line timestamp comparison.

---

### Execution — Third Wave: Markets, Limits, Network (140–154)

| # | Name |
|---|------|
| 140 | Bet limit auto-detection |
| 141 | Sub-second Twitter streaming |
| 142 | Pinnacle / Circa as sharp-consensus oracle |
| 143 | Edit-my-bet feature exploitation |
| 144 | FanDuel SGP+ (multi-game parlay) |
| 145 | Microbet / next-play live markets |
| 146 | PrizePicks / Underdog higher-lower |
| 147 | Pre-emptive placement before lineup release |
| 148 | Per-bet CLV attribution |
| 149 | Multi-account family network |
| 150 | Beard / runner network |
| 151 | Offshore book access (Pinnacle, BetCRIS) |
| 152 | Reload bonus harvesting at mid-tier accounts |
| 153 | VIP host relationships at high volume |
| 154 | State-line geolocation arbitrage |

**Edge 140 — Limit Auto-Detection.** Books reduce limits silently. Detect by submitting test bets at multiple stakes daily; track max accepted. Limit reduction = imminent closure. *Implementation:* automated probe per book per market.

**Edge 141 — Sub-Second Twitter Streaming.** Twitter API v2 filtered stream: <1s from post to ingestion. Custom monitor on beat reporter list. *Implementation:* filtered stream + curated reporter list + NLP for status changes.

**Edge 142 — Pinnacle / Circa Sharp-Consensus.** Sharpest US-accessible books reflect maximum sharp action. Where Pinnacle differs from your model and you agree with its direction: bet softer book. *Implementation:* Pinnacle API or scrape; reverse direction signal.

**Edge 143 — Edit-My-Bet.** DK, FD, MGM offer post-placement edit. Extend +EV bets that became more favorable; hedge those that moved against. *Implementation:* monitor active bets vs current lines.

**Edge 144 — FanDuel SGP+.** Multi-game same-game parlays. Different (weaker) correlation structure than single-game SGP. *Implementation:* joint simulator over multiple games; same approach as edge 20.

**Edge 145 — Microbet / Next-Play Live.** Microbets (next-possession outcome, next-shot make/miss) update second-by-second. Model must be faster than book; live-EV harvesting. *Implementation:* real-time PBP + microbet pricing.

**Edge 146 — PrizePicks / Underdog / Sleeper.** Pick'em platforms with fixed payouts (3-pick 6×, 4-pick 10×). Specific player lines often off from sharp consensus. *Implementation:* scrape lines; compare to consensus; only enter +EV slates.

**Edge 147 — Pre-Emptive Placement.** Lineups confirmed at 1pm, 5pm, 30min pre-tip. Place bets seconds before based on edge 13/14 predictions. *Implementation:* automated queue triggered by clock.

**Edge 148 — Per-Bet CLV Attribution.** Record line at placement and closing line; CLV = log(close/open). Aggregate per feature to identify which edges produce CLV vs win-rate variance. *Implementation:* bet log + closing line capture + feature attribution.

**Edge 149 — Multi-Account Family Network.** Family members independently hold accounts (legal). Coordinated placement spreads heat. *Implementation:* independent ownership, separate IPs and payment methods, careful coordination to avoid account-linking detection. **See risk note at bottom.**

**Edge 150 — Beard / Runner Network.** Third party places bets in person. Legal in most jurisdictions, requires trust. Effectively unlimited per relationship. *Implementation:* relationship-based; small scale.

**Edge 151 — Offshore Books.** Pinnacle, BetCRIS, Bookmaker accept US bettors via crypto. No limiting, lowest vig (-105 vs -110). Offshore = legal gray zone + counterparty risk. *Implementation:* crypto on/off ramp + offshore accounts. **See risk note.**

**Edge 152 — Reload Bonus Harvesting.** Mid-tier accounts ($500–5000 weekly) receive periodic reload bonuses. *Implementation:* per-book promo calendar; route volume to bonus-active books.

**Edge 153 — VIP Host Relationships.** $50K+/month accounts get host. Hosts negotiate limits, settle disputed bets, comp travel. *Implementation:* volume threshold + relationship building.

**Edge 154 — Geolocation Arbitrage.** State borders allow access to best-line state (NJ side of Camden ↔ Philly border). Legal but operationally limited. *Implementation:* physical location + per-state account.

---

## Category IV: Structural Edges — The Market Itself Is Built Wrong

### Core Mispricings (Edges 33–37)

| # | Name | Status |
|---|------|--------|
| 33 | Props priced from box scores | PERMANENT |
| 34 | SGP correlation mispriced | STRUCTURAL |
| 35 | Alternate lines mispriced | STRUCTURAL |
| 36 | Early season miscalibration | RECURRING |
| 37 | Individual vs institutional access | PERMANENT |

---

**Edge 33 — Props Priced from Box Scores, Not Spatial Data** `PERMANENT`

Books have access to Genius Sports and Hawk-Eye via enterprise contracts. But prop pricing teams are small relative to markets they manage. Props are low-priority — less modeling sophistication than game lines. CV-derived spatial features capture information existing in the world but not in the prop price.

**Window:** 1–3 years before Genius Sports or Sportradar ships tracking-integrated prop pricing at scale.

---

**Edge 34 — SGP Correlation Is Mispriced** `STRUCTURAL`

Books price SGPs using formulaic correlation discount applied to individual leg probabilities. The formula is not model-derived. Simulator produces joint distributions naturally. When blowout high, all starters' counting stats lower. When pace high, all stats up. When players share handler roles, assists positively correlated. Generic discount wrong in sign and magnitude.

**Mechanism:** `P(all legs | sim)` > `P(all legs | book)` → +EV SGP.

---

**Edge 35 — Alternate Lines Mispriced vs Mainline** `STRUCTURAL`

Books concentrate modeling on mainline accuracy. Alternates (O27.5, O24.5, O30.5 when main is O27.5) get less attention. Your distribution prices any threshold with equal accuracy. Tails are where books are most wrong.

Often alternates beat the mainline even when mainline is slightly −EV.

---

**Edge 36 — Early Season Miscalibration** `RECURRING — every October`

Academic research (ScienceDirect): totals and props maximally mispriced in first 2–3 weeks. Books lack current-season data; rely on preseason projections + prior-season means. Your model has same data plus better features.

**Action:** Front-load volume in October–early November.

---

**Edge 37 — Individual vs Institutional Access** `PERMANENT`

Individuals hold accounts at 6+ books, operate prediction markets, access gray platforms (Novig, ProphetX), bet Kalshi. Registered investment entities cannot hold DraftKings accounts without regulatory overhead that kills economics. Advantage compounds as books tighten institutional detection while leaving individual accounts more latitude.

See [competitive-landscape.md](competitive-landscape.md).

---

### Structural — Specific Market Pockets (Edges 83–90)

| # | Name | Status |
|---|------|--------|
| 83 | Defensive props (blk/stl) underpriced | STRUCTURAL |
| 84 | Combo props (P+R+A) joint mispriced | STRUCTURAL |
| 85 | Quarter / split props | STRUCTURAL |
| 86 | Rookie / two-way / call-up no baseline | STRUCTURAL |
| 87 | One-off games (All-Star, Cup, Paris) | RECURRING |
| 88 | First-basket / first-to-score | STRUCTURAL |
| 89 | Player-vs-player matchup props | STRUCTURAL |
| 90 | New-market launches discounted juice | RECURRING |

**Edge 83 — Defensive Props Underpriced.** Blocks and steals are low-frequency, high-variance. Book models for them are simpler than scoring models. CV-derived spatial features (paint density, passing-lane positioning) capture signal beyond box scores. *Predicts:* defensive counting-stat overs and unders, especially alternates.

**Edge 84 — Combo Props Joint Mispriced.** P+R+A combo props treat stats as independent or with formulaic correlation. Reality: correlated through minutes, pace, matchup. Joint distribution from simulator prices correctly. *Predicts:* combo prop overs/unders.

**Edge 85 — Quarter / Split Props.** Q1 points, Q1 3PM, H1 rebounds priced as fractions of full-game projections. Books don't model intra-game variance, rotation timing, or pace by quarter. *Predicts:* quarter-by-quarter team totals and player splits.

**Edge 86 — Rookie / Two-Way / Call-Up No Baseline.** Books have minimal data on rookies first 10–20 NBA games, even less on G-League call-ups. NBA2Vec (edge 16) + college/G-League data gives tighter estimates. *Predicts:* rookie counting stats in first 20 games; call-up usage spikes.

**Edge 87 — One-Off Games.** All-Star game (no defense), Cup knockout games (different intensity), international games (Paris, London, Mexico City — travel + venue novelty). Books default to regular-season priors. *Predicts:* distribution shape and central tendency in novelty contexts.

**Edge 88 — First-Basket / First-to-Score.** Markov-dependent on opening tip and first possession. Books simplify to season-aggregate scoring rates. *Predicts:* first-basket scorer probability. *Implementation:* simulator with tip-off conditioning.

**Edge 89 — Player-vs-Player Matchup Props.** Joint distribution across two players on different teams. Books compute as P(A>exp) × P(B<exp) with small correlation adjustment. *Predicts:* player-vs-player matchup props. *Implementation:* joint simulation of both teams.

**Edge 90 — New-Market Launches.** When book newly launches in a state, when exchange (Novig, ProphetX) opens markets, or when book opens new prop type: juice low, lines tentative. Deliberate inefficiency. *Predicts:* identify launch windows; bet aggressively while juice low.

---

### Structural — Third Wave: Operator Mechanics & Rule Quirks (155–164)

| # | Name | Status |
|---|------|--------|
| 155 | Operator-specific quirks (DK / FD / MGM) | PERMANENT |
| 156 | Loyalty program redemption optimization | PERMANENT |
| 157 | Promo juice rotation schedules | RECURRING |
| 158 | Buzzer-beater inclusion variance across books | STRUCTURAL |
| 159 | Overtime not priced into mainline props | STRUCTURAL |
| 160 | Hack-a-FT distorts shooter prop pricing | STRUCTURAL |
| 161 | Replay review variance per ref crew | STRUCTURAL |
| 162 | Free-to-play / pick'em DFS structural cap | STRUCTURAL |
| 163 | New operator subsidized lines for market share | RECURRING |
| 164 | Star-player foul-out priced as average | STRUCTURAL |

**Edge 155 — Operator-Specific Quirks.** DK has aggressive alternate-line juice menu; FD SGP engine has its own correlation discount; MGM uses per-customer profile-based pricing. Each operator's model has known quirks. *Implementation:* per-operator profile of sharpest/softest markets.

**Edge 156 — Loyalty Program Redemption.** Caesars Reward Credits, MGM Tier Credits, DK Crowns. Redemption rates vary; some convert to bet credit at favorable rates. *Implementation:* per-program redemption calendar.

**Edge 157 — Promo Juice Rotation.** Some books run reduced-juice days (-105 instead of -110) on specific markets. *Implementation:* monitor juice per book; concentrate volume on reduced windows.

**Edge 158 — Buzzer-Beater Settlement Variance.** Buzzer-beater FGAs may or may not count in prop settlement depending on book. Same play settles differently across books. *Implementation:* per-book rule-card for end-of-quarter heaves.

**Edge 159 — Overtime Not Priced In.** Mainline props assume regulation only. OT (~7% of games) adds ~3 minutes for starters → counting stat boost. Books price this poorly. *Predicts:* prefer overs on stars when OT probability elevated (closely-matched teams). *Implementation:* add OT probability to distribution.

**Edge 160 — Hack-a-FT Distortion.** Strategic intentional fouling on poor FT shooters distorts FTA distribution heavily. Pre-game hack probability = f(opponent matchup). *Predicts:* FTA spike for poor-FT players vs aggressive opponents. *Implementation:* matchup-conditional hack probability flag.

**Edge 161 — Replay Review Variance Per Crew.** Replay review length and frequency vary per ref crew. Long reviews break momentum; some crews more review-prone. *Implementation:* per-crew review-rate aggregation.

**Edge 162 — Pick'em DFS Structural Cap.** PrizePicks / Underdog cap higher-lower payouts structurally below sportsbook lines (their advantage = structural overround). Bettor's advantage = line freshness on player-specific markets sportsbooks haven't priced. *Implementation:* arbitrage with sportsbook same-line where available.

**Edge 163 — New Operator Subsidies.** New operators (Fanatics, ESPN Bet at launch) subsidize lines + aggressive promos for customer capture. 6–12 month +EV window by structure. *Implementation:* track new operator launches; concentrate volume during subsidy window.

**Edge 164 — Star Foul-Out Priced as Average.** Stars foul out 2–4% of games. Absence from final 6+ minutes changes counting-stat distribution dramatically. Books price as small variance bump rather than mode shift. *Predicts:* high-foul-rate stars vs aggressive opponents. *Implementation:* simulator with foul-out state.

---

## Build Priority Matrix

Priorities are about *order of implementation*, not edge magnitude. Build foundations first; harvest dependents cheaply.

| Priority | Edges | Rationale |
|----------|-------|-----------|
| **P0 — Validate first** | 19 (calibration) | Must confirm edge exists before building anything else |
| **P1 — Trivial, high signal** | 3, 4, 5, 6, 7, 10, 11, 12, 15, 18, 38, 41, 45, 50, 51, 52, 58, 62, 91, 94, 105, 110, 115, 116, 117, 120, 121, 128, 129, 155, 156, 157, 158, 159, 160 | 1–2 days each; directly improves features |
| **P2 — Core infrastructure** | 26, 27, 28, 31, 59, 75, 140, 141, 142, 148, 152 | Enables profitable operation |
| **P3 — High leverage** | 13, 20, 34, 35, 53, 54, 77, 78, 84, 85, 144, 146, 147 | SGP + lineup + combo edges compound |
| **P4 — Moat deepening** | 8, 9, 16, 17, 21, 22, 23, 39, 40, 42, 44, 46, 63, 64, 65, 66, 67, 71, 72, 92, 95, 100, 101, 102, 103, 104, 109, 130, 131, 132, 133, 134, 139, 145, 161, 164 | Meaningful build, widens moat significantly |
| **P5 — Long term** | 24, 25, 30, 32, 33, 36, 37, 47, 48, 49, 55, 56, 57, 60, 61, 68, 69, 70, 73, 74, 76, 79, 80, 81, 82, 83, 86, 87, 88, 89, 90, 93, 96, 97, 98, 99, 106, 107, 108, 111, 112, 113, 114, 118, 119, 122, 123, 124, 125, 126, 127, 135, 136, 137, 138, 162, 163 | Structural or complex; some are free, some advanced ML |
| **Risk-gated** | 149, 150, 151, 153, 154 | See risk note below |

---

## Edge Compounding Map

A small number of *foundation* edges enable many others. Build them once; harvest dozens.

- **CV pipeline (1–9, 38–49, 91–114):** Foundation for 17 (calibration), 20 (SGP), 34 (SGP structural), 83 (defensive props), 84 (combo props), 88 (first-basket), 89 (matchup props), 105–110 (game-state CV), 164 (foul-out mode)
- **Possession simulator (19):** Foundation for 20, 24, 34, 68, 73, 74, 78, 84, 88, 89, 159, 164
- **Multi-book API (26):** Foundation for 27, 28, 29, 30, 76, 80, 140, 142, 143, 144, 146, 154, 155, 157
- **News / sentiment pipeline (28, 58, 59, 72, 125, 126, 127, 128, 141):** Foundation for all news-driven execution windows (14, 28, 118, 124, 147)
- **NBA2Vec (16):** Foundation for 24, 65, 66, 86, 134
- **Bet logging + CLV (148):** Foundation for 139, 23, and feedback loops on every edge
- **Heat tracking (31):** Foundation for 140, 149, 152, 153
- **Operator profiles (155):** Foundation for 26, 27, 75, 140, 142, 143, 144, 156, 157, 158, 163

Foundation list summarized: **CV pipeline, simulator, multi-book API, news pipeline, embeddings, bet log, heat tracking, operator profiles.** Eight foundations enable all 164 edges.

---

## Risk Note — Legal and Counterparty Gradient

Not every edge is unambiguously available. Edges fall on a gradient:

**Always-OK:** All information, model, and most execution edges (1–148, 155–164). Legal everywhere sports betting is legal.

**Operationally-gray, legally-OK in most jurisdictions:**
- Edge 149 (multi-account family network) — legal if accounts are genuinely independent; book TOS may prohibit
- Edge 150 (beards / runners) — legal in most jurisdictions; book TOS prohibits
- Edge 154 (geolocation arbitrage) — legal if physically in licensed state; not VPN-circumvented

**Legal gray zone:**
- Edge 151 (offshore books, crypto access) — federally ambiguous in US; UIGEA risk on banking side; counterparty risk on book solvency
- Edge 153 (VIP relationships at offshore books) — same risks plus relationship-disclosure exposure

**Do not pursue:**
- VPN circumvention of state geolocation — illegal
- Account fraud (synthetic identities, impersonation) — illegal
- Match-fixing or insider information from team / league personnel — illegal and league-banning

Consult counsel for jurisdiction-specific advice before pursuing risk-gated edges. The first 148 edges + 155–164 are sufficient to build a profitable system; the risk-gated edges are scale amplifiers, not requirements.

---

*See [MASTER_PLAN.md](../../MASTER_PLAN.md) for full strategic context. See [validation-methodology.md](validation-methodology.md) for how to verify each edge produces real CLV. See [competitive-landscape.md](competitive-landscape.md) for why institutional firms cannot replicate this stack.*
