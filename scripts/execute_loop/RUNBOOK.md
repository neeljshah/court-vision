# Execute Loop Runbook

_Generated 2026-05-26 03:41 UTC — do not edit by hand._

## Table of Contents

- [L01 — DK/FD slate ingester](#l01--dkfd-slate-ingester)
- [L02 — Fantasy points dist engine](#l02--fantasy-points-dist-engine)
- [L03 — Cash game optimizer (LP)](#l03--cash-game-optimizer-(lp))
- [L04 — GPP optimizer (MC+ownership)](#l04--gpp-optimizer-(mc+ownership))
- [L05 — DK/FD submission engine](#l05--dkfd-submission-engine)
- [L06 — Late-swap watcher](#l06--late-swap-watcher)
- [L07 — Settlement + P&L ledger](#l07--settlement-+-p&l-ledger)
- [L08 — Drift detector](#l08--drift-detector)
- [L09 — Kalshi exchange client](#l09--kalshi-exchange-client)
- [L10 — Polymarket client](#l10--polymarket-client)
- [L11 — Sporttrade client](#l11--sporttrade-client)
- [L12 — Prophet Exchange client](#l12--prophet-exchange-client)
- [L13 — Cross-exchange EV engine](#l13--cross-exchange-ev-engine)
- [L14 — Order manager](#l14--order-manager)
- [L15 — Market-making logic](#l15--market-making-logic)
- [L16 — Live trader](#l16--live-trader)
- [L17 — Hedge calculator](#l17--hedge-calculator)
- [L18 — Bankroll manager (Kelly)](#l18--bankroll-manager-(kelly))
- [L19 — CLV calculator + report](#l19--clv-calculator-+-report)
- [L20 — Injury feed scraper](#l20--injury-feed-scraper)
- [L21 — Lineup announcement watcher](#l21--lineup-announcement-watcher)
- [L22 — Slack/Discord alerting](#l22--slackdiscord-alerting)
- [L23 — Status dashboard](#l23--status-dashboard)
- [L24 — Nightly retrain cron](#l24--nightly-retrain-cron)
- [L25 — A/B shadow harness](#l25--ab-shadow-harness)
- [L26 — Account hygiene tooling](#l26--account-hygiene-tooling)
- [L27 — Tax tracking](#l27--tax-tracking)
- [L28 — Withdrawal automation](#l28--withdrawal-automation)
- [L29 — Multi-account orchestrator](#l29--multi-account-orchestrator)
- [L30 — DFS contest selector](#l30--dfs-contest-selector)
- [L31 — Ownership projection model](#l31--ownership-projection-model)
- [L32 — Stack correlation engine](#l32--stack-correlation-engine)
- [L33 — Sell-to-close optimizer](#l33--sell-to-close-optimizer)
- [L34 — Variance budgeter](#l34--variance-budgeter)
- [L35 — Risk-of-ruin monitor](#l35--risk-of-ruin-monitor)
- [L36 — Edge-erosion watcher](#l36--edge-erosion-watcher)
- [L37 — Postmortem agent](#l37--postmortem-agent)
- [L38 — Health dashboard](#l38--health-dashboard)
- [L39 — Execution backtest harness](#l39--execution-backtest-harness)
- [L40 — Multi-model dispatcher](#l40--multi-model-dispatcher)
- [L41 — Integration harness (end-to-end)](#l41--integration-harness-(end-to-end))
- [L42 — Production readiness checker](#l42--production-readiness-checker)
- [L43 — Runbook generator](#l43--runbook-generator)
- [L44 — Paper-mode helper library](#l44--paper-mode-helper-library)
- [L45 — Daily operator checklist](#l45--daily-operator-checklist)
- [L46 — EventBus (cross-layer routing)](#l46--eventbus-(cross-layer-routing))
- [L47 — Regression / drift detector](#l47--regression--drift-detector)
- [L48 — Swish demo runner](#l48--swish-demo-runner)
- [L49 — State-of-loop summary generator](#l49--state-of-loop-summary-generator)
- [Cross-Reference Table](#cross-reference-table)

## L01 — DK/FD slate ingester

**Status:** `shipped` | **Tests:** 24/24 | **LOC:** —

> L01_slate_ingester.py — DraftKings / FanDuel DFS slate ingester.
> 
> Three-tier fallback: HTTP → cache (.cache/<book>_<date>.json, <6 h) → seed (seed_<book>_<date>.json)
> 
> Public API
> ----------
>     SlateContest          dataclass
>     get_dfs_slate(book, date, paper) -> list[SlateContest] | None
>     parse_dk_contest(group_json, draftables_json) -> SlateContest
>     parse_fd_contest(fd_json) -> SlateContest
>     save_slate(slate, out_dir) -> str
>     main()   CLI --book {dk,fd,both} --date YYYY-MM-DD --out --paper
> 
> Paper vs Live Mode
> ------------------
> When PAPER_MODE is True (the default), the module skips all live HTTP
> requests to DraftKings and FanDuel endpoints and falls back immediately
> to the local cache or seed file.  No network calls are made in paper mode.
> When PAPER_MODE is False (SUBMISSION_MODE=live), live HTTP is attempted
> first, then cache, then seed.
> 
>     PAPER_MODE = (SUBMISSION_MODE != "live")   # module-level constant
> 
> Environment Variables:
>     SUBMISSION_MODE   "paper" (default) → skip HTTP; "live" → attempt HTTP first.
>                       Any value other than "live" is treated as paper mode.

### Public API

```python
class SlateContest
```

```python
def parse_dk_contest(group_json: dict, draftables_json: dict) -> SlateContest
```
_Build SlateContest from DK draftgroup + draftables responses._

```python
def parse_fd_contest(fd_json: dict) -> SlateContest
```
_Build SlateContest from FanDuel fixture-list payload._

```python
def save_slate(slate: SlateContest, out_dir: str='data/dfs_slates') -> str
```
_Write SlateContest to <out_dir>/<book>_<date>_<slate_type>.json; return path._

```python
def get_dfs_slate(book: str, date: str, paper: Optional[bool]=None, out_dir: str='data/dfs_slates') -> Optional[List[SlateContest]]
```
_Fetch/parse DFS slate(s) for book on date. Three-tier fallback: HTTP → cache → seed._

```python
def main(argv: Optional[List[str]]=None) -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `SUBMISSION_MODE` | `'paper'` |

### Paper vs Live Mode

```
Paper vs Live Mode
------------------
When PAPER_MODE is True (the default), the module skips all live HTTP
requests to DraftKings and FanDuel endpoints and falls back immediately
to the local cache or seed file.  No network calls are made in paper mode.
When PAPER_MODE is False (SUBMISSION_MODE=live), live HTTP is attempted
first, then cache, then seed.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L01_slate_ingester.py
```

## L02 — Fantasy points dist engine

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** 271

> L02_fpts_distribution.py — Fantasy Points Distribution Engine (BUILD L2).
> 
> Converts per-stat quantile predictions into correlated FPTS sample distributions
> for DraftKings and FanDuel scoring. Supports lineup simulation via Monte Carlo.
> 
> Public API
> ----------
>     FPTSDistribution         — dataclass with mean/std/quantiles/samples/bonuses
>     compute_player_fpts(...) -> FPTSDistribution | None
>     simulate_lineup_fpts(players, n_samples) -> np.ndarray
>     score_box_to_fpts(box, book) -> float

### Public API

```python
class FPTSDistribution
```

```python
def score_box_to_fpts(box: dict, book: str) -> float
```
_Score a single box-score dict to fantasy points._

```python
def compute_player_fpts(player_name: str, opp: str, season: str, *, book: str='DK', is_home: bool=True, rest_days: float=2.0, gamelog_dir: Optional[str]=None, model_dir: Optional[str]=None, n_samples: int=1000) -> Optional[FPTSDistribution]
```
_Compute a correlated FPTS distribution for one player in one game._

```python
def simulate_lineup_fpts(players: List[FPTSDistribution], n_samples: int=10000) -> np.ndarray
```
_Simulate total lineup FPTS by summing independent player samples._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L02_fpts_distribution.py
```

## L03 — Cash game optimizer (LP)

**Status:** `shipped` | **Tests:** 16/16 | **LOC:** 364

> L03_cash_optimizer.py — DraftKings Classic Cash-Game Lineup Optimizer (LP-based).
> 
> Uses PuLP (CBC) with scipy greedy fallback.
> 
> Public API
> ----------
>     Lineup, InfeasibleError
>     optimize_cash(slate, fpts_data, n_lineups, max_exposure) -> list[Lineup]
>     solve_single_lineup(slate, fpts_dict, banned_players)    -> Lineup
>     enforce_diversity(lineups, max_overlap)                  -> list[Lineup]

### Public API

```python
class Lineup
```

```python
class InfeasibleError(Exception)
```
_Raised when no feasible lineup exists._

```python
def solve_single_lineup(slate: SlateContest, fpts_dict: Dict[str, FPTSDistribution], banned_players: Optional[Set[str]]=None) -> Lineup
```
_Solve one optimal DK Classic lineup. Raises InfeasibleError if unsolvable._

```python
def enforce_diversity(lineups: List[Lineup], max_overlap: int=6) -> List[Lineup]
```
_Greedy-filter lineups so every accepted pair shares ≤ max_overlap players._

```python
def optimize_cash(slate: SlateContest, fpts_data: List[FPTSDistribution] | Dict[str, FPTSDistribution], n_lineups: int=1, max_exposure: float=0.4) -> List[Lineup]
```
_Generate n_lineups optimal cash-game lineups with per-player exposure capping._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L03_cash_optimizer.py
```

## L04 — GPP optimizer (MC+ownership)

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** 532

> L04_gpp_optimizer.py — GPP DFS Lineup Optimizer (BUILD L4).
> 
> Monte Carlo simulated-annealing optimizer for GPP (tournament) contests.
> Uses ownership leverage, correlated FPTS distributions, and field simulation
> to maximize expected ROI against a sampled field.
> 
> Public API
> ----------
>     Lineup                       — dataclass (imported from L03 or defined locally)
>     optimize_gpp(...)           -> list[Lineup]
>     simulate_contest_finish(...) -> float          (E[ROI])
>     compute_leverage_score(...)  -> float

### Public API

```python
def compute_leverage_score(player_ownership: float, player_proj_fpts: float, salary: int) -> float
```
_Compute GPP leverage: value-per-dollar divided by ownership._

```python
def simulate_contest_finish(lineup: 'Lineup', field_lineups: List, payout_curve: Optional[List[Tuple[float, float]]]=None, n_sims: int=2000, *, seed: int=0, _pool_players: Optional[List[dict]]=None) -> float
```
_Simulate E[ROI] for a Lineup against a pre-sampled field._

```python
def optimize_gpp(slate, fpts_data: Dict[str, object], ownership: Optional[Dict[str, float]]=None, n_lineups: int=20, field_size: int=100000, banned: Optional[Set[str]]=None, seed: int=42) -> List['Lineup']
```
_Build n_lineups optimal GPP lineups via simulated annealing + MC field sim._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L04_gpp_optimizer.py
```

## L05 — DK/FD submission engine

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** —

> L05_submission_engine.py — DFS Lineup Submission Engine (PAPER MODE).
> 
> Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
> env-var list).  Per-layer flags checked: dk_submission, fd_submission.
> Env vars below are kept as fallbacks for backward compatibility when L44 is
> absent (soft-import pattern).
> 
> Storage:
>     data/ledger/submission_cache.json   — idempotency cache (TTL 24 h)
>     data/ledger/paper_submissions.json  — paper-mode log
> 
> Mode: SUBMISSION_MODE=paper (default) | live (requires USER_TOKEN + book gates).
> 
> CLI:
>     python L05_submission_engine.py submit --book {dk|fd} --contest_id X --lineup PATH [--live]
>     python L05_submission_engine.py status --submission_id X
> 
> Environment Variables:
>     SUBMISSION_MODE — Controls paper vs live submission routing.
>         "paper" (default when absent): all submissions are logged locally to
>         data/ledger/paper_submissions.json and no real money is wagered.
>         "live": activates real API calls; requires USER_TOKEN + book-specific gates.
> 
>     USER_TOKEN — Bearer token used in the Authorization header for all live API
>         requests (DraftKings and FanDuel). Required when SUBMISSION_MODE=live;
>         if absent in live mode, _check_live_gates raises PermissionError and
>         the submission is blocked. Defaults to empty string (disables live calls).
> 
>     DK_API_KEY — DraftKings API key sent as the X-Api-Key header for DK live
>         submissions. Must be non-empty when SUBMISSION_MODE=live and book=dk.
>         Absent value causes _check_live_gates to block the submission.
> 
>     DK_LIVE_ENABLED — Safety flag that must equal "1" to permit live DraftKings
>         submissions. When absent or set to any other value, DK live submissions
>         are blocked regardless of DK_API_KEY. Defaults to disabled (not "1").
>         Also controlled via L44: DK_LIVE_SUBMISSION_ENABLED=1.
> 
>     FD_API_KEY — FanDuel API key sent as the X-Api-Key header for FD live
>         submissions. Must be non-empty when SUBMISSION_MODE=live and book=fd.
>         Absent value causes _check_live_gates to block the submission.
> 
>     FD_LIVE_ENABLED — Safety flag that must equal "1" to permit live FanDuel
>         submissions. When absent or set to any other value, FD live submissions
>         are blocked regardless of FD_API_KEY. Defaults to disabled (not "1").
>         Also controlled via L44: FD_LIVE_SUBMISSION_ENABLED=1.
> 
> Paper vs Live Mode (MODE GATING):
>     Default behavior is paper mode — no environment variables need to be set.
>     Live submission is gated by ALL of the following conditions being true:
>       1. SUBMISSION_MODE=live
>       2. USER_TOKEN is non-empty
>       3. For DK: DK_LIVE_ENABLED=1 (or L44 dk_submission live) AND DK_API_KEY is non-empty
>          For FD: FD_LIVE_ENABLED=1 (or L44 fd_submission live) AND FD_API_KEY is non-empty
>     If any gate is unsatisfied, _check_live_gates raises PermissionError and
>     submit_lineup falls back to no submission (error propagates to caller).
>     The --live CLI flag sets SUBMISSION_MODE=live in the current process only.

### Public API

```python
class SubmissionResult
```

```python
def uuid4_hex12() -> str
```

```python
def submit_lineup(book: str, contest_id: str, lineup: dict, idempotency_key: Optional[str]=None) -> SubmissionResult
```

```python
def submit_batch(submissions: list[dict]) -> list[SubmissionResult]
```

```python
def cancel_submission(book: str, submission_id: str) -> bool
```

```python
def main(argv=None) -> int
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `USER_TOKEN` | `None` |
| `SUBMISSION_MODE` | `'paper'` |
| `DK_LIVE_ENABLED` | `'0'` |
| `FD_LIVE_ENABLED` | `'0'` |
| `DK_API_KEY` | `None` |
| `FD_API_KEY` | `None` |

### Paper vs Live Mode

```
L05_submission_engine.py — DFS Lineup Submission Engine (PAPER MODE).

Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
env-var list).  Per-layer flags checked: dk_submission, fd_submission.
Env vars below are kept as fallbacks for backward compatibility when L44 is
absent (soft-import pattern).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L05_submission_engine.py
```

## L06 — Late-swap watcher

**Status:** `shipped` | **Tests:** 6/6 | **LOC:** 503

> L06_late_swap.py — Late-Swap Watcher (BUILD L6).
> 
> Polls L20 injury feed for new OUT/DOUBTFUL updates within the slate lock window,
> finds affected lineups, estimates EV swing, and recommends replacement candidates.
> 
> Public API
> ----------
>     SwapAction              frozen dataclass
>     SwapSignal              frozen dataclass
>     watch_for_swaps(slate, current_lineups, current_bets, poll_seconds) -> Iterator[SwapSignal]
>     compute_swap_impact(slate, lineup, news, fpts_data)                 -> SwapSignal | None
>     recommend_swap_actions(signal)                                       -> list[SwapAction]
> 
> CLI
> ---
>     python L06_late_swap.py --help

### Public API

```python
class SwapAction
```

```python
class SwapSignal
```

```python
def compute_swap_impact(slate, lineup: dict, news: InjuryUpdate, fpts_data: Dict[str, float], current_bets: Optional[List[dict]]=None) -> Optional[SwapSignal]
```
_Compute swap signal for a single (lineup, injury-news) pair._

```python
def recommend_swap_actions(signal: SwapSignal) -> List[SwapAction]
```
_Return the recommended SwapActions from a signal, sorted by FPTS delta desc._

```python
def watch_for_swaps(slate, current_lineups: List[dict], current_bets: List[dict], poll_seconds: int=60, fpts_data: Optional[Dict[str, float]]=None, _now_fn=None) -> Iterator[SwapSignal]
```
_Poll L20 every poll_seconds; yield SwapSignal for each actionable injury._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L06_late_swap.py
```

## L07 — Settlement + P&L ledger

**Status:** `shipped` | **Tests:** 29/29 | **LOC:** —

> L07_pnl_ledger.py — Settlement + P&L Ledger (execute_loop layer 7).
> 
> Storage: data/ledger/bets.parquet  (CSV fallback if pyarrow missing)
>          data/ledger/contests.parquet
> 
> CLI:
>     python L07_pnl_ledger.py settle [--date YYYY-MM-DD]
>     python L07_pnl_ledger.py summary [--start YYYY-MM-DD] [--end YYYY-MM-DD]
>                                      [--by stat|book|day]
>     python L07_pnl_ledger.py open
> 
> Event Publication
> -----------------
> L07 publishes the following events via L46 EventBus (additive — does not replace
> existing direct calls to L22 alerting):
> 
> ``bet.settled``
>     Emitted for each bet that transitions from OPEN → WON / LOST / PUSH.
>     Source: ``"L7"``
>     Payload schema::
> 
>         {
>             "bet_id":     str,   # unique bet identifier
>             "status":     str,   # "WON" | "LOST" | "PUSH"
>             "stake":      float, # stake in units
>             "pnl":        float, # realised P&L in units
>             "player":     str,   # player name
>             "stat":       str,   # stat key, e.g. "pts"
>             "settled_at": str,   # ISO 8601 UTC timestamp of settlement
>         }
> 
>     NOTE: VOID (DNP) outcomes do NOT emit ``bet.settled``.

### Public API

```python
class BetRow
```

```python
def place_bet(row: BetRow) -> str
```
_Append a BetRow to the ledger. Returns the bet_id._

```python
def get_open_bets() -> list[BetRow]
```
_Return all OPEN bets as BetRow objects._

```python
def settle_unsettled(date: str=None) -> int
```
_Settle all OPEN bets that have a game_id._

```python
def get_pnl_summary(start: str=None, end: str=None, by: str='stat') -> dict
```
_Aggregate P&L for settled bets, grouped by `by` (stat|book|day)._

```python
def close_contest(contest_id: str, entry_position: int, total_payout: float) -> None
```
_Record final result for a DFS contest entry._

```python
def main(argv=None) -> int
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L07_pnl_ledger.py
```

## L08 — Drift detector

**Status:** `shipped` | **Tests:** 16/16 | **LOC:** —

> L08_drift_detector.py — Model drift detection for player-prop predictions.
> 
> Reads the L07 bets ledger (data/ledger/bets.parquet), compares recent MAE
> and hit-rate against trained baselines, and emits WARN/DRIFT alerts via L22.
> 
> Public API
> ----------
>     DriftMetric           dataclass
>     compute_drift(stat, window_days) -> DriftMetric | None
>     run_all_drift_checks(window_days) -> list[DriftMetric]
>     daily_drift_report() -> dict
>     alert_on_drift(metrics) -> int
> 
> CLI:
>     python L08_drift_detector.py check         # prints summary table
>     python L08_drift_detector.py report [--window 7]
> 
> Environment Variables: none
> 
> Event Publication
> -----------------
> When a stat's drift status is "DRIFT" or "WARN", L08 publishes a
> ``"drift.detected"`` event via the L46 EventBus singleton (soft-imported;
> failure is non-fatal and logged at DEBUG level).
> 
> Event schema::
> 
>     {
>         "stat":         str,   # lowercase stat name, e.g. "pts"
>         "drift_metric": float, # observed z-score
>         "threshold":    float, # z-score threshold that was crossed
>         "severity":     str,   # "warning" (WARN) | "error" (DRIFT)
>         "window_days":  int,   # lookback window used for the check
>         "detected_at":  str,   # ISO 8601 UTC timestamp
>     }
> 
> Subscribers can register via::
> 
>     import scripts.execute_loop.L46_event_bus as L46
>     L46.subscribe("drift.detected", handler, layer="MyLayer")

### Public API

```python
class DriftMetric
```

```python
def compute_drift(stat: str, window_days: int=7) -> Optional[DriftMetric]
```
_Compute drift for a single stat over window_days._

```python
def run_all_drift_checks(window_days: int=7) -> list[DriftMetric]
```
_Return DriftMetric for every stat in _STATS._

```python
def daily_drift_report(window_days: int=7) -> dict
```
_Build report dict and persist to data/ledger/drift_report_<date>.json._

```python
def alert_on_drift(metrics: list[DriftMetric]) -> int
```
_Send alerts for DRIFT/WARN metrics. Returns count of alerts sent._

```python
def main(argv=None) -> int
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L08_drift_detector.py
```

## L09 — Kalshi exchange client

**Status:** `shipped` | **Tests:** 20/20 | **LOC:** —

> L09_kalshi_client.py — Kalshi Exchange Client (PAPER MODE by default).
> 
> MODE GATING
> -----------
>   KALSHI_LIVE_ENABLED=1  AND  KALSHI_API_KEY  AND  KALSHI_API_KEY_ID  → LIVE
>   Else → PAPER (default)
> 
>   Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('kalshi');
>   see L44 for the canonical list of env vars.
> 
> PAPER BEHAVIOUR
> ---------------
>   Orderbook:   read data/exchange_seed/kalshi/<ticker>.json
>                missing ticker → KeyError("unknown market_ticker: <ticker>")
>   post_order:  append to data/ledger/paper_kalshi_orders.json;
>                return {"order_id": "paper_kalshi_<12-hex>", "status": "filled"}
>   Idempotency: same key twice → return cached response, ledger unchanged
>   get_positions: aggregate paper ledger by (ticker, side); avg_price + PnL
> 
> PUBLIC API
> ----------
>     get_orderbook(market_ticker)   -> dict
>     get_positions()                -> list[KalshiPosition]
>     post_order(market_ticker, side, qty, price, idempotency_key) -> dict
>     cancel_order(order_id)         -> bool
> 
> CLI
> ---
>     python L09_kalshi_client.py orderbook --ticker NBA-TEST
>     python L09_kalshi_client.py positions
>     python L09_kalshi_client.py post --ticker X --side yes --qty 10 --price 60 [--live]
> 
> Environment Variables
> ---------------------
>     KALSHI_LIVE_ENABLED   Set to "1" to activate live (HTTP) mode; default paper.
>     KALSHI_API_KEY        API key for live REST calls; required when KALSHI_LIVE_ENABLED=1.
>     KALSHI_API_KEY_ID     API key ID for live REST calls; required when KALSHI_LIVE_ENABLED=1.

### Public API

```python
class KalshiQuote
```

```python
class KalshiPosition
```

```python
def get_orderbook(market_ticker: str) -> dict
```
_Return orderbook dict with yes_bids/yes_asks/no_bids/no_asks._

```python
def get_positions() -> list[KalshiPosition]
```
_Aggregate paper ledger into per-(ticker, side) KalshiPosition objects._

```python
def post_order(market_ticker: str, side: str, qty: int, price: int, idempotency_key: str | None=None) -> dict
```
_Place an order._

```python
def cancel_order(order_id: str) -> bool
```
_Cancel an open order._

```python
def main(argv: list[str] | None=None) -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `KALSHI_LIVE_ENABLED` | `'0'` |
| `KALSHI_API_KEY` | `''` |
| `KALSHI_API_KEY_ID` | `''` |

### Paper vs Live Mode

```
L09_kalshi_client.py — Kalshi Exchange Client (PAPER MODE by default).

MODE GATING
-----------
  KALSHI_LIVE_ENABLED=1  AND  KALSHI_API_KEY  AND  KALSHI_API_KEY_ID  → LIVE
  Else → PAPER (default)
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L09_kalshi_client.py
```

## L10 — Polymarket client

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** —

> L10_polymarket_client.py — Polymarket CLOB client (PAPER MODE default).
> 
> Reads NBA prediction markets from Polymarket's Gamma + CLOB APIs.
> Default mode is PAPER — never touches private keys or real funds.
> LIVE mode requires explicit env vars AND --live flag from caller.
> 
> Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('polymarket');
> see L44 for the canonical list of env vars.
> 
> Public API
> ----------
>     PolyMarket           dataclass
>     PolyOrderbook        dataclass
>     PolyPosition         dataclass
>     find_nba_markets(date)          -> list[PolyMarket]
>     get_orderbook(condition_id)     -> PolyOrderbook | None
>     get_positions(wallet)           -> list[PolyPosition]
>     post_order(...)                 -> dict
>     cancel_order(order_id)          -> bool
> 
> CLI
> ---
>     python L10_polymarket_client.py markets [--date YYYY-MM-DD]
>     python L10_polymarket_client.py orderbook --condition_id X
>     python L10_polymarket_client.py post --condition_id X --outcome yes --qty 100 --price 0.55 [--live]
>     python L10_polymarket_client.py cancel --order_id X
> 
> Environment Variables:
>     POLYMARKET_LIVE_ENABLED  Set to "1" to activate live (HTTP) mode; default paper.
>                              Canonical flag read via L44_paper_mode.is_live_for_layer('polymarket').
>     POLYMARKET_PRIVATE_KEY   EIP-712 signing key for the funded Polymarket wallet.
>                              Required to enable live order submission and cancellation.
>                              Default: absent (paper mode only; live calls raise PermissionError).
>     POLYMARKET_USDC_FUNDED   Confirmation flag that the wallet holds sufficient USDC.
>                              Must be set to exactly "true" (lowercase) to permit live trading.
>                              Default: absent / any other value (live calls raise PermissionError).
> 
> Paper vs Live Mode:
>     Default is PAPER.  All write operations (post_order, cancel_order) record to a local
>     JSON ledger at data/ledger/paper_polymarket_orders.json and never contact the CLOB.
>     Live mode is gated by _is_live_permitted(): BOTH POLYMARKET_PRIVATE_KEY (non-empty)
>     AND POLYMARKET_USDC_FUNDED == "true" must be set, AND the caller must explicitly pass
>     live=True to post_order() / cancel_order().  Missing either env var raises PermissionError
>     before any network call is attempted.

### Public API

```python
class PolyMarket
```
_A single Polymarket prediction market._

```python
class PolyOrderbook
```
_Level-2 orderbook for one Polymarket market._

```python
class PolyPosition
```
_Aggregated paper or live position for one (condition_id, outcome) pair._

```python
def find_nba_markets(date: Optional[str]=None) -> list[PolyMarket]
```
_Return NBA prediction markets from the seed file for *date* (default today UTC)._

```python
def get_orderbook(condition_id: str) -> Optional[PolyOrderbook]
```
_Return the L2 orderbook for *condition_id* from seed, or None if missing._

```python
def get_positions(wallet: Optional[str]=None) -> list[PolyPosition]
```
_Aggregate open paper positions from the ledger._

```python
def post_order(condition_id: str, outcome: str, side: str, qty: float, price_usdc: float, idempotency_key: Optional[str]=None, *, live: bool=False) -> dict
```
_Submit a paper order; in live mode signs EIP-712 and hits the CLOB._

```python
def cancel_order(order_id: str, *, live: bool=False) -> bool
```
_Cancel an open order by ID.  In paper mode marks it cancelled in the ledger._

```python
def main(argv: Optional[list[str]]=None) -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `POLYMARKET_PRIVATE_KEY` | `''` |
| `POLYMARKET_USDC_FUNDED` | `''` |
| `POLYMARKET_LIVE_ENABLED` | `'0'` |

### Paper vs Live Mode

```
L10_polymarket_client.py — Polymarket CLOB client (PAPER MODE default).

Reads NBA prediction markets from Polymarket's Gamma + CLOB APIs.
Default mode is PAPER — never touches private keys or real funds.
LIVE mode requires explicit env vars AND --live flag from caller.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L10_polymarket_client.py
```

## L11 — Sporttrade client

**Status:** `shipped` | **Tests:** 12/12 | **LOC:** —

> L11_sporttrade_client.py — Sporttrade Exchange Client (PAPER / LIVE).
> 
> Sporttrade is a sports-exchange where contracts trade 1-99 (cents-on-dollar).
> 
> Mode gating
> -----------
> - SPORTTRADE_LIVE_ENABLED=1 AND SPORTTRADE_API_KEY set  → LIVE (HTTP calls)
> - Default (env vars absent / empty)                     → PAPER (seed JSON files)
> - SPORTTRADE_LIVE_ENABLED=1 without API key             → PermissionError on any call
> 
> Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('sporttrade');
> see L44 for the canonical list of env vars.
> 
> Public API
> ----------
>     SporttradeQuote     dataclass
>     SporttradePosition  dataclass
>     find_nba_events(date)          -> list[dict]
>     get_orderbook(market_id)       -> dict {bids, asks}
>     get_positions()                -> list[SporttradePosition]
>     post_order(market_id, side, qty, price, idempotency_key) -> dict
>     cancel_order(order_id)         -> bool
>     subscribe_ws(market_ids, on_msg) -> never (stub)
> 
> CLI
> ---
>     python L11_sporttrade_client.py events [--date YYYY-MM-DD]
>     python L11_sporttrade_client.py orderbook --market_id mkt_test
>     python L11_sporttrade_client.py positions
>     python L11_sporttrade_client.py post --market_id X --side back --qty 10 --price 55 [--live]
> 
> Environment Variables
> ---------------------
>     SPORTTRADE_LIVE_ENABLED  — set to "1" to activate live (HTTP) mode; default paper.
>                                Canonical flag read via L44_paper_mode.is_live_for_layer('sporttrade').
>     SPORTTRADE_API_KEY       — bearer token for live REST/WS calls; required when
>                                SPORTTRADE_LIVE_ENABLED=1.

### Public API

```python
class SporttradeQuote
```

```python
class SporttradePosition
```

```python
def find_nba_events(date: Optional[str]=None) -> list[dict]
```
_Return NBA events for *date* (YYYY-MM-DD; default today UTC)._

```python
def get_orderbook(market_id: str) -> dict
```
_Return orderbook for *market_id* as {bids: [[price, qty], ...], asks: ...}._

```python
def post_order(market_id: str, side: str, qty: int, price: float, idempotency_key: Optional[str]=None) -> dict
```
_Submit an order._

```python
def cancel_order(order_id: str) -> bool
```
_Cancel an open order by *order_id*._

```python
def get_positions() -> list[SporttradePosition]
```
_Return current open positions._

```python
def subscribe_ws(market_ids: list[str], on_msg: Callable[[dict], None]) -> None
```
_Stream orderbook updates over WebSocket._

```python
def main(argv: Optional[list[str]]=None) -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `SPORTTRADE_LIVE_ENABLED` | `'0'` |
| `SPORTTRADE_API_KEY` | `''` |

### Paper vs Live Mode

```
Mode gating
-----------
- SPORTTRADE_LIVE_ENABLED=1 AND SPORTTRADE_API_KEY set  → LIVE (HTTP calls)
- Default (env vars absent / empty)                     → PAPER (seed JSON files)
- SPORTTRADE_LIVE_ENABLED=1 without API key             → PermissionError on any call
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L11_sporttrade_client.py
```

## L12 — Prophet Exchange client

**Status:** `shipped` | **Tests:** 13/13 | **LOC:** —

> L12_prophet_client.py — Prophet Exchange Client (PAPER / LIVE).
> 
> Prophet is a sports-prediction exchange where player props trade as
> decimal-priced contracts (1.01 – 100.0 inclusive exclusive of bounds).
> 
> Mode gating
> -----------
> - PROPHET_LIVE_ENABLED=1  AND  PROPHET_API_KEY set  → LIVE (HTTP calls)
> - Default (env vars absent / empty)                  → PAPER (seed JSON files)
> - PROPHET_LIVE_ENABLED=1 without API key             → PermissionError on any call
> 
> Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('prophet');
> see L44 for the canonical list of env vars.
> 
> Public API
> ----------
>     ProphetQuote     dataclass (frozen)
>     ProphetPosition  dataclass
>     find_nba_prop_markets(date)                          -> list[dict]
>     get_orderbook(market_id)                             -> dict {bids, asks, ts}
>     get_positions()                                      -> list[ProphetPosition]
>     post_order(market_id, side, qty, price_decimal,
>                idempotency_key)                          -> dict
>     cancel_order(order_id)                               -> bool
> 
> CLI
> ---
>     python L12_prophet_client.py markets [--date YYYY-MM-DD]
>     python L12_prophet_client.py orderbook --market_id nba_lebron_pts_25_5
>     python L12_prophet_client.py positions
>     python L12_prophet_client.py post --market_id X --side over --qty 10
>                                       --price_decimal 1.90 [--live]
> 
> Environment Variables
> ---------------------
>     PROPHET_LIVE_ENABLED  — set to "1" to activate live (HTTP) mode; default paper.
>                             Canonical flag read via L44_paper_mode.is_live_for_layer('prophet').
>     PROPHET_API_KEY       — bearer token for live REST calls; required when
>                             PROPHET_LIVE_ENABLED=1.

### Public API

```python
class ProphetQuote
```

```python
class ProphetPosition
```

```python
def find_nba_prop_markets(date: Optional[str]=None) -> list[dict]
```
_Return NBA player-prop markets for *date* (YYYY-MM-DD; default today UTC)._

```python
def get_orderbook(market_id: str) -> dict
```
_Return orderbook for *market_id* as {bids, asks, ts}._

```python
def get_positions() -> list[ProphetPosition]
```
_Return current open positions._

```python
def post_order(market_id: str, side: str, qty: float, price_decimal: float, idempotency_key: Optional[str]=None) -> dict
```
_Submit an order._

```python
def cancel_order(order_id: str) -> bool
```
_Cancel an open order by *order_id*._

```python
def main(argv: Optional[list[str]]=None) -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `PROPHET_LIVE_ENABLED` | `'0'` |
| `PROPHET_API_KEY` | `''` |

### Paper vs Live Mode

```
Mode gating
-----------
- PROPHET_LIVE_ENABLED=1  AND  PROPHET_API_KEY set  → LIVE (HTTP calls)
- Default (env vars absent / empty)                  → PAPER (seed JSON files)
- PROPHET_LIVE_ENABLED=1 without API key             → PermissionError on any call
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L12_prophet_client.py
```

## L13 — Cross-exchange EV engine

**Status:** `shipped` | **Tests:** 17/17 | **LOC:** —

> L13_cross_exchange_ev.py — Cross-Exchange EV Engine (PAPER MODE).
> 
> Compares model-implied probabilities against live exchange quotes to find
> positive-EV opportunities across books. No HTTP, no order submission —
> pure function of CSV/JSON inputs.
> 
> Public API
> ----------
>     ExchangeQuote           dataclass
>     EVOpportunity           dataclass
>     find_ev_opportunities(model_predictions, quotes, min_ev_pct,
>                           source, market_id, exchanges) -> list[EVOpportunity]
>     shop_best_price(side, quotes_for_market) -> ExchangeQuote
>     load_quotes_from_snapshot(snapshot_csv_path) -> list[ExchangeQuote]
>     fetch_quotes_from_paper_clients(market_id, exchanges, player, stat, line)
>         -> dict[str, list[ExchangeQuote]]
> 
> CLI
> ---
>     python L13_cross_exchange_ev.py find --snapshot path.csv --model preds.json [--min-ev 2.0]
>     python L13_cross_exchange_ev.py rank --snapshot path.csv --model preds.json --top 20
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
> which control paper-vs-live behaviour individually. This module contains no
> live API calls of its own — it only normalises orderbook data returned by
> those clients.
> 
> Live mode for downstream calls is enabled only when the per-exchange env var
> (e.g. KALSHI_LIVE_ENABLED=1) is set on the underlying client; this module
> defers to those defaults.
> 
> Environment Variables
> ---------------------
> None. This module reads no environment variables directly. All paper/live
> gating is delegated to the L9-L12 exchange clients it composes.

### Public API

```python
def american_to_decimal(p: int) -> float
```
_Convert American odds integer to decimal multiplier (stake included)._

```python
def prob_to_american(p: float) -> int
```
_Convert win probability [0,1] to American odds integer._

```python
class ExchangeQuote
```
_A single price quote from one book for one side of a player prop._

```python
class EVOpportunity
```
_A positive-EV bet opportunity identified by the engine._

```python
def shop_best_price(side: str, quotes_for_market: list[ExchangeQuote]) -> ExchangeQuote
```
_Return the quote with the highest decimal payout for the backer._

```python
def find_ev_opportunities(model_predictions: dict, quotes: list[ExchangeQuote], min_ev_pct: float=2.0, *, source: str='snapshot', market_id: Optional[str]=None, exchanges: Optional[List[str]]=None) -> list[EVOpportunity]
```
_Identify positive-EV opportunities by comparing model probs to market quotes._

```python
def load_quotes_from_snapshot(snapshot_csv_path: str) -> list[ExchangeQuote]
```
_Parse a CSV snapshot file into a list of ExchangeQuote objects._

```python
def fetch_quotes_from_paper_clients(market_id: str, exchanges: list[str] | None=None, player: str='', stat: str='', line: float=0.0) -> dict[str, list[ExchangeQuote]]
```
_Fetch orderbooks from paper-mode exchange clients and normalize to ExchangeQuotes._

```python
def main(argv=None) -> None
```

### Paper vs Live Mode

```
L13_cross_exchange_ev.py — Cross-Exchange EV Engine (PAPER MODE).

Compares model-implied probabilities against live exchange quotes to find
positive-EV opportunities across books. No HTTP, no order submission —
pure function of CSV/JSON inputs.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L13_cross_exchange_ev.py
```

## L14 — Order manager

**Status:** `shipped` | **Tests:** 17/17 | **LOC:** —

> L14_order_manager.py — Order Manager (execute_loop layer 14).
> 
> Tracks live orders across Kalshi / Polymarket / SportTrade, detects fills,
> triggers repricing when model probability drifts, and cancels stale orders.
> 
> Storage: data/ledger/open_orders.json   (list of OrderState dicts)
>          Written atomically via .tmp + os.replace
> 
> Public API
> ----------
>     track_order(order_id, exchange, market_id, side, qty, price, model_p) -> OrderState
>     get_open_orders() -> list[OrderState]
>     update_from_exchange_fills() -> int
>     check_for_reprice(model_predictions: dict) -> list[OrderState]
>     cancel_stale(max_age_seconds: int = 1800) -> int
>     reprice_order(order: OrderState, new_price: int) -> bool
> 
> CLI
> ---
>     python L14_order_manager.py list
>     python L14_order_manager.py update
>     python L14_order_manager.py reprice --order-id X --new-price 60
>     python L14_order_manager.py cancel-stale [--max-age-sec 1800]
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
> which control paper-vs-live behaviour individually. This module makes no
> live API calls of its own — order tracking, fill detection, repricing, and
> cancellation all delegate to the exchange clients in L9-L12, which each
> carry their own paper/live gate.
> 
> Live mode for downstream calls is enabled only when the per-exchange env var
> (e.g. KALSHI_LIVE_ENABLED=1) is set on the underlying client; this module
> defers to those defaults.
> 
> Environment Variables
> ---------------------
> None. This module reads no environment variables directly. All paper/live
> gating is delegated to the L9-L12 exchange clients it composes.
> 
> Event Publication (L46 EventBus)
> ---------------------------------
> L14 publishes two event types through the L46 EventBus singleton so that
> downstream layers (L7 ledger, L22 alerts) can subscribe without L14 needing
> direct knowledge of them.  L46 is soft-imported; if unavailable, all
> existing direct-call paths continue to function unchanged.
> 
>     "fill.received"  — emitted on every successful _apply_fill call
>         payload keys: order_id, exchange, market_id, side,
>                       matched_qty, qty_filled_now, status
> 
>     "order.filled"   — emitted when an order transitions to FILLED status
>                        (qty_filled >= qty); fired once per fill event,
>                        immediately after "fill.received"
>         payload keys: order_id, exchange, market_id, side,
>                       qty_filled, qty, price, model_p

### Public API

```python
class NormalizedFill
```

```python
class OrderState
```

```python
def track_order(order_id: str, exchange: str, market_id: str, side: str, qty: int, price: int, model_p: float) -> OrderState
```
_Create and persist a new tracked order._

```python
def get_open_orders() -> List[OrderState]
```
_Return all currently tracked open/partial orders._

```python
def update_from_exchange_fills() -> int
```
_Poll each exchange and update fill state._

```python
def sync_all_exchanges(positions: Optional[Dict[str, list]]=None, exchanges: Optional[List[str]]=None) -> List[OrderState]
```
_Poll all 4 paper exchange clients and reconcile positions._

```python
def check_for_reprice(model_predictions: dict) -> List[OrderState]
```
_Return orders where |current_model_p - model_predictions[market_id]| > 0.05._

```python
def cancel_stale(max_age_seconds: int=1800) -> int
```
_Cancel orders older than max_age_seconds via exchange.cancel_order._

```python
def reprice_order(order: OrderState, new_price: int) -> bool
```
_Cancel existing order and post a new one at new_price._

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
which control paper-vs-live behaviour individually. This module makes no
live API calls of its own — order tracking, fill detection, repricing, and
cancellation all delegate to the exchange clients in L9-L12, which each
carry their own paper/live gate.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L14_order_manager.py
```

## L15 — Market-making logic

**Status:** `shipped` | **Tests:** 31/31 | **LOC:** 347

> L15_market_making.py — Market-Making Logic (PAPER MODE STRICT).
> 
> Generates two-sided quotes (bid/ask) from a model probability estimate,
> posts them via L14 order tracking, and refreshes quotes when model drift
> exceeds a threshold.
> 
> Public API
> ----------
>     MMQuote                     dataclass
>     prob_to_american(p) -> int
>     compute_mm_quote(model_p, model_p_std, target_spread_pp) -> MMQuote | None
>     should_market_make(model_p, model_p_std, liquidity_threshold) -> bool
>     post_two_sided(exchange, market_id, mm_quote) -> dict
>     update_quotes_on_model_drift(open_quotes, new_predictions) -> list[MMQuote]
> 
> Paper Mode Strict
> -----------------
>     post_two_sided uses soft-imported L14.track_order only.
>     If L14 is unavailable → {"bid_order_id": None, "ask_order_id": None, "status": "L14_missing"}
>     No live exchange HTTP calls are ever made.
> 
> CLI
> ---
>     python L15_market_making.py simulate --market_id X --model_p 0.55 --std 0.03 [--spread 5]

### Public API

```python
class MMQuote
```
_A two-sided market-maker quote for one market._

```python
def prob_to_american(p: float) -> int
```
_Convert win probability [0, 1] to integer American odds._

```python
def should_market_make(model_p: float, model_p_std: float, liquidity_threshold: float=100) -> bool
```
_Return True iff it is safe and worthwhile to post a two-sided quote._

```python
def compute_mm_quote(model_p: float, model_p_std: float, target_spread_pp: int=3, market_id: str='unknown') -> Optional[MMQuote]
```
_Compute a two-sided market-maker quote._

```python
def post_two_sided(exchange: str, market_id: str, mm_quote: MMQuote) -> dict
```
_Post both legs of an MM quote via L14 paper order tracking._

```python
def update_quotes_on_model_drift(open_quotes: list[MMQuote], new_predictions: dict) -> list[MMQuote]
```
_Return quotes that need refreshing because the model has drifted._

### Paper vs Live Mode

```
L15_market_making.py — Market-Making Logic (PAPER MODE STRICT).

Generates two-sided quotes (bid/ask) from a model probability estimate,
posts them via L14 order tracking, and refreshes quotes when model drift
exceeds a threshold.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L15_market_making.py
```

## L16 — Live trader

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** —

> L16_live_trader.py — Live Trader (PAPER MODE STRICT).
> 
> Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
> env-var list).  L16 uses ``not _L44.is_paper_mode()`` as the live gate, with
> LIVE_TRADING_ENABLED env var as the fallback when L44 is absent (soft-import
> pattern ensures behavior is identical if L44 is absent).
> 
> Polls a live prediction engine, evaluates edge vs market quotes, and manages
> paper positions in data/ledger/paper_live_positions.json.  Real order
> submission is permanently gated behind the LIVE_TRADING_ENABLED env var
> (which should never be set in normal operation).
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> L16 is paper-mode by default.  The module-level ``LIVE_TRADING_ENABLED``
> constant (see Config section below) is ``False`` unless the env var is
> explicitly set.  When ``LIVE_TRADING_ENABLED`` is ``False``:
> 
> * ``run_live_session`` logs a reminder and continues in paper mode.
> * All order routing goes through L14 OrderManager → L9-L12 paper clients;
>   no real exchange API calls are made at any point in the chain.
> 
> To enable live trading (intended only for production deployments):
> 
>     export LIVE_TRADING_ENABLED=1   # or "true"
> 
> Even with ``LIVE_TRADING_ENABLED=1`` set, L16 itself does not make direct
> exchange calls — it delegates to L14, which checks per-exchange flags at the
> L9-L12 client layer.  The flag is documented here so L42 audits can confirm
> the paper default is explicit at L16's own level.
> 
> Environment Variables
> ---------------------
>     LIVE_TRADING_ENABLED   Set to "1" or "true" to enable live order routing
>                            (default: "0" → paper mode).  Must be set at the
>                            process level; L16 never writes this var.
> 
> Public API
> ----------
>     LivePosition            dataclass
>     subscribe_live_engine(period) -> Iterator[dict]
>     evaluate_position(prediction, current_quote, existing_position) -> LivePosition
>     run_live_session(game_id, polling_sec) -> int   # returns positions opened
>     exit_all_positions() -> int                     # returns positions closed
> 
> CLI
> ---
>     python L16_live_trader.py session --game-id 0042500207 [--polling-sec 30]
>     python L16_live_trader.py exit-all
>     python L16_live_trader.py status

### Public API

```python
class LivePosition
```

```python
def evaluate_position(prediction: dict, current_quote: dict, existing_position: Optional[LivePosition]=None) -> LivePosition
```
_Evaluate edge and decide action for a given prediction + market quote._

```python
def subscribe_live_engine(period: str='endQ1') -> Iterator[dict]
```
_Yield prediction dicts from the live engine._

```python
def exit_all_positions() -> int
```
_Mark all open positions as CLOSE and persist ledger._

```python
def run_live_session(game_id: str, polling_sec: int=30) -> int
```
_Poll live engine, evaluate positions, persist paper ledger._

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `LIVE_TRADING_ENABLED` | `'0'` |

### Paper vs Live Mode

```
L16_live_trader.py — Live Trader (PAPER MODE STRICT).

Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
env-var list).  L16 uses ``not _L44.is_paper_mode()`` as the live gate, with
LIVE_TRADING_ENABLED env var as the fallback when L44 is absent (soft-import
pattern ensures behavior is identical if L44 is absent).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L16_live_trader.py
```

## L17 — Hedge calculator

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** —

> L17_hedge_calculator.py — Hedge Calculator for live open bets.
> 
> Given an open bet and the current opposite-side market, computes the optimal
> hedge stake and recommends a course of action (full hedge / partial hedge /
> no hedge).
> 
> Public API
> ----------
>     HedgeRecommendation         dataclass
>     calculate_full_hedge(stake_original, odds_original, current_odds_opposite) -> float
>     calculate_partial_hedge(stake_original, odds_original, current_odds_opposite,
>                             target_lock_pct=0.5) -> float
>     recommend_hedge(open_bet, live_market, mode="full") -> HedgeRecommendation | None
> 
> CLI
> ---
>     python L17_hedge_calculator.py recommend \
>         --bet '{"bet_id":"X","side":"OVER","stake":100,"odds_american":-110,"status":"OPEN"}' \
>         --market '{"opposite_side":"UNDER","odds_american_opposite":200,"book":"DK"}'
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
> which control paper-vs-live behaviour individually. This module makes no
> live API calls of its own — hedge math is pure arithmetic over input dicts
> (open_bet, live_market) and does not touch any exchange client directly.
> 
> Live mode for downstream calls is enabled only when the per-exchange env var
> (e.g. KALSHI_LIVE_ENABLED=1) is set on the underlying client; this module
> defers to those defaults.
> 
> Environment Variables
> ---------------------
> None. This module reads no environment variables directly. All paper/live
> gating is delegated to the L9-L12 exchange clients it composes.

### Public API

```python
class HedgeRecommendation
```

```python
def calculate_full_hedge(stake_original: float, odds_original: float, current_odds_opposite: float) -> float
```
_Compute the stake required for a full (equal-payout) hedge._

```python
def calculate_partial_hedge(stake_original: float, odds_original: float, current_odds_opposite: float, target_lock_pct: float=0.5) -> float
```
_Compute a partial hedge stake targeting a fraction of the full hedge._

```python
def recommend_hedge(open_bet: dict, live_market: Optional[dict], mode: str='full') -> Optional[HedgeRecommendation]
```
_Recommend a hedge action for an open bet given a live opposite-side market._

```python
def main(argv=None) -> int
```

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
which control paper-vs-live behaviour individually. This module makes no
live API calls of its own — hedge math is pure arithmetic over input dicts
(open_bet, live_market) and does not touch any exchange client directly.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L17_hedge_calculator.py
```

## L18 — Bankroll manager (Kelly)

**Status:** `shipped` | **Tests:** 17/17 | **LOC:** —

> L18 Bankroll Manager — Kelly sizing, correlation-aware staking, kill switches.
> 
> Public API:
>     kelly_fraction(model_p, american_odds, bankroll) -> float
>     kelly_with_correlation(bets, corr_matrix) -> np.ndarray
>     get_bankroll_state() -> BankrollState
>     update_bankroll(pnl, notes) -> BankrollState
>     check_risk_limits(proposed_stake, correlation_key) -> tuple[bool, str]
>     reset_daily() -> None
>     reset_weekly() -> None
>     trip_kill_switch(reason) -> None
>     clear_kill_switch(user_token) -> None
> 
> Event Publication (via L46 EventBus — optional, non-fatal if unavailable):
>     "kelly.sized"
>         Published after every call to kelly_fraction() that returns a positive
>         fraction.  Payload keys: model_p, american_odds, bankroll,
>         kelly_fraction, kelly_cap_applied (bool).
> 
>     "risk_limit.breached"
>         Published by check_risk_limits() whenever a limit is violated.
>         Payload keys: limit_type (str), proposed_stake (float),
>         threshold (float), reason (str).
> 
> Environment Variables:
>     None required by L18 itself.  L44 env-vars govern paper/live mode
>     for layers that call L18; L18 does not gate its own behaviour on mode.

### Public API

```python
class BetCandidate
```

```python
class BankrollState
```

```python
def kelly_fraction(model_p: float, american_odds: int, bankroll: float=_BANKROLL_NOT_SET, prob: float=None, odds_american: int=None) -> float
```
_Return fractional Kelly stake as a fraction of bankroll._

```python
def kelly_with_correlation(bets: list[BetCandidate], corr_matrix: np.ndarray) -> np.ndarray
```
_Return stake fractions for a portfolio of bets, accounting for correlations._

```python
def get_bankroll_state() -> BankrollState
```
_Load state from ledger; create defaults if missing._

```python
def update_bankroll(pnl: float, notes: str='') -> BankrollState
```
_Apply a realised PnL delta and persist._

```python
def check_risk_limits(proposed_stake: float, correlation_key: str='') -> tuple[bool, str]
```
_Validate proposed_stake against all risk limits._

```python
def reset_daily() -> None
```
_Zero daily PnL and advance daily_start_iso to now._

```python
def reset_weekly() -> None
```
_Zero weekly PnL and advance weekly_start_iso to now._

```python
def trip_kill_switch(reason: str) -> None
```
_Engage kill switch with the given reason._

```python
def clear_kill_switch(user_token: str) -> None
```
_Disengage kill switch; raises ValueError on wrong token._

```python
def main() -> None
```

### Paper vs Live Mode

```
None required by L18 itself.  L44 env-vars govern paper/live mode
    for layers that call L18; L18 does not gate its own behaviour on mode.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L18_bankroll_manager.py
```

## L19 — CLV calculator + report

**Status:** `shipped` | **Tests:** 11/11 | **LOC:** —

> L19_clv_calculator.py — CLV (Closing Line Value) Calculator + Nightly Report.
> 
> Reads the L07 ledger (data/ledger/bets.parquet) and PrizePicks snapshots
> (scripts/validation/real_lines_check/snapshots/prizepicks_*.csv) to compute
> CLV per bet, produce a nightly JSON report, and flag drift.
> 
> Public API
> ----------
>     CLVPoint                dataclass
>     compute_clv(bet, line_at_bet, line_at_close) -> CLVPoint
>     load_snapshots(start_date, end_date, book_filter) -> pd.DataFrame
>     join_bets_to_closes(bets_df, snapshots_df) -> pd.DataFrame
>     nightly_clv_report(date) -> dict
>     rolling_clv_trend(days) -> dict
>     alert_clv_drift(window_days, threshold_pp) -> list
> 
> CLI
> ---
>     python L19_clv_calculator.py report [--date YYYY-MM-DD]
>     python L19_clv_calculator.py trend  [--days 30]
>     python L19_clv_calculator.py alert  [--window 14 --threshold -2.0]
> 
> Paper vs Live Mode — MODE GATING: N/A
> --------------------------------------
> L19 is a **read-only analytics layer** — it makes no API calls and has no
> execution-mode toggle.  The constant ``_MARKET_TYPE_LIVE`` (= ``"live"``)
> is a **data classification**: bets whose ``market`` column contains this
> value were placed after tip-off (in-game prop markets) and are excluded
> from CLV calculations because no pre-game closing line exists.  It is NOT
> an environment-mode gate such as ``if mode == "live"``.  L19 runs
> identically in paper and production environments.  No paper/live mode
> switch is required or applicable.

### Public API

```python
class CLVPoint
```

```python
def compute_clv(bet, line_at_bet: float, line_at_close: float, *, stat: str='', model_p: float=0.0) -> CLVPoint
```
_Compute CLV for one bet._

```python
def load_snapshots(start_date: str, end_date: str, book_filter: list[str]=None) -> pd.DataFrame
```
_Load all PrizePicks snapshots between start_date and end_date (inclusive)._

```python
def join_bets_to_closes(bets_df: pd.DataFrame, snapshots_df: pd.DataFrame) -> pd.DataFrame
```
_For each bet find line_at_bet and line_at_close from snapshots._

```python
def nightly_clv_report(date: str=None) -> dict
```
_Produce a nightly CLV report for `date` (defaults to today)._

```python
def rolling_clv_trend(days: int=30) -> dict
```
_Compute daily mean CLV (prob_pts) over the past `days` days._

```python
def alert_clv_drift(window_days: int=14, threshold_pp: float=-2.0) -> list
```
_Return list of Alert dicts if mean CLV prob_pts over `window_days` < threshold_pp._

```python
def main(argv=None) -> int
```

### Paper vs Live Mode

```
Paper vs Live Mode — MODE GATING: N/A
--------------------------------------
L19 is a **read-only analytics layer** — it makes no API calls and has no
execution-mode toggle.  The constant ``_MARKET_TYPE_LIVE`` (= ``"live"``)
is a **data classification**: bets whose ``market`` column contains this
value were placed after tip-off (in-game prop markets) and are excluded
from CLV calculations because no pre-game closing line exists.  It is NOT
an environment-mode gate such as ``if mode == "live"``.  L19 runs
identically in paper and production environments.  No paper/live mode
switch is required or applicable.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L19_clv_calculator.py
```

## L20 — Injury feed scraper

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** —

> L20_injury_feed.py — Multi-source NBA Injury Feed Scraper (BUILD L20).
> 
> Polls RotoWire, Underdog (Nitter), and the NBA Official JSON for injury
> updates, deduplicates via SHA-1 hash, detects downgrades, and dispatches
> critical alerts through L22.
> 
> Public API
> ----------
>     InjuryUpdate                dataclass
>     fetch_rotowire_injuries()   -> list[InjuryUpdate]
>     fetch_underdog_lineup_news()-> list[InjuryUpdate]
>     fetch_nba_official_injuries() -> list[InjuryUpdate]
>     run_all_sources()           -> list[InjuryUpdate]
>     diff_against_seen(updates)  -> list[InjuryUpdate]
>     alert_on_critical(updates)  -> int
>     main(poll_seconds)
> 
> CLI
> ---
>     python L20_injury_feed.py fetch
>     python L20_injury_feed.py once
>     python L20_injury_feed.py poll [--interval 600]
> 
> Environment Variables
> ---------------------
>     None required for normal operation.  The scraper uses public endpoints
>     and a local JSON cache; no API keys are needed.
> 
>     NBA_INJURY_JSON_PATH
>         Override the default path to the local nba_official_injury.json cache
>         (``data/external/nba_official_injury.json``).  Useful in tests or
>         staging environments that supply a pre-seeded fixture.
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> L20 is a **read-only data fetcher** and therefore carries no mode gate.
> It does not submit bets, place orders, or write financial state.  All
> output is written to local JSON cache files and published as informational
> events on the L46 EventBus.  No SUBMISSION_MODE / LIVE_MODE / PAPER_MODE
> variable is consulted.
> 
> Event Publication (L46 EventBus)
> ---------------------------------
> After each fetch cycle, L20 compares the newly fetched injury records to
> the prior cached state (_seen.json).  For each NEW or CHANGED record (a
> player whose status is either entirely absent from the cache or whose
> status string differs from the most-recently cached value), L20 publishes:
> 
>     event name: "injury.announced"
>     source:     "L20"
>     payload: {
>         "player":           str,   # accent-stripped canonical player name
>         "team":             str,   # e.g. "LAL", "GSW"
>         "status":           str,   # "OUT" | "DOUBTFUL" | "QUESTIONABLE" | ...
>         "reason":           str,   # injury body text
>         "previously_known": str | None,  # prior status, or None if first seen
>         "fetched_at":       str,   # ISO 8601 UTC timestamp of this fetch
>     }
> 
> Events are published via the module-level L46 singleton
> (``L46_event_bus.get_default_bus()``).  Publish failures are caught and
> logged; they never interrupt the fetch/diff pipeline.
> 
> Atomic Writes
> -------------
> All JSON snapshot files (_seen.json, nba_official_injury.json) are written
> via ``_atomic_write_json``: a sibling temp file is created in the same
> directory, written fully, then replaced via ``os.replace()``.  On crash or
> power-loss the previous snapshot is preserved intact.

### Public API

```python
class InjuryUpdate
```

```python
def fetch_nba_official_injuries() -> List[InjuryUpdate]
```
_Load from data/external/nba_official_injury.json or src.data.injuries._

```python
def fetch_rotowire_injuries() -> List[InjuryUpdate]
```
_Scrape https://www.rotowire.com/basketball/injury-report.php._

```python
def fetch_underdog_lineup_news() -> List[InjuryUpdate]
```
_Scrape Nitter proxy for @Underdog__NBA tweets. Likely 5xx — skip gracefully._

```python
def run_all_sources() -> List[InjuryUpdate]
```
_Fetch all three sources, merge, and return combined list._

```python
def diff_against_seen(updates: List[InjuryUpdate]) -> List[InjuryUpdate]
```
_Return only updates whose hash is NOT in _seen.json; persist new hashes._

```python
def alert_on_critical(updates: List[InjuryUpdate]) -> int
```
_Dispatch critical updates via L22 send_alert. Returns count dispatched._

```python
def main(poll_seconds: int=600) -> None
```
_Continuous poll loop. Ctrl-C to exit._

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
L20 is a **read-only data fetcher** and therefore carries no mode gate.
It does not submit bets, place orders, or write financial state.  All
output is written to local JSON cache files and published as informational
events on the L46 EventBus.  No SUBMISSION_MODE / LIVE_MODE / PAPER_MODE
variable is consulted.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L20_injury_feed.py
```

## L21 — Lineup announcement watcher

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** —

> L21_lineup_watcher.py — Lineup Announcement Watcher (BUILD L21, v2).
> 
> Polls Lineups.com and RotoWire for confirmed NBA starting lineups, diffs them
> against expected top-5 fantasy-point starters, and dispatches alerts via L22.
> 
> Public API: LineupConfirmation, fetch_confirmed_lineups, diff_against_expected,
>             alert_on_surprises
> 
> CLI:
>     python L21_lineup_watcher.py fetch [--date YYYY-MM-DD]
>     python L21_lineup_watcher.py once
> 
> Environment Variables
> ---------------------
> None required for core operation.  The following vars affect behaviour when
> used in the broader execute-loop stack:
> 
>   NBA_LINEUP_DIR    Override the default persistence directory
>                     (``<project_root>/data/lineup_announcements``).  Useful
>                     for integration tests or RunPod deployments with a separate
>                     data volume.  Not read by L21 itself (set _LINEUP_DIR in
>                     calling code), but documented here for operator reference.
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> L21 is a read-only watcher: it fetches public lineup information and writes a
> local JSON snapshot.  It performs no financial transactions and therefore has
> no paper/live distinction of its own.
> 
> In *paper* deployments the emitted "lineup.confirmed" events are consumed
> downstream (e.g. by L44) which enforces the paper/live gate before any bet
> submission.  L21 publishes unconditionally regardless of the value of
> SUBMISSION_MODE or any equivalent environment variable.
> 
> Event Publication
> -----------------
> For each newly confirmed lineup (game_id × team first seen, or whose starter
> roster has changed since the last fetch), L21 publishes a ``"lineup.confirmed"``
> event to the L46 EventBus singleton:
> 
>     Event name : "lineup.confirmed"
>     source     : "L21"
>     payload    : {
>         "game_id"          : str   — date-string used as game identifier,
>         "team"             : str   — 3-letter NBA team abbreviation,
>         "starters"         : list[str] — normalised player names,
>         "confirmed_at"     : str   — ISO 8601 UTC timestamp,
>         "previously_unknown": bool — True if first time this team appears,
>     }
> 
> Publication is best-effort: any exception from L46 is caught and logged at
> WARNING level so that a broken bus never blocks lineup data delivery.

### Public API

```python
class LineupConfirmation
```

```python
def fetch_confirmed_lineups(date: Optional[str]=None) -> List[LineupConfirmation]
```
_Fetch confirmed NBA starting lineups for *date* (default: today UTC)._

```python
def diff_against_expected(confirmation: LineupConfirmation, fpts_data: Dict[str, dict]) -> dict
```
_Populate confirmation.surprise_starters / benched_expected vs fpts top-5._

```python
def alert_on_surprises(confirmations: List[LineupConfirmation]) -> int
```
_Send one alert per surprise starter via L22.  Returns alert count sent._

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
L21 is a read-only watcher: it fetches public lineup information and writes a
local JSON snapshot.  It performs no financial transactions and therefore has
no paper/live distinction of its own.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L21_lineup_watcher.py
```

## L22 — Slack/Discord alerting

**Status:** `shipped` | **Tests:** 15/15 | **LOC:** —

> L22_alerting.py — Slack / Discord alerting wrapper (BUILD L22).
> 
> Sends structured alerts to Slack and Discord with token-bucket rate limiting,
> a persistent FIFO queue for back-pressure, and a test mode that writes locally.
> 
> Public API
> ----------
>     send_alert(channel, level, title, body, fields) -> bool
>     send_edge_alert(player, stat, line, model, edge_pp, side, recommended_stake) -> bool
>     send_fill_alert(bet_id, book, stake, status) -> bool
>     send_drawdown_alert(current_bankroll, starting, pct_drop) -> bool
>     send_drift_alert(stat, observed_mae, expected_mae, days_window) -> bool
>     flush_pending() -> int
>     register_alert_subscribers(bus=None) -> None
> 
> Environment Variables
> ---------------------
>     SLACK_WEBHOOK_URL
>         Incoming-webhook URL for Slack. When absent (or empty) Slack delivery
>         is skipped; test-mode local write is used instead.
> 
>     DISCORD_WEBHOOK_URL
>         Default incoming-webhook URL for Discord. Applies to all channels
>         unless overridden by a per-channel variable. When absent, Discord
>         delivery is skipped.
> 
>     DISCORD_<CHANNEL>_WEBHOOK_URL
>         Per-channel Discord webhook override (e.g. DISCORD_EDGES_WEBHOOK_URL).
>         ``<CHANNEL>`` is the upper-cased channel name (edges, fills, drift,
>         drawdown, news, settle, system). Takes precedence over
>         DISCORD_WEBHOOK_URL for that channel.
> 
>     ALERTS_ENABLED
>         Set to "true" to enable live HTTP delivery to Slack/Discord.
>         Any other value (including absent) disables live delivery and
>         writes alerts to the local log file in test mode (default: "false").
> 
>     ALERTS_LIVE_ENABLED
>         Set to "1" to enable live HTTP webhook delivery.  Stored as the
>         module-level ``LIVE_ENABLED`` constant at import time.  Any other
>         value (including absent) keeps L22 in paper/test mode.  This is the
>         L42 paper_default gate constant; prefer ``ALERTS_ENABLED`` (below)
>         for per-send delivery toggling.
> 
>     ALERTS_RATE_LIMIT_PER_MIN
>         Maximum number of alerts dispatched per 60-second rolling window via
>         the token-bucket limiter. Excess alerts are enqueued and replayed via
>         flush_pending(). Integer; default 30.
> 
>     ALERTS_VERBOSE_FILLS
>         Set to "1" to subscribe L22 to "order.filled" EventBus events and emit
>         an INFO alert for each fill.  Default off (any other value or absent).
> 
> Event Subscriptions (L46 EventBus)
> -----------------------------------
>     Call ``register_alert_subscribers(bus)`` once at harness startup to wire
>     L22 as an L46 EventBus subscriber.  The function is IDEMPOTENT — calling
>     it multiple times registers handlers exactly once.
> 
>     Event name           Condition                     Alert level
>     ─────────────────────────────────────────────────────────────
>     incident.opened      payload["severity"] in P0/P1  ERROR
>     incident.classified  payload["severity"] == "P0"   CRITICAL (→ error)
>     drift.detected       payload["severity"] == "error" WARNING
>     risk_limit.breached  (always)                       ERROR
>     order.filled         ALERTS_VERBOSE_FILLS=1 only    INFO
> 
>     L22 does NOT auto-register at import time; the operator / L41 harness
>     must call register_alert_subscribers() explicitly to avoid noisy behaviour
>     in tests that import L22 without intending to subscribe to the bus.
> 
> Atomic writes
> -------------
>     alert_queue.json is written atomically via a sibling temp file +
>     os.replace() so a crash mid-write never leaves a partial/corrupt queue.
>     The daily log file in _LOG_DIR uses append mode; partial appends are
>     benign for log-only files and do not require atomic replacement.
> 
> CLI
> ---
>     python L22_alerting.py test --channel edges --level info --title "msg"
>     python L22_alerting.py flush

### Public API

```python
class AlertRouter
```

```python
def send_alert(channel: str, level: str, title: str, body: str, fields: Optional[Dict[str, str]]=None) -> bool
```

```python
def send_edge_alert(player: str, stat: str, line: float, model: float, edge_pp: float, side: str, recommended_stake: float) -> bool
```

```python
def send_fill_alert(bet_id: str, book: str, stake: float, status: str) -> bool
```

```python
def send_drawdown_alert(current_bankroll: float, starting: float, pct_drop: float) -> bool
```

```python
def send_drift_alert(stat: str, observed_mae: float, expected_mae: float, days_window: int) -> bool
```

```python
def flush_pending() -> int
```

```python
def register_alert_subscribers(bus=None) -> None
```
_Subscribe L22 alert handlers to the L46 EventBus._

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `LIVE_ENABLED` | `os.environ.get('ALERTS_LIVE_ENABLED') == '1'` |
| `ALERTS_LIVE_ENABLED` | `None` |
| `ALERTS_VERBOSE_FILLS` | `None` |
| `ALERTS_RATE_LIMIT_PER_MIN` | `'30'` |
| `SLACK_WEBHOOK_URL` | `''` |
| `DISCORD_WEBHOOK_URL` | `''` |
| `ALERTS_ENABLED` | `'false'` |

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L22_alerting.py
```

## L23 — Status dashboard

**Status:** `shipped` | **Tests:** 7/7 | **LOC:** —

> L23_status_dashboard.py — Local HTTP Status Dashboard (BUILD L23).
> 
> Serves a dark-themed NBA AI status dashboard at http://127.0.0.1:8765/
> Aggregates bankroll, edges, positions, CLV, freshness, health, settlements.
> 
> Public API
> ----------
>     main(argv=None) -> int
>     serve(port, host) -> None
>     get_dashboard_data() -> dict          # 10 s cache
>     render_dashboard_html(data) -> str
>     format_pnl(x) -> str                 # colored HTML span
>     format_pct(x) -> str
>     svg_sparkline(values, width, height) -> str
>     staleness_days(path) -> int | None
>     _atomic_write_text(path, text) -> None
>     _atomic_write_json(path, payload) -> None
> 
> Environment Variables
> ---------------------
>     none — this module reads no environment variables directly.
>     (Flask/http.server host/port are passed as arguments, not env vars.)

### Public API

```python
def staleness_days(path: pathlib.Path) -> Optional[int]
```
_Return file age in whole days, or None if file missing._

```python
def format_pnl(x: float) -> str
```
_Return HTML <span> with green/red/gray color based on sign._

```python
def format_pct(x: float) -> str
```
_Return percentage string with sign and 1 decimal place._

```python
def svg_sparkline(values: list, width: int=120, height: int=30) -> str
```
_Return inline SVG polyline of normalized values._

```python
def get_dashboard_data() -> dict
```
_Collect all dashboard sections. Returns cached result within 10 s TTL._

```python
def render_dashboard_html(data: dict) -> str
```
_Render full dashboard HTML from data dict. Never raises._

```python
def serve(port: int=8765, host: str='127.0.0.1') -> None
```
_Start the dashboard server. Blocks until interrupted._

```python
def main(argv=None) -> int
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L23_status_dashboard.py
```

## L24 — Nightly retrain cron

**Status:** `shipped` | **Tests:** 22/22 | **LOC:** —

> L24_nightly_retrain.py — Nightly model retrain cron (BUILD L24).
> 
> Runs the prop_pergame walk-forward, gates the candidate on 4/4 WF folds +
> single-split MAE improvement, then either promotes live or submits to the
> L25 shadow harness for 50-game observation.
> 
> Public API
> ----------
>     run_nightly(via_shadow=True, dry_run=False) -> RetrainRun
>     compute_production_metrics() -> dict[str, float]
>     run_walk_forward_candidate() -> dict[str, float]
>     check_promotion_gate(candidate, prod) -> tuple[bool, bool, bool]
>     deploy_candidate(via_shadow=True) -> bool
> 
> CLI
> ---
>     python L24_nightly_retrain.py run
>     python L24_nightly_retrain.py dry-run
>     python L24_nightly_retrain.py status
>     python L24_nightly_retrain.py rollback --to <run_id>
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
>     Default deploy path is always ``via_shadow=True`` (paper/shadow observation
>     via L25 for 50 games) unless the caller explicitly passes ``via_shadow=False``.
>     Live copy to the production WF JSON requires RETRAIN_DEPLOY_TOKEN to be set;
>     without the token the live branch is a no-op. Never default to live.
> 
> Environment Variables
> ---------------------
>     RETRAIN_DEPLOY_TOKEN  Token required to authorise a direct live deploy
>                           (via_shadow=False path). If unset, live deploy is
>                           aborted and deploy_mode remains "none".

### Public API

```python
class RetrainRun
```

```python
def compute_production_metrics() -> dict[str, float]
```
_Read current production MAE from prop_pergame_walk_forward.json._

```python
def run_walk_forward_candidate() -> dict[str, float]
```
_Invoke prop_pergame_walk_forward.py as a subprocess and parse results._

```python
def check_promotion_gate(candidate: dict[str, float], prod: dict[str, float]) -> tuple[bool, bool, bool]
```
_Determine if candidate passes the dual gate._

```python
def deploy_candidate(via_shadow: bool=True) -> bool
```
_Deploy candidate models._

```python
def run_nightly(via_shadow: bool=True, dry_run: bool=False) -> RetrainRun
```
_Full nightly retrain pipeline._

```python
def main(argv=None) -> int
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `RETRAIN_DEPLOY_TOKEN` | `''` |

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
    Default deploy path is always ``via_shadow=True`` (paper/shadow observation
    via L25 for 50 games) unless the caller explicitly passes ``via_shadow=False``.
    Live copy to the production WF JSON requires RETRAIN_DEPLOY_TOKEN to be set;
    without the token the live branch is a no-op. Never default to live.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L24_nightly_retrain.py
```

## L25 — A/B shadow harness

**Status:** `shipped` | **Tests:** 13/13 | **LOC:** —

> L25_ab_shadow.py — A/B Shadow Harness (execute_loop layer 25).
> 
> Storage:
>     data/shadow/_registry.json          — active variant registry
>     data/shadow/<variant_name>/
>         predictions.parquet             — (game_id, player, stat, predicted_q50, ts)
>         summary.json                    — written only when settled
> 
> All disk writes use atomic tmp → replace so a crash never leaves a partial file.
> 
> Environment Variables:
>     L25_SHADOW_ROOT   Override shadow storage directory (default: data/shadow/).
>     L25_LEDGER_DIR    Override ledger directory (default: data/ledger/).
> 
> Paper vs Live Mode:
>     This module is data-only — it writes shadow predictions and reads the L07
>     ledger for settlement.  It does NOT place bets.  No paper/live distinction
>     is needed; all shadow runs are inherently paper (observation only).
> 
> CLI:
>     python L25_ab_shadow.py status                   # list_active_shadows table
>     python L25_ab_shadow.py settle --variant <name>
>     python L25_ab_shadow.py compare --variant <name>

### Public API

```python
class ShadowRun
```

```python
class ShadowSummary
```

```python
class ComparisonResult
```

```python
def start_shadow(variant_name: str, predictor_callable: Callable, n_games: int=50) -> ShadowRun
```
_Register a new shadow variant._

```python
def record_prediction(variant_name: str, game_id: str, player: str, stat: str, predicted_q50: Optional[float]) -> None
```
_Append one prediction row to the variant's predictions file._

```python
def settle_shadow(variant_name: str) -> ShadowSummary
```
_Compute MAE by comparing shadow predictions against the L07 ledger._

```python
def compare_to_prod(variant_name: str) -> ComparisonResult
```
_Build per-stat comparison table and emit a PROMOTE/REJECT/INCONCLUSIVE verdict._

```python
def list_active_shadows() -> list[ShadowRun]
```
_Return all shadow variants from the registry._

```python
def shadow_compare_from_l41(harness_report: dict) -> dict
```
_Run a shadow comparison driven by an L41 IntegrationHarness report._

```python
def main(argv=None) -> int
```

### Paper vs Live Mode

```
Paper vs Live Mode:
    This module is data-only — it writes shadow predictions and reads the L07
    ledger for settlement.  It does NOT place bets.  No paper/live distinction
    is needed; all shadow runs are inherently paper (observation only).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L25_ab_shadow.py
```

## L26 — Account hygiene tooling

**Status:** `shipped` | **Tests:** 30/30 | **LOC:** 262

> L26_account_hygiene.py — Account Hygiene Tooling (execute_loop layer 26).
> 
> Monitors submission pace, IP consistency, betting patterns, and deposit
> scheduling to reduce sportsbook account-limitation risk.
> 
> Storage:
>     data/ledger/hygiene_report_<YYYY-MM-DD>.json
> 
> CLI:
>     python L26_account_hygiene.py report
>     python L26_account_hygiene.py pace --book dk

### Public API

```python
class HygieneCheck
```

```python
class BetPace
```

```python
def check_submission_pace(book: str, recent_bets: list[dict]) -> BetPace
```
_Count bets for *book* placed in the last 60 minutes._

```python
def check_ip_consistency(recent_bets: list[dict]) -> HygieneCheck
```
_Inspect distinct IPs across all recent bets._

```python
def check_pattern_flags(recent_bets: list[dict]) -> list[HygieneCheck]
```
_Return a list of HygieneChecks for suspicious betting patterns._

```python
def recommend_deposit_schedule(bankroll_targets: dict[str, float]) -> list[dict]
```
_Produce 2-3 staggered deposit amounts for each book across 3+ days._

```python
def daily_hygiene_report(recent_bets: Optional[list[dict]]=None, bankroll_targets: Optional[dict[str, float]]=None) -> dict
```
_Run all hygiene checks and write data/ledger/hygiene_report_<date>.json._

```python
def main(argv: list[str] | None=None) -> None
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L26_account_hygiene.py
```

## L27 — Tax tracking

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** —

> L27_tax_tracking.py — Tax estimation and 1099-ready export (execute_loop layer 27).
> 
> Storage: data/ledger/bets.parquet  (CSV fallback)
>          data/ledger/1099_export_<year>.csv
> 
> CLI:
>     python L27_tax_tracking.py report --year 2026
>     python L27_tax_tracking.py quarterly --year 2026 --quarter 2
>     python L27_tax_tracking.py export-1099 --year 2026 [--out path.csv]
> 
> Environment Variables:
>     FEDERAL_TAX_RATE  — Federal marginal tax rate applied to net gambling winnings.
>                         Float in [0, 1]. Default: 0.24 (24% bracket).
>     STATE_TAX_RATE    — State marginal tax rate applied to net gambling winnings.
>                         Float in [0, 1]. Default: 0.00 (no state tax; set for
>                         your jurisdiction, e.g. 0.05 for 5%).

### Public API

```python
class TaxBucket
```

```python
def compute_tax_buckets(year: int) -> list[TaxBucket]
```
_Return one TaxBucket per source_type found in the ledger for *year*._

```python
def estimate_quarterly_payment(year: int, quarter: int) -> dict
```
_Estimate tax payment due for a specific calendar quarter._

```python
def export_1099_ready(year: int, out_path: Optional[str]=None) -> str
```
_Write a 1099-ready CSV with one row per source_type bucket._

```python
def annual_tax_report(year: int) -> dict
```
_Return a full annual tax summary dict._

```python
def main() -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `FEDERAL_TAX_RATE` | `'0.24'` |
| `STATE_TAX_RATE` | `'0.00'` |

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L27_tax_tracking.py
```

## L28 — Withdrawal automation

**Status:** `shipped` | **Tests:** 15/15 | **LOC:** —

> L28_withdrawal_automation.py — Withdrawal Automation (execute_loop layer 28).
> 
> Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
> env-var list).  Per-layer flag checked: withdrawal (WITHDRAWAL_LIVE_ENABLED).
> Env var is kept as fallback for backward compatibility when L44 is absent
> (soft-import pattern ensures behavior is identical if L44 is absent).
> 
> Monitors per-book balances and recommends / queues / executes withdrawals when
> a balance exceeds the per-book target by more than the configured buffer.
> 
> Public API:
>     compute_withdrawal_candidates(account_balances, target_max_per_book) -> list[WithdrawalCandidate]
>     execute_withdrawal(book, amount, user_token) -> dict
>     queue_withdrawal_for_review(candidate) -> str   # returns queue_id
>     get_pending_withdrawals() -> list[dict]
> 
> CLI:
>     python L28_withdrawal_automation.py recommend
>     python L28_withdrawal_automation.py queue --book dk --amount 5000
>     python L28_withdrawal_automation.py execute --queue-id X --token WITHDRAW_AUTHORIZED
>     python L28_withdrawal_automation.py list-pending
> 
> Paper vs Live Mode (MODE GATING):
>     This module is paper-by-default. The module-level constant ``PAPER_MODE = True``
>     expresses this intent. All withdrawal executions record entries with
>     status='queued_paper' unless live mode is explicitly enabled via the env var
>     below. Live mode must never be enabled in automated/CI contexts.
> 
> Environment Variables:
>     WITHDRAWAL_LIVE_ENABLED — Set to "1" to enable live withdrawal execution.
>         Default: "0" (paper mode). When unset or "0", execute_withdrawal records
>         entries with status='queued_paper' and does not call any book API.
>         Required to be absent (or "0") for all paper / simulation runs.

### Public API

```python
class WithdrawalCandidate
```

```python
def compute_withdrawal_candidates(account_balances: dict[str, float], target_max_per_book: Optional[dict[str, float]]=None) -> list[WithdrawalCandidate]
```
_Return one WithdrawalCandidate per book whose balance exceeds target * BUFFER_MULTIPLIER._

```python
def execute_withdrawal(book: str, amount: float, user_token: str, *, ledger_path: Path=LEDGER_PATH) -> dict
```
_Validate and record a withdrawal._

```python
def queue_withdrawal_for_review(candidate: WithdrawalCandidate, *, ledger_path: Path=LEDGER_PATH) -> str
```
_Queue a WithdrawalCandidate for human review._

```python
def get_pending_withdrawals(*, ledger_path: Path=LEDGER_PATH) -> list[dict]
```
_Return all entries with status in _ACTIVE_STATUSES._

```python
def main() -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `PAPER_MODE` | `True` |
| `WITHDRAWAL_LIVE_ENABLED` | `'0'` |

### Paper vs Live Mode

```
Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
env-var list).  Per-layer flag checked: withdrawal (WITHDRAWAL_LIVE_ENABLED).
Env var is kept as fallback for backward compatibility when L44 is absent
(soft-import pattern ensures behavior is identical if L44 is absent).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L28_withdrawal_automation.py
```

## L29 — Multi-account orchestrator

**Status:** `gated` | **Tests:** — | **LOC:** —

_(gated — no module)_

## L30 — DFS contest selector

**Status:** `shipped` | **Tests:** 50/50 | **LOC:** 237

> L30_contest_selector.py — DFS contest scoring, ranking, and budget allocation.
> 
> Scores each contest using a model edge + field-quality framework, routes budget
> toward cash vs GPP by edge tier, and sizes entry counts per Kelly-inspired logic.
> 
> Public API
> ----------
>     ContestEV                  dataclass
>     score_contest(contest, model_edge_pct, field_quality) -> ContestEV
>     rank_contests(contests, budget, model_edge_pct, field_quality) -> list[ContestEV]
>     recommend_entry_split(budget, ranked, max_pct_per_contest) -> dict

### Public API

```python
class ContestEV
```

```python
def score_contest(contest: dict, model_edge_pct: float, field_quality: float=0.5, _budget_hint: float=1000.0) -> ContestEV
```
_Score a single contest and return a ContestEV._

```python
def rank_contests(contests: List[dict], budget: float, model_edge_pct: float=5.0, field_quality: float=0.5) -> List[ContestEV]
```
_Score all contests and return sorted by expected_roi DESC._

```python
def recommend_entry_split(budget: float, ranked: List[ContestEV], max_pct_per_contest: float=0.2) -> Dict[str, Dict[str, float]]
```
_Allocate budget across contests._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L30_contest_selector.py
```

## L31 — Ownership projection model

**Status:** `shipped` | **Tests:** 14/14 | **LOC:** 347

> L31_ownership.py — Ownership Projection Model (v1 heuristic).
> 
> Estimates DFS contest ownership percentages for players on a slate using
> salary value, position ranking, star premium, and late-news boosts.
> 
> Public API
> ----------
>     predict_ownership(slate, fpts_data, *, version) -> dict[str, float]
>     load_ownership(date) -> dict[str, float] | None
>     compute_value_score(salary, projected_fpts) -> float
>     heuristic_ownership_v1(slate, fpts_data) -> dict[str, float]

### Public API

```python
def compute_value_score(salary: float, projected_fpts: float) -> float
```
_Return FPTS-per-$1000 value score._

```python
def heuristic_ownership_v1(slate: SlateContest, fpts_data: Dict[str, FPTSDistribution]) -> Dict[str, float]
```
_Compute v1 heuristic ownership percentages._

```python
def load_ownership(date: Optional[str]=None, *, ownership_dir: Path=_OWNERSHIP_DIR) -> Optional[Dict[str, float]]
```
_Load persisted ownership dict for a date._

```python
def predict_ownership(slate: SlateContest, fpts_data: Dict[str, FPTSDistribution], *, version: str='v1', _ownership_dir: Path=_OWNERSHIP_DIR) -> Dict[str, float]
```
_Predict contest ownership percentages for a slate._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L31_ownership.py
```

## L32 — Stack correlation engine

**Status:** `shipped` | **Tests:** 14/14 | **LOC:** 261

> L32_stack_correlation.py — Stack Correlation Engine (BUILD L32).
> 
> Identifies correlated player stacks within a DFS slate and recommends
> bet overlays for high-correlation lineups.
> 
> Public API
> ----------
>     compute_team_stack_correlations(team, fpts_data, *, min_correlation) -> StackCorrelation | None
>     identify_game_stacks(slate, fpts_data, min_correlation) -> list[StackCorrelation]
>     recommend_stack_bets(stack, current_lines) -> list[dict]
> 
> CLI
> ---
>     python L32_stack_correlation.py analyze --slate path.json --fpts path.json
>     python L32_stack_correlation.py recommend --team LAL --lines path.json

### Public API

```python
class StackCorrelation
```
_Encapsulates a correlated player stack for a single team._

```python
def compute_team_stack_correlations(team: str, fpts_data: Dict[str, dict], *, min_correlation: float=0.3) -> Optional[StackCorrelation]
```
_Compute stack correlations for all players on a given team._

```python
def identify_game_stacks(slate: dict, fpts_data: Dict[str, dict], min_correlation: float=0.3) -> List[StackCorrelation]
```
_Identify stacks for every team appearing in a slate._

```python
def recommend_stack_bets(stack: StackCorrelation, current_lines: Dict[str, dict]) -> List[dict]
```
_Generate OVER bet recommendations for top players in a stack._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L32_stack_correlation.py
```

## L33 — Sell-to-close optimizer

**Status:** `shipped` | **Tests:** 23/23 | **LOC:** —

> L33_sell_to_close.py — Sell-to-Close Optimizer for live prediction-market positions.
> 
> Given an open position and the current bid/ask quote, decides whether to HOLD,
> SELL (full position), or SELL_PARTIAL (half the position) by comparing the
> market's current value against the model's expected settlement value.
> 
> Public API
> ----------
>     CloseDecision                 dataclass
>     evaluate_close_decision(position, current_quote, model_p, time_to_settle_min,
>                             *, model_p_var=None) -> CloseDecision
>     score_market_value_now(position, current_quote) -> float
>     score_hold_to_settle(position, model_p) -> float
> 
> CLI
> ---
>     python L33_sell_to_close.py evaluate \
>         --position '{"position_id":"p1","qty":100,"entry_price":0.50,"side":"YES"}' \
>         --quote '{"bid_price":0.70,"ask_price":0.72,"bid_size":50}' \
>         --model-p 0.75 \
>         [--time 30] \
>         [--model-p-var 0.03]
> 
> Environment Variables
> ---------------------
> L33_PAPER_MODE
>     When set to "1", "true", or "yes" (case-insensitive), the module operates in
>     paper mode.  Decisions are computed normally but the mode is logged on every
>     SELL/SELL_PARTIAL action so callers can gate live order submission.  Defaults
>     to paper mode when the variable is absent (safe default).
> 
> L33_EVENT_BUS_DISABLED
>     When set to "1", "true", or "yes" (case-insensitive), event publication is
>     skipped entirely even if L46 is available.  Useful for offline / unit-test
>     environments where importing L46 is undesirable.
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> L33 reads L33_PAPER_MODE at module import time.  The resolved mode is available
> as the module-level boolean ``PAPER_MODE`` (True = paper, False = live).
> 
> In paper mode:
>   - All decision logic runs identically to live mode.
>   - SELL and SELL_PARTIAL actions log a [PAPER] prefix so operators can
>     distinguish simulated closes from real executions.
>   - The "close.recommended" EventBus event is still published; downstream
>     layers (e.g. L34, L44) are responsible for gating real order submission.
> 
> In live mode:
>   - Behaviour is identical; L33 itself does not submit orders.  Live gating
>     belongs to the submission layer (L44).
> 
> Event Publication
> -----------------
> When ``evaluate_close_decision`` returns action "SELL" or "SELL_PARTIAL", L33
> publishes a "close.recommended" event to the L46 EventBus default bus:
> 
>     {
>         "position_id":   str   — position identifier
>         "player":        str   — player name (from position["player"], or "")
>         "stat":          str   — stat label (from position["stat"], or "")
>         "current_price": float — bid_price at decision time
>         "entry_price":   float — original entry price
>         "unrealized_pnl": float — expected_pnl_now at decision time
>         "reason":        str   — decision_reason ("lock_gain" | "de_risk_marginal")
>         "model_p_var":   float | None — variance signal passed to evaluate_close_decision
>         "recommended_at": str  — ISO 8601 UTC timestamp
>     }
> 
> HOLD decisions do not publish any event.  Publication failures are caught and
> logged as warnings so that a broken bus never prevents the CloseDecision from
> being returned to the caller.

### Public API

```python
class CloseDecision
```

```python
def score_market_value_now(position: dict, current_quote: dict) -> float
```
_Return the USD value of selling the position at the current bid price._

```python
def score_hold_to_settle(position: dict, model_p: float) -> float
```
_Return the model-expected USD value at settlement._

```python
def evaluate_close_decision(position: dict, current_quote: dict, model_p: float, time_to_settle_min: int, *, model_p_var: Optional[float]=None) -> CloseDecision
```
_Evaluate whether to close (sell) a position, hold it, or sell it partially._

```python
def main(argv=None) -> int
```

### Paper vs Live Mode

```
L33_PAPER_MODE
    When set to "1", "true", or "yes" (case-insensitive), the module operates in
    paper mode.  Decisions are computed normally but the mode is logged on every
    SELL/SELL_PARTIAL action so callers can gate live order submission.  Defaults
    to paper mode when the variable is absent (safe default).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L33_sell_to_close.py
```

## L34 — Variance budgeter

**Status:** `shipped` | **Tests:** 35/35 | **LOC:** —

> L34 Variance Budgeter — Mean-variance portfolio allocation across betting buckets.
> 
> Public API:
>     compute_daily_allocation(total_bankroll, edges, stds, correlations, max_weight_per_bucket)
>         -> list[Allocation]
>     mean_variance_optimize(expected_returns, stds, correlations, max_weight)
>         -> dict[str, float]
>     coordinate_with_sell_to_close(current_positions, variance_budget)
>         -> list[dict]  — positions suggested for closure, ranked by variance contribution
> 
> Environment Variables:
>     None.  L34 is a pure in-memory computation layer; it writes no files.
> 
> Paper vs Live Mode:
>     L34 produces allocation recommendations only — it does not submit orders.
>     The caller (L33 sell-to-close or the execution router) is responsible for
>     acting on the returned suggestions in either paper or live mode.
> 
> L33 Integration:
>     coordinate_with_sell_to_close() is the bridge to L33 (sell-to-close engine).
>     Pass the current open positions with their variance footprints; L34 returns
>     a prioritised close list whenever the portfolio variance exceeds the budget.

### Public API

```python
class Allocation
```

```python
def mean_variance_optimize(expected_returns: dict[str, float], stds: dict[str, float], correlations: Optional[dict[str, dict[str, float]]]=None, max_weight: float=0.6) -> dict[str, float]
```
_Maximise Sharpe = w'μ / sqrt(w'Σw) subject to sum(w)=1, 0≤w_i≤max_weight._

```python
def compute_daily_allocation(total_bankroll: float, edges: Optional[dict[str, float]]=None, stds: Optional[dict[str, float]]=None, correlations: Optional[dict[str, dict[str, float]]]=None, max_weight_per_bucket: float=0.6) -> list[Allocation]
```
_Compute optimal daily dollar allocation across betting buckets._

```python
def coordinate_with_sell_to_close(current_positions: list, variance_budget: float) -> list[dict]
```
_Return positions suggested for closure, ranked by variance contribution._

```python
def main() -> None
```

### Paper vs Live Mode

```
Paper vs Live Mode:
    L34 produces allocation recommendations only — it does not submit orders.
    The caller (L33 sell-to-close or the execution router) is responsible for
    acting on the returned suggestions in either paper or live mode.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L34_variance_budgeter.py
```

## L35 — Risk-of-ruin monitor

**Status:** `shipped` | **Tests:** 11/11 | **LOC:** —

> L35_risk_of_ruin.py — Risk-of-Ruin Monitor (BUILD L35).
> 
> Monte Carlo simulation of bankroll survival over a rolling 30-day window.
> Reads the L07 bets ledger for daily-return estimation; alerts via L22.
> 
> Public API
> ----------
>     RuinReport                  dataclass
>     run_simulation(...)         Monte Carlo over a daily-return distribution
>     estimate_daily_return_dist_from_ledger(window_days) -> dict
>     alert_on_high_ruin_risk(report, threshold) -> bool
> 
> CLI
> ---
>     python L35_risk_of_ruin.py simulate [--bankroll N --days N --sims N]
>     python L35_risk_of_ruin.py report
>     python L35_risk_of_ruin.py alert

### Public API

```python
class RuinReport
```

```python
def estimate_daily_return_dist_from_ledger(window_days: int=30) -> dict
```
_Estimate daily-return distribution from the L07 bets ledger._

```python
def run_simulation(initial_bankroll: float, daily_return_dist: dict, n_sims: int=10000, n_days: int=30, ruin_threshold_pct: float=0.5) -> RuinReport
```
_Run a Monte Carlo ruin simulation._

```python
def alert_on_high_ruin_risk(report: RuinReport, threshold: float=0.05) -> bool
```
_Send an alert if p_ruin_30d exceeds threshold._

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L35_risk_of_ruin.py
```

## L36 — Edge-erosion watcher

**Status:** `shipped` | **Tests:** 20/20 | **LOC:** —

> L36_edge_erosion.py — Edge-Erosion Watcher (execute_loop layer 36).
> 
> Monitors betting angles for EV degradation over rolling windows.
> Automatically quarantines angles that show statistically-significant
> negative edge, with manual unquarantine requiring a user token.
> 
> Storage:
>     data/ledger/quarantined_angles.json  — quarantine state (atomic write)
>     data/ledger/edge_erosion_report_<date>.json — daily snapshot
> 
> CLI:
>     python L36_edge_erosion.py report
>     python L36_edge_erosion.py quarantine --angle-key X --reason "manual"
>     python L36_edge_erosion.py unquarantine --angle-key X --token UNQUARANTINE_OK
>     python L36_edge_erosion.py list-quarantined
> 
> Event Publication
> -----------------
> When a per-stat erosion crosses the detection threshold, L36 publishes to
> the shared L46 EventBus (if one has been injected via ``set_event_bus``):
> 
>     Event name : "edge_erosion.detected"
>     Payload fields:
>         stat          – stat name derived from angle_key (str)
>         current_edge  – observed_ev_pct for this angle (float)
>         baseline_edge – expected_ev_pct for this angle (float)
>         erosion_pct   – absolute gap (baseline - current, float)
>         threshold     – the erosion gap threshold used (float, default 5.0)
>         severity      – "QUARANTINED" | "WARN" (str)
>         window_days   – window_n used when computing metrics (int)
>         detected_at   – ISO 8601 UTC timestamp (str)
> 
> Publisher failures are silently swallowed so reports are never interrupted.
> 
> Environment Variables
> ---------------------
> None required.  All configuration is provided programmatically:
>     • L36 reads ledger paths from module-level constants (_BETS_PARQUET,
>       _BETS_CSV, _QUARANTINE_FILE) which tests monkeypatch via module attrs.
>     • The L46 EventBus instance is injected via set_event_bus(); L36 does
>       NOT read any env vars at import time.

### Public API

```python
def set_event_bus(bus) -> None
```
_Inject an L46 EventBus instance for edge_erosion.detected events._

```python
class AngleMetric
```

```python
def compute_angle_metrics(window_n: int=50, min_n: int=30) -> list[AngleMetric]
```
_Compute AngleMetric for each angle_key in the settled ledger._

```python
def quarantine_angle(angle_key: str, reason: str, n_bets: int=0, observed_ev: float=0.0) -> None
```
_Append angle_key to quarantine state (idempotent)._

```python
def unquarantine_angle(angle_key: str, user_token: str) -> None
```
_Remove angle_key from quarantine state._

```python
def is_quarantined(angle_key: str) -> bool
```
_Return True if angle_key is currently in the quarantine list._

```python
def daily_edge_report() -> dict
```
_Compute all angle metrics and write a dated JSON snapshot._

```python
def main(argv=None) -> int
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L36_edge_erosion.py
```

## L37 — Postmortem agent

**Status:** `shipped` | **Tests:** 16/16 | **LOC:** —

> L37_postmortem.py — Automated Postmortem Agent (execute_loop layer 37).
> 
> Detects betting incidents (large loss, losing streak, model drift), categorises
> each losing bet to a root cause, writes a Markdown postmortem to
> data/ledger/postmortems/, and surfaces a root-cause hypothesis + remediation.
> 
> Public API
> ----------
>     PostmortemReport            dataclass
>     detect_incidents(window_days) -> list[dict]
>     run_postmortem(losing_bets)   -> PostmortemReport
>     categorize_losses(bets)       -> dict[str, int]
> 
> CLI
> ---
>     python L37_postmortem.py detect [--window 1]
>     python L37_postmortem.py run --losing-bets path.json
>     python L37_postmortem.py list
> 
> Event Publication (L46 EventBus)
> ---------------------------------
> L37 publishes two event types via the L46 default bus (soft-import; bus absence
> is non-fatal — detection and postmortem behaviour are unchanged).
> 
> ``incident.opened``
>     Emitted once per new incident returned by detect_incidents().
>     Payload fields:
>         incident_id  : str   — UUID4 fragment (8 chars) generated for the incident
>         loss_pattern : str   — trigger_type value ("large_loss", "losing_streak", …)
>         bet_count    : int   — number of bets in the incident
>         total_loss   : float — sum of pnl for the incident's bets (negative)
>         avg_clv      : float | None — average CLV if present in the incident dict
>         detected_at  : str  — ISO 8601 UTC timestamp of detection
>         incident_class : str | None — IncidentClass.name from classify_incident()
>         severity       : str | None — "P0" | "P1" | "P2" | None
> 
> ``incident.classified``
>     Emitted by run_postmortem() after structured classification is complete.
>     Payload fields:
>         incident_id    : str
>         incident_class : str | None
>         severity       : str | None
>         remediation    : str | None — Remediation.suggestion
>         trigger_type   : str

### Public API

```python
class IncidentClass
```

```python
class Remediation
```

```python
def classify_incident(incident: dict) -> Optional[IncidentClass]
```
_Heuristic classification of an incident dict._

```python
def suggest_remediation(incident_class: IncidentClass) -> Optional[Remediation]
```
_Return the remediation suggestion for a given IncidentClass._

```python
def register_classifier(class_def: IncidentClass, classifier_fn: Callable[[dict], bool]) -> None
```
_Register a custom incident class and its classifier function._

```python
def register_remediation(remediation: Remediation) -> None
```
_Register or override a remediation for a given class_name._

```python
class PostmortemReport
```

```python
def detect_incidents(window_days: int=1) -> list[dict]
```
_Return list of incident dicts detected in the last *window_days* days._

```python
def categorize_losses(bets: list[dict]) -> dict[str, int]
```
_Assign the first matching cause to each bet; return cause tallies._

```python
def run_postmortem(losing_bets: list[dict], trigger_type: str='large_loss', pnl: Optional[float]=None, bankroll: Optional[float]=None, incident: Optional[dict]=None) -> PostmortemReport
```
_Categorise *losing_bets*, build the report, write Markdown, return dataclass._

```python
def main() -> None
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L37_postmortem.py
```

## L38 — Health dashboard

**Status:** `shipped` | **Tests:** 12/12 | **LOC:** —

> L38_health_dashboard.py — System Health Dashboard (execute_loop layer 38).
> 
> Runs a registry of named checks against live system resources and produces a
> HealthReport with overall HEALTHY / DEGRADED / FAILED status.
> 
> Public API
> ----------
>     HealthCheck     dataclass
>     HealthReport    dataclass
>     run_all_checks() -> HealthReport
>     get_latest_health() -> HealthReport  # 60-second in-process cache
>     run_check(name) -> HealthCheck       # single named check
> 
> CLI
> ---
>     python L38_health_dashboard.py check [--name <check>]
>     python L38_health_dashboard.py serve [--port 9876]
>     python L38_health_dashboard.py once   # exit 0/1/2 = HEALTHY/DEGRADED/FAILED
> 
> Environment Variables
> ---------------------
>     HEALTH_FILE     — Override path for system_health.json persistence file.
>                       Default: <project_root>/data/ledger/system_health.json
>     HEALTH_CACHE_TTL — In-process cache TTL in seconds before re-reading disk.
>                       Default: 60
>     HEALTH_PORT     — Default HTTP server port when --port is not given.
>                       Default: 9876

### Public API

```python
class HealthCheck
```

```python
class HealthReport
```

```python
def register(name: str, severity: str)
```
_Decorator — register a zero-arg function as a named health check._

```python
def run_all_checks() -> HealthReport
```

```python
def get_latest_health() -> HealthReport
```

```python
def run_check(name: str) -> HealthCheck
```

```python
def main(argv=None)
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `HEALTH_FILE` | `str(PROJECT_DIR / 'data' / 'ledger' / 'system_health.json')` |
| `HEALTH_CACHE_TTL` | `'60'` |

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L38_health_dashboard.py
```

## L39 — Execution backtest harness

**Status:** `shipped` | **Tests:** 19/19 | **LOC:** —

> L39 Execution Backtest Harness — simulate historical bet execution vs real closing lines.
> 
> Public API:
>     run_exec_backtest(lines_csv, *, initial_bankroll, kelly_frac, edge_threshold_pct, save)
>     compute_per_stat_breakdown(bets_df)
>     compute_drawdown_series(pnl_series)
>     bootstrap_ci(returns, n)
> 
> Run:
>     python L39_exec_backtest.py run --lines path.csv --kelly 0.25 --edge 5.0
>     python L39_exec_backtest.py compare --runs id1,id2
> 
> Environment Variables:
>     none

### Public API

```python
class BacktestRun
```

```python
def compute_drawdown_series(pnl_series: List[float]) -> Tuple[float, List[float]]
```
_Return (max_drawdown, drawdown_list) from a running P&L series._

```python
def bootstrap_ci(returns: List[float], n: int=2000, seed: int=42) -> Tuple[float, float]
```
_Bootstrap 95% CI on mean ROI._

```python
def compute_per_stat_breakdown(bets_df: List[Dict[str, Any]]) -> Dict[str, Dict]
```
_Aggregate per-stat hit rate, ROI, n_bets from a list of bet dicts._

```python
def run_exec_backtest(lines_csv: str, *, initial_bankroll: float=100000.0, kelly_frac: float=0.25, edge_threshold_pct: float=5.0, save: bool=True, _predict_fn=None, _quantile_fn=None, _build_row_fn=None, _resolve_id_fn=None) -> BacktestRun
```
_Run the execution backtest and return a BacktestRun dataclass._

```python
def main() -> None
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L39_exec_backtest.py
```

## L40 — Multi-model dispatcher

**Status:** `shipped` | **Tests:** 29/29 | **LOC:** —

> L40_multi_model_dispatcher.py — Unified routing layer for per-game prop models.
> 
> Reads dispatch_routing.json to decide which model variant handles each stat,
> then delegates to the appropriate predictor (blend / q50_lgb / q50_xgb /
> multitask_mlp). Falls back to blend with a WARN on any load/import error.
> 
> Public API
> ----------
>     get_routing()                        -> dict[str, ModelRoute]
>     predict_dispatched(stat, row, ...)   -> float | None
>     predict_quantiles_dispatched(...)    -> dict | None
>     update_routing(stat, variant, ...)   -> None
>     best_routing_from_wf_results()       -> dict[str, str]
> 
> CLI
> ---
>     python L40_multi_model_dispatcher.py status
>     python L40_multi_model_dispatcher.py refresh
>     python L40_multi_model_dispatcher.py set --stat ast --variant blend [--notes ...]
> 
> Environment Variables
> ---------------------
>     L40_SLOW_THRESHOLD_MS : int, default 100
>         Per-dispatch latency threshold in milliseconds.  When a predict_dispatched
>         call exceeds this value, a ``"model.slow"`` event is published to L46 in
>         addition to the normal ``"model.routed"`` event.  Set to 0 to always emit
>         slow events; set to a very large value to effectively disable slow alerts.
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
>     L40 is paper/live-agnostic — the same champion/challenger/A-B routing table
>     applies in both modes.  The routing decision (which model variant to call) does
>     not depend on SUBMISSION_MODE or any live-data flag.  Mode enforcement is the
>     responsibility of downstream layers (e.g. L44).  L40 never reads nor writes any
>     SUBMISSION_MODE environment variable.
> 
> Event Publication
> -----------------
>     L40 publishes to L46 (EventBus) after every successful predict_dispatched call:
> 
>     ``"model.routed"`` — always emitted on dispatch:
>         {
>             "request_id": str,        # UUID4 per-call identifier
>             "model_variant": str,     # variant actually used (post-fallback)
>             "is_champion": bool,      # True when variant == HARDCODED_DEFAULTS[stat][0]
>             "is_challenger": bool,    # True when variant != HARDCODED_DEFAULTS[stat][0]
>             "latency_ms": float,      # wall-clock ms for the predict call
>             "routed_at": str,         # ISO 8601 UTC timestamp
>         }
> 
>     ``"model.slow"`` — additionally emitted when latency_ms > L40_SLOW_THRESHOLD_MS:
>         {
>             "model_variant": str,
>             "latency_ms": float,
>             "threshold_ms": float,
>             "request_id": str,
>         }
> 
>     L46 import failures are swallowed so that a missing EventBus never breaks
>     production predictions.

### Public API

```python
class ModelRoute
```

```python
def get_routing(path: Path=ROUTING_PATH) -> Dict[str, ModelRoute]
```
_Load routing from JSON; build + write defaults if missing or corrupt._

```python
def predict_dispatched(stat: str, prediction_row: Any, model_dir: Optional[Path]=None, *, _routing_path: Path=ROUTING_PATH) -> Optional[float]
```
_Dispatch prediction for *stat* using the routed model variant._

```python
def predict_quantiles_dispatched(stat: str, prediction_row: Any, model_dir: Optional[Path]=None, *, _routing_path: Path=ROUTING_PATH) -> Optional[Dict[str, Optional[float]]]
```
_Return q10/q50/q90 for quantile variants; q50-only for blend/multitask._

```python
def update_routing(stat: str, model_variant: str, wf_mae: float, notes: str='', *, _routing_path: Path=ROUTING_PATH) -> None
```
_Update routing for *stat* and atomically persist to JSON._

```python
def best_routing_from_wf_results(wf_path: Path=WF_RESULTS_PATH, *, _routing_path: Path=ROUTING_PATH) -> Dict[str, str]
```
_Read walk-forward JSON and pick the best variant per stat._

```python
def main(argv=None) -> None
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `L40_SLOW_THRESHOLD_MS` | `'100'` |

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
    L40 is paper/live-agnostic — the same champion/challenger/A-B routing table
    applies in both modes.  The routing decision (which model variant to call) does
    not depend on SUBMISSION_MODE or any live-data flag.  Mode enforcement is the
    responsibility of downstream layers (e.g. L44).  L40 never reads nor writes any
    SUBMISSION_MODE environment variable.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L40_multi_model_dispatcher.py
```

## L41 — Integration harness (end-to-end)

**Status:** `shipped` | **Tests:** 23/23 | **LOC:** 996

> L41_integration_harness.py — End-to-end integration harness for the NBA execution loop.
> 
> Wires L01–L41 layers against a deterministic stub slate; no live API calls.
> SUBMISSION_MODE forced to "paper". Missing layers → SKIP. Critical failures → SKIP_DEPENDS.

### Public API

```python
class IntegrationHarness
```
_End-to-end integration harness for the NBA execution loop._

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `SUBMISSION_MODE` | `'paper'` |

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L41_integration_harness.py
```

## L42 — Production readiness checker

**Status:** `shipped` | **Tests:** 18/18 | **LOC:** 574

> L42_production_readiness.py — Production Readiness Checker for L1-L40.
> 
> Read-only: never modifies any audited module or data file.
> 
> Environment variables:
>     L42_DATA_DIR   Override project data/ path (default: PROJECT_ROOT/data/)
>     L42_STRICT     Set to "1" to exit 1 if any FAIL found (same as --strict CLI flag)

### Public API

```python
class CheckResult
```

```python
class LayerKPI
```

```python
class ReadinessReport
```

```python
def check_paper_default(layer: str, module_path: Path) -> CheckResult
```

```python
def check_atomic_writes(layer: str, module_path: Path) -> CheckResult
```

```python
def check_env_var_documentation(layer: str, module_path: Path) -> CheckResult
```

```python
def check_file_perms(data_dir: Path) -> list[CheckResult]
```

```python
class ReadinessChecker
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `L42_DATA_DIR` | `None` |
| `L42_STRICT` | `''` |

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L42_production_readiness.py
```

## L43 — Runbook generator

**Status:** `shipped` | **Tests:** 7/7 | **LOC:** —

> L43_runbook_generator.py — Runbook documentation generator for the execute_loop.
> 
> Reads every L*.py module via AST (never imports them) and writes RUNBOOK.md.
> 
> Environment variables
> ---------------------
>   None required. Defaults work out-of-the-box.
> 
> Invariants
> ----------
>   - Pure stdlib; no third-party imports.
>   - Only top-level (non-private) symbols are documented.
>   - Write is atomic: tmp file + os.replace so no partial state.
>   - L29 (gated, no module file) renders as a placeholder section.

### Public API

```python
class PublicSymbol
```

```python
class LayerInfo
```

```python
class RunbookGenerator
```

```python
def main(argv: Optional[list[str]]=None) -> int
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L43_runbook_generator.py
```

## L44 — Paper-mode helper library

**Status:** `shipped` | **Tests:** 19/19 | **LOC:** —

> L44_paper_mode.py — Single Source of Truth for Paper vs Live Mode.
> 
> Purpose:
>     Centralises all paper/live mode policy for the execute_loop.  Prior to L44
>     each layer (L05, L09, L10, L11, L12, L16, L28, …) maintained its own
>     inline env-var checks, module-level constants, or ad-hoc helper functions.
>     This made the policy diffuse and hard to audit.  L44 is the canonical
>     library that all layers will adopt.  Existing layers are unchanged in this
>     PR; they will migrate in future rounds.
> 
> Environment Variables:
>     SUBMISSION_MODE
>         Set to "live" (case-insensitive) to enable live mode globally.
>         Any other value (or absent) leaves the process in paper mode.
> 
>     KALSHI_LIVE_ENABLED
>         Set to "1" to enable live mode for the Kalshi exchange layer (L09).
> 
>     POLYMARKET_LIVE_ENABLED
>         Set to "1" to enable live mode for the Polymarket layer (L10).
> 
>     SPORTTRADE_LIVE_ENABLED
>         Set to "1" to enable live mode for the SportTrade layer (L11).
> 
>     PROPHET_LIVE_ENABLED
>         Set to "1" to enable live mode for the Prophet layer (L12).
> 
>     WITHDRAWAL_LIVE_ENABLED
>         Set to "1" to enable live mode for the Withdrawal Automation layer (L28).
> 
>     DK_LIVE_SUBMISSION_ENABLED
>         Set to "1" to enable live mode for the DraftKings submission path (L05).
> 
>     FD_LIVE_SUBMISSION_ENABLED
>         Set to "1" to enable live mode for the FanDuel submission path (L05).
> 
> Paper vs Live Mode Policy (MODE GATING):
>     L44 IS the canonical mode-gating library; it does not itself need a
>     PAPER_MODE constant since its public functions are the source of truth.
>     - Paper is the DEFAULT.  No environment variables need to be set.
>     - Live mode is opt-in and requires an EXPLICIT signal.
>     - is_paper_mode() returns False (i.e. live is active) if ANY of the
>       following conditions hold:
>         1. SUBMISSION_MODE == "live"  (case-insensitive)
>         2. KALSHI_LIVE_ENABLED == "1"
>         3. POLYMARKET_LIVE_ENABLED == "1"
>         4. SPORTTRADE_LIVE_ENABLED == "1"
>         5. PROPHET_LIVE_ENABLED == "1"
>         6. WITHDRAWAL_LIVE_ENABLED == "1"
>         7. DK_LIVE_SUBMISSION_ENABLED == "1"
>         8. FD_LIVE_SUBMISSION_ENABLED == "1"
>     - is_live_for_layer() checks ONLY the per-layer flag for the named layer.
>       It does NOT inherit from SUBMISSION_MODE.  Each layer must be opted in
>       independently.
>     - assert_paper_mode() provides a hard guard for code paths that must never
>       execute in live mode (e.g. test harnesses, dry-run simulations).
> 
> Usage example:
>     from scripts.execute_loop.L44_paper_mode import (
>         is_paper_mode,
>         is_live_for_layer,
>         assert_paper_mode,
>         PaperModeRequired,
>     )
> 
>     if is_paper_mode():
>         log_paper_order(order)
>     else:
>         exchange_client.submit(order)
> 
>     # Per-layer check inside L09
>     if is_live_for_layer("kalshi"):
>         ...
> 
>     # Guard in test harness
>     assert_paper_mode("nightly_retrain_dry_run")

### Public API

```python
class PaperModeRequired(RuntimeError)
```
_Raised by assert_paper_mode() when the process is in live mode._

```python
def is_paper_mode() -> bool
```
_Return True if the current process is in paper mode._

```python
def is_live_for_layer(layer_name: str) -> bool
```
_Return True if a specific layer is in live mode._

```python
def assert_paper_mode(operation: str='operation') -> None
```
_Raise PaperModeRequired if the current process is NOT in paper mode._

### Paper vs Live Mode

```
L44_paper_mode.py — Single Source of Truth for Paper vs Live Mode.

Purpose:
    Centralises all paper/live mode policy for the execute_loop.  Prior to L44
    each layer (L05, L09, L10, L11, L12, L16, L28, …) maintained its own
    inline env-var checks, module-level constants, or ad-hoc helper functions.
    This made the policy diffuse and hard to audit.  L44 is the canonical
    library that all layers will adopt.  Existing layers are unchanged in this
    PR; they will migrate in future rounds.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L44_paper_mode.py
```

## L45 — Daily operator checklist

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** —

> L45_daily_checklist.py — Operator Daily Checklist Runner (execute_loop layer 45).
> 
> Purpose
> -------
> A single CLI tool the operator runs before/during/after each game day to walk
> through the standard operational routine and report readiness for each phase.
> Wraps L38 (health dashboard), L42 (production readiness checker), and L41
> (integration harness) into a coherent operator-facing workflow.
> 
> Environment Variables
> ---------------------
> None required directly.  Underlying layers read their own env vars as
> documented in their respective module docstrings.
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> L45 reads paper/live state via L44.is_paper_mode() and surfaces it in every
> checklist run, but is itself mode-agnostic — it is an operator observation
> tool that does not gate or alter live-mode behaviour.  The paper/live toggle
> lives entirely in L44; L45 only reports the observed state.  Default report
> path is scripts/execute_loop/checklist_YYYY-MM-DD_<phase>.md unless
> overridden by --out.
> 
> CLI
> ---
>     python L45_daily_checklist.py morning
>     python L45_daily_checklist.py midday --out /tmp/midday.md
>     python L45_daily_checklist.py postgame
> 
> Exit codes: 0 = all PASS/WARN/SKIP; 1 = any FAIL.

### Public API

```python
class ChecklistItem
```

```python
class DailyChecklist
```
_Run the per-phase operator checklist and produce a markdown report._

```python
def main(argv=None) -> int
```

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
L45 reads paper/live state via L44.is_paper_mode() and surfaces it in every
checklist run, but is itself mode-agnostic — it is an operator observation
tool that does not gate or alter live-mode behaviour.  The paper/live toggle
lives entirely in L44; L45 only reports the observed state.  Default report
path is scripts/execute_loop/checklist_YYYY-MM-DD_<phase>.md unless
overridden by --out.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L45_daily_checklist.py
```

## L46 — EventBus (cross-layer routing)

**Status:** `shipped` | **Tests:** 18/18 | **LOC:** —

> L46_event_bus.py — Cross-layer EventBus for the autonomous NBA execution loop.
> 
> Purpose
> -------
> Formalises the inter-layer notification pattern used across the execute_loop
> stack.  Instead of each layer soft-importing its target layer directly (creating
> an implicit, hard-to-audit dependency graph), publishers emit named Events and
> subscribers register handlers against name patterns.  This makes the dependency
> graph explicit, observable, and testable without changing existing direct-call
> code paths (backward compatible — both approaches work simultaneously).
> 
> Environment Variables
> ---------------------
> None required.  The EventBus is configuration-free by design: callers pass a
> ``persistence_path`` at construction time when durable replay is needed.
> 
> Paper vs Live Mode (MODE GATING)
> ---------------------------------
> L46 is mode-agnostic — it routes events but has no live-mode behaviour itself.
> The ``live`` tokens that appear in payload examples (e.g. event names such as
> ``"bet.live"``) are arbitrary publisher-defined strings, not mode gates.
> L46 neither reads nor writes any SUBMISSION_MODE / LIVE_MODE environment
> variable and carries no conditional logic that differs between paper and live
> deployments.  Mode enforcement is the responsibility of the publishing layer
> (e.g. L44 asserts paper mode before any submission layer publishes).
> 
> Persistence Policy
> ------------------
> When a ``persistence_path`` (Path) is supplied to EventBus.__init__, every
> published Event is appended as a single JSONL line to that file.  We use plain
> ``open(path, "a")`` (append mode) rather than the atomic rename-replace pattern
> used for snapshot files.  This is safe because:
> 
>   1. Each line is a self-contained JSON object terminated by ``\n``.
>   2. On POSIX, writes ≤ PIPE_BUF (≥4 096 bytes) to ``O_APPEND`` files are
>      atomic at the kernel level.  A single serialised Event is always well under
>      this limit in practice.
>   3. On Windows (where PIPE_BUF guarantees do not apply), the EventBus is
>      single-threaded in the common deploy scenario (one process per layer), so
>      interleaving is not a concern.  For multi-process scenarios on Windows,
>      callers should use a dedicated persistence_path per process.
> 
> The atomic rename-replace pattern (_atomic_write_text) is reserved for cases
> where the *entire* file must be consistent (snapshots, config dumps).  For an
> append-only log it would require reading the full file on every publish, which
> is prohibitively expensive.

### Public API

```python
class Event
```
_An immutable event record emitted by a layer._

```python
class Subscription
```
_A registered handler bound to a name_pattern on a specific layer._

```python
class EventBus
```
_Pub/sub event bus with optional JSONL persistence and replay._

```python
def get_default_bus() -> EventBus
```
_Return the module-level EventBus singleton (created on first call)._

```python
def publish(name: str, source: str, payload: dict) -> Event
```
_Convenience wrapper: publish via the default bus singleton._

```python
def subscribe(name_pattern: str, handler: Callable[[Event], None], layer: str) -> Subscription
```
_Convenience wrapper: subscribe via the default bus singleton._

### Paper vs Live Mode

```
Paper vs Live Mode (MODE GATING)
---------------------------------
L46 is mode-agnostic — it routes events but has no live-mode behaviour itself.
The ``live`` tokens that appear in payload examples (e.g. event names such as
``"bet.live"``) are arbitrary publisher-defined strings, not mode gates.
L46 neither reads nor writes any SUBMISSION_MODE / LIVE_MODE environment
variable and carries no conditional logic that differs between paper and live
deployments.  Mode enforcement is the responsibility of the publishing layer
(e.g. L44 asserts paper mode before any submission layer publishes).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L46_event_bus.py
```

## L47 — Regression / drift detector

**Status:** `shipped` | **Tests:** 7/7 | **LOC:** 508

> L47_regression_detector.py — State Regression / Drift Detector for the execute-loop.
> 
> Purpose
> -------
> Reads ``scripts/execute_loop/state.json`` and the layers directory, then flags
> regressions that indicate the loop has broken or silently degraded between
> rounds.  Pure observability — never modifies any file.
> 
> Environment Variables
> ---------------------
>     None.
> 
> Paper vs Live Mode
> ------------------
> N/A — observability only; no money movement, no mode gating required.
> 
> What It Detects
> ---------------
> 1. **test_count_drop**
>    For each layer with multiple ship entries, compare consecutive ships'
>    ``tests`` strings (e.g. "12/12").  If the numerator *or* denominator falls,
>    flag P0.  Increases are healthy and ignored.
> 
> 2. **kpi_drop**
>    If a layer's latest ship has a ``stability_score`` key and it is lower than
>    an earlier ship's score, flag P1.  Also flags if any ship carries a
>    ``kpi_score`` that decreases across consecutive ships.
> 
> 3. **missing_module**
>    For every layer whose status is "shipped", check that a corresponding
>    ``L{N}_*.py`` file exists in the layers directory.  Gated layers (status
>    "gated") are skipped.  Missing file → P0.
> 
> 4. **missing_tests** (orphan tests inverse)
>    For every shipped layer whose latest ship records tests > 0, check that at
>    least one ``test_L{N}_*.py`` exists in ``tests/``.  Missing test file → P1.
> 
> 5. **ship_without_round**
>    Any ship entry that lacks a ``round`` field is a metadata gap → P2.
> 
> Public API
> ----------
>     Regression          frozen dataclass
>     RegressionReport    dataclass with to_markdown() / to_dict()
>     RegressionDetector  main engine
>     main(argv)          CLI entry point

### Public API

```python
class Regression
```
_A single detected regression or metadata issue._

```python
class RegressionReport
```
_Aggregated output of a full regression scan._

```python
def detect_test_count_drops(state_data: dict) -> list[Regression]
```
_Flag layers where a later ship has fewer passing or total tests than a prior ship._

```python
def detect_kpi_drops(state_data: dict, current_kpis: Optional[dict]=None) -> list[Regression]
```
_Flag layers where stability_score or kpi_score declined across ships._

```python
def detect_missing_modules(state_data: dict, layers_dir: Path) -> list[Regression]
```
_Flag shipped layers that have no corresponding L{N}_*.py file._

```python
def detect_orphan_tests(state_data: dict, layers_dir: Path) -> list[Regression]
```
_Flag shipped layers with tests > 0 that have no test_L{N}_*.py file._

```python
def detect_ship_without_round(state_data: dict) -> list[Regression]
```
_Flag ship entries that are missing a 'round' field._

```python
class RegressionDetector
```
_Orchestrates all regression checks against state.json + layers dir._

```python
def main(argv=None) -> int
```

### Paper vs Live Mode

```
Paper vs Live Mode
------------------
N/A — observability only; no money movement, no mode gating required.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L47_regression_detector.py
```

## L48 — Swish demo runner

**Status:** `shipped` | **Tests:** 7/7 | **LOC:** —

> L48_demo_runner.py — Stakeholder-facing end-to-end execute_loop demo.
> 
> Purpose:
>     Demonstrates the full execute_loop pipeline to external stakeholders (e.g.
>     Swish Analytics).  Ingests a stub NBA prop slate, runs through 10 annotated
>     stages (ingest → FPTS → lineup opt → EV scan → Kelly sizing → risk budget →
>     paper submit → settlement → CLV → summary), and writes a single rich
>     markdown artifact suitable for screen-recording or sharing.
> 
>     This is NOT a duplicate of L41 (CI testing) or L45 (operator checklist).
>     L48 is narrative-first: every stage carries a human-readable description,
>     intermediate data snapshots, timing, and an ASCII visualisation.
> 
> Env vars:
>     None required.  SUBMISSION_MODE must NOT be "live"; the module calls
>     L44.assert_paper_mode("demo") at startup and aborts gracefully if live
>     mode is detected.
> 
> Paper vs Live Mode (MODE GATING):
>     L48 is paper-mode strict by design.  L44.assert_paper_mode("demo") is
>     called at the top of DemoRunner.run() and refuses to execute if
>     SUBMISSION_MODE=live.  The ``live`` tokens flagged by static analysis are
>     inside the assert_paper_mode safety check itself (the stub fallback raises
>     RuntimeError when SUBMISSION_MODE=="live"), not a live-mode toggle that
>     permits live execution.  No real orders, bets, or exchange calls are ever
>     made — all submission stages are paper-mode simulations only.

### Public API

```python
class DemoStage
```

```python
class DemoReport
```

```python
class DemoRunner
```
_Stakeholder-facing execute_loop demo runner._

```python
def main(argv: Optional[List[str]]=None) -> int
```

### Environment Variables

| Name | Default / Value |
|------|----------------|
| `SUBMISSION_MODE` | `''` |

### Paper vs Live Mode

```
L44.assert_paper_mode("demo") at startup and aborts gracefully if live
    mode is detected.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L48_demo_runner.py
```

## L49 — State-of-loop summary generator

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** 644

> L49_state_summary.py — Execute-Loop State-of-the-Loop Summary Generator.
> 
> Purpose
> -------
> Aggregates observability data from multiple execute-loop layers into a single,
> board-room-friendly STATE_OF_LOOP.md document.  Pulls from:
> 
>   - state.json          round-by-round narrative + layer metadata
>   - L42 ReadinessChecker  per-layer KPI health scores
>   - L47 RegressionDetector  test-count drops, missing modules
>   - L41 integration harness  end-to-end coverage count
> 
> No external services are called; all inputs are local files or in-process
> Python APIs.  Safe to run at any time without side-effects on trading.
> 
> Environment Variables
> ---------------------
>     None.
> 
> Paper vs Live Mode
> ------------------
> N/A — observability only; no money movement or mode gating required.

### Public API

```python
class LoopSnapshot
```
_Immutable snapshot of loop health at a point in time._

```python
class LoopSummarizer
```
_Aggregates loop observability data into a LoopSnapshot + markdown doc._

```python
def main(argv=None) -> int
```
_Entry point: generate STATE_OF_LOOP.md (or JSON snapshot)._

### Paper vs Live Mode

```
Paper vs Live Mode
------------------
N/A — observability only; no money movement or mode gating required.
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L49_state_summary.py
```

## Cross-Reference Table

| Layer | Imports From |
|-------|-------------|
| `L03` | `L01`, `L02` |
| `L31` | `L01`, `L02` |
