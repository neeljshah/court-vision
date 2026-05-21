"""
strategy_backtester.py — Strategy-level prop backtester with bankroll simulation.

Wraps the lower-level ``src.prediction.prop_backtester.load_historical_results``
loader to run a full walk-forward bankroll simulation for any single stat
category, returning a rich ``BacktestResult`` with hit-rate, ROI, max-drawdown,
and CLV metrics.

Public API
----------
    BacktestResult       — dataclass: per-stat backtest summary
    StrategyBacktester   — main class: backtest_prop_model(stat, seasons)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """
    Summary metrics for a single-stat strategy backtest.

    Fields
    ------
    stat            : Stat category backtested (e.g. 'pts', 'reb').
    seasons         : Season strings used to load data.
    n_predictions   : Total filtered records (stat match, non-None pred+actual).
    total_bets      : Records that cleared edge_threshold and received a wager.
    wins            : Bets where direction matched actual outcome.
    losses          : Bets that did not win.
    hit_rate        : wins / total_bets (0.0 when total_bets == 0).
    roi_pct         : (final_bankroll - starting_bankroll) / starting_bankroll * 100.
    clv             : Mean of per-record ``edge_pct`` where available.
                      NOTE: this is *predicted* edge vs the proxy line stored in
                      the residuals file — NOT true closing-line value (CLV).
                      Real CLV requires a historical market-closing-line feed;
                      that integration is tracked as a follow-up task.
    max_drawdown    : Largest peak-to-trough drop on the bankroll equity curve,
                      expressed as a fraction in [0.0, 1.0].
    final_bankroll  : Bankroll balance after all bets.
    """

    stat: str
    seasons: list
    n_predictions: int
    total_bets: int
    wins: int
    losses: int
    hit_rate: float
    roi_pct: float
    clv: float
    max_drawdown: float
    final_bankroll: float


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

_ODDS = -110          # standard US odds for sportsbook payouts
_BET_FRACTION = 0.02  # flat 2 % of current bankroll per bet


def _payout_multiplier(odds: int = _ODDS) -> float:
    """Return the decimal multiplier for a winning bet at American odds."""
    if odds < 0:
        return 100.0 / abs(odds)   # e.g. -110 → 0.9091
    return odds / 100.0            # e.g. +110 → 1.10


def _compute_max_drawdown(equity: List[float]) -> float:
    """
    Compute the maximum peak-to-trough drawdown on an equity curve.

    Returns a fraction in [0.0, 1.0].  Returns 0.0 for empty or single-point
    curves.
    """
    if len(equity) < 2:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
    return round(max_dd, 6)


class StrategyBacktester:
    """
    Strategy-level prop backtester with flat-bet bankroll simulation.

    Loads historical prediction records from ``prop_backtester.load_historical_results``,
    filters by stat, applies an edge threshold, walks a bankroll forward, and
    returns a ``BacktestResult`` with full performance metrics.

    Parameters
    ----------
    starting_bankroll : float
        Initial paper bankroll in dollars.  Default 1 000.
    edge_threshold : float
        Minimum absolute edge (|predicted - line| / line) to place a bet.
        Default 0.04 (4 %).
    """

    def __init__(
        self,
        starting_bankroll: float = 1000.0,
        edge_threshold: float = 0.04,
    ) -> None:
        self.starting_bankroll = starting_bankroll
        self.edge_threshold = edge_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def backtest_prop_model(
        self,
        stat: str,
        seasons: Optional[List[str]] = None,
    ) -> BacktestResult:
        """
        Backtest the prop model for *stat* across historical seasons.

        Algorithm
        ---------
        1. Load records via ``prop_backtester.load_historical_results(seasons)``.
        2. Filter to records matching *stat* with non-None ``predicted`` and ``actual``.
        3. Walk a bankroll:
           - edge = (predicted - line) / line; fall back to ``predicted`` as line
             when ``line`` is absent.
           - Place a flat ``BET_FRACTION`` (2 %) of current bankroll when
             ``abs(edge) >= self.edge_threshold``.
           - direction "over" if edge > 0, else "under".
           - Win if actual outcome vs line matches direction.
           - Payout uses -110 odds (win → +bet * 10/11; loss → -bet).
        4. Derive hit_rate, roi_pct, max_drawdown, final_bankroll.
        5. CLV = mean of per-record ``edge_pct`` for records that cleared the
           threshold AND have a non-None ``edge_pct`` field.  Set to 0.0 when
           no such field is available.  See ``BacktestResult.clv`` note.

        Returns an all-zero ``BacktestResult`` on empty data — never raises.

        Parameters
        ----------
        stat    : Stat category to filter on (e.g. 'pts', 'reb', 'ast').
        seasons : Season strings to load.  Defaults to the last three seasons
                  as defined by ``load_historical_results``.
        """
        # Deferred import keeps the module importable even when the
        # prediction sub-package is partially initialised.
        from src.prediction import prop_backtester

        _zero = BacktestResult(
            stat=stat,
            seasons=seasons or [],
            n_predictions=0,
            total_bets=0,
            wins=0,
            losses=0,
            hit_rate=0.0,
            roi_pct=0.0,
            clv=0.0,
            max_drawdown=0.0,
            final_bankroll=self.starting_bankroll,
        )

        try:
            all_records = prop_backtester.load_historical_results(seasons)
        except Exception:
            return _zero

        # Filter: stat match + non-None predicted + non-None actual
        records = [
            r for r in all_records
            if r.get("stat") == stat
            and r.get("predicted") is not None
            and r.get("actual") is not None
        ]

        n_predictions = len(records)
        if n_predictions == 0:
            _zero.seasons = seasons or []
            return _zero

        # Walk the bankroll
        bankroll = self.starting_bankroll
        equity: List[float] = [bankroll]   # starting point on the curve
        payout_mult = _payout_multiplier(_ODDS)

        total_bets = 0
        wins = 0
        losses = 0
        clv_values: List[float] = []

        for rec in records:
            predicted = float(rec["predicted"])
            actual = float(rec["actual"])
            line_raw = rec.get("line")
            line = float(line_raw) if line_raw is not None else predicted

            # Avoid divide-by-zero
            denom = abs(line) if abs(line) > 1e-9 else 1e-9
            edge = (predicted - line) / denom

            if abs(edge) < self.edge_threshold:
                continue

            # Bet direction
            direction = "over" if edge > 0 else "under"

            # Flat bet: 2 % of current bankroll
            bet_size = _BET_FRACTION * bankroll

            # Outcome
            if direction == "over":
                won = actual > line
            else:
                won = actual < line

            if won:
                bankroll += bet_size * payout_mult
                wins += 1
            else:
                bankroll -= bet_size
                losses += 1

            total_bets += 1
            equity.append(bankroll)

            # Collect CLV proxy from stored edge_pct when available
            ep = rec.get("edge_pct")
            if ep is not None:
                try:
                    clv_values.append(float(ep))
                except (TypeError, ValueError):
                    pass

        # Guard: no bets placed
        if total_bets == 0:
            return BacktestResult(
                stat=stat,
                seasons=seasons or [],
                n_predictions=n_predictions,
                total_bets=0,
                wins=0,
                losses=0,
                hit_rate=0.0,
                roi_pct=0.0,
                clv=0.0,
                max_drawdown=0.0,
                final_bankroll=self.starting_bankroll,
            )

        hit_rate = wins / total_bets
        roi_pct = (bankroll - self.starting_bankroll) / self.starting_bankroll * 100.0
        max_drawdown = _compute_max_drawdown(equity)
        clv = float(sum(clv_values) / len(clv_values)) if clv_values else 0.0

        return BacktestResult(
            stat=stat,
            seasons=seasons or [],
            n_predictions=n_predictions,
            total_bets=total_bets,
            wins=wins,
            losses=losses,
            hit_rate=round(hit_rate, 4),
            roi_pct=round(roi_pct, 4),
            clv=round(clv, 6),
            max_drawdown=max_drawdown,
            final_bankroll=round(bankroll, 4),
        )
