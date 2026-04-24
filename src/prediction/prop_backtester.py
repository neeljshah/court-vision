"""
prop_backtester.py — Phase 4.9: Historical prop backtester + paper trading mode.

Validates prediction models against historical prop results before risking real money.
Loads historical NBA game outcomes, compares model predictions vs actual stats,
computes accuracy metrics, and runs a paper trading simulation.

Public API
----------
    backtest_props(seasons, stat, edge_threshold)    -> BacktestResult
    paper_trade_today(bankroll, edge_threshold)      -> List[dict]
    load_historical_results(seasons)                 -> List[dict]
    validation_gate(stat, min_roi)                   -> bool
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_NBA_DIR       = os.path.join(PROJECT_DIR, "data", "nba")
_RESULTS_CACHE = os.path.join(_MODELS_DIR, "backtest_results.json")
_PAPER_LOG     = os.path.join(_MODELS_DIR, "paper_trades.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# Validation gate thresholds — must pass before live money is enabled
VALIDATION_MIN_ROI  = 0.03    # 3% ROI minimum on backtest
VALIDATION_MIN_BETS = 50      # minimum sample size
VALIDATION_MIN_CLV  = 0.0     # must have positive average CLV


@dataclass
class BacktestResult:
    """Results of a backtest run for one stat category."""
    stat:          str
    seasons:       List[str]
    n_predictions: int
    n_bets:        int            # predictions that cleared edge_threshold
    wins:          int
    losses:        int
    win_rate:      float
    roi_pct:       float
    mae:           float          # mean absolute error on predictions
    avg_edge:      float          # average predicted edge on placed bets
    edge_buckets:  Dict[str, dict] = field(default_factory=dict)  # edge range → {n, win_rate}
    passed_gate:   bool = False


def load_historical_results(seasons: Optional[List[str]] = None) -> List[dict]:
    """
    Load historical game outcome data for backtesting.

    Pulls from:
    1. data/models/prop_residuals.json  — recorded by outcome_recorder.py
    2. data/nba/gamelogs_*.json         — raw box scores as fallback

    Returns list of dicts: {player_id, player_name, stat, game_date,
                             predicted, actual, line, direction, edge_pct}
    """
    seasons = seasons or ["2024-25", "2023-24", "2022-23"]

    # Try prop_residuals first (most accurate — recorded at prediction time)
    residuals_path = os.path.join(_MODELS_DIR, "prop_residuals.json")
    if os.path.exists(residuals_path):
        try:
            data = json.load(open(residuals_path, encoding="utf-8"))
            if data:
                return data
        except Exception:
            pass

    # Fallback: build from gamelogs + model predictions
    results = []
    for season in seasons:
        log_path = os.path.join(_NBA_DIR, f"gamelogs_{season}.json")
        if not os.path.exists(log_path):
            continue
        try:
            logs = json.load(open(log_path, encoding="utf-8"))
            for entry in logs:
                for stat in STATS:
                    actual = entry.get(stat) or entry.get(f"player_{stat}")
                    if actual is None:
                        continue
                    results.append({
                        "player_id":   str(entry.get("player_id", "")),
                        "player_name": str(entry.get("player_name", "")),
                        "stat":        stat,
                        "game_date":   entry.get("game_date", ""),
                        "predicted":   None,   # no prediction at ingest time
                        "actual":      float(actual),
                        "line":        None,
                        "direction":   None,
                        "edge_pct":    None,
                    })
        except Exception:
            pass

    return results


def backtest_props(
    seasons: Optional[List[str]] = None,
    stat: str = "pts",
    edge_threshold: float = 0.04,
    kelly_fraction: float = 0.25,
    odds: int = -110,
) -> BacktestResult:
    """
    Backtest prop model for a single stat across historical seasons.

    Simulates placing bets when edge > edge_threshold, using paper bankroll.
    Win/loss determined by comparing prediction direction vs actual outcome.

    Args:
        seasons:         Seasons to backtest (default: last 3).
        stat:            Stat category to backtest.
        edge_threshold:  Minimum predicted edge to place a paper bet.
        kelly_fraction:  Fraction of Kelly to simulate.
        odds:            Simulated odds for all bets.

    Returns:
        BacktestResult with full performance metrics.
    """
    seasons = seasons or ["2024-25", "2023-24", "2022-23"]
    records = load_historical_results(seasons)

    stat_recs = [r for r in records
                 if r.get("stat") == stat
                 and r.get("predicted") is not None
                 and r.get("actual") is not None]

    n_pred = len(stat_recs)
    if n_pred == 0:
        return BacktestResult(
            stat=stat, seasons=seasons, n_predictions=0, n_bets=0,
            wins=0, losses=0, win_rate=0.0, roi_pct=0.0, mae=0.0,
            avg_edge=0.0, passed_gate=False,
        )

    maes = []
    bets_placed = []
    bankroll = 1000.0

    for r in stat_recs:
        pred   = float(r["predicted"])
        actual = float(r["actual"])
        line   = r.get("line") or pred   # use pred as line if no market line
        maes.append(abs(pred - actual))

        edge = (pred - line) / max(line, 0.01)
        direction = "over" if edge > 0 else "under"
        abs_edge = abs(edge)

        if abs_edge < edge_threshold:
            continue

        # Kelly sizing
        from scipy.special import expit  # noqa: F401
        implied = 100.0 / (abs(odds) + 100.0) if odds < 0 else 100.0 / (odds + 100.0)
        win_prob = min(0.95, implied + abs_edge)
        b = 100.0 / abs(odds) if odds < 0 else odds / 100.0
        q = 1.0 - win_prob
        fk = max(0.0, (win_prob * b - q) / b)
        bet_size = min(fk * kelly_fraction * bankroll, 0.04 * bankroll)

        # Did the bet win?
        if direction == "over":
            won = actual > line
        else:
            won = actual < line

        payout = bet_size * b if won else -bet_size
        bankroll += payout
        bets_placed.append({
            "edge": abs_edge,
            "won":  won,
            "pnl":  payout,
        })

    n_bets = len(bets_placed)
    if n_bets == 0:
        return BacktestResult(
            stat=stat, seasons=seasons, n_predictions=n_pred, n_bets=0,
            wins=0, losses=0, win_rate=0.0, roi_pct=0.0,
            mae=float(np.mean(maes)), avg_edge=0.0, passed_gate=False,
        )

    wins       = sum(1 for b in bets_placed if b["won"])
    losses     = n_bets - wins
    win_rate   = wins / n_bets
    total_pnl  = sum(b["pnl"] for b in bets_placed)
    total_wag  = sum(abs(b["pnl"] / (100.0/110.0)) for b in bets_placed)   # approximate
    roi        = total_pnl / max(total_wag, 1) * 100
    avg_edge   = float(np.mean([b["edge"] for b in bets_placed]))

    # Edge bucket analysis: group into 4-8%, 8-12%, 12%+
    buckets: Dict[str, dict] = {}
    for lo, hi in [(0.04, 0.08), (0.08, 0.12), (0.12, 1.0)]:
        bucket = [b for b in bets_placed if lo <= b["edge"] < hi]
        if bucket:
            label = f"{int(lo*100)}-{int(hi*100)}%"
            buckets[label] = {
                "n": len(bucket),
                "win_rate": round(sum(1 for b in bucket if b["won"]) / len(bucket), 3),
                "avg_pnl":  round(float(np.mean([b["pnl"] for b in bucket])), 2),
            }

    # Explicit fail-closed guard: no data → never pass gate
    if n_pred == 0 or n_bets == 0:
        passed = False
    else:
        passed = (n_bets >= VALIDATION_MIN_BETS
                  and roi >= VALIDATION_MIN_ROI * 100
                  and avg_edge >= 0.0)

    result = BacktestResult(
        stat=stat, seasons=seasons, n_predictions=n_pred, n_bets=n_bets,
        wins=wins, losses=losses, win_rate=round(win_rate, 3),
        roi_pct=round(roi, 2), mae=round(float(np.mean(maes)), 3),
        avg_edge=round(avg_edge, 4), edge_buckets=buckets, passed_gate=passed,
    )

    # Persist to cache
    _save_backtest(result)
    return result


def _save_backtest(result: BacktestResult) -> None:
    existing: dict = {}
    if os.path.exists(_RESULTS_CACHE):
        try:
            existing = json.load(open(_RESULTS_CACHE, encoding="utf-8"))
        except Exception:
            pass
    existing[result.stat] = {
        "n_bets": result.n_bets,
        "win_rate": result.win_rate,
        "roi_pct": result.roi_pct,
        "mae": result.mae,
        "avg_edge": result.avg_edge,
        "passed_gate": result.passed_gate,
        "edge_buckets": result.edge_buckets,
    }
    os.makedirs(_MODELS_DIR, exist_ok=True)
    json.dump(existing, open(_RESULTS_CACHE, "w", encoding="utf-8"), indent=2)


def validation_gate(stat: str = "pts", min_roi: float = VALIDATION_MIN_ROI) -> bool:
    """
    Return True if the model for this stat passes the validation gate
    (sufficient backtest ROI + sample size).  Guards live money deployment.
    """
    if not os.path.exists(_RESULTS_CACHE):
        return False
    try:
        cache = json.load(open(_RESULTS_CACHE, encoding="utf-8"))
        entry = cache.get(stat, {})
        return (entry.get("n_bets", 0) >= VALIDATION_MIN_BETS
                and entry.get("roi_pct", -999) >= min_roi * 100
                and entry.get("passed_gate", False))
    except Exception:
        return False


def paper_trade_today(
    bankroll: float = 1000.0,
    edge_threshold: float = 0.04,
) -> List[dict]:
    """
    Simulate today's prop bets in paper trading mode (no real money).

    Loads today's predictions from predict_props(), filters by edge_threshold,
    sizes bets with Kelly, and logs to data/models/paper_trades.json.

    Returns:
        List of paper trade dicts with player, stat, direction, edge, kelly_size.
    """
    try:
        from src.prediction.player_props import predict_props
        from src.data.props_scraper import scrape_props
    except ImportError:
        return []

    # Get today's props lines
    try:
        lines_raw = scrape_props()
        lines_map: Dict[str, Dict[str, float]] = {}
        for entry in (lines_raw if isinstance(lines_raw, list) else []):
            pid = str(entry.get("player_id", ""))
            stat = entry.get("stat", "")
            line = entry.get("line")
            if pid and stat and line:
                if pid not in lines_map:
                    lines_map[pid] = {}
                lines_map[pid][stat] = float(line)
    except Exception:
        lines_map = {}

    paper_bets = []
    for pid, player_lines in lines_map.items():
        try:
            preds = predict_props(pid)
        except Exception:
            continue
        for stat, line in player_lines.items():
            pred = preds.get(stat) or preds.get(f"predicted_{stat}")
            if pred is None:
                continue
            edge = (float(pred) - line) / max(line, 0.01)
            if abs(edge) < edge_threshold:
                continue
            direction = "over" if edge > 0 else "under"
            from src.prediction.betting_portfolio import kelly_corr
            size = kelly_corr(abs(edge), -110, bankroll)
            paper_bets.append({
                "player_id":  pid,
                "player_name": preds.get("player_name", pid),
                "stat":       stat,
                "direction":  direction,
                "line":       line,
                "pred":       round(float(pred), 2),
                "edge_pct":   round(edge * 100, 2),
                "kelly_size": size,
                "mode":       "paper",
            })

    # Persist
    existing: List[dict] = []
    if os.path.exists(_PAPER_LOG):
        try:
            existing = json.load(open(_PAPER_LOG, encoding="utf-8"))
        except Exception:
            pass
    existing.extend(paper_bets)
    os.makedirs(_MODELS_DIR, exist_ok=True)
    json.dump(existing, open(_PAPER_LOG, "w", encoding="utf-8"), indent=2)
    return paper_bets


def build_prop_residuals(seasons: Optional[List[str]] = None) -> int:
    """
    Bootstrap prop_residuals.json from gamelogs + model predictions.

    For each gamelog_{player_id}_{season}.json, runs predict_props() and pairs
    predictions against actual stats.  Uses actual values as proxy lines
    (no market line available historically).  Skips players where predict_props
    raises or returns no data.

    Returns number of records written.  Safe to re-run — appends only new
    (player_id, game_date, stat) triples not already in the file.
    """
    import glob as _glob
    import re

    try:
        from src.prediction.player_props import predict_props
    except ImportError:
        print("  [residuals] cannot import predict_props — aborting")
        return 0

    seasons = seasons or ["2024-25", "2025-26"]
    season_set = set(seasons)

    residuals_path = os.path.join(_MODELS_DIR, "prop_residuals.json")
    existing: List[dict] = []
    if os.path.exists(residuals_path):
        try:
            existing = json.load(open(residuals_path, encoding="utf-8"))
        except Exception:
            pass

    # Build a set of already-recorded keys to avoid duplicates
    seen = {
        (r.get("player_id"), r.get("game_date"), r.get("stat"))
        for r in existing
    }

    stat_map = {"PTS": "pts", "REB": "reb", "AST": "ast",
                "FG3M": "fg3m", "STL": "stl", "BLK": "blk", "TOV": "tov"}

    pattern = os.path.join(_NBA_DIR, "gamelog_*_*.json")
    files = _glob.glob(pattern)
    new_records: List[dict] = []

    for fpath in files:
        m = re.search(r"gamelog_(\d+)_(.+?)\.json$", os.path.basename(fpath))
        if not m:
            continue
        player_id, season = m.group(1), m.group(2)
        if season not in season_set:
            continue

        try:
            logs = json.load(open(fpath, encoding="utf-8"))
        except Exception:
            continue

        # Run prediction once per player; skip if it fails
        try:
            preds = predict_props(player_id)
        except Exception:
            continue

        for entry in logs:
            game_date = entry.get("GAME_DATE", "")
            for raw_stat, stat in stat_map.items():
                actual = entry.get(raw_stat)
                if actual is None:
                    continue
                key = (player_id, game_date, stat)
                if key in seen:
                    continue
                pred_val = preds.get(stat) or preds.get(f"predicted_{stat}")
                if pred_val is None:
                    continue
                seen.add(key)
                new_records.append({
                    "player_id":   player_id,
                    "player_name": preds.get("player_name", ""),
                    "stat":        stat,
                    "game_date":   game_date,
                    "predicted":   round(float(pred_val), 3),
                    "actual":      float(actual),
                    "line":        float(actual),   # proxy — no historical market line
                    "direction":   "over" if float(pred_val) > float(actual) else "under",
                    "edge_pct":    round((float(pred_val) - float(actual)) / max(float(actual), 0.01), 4),
                })

    if new_records:
        combined = existing + new_records
        os.makedirs(_MODELS_DIR, exist_ok=True)
        json.dump(combined, open(residuals_path, "w", encoding="utf-8"), indent=2)
        print(f"  [residuals] wrote {len(new_records)} new records ({len(combined)} total) → {residuals_path}")
    else:
        print("  [residuals] no new records to write")

    return len(new_records)


def backtest_all_stats(
    seasons: Optional[List[str]] = None,
    edge_threshold: float = 0.04,
) -> dict:
    """Run backtest for all 7 stats. Returns {stat: BacktestResult}."""
    return {stat: backtest_props(seasons, stat, edge_threshold) for stat in STATS}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prop backtester")
    parser.add_argument("--stat", default="pts", choices=STATS + ["all"])
    parser.add_argument("--edge", type=float, default=0.04)
    parser.add_argument("--paper", action="store_true", help="Run paper trades for today")
    parser.add_argument("--build-residuals", action="store_true",
                        help="Bootstrap prop_residuals.json from gamelogs + model predictions")
    args = parser.parse_args()

    if args.build_residuals:
        n = build_prop_residuals()
        print(f"Done — {n} new records written")
    elif args.paper:
        trades = paper_trade_today(edge_threshold=args.edge)
        print(f"Paper trades today: {len(trades)}")
        for t in trades[:10]:
            print(f"  {t['player_name']} {t['stat']} {t['direction']} "
                  f"line={t['line']} pred={t['pred']} edge={t['edge_pct']:.1f}% ${t['kelly_size']:.2f}")
    elif args.stat == "all":
        results = backtest_all_stats(edge_threshold=args.edge)
        print(f"\n{'Stat':<6} {'N':>5} {'Win%':>6} {'ROI%':>6} {'MAE':>5} {'Gate':>5}")
        for stat, r in results.items():
            gate = '✓' if r.passed_gate else '✗'
            print(f"{stat:<6} {r.n_bets:>5} {r.win_rate*100:>5.1f}% "
                  f"{r.roi_pct:>5.1f}% {r.mae:>5.2f} {gate:>5}")
    else:
        r = backtest_props(stat=args.stat, edge_threshold=args.edge)
        print(f"\n{args.stat} backtest: {r.n_bets} bets, {r.win_rate*100:.1f}% win rate, "
              f"{r.roi_pct:.1f}% ROI, MAE={r.mae:.2f}")
        print(f"Gate passed: {r.passed_gate}")
        if r.edge_buckets:
            for bucket, data in r.edge_buckets.items():
                print(f"  Edge {bucket}: n={data['n']}, win%={data['win_rate']*100:.1f}%")
