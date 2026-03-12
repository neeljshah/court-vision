# Frontend Overview

Description of the planned web application interfaces for the NBA AI system.

The frontend consists of three main surfaces: a **Betting Dashboard**, an **Analytics Dashboard**, and an **AI Chat interface**. Built with React + Next.js and D3 / Recharts for court visualizations.

---

## Betting Dashboard

The primary interface for identifying model edges vs sportsbook lines.

**Components:**
- Today's games list with pre-game win probabilities and projected margins
- Side-by-side view: model probability vs sportsbook implied probability
- Edge score per bet (model edge = model probability − implied probability)
- Best bets panel — automatically surfaces highest-edge opportunities
- Player props table: projected vs posted line, edge, recommended position
- Historical model accuracy tracker: model win rate vs closing line

---

## Analytics Dashboard

Full game analytics viewer, available for any processed game.

### Game Overview Panel
- Final score, quarter-by-quarter scoring, pace, efficiency ratings
- Win probability chart over game time (updated per possession)
- Momentum chart: scoring run visualization, lead change markers

### Court Visualizations
- Player movement trails for any time range (animated or static)
- Heatmaps: player time-on-court density by zone
- Shot charts: makes and misses plotted on 2D court, colored by efficiency
- Team spacing map: convex hull area over time

### Possession Timeline
- Scrollable play-by-play with possession type and outcome
- Filter by play type: isolation, pick-and-roll, transition, etc.
- Possession value score per play
- Shot clock usage distribution

### Shot Analysis
- Shot chart per player or team, filterable by zone and shot type
- Expected FG% (xFG) vs actual FG% by zone
- Defender distance distribution on made vs missed shots
- Shot quality score histogram

### Lineup Analysis
- Minutes and net rating for every 5-man lineup used
- On/off splits per player
- Best and worst lineups by net rating
- Lineup spacing score (average floor coverage)

### Defensive Metrics
- Defensive coverage heatmap by opponent shot zone
- Rotation event log: who rotated, how fast, outcome
- Help defense proximity by game phase

---

## Player Tracking Visualizations

Dedicated view for spatial tracking data.

**Components:**
- Animated frame-by-frame player movement on 2D court (scrubber control)
- Speed and acceleration chart over time per player
- Ball movement path overlay
- Team spacing area (convex hull) animated over possession
- Distance covered per player (full game or by stint)

---

## AI Chat Interface

Claude-powered assistant with tool access to all model outputs and analytics.

**Capabilities:**
- Answer natural language questions about any game, player, or team
- Pull live predictions, stats, and tracking summaries on demand
- Generate custom charts or comparisons from conversational input
- Explain model predictions ("Why does the model favor the Celtics tonight?")
- Surface betting edges on request ("Which props look valuable tonight?")

**Example queries:**
- "How has Curry's shot quality changed in the last 10 games?"
- "Show me the Nuggets' best lineups against zone defense"
- "What's the model's win probability for tonight's Lakers game?"
- "Which player props have the most model edge tonight?"

---

## Technical Stack (Planned)

| Component | Technology |
|---|---|
| Framework | React + Next.js |
| Court visualizations | D3.js, Recharts |
| State management | React Query (server state) |
| API layer | FastAPI (Python backend) |
| Real-time updates | WebSocket (live win probability) |
| AI Chat | Claude API with tool use |
| Database | PostgreSQL |
