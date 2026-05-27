"""build_adv_stats_splits.py — Advanced-stat splits for prop feature pipeline.

Reads data/player_adv_stats.parquet (77,728 rows) and enriches it with
opponent-team-aware and in-season rolling features that haven't been tested
in prior loops:

  adv_usage_season_to_date   — shift(1).expanding().mean() of usagepercentage
  adv_ts_season_to_date      — shift(1).expanding().mean() of trueshootingpercentage
  adv_efg_season_to_date     — shift(1).expanding().mean() of effectivefieldgoalpercentage
  adv_usage_vs_opp_l3        — shift(1).rolling(3, min_periods=1) within same opp_team
  adv_ts_vs_opp_l3           — same for TS%
  adv_usage_z_in_season      — (last shift(1) value − cum_mean) / cum_std

Output: data/cache/adv_stats_splits.parquet
Key: (player_id, game_id, game_date)

Opponent-team join source:
  data/nba/boxscore_adv_*.json  → player's own team (teamtricode per personid+game_id)
  data/nba/season_games_*.json  → game_id → home_team + away_team
  opp_team = other team in the game (not the player's own team)

Leak-free: all rolling/expanding ops use shift(1) so the current-game value
is never visible to its own feature row.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_ADV_PATH = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")
_OUT_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_OUT_PATH = os.path.join(_OUT_DIR, "adv_stats_splits.parquet")

# Columns we compute splits for
_STATS = ("usagepercentage", "trueshootingpercentage", "effectivefieldgoalpercentage")
_MIN_PERIODS_EXPAND = 3   # min games before season-to-date mean is non-null
_OPP_ROLLING = 3          # rolling window for vs-opponent features


# ── Step 1: build game_id → (home_team, away_team) from season_games_*.json ──

def build_game_teams_lookup() -> Dict[str, Tuple[str, str]]:
    """Return {game_id: (home_team, away_team)} from cached season_games files."""
    lookup: Dict[str, Tuple[str, str]] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for g in rows:
            gid = str(g.get("game_id", "")).zfill(10)
            ht = str(g.get("home_team", ""))
            at = str(g.get("away_team", ""))
            if gid and ht and at:
                lookup[gid] = (ht, at)
    return lookup


# ── Step 2: build (game_id, player_id) → player_team from boxscore_adv_*.json ──

def build_player_team_lookup() -> Dict[Tuple[str, int], str]:
    """Return {(game_id, player_id): team_tricode} by scanning adv boxscore cache."""
    lookup: Dict[Tuple[str, int], str] = {}
    files = glob.glob(os.path.join(_NBA_CACHE, "boxscore_adv_*.json"))
    for path in files:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        gid = str(data.get("game_id", "")).zfill(10)
        for p in data.get("players", []):
            pid = p.get("personid")
            tricode = p.get("teamtricode", "")
            if pid is not None and tricode:
                lookup[(gid, int(pid))] = tricode
    return lookup


# ── Step 3: derive opp_team ──

def derive_opp_team(
    df: pd.DataFrame,
    game_teams: Dict[str, Tuple[str, str]],
    player_team: Dict[Tuple[str, int], str],
) -> pd.Series:
    """Vectorised opponent-team derivation.

    For each row: look up player's own team via (game_id, player_id),
    then the other team in the game (home or away) is the opponent.
    Returns a Series of str team tricode (NaN when lookup fails).
    """
    own = df.apply(
        lambda r: player_team.get((r["game_id"], r["player_id"]), None), axis=1
    )
    home = df["game_id"].map(lambda g: game_teams.get(g, (None, None))[0])
    away = df["game_id"].map(lambda g: game_teams.get(g, (None, None))[1])

    opp = pd.Series(index=df.index, dtype="object")
    is_home = own == home
    is_away = own == away
    opp[is_home] = away[is_home]
    opp[is_away] = home[is_away]
    # When own team can't be determined, leave as NaN
    return opp


# ── Step 4: season-to-date expanding features (shift(1), min_periods=3) ──

def _expanding_mean(series: pd.Series, min_periods: int) -> pd.Series:
    """Lag-1 expanding mean — leak-free."""
    return series.shift(1).expanding(min_periods=min_periods).mean()


# ── Step 5: z-score within season ──

def _expanding_z(series: pd.Series, min_periods: int = 5) -> pd.Series:
    """(shift(1) value − expanding_mean) / expanding_std, requires >=5 games."""
    s1 = series.shift(1)
    mu = s1.expanding(min_periods=min_periods).mean()
    sigma = s1.expanding(min_periods=min_periods).std()
    return (s1 - mu) / sigma.replace(0, np.nan)


# ── Step 6: rolling within same opponent (shift(1).rolling(window)) ──

def build_vs_opp_rolling(df: pd.DataFrame, stat: str, window: int) -> pd.Series:
    """Within each (player_id, opp_team) group: shift(1).rolling(window).mean().

    Requires ≥1 prior meeting (min_periods=1) — sparse by design; let consumers
    decide null handling.
    """
    out = pd.Series(index=df.index, dtype="float64")

    # Only process rows where opp_team is known
    mask = df["opp_team"].notna()
    sub = df[mask].copy()

    if sub.empty:
        return out

    sub = sub.sort_values(["player_id", "opp_team", "game_date"])
    rolled = (
        sub.groupby(["player_id", "opp_team"])[stat]
        .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
    )
    out[mask] = rolled.values
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(_OUT_DIR, exist_ok=True)

    # Load source
    print("[build_adv_stats_splits] loading player_adv_stats.parquet…")
    df = pd.read_parquet(_ADV_PATH)
    print(f"  source shape: {df.shape}")

    # Ensure game_date is a proper date string (already object/str)
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # ── Build opponent-team lookup ──────────────────────────────────────────
    print("[build_adv_stats_splits] building game_teams lookup from season_games_*.json…")
    game_teams = build_game_teams_lookup()
    print(f"  game_teams entries: {len(game_teams)}")

    print("[build_adv_stats_splits] building player_team lookup from boxscore_adv_*.json…")
    player_team = build_player_team_lookup()
    print(f"  player_team entries: {len(player_team)}")

    print("[build_adv_stats_splits] deriving opp_team…")
    df["opp_team"] = derive_opp_team(df, game_teams, player_team)
    n_opp_known = df["opp_team"].notna().sum()
    print(f"  opp_team known: {n_opp_known}/{len(df)} ({100*n_opp_known/len(df):.1f}%)")

    # ── Season-to-date expanding features ──────────────────────────────────
    print("[build_adv_stats_splits] computing season-to-date expanding means…")
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    for stat, feat in [
        ("usagepercentage",             "adv_usage_season_to_date"),
        ("trueshootingpercentage",       "adv_ts_season_to_date"),
        ("effectivefieldgoalpercentage", "adv_efg_season_to_date"),
    ]:
        df[feat] = df.groupby("player_id")[stat].transform(
            lambda s: _expanding_mean(s, _MIN_PERIODS_EXPAND)
        )

    # ── Z-score feature ────────────────────────────────────────────────────
    print("[build_adv_stats_splits] computing usage z-score…")
    df["adv_usage_z_in_season"] = df.groupby("player_id")["usagepercentage"].transform(
        lambda s: _expanding_z(s)
    )

    # ── Vs-opponent rolling features ───────────────────────────────────────
    print("[build_adv_stats_splits] computing vs-opponent rolling features…")
    df["adv_usage_vs_opp_l3"] = build_vs_opp_rolling(df, "usagepercentage", _OPP_ROLLING)
    df["adv_ts_vs_opp_l3"]    = build_vs_opp_rolling(df, "trueshootingpercentage", _OPP_ROLLING)

    # ── Select output columns ──────────────────────────────────────────────
    feature_cols = [
        "adv_usage_season_to_date",
        "adv_ts_season_to_date",
        "adv_efg_season_to_date",
        "adv_usage_vs_opp_l3",
        "adv_ts_vs_opp_l3",
        "adv_usage_z_in_season",
    ]
    out = df[["player_id", "game_id", "game_date", "opp_team"] + feature_cols].copy()

    # ── Write ──────────────────────────────────────────────────────────────
    out.to_parquet(_OUT_PATH, index=False)
    print(f"[build_adv_stats_splits] wrote {_OUT_PATH}")

    # ── Diagnostics ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Output shape: {out.shape}")
    print(f"\nNull rates per feature column:")
    for col in feature_cols:
        n_null = out[col].isnull().sum()
        pct = 100 * n_null / len(out)
        print(f"  {col:<35}  {n_null:>7,} / {len(out):,}  ({pct:.1f}% null)")

    # ── LeBron sample ─────────────────────────────────────────────────────
    lebron_id = 2544
    lbj = out[out["player_id"] == lebron_id].sort_values("game_date")
    if not lbj.empty:
        latest = lbj.iloc[-1]
        print(f"\nSample row — LeBron James (player_id=2544), latest game:")
        for k, v in latest.items():
            print(f"  {k}: {v}")
    else:
        print("\n(LeBron not found in dataset — check seasons loaded)")

    print(f"\n[build_adv_stats_splits] DONE — {len(out):,} rows")


if __name__ == "__main__":
    main()
