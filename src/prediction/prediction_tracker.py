"""
prediction_tracker.py — Prompt 6: Prediction tracking + accuracy feedback loop.

Public API
----------
    log_prediction(prediction: dict) -> None
    score_yesterday() -> dict
    get_accuracy_report(last_n_days=30) -> dict

CLI
---
    python -m src.prediction.prediction_tracker --score-yesterday
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")
_SCORED_DIR = os.path.join(_PRED_DIR, "scored")
_STATS = ["pts", "reb", "ast", "fg3m", "blk", "stl", "tov"]
_CONF_BUCKETS = [(0.0, 0.5), (0.5, 0.65), (0.65, 0.8), (0.8, 1.0)]


def log_prediction(prediction: dict) -> None:
    """Persist a prediction dict to data/predictions/ if not already saved."""
    os.makedirs(_PRED_DIR, exist_ok=True)
    game_date = prediction.get("game_date", str(date.today()))
    home = prediction.get("home_team", "UNK")
    away = prediction.get("away_team", "UNK")
    fpath = os.path.join(_PRED_DIR, f"{game_date}_{home}_{away}.json")
    if not os.path.exists(fpath):
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(prediction, f, indent=2, default=str)


def _fetch_box_score(game_date: str) -> Dict[str, Dict[str, float]]:
    """Return {player_id: {stat: value}} for all players on game_date."""
    try:
        from nba_api.stats.endpoints import leaguegamefinder
        import pandas as pd
        gf = leaguegamefinder.LeagueGameFinder(
            date_from_nullable=game_date,
            date_to_nullable=game_date,
            timeout=15,
        )
        games = gf.get_data_frames()[0]
        if games.empty:
            return {}
        game_ids = games["GAME_ID"].unique().tolist()

        from nba_api.stats.endpoints import boxscoretraditionalv2
        actuals: Dict[str, Dict[str, float]] = {}
        for gid in game_ids[:10]:  # cap to avoid rate limits
            try:
                bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=gid, timeout=15)
                pdf = bs.get_data_frames()[0]
                for _, row in pdf.iterrows():
                    pid = str(row.get("PLAYER_ID", ""))
                    if not pid:
                        continue
                    actuals[pid] = {
                        "pts": float(row.get("PTS", 0) or 0),
                        "reb": float(row.get("REB", 0) or 0),
                        "ast": float(row.get("AST", 0) or 0),
                        "fg3m": float(row.get("FG3M", 0) or 0),
                        "blk": float(row.get("BLK", 0) or 0),
                        "stl": float(row.get("STL", 0) or 0),
                        "tov": float(row.get("TO", 0) or 0),
                    }
            except Exception:
                pass
        return actuals
    except Exception:
        return {}


def _load_predictions_for_date(game_date: str) -> List[dict]:
    """Load all prediction files for a given date."""
    if not os.path.exists(_PRED_DIR):
        return []
    preds = []
    for fname in os.listdir(_PRED_DIR):
        if fname.startswith(game_date) and fname.endswith(".json"):
            fpath = os.path.join(_PRED_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    preds.append(json.load(f))
            except Exception:
                pass
    return preds


def score_predictions(game_date: str) -> dict:
    """Score predictions for a date against actual box scores."""
    preds = _load_predictions_for_date(game_date)
    if not preds:
        return {"date": game_date, "error": "no predictions found"}

    actuals = _fetch_box_score(game_date)
    if not actuals:
        return {"date": game_date, "error": "no box scores from nba_api"}

    os.makedirs(_SCORED_DIR, exist_ok=True)
    errors: Dict[str, List[float]] = defaultdict(list)
    clv_entries: List[dict] = []

    for pred in preds:
        for player_entry in pred.get("props", []):
            pid = str(player_entry.get("player_id", ""))
            if pid not in actuals:
                continue
            predictions = player_entry.get("predictions", {})
            confidence = player_entry.get("confidence", {})
            actual = actuals[pid]
            for stat in _STATS:
                pred_val = predictions.get(stat)
                actual_val = actual.get(stat)
                if pred_val is None or actual_val is None:
                    continue
                errors[stat].append(abs(float(pred_val) - float(actual_val)))

        # CLV: for edge plays, measure edge vs outcome
        for ep in pred.get("edges", []):
            pid = str(ep.get("player_id", ""))
            stat = ep.get("stat", "")
            actual_val = actuals.get(pid, {}).get(stat)
            if actual_val is None:
                continue
            line = ep.get("line", 0.0)
            direction = ep.get("direction", "over")
            hit = (actual_val > line) if direction == "over" else (actual_val < line)
            clv_entries.append({
                "player_id": pid,
                "player_name": ep.get("player_name"),
                "stat": stat,
                "direction": direction,
                "line": line,
                "actual": actual_val,
                "edge_pct": ep.get("edge_pct"),
                "kelly_size_usd": ep.get("kelly_size_usd"),
                "hit": hit,
            })

    mae = {stat: round(sum(v) / len(v), 3) for stat, v in errors.items() if v}
    clv_hit_rate = (
        round(sum(1 for e in clv_entries if e["hit"]) / len(clv_entries), 3)
        if clv_entries else None
    )

    scored = {
        "date": game_date,
        "mae_by_stat": mae,
        "clv_hit_rate": clv_hit_rate,
        "clv_entries": clv_entries,
        "players_scored": sum(len(v) for v in errors.values()),
    }
    out_path = os.path.join(_SCORED_DIR, f"{game_date}_scored.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2, default=str)
    return scored


def score_yesterday() -> dict:
    yesterday = str(date.today() - timedelta(days=1))
    return score_predictions(yesterday)


def get_accuracy_report(last_n_days: int = 30) -> dict:
    """Aggregate scored results from the last N days."""
    if not os.path.exists(_SCORED_DIR):
        return {"error": "no scored predictions yet"}

    all_mae: Dict[str, List[float]] = defaultdict(list)
    all_clv_hits: List[bool] = []
    days_found = 0

    cutoff = date.today() - timedelta(days=last_n_days)
    for fname in sorted(os.listdir(_SCORED_DIR)):
        if not fname.endswith("_scored.json"):
            continue
        d_str = fname.replace("_scored.json", "")
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if d < cutoff:
            continue
        fpath = os.path.join(_SCORED_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        days_found += 1
        for stat, mae in s.get("mae_by_stat", {}).items():
            all_mae[stat].append(float(mae))
        for e in s.get("clv_entries", []):
            if "hit" in e:
                all_clv_hits.append(e["hit"])

    if not days_found:
        return {"error": f"no scored data in last {last_n_days} days"}

    avg_mae = {stat: round(sum(v) / len(v), 3) for stat, v in all_mae.items()}
    clv_hit_rate = (
        round(sum(all_clv_hits) / len(all_clv_hits), 3) if all_clv_hits else None
    )
    return {
        "last_n_days": last_n_days,
        "days_with_data": days_found,
        "avg_mae_by_stat": avg_mae,
        "clv_hit_rate": clv_hit_rate,
        "total_edge_plays_scored": len(all_clv_hits),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prediction tracker / accuracy scorer")
    parser.add_argument("--score-yesterday", action="store_true")
    parser.add_argument("--score-date", default=None, help="ISO date e.g. 2026-04-07")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    if args.score_yesterday:
        result = score_yesterday()
        print(json.dumps(result, indent=2, default=str))
    elif args.score_date:
        result = score_predictions(args.score_date)
        print(json.dumps(result, indent=2, default=str))
    elif args.report:
        result = get_accuracy_report(args.days)
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()
