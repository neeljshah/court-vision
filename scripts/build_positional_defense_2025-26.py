"""Build 2025-26 TEAM and PLAYER positional-defense parquets from stats.nba.com.

Endpoints:
  - LeagueDashPtTeamDefend  -> data/team_positional_defense_2025-26.parquet (30 rows)
  - LeagueDashPtDefend       -> data/player_positional_defense_2025-26.parquet

Gentle on the API: 1.0s sleep between calls, exponential-ish backoff (5s) on
HTTP 429/timeout, up to 3 retries per call.
"""
import sys
import time
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data import nba_api_headers_patch  # noqa: F401,E402  (must import before NBA-API calls)
from nba_api.stats.endpoints import LeagueDashPtTeamDefend, LeagueDashPtDefend
from nba_api.stats.static import teams as static_teams

ROOT = Path(__file__).resolve().parent.parent
SEASON = "2025-26"
SEASON_TYPE = "Regular Season"
PER_MODE = "PerGame"

# Category label -> column prefix
TEAM_CATEGORIES = {
    "Overall": "overall",
    "3 Pointers": "perim_3pt",
    "2 Pointers": "two_pt",
    "Less Than 6Ft": "rim_lt6",
    "Less Than 10Ft": "paint_lt10",
    "Greater Than 15Ft": "mid_gt15",
}

PLAYER_CATEGORIES = {
    "Overall": "overall",
    "Less Than 6Ft": "rim_lt6",
    "3 Pointers": "perim_3pt",
}

# Each defense category emits category-specific shooting column names. Map the
# source columns -> canonical suffixes so every category yields the same schema:
#   <prefix>_freq, _d_fgm, _d_fga, _d_fg_pct, _normal_fg_pct, _pct_plusminus
# Keyed by defense_category label.
CATEGORY_COLMAP = {
    "Overall": {
        "FREQ": "freq", "D_FGM": "d_fgm", "D_FGA": "d_fga",
        "D_FG_PCT": "d_fg_pct", "NORMAL_FG_PCT": "normal_fg_pct", "PCT_PLUSMINUS": "pct_plusminus",
    },
    "3 Pointers": {
        "FREQ": "freq", "FG3M": "d_fgm", "FG3A": "d_fga",
        "FG3_PCT": "d_fg_pct", "NS_FG3_PCT": "normal_fg_pct", "PLUSMINUS": "pct_plusminus",
    },
    "2 Pointers": {
        "FREQ": "freq", "FG2M": "d_fgm", "FG2A": "d_fga",
        "FG2_PCT": "d_fg_pct", "NS_FG2_PCT": "normal_fg_pct", "PLUSMINUS": "pct_plusminus",
    },
    "Less Than 6Ft": {
        "FREQ": "freq", "FGM_LT_06": "d_fgm", "FGA_LT_06": "d_fga",
        "LT_06_PCT": "d_fg_pct", "NS_LT_06_PCT": "normal_fg_pct", "PLUSMINUS": "pct_plusminus",
    },
    "Less Than 10Ft": {
        "FREQ": "freq", "FGM_LT_10": "d_fgm", "FGA_LT_10": "d_fga",
        "LT_10_PCT": "d_fg_pct", "NS_LT_10_PCT": "normal_fg_pct", "PLUSMINUS": "pct_plusminus",
    },
    "Greater Than 15Ft": {
        "FREQ": "freq", "FGM_GT_15": "d_fgm", "FGA_GT_15": "d_fga",
        "GT_15_PCT": "d_fg_pct", "NS_GT_15_PCT": "normal_fg_pct", "PLUSMINUS": "pct_plusminus",
    },
}


def _call(endpoint_cls, defense_category, retries=3):
    """Call an endpoint with gentle backoff. Returns the first DataFrame."""
    last_err = None
    for attempt in range(retries):
        try:
            ep = endpoint_cls(
                defense_category=defense_category,
                per_mode_simple=PER_MODE,
                season=SEASON,
                season_type_all_star=SEASON_TYPE,
                timeout=60,
            )
            df = ep.get_data_frames()[0]
            time.sleep(1.0)
            return df
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e)
            print(f"  [warn] {defense_category} attempt {attempt+1}/{retries} failed: {msg[:120]}")
            time.sleep(5.0)
    raise RuntimeError(f"Failed {endpoint_cls.__name__} / {defense_category}: {last_err}")


def _suffix_cols(df, prefix, category):
    """Extract category metric cols, rename to <prefix>_<canonical>."""
    colmap = CATEGORY_COLMAP[category]
    keep = [c for c in colmap if c in df.columns]
    out = df[keep].copy()
    out.columns = [f"{prefix}_{colmap[c]}" for c in keep]
    return out


def build_team():
    team_map = {t["id"]: t["abbreviation"] for t in static_teams.get_teams()}
    base = None  # team_id, team_name index frame
    cat_frames = []
    for cat, prefix in TEAM_CATEGORIES.items():
        print(f"[TEAM] {cat} -> {prefix}")
        df = _call(LeagueDashPtTeamDefend, cat)
        # id columns (TEAM_ABBREVIATION dropped; we map team_id -> tricode below)
        id_cols = [c for c in ["TEAM_ID", "TEAM_NAME"] if c in df.columns]
        if base is None:
            base = df[id_cols].copy()
        metrics = _suffix_cols(df, prefix, cat)
        metrics.insert(0, "TEAM_ID", df["TEAM_ID"].values)
        cat_frames.append(metrics)

    merged = base
    for cf in cat_frames:
        merged = merged.merge(cf, on="TEAM_ID", how="left")

    merged.rename(columns={"TEAM_ID": "team_id", "TEAM_NAME": "team_name"}, inplace=True)
    merged["team_abbreviation"] = merged["team_id"].map(team_map)
    # order id cols first
    front = [c for c in ["team_id", "team_abbreviation", "team_name"] if c in merged.columns]
    rest = [c for c in merged.columns if c not in front]
    merged = merged[front + rest]
    return merged


def build_player():
    ID_COL = "CLOSE_DEF_PERSON_ID"
    cat_frames = []
    base = None
    for cat, prefix in PLAYER_CATEGORIES.items():
        print(f"[PLAYER] {cat} -> {prefix}")
        df = _call(LeagueDashPtDefend, cat)
        id_cols = [c for c in [ID_COL, "PLAYER_NAME", "PLAYER_LAST_TEAM_ABBREVIATION", "PLAYER_POSITION", "GP"] if c in df.columns]
        if base is None:
            base = df[id_cols].copy()
        metrics = _suffix_cols(df, prefix, cat)
        metrics.insert(0, ID_COL, df[ID_COL].values)
        cat_frames.append(metrics)

    merged = base
    for cf in cat_frames:
        merged = merged.merge(cf, on=ID_COL, how="left")

    merged.rename(
        columns={
            ID_COL: "player_id",
            "PLAYER_NAME": "player_name",
            "PLAYER_LAST_TEAM_ABBREVIATION": "team_abbreviation",
            "PLAYER_POSITION": "player_position",
            "GP": "gp",
        },
        inplace=True,
    )
    front = [c for c in ["player_id", "player_name", "team_abbreviation"] if c in merged.columns]
    rest = [c for c in merged.columns if c not in front]
    merged = merged[front + rest]
    return merged


def main():
    team = build_team()
    team_path = ROOT / "data" / "team_positional_defense_2025-26.parquet"
    team.to_parquet(team_path, index=False)

    player = build_player()
    player_path = ROOT / "data" / "player_positional_defense_2025-26.parquet"
    player.to_parquet(player_path, index=False)

    # ---------- VERIFY ----------
    print("\n" + "=" * 70)
    print("TEAM parquet:", team_path)
    print("  rows:", len(team))
    print("  columns:", team.columns.tolist())
    if "rim_lt6_d_fg_pct" in team.columns:
        top = team.sort_values("rim_lt6_d_fg_pct").head(5)
        print("  Top-5 rim protection (lowest rim_lt6_d_fg_pct):")
        cols = [c for c in ["team_abbreviation", "rim_lt6_d_fg_pct", "rim_lt6_fga", "rim_lt6_pct_plusminus"] if c in team.columns]
        print(top[cols].to_string(index=False))

    print("\n" + "=" * 70)
    print("PLAYER parquet:", player_path)
    print("  rows:", len(player))
    print("  distinct players:", player["player_id"].nunique())
    print("  columns:", player.columns.tolist())
    if "rim_lt6_d_fg_pct" in player.columns and "rim_lt6_d_fga" in player.columns:
        elig = player[player["rim_lt6_d_fga"] >= 4]
        top = elig.sort_values("rim_lt6_d_fg_pct").head(5)
        print("  Top-5 rim protectors (rim_lt6_d_fga>=4, lowest rim_lt6_d_fg_pct):")
        cols = [c for c in ["player_name", "team_abbreviation", "rim_lt6_d_fga", "rim_lt6_d_fg_pct", "rim_lt6_pct_plusminus"] if c in player.columns]
        print(top[cols].to_string(index=False))

    return team, player


if __name__ == "__main__":
    main()
