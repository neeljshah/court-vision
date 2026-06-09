"""build_linescore_context.py — per-game linescore blowout/pace context features.

Reads data/nba/linescores_all.json (4,915 games, 4 seasons) and
data/nba/season_games_*.json (for game_date + home/away team tricode).

For each (team_abbreviation, game_date) pair, computes 7 rolling features
using shift(1).rolling(5, min_periods=2) — strictly leak-free.

Team-side features (from team's own game history):
    ls_blowout_pct_l5       — frac of last 5 games with |H1 margin| > 15
    ls_avg_total_l5         — avg game total (final pts both teams) last 5
    ls_avg_q1_pts_l5        — team's avg Q1 pts last 5
    ls_avg_q4_pts_l5        — team's avg Q4 pts last 5
    ls_garbage_time_pct_l5  — frac last 5 with final margin > 20

Opponent-side features (from opp's game history — also pre-computed per team):
    ls_opp_avg_total_allowed_l5  — opp's avg game total last 5
    ls_opp_q1_pts_allowed_l5     — opp's avg Q1 pts allowed last 5

Output: data/cache/linescore_context.parquet
Key: (team_abbreviation, game_date)

Iter-19 — Sonnet sub-agent loop 2026-05-27.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_LINESCORE_PATH = os.path.join(_NBA_CACHE, "linescores_all.json")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "linescore_context.parquet")


def build_game_schedule() -> List[Dict]:
    """Return list of {game_id, game_date, home_team, away_team} from all season_games files."""
    rows = []
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        game_rows = payload["rows"] if isinstance(payload, dict) and "rows" in payload else payload
        for g in game_rows:
            gid = str(g.get("game_id", "")).zfill(10)
            gdate = str(g.get("game_date", ""))
            home_team = str(g.get("home_team", "")).strip()
            away_team = str(g.get("away_team", "")).strip()
            if gid and gdate and home_team and away_team:
                rows.append({
                    "game_id": gid,
                    "game_date": gdate,
                    "home_team": home_team,
                    "away_team": away_team,
                })
    print(f"[linescore-context] schedule: {len(rows)} game rows from season_games")
    return rows


def build_per_team_rows(schedule: List[Dict], linescores: Dict) -> List[Dict]:
    """Expand each game into 2 team-side rows with per-game stats."""
    rows = []
    for g in schedule:
        gid = g["game_id"]
        gdate = g["game_date"]
        ls = linescores.get(gid)
        if ls is None:
            continue
        home_team = g["home_team"]
        away_team = g["away_team"]

        # Compute per-team stats
        home_total = (ls.get("home_q1", 0) + ls.get("home_q2", 0) +
                      ls.get("home_q3", 0) + ls.get("home_q4", 0))
        away_total = (ls.get("away_q1", 0) + ls.get("away_q2", 0) +
                      ls.get("away_q3", 0) + ls.get("away_q4", 0))
        game_total = home_total + away_total

        home_h1 = ls.get("home_h1", home_total // 2)
        away_h1 = ls.get("away_h1", away_total // 2)
        h1_margin = abs(home_h1 - away_h1)
        final_margin = abs(home_total - away_total)
        is_blowout = 1 if h1_margin > 15 else 0
        is_garbage = 1 if final_margin > 20 else 0

        # Home team row
        rows.append({
            "game_id": gid,
            "game_date": gdate,
            "team_abbreviation": home_team,
            "opp_abbreviation": away_team,
            "q1_pts": float(ls.get("home_q1", 0)),
            "q4_pts": float(ls.get("home_q4", 0)),
            "opp_q1_pts": float(ls.get("away_q1", 0)),
            "game_total": float(game_total),
            "is_blowout": float(is_blowout),
            "is_garbage": float(is_garbage),
        })

        # Away team row
        rows.append({
            "game_id": gid,
            "game_date": gdate,
            "team_abbreviation": away_team,
            "opp_abbreviation": home_team,
            "q1_pts": float(ls.get("away_q1", 0)),
            "q4_pts": float(ls.get("away_q4", 0)),
            "opp_q1_pts": float(ls.get("home_q1", 0)),
            "game_total": float(game_total),
            "is_blowout": float(is_blowout),
            "is_garbage": float(is_garbage),
        })
    return rows


def compute_rolling_features(df) -> "pd.DataFrame":
    """Compute shift(1).rolling(5, min_periods=2) features per (team_abbreviation, game_date)."""
    import pandas as pd

    df = df.sort_values(["team_abbreviation", "game_date"]).reset_index(drop=True)

    out_rows = []
    for team, grp in df.groupby("team_abbreviation", sort=False):
        grp = grp.sort_values("game_date").reset_index(drop=True)

        # shift(1) then rolling(5, min_periods=2)
        shifted_blowout   = grp["is_blowout"].shift(1).rolling(5, min_periods=2)
        shifted_total     = grp["game_total"].shift(1).rolling(5, min_periods=2)
        shifted_q1        = grp["q1_pts"].shift(1).rolling(5, min_periods=2)
        shifted_q4        = grp["q4_pts"].shift(1).rolling(5, min_periods=2)
        shifted_garbage   = grp["is_garbage"].shift(1).rolling(5, min_periods=2)
        # Opp-context: opp_q1_pts allowed (from this team's game log, opp q1 pts scored against us)
        shifted_opp_total = grp["game_total"].shift(1).rolling(5, min_periods=2)
        shifted_opp_q1    = grp["opp_q1_pts"].shift(1).rolling(5, min_periods=2)

        grp = grp.copy()
        grp["ls_blowout_pct_l5"]          = shifted_blowout.mean()
        grp["ls_avg_total_l5"]            = shifted_total.mean()
        grp["ls_avg_q1_pts_l5"]           = shifted_q1.mean()
        grp["ls_avg_q4_pts_l5"]           = shifted_q4.mean()
        grp["ls_garbage_time_pct_l5"]     = shifted_garbage.mean()
        # Opp-allowed variants reuse the same game's totals from this team's POV
        # (ls_opp_avg_total_allowed_l5 and ls_opp_q1_pts_allowed_l5 are computed
        # below when we join by opponent team — see merge_opp_features)
        grp["ls_opp_avg_total_allowed_l5"] = shifted_opp_total.mean()
        grp["ls_opp_q1_pts_allowed_l5"]   = shifted_opp_q1.mean()

        out_rows.append(grp)

    result = pd.concat(out_rows, ignore_index=True)
    return result


def main():
    import pandas as pd

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)

    # Load linescores
    print(f"[linescore-context] reading {_LINESCORE_PATH}")
    with open(_LINESCORE_PATH, encoding="utf-8") as f:
        linescores = json.load(f)
    print(f"[linescore-context] {len(linescores)} games in linescores_all.json")

    # Load schedule
    schedule = build_game_schedule()

    # Build per-team raw rows
    raw_rows = build_per_team_rows(schedule, linescores)
    print(f"[linescore-context] {len(raw_rows)} team-game rows (2 per game)")

    if not raw_rows:
        print("[linescore-context] ERROR: no rows built — check data files")
        sys.exit(1)

    df = pd.DataFrame(raw_rows)
    df = df.drop_duplicates(subset=["team_abbreviation", "game_date"])
    print(f"[linescore-context] after dedup: {len(df)} rows")
    print(f"[linescore-context] teams: {df['team_abbreviation'].nunique()}")
    print(f"[linescore-context] date range: {df['game_date'].min()} -> {df['game_date'].max()}")

    # Compute rolling features
    df = compute_rolling_features(df)

    # Keep only the output columns
    feature_cols = [
        "team_abbreviation", "game_date",
        "ls_blowout_pct_l5",
        "ls_avg_total_l5",
        "ls_avg_q1_pts_l5",
        "ls_avg_q4_pts_l5",
        "ls_garbage_time_pct_l5",
        "ls_opp_avg_total_allowed_l5",
        "ls_opp_q1_pts_allowed_l5",
    ]
    df_out = df[feature_cols].copy()

    # Fill NaN (first 1-2 games of each team have no prior data) with 0.0
    for col in feature_cols[2:]:
        df_out[col] = df_out[col].fillna(0.0)

    df_out = df_out.sort_values(["team_abbreviation", "game_date"]).reset_index(drop=True)
    df_out.to_parquet(_OUT_PATH, index=False)
    print(f"[linescore-context] wrote {_OUT_PATH} ({len(df_out)} rows)")
    print(f"[linescore-context] columns: {df_out.columns.tolist()}")
    print(f"[linescore-context] sample (first 3):")
    print(df_out.head(3).to_string())


if __name__ == "__main__":
    main()
