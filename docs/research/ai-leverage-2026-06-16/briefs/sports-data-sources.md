# Sports Data Sources 2026: APIs, Open Datasets, Tracking
_Researched 2026-06-16. Scope: odds APIs, stats/PBP sources, tracking data, and open datasets across NBA/MLB/Soccer/Tennis -- access patterns, cost, licensing, freshness, and prioritized recommendations for a solo-built calibrated prediction platform._

---

## TL;DR (highest-leverage takeaways)

- **The Odds API is the right odds backbone at $30-99/mo**: 40+ soft books + historical archive from June 2020; Pinnacle (sharp anchor for CLV diagnostics) requires the $99 Business tier or a third-party aggregator (OddsPapi has it on free tier); direct Pinnacle API closed publicly July 2025.
- **MLB StatsAPI (statsapi.mlb.com) is fully free, no key required**: live game feed, pitch-by-pitch PBP, win probability, context metrics -- the best free real-time feed of any sport covered here.
- **nba_api v1.5+ now requires PlayByPlayV3** (V2 returns empty JSON); cloud IPs still get rate-limited -- residential proxy or 1-2s delays mandatory; 70+ endpoints remain free.
- **StatsBomb open data (soccer)** covers ~50 competitions/seasons in JSON event format (shot location, pressure, 360-degree freeze frames for selected matches) under a research-attribution license -- best free granular soccer event data; FBref aggregates complement it for season-level features.
- **Jeff Sackmann's tennis repos (CC BY-NC-SA 4.0)**: ATP + WTA match results/rankings back to 1968, point-by-point data for ~5000+ charted matches, continuously updated through current season -- the single best free tennis corpus.
- **Retrosheet (baseball)**: full event files 1898-2025 released Fall 2025, including 2025 regular season + postseason; copyrighted but free for non-commercial research; the deepest historical baseball PBP corpus.
- **The moat remains proprietary CV tracking**: all stats/odds sources above are available to any analyst; broadcast-video-derived positions/spacing/fatigue are still uncommoditized.

---

## Key capabilities / techniques

### 1. The Odds API (the-odds-api.com)

**What it is:** REST API aggregating pre-game and live odds from 40-50+ sportsbooks (US, UK, AU, EU) into a single normalized feed. The de facto standard for indie model builders.

**Endpoints (V4):**
- `GET /sports` -- list in-season sports (free, no credit cost)
- `GET /odds` -- live/upcoming odds; 1 credit per market per region
- `GET /scores` -- live + recently completed scores
- `GET /event/odds` -- all markets for a single event
- `GET /historical/odds` -- snapshots from June 2020 onward; costs 10x credit multiplier
- `GET /participants` -- team/player roster data (1 credit)

**Market types:** h2h (moneyline), spreads, totals, outrights (futures), player props (NBA/MLB/NHL player_points, player_home_runs, etc.), period/quarter markets, alternate lines.

**Regions:** us, us2, uk, au, eu (each region = +1x credit cost per query).

**Pricing 2026:**
| Tier | Cost | Credits/mo | Notes |
|------|------|-----------|-------|
| Free | $0 | 500 | h2h only, no Pinnacle |
| Professional | $30 | 20,000 | Spreads/totals, ~40 US books |
| Business | $99 | 200,000 | Player props, Pinnacle, EU/UK/AU books, full historical archive |

**Historical archive:** June 2020 to present; useful for building OOS CLV validation sets. Cost: 10 credits per market per region per snapshot.

**Pinnacle access:** only at the $99 Business tier as of 2026; provides "sharp anchor" lines for CLV diagnostics (compare own pre-game projection to Pinnacle open -> Pinnacle close).

**Rate limits:** response headers return `x-requests-remaining`, `x-requests-used`, `x-requests-last` on every call; plan queries around credit budget not time-based limits.

---

### 2. Pinnacle Odds (direct + aggregators)

**Direct Pinnacle API:** closed to public July 23, 2025. To apply: email api@pinnacle.com with use-case description. Requires funded account + regional eligibility. Not a reliable path for solo builders.

**Third-party paths to Pinnacle lines:**
- **The Odds API Business ($99/mo)** -- Pinnacle included in bookmaker set
- **OddsPapi (free tier: 250 req/mo)** -- includes Pinnacle + Singbet on free tier; no historical penalty (1 request = 1 request regardless of snapshot age); 350+ books total; no-vig lines available
- **SharpAPI (sharpapi.io)** -- markets itself as "the only stable Pinnacle odds API"; REST + SSE streaming; paid plans
- **BettingIsCool (api.bettingiscool.com)** -- 2.7 billion odds records back to 2021, 46 sports; best for historical Pinnacle CLV reconstruction

**Why Pinnacle matters for this project:** Pinnacle closing lines are the standard calibration anchor for CLV measurement. Devigged Pinnacle closing line = the market's best probability estimate. Use it diagnostically (how well does our pregame projection track Pinnacle's open-to-close movement?) not as a betting signal.

---

### 3. Betfair Exchange

**Access:** Betfair Exchange API (free; requires UK/international account). Provides exchange lay/back odds with volume depth -- true market-clearing prices, not book-shaded lines. Available in the US only via betfair.com/exchange if account is pre-existing.

**Use case for this project:** Exchange odds are the closest thing to a true probability market (no vig direction, just a spread between back/lay). In-play exchange prices update tick-by-tick -- better in-game calibration anchor than US soft books. However, US legal access is gated on account jurisdiction.

---

### 4. OddsJam / OddsAPI

OddsJam's API product (oddsapi.io) targets +EV detection use cases. As of 2026 its pricing focuses on retail-facing bet-finding tools rather than raw data feeds. For raw data, The Odds API or OddsPapi are better choices for this project.

---

### 5. nba_api (Python, github.com/swar/nba_api)

**What:** Unofficial Python wrapper for stats.nba.com. 70+ endpoint classes mapping every published NBA.com stats endpoint.

**Key 2026 status changes:**
- `PlayByPlayV2` is deprecated -- NBA.com API now returns empty JSON for it. Use `PlayByPlayV3` instead (import from `nba_api.stats.endpoints`).
- Library now requires Python 3.10+.
- Cloud IP blocking: stats.nba.com actively blocks AWS/GCP/Azure IPs. Use residential proxy or inject `time.sleep(1-2)` between calls. The existing project workaround (`cdn.nba.com/liveData` for live PBP) sidesteps this correctly.

**Most valuable endpoints:**
- `PlayByPlayV3` -- action-level PBP with coordinates
- `LeagueDashPtStats` -- speed, distance, touches, closest defender aggregates (tracking summary)
- `ShotChartDetail` -- shot x/y coordinates, defender distance, shot zone
- `LeagueGameLog` / `BoxScoreAdvancedV3` -- advanced box scores
- `LineupStats` / `PlayerDashLineups` -- 2/3/5-man lineup splits

**Rate limits:** ~600 req/min theoretical max; practical safe rate is ~30/min with delays to avoid bans. Pre-scraped corpora (shufinskiy/nba_data, Kaggle PBP) preferred for bulk historical work.

---

### 6. MLB StatsAPI (statsapi.mlb.com)

**What:** Official MLB API. No API key required. No documented rate limits. Completely free.

**Base URL:** `https://statsapi.mlb.com/api/v1/`

**Key endpoints for this project:**
- `game/{gamePk}/feed/live` -- full live game feed: pitch-by-pitch PBP, current score, runners on base, count, pitch velocity/location (Statcast-derived), play outcomes
- `game/{gamePk}/playByPlay` -- detailed play-by-play
- `game/{gamePk}/linescore` -- inning-by-inning score
- `game/{gamePk}/boxscore` -- box scores with splits
- `game/{gamePk}/winProbability` -- built-in win probability (MLB's own model -- useful as calibration baseline)
- `game/{gamePk}/contextMetrics` -- leverage index and game context
- `schedule` -- daily schedule with gamePk IDs

**Python wrapper:** `MLB-StatsAPI` (pypi: `MLB-StatsAPI`, github.com/toddrob99/MLB-StatsAPI) provides convenient wrappers. No auth needed. The live game feed is the richest free real-time sports data feed of any sport covered in this brief.

**Statcast data (separate):** Baseball Savant (baseballsavant.mlb.com) publishes Statcast pitch tracking (exit velocity, launch angle, spin rate, x/y coordinates) as downloadable CSVs. The `pybaseball` library wraps Statcast queries. Free, no key.

---

### 7. ESPN Endpoints (unofficial)

ESPN maintains hidden JSON endpoints used by their own site and app. Not officially documented but widely used:

- `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard` -- live scores
- `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={eventId}` -- PBP + box score

No key required. No published rate limits. Stability risk: ESPN has changed endpoint structure multiple times; treat as supplemental, not primary.

---

### 8. StatsBomb Open Data (soccer)

**Repo:** github.com/statsbomb/open-data (1000+ commits, actively maintained)

**Coverage (as of 2026):** ~50 competitions including:
- FIFA World Cup 2018, 2022
- UEFA Euro 2020
- La Liga, Premier League, Bundesliga, Serie A (selected seasons)
- NWSL, FA WSL, Champions League (women's)
- Indian Super League

**Event types:** every match event is geolocated on the pitch with contextual variables: passes (type, height, technique, end location), shots (technique, body part, xG), pressures, duels, interceptions, carries, ball receipts. StatsBomb 360 (freeze-frame freeze data showing all 22 player positions at event moment) available for selected matches.

**Format:** JSON files (one per match) exported from StatsBomb's commercial API. Python access: `statsbombpy` library.

**License:** Free for research/education; require attribution ("Data provided by StatsBomb") + StatsBomb logo on published work. Non-commercial only -- not for commercial products without a commercial license.

**FBref (fbref.com):** FBref uses StatsBomb's commercial data under license and publishes aggregated season/player/team stats. Scrapeable but rate-limit carefully. Useful for long-run team-strength aggregates, xG, progressive carries/passes at season level. The `soccerdata` Python library wraps FBref and several other sources.

---

### 9. Jeff Sackmann Tennis Data (GitHub)

**Repos:**
- `JeffSackmann/tennis_atp` -- ATP match results, rankings, player bios; back to 1968; updated continuously through current season. CSV per year.
- `JeffSackmann/tennis_wta` -- same format, WTA. Same coverage.
- `JeffSackmann/tennis_MatchChartingProject` -- shot-by-shot point data for 5000+ charted matches; user-contributed; includes serve direction, shot type, depth, error type.
- `JeffSackmann/tennis_pointbypoint` -- sequential point-by-point data for tens of thousands of ATP/WTA tour matches; score state at each point.

**Format:** CSVs. Match results files: date, tournament, surface, round, winner/loser IDs, scores, match stats (1st serve %, aces, double faults, etc.). Rankings files: weekly ELO-style ranking snapshots.

**Coverage:** ATP/WTA main draw events continuous from ~2000; challenger/ITF partial. Grand Slam point-by-point via `tennis_slam_pointbypoint`.

**License:** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0). Free for research; attribution required; no commercial use without permission.

**Why it matters for this project:** The tennis domain already uses Elo ML models (proven in the platform build). Sackmann's data is the foundational corpus -- match-level for Elo rating, surface splits, fatigue (tournament schedule), and PbP for in-game conditioning.

---

### 10. Retrosheet (baseball historical PBP)

**Site:** retrosheet.org

**Coverage:** Play-by-play event files 1898-2025 (Fall 2025 release includes full 2025 regular season + postseason + All-Star game). Historical coverage continuous from 1918+; earlier years have gaps.

**Fall 2025 release highlights:**
- Full 2025 MLB regular season + postseason event files
- 1910 AL/NL complete event files (newly digitized)
- 230 historical game updates (1921-2024) from scorecards/media
- 326MB traditional zip + 710MB CSV collection downloadable

**Format:** Proprietary `.evN` event file format (parsed by Chadwick Baseball Bureau tools) + CSV exports. Each play coded as: pitch sequence, base state, play result, fielding credits. The `pyretrosheet` or `chadwick` tools parse these.

**License:** Copyright 1996-2026 by Retrosheet. Free for research/non-commercial use. Attribution required. NOT open source -- cannot redistribute raw data files.

**Lahman Database (related):** A cleaned, user-friendly relational baseball database (Sean Lahman) covering 1871-present: batting/pitching/fielding season stats, awards, salaries, teams. Public domain. Available at seanlahman.com or via the `lahman` R package / Kaggle. Retrosheet is more granular (play-by-play); Lahman is better for season-level historical modeling.

---

### 11. Tracking Data (NBA second-spectrum, MLB Statcast, soccer tracking)

**NBA (Second Spectrum):** NBA's official optical tracking vendor since 2017. Raw 25fps XY player + ball coordinates are NOT publicly available. Aggregated tracking stats (speed, distance, touches, closest defender at shot) accessible via `nba_api` LeagueDashPtStats. The only public raw NBA tracking release remains SportVU 2015-16 (631 games; github.com/sealneaward/nba-movement-data).

**MLB Statcast:** Pitch tracking (location, velocity, spin, extension) + batted ball tracking (exit velocity, launch angle, spray angle) publicly available via Baseball Savant. `pybaseball` library. Coverage: 2015-present. This is the most democratized tracking data in pro sports.

**Soccer:** Professional optical tracking (TRACAB, ChyronHego) is behind expensive data vendor licenses ($10K+/year). Exception: StatsBomb 360 freeze-frame (in open data for selected matches) gives all 22 player positions at event moment. For open-source tracking research: `kloppy` library normalizes tracking data across vendors; SoccerTrack (GitHub) for computer vision research.

**Tennis:** Hawk-Eye ball-tracking data is proprietary to ATP/WTA. Shot-level data in Sackmann's Match Charting Project is human-coded, not sensor-tracked.

---

## How THIS project should use it

### Immediate wins (low effort, high value)

1. **Upgrade The Odds API to the $99 Business tier**: unlocks player props (needed for multi-sport prop calibration), Pinnacle (CLV anchor), and historical archive (OOS validation back to June 2020). At 200K credits/mo this supports ~5K daily market snapshots with room to spare.

2. **Wire MLB StatsAPI live game feed for in-game conditioning**: `game/{gamePk}/feed/live` is free, requires no key, and delivers pitch-by-pitch state (count, runners, score, inning) -- exactly the "realized state" input the in-game conditioning layer needs. MLB is the easiest sport to add real-time in-game features to.

3. **Activate OddsPapi free tier (250 req/mo)** for Pinnacle no-vig lines: devigged Pinnacle closing line is the calibration target (what does the market's best predictor say?). Compare own pregame projection to this; Brier/log-loss gap is the honest measure of prediction quality. OddsPapi free tier is sufficient for a handful of games per day.

4. **Pull Jeff Sackmann ATP data for 2025-26 season**: the existing tennis Elo ML proof used a static corpus; extend it with the continuously-updated `tennis_atp` CSVs. Surface, fatigue (days-since-last-match, rounds-played-tournament), and H2H deltas are the freshness inputs the Elo model can absorb without any architectural change.

5. **Switch nba_api PBP calls to PlayByPlayV3**: the project likely already does this via cdn.nba.com liveData, but any legacy V2 call will silently return empty JSON. Audit `domains/basketball_nba/` for any remaining V2 imports.

### Medium-term (model quality)

6. **Add StatsBomb open data soccer event layer**: the existing soccer domain uses O/U Poisson models. StatsBomb shot-level xG gives a principled shot-probability-aggregated goal rate estimate -- better than aggregated team goal rates for adjusting the Poisson lambda. Free (research license). The `statsbombpy` library makes this a one-afternoon integration.

7. **Activate Retrosheet / Lahman for MLB historical OOS corpus**: the MLB domain proof used a single corpus. Retrosheet event files give a second independent corpus (different seasons, pre-modern era). Two corpora -> honest multi-corpus OOS validation (the project's binding invariant). Use `pybaseball` + Retrosheet 2010-2024 as the second corpus.

8. **Use MLB Statcast (pybaseball) for pitcher quality features**: starter quality (xFIP, SIERA) and bullpen leverage are the biggest non-market information in MLB totals prediction. Statcast is free and covers 2015-present. Starter-matchup Statcast features are the most defensible freshness signal in MLB.

9. **Wire Betfair Exchange in-play odds (if account accessible)**: exchange in-play prices are the most honest real-time win probability available. Compare the sim's in-game Brier against both the exchange mid-price and the NBA/MLB own published win probability (both free). Establishes a clear calibration ladder: sim -> MLB official WP -> exchange.

10. **OddsPortal + BettingIsCool for historical CLV reconstruction**: BettingIsCool's 2.7B records from 2021 + Pinnacle are useful for building a historical CLV validation set outside The Odds API's June 2020 window. Use for testing whether pre-game projections moved the line in the right direction (directional CLV) even where exact captured price is unknown.

### Data freshness discipline

The freshest sources in order: Betfair Exchange (tick-by-tick in-play) -> The Odds API live odds (seconds) -> MLB StatsAPI live feed (pitch-by-pitch) -> nba_api live (quarter-level) -> nba_api next-day (final box scores). Freshness is the binding constraint on pregame calibration -- the project already knows this. The in-game layer (where freshness is fully capturable) is the priority funnel investment.

---

## Gotchas / limits

- **The Odds API historical data is expensive in credits**: at 10x multiplier, pulling 3 markets x 1 region x 1000 historical snapshots = 30,000 credits -- 1.5 months of the $30 plan in one historical pull. Budget carefully; cache all historical pulls locally.
- **stats.nba.com blocks cloud IPs**: even with PlayByPlayV3, cloud-hosted agents will get 429s. The project's cdn.nba.com workaround is correct; maintain it. Residential proxy adds ~$5-10/mo.
- **StatsBomb open data is NOT the full StatsBomb product**: commercial StatsBomb covers all top-5 European leagues going back 10+ years with 360 data for every match. The open data is a curated subset. For full coverage, the commercial license is $10K+/year -- out of scope for solo builder.
- **Retrosheet data requires Chadwick tools to parse**: the `.evN` event file format is not human-readable. Use the `chadwick` command-line tools or `pyretrosheet` to convert to CSV. Plan an afternoon for the pipeline setup.
- **Jeff Sackmann match charting data is human-coded, not complete**: only 5000+ matches charted; coverage biased toward high-profile ATP events. For full-tour coverage, use ATP result CSVs (complete); use charting data only for secondary point-level features.
- **Direct Pinnacle API is closed to public (July 2025)**: do not plan a pipeline around direct Pinnacle access. Use The Odds API Business tier or OddsPapi as the stable path.
- **MLB StatsAPI is unofficial and undocumented by MLB**: no SLA, no official rate limits, no warning before endpoint changes. Has been stable for years but treat as "works until it doesn't." Cache all fetched game feeds locally.
- **ESPN endpoints are undocumented and break without notice**: use only as secondary/supplemental, never as primary data source for models.
- **Betfair Exchange US access is jurisdiction-gated**: US residents cannot legally open new Betfair accounts in 2026. If the project intends to use exchange prices as a calibration anchor, this must route through historical odds sources (BettingIsCool, OddsPortal) not live exchange data.
- **FBref scraping**: FBref has anti-bot measures and rate limits. Use `soccerdata` library which handles session management, or pull CSVs during off-peak hours with delays. The `soccerdata` FBref adapter is the reliable path.
- **License compliance matters for publication**: StatsBomb requires attribution + logo; Sackmann is CC BY-NC-SA; Retrosheet allows research use but prohibits redistribution of raw files. All compatible with building + publishing models/results; NOT compatible with selling the raw data.

---

## Sources

- [The Odds API V4 Documentation](https://the-odds-api.com/liveapi/guides/v4/)
- [Odds API Pricing 2026 Comparison (OddsPapi Blog)](https://oddspapi.io/blog/odds-api-pricing-2026-comparison/)
- [nba_api GitHub (swar)](https://github.com/swar/nba_api)
- [nba_api PlayByPlay Notebook](https://github.com/swar/nba_api/blob/master/docs/examples/PlayByPlay.ipynb)
- [nba-on-court package (shufinskiy)](https://github.com/shufinskiy/nba-on-court)
- [StatsBomb Open Data GitHub](https://github.com/statsbomb/open-data)
- [StatsBomb American Football Open Data](https://github.com/statsbomb/amf-open-data)
- [Jeff Sackmann tennis_atp GitHub](https://github.com/JeffSackmann/tennis_atp)
- [Jeff Sackmann tennis_wta GitHub](https://github.com/JeffSackmann/tennis_wta)
- [Jeff Sackmann tennis_MatchChartingProject](https://github.com/JeffSackmann/tennis_MatchChartingProject)
- [Jeff Sackmann tennis_pointbypoint](https://github.com/JeffSackmann/tennis_pointbypoint)
- [MLB-StatsAPI Python Package (toddrob99)](https://github.com/toddrob99/MLB-StatsAPI)
- [MLB-StatsAPI Endpoints Wiki](https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints)
- [Retrosheet Fall 2025 Release](https://www.retrosheet.org/fall2025release.html)
- [Retrosheet Game Data](https://retrosheet.org/game.htm)
- [SABR: Retrosheet Fall 2025 Announcement](https://sabr.org/latest/retrosheet-announces-fall-2025-updates/)
- [Pinnacle API 2026 Overview (sportsapis.dev)](https://sportsapis.dev/pinnacle-api)
- [SharpAPI Pinnacle Odds API](https://sharpapi.io/sportsbooks/pinnacle-odds-api)
- [BettingIsCool Historical Odds API](https://api.bettingiscool.com/)
- [Free Football Data Guide (SportsCampus)](https://english-programs.sportsdatacampus.com/free-football-data-websites/)
- [Where to Get Free Football Data (McKay Johns Substack)](https://mckayjohns.substack.com/p/where-to-get-free-football-data)
