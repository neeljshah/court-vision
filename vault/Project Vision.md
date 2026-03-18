# Project Vision — NBA AI Analytics & Prediction System
> **Goal: Build the world's best NBA analytics and prediction system.**
> Last updated: 2026-03-17

---

## What We Are Building

A self-improving NBA prediction platform that combines computer vision player tracking, exhaustive NBA API data, betting market intelligence, and external context into 90 ML models — simulating every game 10,000 times to produce accurate stat distributions for every player and surface +EV betting edges automatically.

**The moat:** Spatial CV data from broadcast video (defender distance, spacing, fatigue, play type) that no public tool has for free. Second Spectrum charges NBA teams $1M+/year for equivalent data. The system gets better with every game processed.

---

## Three End Products

### 1. Betting Dashboard
- Live sportsbook lines via The Odds API + DraftKings/FanDuel props
- Sharp money signal from Action Network + Pinnacle line movement
- Model predictions vs every market → edge sorted by EV
- Star rating (1-3★) based on edge magnitude + sharp confirmation
- Kelly-sized allocation: fractional Kelly, bankroll %, correlated leg adjustment
- CLV tracking: did your bet beat the closing line? (primary ROI metric)
- Injury reaction alerts: 30-60 min window when props lag book adjustment
- Same-game parlay optimizer: correlation-adjusted true probability

### 2. Analytics Dashboard
- Shot charts: D3 hexbin colored by xFG%, hover for zone stats
- Win probability waterfall: possession-by-possession timeline
- Team spacing over time: convex hull area per possession
- Shot quality by zone: xFG v2 vs actual eFG% (shooting luck indicator)
- Lineup matrix: 5-man net rating grid, best/worst matchups
- Defensive pressure heatmap: court zones colored by pressure differential
- Ball movement network: pass map, touch distribution
- Fatigue chart: player efficiency vs minutes + distance run
- Regression candidates: players shooting above/below xFG (due to mean-revert)
- 96 total analytics metrics across player / team / lineup / game / predictive

### 3. AI Chat Interface
- Claude API (claude-sonnet-4-6) + 10 tools + render_chart → inline charts
- Context: today's games + live injuries + current lines in system prompt
- Example queries:
  - "What's my edge on Murray over 22.5 tonight?" → full prediction pipeline
  - "Show me Jokic's shot quality vs last season" → shot chart comparison
  - "Who's most due for shooting regression this week?" → ranked list + scatter
  - "Best DFS lineup tonight?" → correlation-optimized lineup
  - "Break down Nuggets vs Lakers tonight" → simulation + lineup matrix
  - "What's my optimal $500 allocation tonight?" → Kelly-sized edge list

---

## Complete Data Architecture

### What the System Collects

**CV Tracker (broadcast video):**
- Player 2D positions, speed, acceleration every frame
- Team classification, jersey numbers, player identity
- Ball position, possession, events (shot/pass/dribble)
- Spacing index, paint density, defensive alignment
- Play type, possession type, screen detection
- Shot arc, ball trajectory, contest angle
- Player fatigue (speed vs baseline), movement asymmetry
- Crowd noise level, announcer keyword events

**NBA API (nba_api — free, comprehensive):**
- 221,866 shot chart coordinates (3 seasons)
- 568/569 player gamelogs + advanced stats
- 3,100+ play-by-play games
- 30 teams × 3 seasons advanced stats
- Hustle stats, player tracking (speed/distance/touches)
- Matchup data (who guards whom, pts allowed)
- Synergy play types (pts/possession by play type)
- Clutch splits, on/off splits, lineup data

**Basketball Reference (free, scraped):**
- BPM / VORP / Win Shares historical
- Historical injuries, coaching records
- Contract/salary data, transactions
- Historical Vegas lines for CLV backtesting
- Draft history + college stats

**Betting Markets (free):**
- The Odds API: live lines (spread/total/ML/props)
- Action Network: public bet% and money%
- OddsPortal: historical closing lines 15 years
- Pinnacle: sharpest opening lines
- DraftKings/FanDuel: current props

**News/Injury (free):**
- ESPN injury API (already integrated)
- NBA official injury report PDF (5pm ET daily)
- RotoWire RSS feed
- Reddit r/nba (praw package)
- Twitter beat reporters

**Context (free):**
- Schedule context: rest, B2B, travel distance, timezone
- Referee tendencies: pace, foul rate, home win%
- Arena altitude, player contracts, team transactions

---

## The 90-Model Stack

### By Tier

| Tier | Models | Data Requirement | Status |
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
| 8B | 4 | NLP data (Reddit/Twitter) | 🔲 Phase 9 |
| 9 | 6 | Live data feed | 🔲 Phase 11 |
| 10 | 7 | 200 CV full games | 🔲 Phase 12/16 |

See [[Complete Model Catalog]] for full detail on all 90 models.

### The 7-Model Possession Chain (Core Engine)
Every game simulated 10,000 times via:
1. Play Type Selector → what kind of possession is this?
2. Shot Selector → who shoots from where?
3. xFG Model → P(make) given shooter + location + defender
4. Turnover/Foul Model → does it end in a TO or foul instead?
5. Rebound Model → who gets the board if missed?
6. Fatigue Model → efficiency decay multiplier
7. Substitution Model → does coach sub based on foul/fatigue/score?

---

## The Self-Improving Loop

```
New game available (video + game-id)
    ↓
CV tracker: positions + spacing + events + play types
    ↓
NBA API enrichment: shot outcomes + possession results + box scores
    ↓
PostgreSQL: all data stored, versioned by tracker_version + date
    ↓
Auto-retrain: triggered at 20/50/100/200 game milestones
    ↓
Simulator improves → predictions more accurate
    ↓
Outcome tracked: CLV (beat closing line?) = primary success metric
    ↓
Feedback into confidence calibration → better bet sizing
    ↓
Loop → next game → repeat
```

---

## Competitive Edge

**vs Casual bettors:** Categorical. No contest.
**vs Public analytics tools:** Significant. CV spatial data + Monte Carlo sim they don't have.
**vs Sportsbooks on major lines:** Minimal. Books are efficient here. Don't fight it.
**vs Sportsbooks on role player props:** Real. Books price lazily, your model has better inputs.
**vs Sharp syndicates:** Not there yet. But you don't need to beat them — just beat the closing line by 2-3% consistently on secondary markets.

**Your specific edges:**
1. Role player props — spatial data books don't have
2. Injury reaction window — 15-60 min after news breaks
3. Same-game parlay correlation — books use independence assumption
4. Back-to-back fatigue props — player-specific curves vs aggregate
5. Live props — simulator updates faster than books adjust
6. DFS — projection quality vs free tools is significant

---

## Roadmap Overview

| Phase | Goal | Status |
|---|---|---|
| 1 | Data infrastructure | ✅ |
| 2 | CV tracker bug fixes | ✅ |
| 2.5 | CV quality upgrades | 🟡 |
| 3 | NBA API data maximization | ✅ |
| 3.5 | Expanded data: BBRef + untapped nba_api + news | 🔲 |
| 4 | Tier 1 ML models | ✅ |
| 4.5 | Betting market models + lifecycle models | 🔲 |
| 5 | External factors | ✅ |
| 6 | 20 full games + PostgreSQL | 🔲 |
| 7 | Tier 2-3 spatial models | 🔲 |
| 8 | Possession simulator v1 | 🔲 |
| 9 | Feedback loop + NLP models | 🔲 |
| 10 | Tier 4-5 volume models | 🔲 |
| 11 | Betting infrastructure + live models | 🔲 |
| 12 | Full Monte Carlo (all 90 models) | 🔲 |
| 13 | FastAPI backend | 🔲 |
| 14 | Analytics dashboard | 🔲 |
| 15 | AI chat interface | 🔲 |
| 16 | Live win prob LSTM | 🔲 |
| 17 | Infrastructure | 🔲 |

See `.planning/ROADMAP.md` for full phase detail.

---

## Related Documents
- [[Complete Data Sources]] — every data source, priority, how to pull
- [[Complete Model Catalog]] — all 90 models with inputs, targets, status
- [[Prediction Pipeline]] — the master prediction formula end-to-end
- [[System Architecture]] — technical pipeline wiring
- [[Tracker Improvements Log]] — CV data quality progress
- [[Key Metrics]] — 96 analytics metrics catalog
