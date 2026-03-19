# Complete Data Sources Catalog
> Every data source the system collects from — free, categorized by how it enters the prediction pipeline.
> Last updated: 2026-03-17

---

## Layer 1 — CV Tracker (Broadcast Video)

Downloaded via yt-dlp, processed frame-by-frame. Everything extracted from pixels.

### Currently Extracting ✅
| Signal | Module | Output |
|---|---|---|
| Player 2D court positions (x,y) | advanced_tracker.py | tracking_data.csv |
| Player speed + acceleration | feature_engineering.py | Per-frame velocity |
| Team classification (which team) | color_reid.py | team_id 0/1 |
| Jersey number via OCR | jersey_ocr.py | player_name lookup |
| Player identity (roster match) | player_identity.py | named player |
| Ball position (2D) | ball_detect_track.py | ball_x, ball_y |
| Possession (who has ball) | ball_detect_track.py | possessor_id |
| Events: shot / pass / dribble | event_detector.py | event type + frame |
| Court homography (per clip) | court_detector.py | M1 matrix |
| Scoreboard OCR | scoreboard_ocr.py | score, clock, shot clock |
| Play type classification | play_type_classifier.py | ISO/PnR/C+S/etc |
| Possession type | possession_classifier.py | transition/drive/paint/post |

### Not Yet Extracting — Build In Phase 2.5 / 6 🔲
| Signal | Method | Value |
|---|---|---|
| Spacing index | Convex hull of 5 offensive positions | Offensive quality modifier |
| Paint density | # players in paint at shot moment | Rebound + foul predictor |
| Defensive alignment | All 5 defenders between ball and basket? | xFG modifier |
| Pick-and-roll coverage type | Help defender movement pattern | Shot outcome predictor |
| Zone vs man detection | Off-ball defender positioning | Massive xFG modifier |
| Double team detection | 2 defenders converging on 1 player | Kick-out pass predictor |
| Off-ball screen detection | Velocity stop pattern + another player accelerates | Play type label |
| Backdoor cut detection | Player moves toward basket while defender ball-watches | Open layup signal |
| Help rotation angle | Degrees/frame of nearest off-ball defender closing | Defensive quality score |
| Ball shot arc | Parabola fit to ball trajectory in air | Shot quality signal |
| Ball release speed | Distance / frames from last contact to first airborne | Contested-ness proxy |
| Pass speed | Ball distance / frames in air | Transition / open look |
| Dribble rhythm | Time between ball-ground contacts | Pressure detection |
| Movement asymmetry | Left vs right leg favor across 50+ frames | Sub-clinical injury signal |
| Player speed vs baseline | Current game speed vs season average | Real-time fatigue |
| Jump frequency | Times player leaves ground per possession | Q4 fatigue proxy |
| Contest arm extension | Defender arm vertical vs reaching | xFG modifier ±3-5% |
| Crowd noise level | Audio RMS amplitude per possession | Momentum swing signal |
| Announcer keyword detection | Speech-to-text: "AND ONE", "FLAGRANT", "TIMEOUT" | Faster event labeling |
| Forced shot flag | Shot clock < 5 + off-balance shooter velocity | Bad shot predictor |

---

## Layer 2 — NBA API (nba_api package — free, already installed)

### Currently Pulling ✅
| Endpoint | Data | Status |
|---|---|---|
| LeagueDashPlayerStats | Base stats: pts/reb/ast/min/fg%/3pt%/ft% | ✅ 569 players |
| PlayerDashboardByYearOverYear | Advanced: usg%, TS%, off_rtg, def_rtg, net_rtg, PIE, eFG% | ✅ 569/569 |
| PlayerGameLog | 24-col game log per player | ✅ 568/569 |
| ShotChartDetail | 221,866 shots: court_x/y, made/missed, zone, shot type | ✅ 569 players × 3 seasons |
| PlayByPlayV3 | Full PBP events: 3,102 games (84%) | ✅ Ongoing |
| LeagueGameLog | Schedule, results, home/away | ✅ 3 seasons |
| CommonTeamRoster | Roster per team per season | ✅ |
| BoxScoreTraditionalV2 | Per-player box scores | ✅ 13 games |
| LeagueDashTeamStats | Team off_rtg, def_rtg, pace, eFG%, TS%, TOV% | ✅ 30 × 3 seasons |
| schedule_context.py | Rest days, back-to-back, travel distance | ✅ |
| lineup_data.py | 5-man units, on/off splits | ✅ |

### Not Yet Pulling — High Priority 🔲
| Endpoint | Data | Model Value |
|---|---|---|
| **BoxScorePlayerTrackV2** | Speed (mph), distance (mi), touches, paint touches, elbow touches per game | Real fatigue + usage depth |
| **PlayerDashPtShots** | Contested %, C+S %, pull-up %, touch time, dribbles before shot | xFG modifier, shot creation type |
| **LeagueDashPtDefend** | Defender stats per opponent: FG% allowed at rim / mid / 3pt | Matchup matrix ground truth |
| **MatchupsRollup** | Who guards whom per game, time, partial possessions, pts/100 | Actual player-on-player efficiency |
| **LeagueHustleStatsPlayer** | Screen assists, deflections, loose balls, charges, contested shots | Defensive effort, screen ROI |
| **SynergyPlayTypes** | Pts/possession by play type (ISO/PnR-BH/PnR-Screen/Post/C+S/Cut/Hand-off/Spot-up/Transition) | Play type model ground truth + xFG by play type |
| **LeagueDashPlayerClutch** | Full box score in clutch (last 5 min ≤5 pt margin) | Clutch model ground truth |
| **LeaguePlayerOnDetails** | Net rating with player on vs off court | True player impact |
| **PlayerDashboardByLastNGames** | Last 5/10/15/20/25 game rolling splits | Recency weighting |
| **LeagueDashOppPtShot** | Opponent shot quality allowed by zone: paint / mid / corner3 / above-break3 | xFG v2 defensive zone input |
| **DraftHistory** | Every pick, college, nationality, year | Development curve, experience |
| **CommonPlayerInfo** | Height, weight, wingspan (some), birthdate, experience, position | Age curve, physical features |
| **VideoEvents** | Video clip URLs for specific play types by player | FREE labeled training data for CV classifier |
| **LeagueDashLineups** | 5-man lineup performance with more granularity | Lineup chemistry detail |
| **TeamDashLineups** | Per-team lineup splits with advanced metrics | Rotation model |

---

## Layer 3 — Basketball Reference (free, scraped with requests + BeautifulSoup)

> **Priority: HIGH** — largest free dataset not yet tapped. Decades of historical data.

| Dataset | What You Get | Model Unlocked |
|---|---|---|
| **BPM / Box Plus-Minus** | Impact metric not in nba_api | Cross-validate your player impact model |
| **VORP** | Value Over Replacement Player | Career baseline comparisons |
| **Win Shares / WS/48** | Team contribution metric | Age curve ground truth |
| **Historical game logs (1946–present)** | Every game ever played | Much deeper training data for win prob |
| **Historical PBP (1996–present)** | Full play-by-play older seasons | More training data for all sequence models |
| **Shooting splits by exact distance** | 0-3ft, 3-10ft, 10-16ft, 16-3pt, 3pt separately | More granular xFG zones |
| **Per-100 possession stats** | Volume-neutralized efficiency | Better player comp baseline |
| **Injury history (game availability)** | Per-player, every game missed, injury type | Injury recurrence model |
| **Coaching records** | Every coach: wins/losses, tenure, system | Coaching adjustment model |
| **Draft + college stats** | College efficiency → NBA translation | Player development curve |
| **Arena data** | Altitude, coordinates, capacity | Altitude fatigue, travel model |
| **Contract / salary** | Annual salary, years remaining, type | Contract year motivation model |
| **Transactions** | Every trade, signing, waiver, call-up date | Team chemistry disruption timeline |
| **Referee assignments** | Ref names from historical game logs | Extended ref tendency database |
| **Historical Vegas lines (~2008+)** | ATS record, game totals historical | CLV backtesting without paid data |
| **On/off splits (detailed)** | Per-player net/off/def rtg on vs off | More granular player impact |

---

## Layer 4 — Betting Market Data (free sources)

| Source | What You Get | How | Priority |
|---|---|---|---|
| **The Odds API** | Live lines: spread, total, ML, props across 20+ books | Already integrated (ODDS_API_KEY) | ✅ Active |
| **Action Network** (actionnetwork.com) | Public bet % + money % per game and prop | Scrape HTML | 🔴 HIGH |
| **OddsPortal** (oddsportal.com) | Historical closing lines all major books ~15 years | Scrape HTML | 🔴 HIGH |
| **Covers.com** | Historical ATS records, consensus picks, line history | Scrape HTML | 🟡 MED |
| **Pinnacle** (pinnacle.com) | Sharpest opening lines in world — public pages | Scrape or unofficial API | 🔴 HIGH |
| **DraftKings** props | Current player props + lines for tonight | Scrape or unofficial API | 🟡 MED |
| **FanDuel** props | Current player props + lines for tonight | Scrape or unofficial API | 🟡 MED |
| **BettingPros** | Aggregated best available lines across 20+ books | Free tier API | 🟡 MED |

**Key derived signals:**
- **Sharp money signal** = line moves against public bet % (reverse line movement)
- **Steam move** = sudden Pinnacle line move within seconds → sharp syndicate action
- **CLV proxy** = your line at time of bet vs Pinnacle closing line
- **Prop correlation** = if DraftKings Murray pts moves, which other props are correlated?

---

## Layer 5 — News / Injury (free)

| Source | Signal | Method | Priority |
|---|---|---|---|
| **ESPN API** (unofficial) | Injury status, news headlines | Already integrated (injury_monitor.py) | ✅ Active |
| **NBA Official Injury Report PDF** | Exact status: out/questionable/probable + injury type, published ~5pm ET daily | PDF scrape at nba.com | 🔴 HIGH |
| **RotoWire RSS feed** | Injury + lineup news, faster than ESPN | feedparser Python package | 🔴 HIGH |
| **Reddit r/nba API** | Injury threads, lineup news, discussion | praw Python package — completely free | 🟡 MED |
| **Twitter/X beat reporters** | Injury news 1-4 hours before official | snscrape or search API | 🟡 MED |
| **HoopsHype** (hoopshype.com) | Salary cap data, contract years, extension news | Scrape HTML | 🟡 MED |
| **ProSportsTransactions** | Every transaction: trades, signings, call-ups, 10-days | Scrape HTML | 🟡 MED |
| **news_scraper.py** | ESPN news headlines | Already integrated | ✅ Active |

**Key derived signals:**
- **Injury lag window** = time between beat reporter tweet and book line adjustment (15-60 min edge)
- **Trade disruption clock** = games since last roster move (chemistry reset model)
- **Load management pattern** = coach + player history of sitting on B2Bs

---

## Layer 6 — Context Data (free)

| Source | What You Get | Method |
|---|---|---|
| **schedule_context.py** | Rest days, B2B, travel distance | Already integrated ✅ |
| **ref_tracker.py** | Referee tendencies: pace, foul rate, home win% | Already integrated ✅ |
| **Arena altitude lookup** | Denver (5,280ft), Utah (4,226ft), San Antonio (650ft) — all elevated | Static lookup table |
| **TimeZoneDB API** (free tier) | Timezone of every arena — calculate timezone shifts per road trip | Free API |
| **Google Maps Distance API** (free 200/day) | Exact travel distance city to city | Free tier |
| **Spotrac** | Player contracts: years remaining, annual salary, options | Scrape HTML |
| **CommonPlayerInfo** (nba_api) | Age, experience (years in NBA), height, weight | Already have package |

---

## Data Collection Priority Order

| Priority | Source | Effort | Edge Unlocked |
|---|---|---|---|
| 1 | nba_api hustle + tracking endpoints | 1 day | Real touch data, contested %, defensive effort |
| 2 | nba_api SynergyPlayTypes | 1 day | Ground truth play type labels, pts/possession |
| 3 | nba_api matchup + defender endpoints | 1 day | True matchup matrix, who guards whom |
| 4 | NBA official injury report PDF | 1 day | Faster injury signal than ESPN |
| 5 | Action Network public %s | 1 day | Sharp vs public split on every game/prop |
| 6 | OddsPortal historical lines | 2 days | CLV backtesting without paying for data |
| 7 | Basketball Reference scraper | 3 days | BPM, historical injuries, contracts, coaching records |
| 8 | RotoWire RSS | 2 hours | Injury news faster than ESPN |
| 9 | DraftKings/FanDuel props scraper | 1 day | Prop lines for correlation model |
| 10 | CV audio signals (crowd noise, announcer) | 2 days | Momentum signal, faster event labeling |

---

## Related
- [[Complete Model Catalog]] — all 80 models and what feeds them
- [[Prediction Pipeline]] — how all data combines into one prediction
- [[System Architecture]] — technical wiring diagram
- [[Tracker Improvements Log]] — CV data quality progress
