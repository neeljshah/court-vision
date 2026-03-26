"""
record_outcome.py — Record actual game stats and update CLV tracking.

Run AFTER a game ends to compare predictions vs actuals.

Usage:
    conda activate basketball_ai
    python scripts/record_outcome.py --game-id 0022401001
    python scripts/record_outcome.py --game-id 0022401001 --season 2024-25
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date as _date

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("record_outcome")

TODAY = _date.today().isoformat()

_STAT_COLS = {
    "pts": "PTS", "reb": "REB", "ast": "AST",
    "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV",
}


# ── Step 1+2: Fetch actual box score ──────────────────────────────────────────

def fetch_actuals(game_id: str) -> dict:
    """Fetch player box score from NBA API. Returns {player_id: {stat: val}}."""
    log.info("Fetching box score for game %s …", game_id)
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2
        time.sleep(0.8)
        resp = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        df   = resp.get_data_frames()[0]
    except Exception as e:
        log.warning("NBA API box score error: %s", e)
        return {}

    result: dict = {}
    for _, row in df.iterrows():
        pid = int(row.get("PLAYER_ID", 0) or 0)
        if not pid:
            continue
        stats: dict = {}
        for stat, col in _STAT_COLS.items():
            val = row.get(col)
            if val is not None:
                try:
                    stats[stat] = float(val)
                except (TypeError, ValueError):
                    stats[stat] = 0.0
        result[pid] = {"name": str(row.get("PLAYER_NAME", "")), **stats}
    log.info("  %d players in box score", len(result))
    return result


# ── Step 3: Load today's predictions ─────────────────────────────────────────

def load_predictions(game_id: str) -> dict:
    """
    Load today's edge predictions.

    Checks data/edges/edges_{today}.json first, then
    data/predictions/predictions_{today}.json (written by OutcomeRecorder).
    Merges both if both exist.

    Keys in returned dict:
      (int_player_id, stat)   — when player_id is a numeric ID
      ("__name__", name, stat) — fallback when player_id is a name string
    """
    paths = [
        os.path.join(PROJECT_DIR, "data", "edges", f"edges_{TODAY}.json"),
        os.path.join(PROJECT_DIR, "data", "predictions", f"predictions_{TODAY}.json"),
    ]

    result: dict = {}
    loaded_any = False
    for pred_path in paths:
        if not os.path.exists(pred_path):
            continue
        try:
            with open(pred_path) as f:
                raw = json.load(f)
            edges = raw if isinstance(raw, list) else raw.get("predictions", [])
            for edge in edges:
                pid  = edge.get("player_id")
                stat = edge.get("stat")
                if pid is None or stat is None:
                    continue
                # Prefer numeric key; fall back to name key when pid is a name string
                try:
                    result[(int(pid), stat)] = edge
                except (TypeError, ValueError):
                    player_name = (edge.get("player_name") or str(pid)).lower()
                    result[("__name__", player_name, stat)] = edge
            loaded_any = True
        except Exception as e:
            log.warning("Could not load predictions from %s: %s", pred_path, e)

    if not loaded_any:
        log.warning("No predictions file found for today (%s)", TODAY)
    else:
        log.info("  Loaded %d prediction edges", len(result))
    return result


# ── Step 4+5: Compare + record outcomes ──────────────────────────────────────

def compare_and_record(game_id: str, actuals: dict, predictions: dict, season: str) -> dict:
    """Compare actuals vs predictions and record outcomes."""
    from src.pipeline.outcome_recorder import OutcomeRecorder

    recorder = OutcomeRecorder()
    hits = []
    misses = []
    clv_values = []

    for pid, player_data in actuals.items():
        name = player_data.get("name", str(pid))
        for stat in _STAT_COLS:
            actual = player_data.get(stat)
            if actual is None:
                continue

            edge = predictions.get((pid, stat))
            # Name-based fallback when player_id was stored as a name string
            if edge is None:
                edge = predictions.get(("__name__", name.lower(), stat))
            if edge is None:
                continue

            predicted = edge.get("projection", 0.0)
            line      = edge.get("line", 0.0)
            direction = edge.get("direction", "over")
            ev        = edge.get("ev", 0.0)

            try:
                recorder.record_outcome(
                    game_id=game_id,
                    player_id=pid,
                    stat=stat,
                    predicted=float(predicted or 0),
                    actual=float(actual),
                    line=float(line or 0),
                    season=season,
                )
            except Exception as e:
                log.warning("record_outcome error pid=%s stat=%s: %s", pid, stat, e)

            # CLV: did we beat the closing line?
            won = (actual > line) if direction == "over" else (actual < line)
            clv_values.append(ev if won else -ev)

            entry = {
                "player": name, "stat": stat,
                "predicted": predicted, "actual": actual,
                "line": line, "direction": direction, "ev": ev, "won": won,
            }
            (hits if won else misses).append(entry)

    return {"hits": hits, "misses": misses, "clv_values": clv_values}


# ── Step 6: Print CLV report ──────────────────────────────────────────────────

def print_clv_report(game_id: str, results: dict) -> None:
    hits   = results["hits"]
    misses = results["misses"]
    clv    = results["clv_values"]

    n_total = len(hits) + len(misses)
    avg_clv = (sum(clv) / len(clv)) if clv else 0.0

    print("\n" + "=" * 60)
    print(f"  CLV Report — Game {game_id} — {TODAY}")
    print("=" * 60)
    print(f"  Predictions matched: {n_total}")
    print(f"  Wins:   {len(hits)}  ({100*len(hits)/max(n_total,1):.0f}%)")
    print(f"  Losses: {len(misses)}")
    print(f"  Avg CLV: {avg_clv:+.4f}")

    if hits:
        print("\n  Top Hits:")
        for h in sorted(hits, key=lambda x: float(x.get("ev", 0)), reverse=True)[:3]:
            print(f"    ✓ {h['player']} {h['stat']}: pred={h['predicted']:.1f} "
                  f"actual={h['actual']:.1f} line={h['line']} EV={h['ev']:.3f}")

    if misses:
        print("\n  Top Misses:")
        for m in sorted(misses, key=lambda x: float(x.get("ev", 0)), reverse=True)[:3]:
            print(f"    ✗ {m['player']} {m['stat']}: pred={m['predicted']:.1f} "
                  f"actual={m['actual']:.1f} line={m['line']} EV={m['ev']:.3f}")

    print("=" * 60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Record actual game outcomes vs predictions")
    parser.add_argument("--game-id", required=True, help="NBA game ID, e.g. 0022401001")
    parser.add_argument("--season",  default="2024-25")
    args = parser.parse_args()

    log.info("Recording outcomes for game %s …", args.game_id)

    actuals     = fetch_actuals(args.game_id)
    if not actuals:
        log.warning("No box score data — cannot record outcomes")
        return

    predictions = load_predictions(args.game_id)
    results     = compare_and_record(args.game_id, actuals, predictions, args.season)
    print_clv_report(args.game_id, results)


if __name__ == "__main__":
    main()
