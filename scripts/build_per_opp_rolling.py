"""build_per_opp_rolling.py — per-opponent rolling-3 stat features (Iter-46).

For each (player_id, opp_team) pair, compute shift(1).rolling(3, min_periods=1)
means of PTS, REB, AST, FG3M, STL, BLK from the player's per-game gamelogs.
High null rate expected (most pairs have <3 prior meetings) — that's fine,
the model handles NaN.

Output: data/cache/per_opp_stat_rolling.parquet
Key: (player_id, game_date)  — ISO date string YYYY-MM-DD
Columns: per_opp_pts_l3, per_opp_reb_l3, per_opp_ast_l3,
         per_opp_fg3m_l3, per_opp_stl_l3, per_opp_blk_l3
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_OUT_PATH = os.path.join(_OUT_DIR, "per_opp_stat_rolling.parquet")

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk")
_BOX_COL = {"pts": "PTS", "reb": "REB", "ast": "AST",
            "fg3m": "FG3M", "stl": "STL", "blk": "BLK"}
_MIN_PLAYED = 1.0
_OPP_WINDOW = 3


def _parse_date(raw: str) -> Optional[datetime]:
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def _opponent_from_matchup(matchup: str) -> str:
    """Extract opponent team code from NBA gamelog MATCHUP string.

    'SAS vs. TOR'  -> 'TOR'  (player's team is HOME)
    'SAS @ PHX'    -> 'PHX'  (player's team is AWAY)
    """
    if " vs. " in matchup:
        return matchup.split(" vs. ")[1].strip()
    if " @ " in matchup:
        return matchup.split(" @ ")[1].strip()
    return ""


def _load_all_gamelogs(gamelog_dir: str) -> pd.DataFrame:
    """Load all gamelog_*.json files into a single DataFrame with typed columns."""
    records: List[dict] = []
    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            player_id = int(parts[1])
        except (IndexError, ValueError):
            continue
        try:
            games: List[dict] = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            try:
                minutes = float(g.get("MIN") or 0)
            except (TypeError, ValueError):
                minutes = 0.0
            if minutes < _MIN_PLAYED:
                continue
            gdate = _parse_date(g.get("GAME_DATE", ""))
            if gdate is None:
                continue
            matchup = str(g.get("MATCHUP", ""))
            opp = _opponent_from_matchup(matchup)
            if not opp:
                continue
            row: Dict[str, object] = {
                "player_id": player_id,
                "game_date": gdate.date().isoformat(),
                "opp_team": opp,
            }
            for stat, col in _BOX_COL.items():
                try:
                    row[stat] = float(g.get(col) or 0)
                except (TypeError, ValueError):
                    row[stat] = 0.0
            records.append(row)
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["player_id", "opp_team", "game_date"]).reset_index(drop=True)
    return df


def build_per_opp_rolling(df: pd.DataFrame) -> pd.DataFrame:
    """Compute shift(1).rolling(3, min_periods=1).mean() within (player_id, opp_team)."""
    result_cols: Dict[str, pd.Series] = {}
    grp = df.groupby(["player_id", "opp_team"], sort=False)
    for stat in _STATS:
        col_name = f"per_opp_{stat}_l3"
        result_cols[col_name] = grp[stat].transform(
            lambda s: s.shift(1).rolling(_OPP_WINDOW, min_periods=1).mean()
        )
    out = df[["player_id", "game_date"]].copy()
    for col_name, series in result_cols.items():
        out[col_name] = series
    out["game_date"] = out["game_date"].dt.strftime("%Y-%m-%d")
    out = out.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    return out


def main() -> None:
    os.makedirs(_OUT_DIR, exist_ok=True)

    print("[build_per_opp_rolling] loading gamelogs…")
    df = _load_all_gamelogs(_NBA_CACHE)
    print(f"  played rows: {len(df):,}  players: {df['player_id'].nunique():,}")
    print(f"  date range: {df['game_date'].min()} → {df['game_date'].max()}")

    print("[build_per_opp_rolling] computing per-opponent rolling-3 features…")
    out = build_per_opp_rolling(df)
    print(f"  output rows: {len(out):,}")

    feat_cols = [f"per_opp_{s}_l3" for s in _STATS]
    print("\nNull rates:")
    for col in feat_cols:
        n_null = out[col].isnull().sum()
        pct = 100.0 * n_null / max(len(out), 1)
        print(f"  {col:<25}  {n_null:>8,} / {len(out):,}  ({pct:.1f}% null)")

    out.to_parquet(_OUT_PATH, index=False)
    print(f"\n[build_per_opp_rolling] wrote {_OUT_PATH}  ({len(out):,} rows)")


if __name__ == "__main__":
    main()
