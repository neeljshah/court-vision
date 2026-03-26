"""
outcome_recorder.py -- Phase D2: Record actual outcomes vs predictions after each game.

After a game completes:
1. Pull actual box score from NBA API
2. Compare against stored predictions for every prop
3. Store to `outcomes` table: player, stat, predicted, actual, error
4. Compute rolling MAE per model

Public API
----------
    record_game_outcomes(game_id, season)  -> dict  (summary)
    get_model_accuracy(stat, n_games)      -> dict  (rolling MAE)
    get_calibration_report(n_games)        -> dict  (all models)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_EVENTS_DIR = os.path.join(PROJECT_DIR, "data", "events")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")

_STAT_COLS = {
    "pts":  "PTS",
    "reb":  "REB",
    "ast":  "AST",
    "fg3m": "FG3M",
    "stl":  "STL",
    "blk":  "BLK",
    "tov":  "TOV",
}


# ── Box score fetcher ─────────────────────────────────────────────────────────

def _fetch_box_score(game_id: str) -> dict:
    """
    Fetch player box score from NBA API for a game.

    Returns:
        {player_id (int): {"pts": float, "reb": float, ...}, ...}
    """
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2
        import time as _time
        _time.sleep(0.8)
        resp = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[outcome_recorder] BoxScore error for {game_id}: {e}")
        return {}

    result = {}
    for _, row in df.iterrows():
        pid = int(row.get("PLAYER_ID", 0) or 0)
        if not pid:
            continue
        stats = {}
        for stat, col in _STAT_COLS.items():
            val = row.get(col)
            if val is not None:
                try:
                    stats[stat] = float(val)
                except (TypeError, ValueError):
                    stats[stat] = 0.0
        result[pid] = stats

    return result


# ── Prediction loader ─────────────────────────────────────────────────────────

def _load_game_predictions(game_id: str) -> dict:
    """
    Load stored predictions for a game.
    Checks: data/events/{game_id}_features.json for embedded predictions,
            or tries PostgreSQL predictions table.

    Returns:
        {player_id (int): {"pts": float, ...}, ...}
    """
    # Try flat predictions JSON first
    pred_path = os.path.join(_EVENTS_DIR, f"{game_id}_predictions.json")
    if os.path.exists(pred_path):
        try:
            data = json.load(open(pred_path))
            # Normalize: {str(pid): {stat: value}}
            return {int(k): v for k, v in data.items() if k.isdigit()}
        except Exception:
            pass

    # Try PostgreSQL
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT predictions_json FROM predictions WHERE game_id = %s LIMIT 1",
                    (game_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    props = data.get("props", data)
                    return {int(k): v for k, v in props.items() if str(k).isdigit()}
    except Exception:
        pass

    return {}


# ── Core recorder ─────────────────────────────────────────────────────────────

def record_game_outcomes(
    game_id: str,
    season: str = "2024-25",
    model_version: str = "v1",
) -> dict:
    """
    Pull actual box score and compare against predictions.
    Stores results to PostgreSQL outcomes table.

    Args:
        game_id:       NBA game ID
        season:        Season string
        model_version: Which model version made the predictions

    Returns:
        {
            "game_id": str,
            "players_recorded": int,
            "stats_recorded": int,
            "mae_by_stat": {"pts": float, ...},
            "stored_to_db": bool,
        }
    """
    # Fetch actual box score
    actual = _fetch_box_score(game_id)
    if not actual:
        return {"game_id": game_id, "error": "no_boxscore", "players_recorded": 0}

    # Load stored predictions
    predictions = _load_game_predictions(game_id)

    # Compute errors
    outcome_rows = []
    errors_by_stat: dict = {s: [] for s in _STAT_COLS}

    for pid, act_stats in actual.items():
        pred_stats = predictions.get(pid, {})
        for stat in _STAT_COLS:
            act_val = act_stats.get(stat)
            if act_val is None:
                continue
            pred_val = pred_stats.get(stat)
            error = (act_val - pred_val) if pred_val is not None else None
            if error is not None:
                errors_by_stat[stat].append(abs(error))

            outcome_rows.append({
                "game_id":         game_id,
                "player_id":       pid,
                "season":          season,
                "stat_name":       stat,
                "actual_value":    act_val,
                "predicted_value": pred_val,
                "error":           error,
                "model_version":   model_version,
            })

    mae_by_stat = {
        s: round(sum(v) / len(v), 4) if v else None
        for s, v in errors_by_stat.items()
    }

    # Store to PostgreSQL
    stored = _store_outcomes(outcome_rows)

    # Also save to JSON file for offline inspection
    out_path = os.path.join(_EVENTS_DIR, f"{game_id}_outcomes.json")
    os.makedirs(_EVENTS_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "game_id":      game_id,
            "season":       season,
            "mae_by_stat":  mae_by_stat,
            "outcomes":     outcome_rows,
        }, f, indent=2)

    return {
        "game_id":           game_id,
        "players_recorded":  len(actual),
        "stats_recorded":    len(outcome_rows),
        "mae_by_stat":       mae_by_stat,
        "stored_to_db":      stored,
        "output_path":       out_path,
    }


def _store_outcomes(rows: list) -> bool:
    """Insert outcome rows into PostgreSQL outcomes table."""
    if not rows:
        return False
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                for r in rows:
                    cur.execute(
                        """
                        INSERT INTO outcomes
                            (game_id, player_id, season, stat_name, actual_value,
                             predicted_value, error, model_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            r["game_id"], r["player_id"], r["season"],
                            r["stat_name"], r["actual_value"],
                            r["predicted_value"], r["error"], r["model_version"],
                        ),
                    )
            conn.commit()
        return True
    except Exception as e:
        print(f"[outcome_recorder] DB store error: {e}")
        return False


# ── Rolling accuracy ──────────────────────────────────────────────────────────

def get_model_accuracy(
    stat: str = "pts",
    n_games: int = 20,
    season: Optional[str] = None,
) -> dict:
    """
    Compute rolling MAE and R² for a prop model over the last N games.

    Returns:
        {"stat": str, "mae": float, "r2": float, "n": int, "source": str}
    """
    # Try PostgreSQL first
    try:
        from src.data.db import get_connection
        import math
        with get_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT actual_value, predicted_value
                    FROM outcomes
                    WHERE stat_name = %s
                      AND predicted_value IS NOT NULL
                    ORDER BY recorded_at DESC
                    LIMIT %s
                """
                params = [stat, n_games * 15]  # ~15 players per game
                if season:
                    query = query.replace("WHERE stat_name", "WHERE season = %s AND stat_name")
                    params.insert(0, season)
                cur.execute(query, params)
                rows = cur.fetchall()

        if rows:
            actual  = [r[0] for r in rows]
            pred    = [r[1] for r in rows]
            errors  = [abs(a - p) for a, p in zip(actual, pred)]
            mae     = round(sum(errors) / len(errors), 4)
            mean_a  = sum(actual) / len(actual)
            ss_res  = sum((a - p) ** 2 for a, p in zip(actual, pred))
            ss_tot  = sum((a - mean_a) ** 2 for a in actual)
            r2      = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0
            return {"stat": stat, "mae": mae, "r2": r2, "n": len(rows), "source": "db"}
    except Exception:
        pass

    # Fallback: read from local outcome files
    all_actual, all_pred = [], []
    if os.path.isdir(_EVENTS_DIR):
        files = sorted(
            [f for f in os.listdir(_EVENTS_DIR) if f.endswith("_outcomes.json")],
            reverse=True,
        )[:n_games]
        for fname in files:
            try:
                data = json.load(open(os.path.join(_EVENTS_DIR, fname)))
                for row in data.get("outcomes", []):
                    if row.get("stat_name") == stat and row.get("predicted_value") is not None:
                        all_actual.append(row["actual_value"])
                        all_pred.append(row["predicted_value"])
            except Exception:
                pass

    if not all_actual:
        return {"stat": stat, "mae": None, "r2": None, "n": 0, "source": "none"}

    errors = [abs(a - p) for a, p in zip(all_actual, all_pred)]
    mae    = round(sum(errors) / len(errors), 4)
    mean_a = sum(all_actual) / len(all_actual)
    ss_res = sum((a - p) ** 2 for a, p in zip(all_actual, all_pred))
    ss_tot = sum((a - mean_a) ** 2 for a in all_actual)
    r2     = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0
    return {"stat": stat, "mae": mae, "r2": r2, "n": len(all_actual), "source": "file"}


def get_calibration_report(n_games: int = 20) -> dict:
    """Return accuracy report for all 7 prop models."""
    return {
        stat: get_model_accuracy(stat, n_games)
        for stat in _STAT_COLS
    }


# ── log_predictions ───────────────────────────────────────────────────────────

def log_predictions(edges: list) -> None:
    """
    Save today's BetEdge predictions to data/predictions/predictions_{today}.json
    and to PostgreSQL predictions table if DATABASE_URL is set.

    Args:
        edges: list of BetEdge (or dict-like) from PredictionOrchestrator.get_today_edges()
    """
    from datetime import date as _date
    today = _date.today().isoformat()
    pred_dir = os.path.join(PROJECT_DIR, "data", "predictions")
    os.makedirs(pred_dir, exist_ok=True)
    out_path = os.path.join(pred_dir, f"predictions_{today}.json")

    def _edge_to_dict(edge) -> dict:
        if isinstance(edge, dict):
            return edge
        return {k: getattr(edge, k, None) for k in (
            "player_id", "player_name", "stat", "direction", "line",
            "projection", "ev", "kelly_fraction", "confidence",
            "model_agreement", "game_id", "date",
        )}

    rows = [_edge_to_dict(e) for e in (edges or [])]

    # Write to JSON
    try:
        with open(out_path, "w") as f:
            json.dump({"date": today, "predictions": rows}, f, indent=2)
    except Exception as e:
        print(f"[outcome_recorder] log_predictions JSON write error: {e}")

    # Write to PostgreSQL if available
    if os.environ.get("DATABASE_URL"):
        try:
            from src.data.db import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    for row in rows:
                        cur.execute(
                            """
                            INSERT INTO predictions
                                (game_id, player_id, stat_name, direction,
                                 line_value, projection, ev, kelly_fraction,
                                 confidence, predictions_json, prediction_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                row.get("game_id"), str(row.get("player_id", "")),
                                row.get("stat"), row.get("direction"),
                                row.get("line"), row.get("projection"),
                                row.get("ev"), row.get("kelly_fraction"),
                                row.get("confidence"), json.dumps(row), today,
                            ),
                        )
                conn.commit()
        except Exception as e:
            print(f"[outcome_recorder] log_predictions DB error: {e}")


class OutcomeRecorder:
    """Class wrapper around module-level functions for caller convenience."""

    def record_outcome(
        self,
        game_id: str,
        player_id: int,
        stat: str,
        predicted: float,
        actual: float,
        line: float,
        season: str = "2024-25",
    ) -> None:
        """Record a single predicted vs actual outcome."""
        row = {
            "game_id":         game_id,
            "player_id":       player_id,
            "season":          season,
            "stat_name":       stat,
            "actual_value":    actual,
            "predicted_value": predicted,
            "error":           actual - predicted,
            "model_version":   "v1",
        }
        _store_outcomes([row])

    def log_predictions(self, edges: list) -> None:
        """Delegate to module-level log_predictions."""
        log_predictions(edges)

    def record_game(self, game_id: str, season: str = "2024-25") -> dict:
        """Convenience wrapper around record_game_outcomes."""
        return record_game_outcomes(game_id, season)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Record actual outcomes for a game")
    parser.add_argument("--game-id", required=True, help="NBA game ID")
    parser.add_argument("--season",  default="2024-25")
    parser.add_argument("--report",  action="store_true", help="Print calibration report")
    args = parser.parse_args()

    if args.report:
        report = get_calibration_report()
        print("\nModel Calibration Report (last 20 games):")
        for stat, metrics in report.items():
            mae = metrics.get("mae")
            r2  = metrics.get("r2")
            n   = metrics.get("n", 0)
            mae_str = f"{mae:.4f}" if mae is not None else "N/A"
            r2_str  = f"{r2:.4f}"  if r2  is not None else "N/A"
            print(f"  {stat}: MAE={mae_str}  R2={r2_str}  n={n}")
    else:
        result = record_game_outcomes(args.game_id, args.season)
        print(json.dumps(result, indent=2))
