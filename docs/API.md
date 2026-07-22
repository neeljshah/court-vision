# API Reference — CourtVision

> FastAPI backend serving the full prediction, analytics, and dashboard surface.
> For the model layer backing these endpoints see [`docs/ML_MODELS.md`](ML_MODELS.md).
> For system architecture see [`ARCHITECTURE.md`](../ARCHITECTURE.md).
> For the frontend surfaces that consume these endpoints see
> [`docs/FRONTEND_OVERVIEW.md`](FRONTEND_OVERVIEW.md).

There are **two API surfaces** in this repo, by design:

| Surface | Entry | Port | Role |
|---|---|---|---|
| **Predict-service Auto-API** | `predict_service.app:app` | 8099 | The canonical, multi-sport, read-mostly decision-support API. Serves **one canonical snapshot per sport** out of an atomic store. Honest-by-construction: no `$` field anywhere. **Documented first below.** |
| Legacy CourtVision FastAPI | `api.main:app` / `api.live_v2_app:app` | 8000 | The original ~99-endpoint NBA research/dashboard surface (simulation, props, de-vig, CLV pages, risk). Documented from [Router Map](#router-map) down. |

---

## Predict-service Auto-API (port 8099) — the canonical surface

**Module:** `predict_service/app.py` (`predict_service.app:app`). Run:
`python -m predict_service.app` (port via `PREDICT_SERVICE_PORT`, default `8099`).

This is the single source of truth the React panel and the paper-trading engine
both read. It consolidates and supersedes the M1 stopgap `frontend/serve.py`. Every
read goes through `predict_service.store` (the one canonical store); every response
field is **real or the explicit `unavailable` sentinel** — never fabricated.

### The honest contract (binding, enforced by shape)

The wire schema lives in `predict_service/contracts.py` (`SCHEMA_VERSION = "1.2.0"`).
Its dataclasses make the honesty rails structural, not a convention:

- **No `$` / `roi` / `pnl` / `profit` / `bankroll` / `stake_dollars` field exists
  anywhere** in `MarketRow`, `EdgeRow`, `PredictionRecord`, or `SnapshotEnvelope`.
  An `EdgeRow` carries `model_prob`, `market_prob`, and `ev` (a pure probability-space
  ratio, *not* a dollar amount) — and that is all the money-adjacent data there is.
- `edge_claimed` is stamped **`false`** on the deep edge/bestbets views. Markets are
  efficient; this is calibrated decision-support, not a profit claim.
- CLV ("better-number-than-close") is the only honest yardstick and is computed
  downstream by the vetted `scripts.platformkit.clv_ledger` — never reimplemented
  or stored here as a money edge. Proxy closes are surfaced as `clv_is_proxy=true`,
  never hidden.
- Every envelope carries an `honest_note` string repeating the above.
- Stake *sizing* (flat unit + quarter-Kelly **units**) is recorded later by the paper
  engine, in units only; the snapshot only carries what the engine needs to size.

### Canonical store + the `unavailable` sentinel

**Module:** `predict_service/store.py`. One writer, many readers, under
`data/frontend/predict_service/<sport>/`:

| Artifact | Write discipline | Purpose |
|---|---|---|
| `latest.json` | **Atomic** (`tmp` file → `fsync` → `os.replace`) | Current snapshot. A concurrent reader sees either the OLD file or the COMPLETE new one — never a torn read. |
| `history.jsonl` | **Append-only** (one line per save, never overwritten) | The immutable record of what was predicted. |

`read_latest(sport)` **NEVER raises and NEVER returns a partial object.** A missing,
empty, truncated, corrupt, or malformed-shape file all degrade to the
`status="unavailable"` sentinel envelope (`SnapshotEnvelope.unavailable(...)`).
A reader can therefore always trust the result is *either* a complete `"ok"` snapshot
*or* an explicit `"unavailable"` one. `data/` is gitignored — this is a local cache,
never committed.

```
  predict_service.produce  ──(atomic save)──▶  data/frontend/predict_service/<sport>/
                                                  ├─ latest.json   (atomic, 1 writer)
                                                  └─ history.jsonl (append-only)
                                                          │
                  ┌───────────────────────────────────────┼───────────────────────────┐
                  ▼                                         ▼                           ▼
        predict_service.app                       scripts/.../frontend/serve   paper-trading engine
        (Auto-API :8099, read-only)               (legacy :8098, prefers store)  (reads same store)
```

### SnapshotEnvelope shape

```jsonc
{
  "schema_version": "1.2.0",
  "sport": "nba",
  "generated_at": "2026-06-18T00:00:00+00:00",  // ISO-8601 UTC
  "status": "ok",                                 // or "unavailable"
  "predictions": [ /* PredictionRecord */ ],
  "markets":     [ /* MarketRow */ ],
  "edges":       [ /* EdgeRow (NO $ field) */ ],
  "honest_note": "Calibrated decision-support only. Markets are efficient; no $ edge...",
  "note": ""
}
```

| Dataclass | Key fields (no `$` anywhere) |
|---|---|
| `PredictionRecord` | `sport, game_id, home, away, tipoff, pregame_probs{}, markets[], leak_guard{in_sample}, produced_at, note` |
| `MarketRow` | `sport, game_id, market_type(moneyline/spread/total), side, line, odds(decimal), book, devigged_prob, captured_at, is_close, clv_is_proxy` |
| `EdgeRow` | `game_id, market_type, side, model_prob, market_prob, ev, tier(A/B/C\|null), book, line, clv_is_proxy` |

`leak_guard.in_sample` flags an honest in-sample prediction so it is never mistaken
for OOS. `tier` is an evidence label, not a money figure.

### Endpoints

| Method · Path | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` — liveness only. |
| `GET /api/sports` | `{status, active:[<sport>...], capabilities:{<sport>:{has_predictor, markets[], produce, note}}, honest_note}`. `active` is the sports whose predictor built on **this** machine (a fresh clone with no corpus returns `[]` — never crashes). |
| `GET /api/predict/{sport}` | `store.read_latest(sport).to_dict()` verbatim — the full `SnapshotEnvelope`, including the `status="unavailable"` sentinel as-is. |
| `GET /api/predict/{sport}/{game_id}` | The single `PredictionRecord` for `game_id` plus its `markets`/`edges`, or the `unavailable` sentinel when the snapshot or game is missing. |

Known sports (from `predict_service/registry.py`): `nba`, `mlb`, `soccer`,
`soccer_intl` (World Cup), `tennis`. Each entry declares its market catalog and an
honest one-line note (every note ends `; no $ edge`). The registry delegates to the
guarded/cached `scripts.platformkit.predictor_jd._build_predictor`, so a sport whose
parquets are absent simply drops out of `active`.

### Mounted routers (all guarded — a boot failure degrades to a 503 sentinel)

Every `include_router` in `app.py` is wrapped in `try/except`: if a router module
fails to import, its paths are replaced with a degraded **503 `status:"unavailable"`**
stub (carrying `edge_claimed:false`) so the rest of the API still boots. A bad module
can never silently 404 or sink the service.

| Mounted paths | Module | Purpose |
|---|---|---|
| `GET /api/v1/edges/{sport}[/{game_id}]` | `frontend/edge_routes.py` → `edge_api.py` | Deep lines-vs-predictions comparison over the store. **ETag / `If-None-Match` → 304** on an unchanged snapshot (cache key = `generated_at`). `edge_claimed:false`; `edge = model_prob - market_prob` (probability space). |
| `GET /api/v1/bestbets/{sport}[/{game_id}]` | `frontend/bestbets_routes.py` → `exec_decision.py` | EXECUTION API: edge view (line-shopped, **Shin**-devigged) run through the tier-floor / no-bet / **units-only** decision layer (`flat_unit` + capped quarter-Kelly **units**, never `$`), with the in-game number + CLV beat-scoreboard attached. Below-floor candidates kept as `decision:"no_bet"` for transparency. |
| `GET /api/report/{sport}` | `frontend/report_routes.py` | Light browse list: `{status, game_ids[], count, generated_at, honest_note}` so the React grid enumerates games without downloading the full envelope. |
| `GET /api/report/{sport}/{game_id}` | `frontend/report.py` | Full per-game report: `{pregame, markets[], edges[] (no $), live{}, intel, meta}`. Each optional section (live, intel, freshness) is independently guarded — a miss nulls THAT section only. |
| `GET /api/paper/trail`, `GET /api/paper/clv` | `frontend/paper_routes.py` | Paper-trade trail + CLV summary (units/probability only). |
| `POST /api/paper/place`, `GET /api/paper/open` | `frontend/exec_routes.py` | MANUAL paper execution — `executed` is **always `false`**; no sportsbook connection. |
| `GET /api/stream/game/{sport}/{game_id}`, `GET /api/stream/paper` | `frontend/sse.py` | SSE streams (see [SSE](#sse-predict-service-streams) below). |
| `GET /api/ops/status`, `/api/ops/metrics`, `/api/ops/doctor` | `ops/status_endpoint.py` | Supervised always-on status page; metrics are CLV + liveness, no `$`. |
| `GET /api/improve/status`, `GET /api/parity` | `frontend/status_routes.py` | Self-improve ratchet FSM + cross-sport parity grid; `edge_claimed:false`. |

### SSE (predict-service streams)

**Module:** `frontend/sse.py`. Two `text/event-stream` endpoints whose payloads are
**byte-identical to the corresponding REST bodies** — no new data, no new claims, no
fabricated field. The stream is just periodic re-delivery of the same honest snapshot.

- `GET /api/stream/game/{sport}/{game_id}` — emits `build_report(sport, game_id)` (==
  the `GET /api/report/...` body) immediately, then every `SSE_INTERVAL_SEC` (default 5s).
- `GET /api/stream/paper` — emits the paper trail merged with the CLV summary on the
  same interval.

Both send an initial event with no first-tick delay, emit a `: heartbeat` comment
every `SSE_HEARTBEAT_SEC` (default 15s) to keep proxies from closing idle connections,
and auto-close after `SSE_MAX_DURATION_SEC` (default 3600s; `0` = unlimited). A per-tick
build error emits `{"status":"unavailable", ...}` rather than killing the stream. This
is the SSE half of the **SSE-with-poll-fallback** pattern (the React client polls every
30s when a stream is not used).

---

## Intel Query -- ask() surfaces (offline, VERIFIED-claims CLI)

**Module family:** `scripts/platformkit/intel_query/`. Not an HTTP surface --
a Python CLI/importable layer that answers ONLY from claim rows an independent
validator marked `VERIFIED` (see [`docs/INTELLIGENCE.md`](INTELLIGENCE.md)).
`ask.py`'s `ask(question)` classifies a free-text question via
`families.classify` (keyword/regex, no LLM call inside the module) and routes
to one of several composers. A question no VERIFIED claim covers returns
`{"answerable": False, "reason": ..., "nearest_supported_families": [...]}` --
never a guess.

```bash
python -m scripts.platformkit.intel_query.ask "Who are the top 5 best shooters (composite) in window=last_20?"
python -m scripts.platformkit.intel_query.ask --demo
```

### Shooter trait-profile family -- `compose_profile.py`

`compose_profile(player) -> dict` answers "what kind of shooter is X?" as a
**vector**, never one re-weighted scalar: each of 10 axes (volume /
efficiency / difficulty / gravity / context group) is reported with its own
`value`, `rank`, `pct_pool`, and `pct_qualified` (percentile within the
fg3m>=82 NBA-official qualification subset), each citing its own VERIFIED
claim. Axes are never combined into a score. A `trait_line` (e.g.
`"high-volume, elite-efficiency shooter; self-creation high, gravity elite"`)
is derived only from the declared `BANDS` word thresholds (config data, never
tuned). Fail-closed: a player found on no axis, or a missing qualified-pool
claim, returns `{"status": "UNANSWERABLE", ...}`; a single missing axis is
reported per-axis as `not_in_pool`, never guessed. Routed automatically from
`ask()` via the `shooter_profile` family (`"what kind of shooter is X"` /
`"shooter profile for X"`), or callable directly:

```bash
python -m scripts.platformkit.intel_query.compose_profile "Luka Doncic"
```

### One-conclusion best-X composer -- `compose_best.py`

`compose_best(aspect="shooter") -> dict` answers "who is the best X, all
factors weighed, ONE conclusion" per a `COMPOSITION_RULE` emitted verbatim in
the response so the conclusion is auditable: (0) an optional **domain
filter** (e.g. the NBA's own fg3m>=82 3P%-title qualification minimum,
cited to an external convention, never tuned) restricts the primary pool
before rank-1 selection -- the unfiltered #1 is still reported alongside for
transparency; (1) the **primary axis** is whichever VERIFIED ranking claim
the pre-registered predictive-validity gate verdict currently selects, read
live from the verdict JSON at call time -- never hardcoded, so a gate flip
changes the answer with no code change; (2) **attribution axes** annotate the
primary axis's #1 player with other VERIFIED claims' rank/value for that same
player, never overriding it; (3) **honest disagreement** is surfaced
explicitly whenever an attribution axis's own #1 differs from the primary
axis's #1, with the gate citation explaining why the primary axis still wins.
Fail-closed: a missing primary claim or gate-verdict file returns
`{"status": "UNANSWERABLE", "missing": [...]}`; a missing attribution axis is
annotated `not_verified`, never load-bearing for the conclusion. v1 wires one
aspect (`"shooter"`) -- a new aspect gets its own `_AspectConfig` entry only
when actually asked for.

```bash
python -m scripts.platformkit.intel_query.compose_best shooter
```

### Paper-analytics CLI -- `paper_analytics.py`

Ask-style surface over the live PAPER TRADING ledger (`data/frontend/clv_ledger.jsonl`)
-- a different kind of source than the VERIFIED-claims stores above (fresh-read,
never "validated"). Streams the ledger line-by-line (one malformed line is
skipped, never fatal -- the ledger is large and growing). Every answer carries
`source_files`, `edge_claimed: false`, and a `net_units` figure is never shown
without its channel's fail-closed greenlight status (`RED`/`AMBER`/`GREEN`,
read from `data/frontend/ops/edge_greenlight.json`; a channel the gate has no
verdict for reports `"unknown"`, never GREEN-by-silence).

```bash
python -m scripts.platformkit.intel_query.paper_analytics "this week by channel"
python -m scripts.platformkit.intel_query.paper_analytics "today"
python -m scripts.platformkit.intel_query.paper_analytics "arb lane"
python -m scripts.platformkit.intel_query.paper_analytics "settlement backlog"
```

Full flow (placement -> fill sim -> close capture -> settlement -> grading ->
greenlight gate -> this CLI) is documented in
[`docs/PAPER_TRADING_STACK.md`](PAPER_TRADING_STACK.md).

### The `pairs_for_claim_stores` subset-loading pattern

`ask.load_verified_claims(pairs=None)` re-reads the module-level
`CLAIM_SOURCE_PAIRS` and joins **every** claims store discovered under
`data/cache/intel_claims/`. That is fine for `ask()` itself, but a composer
that only ever needs 3-4 named stores must NOT call it bare: some stores
(bulk player-box rate stores) are GB-scale, and a whole-repo load produced a
live `MemoryError` (2026-07-07). `pairs_for_claim_stores(store_names)` filters
`CLAIM_SOURCE_PAIRS` down to just the claims-file names passed in, then that
subset is handed to `load_verified_claims(pairs=...)`:

```python
from scripts.platformkit.intel_query.ask import load_verified_claims, pairs_for_claim_stores

_PROFILE_STORES = ("nba_shooter_profile_claims.jsonl", "nba_shooting_claims.jsonl", ...)
verified = load_verified_claims(pairs_for_claim_stores(_PROFILE_STORES))
```

Both `compose_profile.py` and `compose_best.py` load through this pattern
exclusively -- any new composer over VERIFIED claims must do the same.

---

## Quick Start

```bash
conda activate basketball_ai
uvicorn api.main:app --reload --port 8000
# Interactive Swagger UI: http://localhost:8000/docs
# ReDoc:                  http://localhost:8000/redoc
```

**Environment:**
- `NBA_OFFLINE=1` (default) — serves stale NBA API cache; prevents stats.nba.com hangs
- `NBA_OFFLINE=0` — enables live NBA API fetches
- `LIVE_V2_AUTH_TOKEN=<token>` — enables auth on risk endpoints (open in local-dev when unset)
- `SENTRY_DSN=<dsn>` — enables Sentry error tracking

**App entry:** `api.main:app` (primary), `api.live_v2_app:app` (cloud/Railway entry with
static assets and Jinja dashboard templates)

---

## Router Map

~99 endpoints across the routers actually mounted in `api/main.py`, counted at runtime from `app.routes`.

| Router module | Mount prefix | Tags | Purpose |
|---|---|---|---|
| `api/main.py` (inline) | `/` | simulation, props, health | Simulation, props, health |
| `api/models_router.py` | `/predictions` | predictions | xFG, win-prob, player EPA |
| `api/predictions_router.py` | `/predictions` | predictions | Full prop stack, injury, breakout, lineup optimizer |
| `api/analytics_router.py` | `/analytics` | analytics | Shot chart, tracking coords, lineup stats |
| `api/stitch_router.py` | `/stitch` | stitch | Stitch surface (mounted; see prefix-doubling note in Known Issues) |
| `api/dashboard_router.py` | `/` | dashboard | AI chat, CLV summary, today's edges |
| `api/devig_router.py` | `/` | devig | Shin + 4 de-vig methods |
| `api/clv_router.py` | `/` | clv | CLV dashboard page + data |
| `api/live_game_router.py` | `/` | live | Per-game live projection panel |
| `api/lines_router.py` | `/` | lines | Multi-book line scanner (guarded import) |
| `api/courtvision_router.py` | `/` | courtvision | CourtVision UI (home, game, tonight, parlays) (guarded import) |
| `api/_risk_router.py` | `/` | risk | Kill switch, drawdown, bankroll (guarded import) |

`api/execution_router.py` exists in the tree but is never imported or mounted in
`api/main.py` — its order-execution stubs are not part of the live router map.

---

## Health

### GET `/health`

Fast liveness check. Always returns 200 if the server is up.

```json
{
  "status": "ok",
  "model_status": {
    "possession_simulator": "loaded",
    "player_props": "available",
    "betting_edge": "loaded",
    "win_probability": "available",
    "tracking": "available",
    "re_id": "available"
  }
}
```

### GET `/health/ops`

Operational pipeline metrics. Reads from `data/models/bet_log.json`,
`data/models/clv_log.json`, `data/models/quarantine_state.json`, and the
`scraper_runs` SQLite table.

```json
{
  "status": "ok",
  "scraper_lag_min": 4.2,
  "model_inference_ms_p95": null,
  "daily_bet_count": 12,
  "clv_hit_rate": 0.543,
  "drift_flags": [],
  "last_slate_duration_min": null,
  "uptime_hours": 3.14
}
```

`scraper_lag_min`: minutes since last successful scrape run (`scraper_runs` table,
`status='done'`). `clv_hit_rate`: fraction of logged bets with positive CLV.
`drift_flags`: model names currently in quarantine.

---

## Simulation

All simulation endpoints use `src/prediction/possession_simulator.py` —
`PossessionSimulator`. Responses are TTL-cached 300s in-process (key = params tuple).

### POST `/simulate`

Monte Carlo game simulation.

**Request:**
```json
{ "team_a": "BOS", "team_b": "MIL", "n_sims": 1000, "player_stats": null }
```

**Response:**
```json
{
  "team_a_win_pct": 0.58,
  "mean_score_a": 112.4,
  "mean_score_b": 108.1,
  "player_distributions": {}
}
```

### POST `/simulate_game`

Full game simulation with optional per-team stat overrides.

**Request:**
```json
{
  "team_a": "BOS",
  "team_b": "MIL",
  "n_sims": 1000,
  "team_a_stats": null,
  "team_b_stats": null
}
```

### POST `/over_prob`

Per-player per-stat over probability from Monte Carlo distribution.

**Request:**
```json
{
  "player_id": "Jayson Tatum",
  "stat": "pts",
  "line": 26.5,
  "team_a": "BOS",
  "team_b": "MIL",
  "roster_a": ["Jayson Tatum", "Jaylen Brown"],
  "roster_b": ["Giannis Antetokounmpo"],
  "n_sims": 1000
}
```

**Response:**
```json
{
  "player_id": "Jayson Tatum",
  "stat": "pts",
  "line": 26.5,
  "over_prob": 0.612,
  "mean": 27.4
}
```

---

## Props

### GET `/props/{player_id}`

7-stat pregame prop projections. Accepts player name or name-based ID string.
Calls `stack_predict()` from `src/prediction/prop_model_stack.py`; falls back to
`predict_props()` from `src/prediction/player_props.py` if the stack returns empty.

**Query params:** `opp_team=GSW` (default), `season=2025-26` (default)

**Response:**
```json
{
  "pts": 27.4,
  "reb": 8.1,
  "ast": 4.8,
  "fg3m": 2.1,
  "stl": 1.1,
  "blk": 0.6,
  "tov": 2.8
}
```

**Honest note:** STL R²=0.18 — do not size aggressively. BLK R²=0.16. The
v2 models (`props_{stat}_v2.json`) are active; v1 files retained as fallback.

### GET `/edge/{game_id}`

Betting edge vs current market line. Uses `BettingEdge` from
`src/prediction/betting_edge.py` (wraps win probability).

**Query params:** `home=BOS`, `away=MIL`, `home_odds=-110`, `away_odds=-110`

**Response:**
```json
{
  "game_id": "0022400512",
  "edges": [
    { "team": "BOS", "edge": 0.043, "ev": 0.031, "kelly_fraction": 0.028 }
  ]
}
```

### GET `/win-prob/{game_id}`

Pregame win probability from `src/prediction/win_probability.py`.

**Query params:** `home=BOS`, `away=MIL`, `season=2025-26`

**Response:**
```json
{
  "game_id": "0022400512",
  "home_win_prob": 0.61,
  "confidence_interval": [0.56, 0.66],
  "model": "xgboost_v2"
}
```

Honest metric: 0.709 accuracy / 0.193 Brier (3-fold walk-forward).
Do not cite the endQ3 Brier 0.1191 — that figure is retracted (Q4 feature leak).

### GET `/lineup/{team}`

Injury-filtered DNP list via `InjuryMonitor` (ESPN + NBA official feeds).

```json
{ "team": "BOS", "dnp": ["Kristaps Porzingis"], "active_count": "unknown" }
```

### POST `/backtest/{stat}`

Prop backtest gate. Cached 24h. `stat` ∈ {pts, reb, ast, fg3m, stl, blk, tov}.

**Request:** `{ "seasons": ["2024-25"], "edge_threshold": 0.04 }`

**Response:**
```json
{
  "stat": "pts",
  "n": 1240,
  "mae": 4.83,
  "hit_rate_over": 0.512,
  "roi_at_break_even_odds": -0.020,
  "passed_gate": false,
  "edge_buckets": {}
}
```

---

## Predictions Router (`/predictions`)

**Module:** `api/predictions_router.py`

### GET `/predictions/props/{player_id}`

Full prop stack by numeric NBA player ID. More complete than root `/props` —
includes DNP probability, injury risk, confidence, suppression flag.

**Query params:** `season=2025-26`, `opp_team=""`

**Response:**
```json
{
  "player_id": 2544,
  "player_name": "LeBron James",
  "props": { "pts": 24.1, "reb": 7.4, "ast": 8.1, "fg3m": 1.8, "stl": 1.2, "blk": 0.6, "tov": 3.1 },
  "dnp_prob": 0.03,
  "injury_risk": 0.12,
  "suppressed": false,
  "suppression_reason": null,
  "confidence": 0.82,
  "edges": { "pts": 0.026, "reb": 0.018 }
}
```

### POST `/predictions/injury-risk`

Injury risk + load management from `data/models/injury_risk.pkl`.

**Request:** `{ "player_id": 2544, "season": "2025-26" }`

**Response:**
```json
{
  "player_id": 2544,
  "player_name": "LeBron James",
  "injury_risk_score": 0.18,
  "risk_level": "Low",
  "load_management_prob": 0.08,
  "games_missed_recent": 2,
  "drivers": { "age": 0.12, "b2b": 0.06 }
}
```

### POST `/predictions/breakout`

Breakout potential score from `data/models/breakout_predictor.pkl`.

**Request:** `{ "player_id": 1629029, "opponent_team": "OKC", "season": "2025-26" }`

**Response:**
```json
{
  "player_id": 1629029,
  "player_name": "Ja Morant",
  "breakout_score": 0.74,
  "predicted_pts_above_avg": 3.2,
  "key_factors": ["usage_trend", "matchup_advantage"],
  "signals": { "usage_trend": 0.82, "matchup_advantage": 0.61 }
}
```

### POST `/predictions/lineup-optimizer`

Greedy DFS optimizer. Requires at least one `game_id` from tonight's slate.

**Request:**
```json
{ "game_ids": ["0022400512"], "budget": 50000.0, "platform": "draftkings" }
```

### POST `/predictions/game`

Full game prediction: win prob + game-level models + player props + Kelly edges.

**Request:**
```json
{
  "home_team": "BOS",
  "away_team": "MIL",
  "season": "2025-26",
  "player_ids": null,
  "lines": null,
  "bankroll": 10000.0,
  "game_date": null
}
```

### GET `/predictions/today`

Win probabilities + top props for tonight's games via NBA scoreboard.

---

## Models Router (`/predictions`)

**Module:** `api/models_router.py`

### GET `/predictions/shot`

xFG probability from spatial features (xFG v1, Brier 0.226, 221K shots).

**Query params:** `defender_dist` (required), `shot_angle` (required),
`fatigue_proxy=0.0`, `court_zone=paint`

**Response:** `{ "probability": 0.487, "model": "xfg_v1", "inputs": {...} }`

### GET `/predictions/win`

In-game win probability from spatial momentum features.

**Query params:** `convex_hull_area` (required), `avg_inter_player_dist=0.0`,
`scoring_run=0`, `possession_streak=0`, `swing_point=0`

**Response:** `{ "win_probability": 0.634 }`

### GET `/predictions/player-impact`

Player EPA per 100 possessions. Returns 503 until 20+ CV games are trained
(Phase 6 requirement).

---

## Analytics Router (`/analytics`)

**Module:** `api/analytics_router.py`

### GET `/analytics/shot-chart`

All shot log records for a game from the `shot_logs` SQLite table.

**Query params:** `game_id` (required)

**Response:**
```json
{
  "game_id": "abc123",
  "shots": [
    {
      "player_id": 1,
      "x": 14.2,
      "y": 8.1,
      "made": true,
      "court_zone": "paint",
      "nearest_defender_dist": 3.1,
      "shot_angle": 45.0,
      "fatigue_proxy": 0.12
    }
  ]
}
```

### GET `/analytics/tracking`

Raw tracking coordinates for a frame range.

**Query params:** `game_id` (required), `frame_start=0`, `frame_end=500`,
`object_type=player`

**Response:**
```json
{
  "game_id": "abc123",
  "frame_range": [0, 500],
  "rows": [
    { "frame_number": 0, "track_id": 1, "x": 24.1, "y": 12.3,
      "vx": 0.4, "vy": -0.1, "direction": 45.0, "object_type": "player" }
  ]
}
```

### GET `/analytics/lineup-stats`

Returns **503** until Phase 6 (requires 20+ full games of CV data).

---

## De-Vig Router

**Module:** `api/devig_router.py`

### POST `/api/devig`

Converts vigged sportsbook odds into fair probabilities.

**Request (2-way market):**
```json
{ "over_odds": -115, "under_odds": -105, "method": "shin" }
```

**Request (n-way market):**
```json
{ "odds": [-110, -110, +250], "method": "proportional" }
```

`method` ∈ `{"shin", "additive", "proportional", "multiplicative", "power"}`
Default: `"shin"` (Shin 1992 insider-trading model, numerically-stable bisection).

**Response:**
```json
{
  "method": "shin",
  "vigged": [0.535, 0.488],
  "fair_probs": [0.523, 0.477],
  "fair_odds": [-109, +109],
  "overround": 0.023
}
```

Implementation: `src/prediction/devig.py` — 7 tests verify Shin output against
published theory. `devig()` is also the internal de-vig used by the Kelly sizer.

---

## Live Game Router

**Module:** `api/live_game_router.py`

### GET `/live/{game_id}`

Per-game live projection panel (HTML page). Read-only — does not poll NBA API or
write to disk.

Surfaces for every player in the game:
- Pregame projection (q50) from `data/cache/predictions_cache_<date>.parquet`
- Current actual (if a live box score is cached)
- Pace-projected final (`current / minutes_played × projected_minutes`)
- Best current sportsbook line (from `api._courtvision_odds.consolidate()`)
- Edge vs line for PTS

Optional quarter-shape decay: set `CV_QSHAPE_DECAY=1` to apply league-average
per-quarter rate factors (Q4 is lower for pts/ast/fg3m).

---

## Lines Router

**Module:** `api/lines_router.py`

### GET `/api/lines/scan`

Multi-book line scanner. Reads consolidated per-book CSVs via
`api._courtvision_odds.consolidate(date)`.

**Query params:** `date=YYYY-MM-DD`, `stat=pts`, `min_books=2`, `sort=edge`

**Response:**
```json
{
  "date": "2026-06-11",
  "rows": [
    {
      "player": "Jayson Tatum",
      "stat": "pts",
      "line": 26.5,
      "best_over_book": "fanduel",
      "best_over_price": -108,
      "best_under_book": "draftkings",
      "best_under_price": -112,
      "best_combined_edge": 0.018,
      "books": [...]
    }
  ]
}
```

`best_combined_edge` = max implied-probability spread across books (larger =
more line-shopping value). Computed via `_american_to_implied` from
`api._courtvision_odds`.

### GET `/scan`

HTML line-scanner dashboard page (rendered from `templates/scan.html`).

---

## CLV Router

**Module:** `api/clv_router.py`

### GET `/clv`

CLV dashboard HTML page. Renders dark-theme dashboard with:
- Headline tiles: P&L, ROI, avg CLV bps, win%, Sharpe
- `by_book` table
- `by_stat` table
- Daily ROI sparkline (reads `data/clv/daily_clv.csv`)

### GET `/api/clv/summary`

Rolling CLV summary (7d, 30d) as JSON.

**Query params:** `days=7`

---

## Risk Router

**Module:** `api/_risk_router.py`
**Auth:** `LIVE_V2_AUTH_TOKEN` env var — query param `?token=` or `cv_session` HttpOnly cookie

### GET `/api/risk/status`

Live risk snapshot from `src/prediction/risk_guards.py`.

```json
{
  "kill_switch_engaged": false,
  "current_drawdown_pct": 2.1,
  "daily_bet_count": 8,
  "bankroll": 10000.0,
  "alerts": []
}
```

Drawdown alerts fire to Slack webhook when drawdown crosses 10% (medium) or 15%
(auto-engages kill switch).

### POST `/api/risk/kill-switch`

Engage or disengage the drawdown kill switch.

**Request:** `{ "engage": true }`

### POST `/api/bankroll/set`

Update bankroll value (auth-gated).

**Request:** `{ "bankroll": 12000.0 }`

---

## Dashboard Router

**Module:** `api/dashboard_router.py`

### POST `/chat`

AI chat backed by Claude + live DB + model tools.

**Request:** `{ "message": "What are the top edges tonight?", "game_id": null }`
**Response:** `{ "response": "..." }`

### GET `/analytics/edges/today`

Ranked betting edges for today's slate.

**Query params:** `min_ev=0.03`

**Response:**
```json
{
  "edges": [
    { "game_id": "...", "stat": "pts", "direction": "over", "ev": 0.045, "kelly": 0.028 }
  ],
  "count": 3
}
```

### GET `/analytics/clv-summary`

Rolling CLV for spread and total (7d, 30d).

---

## CourtVision Router

**Module:** `api/courtvision_router.py`

HTML/JSON surface for the live betting dashboard. All cold-path caches are
pre-warmed on startup (background thread).

| Route | Type | Description |
|-------|------|-------------|
| `GET /` | HTML | Home page |
| `GET /tonight` | HTML | Tonight's slate |
| `GET /game/{game_id}` | HTML | Per-game view |
| `GET /plus_ev` | HTML | +EV opportunities page |
| `GET /api/slate` | JSON | Tonight's props + edges |
| `GET /api/parlays` | JSON | Parlay suggestions |
| `GET /api/plus_ev` | JSON | +EV summary |
| `POST /api/bet/{id}` | JSON | Grade/update a bet |

**Rate limiting:** slowapi, 60 requests/minute per IP when `slowapi` is installed.

---

## WebSocket + SSE

### WebSocket `/ws/live-winprob`

Streams real-time win probability updates during live games.

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/live-winprob");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
// {"game_id": "...", "home_win_prob": 0.63, "period": 3, "clock": "5:42"}
```

### SSE `/sse/live_edges`

Server-sent events stream for cross-book arbitrage opportunities.
Source: `scripts/arb_emitter_daemon.py` + `api._courtvision_odds.cross_book_spread`.

```javascript
const es = new EventSource("/sse/live_edges");
es.onmessage = (e) => console.log(JSON.parse(e.data));
// {"event": "arb.detected", "player": "...", "stat": "pts",
//  "over_book": "fanduel", "under_book": "draftkings", "edge_pp": 0.018}
```

Edges are freshness-gated (stale lines filtered), de-vigged via Shin, and tiered
by implied-prob spread magnitude before emission.

---

## Startup WebSocket Subscribers

The following background WebSocket subscribers start on boot when their env var
is set. Each writes to a separate dated CSV to avoid dual-writer races with HTTP
scrapers.

| Env var | Module | Output file |
|---------|--------|-------------|
| `DK_WS_ENABLED=1` | `scripts/draftkings_ws.py` | `data/lines/<date>_dk_ws.csv` |
| `FD_WS_ENABLED=1` | `scripts/fanduel_ws.py` | `data/lines/<date>_fd_ws.csv` |
| `BR_WS_ENABLED=1` | `scripts/betrivers_ws.py` | `data/lines/<date>_br_ws.csv` |
| `DK_INPLAY_WS_ENABLED=1` | `scripts/dk_inplay_ws.py` | `data/lines/<date>_dk_inplay_ws.csv` |

Task supervision: `scripts/task_supervisor.create_supervised_task()` wraps each
subscriber; failures log a warning but never crash the server.

---

## Caching

| Layer | TTL | Key |
|-------|-----|-----|
| In-process TTL cache (`_CACHE` dict) | 300s | endpoint + params tuple |
| Backtest cache (`_BACKTEST_CACHE`) | 24h | stat name |
| CourtVision slate cache | build-triggered | date string |
| NBA API game-log cache | 24h | season + player |
| Player season-average cache | 24h | season |

No Redis dependency for local development. The Railway/Fly deployment uses the
same in-process cache; a Redis layer is not currently wired.

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid parameter (e.g., unknown stat for backtest) |
| 401 | Missing or invalid auth token (risk endpoints) |
| 404 | Player not found |
| 500 | Internal error (model load failure, DB error) |
| 503 | Feature not available (lineup-stats, player-impact before Phase 6 CV data) |

---

## Deployment

**Docker images (5):** each purpose-built for a deployment target.

```bash
# API server
docker build -f Dockerfile -t courtvision-api .
docker run -p 8000:8000 -e NBA_OFFLINE=1 courtvision-api

# Railway (auto-detects nixpacks.toml or Dockerfile)
# fly.toml for Fly.io; Procfile for Heroku-style

# Environment variables
NBA_OFFLINE=1               # default ON — prevent NBA API hangs
LIVE_V2_AUTH_TOKEN=<token>  # enable auth on risk endpoints
SENTRY_DSN=<dsn>            # optional error tracking
DK_WS_ENABLED=1             # optional DK WebSocket feed
```

**CI:** 3 GitHub Actions workflows — test + coverage gate, scheduled scrape.
Coverage floor enforced at 30%; core betting-math tests always required to pass.

---

## Known Issues

| Issue | Endpoint affected | Status |
|-------|-------------------|--------|
| `verify_production_mae.py` crashes (85 vs 129 feature mismatch) | `POST /backtest/{stat}` | Open |
| `verify_winprob.py` reads uncommitted cache — fails fresh clone | `GET /win-prob/{game_id}` | Open |
| DK/Caesars/MGM scrapers IP-blocked in production | `/api/lines/scan`, `/sse/live_edges` | Live coverage subset |
| PostgreSQL migration pending | All DB-backed endpoints use SQLite | ISSUE-021 |
| `/stitch` prefix doubles (router path + mount prefix) | `api/stitch_router.py` routes | Known |

---

*Related: [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`docs/ML_MODELS.md`](ML_MODELS.md) · [`docs/CV_TRACKING.md`](CV_TRACKING.md) · [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-07-15*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
