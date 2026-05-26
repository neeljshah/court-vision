# Execute Loop Runbook

_Generated 2026-05-26 01:25 UTC — do not edit by hand._

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
- [Cross-Reference Table](#cross-reference-table)

## L01 — DK/FD slate ingester

**Status:** `shipped` | **Tests:** 24/24 | **LOC:** 437

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

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** 325

> L05_submission_engine.py — DFS Lineup Submission Engine (PAPER MODE).
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
> 
>     FD_API_KEY — FanDuel API key sent as the X-Api-Key header for FD live
>         submissions. Must be non-empty when SUBMISSION_MODE=live and book=fd.
>         Absent value causes _check_live_gates to block the submission.
> 
>     FD_LIVE_ENABLED — Safety flag that must equal "1" to permit live FanDuel
>         submissions. When absent or set to any other value, FD live submissions
>         are blocked regardless of FD_API_KEY. Defaults to disabled (not "1").
> 
> Paper vs Live Mode:
>     Default behavior is paper mode — no environment variables need to be set.
>     Live submission is gated by ALL of the following conditions being true:
>       1. SUBMISSION_MODE=live
>       2. USER_TOKEN is non-empty
>       3. For DK: DK_LIVE_ENABLED=1 AND DK_API_KEY is non-empty
>          For FD: FD_LIVE_ENABLED=1 AND FD_API_KEY is non-empty
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
| `DK_LIVE_ENABLED` | `None` |
| `DK_API_KEY` | `None` |
| `FD_LIVE_ENABLED` | `None` |
| `FD_API_KEY` | `None` |

### Paper vs Live Mode

```
L05_submission_engine.py — DFS Lineup Submission Engine (PAPER MODE).

Storage:
    data/ledger/submission_cache.json   — idempotency cache (TTL 24 h)
    data/ledger/paper_submissions.json  — paper-mode log
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

**Status:** `shipped` | **Tests:** 26/26 | **LOC:** —

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

**Status:** `shipped` | **Tests:** 13/13 | **LOC:** —

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

**Status:** `shipped` | **Tests:** 20/20 | **LOC:** 466

> L09_kalshi_client.py — Kalshi Exchange Client (PAPER MODE by default).
> 
> MODE GATING
> -----------
>   KALSHI_LIVE_ENABLED=1  AND  KALSHI_API_KEY  AND  KALSHI_API_KEY_ID  → LIVE
>   Else → PAPER (default)
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
| `KALSHI_LIVE_ENABLED` | `''` |
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

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** 387

> L10_polymarket_client.py — Polymarket CLOB client (PAPER MODE default).
> 
> Reads NBA prediction markets from Polymarket's Gamma + CLOB APIs.
> Default mode is PAPER — never touches private keys or real funds.
> LIVE mode requires explicit env vars AND --live flag from caller.
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
| `SPORTTRADE_LIVE_ENABLED` | `''` |
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

**Status:** `shipped` | **Tests:** 13/13 | **LOC:** 314

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
| `PROPHET_LIVE_ENABLED` | `''` |
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

**Status:** `shipped` | **Tests:** 14/14 | **LOC:** —

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
> Polls a live prediction engine, evaluates edge vs market quotes, and manages
> paper positions in data/ledger/paper_live_positions.json.  Real order
> submission is permanently gated behind the LIVE_TRADING_ENABLED env var
> (which should never be set in normal operation).
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
| `LIVE_TRADING_ENABLED` | `''` |

### Paper vs Live Mode

```
L16_live_trader.py — Live Trader (PAPER MODE STRICT).

Polls a live prediction engine, evaluates edge vs market quotes, and manages
paper positions in data/ledger/paper_live_positions.json.  Real order
submission is permanently gated behind the LIVE_TRADING_ENABLED env var
(which should never be set in normal operation).
```

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L16_live_trader.py
```

## L17 — Hedge calculator

**Status:** `shipped` | **Tests:** 9/9 | **LOC:** 363

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

**Status:** `shipped` | **Tests:** 11/11 | **LOC:** 431

> L18 Bankroll Manager — Kelly sizing, correlation-aware staking, kill switches.
> 
> Public API:
>     kelly_fraction(prob, odds_american) -> float
>     kelly_with_correlation(bets, corr_matrix) -> np.ndarray
>     get_bankroll_state() -> BankrollState
>     update_bankroll(pnl, notes) -> BankrollState
>     check_risk_limits(proposed_stake, correlation_key) -> tuple[bool, str]
>     reset_daily() -> None
>     reset_weekly() -> None
>     trip_kill_switch(reason) -> None
>     clear_kill_switch(user_token) -> None

### Public API

```python
class BetCandidate
```

```python
class BankrollState
```

```python
def kelly_fraction(prob: float, odds_american: int) -> float
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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L18_bankroll_manager.py
```

## L19 — CLV calculator + report

**Status:** `shipped` | **Tests:** 11/11 | **LOC:** 295

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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L19_clv_calculator.py
```

## L20 — Injury feed scraper

**Status:** `shipped` | **Tests:** 5/5 | **LOC:** 453

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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L20_injury_feed.py
```

## L21 — Lineup announcement watcher

**Status:** `shipped` | **Tests:** 5/5 | **LOC:** 308

> L21_lineup_watcher.py — Lineup Announcement Watcher (BUILD L21).
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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L21_lineup_watcher.py
```

## L22 — Slack/Discord alerting

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** —

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
>     ALERTS_RATE_LIMIT_PER_MIN
>         Maximum number of alerts dispatched per 60-second rolling window via
>         the token-bucket limiter. Excess alerts are enqueued and replayed via
>         flush_pending(). Integer; default 30.
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

### Environment Variables

| Name | Default / Value |
|------|----------------|
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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L24_nightly_retrain.py
```

## L25 — A/B shadow harness

**Status:** `shipped` | **Tests:** 10/10 | **LOC:** 309

> L25_ab_shadow.py — A/B Shadow Harness (execute_loop layer 25).
> 
> Storage:
>     data/shadow/_registry.json          — active variant registry
>     data/shadow/<variant_name>/
>         predictions.parquet             — (game_id, player, stat, predicted_q50, ts)
>         summary.json                    — written only when settled
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
def main(argv=None) -> int
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

**Status:** `shipped` | **Tests:** 15/15 | **LOC:** 249

> L28_withdrawal_automation.py — Withdrawal Automation (execute_loop layer 28).
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
> Paper vs Live Mode:
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
Paper vs Live Mode:
    This module is paper-by-default. The module-level constant ``PAPER_MODE = True``
    expresses this intent. All withdrawal executions record entries with
    status='queued_paper' unless live mode is explicitly enabled via the env var
    below. Live mode must never be enabled in automated/CI contexts.
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

**Status:** `shipped` | **Tests:** 19/19 | **LOC:** 263

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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L33_sell_to_close.py
```

## L34 — Variance budgeter

**Status:** `shipped` | **Tests:** 27/27 | **LOC:** 388

> L34 Variance Budgeter — Mean-variance portfolio allocation across betting buckets.
> 
> Public API:
>     compute_daily_allocation(total_bankroll, edges, stds, correlations, max_weight_per_bucket)
>         -> list[Allocation]
>     mean_variance_optimize(expected_returns, stds, correlations, max_weight)
>         -> dict[str, float]

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
def main() -> None
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

**Status:** `shipped` | **Tests:** 15/15 | **LOC:** 486

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

### Public API

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

**Status:** `shipped` | **Tests:** 7/7 | **LOC:** 598

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

### Public API

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
def run_postmortem(losing_bets: list[dict], trigger_type: str='large_loss', pnl: Optional[float]=None, bankroll: Optional[float]=None) -> PostmortemReport
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

**Status:** `shipped` | **Tests:** 25/25 | **LOC:** 489

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

### How to Run

```bash
conda run -n basketball_ai python scripts\execute_loop\L40_multi_model_dispatcher.py
```

## L41 — Integration harness (end-to-end)

**Status:** `shipped` | **Tests:** 11/11 | **LOC:** —

> L41_integration_harness.py — End-to-end integration harness for the autonomous NBA execution loop.
> 
> Purpose
> -------
> Wire every shipped layer (L01–L37) end-to-end against a deterministic stub slate
> and verify the full pipeline executes without live API calls.
> 
> Environment variables
> ---------------------
> SUBMISSION_MODE : forced to "paper" for every run (never "live" inside the harness).
> 
> Invariants
> ----------
> - No live API calls are made; all HTTP is blocked by design in stub mode.
> - All RNG is seeded via np.random.default_rng(seed) for full reproducibility.
> - Missing layers are soft-imported and result in SKIP stages, not failures.
> - Critical-stage failures propagate as SKIP_DEPENDS to downstream stages.

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

**Status:** `shipped` | **Tests:** 8/8 | **LOC:** 275

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

**Status:** `shipped` | **Tests:** 7/7 | **LOC:** 295

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

## Cross-Reference Table

| Layer | Imports From |
|-------|-------------|
| `L03` | `L01`, `L02` |
| `L31` | `L01`, `L02` |
