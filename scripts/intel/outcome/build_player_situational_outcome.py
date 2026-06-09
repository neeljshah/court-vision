"""
build_player_situational_outcome.py
────────────────────────────────────
OUTCOME-IMPACT campaign: player HOME/ROAD + REST/B2B situational splits.

SOURCE : data/cache/cv_fix/leaguegamelog_regular_season.parquet
          2025-26 regular season, one row per player-game.
OUTPUT : data/cache/intel_outcome/player_situational_outcome.json

METHODOLOGY (leak-free, descriptive):
  - Exclude MIN==0 rows (DNPs – no contribution, distorts ±)
  - is_road  = '@' in MATCHUP (team abbreviation precedes '@')
  - rest_days = days since that player's own previous game
                (sorted per player by GAME_DATE; first game of season → NaN, excluded)
  - b2b      = rest_days == 1  (back-to-back: played consecutive calendar days)
  - rested   = rest_days >= 2  (2+ days rest)
  - Gates:
      • player overall: ≥30 played games (MIN>0)
      • each split bucket: ≥10 games
  - Metrics per bucket:
      • avg PLUS_MINUS  (team net while player is logged)
      • win_pct (WL=='W')
  - Confidence = 'high' (n≥25), 'medium' (n≥15), 'low' (n<15)
  - home_road_gap = road_pm - home_pm  (negative → road fade)
  - b2b_fade      = b2b_pm - rested_pm  (negative → fatigue fade)
  - road_warriors: top-8 by road_pm (must have n_road≥10)
  - road_faders:   bottom-8 by home_road_gap (most negative gap, n_road≥10)
  - b2b_faders:    bottom-8 by b2b_fade (most negative, n_b2b≥10)

NO FUTURE DATA LEAKAGE: all features derived from per-game logs using
only information available at game time; rest computed from chronological
sort within each player's own game history.
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
SRC_PARQ = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
OUT_DIR = ROOT / "data/cache/intel_outcome"
OUT_JSON = OUT_DIR / "player_situational_outcome.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── gates ────────────────────────────────────────────────────────────────────
MIN_TOTAL_GAMES = 30       # minimum played games for a player to be included
MIN_BUCKET_GAMES = 10      # minimum games in each split bucket

# ── helpers ──────────────────────────────────────────────────────────────────

def confidence_label(n: int) -> str:
    if n >= 25:
        return "high"
    if n >= 15:
        return "medium"
    return "low"


def safe_round(x, digits=2):
    """Round float; return None if NaN/None."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), digits)


def bucket_stats(sub: pd.DataFrame) -> dict:
    """Return {pm, win_pct, n, confidence} for a sub-DataFrame."""
    n = len(sub)
    pm = safe_round(sub["PLUS_MINUS"].mean())
    win_pct = safe_round((sub["WL"] == "W").mean())
    return {
        "pm": pm,
        "win_pct": win_pct,
        "n": n,
        "confidence": confidence_label(n),
    }


# ── load & clean ─────────────────────────────────────────────────────────────
print(f"Loading {SRC_PARQ} …")
df = pd.read_parquet(SRC_PARQ)
print(f"  Raw rows: {len(df):,}  players: {df['PLAYER_ID'].nunique()}")

# Exclude DNPs (no minutes played)
df = df[df["MIN"] > 0].copy()
print(f"  After MIN>0 filter: {len(df):,} rows")

# Parse date
df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])

# ── is_road flag ─────────────────────────────────────────────────────────────
# MATCHUP format: "GSW @ LAL" → road  |  "LAL vs. GSW" → home
df["is_road"] = df["MATCHUP"].str.contains("@")

# ── rest days (per player, chronological) ─────────────────────────────────────
df = df.sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True)
df["prev_date"] = df.groupby("PLAYER_ID")["GAME_DATE"].shift(1)
df["rest_days"] = (df["GAME_DATE"] - df["prev_date"]).dt.days
# First game of season → NaN rest_days (excluded from rest/b2b splits)

df["is_b2b"] = df["rest_days"] == 1   # consecutive calendar days = true B2B
df["is_rested"] = df["rest_days"] >= 2  # 2+ days rest

# ── per-player split computation ──────────────────────────────────────────────
print("Computing per-player situational splits …")

players_out = {}

for pid, grp in df.groupby("PLAYER_ID"):
    n_total = len(grp)
    if n_total < MIN_TOTAL_GAMES:
        continue

    # Most recent team and name
    latest = grp.sort_values("GAME_DATE").iloc[-1]
    name = latest["PLAYER_NAME"]
    team = latest["TEAM_ABBREVIATION"]

    home_grp = grp[~grp["is_road"]]
    road_grp = grp[grp["is_road"]]
    b2b_grp = grp[grp["is_b2b"]]
    rested_grp = grp[grp["is_rested"]]

    n_home = len(home_grp)
    n_road = len(road_grp)
    n_b2b = len(b2b_grp)
    n_rested = len(rested_grp)

    # Both home and road must meet bucket gate for H/R entry
    hr_valid = (n_home >= MIN_BUCKET_GAMES) and (n_road >= MIN_BUCKET_GAMES)
    # Both rested and b2b must meet bucket gate for rest entry
    rest_valid = (n_rested >= MIN_BUCKET_GAMES) and (n_b2b >= MIN_BUCKET_GAMES)

    # Compute raw metrics regardless of gate (store None if below gate)
    home_pm = safe_round(home_grp["PLUS_MINUS"].mean()) if n_home > 0 else None
    road_pm = safe_round(road_grp["PLUS_MINUS"].mean()) if n_road > 0 else None
    home_win = safe_round((home_grp["WL"] == "W").mean()) if n_home > 0 else None
    road_win = safe_round((road_grp["WL"] == "W").mean()) if n_road > 0 else None
    rested_pm = safe_round(rested_grp["PLUS_MINUS"].mean()) if n_rested > 0 else None
    b2b_pm = safe_round(b2b_grp["PLUS_MINUS"].mean()) if n_b2b > 0 else None

    home_road_gap = safe_round(road_pm - home_pm) if (road_pm is not None and home_pm is not None) else None
    b2b_fade = safe_round(b2b_pm - rested_pm) if (b2b_pm is not None and rested_pm is not None) else None

    # Overall confidence anchors on minimum bucket n for each split type
    hr_conf = confidence_label(min(n_home, n_road)) if hr_valid else "insufficient"
    rest_conf = confidence_label(min(n_rested, n_b2b)) if rest_valid else "insufficient"

    players_out[str(pid)] = {
        "name": name,
        "team": team,
        "n_games": n_total,
        # Home/road
        "home_pm": home_pm if hr_valid else None,
        "road_pm": road_pm if hr_valid else None,
        "home_road_gap": home_road_gap if hr_valid else None,
        "home_winpct": home_win if hr_valid else None,
        "road_winpct": road_win if hr_valid else None,
        "n_home": n_home,
        "n_road": n_road,
        "hr_confidence": hr_conf,
        # Rest/B2B
        "rested_pm": rested_pm if rest_valid else None,
        "b2b_pm": b2b_pm if rest_valid else None,
        "b2b_fade": b2b_fade if rest_valid else None,
        "n_rested": n_rested,
        "n_b2b": n_b2b,
        "rest_confidence": rest_conf,
    }

print(f"  Players included (≥{MIN_TOTAL_GAMES} games): {len(players_out)}")

# ── leaderboards ─────────────────────────────────────────────────────────────

def make_leaderboard(players_out, key, ascending, gate_key, gate_val=MIN_BUCKET_GAMES, top_n=8):
    """Return top_n player entries sorted by key (ascending or descending)."""
    eligible = [
        (pid, rec) for pid, rec in players_out.items()
        if rec.get(key) is not None and rec.get(gate_key, 0) >= gate_val
    ]
    eligible.sort(key=lambda x: x[1][key], reverse=not ascending)
    result = []
    for pid, rec in eligible[:top_n]:
        result.append({
            "player_id": pid,
            "name": rec["name"],
            "team": rec["team"],
            key: rec[key],
            "n": rec.get(gate_key, "?"),
        })
    return result

# road_warriors: highest road_pm (n_road >= 10)
road_warriors = make_leaderboard(players_out, "road_pm", ascending=False, gate_key="n_road", top_n=8)

# road_faders: most negative home_road_gap (road_pm - home_pm, lowest = biggest fade)
road_faders = make_leaderboard(players_out, "home_road_gap", ascending=True, gate_key="n_road", top_n=8)

# b2b_faders: most negative b2b_fade (b2b_pm - rested_pm, lowest = biggest fatigue drop)
b2b_faders = make_leaderboard(players_out, "b2b_fade", ascending=True, gate_key="n_b2b", top_n=8)

# ── assemble output ───────────────────────────────────────────────────────────
# Coverage stats
n_hr_valid = sum(1 for r in players_out.values() if r["hr_confidence"] != "insufficient")
n_rest_valid = sum(1 for r in players_out.values() if r["rest_confidence"] != "insufficient")

output = {
    "meta": {
        "season": "2025-26",
        "source": "leaguegamelog_regular_season.parquet (NBA official box scores)",
        "units": "PLUS_MINUS = integer team net pts while player logged; win_pct = team win rate",
        "gates": {
            "min_total_games": MIN_TOTAL_GAMES,
            "min_bucket_games": MIN_BUCKET_GAMES,
        },
        "coverage": {
            "total_players_included": len(players_out),
            "players_with_valid_home_road_splits": n_hr_valid,
            "players_with_valid_rest_b2b_splits": n_rest_valid,
        },
        "caveats": [
            "PLUS_MINUS is team net — reflects teammates, opponent, game flow, NOT individual defense/scoring in isolation.",
            "Small n buckets (n_b2b especially) are noisy; treat confidence='low' as directional signal only.",
            "Rest days computed from player's own game log — not opponent rest, which is omitted here.",
            "DNPs (MIN=0) excluded; first game of season excluded from rest splits (no prior date). B2B = rest_days==1 (consecutive calendar nights); rested = rest_days>=2.",
            "Season = 2025-26 regular season only (single season; no multi-year smoothing).",
            "home_road_gap = road_pm minus home_pm; negative = player's team performs worse on road with him.",
            "b2b_fade = b2b_pm minus rested_pm; negative = fatigue effect on team net.",
            "SCOUTING ONLY: do not fold into model features without OOS validation.",
        ],
        "field_definitions": {
            "home_pm": "avg team PLUS_MINUS in home games",
            "road_pm": "avg team PLUS_MINUS in road games",
            "home_road_gap": "road_pm - home_pm (negative = road underperformance)",
            "home_winpct": "team win rate in home games",
            "road_winpct": "team win rate in road games",
            "rested_pm": "avg PLUS_MINUS on 2+ days rest",
            "b2b_pm": "avg PLUS_MINUS on 1 day rest (back-to-back: consecutive calendar nights)",
            "b2b_fade": "b2b_pm - rested_pm (negative = fatigue drag)",
            "hr_confidence": "based on min(n_home, n_road): high>=25, medium>=15, low>=10",
            "rest_confidence": "based on min(n_rested, n_b2b): high>=25, medium>=15, low>=10",
        },
    },
    "players": players_out,
    "road_warriors": road_warriors,
    "road_faders": road_faders,
    "b2b_faders": b2b_faders,
}

# ── write ─────────────────────────────────────────────────────────────────────
with open(OUT_JSON, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nWrote {OUT_JSON}")
print(f"  Players: {len(players_out)}")
print(f"  H/R valid splits: {n_hr_valid}")
print(f"  Rest/B2B valid splits: {n_rest_valid}")

# ── print leaderboards to stdout ──────────────────────────────────────────────
print("\n=== TOP 8 ROAD WARRIORS (road_pm) ===")
for i, r in enumerate(road_warriors, 1):
    print(f"  {i}. {r['name']:<28} {r['team']}  road_pm={r['road_pm']:+.1f}  n_road={r['n']}")

print("\n=== TOP 8 ROAD FADERS (home_road_gap, most negative) ===")
for i, r in enumerate(road_faders, 1):
    print(f"  {i}. {r['name']:<28} {r['team']}  gap={r['home_road_gap']:+.1f}  n_road={r['n']}")

print("\n=== TOP 8 B2B FADERS (b2b_fade, most negative) ===")
for i, r in enumerate(b2b_faders, 1):
    print(f"  {i}. {r['name']:<28} {r['team']}  b2b_fade={r['b2b_fade']:+.1f}  n_b2b={r['n']}")
