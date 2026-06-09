"""
build_team_schedule_spots.py
─────────────────────────────────────────────────────────────────────────────
Derives schedule-stress / rest-day effects on GAME OUTCOMES for the 2025-26
NBA regular season.

SOURCES
    data/nba/season_games_2025-26.json
        ­— per-game rows with home/away rest_days, back_to_back flags, home_win,
          home_pace, away_pace (rolling pre-game averages).  N=1,231 completed
          regular-season games (game_id prefix 0022500xxx).
    data/cache/cv_fix/leaguegamelog_regular_season.parquet
        — player-level box scores; aggregated to game level to obtain ACTUAL
          home_pts, away_pts, margin, and total.  Same 1,230 regular-season
          games (player log covers 0022500xxx).

LEAK SAFETY
    All rest / back-to-back flags are computed from *prior* completed game
    dates only — no future-game information.  The leaguegamelog covers only
    regular-season games through 2026-04-12 (no playoff leakage).  Season_games
    playoff rows (N=6, prefix 0042500xxx) are excluded from all aggregations.

OUTPUT
    data/cache/intel_outcome/team_schedule_spots.json

SCHEMA (all units documented inline)
    league:
        home_edge_winpct   float  — fraction of games won by home team [0,1]
        home_edge_margin   float  — mean(home_pts - away_pts) in points
        n_games            int    — total completed regular-season games
        baseline_total     float  — mean(home_pts + away_pts) for all games
        baseline_pace      float  — mean(home_pace + away_pace)/2 for all games

        b2b:       stats for "at least one team on back-to-back" (rest=1 day)
        b2b_home:  stats for home team specifically on B2B
        b2b_away:  stats for away team specifically on B2B
        rest1:     home team on exactly 1 rest day (≡ b2b_home, kept for parity)
        rest2:     home team on exactly 2 rest days (most common)
        rest2plus: home team on 2+ rest days (rested baseline)
        three_in_four:  a team playing its 3rd game in a 4-day window
        four_in_six:    a team playing its 4th game in a 6-day window

        Each scenario dict:
            winpct       float  — win% for the team in that spot [0,1]
                                  (home win% for home-team scenarios;
                                   away win% = 1-winpct for away scenarios)
            margin       float  — mean signed margin from team perspective (pts)
            margin_delta float  — deviation from league baseline margin (+home)
            total        float  — mean game total (pts both teams)
            total_delta  float  — deviation from league baseline total
            pace         float  — mean pre-game pace proxy (rolling avg)
            pace_delta   float  — deviation from league baseline pace
            n            int    — number of team-game instances

    teams:
        "<TRI>":
            b2b_winpct   float  — team win% on back-to-back nights
            b2b_margin   float  — mean point margin (positive = win) on B2B
            b2b_total    float  — mean game total on B2B
            rested_winpct float — win% when NOT on B2B (rest >= 2 days)
            rested_margin float — mean margin when rested
            n_b2b        int    — team-game instances on B2B this season
            n_rested     int    — team-game instances rested
            b2b_margin_delta float — B2B margin minus rested margin (fade signal)
            notes        str    — interpretation label

    meta:
        generated_at str
        source_games int
        season       str
        leak_safe    bool
        caveats      list[str]
"""

import json
import math
import pathlib
from datetime import datetime, timezone

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = pathlib.Path("C:/Users/neelj/nba-ai-system")
SEASON_GAMES_PATH = ROOT / "data/nba/season_games_2025-26.json"
GAMELOG_PATH = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
OUT_DIR = ROOT / "data/cache/intel_outcome"
OUT_PATH = OUT_DIR / "team_schedule_spots.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _round(x, n=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), n)


def _scenario_stats(sub_games, *, team_wins_col, margin_col, total_col, pace_col):
    """Return dict of stats for a subset of games."""
    n = len(sub_games)
    if n == 0:
        return {"winpct": None, "margin": None, "total": None, "pace": None, "n": 0}
    return {
        "winpct":  _round(sub_games[team_wins_col].mean()),
        "margin":  _round(sub_games[margin_col].mean()),
        "total":   _round(sub_games[total_col].mean()),
        "pace":    _round(sub_games[pace_col].mean()),
        "n":       n,
    }


def _add_deltas(stats, baseline_margin, baseline_total, baseline_pace):
    """Mutate stats dict in-place to add _delta fields."""
    for field, baseline in [
        ("margin", baseline_margin),
        ("total", baseline_total),
        ("pace", baseline_pace),
    ]:
        val = stats.get(field)
        if val is not None:
            stats[f"{field}_delta"] = _round(val - baseline)
        else:
            stats[f"{field}_delta"] = None
    return stats


# ── 1. Load season_games — completed regular-season games only ────────────────
print("Loading season_games_2025-26.json ...")
raw = json.loads(SEASON_GAMES_PATH.read_text(encoding="utf-8"))
df_sg = pd.DataFrame(raw["rows"])

# Keep only completed regular-season games (home_win not null; prefix 0022)
df_sg = df_sg[df_sg["game_id"].str.startswith("0022")].copy()
df_sg = df_sg.dropna(subset=["home_win"])
print(f"  Completed reg-season games: {len(df_sg)}")

# Cast types
df_sg["game_date"] = pd.to_datetime(df_sg["game_date"])
for col in ["home_win", "home_rest_days", "away_rest_days",
            "home_back_to_back", "away_back_to_back",
            "home_pace", "away_pace"]:
    df_sg[col] = pd.to_numeric(df_sg[col])


# ── 2. Build actual game scores from leaguegamelog ───────────────────────────
print("Loading leaguegamelog_regular_season.parquet ...")
dflog = pd.read_parquet(GAMELOG_PATH)

# Aggregate player rows → game-team PTS
dflog["is_home"] = dflog["MATCHUP"].str.contains(r" vs\.")
game_team = (
    dflog.groupby(["GAME_ID", "TEAM_ABBREVIATION", "WL"])
    .agg(PTS=("PTS", "sum"), is_home=("is_home", "first"))
    .reset_index()
)

home_df = game_team[game_team["is_home"]].rename(
    columns={"TEAM_ABBREVIATION": "home_team", "PTS": "home_pts"}
)[["GAME_ID", "home_team", "home_pts", "WL"]]

away_df = game_team[~game_team["is_home"]].rename(
    columns={"TEAM_ABBREVIATION": "away_team", "PTS": "away_pts"}
)[["GAME_ID", "away_team", "away_pts"]]

scores = home_df.merge(away_df, on="GAME_ID")
scores["margin"] = scores["home_pts"] - scores["away_pts"]
scores["total"] = scores["home_pts"] + scores["away_pts"]
scores["home_win_actual"] = (scores["WL"] == "W").astype(int)
print(f"  Gamelog game-level rows: {len(scores)}")


# ── 3. Master join: season_games (rest flags) + actual scores ─────────────────
df = df_sg.merge(
    scores[["GAME_ID", "home_pts", "away_pts", "margin", "total"]],
    left_on="game_id",
    right_on="GAME_ID",
    how="left",
)
print(f"  After join: {len(df)} rows, score coverage: {df['total'].notna().sum()}")

# game pace proxy: mean of home/away rolling pace averages
df["game_pace"] = (df["home_pace"] + df["away_pace"]) / 2


# ── 4. Per-team schedule reconstruction for 3-in-4 and 4-in-6 ────────────────
print("Building per-team schedule spots ...")

# Build long table: one row per team-game
home_long = df[["game_id", "game_date", "home_team", "home_win", "margin",
                "total", "game_pace", "home_back_to_back", "home_rest_days"]].copy()
home_long.columns = ["game_id", "game_date", "team", "win", "margin",
                     "total", "game_pace", "b2b", "rest_days"]

away_long = df[["game_id", "game_date", "away_team", "home_win", "margin",
                "total", "game_pace", "away_back_to_back", "away_rest_days"]].copy()
# Away team: win = 1 - home_win; margin from away's perspective = -margin
away_long["away_win"] = 1 - df["home_win"]
away_long["away_margin"] = -df["margin"]
away_long = away_long.drop(columns=["home_win", "margin"])
away_long = away_long.rename(columns={
    "away_team": "team",
    "away_win": "win",
    "away_margin": "margin",
    "away_back_to_back": "b2b",
    "away_rest_days": "rest_days",
})

team_long = pd.concat([home_long, away_long], ignore_index=True)
team_long = team_long.sort_values(["team", "game_date"]).reset_index(drop=True)

# Add 3-in-4 and 4-in-6 flags per team
team_long["prev_date"] = team_long.groupby("team")["game_date"].shift(1)
team_long["prev2_date"] = team_long.groupby("team")["game_date"].shift(2)
team_long["prev3_date"] = team_long.groupby("team")["game_date"].shift(3)

team_long["days_since_2ago"] = (team_long["game_date"] - team_long["prev2_date"]).dt.days
team_long["days_since_3ago"] = (team_long["game_date"] - team_long["prev3_date"]).dt.days

# 3-in-4: this game + 2 prior = 3 games; first game to last ≤ 3 days
team_long["is_3in4"] = team_long["days_since_2ago"].le(3) & team_long["days_since_2ago"].notna()
# 4-in-6: this game + 3 prior = 4 games; first game to last ≤ 6 days
team_long["is_4in6"] = team_long["days_since_3ago"].le(6) & team_long["days_since_3ago"].notna()

print(f"  3-in-4 team-game instances: {team_long['is_3in4'].sum()}")
print(f"  4-in-6 team-game instances: {team_long['is_4in6'].sum()}")


# ── 5. League-level aggregations ─────────────────────────────────────────────
print("Computing league-level schedule spot effects ...")

# Baseline: all completed regular-season games
n_games = len(df)
baseline_home_win = df["home_win"].mean()
baseline_margin = df["margin"].mean()      # from home team perspective
baseline_total = df["total"].mean()
baseline_pace = df["game_pace"].mean()

print(f"  n_games={n_games}, home_win%={baseline_home_win:.3f}, "
      f"margin={baseline_margin:.2f}, total={baseline_total:.2f}, pace={baseline_pace:.2f}")


def _league_home_stats(mask, baseline_margin, baseline_total, baseline_pace):
    """Stats for home team in selected games."""
    sub = df[mask]
    s = _scenario_stats(sub,
                        team_wins_col="home_win",
                        margin_col="margin",
                        total_col="total",
                        pace_col="game_pace")
    _add_deltas(s, baseline_margin, baseline_total, baseline_pace)
    return s


# B2B: at least one team on B2B (any_b2b game)
mask_any_b2b = (df["home_back_to_back"] == 1) | (df["away_back_to_back"] == 1)

# B2B for specifically the home team
mask_h_b2b = df["home_back_to_back"] == 1
mask_a_b2b = df["away_back_to_back"] == 1

# Rest buckets for home team
mask_h_rest1 = df["home_rest_days"] == 1  # identical to h_b2b
mask_h_rest2 = df["home_rest_days"] == 2
mask_h_rest2plus = df["home_rest_days"] >= 2


def _league_team_long_stats(mask, baseline_margin, baseline_total, baseline_pace):
    """Stats from the team_long perspective (team-game view)."""
    sub = team_long[mask]
    s = _scenario_stats(sub,
                        team_wins_col="win",
                        margin_col="margin",
                        total_col="total",
                        pace_col="game_pace")
    _add_deltas(s, baseline_margin / 2, baseline_total, baseline_pace)
    # Note: baseline_margin / 2 is not meaningful here since margin sign differs home/away
    # Re-compute delta vs 0 for margin (team-perspective)
    s["margin_delta"] = _round(s["margin"]) if s["margin"] is not None else None
    return s


# 3-in-4 and 4-in-6 (team_long perspective)
mask_3in4 = team_long["is_3in4"]
mask_4in6 = team_long["is_4in6"]

# Rested: not on B2B (rest >= 2 days) from team perspective
mask_rested = team_long["b2b"] == 0
mask_tl_b2b = team_long["b2b"] == 1

# Team-long stats: win%, margin (from team's POV), total, pace
def _tl_stats(mask):
    sub = team_long[mask]
    n = len(sub)
    if n == 0:
        return {"winpct": None, "margin": None, "total": None, "pace": None, "n": 0,
                "margin_delta": None, "total_delta": None, "pace_delta": None}
    winpct = _round(sub["win"].mean())
    margin = _round(sub["margin"].mean())
    total = _round(sub["total"].mean())
    pace = _round(sub["game_pace"].mean())
    margin_delta = _round(margin) if margin is not None else None  # vs 0 baseline team perspective
    total_delta = _round(total - baseline_total) if total is not None else None
    pace_delta = _round(pace - baseline_pace) if pace is not None else None
    return {"winpct": winpct, "margin": margin, "total": total, "pace": pace, "n": n,
            "margin_delta": margin_delta, "total_delta": total_delta, "pace_delta": pace_delta}


tl_b2b_stats = _tl_stats(mask_tl_b2b)
tl_rested_stats = _tl_stats(mask_rested)
tl_3in4_stats = _tl_stats(mask_3in4)
tl_4in6_stats = _tl_stats(mask_4in6)

# Home-specific B2B: from game-level (home_win perspective)
h_b2b = _league_home_stats(mask_h_b2b, baseline_margin, baseline_total, baseline_pace)
h_rest1 = _league_home_stats(mask_h_rest1, baseline_margin, baseline_total, baseline_pace)
h_rest2 = _league_home_stats(mask_h_rest2, baseline_margin, baseline_total, baseline_pace)
h_rest2plus = _league_home_stats(mask_h_rest2plus, baseline_margin, baseline_total, baseline_pace)

# Away B2B: home_win perspective — if away is on B2B, does home win more?
a_b2b = _league_home_stats(mask_a_b2b, baseline_margin, baseline_total, baseline_pace)

# Any B2B game totals (both perspectives)
any_b2b = _league_home_stats(mask_any_b2b, baseline_margin, baseline_total, baseline_pace)


# ── 6. Per-team splits ────────────────────────────────────────────────────────
print("Computing per-team B2B splits ...")

TEAMS = sorted(team_long["team"].unique())
teams_out = {}

for tri in TEAMS:
    t = team_long[team_long["team"] == tri]
    b2b_t = t[t["b2b"] == 1]
    rest_t = t[t["b2b"] == 0]

    n_b2b = len(b2b_t)
    n_rest = len(rest_t)

    b2b_win = _round(b2b_t["win"].mean()) if n_b2b > 0 else None
    b2b_margin = _round(b2b_t["margin"].mean()) if n_b2b > 0 else None
    b2b_total = _round(b2b_t["total"].mean()) if n_b2b > 0 else None
    rested_win = _round(rest_t["win"].mean()) if n_rest > 0 else None
    rested_margin = _round(rest_t["margin"].mean()) if n_rest > 0 else None

    margin_delta = None
    if b2b_margin is not None and rested_margin is not None:
        margin_delta = _round(b2b_margin - rested_margin)

    # Qualitative label
    if n_b2b < 5:
        notes = "tiny_sample"
    elif margin_delta is not None and margin_delta <= -8:
        notes = "fades_hard_b2b"
    elif margin_delta is not None and margin_delta <= -4:
        notes = "fades_b2b"
    elif margin_delta is not None and margin_delta >= 4:
        notes = "holds_b2b"
    else:
        notes = "neutral"

    teams_out[tri] = {
        "b2b_winpct":      b2b_win,
        "b2b_margin":      b2b_margin,
        "b2b_total":       b2b_total,
        "rested_winpct":   rested_win,
        "rested_margin":   rested_margin,
        "b2b_margin_delta": margin_delta,
        "n_b2b":           n_b2b,
        "n_rested":        n_rest,
        "notes":           notes,
    }

# Find top 3 faders (most negative margin_delta, min 5 B2B games)
faders = [
    (tri, v["b2b_margin_delta"])
    for tri, v in teams_out.items()
    if v["n_b2b"] >= 5 and v["b2b_margin_delta"] is not None
]
faders_sorted = sorted(faders, key=lambda x: x[1])
top_faders = [{"team": tri, "b2b_margin_delta": d} for tri, d in faders_sorted[:5]]
print(f"  Top B2B faders: {top_faders[:3]}")


# ── 7. Assemble output ────────────────────────────────────────────────────────
output = {
    "meta": {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": "2025-26",
        "source_games": n_games,
        "gamelog_coverage": int(df["total"].notna().sum()),
        "leak_safe": True,
        "notes": (
            "rest_days and back_to_back derived solely from prior completed game dates. "
            "Regular season only (game_id prefix 0022500xxx). Playoffs excluded."
        ),
        "caveats": [
            "Per-team n_b2b is 8-23 games — margins are directionally informative but "
            "high-variance; treat as scouting color not sharp signals.",
            "home_pace and away_pace are rolling pre-game averages (not actual game pace); "
            "pace_delta reflects style differences, not measured fatigue.",
            "3-in-4 and 4-in-6 are per team-game instances (team playing that slot); "
            "a game can have both teams in the spot simultaneously.",
            "margin for 3-in-4 / 4-in-6 is from the fatigued team's perspective (signed).",
            "No market-line comparison in this artifact — ROI grading requires a separate "
            "live-odds dataset.",
        ],
        "top_b2b_faders": top_faders,
    },
    "league": {
        "home_edge_winpct":  _round(baseline_home_win),
        "home_edge_margin":  _round(baseline_margin),
        "n_games":           n_games,
        "baseline_total":    _round(baseline_total),
        "baseline_pace":     _round(baseline_pace),
        # ── B2B scenarios (team_long perspective — fatigued team's view) ──
        "b2b": {
            "description": "Team playing on 0-days rest (back-to-back 2nd night), from fatigued team POV",
            **tl_b2b_stats,
        },
        "rested": {
            "description": "Team on 2+ days rest (not on B2B), from team POV — comparison baseline",
            **tl_rested_stats,
        },
        # ── Home team specific rest buckets (game-level perspective) ──
        "b2b_home": {
            "description": "Games where home team is on B2B (home win% / home margin)",
            **h_b2b,
        },
        "b2b_away": {
            "description": "Games where away team is on B2B — shows whether home benefits",
            **a_b2b,
        },
        "any_b2b_game": {
            "description": "Any game with at least one team on B2B",
            **any_b2b,
        },
        "rest1": {
            "description": "Home team on exactly 1 rest day (identical to b2b_home bucket)",
            **h_rest1,
        },
        "rest2": {
            "description": "Home team on exactly 2 rest days (most common bucket)",
            **h_rest2,
        },
        "rest2plus": {
            "description": "Home team on 2+ rest days (rested home baseline)",
            **h_rest2plus,
        },
        # ── Multi-game stretches (team_long view) ──
        "three_in_four": {
            "description": "Team playing its 3rd game in a 4-day window (fatigue accumulation)",
            **tl_3in4_stats,
        },
        "four_in_six": {
            "description": "Team playing its 4th game in a 6-day window (deep grind)",
            **tl_4in6_stats,
        },
    },
    "teams": teams_out,
}

# ── 8. Write output ──────────────────────────────────────────────────────────
OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"\nWrote: {OUT_PATH}")
print(f"  Size: {OUT_PATH.stat().st_size:,} bytes")

# ── 9. Print summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("LEAGUE SCHEDULE SPOT SUMMARY (2025-26 Regular Season)")
print("=" * 65)
print(f"{'Scenario':<22} {'WinPct':>7} {'Margin':>8} {'Total':>8} {'Pace':>8} {'N':>6}")
print("-" * 65)
lg = output["league"]

def _fmt(d):
    wp = f"{d['winpct']:.3f}" if d.get("winpct") is not None else " N/A"
    mg = f"{d['margin']:+.2f}" if d.get("margin") is not None else "  N/A"
    tot = f"{d['total']:.1f}" if d.get("total") is not None else "  N/A"
    pace = f"{d['pace']:.2f}" if d.get("pace") is not None else "  N/A"
    return wp, mg, tot, pace, d.get("n", 0)

for label, key in [
    ("Baseline (all)",  None),
    ("Rested (2+ days)","rested"),
    ("B2B (any team)",  "b2b"),
    ("B2B home",        "b2b_home"),
    ("B2B away",        "b2b_away"),
    ("Rest1 (home)",    "rest1"),
    ("Rest2 (home)",    "rest2"),
    ("Rest2+ (home)",   "rest2plus"),
    ("3-in-4",          "three_in_four"),
    ("4-in-6",          "four_in_six"),
]:
    if key is None:
        print(f"{'Baseline (all)':<22} {lg['home_edge_winpct']:>7.3f} "
              f"{lg['home_edge_margin']:>+8.2f} {lg['baseline_total']:>8.1f} "
              f"{lg['baseline_pace']:>8.2f} {lg['n_games']:>6}")
    else:
        d = lg[key]
        wp, mg, tot, pace, n = _fmt(d)
        print(f"{label:<22} {wp:>7} {mg:>8} {tot:>8} {pace:>8} {n:>6}")

print("\nHome court: win% {:.3f}, avg margin {:+.2f} pts".format(
    lg['home_edge_winpct'], lg['home_edge_margin']))

print("\nTop B2B faders (team, margin_delta):")
for f in output["meta"]["top_b2b_faders"]:
    print(f"  {f['team']}: {f['b2b_margin_delta']:+.2f} pts on B2B vs rested")

print("\nDONE")
