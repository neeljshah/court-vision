# 05 - Execution + Line Shopping

> **Honesty framing:** all outputs here are **paper / units only** -- no real money has
> been placed. The execution layer ships with a drawdown-triggered kill-switch and a
> **default-DENY real-money gate** that requires a separate, explicit human flip before
> any live placement. Every claim traces back to
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).

---

## What this layer does

The execution and line-shopping layer sits between the calibrated probability outputs
(from the prop XGBs and decision engine) and any downstream action. It has three
responsibilities:

1. **Consolidate lines across books** -- scan per-book CSVs and surface the
   best-available price for every (player, stat, line) triple.
2. **Select and rank bets** -- apply a multi-gate filter chain (edge floor, stat
   allowlist, direction filter, CLV-prediction gate, risk gate, per-period EV floor)
   and size the survivors with fractional Kelly.
3. **Log everything for settlement** -- the shadow logger records every evaluated
   candidate (including ones the gate blocked) so downstream CLV settlement has a
   full counterfactual dataset, not a survivorship-biased sample.

Real-money placement is permanently default-DENY. The paper ledger accumulates a CLV
track record. The conservative real-money gate (`scripts/platformkit/pm_trading/realmoney_gate.py`)
reads that record and outputs only an advisory boolean -- even when it returns
`eligible=True`, a human flip is always required.

---

## Step 1: Multi-book line aggregation

### How lines arrive on disk

Parallel scrapers write per-book CSVs to `data/lines/<date>_<book>.csv`. Each row
carries: `captured_at, book, game_id, player_id, player_name, stat, line, over_price,
under_price, start_time` and (for DK, FD, PB) `book_selection_id_over/under` for
deep-linking.

A 7-day sliding-window lookup (`_CSV_LOOKBACK_DAYS = 7` in `api/_courtvision_odds.py`)
handles the common case where a scraper writes today's file for a game scheduled two
days out. Rows are filtered per-row by `start_time[:10]` to stay date-accurate.

Certain books are excluded from the two-sided consolidation because they publish
one-sided or unmatched spreads that would corrupt the over/under comparison:
`_EXCLUDED_BOOKS = {"bov", "mgm", "caesars", "fanatics", "fd"}`. DraftKings (dk) and
Pinnacle (pinnacle, when available) supply genuine two-sided prices and remain in.

### Consolidation into a single view

`api/_courtvision_odds.py::consolidate(date)` merges all per-book CSVs into one list
of `ConsolidatedProp` objects, each carrying a `books` array with one entry per
active book. A game-ID alias table (`data/cache/games_lookup.json`) resolves the
different numeric/hash IDs each book assigns to the same matchup so filtering is
matchup-scoped, not ID-scoped.

An NBA-roster filter (`data/players_nba_active.json`) drops non-NBA names, using
accent-stripped lowercase comparison so "Nikola Jokic" (book ASCII) matches
"Nikola Jokic" (accented roster entry) correctly.

### Line scanner endpoint

`GET /api/lines/scan?date=YYYY-MM-DD&stat=pts&min_books=2&sort=edge`
(`api/lines_router.py`) exposes the consolidated view as JSON. For every
(player, stat, line) row it computes:

```
over_spread_cents  = best_over_price  - worst_over_price   (American odds units)
under_spread_cents = best_under_price - worst_under_price
implied_diff       = worst_implied_prob - best_implied_prob  (percentage points)
best_combined_edge = max(implied_diff_over, implied_diff_under)
```

Rows default-sort descending by `best_combined_edge` so the props with the most
shopping value across books appear first. Steam (sharp-money) events are annotated
per-row when the event is less than 10 minutes old.

---

## Step 2: De-vig -- stripping the sportsbook's margin

Before any probability comparison happens, the raw implied probabilities (which sum to
more than 1 because of the house margin) are converted to fair probabilities via
`src/prediction/devig.py`. Four methods are implemented from scratch:

| Method | Mechanism | When to use |
|---|---|---|
| `proportional` / `additive` | Divide each implied prob by the overround | Fast approximation; symmetric |
| `multiplicative` | Bisect for k such that sum(pi^k) == 1, return pi^k | More principled power renorm |
| `power` | Raise each prob to 1/n then renormalize | n-th root closed-form approx |
| `shin` (default) | Shin (1992) bisection for insider-trading z | Asymmetric; loads vig onto the longshot |

**Why Shin is the default.** The Shin (1992) model assumes a fraction z of bettors
are informed. It corrects the favourite probability upward (and the longshot downward)
compared to simple proportional devig -- closer to how a sharp book like Pinnacle
actually sets lines. The bisection converges to 1e-12 tolerance in at most 64 iterations.

The API surface is `POST /api/devig` (in `api/devig_router.py`), defaulting to `shin`.
It returns `vigged` (raw implied probs), `fair_probs` (de-vigged, sum == 1.0 within
1e-9), `fair_odds` (back-converted American), and `overround` (the margin being removed).

The same de-vig math is wired directly into `detect_arb()` in
`src/prediction/betting_portfolio.py`: two books' implied probs are compared after
de-vig, and a true arbitrage exists only when the combined implied probability drops
below 1.0.

---

## Step 3: Bet selection -- the multi-gate filter chain

`src/prediction/bet_selector.py::select()` takes the edge rows from the daily slate
and passes every candidate through a chain of filters in order. A candidate must
clear ALL gates or it is dropped.

```
edge_rows (from slate)
    |
    v
[1] |edge| > edge_min (4% floor from config/betting.yaml)
    |
    v
[2] stat-direction filter (bet_thresholds.py: BLK UNDER only; other stats both)
    |
    v
[3] stat allowlist (CV_BET_POLICY: controls which stats the active policy permits)
    |
    v
[4] per-policy edge floor + AST playoff guard
    |
    v
[5] CLV-prediction gate (clv_predictor.pkl, requires predicted CLV > 1.5%)
    |
    v
[6] Risk gate (RiskConfig / RiskState: kill-switch, drawdown cap, open-bet cap)
    |
    v
    SIZED (fractional Kelly) -> paper ledger + shadow log
```

**Gate details that matter:**

- **Edge floor (Gate 1).** `edge_min = 0.04` (4%) from `config/betting.yaml`. This is
  the raw stat-unit edge (`proj - line`) normalized by the line value.

- **Direction filter (Gate 2).** Research found BLK OVER has zero measured edge
  (Iter-50: n=105, ROI=0.00%, z=0.00). Only BLK UNDER is permitted. All other stats
  allow both directions. This is the only current directional filter.

- **AST playoff guard (Gate 4).** AST bets on playoff game IDs (prefix `004`) are
  blocked unless `CV_ALLOW_PLAYOFF_AST=1`. Data showed AST edge breaks in the playoffs
  (gated result: -2.78%).

- **CLV gate (Gate 5).** A trained predictor (`src/prediction/clv_predictor.py`) must
  estimate CLV > 1.5% before the bet advances. If the model file is absent (no
  settled history yet), the gate degrades gracefully to edge-only filtering rather
  than crashing.

- **Risk gate (Gate 6).** `src/prediction/risk_controls.py` evaluates kill-switch
  state, 30-day drawdown, and open-bet cap. If the portfolio kill-switch is engaged
  or the drawdown breaker has fired, zero bets are emitted for that cycle.

All dropped candidates are still written to the shadow log with a `gate_status` and
`gate_blocked_by` field. This is how the system avoids survivorship bias when
evaluating threshold choices later.

---

## Step 4: Tiering -- S / A / B

The decision engine (`src/prediction/decision_engine.py`) assigns every candidate a
tier based on expected value (EV%) and projection delta:

```
Tier S : EV >= 8%  AND  |proj - line| >= 1.0 stat unit
Tier A : EV >= 4%
Tier B : EV >= 4%  (calibrated floor; was 1% pre-2026-05-27)
(below B): not emitted
```

Per-period EV floors are stricter for earlier quarters because projections are noisier
mid-game. End-of-Q1 and end-of-Q2 use a floor of 0.12 (12%); end-of-Q3 also 0.12.
These were calibrated on a 90,846-row, 50-game backtest.

Each emitted bet carries a `WHY` string:

```
"S: A.Player PTS OVER 24.5 @ dk -110 | proj 27.3 (p=62.3%, EV=+9.1%, K=3.2%)"
```

---

## Step 5: Fractional Kelly sizing

Sizing uses two complementary methods from `src/prediction/betting_portfolio.py`:

**`kelly_corr()` -- the main method.**
Full Kelly = (bp - q) / b where b is the net payout, p is the calibrated win
probability, and q = 1 - p. Scaling:

- Quarter-Kelly (`KELLY_FRACTION = 0.25`).
- Correlation penalty: if an open bet on a correlated stat is already in flight,
  the size shrinks proportionally. The correlation matrix is loaded from
  `data/models/prop_corr_matrix.json`.
- Hard cap: single bet cannot exceed 4% of bankroll (`MAX_BET_PCT = 0.04`).
- Drawdown halt: if realized drawdown from the starting bankroll exceeds 15%,
  `kelly_corr()` returns 0.0 for all bets.

**`kelly_b_stake()` -- edge-proportional sizing (Iter-33, shipped).**
Instead of a binary above/below threshold, sizes all positive-edge bets
proportionally to edge magnitude. Bigger edges get a higher estimated p_win
and therefore a larger Kelly fraction, capped at 3 units. Per-stat hit-rate
anchors are calibrated from Iter-22+25+28 production data (1,016 OOS bets).

When `KELLY_B_ENABLED = True` (the current default in `src/prediction/bet_thresholds.py`),
`bet_selector` calls `kelly_b_stake()` for above-threshold bets.

---

## Step 6: CLV tracking + the real-money gate

**What CLV means here.** CLV (closing line value) measures whether the price at
bet time was better than the final sharp closing price. Positive CLV = locked a
more favorable number than where the efficient market settled.

```
OVER  bet: CLV = (closing_line - opening_line) / |opening_line|
           positive when closing > opening (market agreed, moved the line up)
UNDER bet: CLV = (opening_line - closing_line) / |opening_line|
           positive when closing < opening (market agreed, moved the line down)
```

This convention is implemented in `betting_portfolio.py::record_clv()` and enforced
consistently in `scripts/clv_tracker.py`, `clv_tracker_daemon.py`, and
`player_props.py`.

A legacy analysis dashboard lives at `GET /clv` (FastAPI + Jinja, `api/clv_router.py`).
It is a **backtest/paper analysis tool**, not the product surface: the headline metric
is **CLV** (closing-line value -- the honest edge yardstick); any PnL/ROI/Sharpe tiles it
renders are **paper, units-based, backtest-descriptive only** -- they are NOT real-money
results and NOT an edge or profit claim (real money is default-DENY; see
`10_HONEST_LIMITS.md`). The canonical, units-only product UI is the webapp (`/bets`,
`/paper`, `/models`); CLV is what actually tells you whether a number beat the close.

**The real-money gate (`scripts/platformkit/pm_trading/realmoney_gate.py`).**
This module is DECISION-ONLY -- it never moves money or authorizes placement. It reads
the paper CLV ledger and checks five pre-registered criteria (fixed before the data):

| Criterion | Threshold |
|---|---|
| Settled paper bets with real CLV | >= 500 |
| Bootstrap 95% lower bound on CLV% | strictly > 0.0 |
| Fraction of bets that beat the close | >= 55% |
| Fraction of record on TRUE (not proxy) closes | >= 90% |
| ROI | NOT a criterion -- CLV is the honest yardstick |

Even when all five pass, the gate returns `eligible=True` as advice only. A human
flip of a separate environment variable is the only path to real-money placement.
The system has never placed real money. The ledger that would seed the gate does not
yet have enough settled bets to pass MIN_SETTLED_N.

---

## Step 7: Portfolio guards + risk surface

`src/prediction/betting_portfolio.py` enforces portfolio-level limits:

- `MAX_OPEN_BETS = 20` -- never more than 20 bets in flight simultaneously.
- `MAX_DRAWDOWN_PCT = 0.15` -- halt all new bets when drawdown from starting
  bankroll exceeds 15%.
- Quarter-Kelly cap: `KELLY_FRACTION = 0.25`.
- Per-bet cap: `MAX_BET_PCT = 0.04` (4% of bankroll).

`GET /api/risk/status` (in `api/_risk_router.py`) returns the live snapshot: current
bankroll, daily PnL and stake, open-bet count, 30-day drawdown, and kill-switch state.
Drawdown alerts fire to Slack when threshold crosses 10% (warning) or 15% (auto-engage
kill-switch). The kill-switch halts the decision engine from emitting recommendations
entirely until manually disengaged.

`GET /health/ops` (in `api/main.py`) aggregates scraper freshness, CLV hit-rate, drift
flags, and component health -- the operational dashboard.

---

## What the system does NOT do

- **No real-money placement.** The entire chain operates on units, not dollars. The
  `bet_selector.py` default is `dry_run=False` (reads from config), but
  `config/betting.yaml` sets the paper mode. Even if wired for live placement,
  the risk gate and kill-switch are the last line of defense.
- **No claimed pregame edge.** The market is efficient pregame. The calibrated model
  MATCHES the Shin-devigged close within noise on team-strength markets. The execution
  layer does not manufacture edge that the model did not find.
- **No cross-book arbitrage claims.** `detect_arb()` surfaces pure arbitrage (combined
  implied probability < 1.0) as an informational signal. Arb opportunities at real
  books are fleeting and line-limit constrained; the system does not automate capture.

---

## ASCII decision-flow summary

```
multi-book CSVs
   data/lines/<date>_<book>.csv
          |
          v
  api/_courtvision_odds.py::consolidate()
    [7-day window, game-ID alias, roster filter]
          |
          v
  api/lines_router.py  GET /api/lines/scan
    [best/worst per side, implied_diff, steam badge]
          |
          v
  src/prediction/bet_selector.py::select()
    Gate 1: |edge| > 4%
    Gate 2: stat direction allowed (BLK UNDER only)
    Gate 3: stat in active CV_BET_POLICY
    Gate 4: AST not in playoffs (unless flag override)
    Gate 5: predicted CLV > 1.5%  (or degrade to edge-only)
    Gate 6: risk controls OK (kill-switch, drawdown, open-bet cap)
          |
          v
  betting_portfolio.kelly_b_stake()
    [edge-proportional, capped at 3u, per-stat correlation penalty]
          |
          v
  shadow_logger.log_evaluation()   <-- ALL candidates, pass or fail
          |
          v
  paper ledger  data/shadow/<game_id>_<date>.csv
          |
    [after market close]
          v
  betting_portfolio.record_clv()
    CLV = (close - open) / |open| [OVER]
    CLV = (open - close) / |open| [UNDER]
          |
          v
  data/clv/daily_clv.csv  -> GET /clv dashboard
          |
          v
  realmoney_gate.py  (advisory only, DEFAULT INELIGIBLE)
          |
          v
  [human flip required] -> no real money placed (ever)
```

---

## Where to look in the repo

- `api/_courtvision_odds.py` -- multi-book CSV consolidation, game-ID alias, roster filter, steam lookup.
- `api/lines_router.py` -- `GET /api/lines/scan`, best/worst per side, `best_combined_edge` metric.
- `src/prediction/devig.py` -- Shin (1992) de-vig (bisection), multiplicative, power, proportional; `POST /api/devig` is the API surface.
- `src/prediction/bet_selector.py` -- the 6-gate filter chain, CLV gate wiring, timing recommender, shadow log integration.
- `src/prediction/bet_thresholds.py` -- per-stat edge thresholds, `STAT_DIRECTIONS` (BLK under-only), `KELLY_B_ENABLED` flag.
- `src/prediction/betting_portfolio.py` -- `kelly_corr()` and `kelly_b_stake()`, `detect_arb()`, `record_clv()`, portfolio guards (`MAX_OPEN_BETS`, `MAX_DRAWDOWN_PCT`).
- `src/prediction/shadow_logger.py` -- append-only 21-column CSV of every evaluated candidate, including gate-blocked ones.
- `src/prediction/decision_engine.py` -- tier classification (S/A/B), per-period EV floors, risk filter, shadow DB log.
- `api/_risk_router.py` -- `GET /api/risk/status`, kill-switch endpoint, drawdown alerting.
- `api/clv_router.py` -- CLV dashboard at `GET /clv`, daily sparkline.
- `api/execution_router.py` -- thin wrappers: `/api/portfolio/summary`, `/api/portfolio/open`, `/api/portfolio/log`, `/api/arb/detect`.
- `scripts/platformkit/pm_trading/realmoney_gate.py` -- advisory CLV-based real-money eligibility check; never authorizes placement.
- `docs/research/validation-methodology.md` -- CLV-over-ROI doctrine, Shin model references.
