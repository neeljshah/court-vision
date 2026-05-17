# Dashboard Specification — Bloomberg Terminal for Sports Betting

*Design specification for the real-time monitoring interface.*

---

## Design Philosophy

No existing tool (OddsJam, Unabated, Pikkit, Betstamp) combines:
- Custom model signals with CV-derived features
- Portfolio-level risk management (real-time correlation, not just position tracking)
- Bet tracking with CLV (not just P&L)
- Account health monitoring across multiple books
- System health monitoring with data freshness alerts

The goal: an integrated quant betting terminal. Dense information, no wasted space, sub-second updates for live odds. Think Bloomberg terminal — not a betting app.

---

## Tech Stack

| Layer | Tool | Reason |
|-------|------|--------|
| Frontend | Next.js + React | SSR + client-side; existing skills |
| Charting | TradingView Lightweight Charts + Recharts | Financial-grade time series + custom |
| Real-time | WebSocket (Socket.IO) | Sub-second odds updates |
| State management | Zustand or Jotai | High-frequency updates without React storms |
| Tables | TanStack Table + virtualization | Dense grids, 1000+ rows without janking |
| Backend | FastAPI (already built) | WebSocket + REST in one |
| Event bus | Redis Pub/Sub | Fan out odds updates to all connected clients |
| Ops monitoring | Grafana | System health, model latency, data freshness |

**Latency targets:**
- Pre-game opportunity feed: sub-5s from data change to screen
- Live odds stream: sub-1s cell update

---

## Panel Specifications

### Panel 1: Live Opportunity Feed (Primary View)

Real-time ranked list of +EV bets across all books.

**Columns:**
| Column | Description |
|--------|-------------|
| Player | Name + team |
| Prop | Stat type + threshold (e.g., PTS O27.5) |
| Book | Venue name |
| Your Prob | Model's devigged probability |
| Book Implied | No-vig probability from current line |
| Edge % | Your prob − book implied |
| Size | Recommended Kelly-fractional bet amount |
| CI | 90% confidence interval on edge estimate |
| Confidence | High/Medium/Low based on model uncertainty |

**Color coding:** Green = high confidence edge; Yellow = moderate; Gray = at threshold; Red = do not bet (edge below filter).

**Behavior:** Auto-refreshes every 30–60 seconds. Click any row → drill-down to Player Distribution View for that market.

**Filter controls:** Minimum edge %, book selector, prop type filter, confidence tier filter.

---

### Panel 2: Odds Stream

WebSocket-fed table showing current odds across all books for tonight's games.

**Layout:** Games as row groups; props as sub-rows; books as columns. Cell = current line + implied probability.

**Cell-level color flash:**
- Green flash: line moved in your favor vs model (better value now)
- Red flash: moved against (book correcting toward model)
- Yellow highlight: book lagging the market by > 0.5 points (potential steam window)

**Steam detection:** If 3+ books move same direction within 60 seconds, row highlights with steam indicator.

---

### Panel 3: Edge Heatmap

Games × Prop Types matrix.

- Cell color = edge magnitude at best available book (blue = high, white = neutral, red = against)
- Click cell → see book-by-book comparison modal
- Quickly identify which games and prop types have tonight's best concentrations
- Size of cell = volume / number of lines available

---

### Panel 4: Player Distribution View

For a selected player × prop combination:

**Violin plot:** Model distribution (y-axis = probability density) with:
- Mainline threshold marked with horizontal line
- Alternate thresholds (±4, ±8 from mainline) shown as additional lines
- Book's implied probability at each threshold overlaid as points
- Color shading: regions where model > book (green) vs book > model (red)

**Below the violin:**
- Historical calibration: how accurate have predictions been for this player × prop type?
- Recent game actuals (last 5) vs model predicted vs book line
- Confidence interval: 80% and 95% CI on this prediction

---

### Panel 5: Portfolio View

All active (unsettled) bets shown as positions.

**Correlation heatmap:**
- All active bets as axes
- Cell color = pairwise correlation (estimated from prop residuals)
- Identifies clusters of correlated bets (e.g., all point-guard scoring props in the same game)

**Directional exposure:**
- If all overs hit: total P&L projection
- If all unders hit: total P&L projection
- Shows net directional bias in the portfolio

**Current metrics:**
- Total at-risk capital (sum of all bet amounts)
- Portfolio % of bankroll
- Number of correlated clusters
- Largest single-cluster exposure

---

### Panel 6: Bankroll Curve

Cumulative P&L over time.

- Main line: portfolio value vs time
- Drawdown shading: red background when below prior peak
- Kelly fraction line: secondary y-axis showing current k multiplier
- Rolling Sharpe annotation: 30-day trailing
- Per-market type breakdown: toggle lines for pts, reb, ast, fg3m, etc.
- Markers: when circuit breakers triggered; when model retrained; when accounts limited

---

### Panel 7: Book Health Dashboard

Per-book cards showing:

| Metric | Display | Alert threshold |
|--------|---------|----------------|
| Bet count | Progress bar vs ~300 limit | Warn at 250 |
| Win rate | Rolling 50-bet % | Warn > 55% |
| Heat score | 0–1 gauge | Yellow > 0.4, Red > 0.7 |
| Days since opened | — | Context only |
| Estimated days remaining | Based on current velocity | Alert if < 30 days |
| Last bet | Timestamp | Alert if > 48 hours (confirms account is active) |

**Traffic light:** Green (healthy) / Yellow (watch) / Red (approaching limit).

**Auto-limit confirmation:** When a book downsizes an accepted bet, confirm account is being limited and update heat score accordingly.

---

### Panel 8: CLV Tracker

**Rolling CLV by time window:**
- 7-day, 30-day, 90-day, full history
- Plotted as time series — should show positive trend if edge is real

**By market type breakdown:**
- Which prop types have best CLV (size up there)
- Which have worst CLV (reduce or stop)

**CLV vs ROI comparison:**
- If CLV positive but ROI negative: variance → run more volume
- If both negative: model problem → investigate

**Edge decay alert:** If 30-day CLV drops below 5-day trailing CLV by > 10 bps: flag edge decay. This is the signal to check feature importance drift.

---

### Panel 9: Model Performance

- Feature importance by prop type: which features drive each model's predictions
- Calibration curves: predicted probability vs empirical frequency (reliability diagrams)
- R² by prop type over time: track model improvement
- Residual distributions: are errors systematic or random?
- Model version history: when each model was last retrained and on how many games

---

### Panel 10: System Health

**Data freshness:** Last successful pull from each API/source. Alert if any is stale > expected refresh interval.

| Source | Expected freshness | Alert if stale |
|--------|-------------------|----------------|
| Odds API | 60 seconds | > 3 minutes |
| NBA injury reports | Daily at 1pm/5pm | > 1 hour post-expected |
| Referee assignments | Daily at 9am | > 30 min post-expected |
| CV tracking data | Per game (next day) | If prior game missing > 24hr |

**Model latency:** Time from lineup announcement to updated distributions available. Target: < 60 seconds.

**Execution status:** Last successful bet placement per book. Last error per book. Queue depth (pending bets awaiting placement).

**Error log:** Last 24 hours. Filterable by severity and component.

---

## Layout

Primary layout (widescreen):
```
┌──────────────────────────────┬──────────────────────────────────────┐
│   Live Opportunity Feed      │   Odds Stream                        │
│   (scrollable ranked list)   │   (multi-book real-time)             │
├──────────────┬───────────────┼─────────────────────────────────────┤
│ Edge Heatmap │ Distribution  │   Portfolio View                     │
│              │ View          │   (active positions + correlation)   │
├──────────────┴───────────────┼─────────────────────────────────────┤
│   Book Health (cards)        │   CLV Tracker    │   Bankroll Curve  │
├──────────────────────────────┴──────────────────┴───────────────────┤
│   Model Performance                │   System Health                │
└─────────────────────────────────────────────────────────────────────┘
```

Mobile: panels stack vertically with tab navigation. Opportunity Feed as default view.

---

*See [system-overview.md](system-overview.md) for how data flows into the dashboard. See [execution-engine.md](execution-engine.md) for the book router the dashboard monitors.*
