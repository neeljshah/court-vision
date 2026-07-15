# 04 -- The Paper-Trading System

> FRAMING FIRST. This system is a calibrated prediction engine, not a
> money-making tool. No real bets are placed. Every prediction record
> carries `executed=False`, `edge_claimed=False`, and `real_money_enabled=False`.
> The gate that guards real-money eligibility returns `authorizes_bet=False`
> by design -- a human must always flip that switch. The honest yardstick is
> CLV (did we log a better number than where the market closed?), not ROI.

---

## What paper trading means here

"Paper trading" means the system runs its full prediction-to-decision pipeline
on real live games, logs every pick with model probabilities and unit sizing,
records outcomes against real final scores, and grades the predictions for CLV
-- all without touching a sportsbook API or moving a dollar.

The purpose is measurement: does the model produce predictions that, if acted
on, would routinely capture a better number than the efficient closing line?
That is the only honest forward-validation of a prediction model on sports
markets. ROI on paper-simulated bets is not reported as evidence of edge
because small-N ROI inflates from variance, and the closing line is the honest
anchor.

---

## The two records

### 1. paper_predictions.jsonl (22,640 rows as of 2026-07-15)

**File:** `data/frontend/paper_predictions.jsonl`

Every row is a real-time model prediction logged at decision time. As of the
most recent audit the file contains 22,640 rows across three sports:

- MLB: 15,444 rows
- Soccer (international): 5,800 rows
- NBA: 1,340 rows

Each row captures what the model actually believed at prediction time:
`logged_at`, `sport`, `matchup`, `model_prob` (calibrated win probability),
`fair_odds`, `event_id`, `commence_time`, and a `close_proxy` block that stores
the devigged closing line when one was captured.

**CLV is computed as:**
`clv = model_prob - fair_close_prob`
where `fair_close_prob` is the Shin-devigged consensus from the closing
snapshot. Positive CLV means the model logged a better probability than
where the market closed. When no closing snapshot was captured, CLV reads
`null` (status = `no_close`) -- this is honest, never imputed.

Settled games carry a real graded result (`win`/`loss`/`push`) looked up
from ESPN final scores. Pending or unresolved games carry `pending` or `null`.

**Served at:** `GET /api/paper/predictions` (paginated, up to 500 rows per
page, filterable by sport). Source: `predict_service/frontend/paper_predictions_routes.py`.

### 2. pnl_ledger.csv -- the manual prop bet ledger

**File:** `data/pnl_ledger.csv`

A transactional, append-only ledger of individual prop-market picks (player
props: pts / reb / ast / fg3m / stl / blk / tov). Each row records:

- `player`, `stat`, `line`, `side` (OVER/UNDER), `book`, `american_odds`
- `stake` (paper units, not dollars)
- `model_pred` (point prediction), `model_prob`, `model_edge` (pred - line)
- `kelly_pct` (fractional Kelly sizing from calibrated probabilities)
- `status` (open / won / lost / push / voided)
- `actual_stat`, `profit_loss`, `bankroll_after` (filled at settlement)
- `strategy` tag for A/B attribution

Every write is atomic (tmpfile + os.replace) and guarded by a cross-platform
file lock with stale-lock recovery. Source: `src/betting/pnl_ledger.py`.

**CLV enrichment:** `data/pnl_ledger_clv.csv` joins every ledger row against
per-minute closing-line snapshots from `data/lines/<date>_<book>.csv`.
CLV is computed as:
- `clv_percent` = closing implied probability - placement implied probability
  (positive = beat the close)
- `beat_close` = bool

The enrichment pipeline prefers an id-based match (book + game_id + player_id
+ stat) and falls back to a name-based match. A snapshot more than 24 hours
old is rejected. Source: `src/betting/clv.py` -> `enrich_pnl_with_clv()`.

---

## The prediction-market (Kalshi / Polymarket) paper trail

The system also paper-trades binary game-winner markets on Kalshi and
Polymarket using the same calibrated model probabilities.

**Kalshi** (`scripts/platformkit/odds_provider/kalshi.py`): reads public
market data from `api.elections.kalshi.com/trade-api/v2` without auth (auth is
only needed for actual trading). Prices are `yes_ask_dollars` values in [0,1]
-- the implied probability of the YES side. Sports tracked: NBA (`KXNBA`),
MLB (`KXMLB`), soccer (`KXEPL`/`KXWC`), ATP tennis (`KXATP`).

**Polymarket** (`scripts/platformkit/odds_provider/polymarket.py`): reads
public data from `gamma-api.polymarket.com` (no auth required). Handles both
two-team markets (outcomes = ["TeamA", "TeamB"]) and binary YES/NO markets.

For each contract the system computes an edge signal:

```
edge = fair_prob - market_price
edge_bps = edge * 10000
```

`fair_prob` is the calibrated model output; `market_price` is the venue's
YES price in [0,1]. A `Signal` object records whether the model and the
devigged sportsbook lean the same direction (disagreement = yellow flag, likely
a model error rather than a real mispricing). Source:
`scripts/platformkit/pm_trading/edge_signal.py`.

**Important: `edge_bps` is a raw hypothesis, not a claimed edge.** A large
value usually means a thin book, a stale price, or a model error. It earns
the label "edge" only after it survives forward paper CLV grading through
the eval gate. No edge is currently claimed on these markets.

The `PaperVenue` (`scripts/platformkit/pm_trading/venues/paper.py`) is a
deterministic in-memory exchange: you seed it with order books, it matches
incoming orders against resting liquidity with a price-time engine. Identical
inputs produce identical fills -- no wall-clock, no randomness -- which is
exactly what a forward-paper validation harness needs to be reproducible.

The P&L blotter for prediction-market trades lives at
`data/pm_trading/blotter.jsonl`. Settlement P&L for one binary YES contract
is `net_qty * (resolution - avg_price)`. Net paper P&L = realized settlement
P&L - fees. Source: `scripts/platformkit/pm_trading/pnl.py`.

---

## In-game / live paper trading

The in-game conditioning layer is the one measured calibration win in the
system (NBA Brier 0.209 -> 0.159, MLB 0.241 -> 0.126 at end-of-Q3 / end-of-
inning; scoped to real-corpus OOS, calibration not $). The paper loop
exercises it on live games:

`scripts/platformkit/pm_trading/live_ingame.py` ingests the MLB live linescore
API (keyless, `statsapi.mlb.com`) to detect games currently in `"Live"` state,
extracts inning / half / run differential, feeds them to `predict_live`, and
logs the recalibrated win probability forward for grading.

These in-game predictions land in the same prediction ledger as pregame picks
(`layer="ingame"` field) and are graded by `grade_live.py` once the game goes
Final -- using the MLB stats API to fetch the actual final score, never a
proxy.

---

## Grading and CLV

The grading pipeline:

```
shadow log (data/shadow/<game_id>_YYYY-MM-DD.csv)
    -> settlement.settle_day()
        -> cdn.nba.com box score (gameStatus == 3 = Final)
            -> actual stat per player, per game
                -> outcome: hit / miss / push / no_actual
```

Every prediction the engine evaluated is shadow-logged including ones the
gate blocked (`gate_status: blocked`). This is anti-survivorship-bias
discipline: you need the full counterfactual distribution to calibrate filter
thresholds, not only the bets that passed. Source:
`src/prediction/shadow_logger.py`, `src/prediction/settlement.py`.

**CLV semantics (corrected, CV_CLV_LINE_SIGN_FIX):**

| Bet | Beat the close when... |
|-----|------------------------|
| OVER | the line CLOSED HIGHER than you placed (you got the lower, better number) |
| UNDER | the line CLOSED LOWER than you placed (you got the higher, better number) |

`clv_line` = positive means you beat the close. `clv_percent` =
`closing_implied_prob - placement_implied_prob` (positive = you locked the
longer price). Both signs are verified in `src/betting/clv.py`; a legacy
inversion bug (`CV_CLV_LINE_SIGN_FIX=off`) is documented and gated.

**The CLV dashboard** is served at `GET /clv`. It renders headline tiles
(total stake / units, avg CLV bps, win%, Sharpe), by-book and by-stat
breakdowns, and a daily CLV sparkline from `data/clv/daily_clv.csv`.
Source: `api/clv_router.py`.

---

## The auto-loop (always-on, self-improving)

`scripts/platformkit/pm_trading/auto_loop.py` runs the full paper cycle on a
20-minute heartbeat (default `--interval 1200`). One cycle does:

1. **PAPER** -- run `run_paper_cycle()`: log today's predictions for live games
2. **GRADE** -- run `grade_open_bets()`: settle finished games from real scores
3. **IMPROVE** -- run `improve_all()`: recalibrate the model on accumulated
   real outcomes, gated by the eval gate (only ever improve or hold, never
   ship a regression)
4. **LINE TICK** -- `poll_once()` per sport: capture a closing-line snapshot
5. **SCOREBOARD** -- write `grade_summary.json` atomically so the UI and the
   real-money gate always read a fresh view
6. **RATCHET** -- evaluate any pending self-improvement candidate through the
   Milestone-8 ratchet (SHIP only if it clears the gate; honest REJECT otherwise)

Every step is independently guarded: one failing step never blocks the others.
The loop logs `HONEST: paper only (executed=False); calibration/CLV is the
yardstick, NOT a $ edge.` on every cycle.

---

## The real-money gate (default DENY)

`scripts/platformkit/pm_trading/realmoney_gate.py` expresses the
conservative, pre-registered criteria that the paper CLV record must clear
before a human may even consider real-money execution. The gate:

- Requires >= 500 settled bets with a real (non-proxy) CLV reading
- Requires >= 90% of the CLV record to rest on TRUE closes (not last-price
  proxies -- proxy CLV is a measurement convenience, not a proof)
- Requires the bootstrap 95% LOWER BOUND on CLV percent to strictly exceed 0.0
  (computed via 2,000-iteration bootstrap with fixed seed 1729 for
  reproducibility -- the pessimistic case must clear zero, not the mean)
- Requires >= 55% of settled bets to have beaten the close
- ROI is NEVER a criterion

The gate always returns `authorizes_bet=False`. Even when `eligible=True`, a
human flip is required downstream. The gate is decision-only arithmetic, not an
authorization. As of this writing, the criteria have not yet been cleared
(insufficient settled true-close CLV observations -- the NBA season was in
offseason and liquid in-play prices were unavailable).

---

## How to read the /paper and /clv pages

### GET /api/paper/predictions

```
?sport=nba|mlb|soccer_intl   -- filter to one sport (optional)
?offset=0&limit=100          -- pagination (max 500 per page)
```

Response fields:
- `total` -- total logged predictions matching the filter
- `trades[].model_prob` -- calibrated model probability at log time
- `trades[].market_prob` -- 1/fair_odds (null when unavailable)
- `trades[].clv` -- model_prob - fair_close_prob (null = INSUFFICIENT_DATA)
- `trades[].clv_status` -- "proxy" | "no_close"
- `trades[].result` -- "win" | "loss" | "push" | "pending" | null
- `trades[].executed` -- always False
- `trades[].edge_claimed` -- always False
- `trades[].real_money_enabled` -- always False

### GET /clv

Dashboard: headline tiles, by_book / by_stat CLV tables, daily sparkline.
Reads `data/clv/daily_clv.csv` and calls the internal `api_clv_summary()`
function (no HTTP round-trip). Accepts `?days=N` (default 30).

### GET /api/paper (legacy)

The older dashboard at `:8098` (FastAPI + Jinja) surfaces the same underlying
data in `data/pnl_ledger.csv` and `data/pnl_ledger_clv.csv` via the
`courtvision_router`. The data layer is identical; the view is a different
template.

---

## Architecture map

```
live games (keyless APIs)
    |
    v
run_paper_cycle() / live_ingame.py
    |-- model prediction (calibrated prob, kelly_pct)
    |-- paper_predictions.jsonl    (game-winner records)
    |-- pnl_ledger.csv             (prop records)
    |-- shadow/<game_id>_date.csv  (all evaluations, inc. blocked)
    |
    v
grade_live.py / settlement.settle_day()   <-- real final scores
    |-- outcome: hit/miss/push/no_actual
    |-- pnl_ledger_clv.csv  (CLV enrichment from closing snapshots)
    |
    v
grade_summary.json / CLV dashboard (/clv)
    |
    v
realmoney_gate.evaluate()  -->  eligible=False (default)  -->  human gate
```

---

## Where to look in the repo

| Topic | File |
|-------|------|
| Shadow logger (all evaluations, inc. blocked) | `src/prediction/shadow_logger.py` |
| Settlement (NBA box score grading) | `src/prediction/settlement.py` |
| Prop P&L ledger (atomic writes, file locking) | `src/betting/pnl_ledger.py` |
| CLV enrichment (closing-line join, corrected signs) | `src/betting/clv.py` |
| CLV dashboard route | `api/clv_router.py` |
| Paper predictions API route | `predict_service/frontend/paper_predictions_routes.py` |
| Predictions JSONL (22,640 rows) | `data/frontend/paper_predictions.jsonl` |
| PaperVenue (deterministic in-memory exchange) | `scripts/platformkit/pm_trading/venues/paper.py` |
| Edge signal (calibrated prob vs venue price) | `scripts/platformkit/pm_trading/edge_signal.py` |
| PM P&L blotter | `scripts/platformkit/pm_trading/pnl.py` |
| In-game live paper predictions | `scripts/platformkit/pm_trading/live_ingame.py` |
| Live prediction grading | `scripts/platformkit/pm_trading/grade_live.py` |
| Auto-loop (20-min cycle, self-improving) | `scripts/platformkit/pm_trading/auto_loop.py` |
| Real-money gate (default DENY, authorizes_bet=False) | `scripts/platformkit/pm_trading/realmoney_gate.py` |
| Kalshi keyless market reader | `scripts/platformkit/odds_provider/kalshi.py` |
| Polymarket keyless market reader | `scripts/platformkit/odds_provider/polymarket.py` |
| Validation methodology doc | `docs/research/validation-methodology.md` |
| Honest numbers reference | `docs/JOB_EVIDENCE_PACKET.md` |
