"""
drawdown_tracker.py — Rolling drawdown analytics from a bet ledger's daily P&L.

Public API
----------
    get_drawdown_summary(source) -> dict

Keys returned
-------------
    max_dd_pct            : float  — worst peak-to-trough drawdown as a fraction (e.g. -0.15)
    current_dd_pct        : float  — current distance below the latest HWM
    drawdown_duration_days: int    — calendar days since the last HWM was set
    recovery_estimate_days: int    — estimated days to recover at the trailing 30-day daily return rate
"""

from __future__ import annotations

import os
from typing import Union

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_LEDGER = os.path.join(PROJECT_DIR, "data", "output", "bet_ledger.csv")

_ZEROED: dict = {
    "max_dd_pct": 0.0,
    "current_dd_pct": 0.0,
    "drawdown_duration_days": 0,
    "recovery_estimate_days": 0,
}


def _load_ledger(source: Union[str, pd.DataFrame, None]) -> pd.DataFrame:
    """Return a DataFrame with at least a ``date`` and ``pnl`` column."""
    if isinstance(source, pd.DataFrame):
        return source.copy()
    path = source if isinstance(source, str) else _DEFAULT_LEDGER
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def _build_equity_curve(df: pd.DataFrame) -> pd.Series:
    """Return a cumulative-sum equity curve indexed by row order."""
    col = next(
        (c for c in ["pnl", "PnL", "profit_loss", "returns"] if c in df.columns),
        None,
    )
    if col is None:
        return pd.Series(dtype=float)

    pnl = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # If a date column exists, sort by it first
    date_col = next(
        (c for c in ["date", "Date", "game_date"] if c in df.columns), None
    )
    if date_col:
        df = df.copy()
        df["__date__"] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values("__date__").reset_index(drop=True)
        pnl = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return pnl.cumsum()


def _compute_drawdowns(equity: pd.Series) -> dict:
    """
    Compute drawdown metrics from a cumulative equity curve.

    Returns a dict matching the public summary schema.
    """
    if equity.empty:
        return dict(_ZEROED)

    hwm = equity.cummax()
    drawdown = equity - hwm  # always <= 0

    # --- max drawdown as a fraction of the HWM at that point ---
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_pct = np.where(hwm != 0, drawdown / hwm.abs(), 0.0)
    max_dd_pct = float(np.min(dd_pct))  # most negative value

    # --- current drawdown ---
    current_hwm = float(hwm.iloc[-1])
    current_equity = float(equity.iloc[-1])
    if current_hwm != 0:
        current_dd_pct = (current_equity - current_hwm) / abs(current_hwm)
    else:
        current_dd_pct = 0.0

    # --- drawdown duration: rows since last HWM was set ---
    last_hwm_idx = int(hwm[hwm == hwm.iloc[-1]].index[0])
    drawdown_duration_days = int(len(equity) - 1 - last_hwm_idx)

    # --- recovery estimate ---
    # Use trailing 30-row average daily P&L as the run-rate
    recovery_estimate_days = 0
    if current_dd_pct < 0:
        deficit = current_hwm - current_equity  # positive dollars needed
        window = equity.tail(30)
        daily_rate = float(window.diff().mean()) if len(window) > 1 else 0.0
        if daily_rate > 0:
            recovery_estimate_days = int(np.ceil(deficit / daily_rate))
        else:
            recovery_estimate_days = 0  # cannot estimate with non-positive run-rate

    return {
        "max_dd_pct": round(max_dd_pct, 6),
        "current_dd_pct": round(current_dd_pct, 6),
        "drawdown_duration_days": drawdown_duration_days,
        "recovery_estimate_days": recovery_estimate_days,
    }


def get_drawdown_summary(
    source: Union[str, pd.DataFrame, None] = None,
) -> dict:
    """
    Compute drawdown analytics from a bet ledger.

    Parameters
    ----------
    source : str | pd.DataFrame | None
        Path to a CSV with ``date`` and ``pnl`` columns, a pre-loaded
        DataFrame with the same columns, or ``None`` to use the default
        ledger at ``data/output/bet_ledger.csv``.  Returns a zeroed
        summary dict if the file is absent or the DataFrame is empty.

    Returns
    -------
    dict with keys: max_dd_pct, current_dd_pct,
                    drawdown_duration_days, recovery_estimate_days.
    """
    df = _load_ledger(source)
    if df.empty:
        return dict(_ZEROED)

    equity = _build_equity_curve(df)
    if equity.empty:
        return dict(_ZEROED)

    return _compute_drawdowns(equity)
