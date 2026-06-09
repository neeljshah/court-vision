"""
build_rest_advantage.py
─────────────────────────────────────────────────────────────────────────────
REST-ADVANTAGE matchup-outcome intelligence for the 2025-26 NBA regular season.

This is the schedule-MISMATCH signal: when one team enters a game with a rest
edge over its opponent (e.g. rested vs an opponent on a back-to-back), how does
that differential move the game's MARGIN, WIN%, and TOTAL?  This is DISTINCT
from a team's own back-to-back fade (see build_team_schedule_spots.py): here the
unit of analysis is the *gap* between the two teams' rest, classified by
REST DIFFERENTIAL  = team_rest_days − opp_rest_days  ∈ {…, −2, −1, 0, +1, +2 …}.

SOURCES
    data/nba/season_games_2025-26.json
        — per-game rows with home/away rest_days + back_to_back flags + pace.
          Rest flags are pre-game (derived from prior completed game dates).
          N=1,225 completed regular-season games (game_id prefix 0022500xxx).
          NOTE: rest_days is clipped to [1, 9]; a back-to-back (0 days off)
          is encoded as rest_days==1 and back_to_back==1 (verified 1:1).
    data/cache/cv_fix/leaguegamelog_regular_season.parquet
        — player box scores; aggregated to game level for ACTUAL home_pts,
          away_pts → margin and total.  Covers all 1,225 games (100% join).

LEAK SAFETY
    rest_days / back_to_back come solely from the schedule (each team's prior
    completed game date) and are KNOWN before tip — no future-game info.  Only
    the realized margin/total (the thing we measure the effect ON) comes from
    completed games.  Regular season only; playoff rows (prefix 0042) excluded.
    No market lines are touched here — this artifact is SCOUTING, not ROI.

UNIT OF ANALYSIS
    A "team-game" — each completed game yields two rows, one per team, viewed
    from that team's perspective (margin signed for/against, win 0/1, rest_diff
    from that team's POV).  Because every game contributes a +d row and a −d row,
    the rest_diff distribution is anti-symmetric and the n=0 bucket is the
    natural league baseline (equal rest).

OUTPUT
    data/cache/intel_outcome/rest_advantage_outcome.json

SCHEMA  (all units documented in meta.units)
    meta: season, units, generated_at, source_games, leak_safe, caveats
    league_baseline:
        winpct, margin, total, pace, n   (all team-games; margin≈0 by symmetry)
        home_winpct, home_margin         (home-court reference, game-level)
    by_rest_diff:  keyed "+2","+1","0","-1","-2"  (|diff|≥3 folded into ±2 cap)
        rested_winpct  — win% of the team holding this rest differential
        rested_margin  — mean signed margin (this team − opp), points
        margin_lift    — rested_margin minus the equal-rest (0) baseline margin
        winpct_lift    — rested_winpct minus the equal-rest (0) baseline win%
        total          — mean game total (both teams' points)
        total_lift     — total minus equal-rest baseline total
        pace           — mean pre-game pace proxy (rolling avg of both teams)
        n              — team-game instances in this bucket
    headline:
        rested_vs_b2b  — the marquee mismatch: this team rest≥2, opponent on B2B
        b2b_vs_rested  — the mirror (this team on B2B vs a rested opponent)
        both_b2b       — both teams on a back-to-back (tired-vs-tired)
        both_rested    — both teams rest≥2 (the common, neutral state)
    rest_diff_curve:  ordered list of {diff, rested_winpct, rested_margin,
                      total, n} for quick plotting / scanning.
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
OUT_PATH = OUT_DIR / "rest_advantage_outcome.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# Cap the rest differential magnitude; buckets beyond this are sparse.
DIFF_CAP = 2


# ── Helpers ───────────────────────────────────────────────────────────────────
def _round(x, n=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), n)


def _bucket_stats(sub, base_margin, base_total, base_winpct):
    """Aggregate one team-game subset into the output stat dict (+lifts)."""
    n = len(sub)
    if n == 0:
        return {
            "rested_winpct": None, "rested_margin": None,
            "margin_lift": None, "winpct_lift": None,
            "total": None, "total_lift": None, "pace": None, "n": 0,
        }
    winpct = sub["win"].mean()
    margin = sub["margin"].mean()
    total = sub["total"].mean()
    pace = sub["game_pace"].mean()
    return {
        "rested_winpct": _round(winpct),
        "rested_margin": _round(margin),
        "margin_lift": _round(margin - base_margin) if base_margin is not None else None,
        "winpct_lift": _round(winpct - base_winpct) if base_winpct is not None else None,
        "total": _round(total),
        "total_lift": _round(total - base_total) if base_total is not None else None,
        "pace": _round(pace),
        "n": int(n),
    }


# ── 1. Load season_games — completed regular-season games only ────────────────
print("Loading season_games_2025-26.json ...")
raw = json.loads(SEASON_GAMES_PATH.read_text(encoding="utf-8"))
df_sg = pd.DataFrame(raw["rows"])
df_sg = df_sg[df_sg["game_id"].str.startswith("0022")].copy()
df_sg = df_sg.dropna(subset=["home_win"])
print(f"  Completed reg-season games: {len(df_sg)}")

for col in ["home_win", "home_rest_days", "away_rest_days",
            "home_back_to_back", "away_back_to_back",
            "home_pace", "away_pace"]:
    df_sg[col] = pd.to_numeric(df_sg[col])

# ── 2. Actual game scores from leaguegamelog ─────────────────────────────────
print("Loading leaguegamelog_regular_season.parquet ...")
dflog = pd.read_parquet(GAMELOG_PATH)
dflog["is_home"] = dflog["MATCHUP"].str.contains(r" vs\.")
game_team = (
    dflog.groupby(["GAME_ID", "TEAM_ABBREVIATION", "WL"])
    .agg(PTS=("PTS", "sum"), is_home=("is_home", "first"))
    .reset_index()
)
home_df = game_team[game_team["is_home"]].rename(
    columns={"TEAM_ABBREVIATION": "home_team", "PTS": "home_pts"}
)[["GAME_ID", "home_team", "home_pts"]]
away_df = game_team[~game_team["is_home"]].rename(
    columns={"TEAM_ABBREVIATION": "away_team", "PTS": "away_pts"}
)[["GAME_ID", "away_team", "away_pts"]]
scores = home_df.merge(away_df, on="GAME_ID")
scores["margin"] = scores["home_pts"] - scores["away_pts"]   # home perspective
scores["total"] = scores["home_pts"] + scores["away_pts"]
print(f"  Gamelog game-level rows: {len(scores)}")

# ── 3. Master join: rest flags + actual scores ───────────────────────────────
df = df_sg.merge(
    scores[["GAME_ID", "margin", "total"]],
    left_on="game_id", right_on="GAME_ID", how="inner",
)
df["game_pace"] = (df["home_pace"] + df["away_pace"]) / 2
print(f"  Joined games with scores: {len(df)} "
      f"(coverage {len(df)/len(df_sg):.1%})")

# ── 4. Build team-game long table with rest_diff from each team's POV ─────────
# Home rows: rest_diff = home_rest − away_rest; margin/win from home POV.
home_long = pd.DataFrame({
    "game_id": df["game_id"].values,
    "team": df["home_team"].values,
    "opp": df["away_team"].values,
    "win": df["home_win"].astype(int).values,
    "margin": df["margin"].values,
    "total": df["total"].values,
    "game_pace": df["game_pace"].values,
    "team_rest": df["home_rest_days"].values,
    "opp_rest": df["away_rest_days"].values,
    "team_b2b": df["home_back_to_back"].astype(int).values,
    "opp_b2b": df["away_back_to_back"].astype(int).values,
})
# Away rows: rest_diff = away_rest − home_rest; margin/win flipped to away POV.
away_long = pd.DataFrame({
    "game_id": df["game_id"].values,
    "team": df["away_team"].values,
    "opp": df["home_team"].values,
    "win": (1 - df["home_win"]).astype(int).values,
    "margin": (-df["margin"]).values,
    "total": df["total"].values,
    "game_pace": df["game_pace"].values,
    "team_rest": df["away_rest_days"].values,
    "opp_rest": df["home_rest_days"].values,
    "team_b2b": df["away_back_to_back"].astype(int).values,
    "opp_b2b": df["home_back_to_back"].astype(int).values,
})
tl = pd.concat([home_long, away_long], ignore_index=True)
tl["rest_diff_raw"] = tl["team_rest"] - tl["opp_rest"]
tl["rest_diff"] = tl["rest_diff_raw"].clip(-DIFF_CAP, DIFF_CAP).astype(int)
print(f"  Team-game rows: {len(tl)}  (= 2 × {len(df)})")
print("  Raw rest_diff distribution:")
print(tl["rest_diff_raw"].value_counts().sort_index().to_string())

# ── 5. Baselines (equal rest = the rest_diff==0 bucket is the natural null) ───
base = tl[tl["rest_diff"] == 0]
base_winpct = base["win"].mean()
base_margin = base["margin"].mean()
base_total = base["total"].mean()
base_pace = base["game_pace"].mean()
print(f"\n  Equal-rest baseline (n={len(base)}): "
      f"win%={base_winpct:.3f} margin={base_margin:+.2f} "
      f"total={base_total:.1f} pace={base_pace:.2f}")

# Whole-league (all team-games) reference — margin ~0 by anti-symmetry.
all_winpct = tl["win"].mean()
all_margin = tl["margin"].mean()
all_total = tl["total"].mean()
all_pace = tl["game_pace"].mean()
# Home-court reference (game-level).
home_winpct = df["home_win"].mean()
home_margin = df["margin"].mean()

# ── 6. by_rest_diff buckets ──────────────────────────────────────────────────
by_rest_diff = {}
for d in range(DIFF_CAP, -DIFF_CAP - 1, -1):
    key = f"+{d}" if d > 0 else str(d)
    sub = tl[tl["rest_diff"] == d]
    by_rest_diff[key] = _bucket_stats(sub, base_margin, base_total, base_winpct)

# ── 7. Headline spots (B2B-based, the sharpest mismatch definitions) ─────────
def _spot(mask):
    return _bucket_stats(tl[mask], base_margin, base_total, base_winpct)

m_rested_vs_b2b = (tl["team_b2b"] == 0) & (tl["opp_b2b"] == 1)   # we're fresh, they're tired
m_b2b_vs_rested = (tl["team_b2b"] == 1) & (tl["opp_b2b"] == 0)   # mirror
m_both_b2b = (tl["team_b2b"] == 1) & (tl["opp_b2b"] == 1)
m_both_rested = (tl["team_b2b"] == 0) & (tl["opp_b2b"] == 0)

headline = {
    "rested_vs_b2b": {
        "description": "This team rest>=2 days, opponent on a back-to-back "
                       "(the marquee schedule mismatch — fresh side's POV).",
        **_spot(m_rested_vs_b2b),
    },
    "b2b_vs_rested": {
        "description": "Mirror: this team on a back-to-back vs a rested "
                       "opponent (the tired side's POV).",
        **_spot(m_b2b_vs_rested),
    },
    "both_b2b": {
        "description": "Both teams on a back-to-back (tired-vs-tired). "
                       "Watch total for an under tilt.",
        **_spot(m_both_b2b),
    },
    "both_rested": {
        "description": "Both teams rest>=2 days (the common, neutral state).",
        **_spot(m_both_rested),
    },
}

# ── 8. Compact curve for plotting ────────────────────────────────────────────
rest_diff_curve = [
    {
        "diff": d,
        "rested_winpct": by_rest_diff[(f"+{d}" if d > 0 else str(d))]["rested_winpct"],
        "rested_margin": by_rest_diff[(f"+{d}" if d > 0 else str(d))]["rested_margin"],
        "total": by_rest_diff[(f"+{d}" if d > 0 else str(d))]["total"],
        "n": by_rest_diff[(f"+{d}" if d > 0 else str(d))]["n"],
    }
    for d in range(-DIFF_CAP, DIFF_CAP + 1)
]

# ── 9. Assemble + write ──────────────────────────────────────────────────────
output = {
    "meta": {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": "2025-26",
        "artifact": "rest_advantage_outcome",
        "source_games": int(len(df)),
        "team_game_rows": int(len(tl)),
        "leak_safe": True,
        "diff_cap": DIFF_CAP,
        "units": {
            "rest_diff": "team_rest_days minus opp_rest_days, clipped to +/-2 "
                         "(B2B encoded as rest_days==1).",
            "rested_winpct": "win fraction [0,1] of the team holding the differential",
            "rested_margin": "mean signed point margin (team minus opp)",
            "margin_lift": "rested_margin minus equal-rest(0) baseline margin, points",
            "winpct_lift": "rested_winpct minus equal-rest(0) baseline win%",
            "total": "mean game total (both teams' points)",
            "total_lift": "total minus equal-rest(0) baseline total, points",
            "pace": "mean pre-game pace proxy (rolling avg of both teams)",
            "n": "team-game instances in the bucket",
        },
        "caveats": [
            "rest_days is clipped to [1,9]; a back-to-back is rest_days==1, so "
            "rest_diff==0 includes both-rested AND both-B2B games (use the "
            "headline both_b2b / both_rested splits to separate them).",
            "Anti-symmetry: every game contributes a +d and a -d team-game, so "
            "by_rest_diff is a mirror around 0 and rested_margin(+d) == "
            "-rested_margin(-d) up to rounding; report the fresh side (+d).",
            "Effects are CORRELATIONAL, not rest-only: the schedule isn't random "
            "(home teams skew slightly more rested) and these buckets mix home "
            "and away team-games. Home-court reference is in league_baseline.",
            "pace is a pre-game rolling proxy, not measured game pace; total is "
            "the actual realized points and is the reliable fatigue read.",
            "Per-bucket n shrinks fast beyond +/-1 (|diff|>=3 folded into +/-2); "
            "treat +/-2 as directional scouting, not a sharp estimate.",
            "SCOUTING ONLY — no market lines compared here. Whether this edge is "
            "already priced into spreads/totals is a SEPARATE betting-validation "
            "agent's job.",
        ],
    },
    "league_baseline": {
        "description": "Equal-rest (rest_diff==0) bucket = the null against which "
                       "lifts are measured, plus whole-league + home-court refs.",
        "equal_rest_winpct": _round(base_winpct),
        "equal_rest_margin": _round(base_margin),
        "equal_rest_total": _round(base_total),
        "equal_rest_pace": _round(base_pace),
        "equal_rest_n": int(len(base)),
        "all_teamgames_winpct": _round(all_winpct),
        "all_teamgames_margin": _round(all_margin),
        "all_teamgames_total": _round(all_total),
        "all_teamgames_pace": _round(all_pace),
        "home_winpct": _round(home_winpct),
        "home_margin": _round(home_margin),
        "n_games": int(len(df)),
    },
    "by_rest_diff": by_rest_diff,
    "headline": headline,
    "rest_diff_curve": rest_diff_curve,
}

OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"\nWrote: {OUT_PATH}")
print(f"  Size: {OUT_PATH.stat().st_size:,} bytes")

# ── 10. Console summary ──────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("REST-ADVANTAGE OUTCOME SUMMARY (2025-26 Regular Season)")
print("=" * 72)
print(f"Equal-rest baseline: win%={base_winpct:.3f}  margin={base_margin:+.2f}  "
      f"total={base_total:.1f}  (n={len(base)})")
print(f"Home court (ref):    win%={home_winpct:.3f}  margin={home_margin:+.2f}\n")
print(f"{'rest_diff':>9} {'win%':>7} {'margin':>8} {'mlift':>7} "
      f"{'wlift':>7} {'total':>7} {'tlift':>7} {'n':>6}")
print("-" * 72)
for d in range(DIFF_CAP, -DIFF_CAP - 1, -1):
    key = f"+{d}" if d > 0 else str(d)
    s = by_rest_diff[key]
    if s["n"] == 0:
        continue
    print(f"{key:>9} {s['rested_winpct']:>7.3f} {s['rested_margin']:>+8.2f} "
          f"{s['margin_lift']:>+7.2f} {s['winpct_lift']:>+7.3f} "
          f"{s['total']:>7.1f} {s['total_lift']:>+7.2f} {s['n']:>6}")

print("\nHEADLINE SPOTS:")
for k, v in headline.items():
    if v["n"] == 0:
        continue
    print(f"  {k:<16} win%={v['rested_winpct']:.3f}  "
          f"margin={v['rested_margin']:+.2f} (lift {v['margin_lift']:+.2f})  "
          f"total={v['total']:.1f} (lift {v['total_lift']:+.2f})  n={v['n']}")

print("\nDONE")
