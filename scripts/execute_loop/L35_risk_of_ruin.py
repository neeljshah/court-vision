"""L35_risk_of_ruin.py — Risk-of-Ruin Monitor (BUILD L35).

Monte Carlo simulation of bankroll survival over a rolling 30-day window.
Reads the L07 bets ledger for daily-return estimation; alerts via L22.

Public API
----------
    RuinReport                  dataclass
    run_simulation(...)         Monte Carlo over a daily-return distribution
    estimate_daily_return_dist_from_ledger(window_days) -> dict
    alert_on_high_ruin_risk(report, threshold) -> bool

CLI
---
    python L35_risk_of_ruin.py simulate [--bankroll N --days N --sims N]
    python L35_risk_of_ruin.py report
    python L35_risk_of_ruin.py alert
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

# ── project root on path ──────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_BETS_PARQUET = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"
_BANKROLL_STATE = _PROJECT_DIR / "data" / "ledger" / "bankroll_state.json"

_FALLBACK_BANKROLL = 100_000.0
_FALLBACK_MEAN = 0.065
_FALLBACK_STD = 0.24          # weighted: 0.5*0.08 + 0.5*0.40
_MIN_OBS_FOR_REAL_DIST = 14

log = logging.getLogger(__name__)

# ── optional scipy ────────────────────────────────────────────────────────────
try:
    from scipy.stats import skew as _sp_skew, kurtosis as _sp_kurtosis
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

# ── optional pandas / parquet ─────────────────────────────────────────────────
try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False


# ── dataclass ─────────────────────────────────────────────────────────────────
@dataclass
class RuinReport:
    simulated_bankrolls: list  # final value per sim (truncated to 1000 in JSON)
    p_ruin_30d: float
    p_drawdown_50: float
    expected_final: float
    median_final: float
    sharpe: float              # annualized
    observed_daily_returns_count: int
    mean_daily_return: float
    std_daily_return: float
    used_fallback_dist: bool
    generated_at: str          # ISO


# ── ledger reader ─────────────────────────────────────────────────────────────
def _load_bets_df():
    """Return a pandas DataFrame of bets, or None if unavailable."""
    if not _HAS_PANDAS:
        log.warning("[L35] pandas not available — cannot read ledger")
        return None

    if _HAS_PARQUET and _BETS_PARQUET.exists():
        try:
            return pd.read_parquet(_BETS_PARQUET)
        except Exception as exc:
            log.warning("[L35] Failed to read bets.parquet: %s", exc)

    if _BETS_CSV.exists():
        try:
            return pd.read_csv(_BETS_CSV)
        except Exception as exc:
            log.warning("[L35] Failed to read bets.csv: %s", exc)

    log.warning("[L35] No bets ledger found at %s — using fallback dist", _LEDGER_DIR)
    return None


def _current_bankroll_from_state() -> float:
    """Read current_bankroll from L18 bankroll_state.json if present."""
    if not _BANKROLL_STATE.exists():
        return _FALLBACK_BANKROLL
    try:
        state = json.loads(_BANKROLL_STATE.read_text(encoding="utf-8"))
        return float(state.get("current_bankroll", _FALLBACK_BANKROLL))
    except Exception as exc:
        log.warning("[L35] Could not read bankroll_state.json: %s", exc)
        return _FALLBACK_BANKROLL


def estimate_daily_return_dist_from_ledger(window_days: int = 30) -> dict:
    """Estimate daily-return distribution from the L07 bets ledger.

    Filters to WON/LOST/PUSH bets within the last *window_days* days, groups
    by settlement date, and computes daily returns as daily_pnl / starting_bankroll.

    Returns a dict with keys: mean, std, n_observations, skew, kurtosis, used_fallback.
    Falls back to a blended cash/GPP distribution when fewer than 14 days of data.
    """
    _fallback = {
        "mean": _FALLBACK_MEAN,
        "std": _FALLBACK_STD,
        "n_observations": 0,
        "skew": 0.0,
        "kurtosis": 0.0,
        "used_fallback": True,
    }

    df = _load_bets_df()
    if df is None or df.empty:
        log.warning("[L35] Empty or missing ledger — using fallback distribution")
        return _fallback

    # Filter to settled bets within the window
    settled_statuses = {"WON", "LOST", "PUSH"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    try:
        df = df[df["status"].isin(settled_statuses)].copy()
        df["settled_dt"] = pd.to_datetime(df["settled_at_iso"], utc=True, errors="coerce")
        df = df[df["settled_dt"] >= cutoff].copy()
        df["pnl_num"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0)
        df["date_key"] = df["settled_dt"].dt.date
    except Exception as exc:
        log.warning("[L35] Ledger processing error: %s — using fallback", exc)
        return _fallback

    if df.empty:
        log.warning("[L35] No settled bets in last %d days — using fallback", window_days)
        return _fallback

    daily_pnl = df.groupby("date_key")["pnl_num"].sum()
    n_days = len(daily_pnl)

    if n_days < _MIN_OBS_FOR_REAL_DIST:
        log.warning(
            "[L35] Only %d days of data (need %d) — using fallback distribution",
            n_days, _MIN_OBS_FOR_REAL_DIST,
        )
        return _fallback

    starting_bankroll = _current_bankroll_from_state()
    daily_returns = (daily_pnl / starting_bankroll).values

    mean = float(np.mean(daily_returns))
    std = float(np.std(daily_returns, ddof=1)) if n_days > 1 else 0.0

    if _HAS_SCIPY and n_days >= 3:
        skewness = float(_sp_skew(daily_returns))
        kurt = float(_sp_kurtosis(daily_returns))
    else:
        skewness = 0.0
        kurt = 0.0

    log.info(
        "[L35] Ledger dist: n=%d mean=%.4f std=%.4f skew=%.2f kurt=%.2f",
        n_days, mean, std, skewness, kurt,
    )
    return {
        "mean": mean,
        "std": std,
        "n_observations": n_days,
        "skew": skewness,
        "kurtosis": kurt,
        "used_fallback": False,
    }


# ── monte carlo ───────────────────────────────────────────────────────────────
def run_simulation(
    initial_bankroll: float,
    daily_return_dist: dict,
    n_sims: int = 10_000,
    n_days: int = 30,
    ruin_threshold_pct: float = 0.5,
) -> RuinReport:
    """Run a Monte Carlo ruin simulation.

    Parameters
    ----------
    initial_bankroll    : starting bankroll value
    daily_return_dist   : dict with keys 'mean', 'std', 'used_fallback', etc.
    n_sims              : number of simulation paths
    n_days              : horizon in days
    ruin_threshold_pct  : fraction of initial_bankroll below which ruin is declared

    Returns
    -------
    RuinReport with all simulation metrics populated.
    """
    mean = float(daily_return_dist.get("mean", _FALLBACK_MEAN))
    std = float(daily_return_dist.get("std", _FALLBACK_STD))
    used_fallback = bool(daily_return_dist.get("used_fallback", False))
    n_obs = int(daily_return_dist.get("n_observations", 0))
    generated_at = datetime.now(timezone.utc).isoformat()

    ruin_level = initial_bankroll * ruin_threshold_pct
    drawdown_50_level = initial_bankroll * 0.5

    # Deterministic path: std == 0
    if std == 0.0:
        log.warning("[L35] std=0 — deterministic path, no Monte Carlo needed")
        final_val = initial_bankroll * ((1 + mean) ** n_days)
        ever_ruined = final_val < ruin_level or (mean < 0 and ruin_level > 0)

        # Walk through deterministically to find minimum
        path_min = initial_bankroll
        bk = initial_bankroll
        for _ in range(n_days):
            bk *= (1 + mean)
            if bk < path_min:
                path_min = bk

        p_ruin = 1.0 if path_min < ruin_level else 0.0
        p_dd50 = 1.0 if path_min < drawdown_50_level else 0.0
        sharpe = 0.0  # undefined when std=0
        return RuinReport(
            simulated_bankrolls=[final_val],
            p_ruin_30d=p_ruin,
            p_drawdown_50=p_dd50,
            expected_final=final_val,
            median_final=final_val,
            sharpe=sharpe,
            observed_daily_returns_count=n_obs,
            mean_daily_return=mean,
            std_daily_return=std,
            used_fallback_dist=used_fallback,
            generated_at=generated_at,
        )

    # Vectorized Monte Carlo
    rng = np.random.default_rng(seed=42)
    daily_returns = rng.normal(mean, std, (n_sims, n_days))
    bankroll_paths = initial_bankroll * np.cumprod(1 + daily_returns, axis=1)

    min_per_sim = bankroll_paths.min(axis=1)
    ruin_flags = min_per_sim < ruin_level
    p_ruin_30d = float(ruin_flags.mean())
    p_drawdown_50 = float((min_per_sim < drawdown_50_level).mean())

    final_bankrolls = bankroll_paths[:, -1]
    expected_final = float(final_bankrolls.mean())
    median_final = float(np.median(final_bankrolls))
    sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0

    log.info(
        "[L35] MC n_sims=%d n_days=%d p_ruin=%.3f p_dd50=%.3f "
        "E[final]=%.0f median=%.0f sharpe=%.2f",
        n_sims, n_days, p_ruin_30d, p_drawdown_50,
        expected_final, median_final, sharpe,
    )

    return RuinReport(
        simulated_bankrolls=final_bankrolls.tolist(),
        p_ruin_30d=p_ruin_30d,
        p_drawdown_50=p_drawdown_50,
        expected_final=expected_final,
        median_final=median_final,
        sharpe=sharpe,
        observed_daily_returns_count=n_obs,
        mean_daily_return=mean,
        std_daily_return=std,
        used_fallback_dist=used_fallback,
        generated_at=generated_at,
    )


# ── alerting ──────────────────────────────────────────────────────────────────
def alert_on_high_ruin_risk(report: RuinReport, threshold: float = 0.05) -> bool:
    """Send an alert if p_ruin_30d exceeds threshold.

    Severity escalates to 'error' when p_ruin > 0.20.
    Returns False when no alert is warranted or L22 is unavailable.
    """
    # Look up L22 via sys.modules so that monkeypatch.setitem works in tests.
    # Using `import ... as X` would bind X to the parent package attribute, not
    # sys.modules, making the mock invisible to the import statement.
    import sys as _sys
    _L22_KEY = "scripts.execute_loop.L22_alerting"
    _sentinel = object()
    L22 = _sys.modules.get(_L22_KEY, _sentinel)
    if L22 is _sentinel:
        # Not yet imported — trigger the real import, then fetch from sys.modules
        try:
            import scripts.execute_loop.L22_alerting  # noqa: F401
            L22 = _sys.modules.get(_L22_KEY)
        except ImportError:
            log.warning("[L35] L22_alerting not importable — skipping alert")
            return False
    if L22 is None:
        # monkeypatch set to None to simulate ImportError
        log.warning("[L35] L22_alerting not importable — skipping alert")
        return False

    p = report.p_ruin_30d
    if p > 0.20:
        severity = "error"
    elif p > threshold:
        severity = "warning"
    else:
        return False

    body = (
        f"P(ruin 30d)={p:.2%} | P(drawdown 50%)={report.p_drawdown_50:.2%} | "
        f"E[final]=${report.expected_final:,.0f} | sharpe={report.sharpe:.2f}"
    )
    log.warning("[L35] Ruin alert — severity=%s p_ruin=%.3f", severity, p)
    L22.send_alert(
        channel="drawdown",
        level=severity,
        title="Ruin risk",
        body=f"P(ruin 30d)={p:.2%}",
        fields={
            "P(ruin 30d)": f"{p:.2%}",
            "P(drawdown 50%)": f"{report.p_drawdown_50:.2%}",
            "E[final]": f"${report.expected_final:,.0f}",
            "Sharpe": f"{report.sharpe:.2f}",
            "Details": body,
        },
    )
    return True


# ── report serializer ─────────────────────────────────────────────────────────
def _report_to_json(report: RuinReport) -> dict:
    d = asdict(report)
    d["simulated_bankrolls"] = d["simulated_bankrolls"][:1000]
    return d


def _save_report(report: RuinReport) -> Path:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = _LEDGER_DIR / f"ruin_report_{date_str}.json"
    out_path.write_text(
        json.dumps(_report_to_json(report), indent=2), encoding="utf-8"
    )
    log.info("[L35] Report saved → %s", out_path)
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="L35 Risk-of-Ruin Monitor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sim_p = sub.add_parser("simulate", help="Run Monte Carlo simulation")
    sim_p.add_argument("--bankroll", type=float, default=100_000.0)
    sim_p.add_argument("--days",     type=int,   default=30)
    sim_p.add_argument("--sims",     type=int,   default=10_000)

    sub.add_parser("report", help="Run simulation + save JSON report")
    sub.add_parser("alert",  help="Run simulation + send alert if high risk")

    args = parser.parse_args()

    if args.cmd == "simulate":
        dist = estimate_daily_return_dist_from_ledger()
        report = run_simulation(
            initial_bankroll=args.bankroll,
            daily_return_dist=dist,
            n_sims=args.sims,
            n_days=args.days,
        )
        print(json.dumps(_report_to_json(report), indent=2))

    elif args.cmd == "report":
        dist = estimate_daily_return_dist_from_ledger()
        bankroll = _current_bankroll_from_state()
        report = run_simulation(initial_bankroll=bankroll, daily_return_dist=dist)
        path = _save_report(report)
        print(f"Report saved: {path}")
        print(f"p_ruin_30d={report.p_ruin_30d:.2%}  sharpe={report.sharpe:.2f}")

    elif args.cmd == "alert":
        dist = estimate_daily_return_dist_from_ledger()
        bankroll = _current_bankroll_from_state()
        report = run_simulation(initial_bankroll=bankroll, daily_return_dist=dist)
        alerted = alert_on_high_ruin_risk(report)
        print(f"Alert fired: {alerted}  p_ruin_30d={report.p_ruin_30d:.2%}")


if __name__ == "__main__":
    _cli()
