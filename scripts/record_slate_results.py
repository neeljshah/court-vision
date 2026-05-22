"""
record_slate_results.py — Phase 14.2: Record actual box-score results for a slate.

Run the morning after each slate (T+1). Loads slate_YYYYMMDD.json, fetches
actual box scores, appends (pred, actual) pairs to prop_residuals.json, and
updates bet_log.json win/loss/pnl.

Usage:
    python scripts/record_slate_results.py [--date YYYY-MM-DD]
    # Defaults to yesterday if --date is omitted.

Idempotent: skips rows already in prop_residuals.json (keyed by player_id + date + stat).
Handles postponed/missing games gracefully (warns, skips).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_RESIDUALS  = os.path.join(_MODELS_DIR, "prop_residuals.json")
_BET_LOG    = os.path.join(_MODELS_DIR, "bet_log.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
BOX_COL = {"pts": "PTS", "reb": "REB", "ast": "AST",
           "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_boxscore(game_id: str) -> dict[int, dict]:
    """Return player_id → stat dict from BoxScoreTraditional. Returns {} on failure."""
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2
        time.sleep(0.6)
        bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        df = bs.get_data_frames()[0]   # player stats frame
        result: dict[int, dict] = {}
        for _, row in df.iterrows():
            pid = int(row["PLAYER_ID"])
            result[pid] = {
                "PTS":  _safe_float(row.get("PTS")),
                "REB":  _safe_float(row.get("REB")),
                "AST":  _safe_float(row.get("AST")),
                "FG3M": _safe_float(row.get("FG3M")),
                "STL":  _safe_float(row.get("STL")),
                "BLK":  _safe_float(row.get("BLK")),
                "TOV":  _safe_float(row.get("TOV")),
                "MIN":  row.get("MIN", ""),
            }
        return result
    except Exception as e:
        print(f"    [boxscore] {game_id}: {e}")
        return {}


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


# ── Residuals ─────────────────────────────────────────────────────────────────

def _load_residuals() -> tuple[list[dict], set[tuple]]:
    if os.path.exists(_RESIDUALS):
        try:
            data = json.load(open(_RESIDUALS, encoding="utf-8"))
            keys = {(r["player_id"], r["game_date"], r["stat"]) for r in data}
            return data, keys
        except Exception:
            pass
    return [], set()


def _save_residuals(records: list[dict]) -> None:
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_RESIDUALS, "w", encoding="utf-8") as f:
        json.dump(records, f)


# ── Bet log ───────────────────────────────────────────────────────────────────

def _load_bet_log() -> list[dict]:
    if os.path.exists(_BET_LOG):
        try:
            return json.load(open(_BET_LOG, encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_bet_log(bets: list[dict]) -> None:
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_BET_LOG, "w", encoding="utf-8") as f:
        json.dump(bets, f, indent=2)


def _resolve_bets(bets: list[dict], actuals_by_player: dict[int, dict],
                  slate_date: str) -> tuple[int, int]:
    """Update open bets from this slate's date with win/loss/pnl. Returns (resolved, skipped)."""
    resolved = skipped = 0
    for bet in bets:
        if bet.get("status") not in (None, "open", "paper"):
            continue
        if bet.get("game_date", "")[:10] != slate_date[:10]:
            continue

        pid = bet.get("player_id")
        stat = bet.get("stat")
        line = bet.get("line")
        odds = bet.get("odds", -110)
        stake = bet.get("stake", 0.0)

        if not pid or not stat or line is None:
            skipped += 1
            continue

        player_actuals = actuals_by_player.get(int(pid), {})
        col = BOX_COL.get(stat)
        if not col:
            skipped += 1
            continue
        actual = player_actuals.get(col)
        if actual is None:
            skipped += 1
            continue

        direction = bet.get("direction", "over")
        won = (actual > line) if direction == "over" else (actual < line)

        if odds < 0:
            pnl = stake if won else -stake
        else:
            pnl = stake * (odds / 100) if won else -stake

        bet["actual"] = actual
        bet["won"] = won
        bet["pnl"] = round(pnl, 2)
        bet["status"] = "won" if won else "lost"
        resolved += 1

    return resolved, skipped


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Record slate results into prop_residuals.json")
    parser.add_argument("--date", default=None,
                        help="Slate date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    if args.date:
        slate_date = args.date
    else:
        slate_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    date_nodash = slate_date.replace("-", "")
    slate_path = os.path.join(_OUTPUT_DIR, f"slate_{date_nodash}.json")

    if not os.path.exists(slate_path):
        print(f"No slate file for {slate_date}: {slate_path}")
        sys.exit(0)

    print(f"Recording results for slate: {slate_date}")
    slate = json.load(open(slate_path, encoding="utf-8"))
    predictions = slate.get("all_predictions", [])
    if not predictions:
        print("  Slate has no predictions — nothing to record.")
        sys.exit(0)

    print(f"  {len(predictions)} player predictions in slate")

    # Deduplicate game_ids in slate
    game_ids: set[str] = {p["game_id"] for p in predictions if p.get("game_id")}
    print(f"  Fetching box scores for {len(game_ids)} games...")

    actuals_by_game: dict[str, dict[int, dict]] = {}
    for gid in sorted(game_ids):
        print(f"    {gid}...", end=" ", flush=True)
        box = _fetch_boxscore(gid)
        if box:
            actuals_by_game[gid] = box
            print(f"{len(box)} players")
        else:
            print("postponed/missing")

    # Merge player actuals across games (by player_id)
    actuals_by_player: dict[int, dict] = {}
    for box in actuals_by_game.values():
        actuals_by_player.update(box)

    # Build residual rows
    residuals, existing_keys = _load_residuals()
    season = f"{int(slate_date[:4]) - 1}-{slate_date[2:4]}"  # e.g. 2025-26 → 2024-25
    # Adjust: if month >= 10 it's the start of a new season
    dt = datetime.strptime(slate_date, "%Y-%m-%d")
    if dt.month >= 10:
        season = f"{dt.year}-{str(dt.year + 1)[2:]}"
    else:
        season = f"{dt.year - 1}-{str(dt.year)[2:]}"

    new_rows = added = duped = missing = 0
    for pred in predictions:
        pid = pred.get("player_id")
        game_id = pred.get("game_id")
        player_name = pred.get("player", "")
        if not pid:
            continue

        player_actuals = actuals_by_player.get(int(pid))
        if not player_actuals:
            missing += 1
            continue

        for stat in STATS:
            key = (int(pid), slate_date, stat)
            if key in existing_keys:
                duped += 1
                continue
            predicted = pred.get(stat)
            col = BOX_COL[stat]
            actual = player_actuals.get(col)
            line = pred.get(f"{stat}_book_line") or predicted
            if predicted is None or actual is None:
                continue

            residuals.append({
                "player_id":   int(pid),
                "player_name": player_name,
                "game_date":   slate_date,
                "game_id":     game_id or "",
                "season":      season,
                "stat":        stat,
                "predicted":   round(float(predicted), 4),
                "actual":      float(actual),
                "line":        round(float(line), 4) if line is not None else round(float(predicted), 4),
                "source":      "slate",
            })
            existing_keys.add(key)
            added += 1

    _save_residuals(residuals)
    print(f"\nResiduals: +{added} new, {duped} duped, {missing} players missing box score")
    print(f"Total residuals: {len(residuals)}")

    # Resolve bets
    bets = _load_bet_log()
    if bets:
        res, skip = _resolve_bets(bets, actuals_by_player, slate_date)
        if res > 0:
            _save_bet_log(bets)
        print(f"Bets: {res} resolved, {skip} skipped (open from other dates or missing data)")

    # Generate weekly CLV beat-rate report + refresh the CLV training dataset
    try:
        target_date = datetime.strptime(slate_date, "%Y-%m-%d").date()
        _week = f"{target_date.isocalendar()[0]}-W{target_date.isocalendar()[1]:02d}"
        sys.path.insert(0, os.path.dirname(__file__))
        from clv_tracker import build_clv_training_data, generate_beat_rate_report
        generate_beat_rate_report(week=_week)
        build_clv_training_data()
    except Exception as _e:
        print(f"  [record_slate_results] CLV report skipped: {_e}")

    print(f"\nDone. Run calibration next:")
    print(f"  python scripts/fit_prop_calibration.py --all-stats")


if __name__ == "__main__":
    main()
