# Frontend Overview

Description of the web application interfaces for the NBA AI system.

There are two layers here: the **shipped decision-support panel** (a real React +
shadcn/ui app that reads the canonical Auto-API) and the **planned analytics /
chat surfaces** (the broader vision below). The shipped layer is documented first,
because it is the one that actually exists and runs today.

> Backing API contracts: [`docs/API.md`](API.md) — especially the **Predict-service
> Auto-API (port 8099)** section and the no-`$` honesty contract.

---

## Shipped surface — the decision-support panel (React + shadcn/ui)

A small, self-contained React app under
`scripts/platformkit/frontend/web/` (Vite + TypeScript + Tailwind + shadcn/ui),
served as static assets. It reads a Python FastAPI service and **never recomputes
predictions client-side** — every number on screen comes from the real predictor or
is shown as `unavailable`. There is **no `$` / P&L / ROI field** in any payload it
consumes (the contract forbids it; see [`docs/API.md`](API.md)).

### What reads which API

The panel can be served by either of two co-designed FastAPI apps:

| Server | Port | Endpoints the panel calls |
|---|---|---|
| `predict_service.app` (canonical Auto-API) | 8099 | `/api/sports`, `/api/predict/{sport}`, `/api/report/{sport}[/{game_id}]`, `/api/v1/edges/*`, `/api/v1/bestbets/*`, `/api/paper/*`, `/api/stream/*` |
| `scripts.platformkit.frontend.serve` (legacy, store-preferring) | 8098 | `/health`, `/api/slate`, `/api/live`, `/api/props`, `/api/game`, `/api/clv`, `/api/intent` |

Both read the **same canonical store** (`predict_service/store.py`). The legacy
`serve.py` explicitly *prefers* `predict_service.store.read_latest` and only falls
back to a live recompute on a cache miss — so the two surfaces never disagree.

### Read precedence (never dark-screen, never fabricate)

`/api/slate` and `/api/live` resolve through a transparent fall-through chain; each
miss falls through to the next source, and the final source is always real or an
explicit `unavailable`:

```
/api/slate :  predict_service.store (canonical)  ->  snapshot_writer (legacy)  ->  live compute
/api/live  :  M6 ingame spine snapshot           ->  snapshot_writer "live"    ->  keyless ESPN live_board
```

Every payload is stamped with `served_from` (`predict_service_store` / `snapshot` /
`live_compute`) and a `freshness` block (`as_of` + `source`) so the UI can show the
user exactly how fresh the number is and where it came from.

### SSE + 30s poll fallback

Real-time updates use the **SSE-with-poll-fallback** pattern:

- **SSE (preferred):** `GET /api/stream/game/{sport}/{game_id}` and
  `GET /api/stream/paper` push events whose bodies are *byte-identical* to the REST
  endpoints (no new data, no new claims). Heartbeats keep idle proxies open.
- **Poll (fallback):** `web/src/lib/useSlate.ts` polls `fetchSlate(sport)` every
  `POLL_MS = 30_000` (30s) when auto-poll is on. The hook exposes
  `{ data, loading, error, lastUpdated, reload }` so the UI always shows last-updated
  state and never blocks on a failed fetch.

### Honest typing on the client

`web/src/lib/api.ts` mirrors the server contract exactly and bakes the disclaimers
into the type comments:

- `SlateRow.edge` is documented as `model P(home) - market-implied P(home)` —
  *decision support only*.
- `arb_pct` is labelled an **execution** edge (line-shopping/arb), explicitly **NOT**
  a model money edge.
- `BetRow.ev_pct` is `percent vs the best AVAILABLE price` — explicitly **NOT vs the
  close**; a `null` `best_price`/`ev_pct` means "model view only".
- Every field is `T | null`: a missing value is `null`, never a guessed number.
- `Verdict` is a closed union (`MATCH` / `BEHIND` / `AHEAD` / `CALIBRATED` /
  `UNAVAILABLE` / `UNKNOWN`) — surfaced as a `VerdictBadge`, no profit language.
- `postIntent()` logs a **non-binding** "I placed this" record to a local JSONL and
  returns a note that no real bet was placed; there is no sportsbook connection.
  Server-side, `log_intent()` hard-stamps `executed = false` and
  `channel = "manual_human"`.

### Component map (shadcn/ui)

```
web/src/
  App.tsx                         top-level screen router + sport selector (World Cup first)
  lib/
    api.ts                        typed client + SlateRow/BetRow/GameBoard types (no $ field)
    useSlate.ts                   30s poll hook (SSE-fallback)
    format.ts / utils.ts          display helpers
  components/
    board/                        BoardScreen table: BoardControls, BoardTable, useSort,
                                  VerdictBadge, HonestBanner, RowActions
    game/                         GameDetail drill-down: BestBetCard, BetRowsTable, betFormat
    screens/                      BoardScreen, PlaceholderScreen
    ui/                           shadcn/ui primitives (badge, button, card, collapsible,
                                  dialog, input, select, table, tabs)
```

`HonestBanner` renders the `honest_note` from the API on every board so the
"calibration not profit / no `$` edge" disclaimer is always on screen.

---

## Planned surfaces (vision)

The broader vision is three surfaces — a **Betting Dashboard**, an **Analytics
Dashboard**, and an **AI Chat interface** — built with React and D3 / Recharts for
court visualizations. These extend the shipped panel above; they are aspirational
where not yet built.

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

## Technical Stack

**Shipped panel (real today):**

| Component | Technology |
|---|---|
| Framework | React + Vite + TypeScript |
| UI kit | Tailwind CSS + shadcn/ui (`web/src/components/ui`) |
| State / data fetching | Plain hooks (`useSlate`, 30s poll) + `fetch` |
| API layer | FastAPI (`predict_service.app` :8099 / `frontend.serve` :8098) |
| Real-time updates | SSE (`/api/stream/*`) with 30s poll fallback |
| Canonical store | Atomic `latest.json` + append-only `history.jsonl` (file-based) |

**Planned extensions (vision):**

| Component | Technology |
|---|---|
| Court visualizations | D3.js, Recharts |
| AI Chat | Claude API with tool use |
| Database | PostgreSQL (currently file/SQLite-backed) |

---

*Related: [`docs/API.md`](API.md) · [`docs/architecture/dashboard-spec.md`](architecture/dashboard-spec.md) · [`docs/CV_TRACKING.md`](CV_TRACKING.md) · [`docs/INDEX.md`](INDEX.md)*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
