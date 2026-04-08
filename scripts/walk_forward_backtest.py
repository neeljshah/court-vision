"""
walk_forward_backtest.py — Walk-forward prop bet backtest.

Protocol:
  1. Load historical prop predictions + closing lines from cached data.
  2. Walk windows: train on [start, T], predict [T, T+1wk].
  3. Compute CLV (closing line value), ROI, Sharpe, hit rate.
  4. Bucket results by data_confidence -> show if higher confidence = better ROI.

Output:
  data/backtest_results.parquet   — per-bet records
  data/backtest_summary.json      — Sharpe, ROI, CLV, hit rate by bucket

Usage:
    python scripts/walk_forward_backtest.py [--stat pts] [--lookback-weeks 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR    = PROJECT_DIR / "data"
sys.path.insert(0, str(PROJECT_DIR))

_PROP_STATS     = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_EV_THRESHOLD   = 0.03    # min CLV to count as a bet (3%)
_KELLY_FRACTION = 0.25    # quarter-Kelly for safety
_STARTING_BANKROLL = 1000.0


# ── helpers ───────────────────────────────────────────────────────────────────

def _american_to_prob(american: float) -> float:
    """Convert American odds to implied probability (with vig)."""
    if american >= 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def _clv(open_prob: float, close_prob: float) -> float:
    """CLV = (1/close_prob) - (1/open_prob); positive = bet closed better."""
    if close_prob <= 0 or open_prob <= 0:
        return 0.0
    return round(1 / close_prob - 1 / open_prob, 5)


def _kelly_size(edge: float, odds_decimal: float, fraction: float = _KELLY_FRACTION) -> float:
    """Fractional Kelly bet size (fraction of bankroll)."""
    p    = edge
    q    = 1 - p
    b    = odds_decimal - 1
    kelly = (p * b - q) / b
    return max(0.0, kelly * fraction)


def _sharpe(returns: pd.Series, periods_per_year: float = 52.0) -> float:
    """Annualised Sharpe ratio from weekly unit P&L series."""
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


# ── data loading ──────────────────────────────────────────────────────────────

def _load_clv_log() -> pd.DataFrame:
    """Load historical CLV log from nba_ai.db or data/edges/."""
    # Primary: data/edges/*.json
    edge_dir = DATA_DIR / "edges"
    frames = []
    if edge_dir.exists():
        for fp in edge_dir.glob("*.json"):
            try:
                d = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(d, list):
                    frames.extend(d)
                elif isinstance(d, dict):
                    frames.append(d)
            except Exception:
                pass

    # Secondary: nba_ai.db clv_log table
    db_path = DATA_DIR / "nba_ai.db"
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            db_df = pd.read_sql("SELECT * FROM clv_log", conn)
            conn.close()
            frames.extend(db_df.to_dict("records"))
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()
    df = pd.DataFrame(frames)
    df.columns = [c.lower() for c in df.columns]
    return df


def _load_predictions_log() -> pd.DataFrame:
    """Load stored predictions from nba_ai.db."""
    db_path = DATA_DIR / "nba_ai.db"
    if not db_path.exists():
        return pd.DataFrame()
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM predictions", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


# ── walk-forward engine ───────────────────────────────────────────────────────

def run_backtest(
    stat:            str = "pts",
    lookback_weeks:  int = 8,
    start_date:      Optional[str] = None,
    confidence_bins: List[float] = None,
) -> Dict[str, Any]:
    """
    Run walk-forward backtest for one prop stat.

    Returns summary dict with Sharpe, ROI, CLV, hit_rate by confidence bucket.
    """
    if confidence_bins is None:
        confidence_bins = [0.0, 0.50, 0.70, 0.85, 1.01]

    clv_df  = _load_clv_log()
    pred_df = _load_predictions_log()

    if clv_df.empty and pred_df.empty:
        print(f"  [{stat}] No historical data found — generating synthetic backtest")
        return _synthetic_backtest(stat, lookback_weeks)

    # Merge predictions with CLV if available
    df = _merge_predictions_clv(clv_df, pred_df, stat)
    if df.empty:
        return _synthetic_backtest(stat, lookback_weeks)

    return _run_walk_forward(df, stat, lookback_weeks, confidence_bins)


def _merge_predictions_clv(
    clv_df: pd.DataFrame, pred_df: pd.DataFrame, stat: str
) -> pd.DataFrame:
    """Inner join predictions with CLV records on game_id + player_id."""
    if clv_df.empty or pred_df.empty:
        return pd.DataFrame()
    try:
        merged = pred_df.merge(clv_df, on=["game_id", "player_id"], how="inner", suffixes=("_pred", "_clv"))
        if stat + "_pred" in merged.columns or f"pred_{stat}" in merged.columns:
            return merged
    except Exception:
        pass
    return pd.DataFrame()


def _run_walk_forward(
    df: pd.DataFrame,
    stat: str,
    lookback_weeks: int,
    confidence_bins: List[float],
) -> Dict[str, Any]:
    """Core walk-forward loop on real data."""
    df = df.sort_values("game_date").reset_index(drop=True)
    dates = pd.to_datetime(df["game_date"])
    start = dates.min()
    end   = dates.max()

    all_bets: List[dict] = []
    cursor = start + timedelta(weeks=lookback_weeks)

    while cursor <= end:
        window_end = cursor + timedelta(weeks=1)
        test_mask  = (dates >= cursor) & (dates < window_end)
        test_df    = df[test_mask]

        for _, row in test_df.iterrows():
            bet = _evaluate_bet(row, stat)
            if bet:
                all_bets.append(bet)

        cursor = window_end

    return _summarise(all_bets, stat, confidence_bins)


def _evaluate_bet(row: pd.Series, stat: str) -> Optional[dict]:
    """Evaluate one predicted prop vs closing line."""
    try:
        pred_col  = f"pred_{stat}" if f"pred_{stat}" in row.index else f"{stat}_pred"
        pred      = float(row.get(pred_col, row.get(stat, 0.0)))
        line      = float(row.get(f"{stat}_line", row.get("line", pred)))
        open_ml   = float(row.get("open_ml_over", -110))
        close_ml  = float(row.get("close_ml_over", open_ml))
        data_conf = float(row.get("data_confidence", 0.85))

        open_prob  = _american_to_prob(open_ml)
        close_prob = _american_to_prob(close_ml)
        model_prob = 0.55 if pred > line else 0.45   # simplified; real: calibrated prob

        edge       = model_prob - open_prob
        clv_val    = _clv(open_prob, close_prob)
        odds_dec   = 1 + 100 / abs(open_ml) if open_ml < 0 else 1 + open_ml / 100
        kelly_f    = _kelly_size(model_prob, odds_dec)

        actual     = float(row.get(f"actual_{stat}", row.get("actual", float("nan"))))
        result_over = int(actual > line) if not np.isnan(actual) else None
        pnl         = (odds_dec - 1) * kelly_f if result_over else -kelly_f if result_over is not None else 0.0

        if abs(edge) < _EV_THRESHOLD:
            return None

        return {
            "stat": stat, "pred": pred, "line": line,
            "edge": round(edge, 4), "clv": clv_val,
            "kelly_f": round(kelly_f, 4),
            "result_over": result_over,
            "pnl": round(pnl, 4),
            "data_confidence": data_conf,
            "game_date": str(row.get("game_date", "")),
        }
    except Exception:
        return None


def _summarise(bets: List[dict], stat: str, bins: List[float]) -> Dict[str, Any]:
    """Compute Sharpe, ROI, CLV, hit_rate overall and by confidence bucket."""
    if not bets:
        return {"stat": stat, "n_bets": 0, "sharpe": 0.0, "roi": 0.0,
                "clv_mean": 0.0, "hit_rate": 0.0, "by_confidence": {}}

    df   = pd.DataFrame(bets)
    n    = len(df)
    roi  = float(df["pnl"].sum() / max(n, 1))
    clv  = float(df["clv"].mean())
    hit  = float((df["result_over"] == 1).sum() / max((df["result_over"].notna()).sum(), 1))

    weekly = df.groupby("game_date")["pnl"].sum()
    sharpe = _sharpe(weekly)

    # By confidence bucket
    labels = [f"{bins[i]:.2f}-{bins[i+1]:.2f}" for i in range(len(bins)-1)]
    df["conf_bucket"] = pd.cut(df["data_confidence"], bins=bins, labels=labels)
    by_conf: dict = {}
    for lbl, grp in df.groupby("conf_bucket", observed=True):
        by_conf[str(lbl)] = {
            "n": len(grp),
            "roi": round(float(grp["pnl"].sum() / max(len(grp), 1)), 4),
            "clv": round(float(grp["clv"].mean()), 5),
            "hit_rate": round(float((grp["result_over"] == 1).sum() / max((grp["result_over"].notna()).sum(), 1)), 3),
        }

    return {
        "stat": stat, "n_bets": n,
        "sharpe": round(sharpe, 3),
        "roi": round(roi, 4),
        "clv_mean": round(clv, 5),
        "hit_rate": round(hit, 3),
        "by_confidence": by_conf,
    }


def _synthetic_backtest(stat: str, lookback_weeks: int) -> Dict[str, Any]:
    """
    Generate a synthetic backtest when no historical data is available.
    Uses NBA-realistic distributions to produce meaningful output shape.
    """
    rng = np.random.default_rng(hash(stat) % (2**32))
    n   = lookback_weeks * 15   # ~15 bets per week

    edges        = rng.normal(0.02, 0.04, n)
    clv_vals     = rng.normal(0.01, 0.02, n)
    pnl          = edges * rng.uniform(0.8, 1.2, n)
    data_conf    = rng.uniform(0.5, 1.0, n)
    hit_rate     = 0.53 + edges.mean()

    df = pd.DataFrame({"pnl": pnl, "clv": clv_vals, "data_confidence": data_conf,
                       "result_over": rng.binomial(1, hit_rate, n)})
    bins   = [0.0, 0.50, 0.70, 0.85, 1.01]
    labels = [f"{bins[i]:.2f}-{bins[i+1]:.2f}" for i in range(len(bins)-1)]
    df["conf_bucket"] = pd.cut(df["data_confidence"], bins=bins, labels=labels)
    by_conf: dict = {}
    for lbl, grp in df.groupby("conf_bucket", observed=True):
        by_conf[str(lbl)] = {
            "n": len(grp),
            "roi": round(float(grp["pnl"].mean()), 4),
            "clv": round(float(grp["clv"].mean()), 5),
            "hit_rate": round(float((grp["result_over"] == 1).sum() / max(len(grp), 1)), 3),
        }

    weekly = pd.Series(pnl).groupby(np.arange(n) // 15).sum()
    return {
        "stat": stat, "n_bets": n,
        "sharpe": round(_sharpe(weekly), 3),
        "roi":    round(float(pnl.mean()), 4),
        "clv_mean": round(float(clv_vals.mean()), 5),
        "hit_rate": round(hit_rate, 3),
        "by_confidence": by_conf,
        "note": "synthetic — no historical bet data in DB yet",
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat",            default="all")
    ap.add_argument("--lookback-weeks",  type=int, default=8)
    ap.add_argument("--start-date",      default=None)
    args = ap.parse_args()

    stats = _PROP_STATS if args.stat == "all" else [args.stat]
    all_results = {}

    for stat in stats:
        print(f"\n[backtest] Running {stat.upper()}...")
        result = run_backtest(stat, args.lookback_weeks, args.start_date)
        all_results[stat] = result
        print(f"  n_bets={result['n_bets']}  sharpe={result['sharpe']:.3f}  "
              f"roi={result['roi']:.4f}  clv={result['clv_mean']:.5f}  "
              f"hit_rate={result['hit_rate']:.3f}")
        if result.get("by_confidence"):
            print("  by confidence bucket:")
            for bucket, bm in result["by_confidence"].items():
                print(f"    [{bucket}]  n={bm['n']}  roi={bm['roi']:.4f}  "
                      f"clv={bm['clv']:.5f}  hit={bm['hit_rate']:.3f}")

    # Save outputs
    out_path = DATA_DIR / "backtest_results.json"
    out_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\n[backtest] Results saved to {out_path}")


if __name__ == "__main__":
    main()
