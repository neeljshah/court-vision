"""fetch_actuals.py — pull post-game player stat lines from NBA Stats for a date.

Closes the cycle-68/69 settlement loop:
    1. compare_to_lines --bet-log    -> data/bets/<date>.csv             (cycle 68)
    2. (games complete)
    3. python scripts/fetch_actuals.py --date <date>
                                       -> data/actuals/<date>.csv         (this cycle)
    4. python scripts/settle_bets.py data/bets/<date>.csv data/actuals/<date>.csv
                                       -> data/bets/<date>_settled.csv    (cycle 69)

Output schema matches what settle_bets.py expects:
    date, player, stat, actual_value

One row per (player, stat) — 7 rows per player who played
(pts, reb, ast, fg3m, stl, blk, tov).

Fetch flow:
    predict_slate.fetch_games(date_str)  ->  list of games for the date
    for each game: boxscoretraditionalv2(game_id) -> per-player rows
    flatten to 7 rows per player

Run:
    python scripts/fetch_actuals.py                          # today's games
    python scripts/fetch_actuals.py --date 2026-05-23        # historical
    python scripts/fetch_actuals.py --date 2026-05-23 --out /tmp/x.csv

Sandbox note: nba_api ScoreboardV2 / boxscoretraditionalv2 may be blocked
from non-residential IPs (Agent A documented this for the injury-PDF source).
The script reports zero games + zero rows in that case rather than crashing.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import date as _date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports.
import src.data.nba_api_headers_patch  # noqa: F401, E402


# Mapping from nba_api BoxScoreTraditionalV2 column → canonical stat key.
# The endpoint also returns MIN, FGM, etc. — we only emit the 7 the model
# predicts.
_STAT_COL_MAP = {
    "pts":  "PTS",
    "reb":  "REB",
    "ast":  "AST",
    "fg3m": "FG3M",
    "stl":  "STL",
    "blk":  "BLK",
    "tov":  "TO",      # NBA Stats uses 'TO' not 'TOV'
}


def _today_iso() -> str:
    return _date.today().isoformat()


def fetch_games_for_date(date_str: str) -> List[Dict]:
    """Wraps predict_slate.fetch_games. Returns list of game dicts."""
    try:
        from scripts.predict_slate import fetch_games  # noqa: PLC0415
    except Exception as e:
        print(f"  [warn] fetch_games unavailable: {e}")
        return []
    return fetch_games(date_str)


def fetch_box_score(game_id: str, sleep_secs: float = 0.6) -> List[Dict]:
    """Pull one game's player-level box score. Returns list of player rows.

    Each row has at least PLAYER_NAME + the columns in _STAT_COL_MAP.values().
    """
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2  # noqa: PLC0415
        time.sleep(sleep_secs)
        df = boxscoretraditionalv2.BoxScoreTraditionalV2(
            game_id=game_id).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] box score fetch {game_id}: {e}")
        return []
    return df.to_dict("records")


def rows_for_player(player_row: Dict, date_str: str) -> List[Dict]:
    """Convert one player's box-score row to per-stat actuals rows.

    Skips players with MIN == 0 / NaN / blank (didn't play).
    """
    minutes = player_row.get("MIN")
    # MIN comes as "MM:SS" string or "0" or None for DNPs.
    if minutes in (None, "", "0", "0:00"):
        return []
    name = player_row.get("PLAYER_NAME", "").strip()
    if not name:
        return []
    out = []
    for stat_key, col in _STAT_COL_MAP.items():
        v = player_row.get(col)
        if v is None:
            continue
        try:
            actual = float(v)
        except (TypeError, ValueError):
            continue
        out.append({
            "date":         date_str,
            "player":       name,
            "stat":         stat_key,
            "actual_value": f"{actual:g}",
        })
    return out


def write_csv(rows: List[Dict], out_path: str) -> int:
    """Write actuals rows in the schema settle_bets expects."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "player", "stat", "actual_value"])
        for r in rows:
            w.writerow([r["date"], r["player"], r["stat"], r["actual_value"]])
    return len(rows)


def fetch_actuals_for_date(date_str: str,
                             games_fn=fetch_games_for_date,
                             box_fn=fetch_box_score) -> List[Dict]:
    """Orchestrator: fetch all games + their box scores; return flat actuals rows.

    games_fn / box_fn are injectable for tests so we don't hit nba_api.
    """
    games = games_fn(date_str)
    if not games:
        return []
    all_rows: List[Dict] = []
    for g in games:
        gid = g.get("game_id")
        if not gid:
            continue
        for player_row in box_fn(gid):
            all_rows.extend(rows_for_player(player_row, date_str))
    return all_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="Date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: data/actuals/<date>.csv)")
    args = ap.parse_args()

    date_str = args.date or _today_iso()
    out = args.out or os.path.join(PROJECT_DIR, "data", "actuals",
                                     f"{date_str}.csv")

    print(f"[fetch_actuals] fetching games + box scores for {date_str}",
          flush=True)
    rows = fetch_actuals_for_date(date_str)
    if not rows:
        print(f"[fetch_actuals] no actuals (no games OR nba_api blocked); "
              f"not writing {out}.")
        return 1
    n = write_csv(rows, out)
    n_players = len({r["player"] for r in rows})
    print(f"  wrote {n} actuals rows ({n_players} players) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
