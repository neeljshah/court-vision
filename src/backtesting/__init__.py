"""
src/backtesting/__init__.py — Strategy-level prop backtester package.

Public exports
--------------
    StrategyBacktester   — bankroll-simulation backtester for prop models
    BacktestResult       — dataclass holding per-stat backtest metrics
"""

from src.backtesting.strategy_backtester import BacktestResult, StrategyBacktester

__all__ = ["StrategyBacktester", "BacktestResult"]
