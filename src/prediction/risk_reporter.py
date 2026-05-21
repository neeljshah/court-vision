"""Daily VaR / CVaR risk report for the betting ledger.

Computes:
  - 95% parametric VaR   (Gaussian assumption)
  - 95% historical VaR   (empirical percentile)
  - CVaR / Expected Shortfall at 95% (mean of losses beyond the VaR threshold)

Writes `data/output/risk/risk_{YYYYMMDD}.json`.

Usage::

    from src.prediction.risk_reporter import build_report
    report = build_report()          # reads bet_ledger.csv automatically
    report = build_report(df=my_df)  # pass a DataFrame directly
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = _ROOT / "data" / "output" / "bet_ledger.csv"
RISK_DIR = _ROOT / "data" / "output" / "risk"

# ── Constants ─────────────────────────────────────────────────────────────────
CONFIDENCE = 0.95
LOOKBACK_DAYS = 60


# ── Core computation ──────────────────────────────────────────────────────────

def _compute_var_cvar(pnl: np.ndarray, confidence: float = CONFIDENCE) -> dict:
    """Return VaR / CVaR metrics for a 1-D P&L array (positive = profit).

    All returned VaR / ES values are expressed as *positive* numbers
    representing the magnitude of the potential loss (right-tail of losses).
    """
    if pnl.size == 0:
        nan = float("nan")
        return {
            "parametric_var_95": nan,
            "historical_var_95": nan,
            "cvar_95": nan,
            "expected_shortfall_95": nan,
            "n_observations": 0,
        }

    mu = float(np.mean(pnl))
    sigma = float(np.std(pnl, ddof=1)) if pnl.size > 1 else 0.0
    alpha = 1.0 - confidence   # 0.05

    # ── Parametric VaR (Gaussian) ─────────────────────────────────────────────
    # z-score for the lower alpha quantile of a standard normal
    z_alpha = _norm_ppf(alpha)          # negative number, e.g. -1.6449
    parametric_var = -(mu + z_alpha * sigma)   # flip sign → positive loss

    # ── Historical VaR ────────────────────────────────────────────────────────
    hist_var = -float(np.percentile(pnl, alpha * 100))   # positive loss

    # ── CVaR / Expected Shortfall ─────────────────────────────────────────────
    threshold = float(np.percentile(pnl, alpha * 100))   # lower alpha quantile
    tail = pnl[pnl <= threshold]
    cvar = -float(np.mean(tail)) if tail.size > 0 else float("nan")

    return {
        "parametric_var_95": round(parametric_var, 4),
        "historical_var_95": round(hist_var, 4),
        "cvar_95": round(cvar, 4),
        "expected_shortfall_95": round(cvar, 4),   # same as CVaR here
        "n_observations": int(pnl.size),
    }


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF (percent point function) via scipy or pure-Python fallback."""
    try:
        from scipy.stats import norm  # type: ignore
        return float(norm.ppf(p))
    except ImportError:
        pass
    # Rational approximation (Abramowitz & Stegun 26.2.17)
    t = math.sqrt(-2.0 * math.log(p))
    c = (2.515517, 0.802853, 0.010328)
    d = (1.432788, 0.189269, 0.001308)
    return -(t - (c[0] + c[1] * t + c[2] * t ** 2)
             / (1 + d[0] * t + d[1] * t ** 2 + d[2] * t ** 3))


# ── DataFrame helpers ─────────────────────────────────────────────────────────

def _load_ledger(path: Path) -> Optional[pd.DataFrame]:
    """Load the CSV ledger; return None if the file is absent."""
    if not path.is_file():
        return None
    return pd.read_csv(path)


def _recent_daily_pnl(df: pd.DataFrame, lookback: int = LOOKBACK_DAYS) -> np.ndarray:
    """Extract a daily P&L array from the ledger DataFrame.

    The ledger is expected to have a `date` column (parseable) and a
    `pnl` column (numeric).  If either is missing the function falls
    back gracefully.
    """
    df = df.copy()

    # Normalise column names to lower-case
    df.columns = [c.lower().strip() for c in df.columns]

    if "date" not in df.columns or "pnl" not in df.columns:
        # Try to use a numeric column named 'profit', 'return', 'net', etc.
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            return np.array([], dtype=float)
        pnl_col = next(
            (c for c in numeric_cols if c in ("pnl", "profit", "net", "return")),
            numeric_cols[0],
        )
        return df[pnl_col].dropna().values.astype(float)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "pnl"])
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    df = df.dropna(subset=["pnl"])

    cutoff = pd.Timestamp.today() - pd.Timedelta(days=lookback)
    df = df[df["date"] >= cutoff]

    # Aggregate to daily totals
    daily = df.groupby(df["date"].dt.date)["pnl"].sum()
    return daily.values.astype(float)


# ── Public API ────────────────────────────────────────────────────────────────

def build_report(
    ledger: Union[Path, str, None] = None,
    df: Optional[pd.DataFrame] = None,
    report_date: Optional[date] = None,
    confidence: float = CONFIDENCE,
    lookback_days: int = LOOKBACK_DAYS,
) -> dict:
    """Compute VaR / CVaR and write a JSON report.

    Parameters
    ----------
    ledger:
        Path to the bet ledger CSV.  Defaults to ``data/output/bet_ledger.csv``.
        Ignored if *df* is provided.
    df:
        Pre-loaded DataFrame.  If given, *ledger* is not read from disk.
    report_date:
        Date used in the output filename.  Defaults to today.
    confidence:
        Quantile level (default 0.95).
    lookback_days:
        How many calendar days of history to include (default 60).

    Returns
    -------
    dict
        Report payload (also written to ``data/output/risk/risk_{YYYYMMDD}.json``).
    """
    # ── Resolve data ──────────────────────────────────────────────────────────
    if df is None:
        path = Path(ledger) if ledger is not None else DEFAULT_LEDGER
        df = _load_ledger(path)

    if df is None or (hasattr(df, "__len__") and len(df) == 0):
        pnl = np.array([], dtype=float)
    else:
        pnl = _recent_daily_pnl(df, lookback=lookback_days)

    # ── Compute metrics ───────────────────────────────────────────────────────
    metrics = _compute_var_cvar(pnl, confidence=confidence)

    today = report_date or date.today()
    report = {
        "report_date": today.strftime("%Y-%m-%d"),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "confidence": confidence,
        "lookback_days": lookback_days,
        **metrics,
    }

    # ── Write report ──────────────────────────────────────────────────────────
    RISK_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RISK_DIR / f"risk_{today.strftime('%Y%m%d')}.json"
    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=2)

    return report


__all__ = ["build_report", "DEFAULT_LEDGER", "RISK_DIR"]
