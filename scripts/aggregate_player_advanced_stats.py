"""aggregate_player_advanced_stats.py — build per-player advanced-stat time series.

Reads every cached data/nba/boxscore_adv_*.json (cycle 1 bg fetch product —
2455 games) and writes data/player_adv_stats.parquet with one row per
(player_id, game_id, game_date) containing the player's per-game advanced
stats: USG%, TS%, AST%, REB%, OREB%, DREB%, OFF_RATING, DEF_RATING, NET_RATING,
EFG%, AST/TO, PIE, possessions, paceper40.

Game-date join: pulled from the cached data/nba/season_games_<season>.json
files (game_id -> game_date).

Output schema is ready for prop_pergame to compute L5/L10/EWMA rolling means
keyed on player_id, with shift(1) point-in-time protection.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")

# Per-game advanced stats we keep — all come straight from boxscoreadvancedv3.
_ADV_COLS = (
    "usagepercentage",
    "trueshootingpercentage",
    "effectivefieldgoalpercentage",
    "assistpercentage",
    "reboundpercentage",
    "offensivereboundpercentage",
    "defensivereboundpercentage",
    "offensiverating",
    "defensiverating",
    "netrating",
    "assisttoturnover",
    "assistratio",
    "turnoverratio",
    "pie",
    "possessions",
    "paceper40",
    "minutes",
)


def build_game_date_lookup() -> Dict[str, str]:
    """Map game_id -> game_date by scanning cached season_games files."""
    lookup: Dict[str, str] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for g in rows:
            gid = str(g.get("game_id", "")).zfill(10)
            if gid:
                lookup[gid] = str(g.get("game_date", ""))
    return lookup


def parse_minutes(raw) -> float:
    """boxscoreadvancedv3 minutes can be 'mm:ss' (e.g. '28:17'), 'PT34M12.0S'
    ISO duration, or a plain float — handle all three."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if ":" in s and not s.startswith("PT"):
        mm, _, ss = s.partition(":")
        try:
            return round(float(mm) + float(ss) / 60.0, 2)
        except ValueError:
            return 0.0
    if s.startswith("PT"):
        s = s[2:]
        mins = 0.0
        if "M" in s:
            mins_str, _, rest = s.partition("M")
            try:
                mins = float(mins_str)
            except ValueError:
                mins = 0.0
            s = rest
        if "S" in s:
            sec_str = s.rstrip("S")
            try:
                mins += float(sec_str) / 60.0
            except ValueError:
                pass
        return round(mins, 2)
    try:
        return float(s)
    except ValueError:
        return 0.0


def main():
    date_lookup = build_game_date_lookup()
    print(f"[aggregate] game_date lookup: {len(date_lookup)} entries")

    files = glob.glob(os.path.join(_NBA_CACHE, "boxscore_adv_*.json"))
    print(f"[aggregate] reading {len(files)} adv boxscore files")

    rows = []
    skipped_no_date = 0
    for path in files:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        gid = str(data.get("game_id", "")).zfill(10)
        gdate = date_lookup.get(gid)
        if not gdate:
            skipped_no_date += 1
            continue
        for p in data.get("players", []):
            pid = p.get("personid")
            if pid is None:
                continue
            mn = parse_minutes(p.get("minutes"))
            if mn < 1.0:
                continue  # DNP — adv stats meaningless
            row = {"player_id": int(pid), "game_id": gid, "game_date": gdate}
            for c in _ADV_COLS:
                v = p.get(c)
                if c == "minutes":
                    row[c] = mn
                else:
                    try:
                        row[c] = float(v) if v is not None else 0.0
                    except (TypeError, ValueError):
                        row[c] = 0.0
            rows.append(row)

    import pandas as pd
    df = pd.DataFrame(rows)
    print(f"[aggregate] {len(df)} player-game rows; skipped {skipped_no_date} games (no date)")
    print(f"[aggregate] unique players: {df['player_id'].nunique()}")
    print(f"[aggregate] date range: {df['game_date'].min()} -> {df['game_date'].max()}")
    df.to_parquet(_OUT_PATH, index=False)
    print(f"[aggregate] wrote {_OUT_PATH}")


if __name__ == "__main__":
    main()
