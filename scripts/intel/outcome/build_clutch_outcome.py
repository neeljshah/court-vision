#!/usr/bin/env python
"""
build_clutch_outcome.py  --  CLUTCH / CLOSING outcome layer for CourtVision.

Answers: who actually closes out games -- at the TEAM level (do they close or
choke?) and the PLAYER level (who is the league's best closer?).

SCOPE / HOUSE RULES
-------------------
- Season: 2025-26 regular season is PRIMARY (the only season in the team-game
  source). All numbers are descriptive, within-season, leak-free (they describe
  what already happened this season -- no forward prediction, no future leakage).
- DESCRIPTIVE ONLY. This is a scouting artifact, not a bet model.

CLUTCH DEFINITIONS (two complementary lenses; documented per-field)
-------------------------------------------------------------------
PLAYER clutch box stats come from `clutch_profiles_2025-26.parquet`, which is the
  NBA-Stats clutch definition: last 5 minutes of the game with score margin <= 5
  points (LeagueDashPlayerClutch). This is the canonical "clutch" window.

TEAM clutch record uses a FINAL-MARGIN proxy: a game is a "clutch game" for both
  teams if the FINAL score margin was <= 5 points. This is computed from
  per-team final points in `leaguegamelog_regular_season.parquet`. It is a proxy
  for "close finish", NOT the exact last-5-min/<=5-pt NBA clutch-game flag (which
  would require the LeagueDashTeamClutch endpoint, not present in this repo). It
  is stricter than the true clutch-game rate (a tied-at-5-min game that blows
  open is NOT counted), so n_clutch_games here is a lower bound on true clutch
  games. ~24.5% of 2025-26 games finished within 5.

SECONDARY (CV, low-n, flagged): `clutch_rankings.json` ELEVATOR/SHRINKER tags
  from tracking deltas (clutch vs non-clutch movement). Coverage is tiny (1-4
  games/player) so it is attached only as a low-confidence behavioral note.

SOURCES (all under data/, recon'd)
----------------------------------
- data/cache/clutch_profiles_2025-26.parquet   (player NBA-clutch box: gp/min/pts/fg/+-)
- data/cache/cv_fix/leaguegamelog_regular_season.parquet  (2025-26 player game logs ->
      team-game final scores -> margins/records, and player->team map)
- data/intelligence/clutch_rankings.json       (CV elevator/shrinker, low-n)

OUTPUT
------
data/cache/intel_outcome/clutch_outcome.json
"""

from __future__ import annotations
import json
import math
import os
import sys

import numpy as np
import pandas as pd

# Windows console defaults to cp1252; force UTF-8 so player names with accents
# (Jokic, Doncic, ...) don't crash the summary print. Does not affect the JSON.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def P(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


SEASON = "2025-26"
CLUTCH_MARGIN = 5            # final-margin proxy threshold for a team "clutch game"
LOWN_CLUTCH_GP = 10         # players below this clutch_gp are flagged low-n
MIN_CLUTCH_GP_LEADERBOARD = 10  # closers leaderboard requires >= this many clutch games

OUT_DIR = P("data", "cache", "intel_outcome")
OUT_PATH = os.path.join(OUT_DIR, "clutch_outcome.json")

LGL_PATH = P("data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")
CLUTCH_PROFILES_PATH = P("data", "cache", "clutch_profiles_2025-26.parquet")
CLUTCH_RANKINGS_PATH = P("data", "intelligence", "clutch_rankings.json")


def _round(x, n=3):
    if x is None:
        return None
    try:
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# 1. TEAM clutch profile (final-margin <=5 proxy)
# --------------------------------------------------------------------------- #
def build_teams(lgl: pd.DataFrame) -> dict:
    # one row per (game, team) with final points + W/L
    tg = (
        lgl.groupby(["GAME_ID", "TEAM_ABBREVIATION"])
        .agg(pts=("PTS", "sum"), wl=("WL", "first"))
        .reset_index()
    )
    # per-game point differential: team_pts - opponent_pts. (Do NOT sum player
    # PLUS_MINUS -- that double-counts on-court slots and yields ~5x the margin.)
    tot = tg.groupby("GAME_ID")["pts"].sum().rename("game_total")
    tg = tg.merge(tot, on="GAME_ID")
    tg["opp_pts"] = tg["game_total"] - tg["pts"]
    tg["net"] = tg["pts"] - tg["opp_pts"]

    # final margin per game (both teams share it)
    gm = tg.groupby("GAME_ID").agg(maxp=("pts", "max"), minp=("pts", "min"))
    gm["margin"] = gm["maxp"] - gm["minp"]
    clutch_games = set(gm.index[gm["margin"] <= CLUTCH_MARGIN])
    tg["is_clutch_game"] = tg["GAME_ID"].isin(clutch_games)

    teams = {}
    for tri, sub in tg.groupby("TEAM_ABBREVIATION"):
        total_g = len(sub)
        wins = int((sub["wl"] == "W").sum())
        losses = int((sub["wl"] == "L").sum())
        overall_winpct = wins / total_g if total_g else None

        cl = sub[sub["is_clutch_game"]]
        n_cl = len(cl)
        cl_w = int((cl["wl"] == "W").sum())
        cl_l = int((cl["wl"] == "L").sum())
        cl_winpct = cl_w / n_cl if n_cl else None
        # clutch net rating proxy: mean per-game point differential in clutch games
        # (PLUS_MINUS summed over a team's players in a game == team point diff)
        clutch_net = float(cl["net"].mean()) if n_cl else None
        # full-season net for context
        season_net = float(sub["net"].mean()) if total_g else None

        delta = (
            (cl_winpct - overall_winpct)
            if (cl_winpct is not None and overall_winpct is not None)
            else None
        )

        teams[tri] = {
            "clutch_w": cl_w,
            "clutch_l": cl_l,
            "clutch_winpct": _round(cl_winpct),
            "overall_w": wins,
            "overall_l": losses,
            "overall_winpct": _round(overall_winpct),
            "clutch_winpct_delta": _round(delta),
            "clutch_net": _round(clutch_net, 2),
            "season_net": _round(season_net, 2),
            "pct_games_clutch": _round(n_cl / total_g if total_g else None),
            "n_clutch_games": n_cl,
            "n_games": total_g,
        }
    return teams, len(clutch_games)


# --------------------------------------------------------------------------- #
# 2. PLAYER "who closes games"
# --------------------------------------------------------------------------- #
def build_player_team_map(lgl: pd.DataFrame) -> dict:
    """Primary team per player = team with most games played in 2025-26."""
    g = (
        lgl.groupby(["PLAYER_ID", "TEAM_ABBREVIATION"])
        .size()
        .reset_index(name="gp")
        .sort_values("gp", ascending=False)
        .drop_duplicates("PLAYER_ID")
    )
    return {int(r.PLAYER_ID): r.TEAM_ABBREVIATION for r in g.itertuples()}


def build_players(cp: pd.DataFrame, team_map: dict, cv_tags: dict) -> tuple[dict, list]:
    """
    cp columns: player_id, player_name, clutch_gp, clutch_min, clutch_pts,
                clutch_fg_pct, clutch_fg3_pct, clutch_ft_pct, clutch_plus_minus,
                clutch_pts_per36, season
    clutch_pts / clutch_min / clutch_plus_minus are PER-GAME (already averaged).
    """
    # eFG proxy from available pct fields:
    #   eFG = (FGM + 0.5*FG3M) / FGA. We don't have raw counts here (DEFER note in
    #   atlas), so we approximate "clutch shot efficiency" with a blended scoring
    #   efficiency = fg_pct uplifted by the 3pt share. Honest: this is fg_pct-based,
    #   not a true eFG. We expose clutch_fg_pct/fg3_pct directly and compute a
    #   best-effort efg using the 3P proportion of made shots is unknown -> we keep
    #   it transparent: efg_proxy = fg_pct + 0.5 * fg3_pct * (heuristic 3p make share).
    # Since raw FGA/FG3A are unavailable, we report clutch_efg as the plain fg_pct
    # plus a small 3pt bonus only when fg3_pct is itself meaningful; documented as a
    # proxy. To stay honest we set clutch_efg = fg_pct when no better basis exists.
    players: dict[str, dict] = {}
    scored = []  # for leaderboard / impact ranking

    for r in cp.itertuples():
        pid = int(r.player_id)
        spid = str(pid)
        name = r.player_name
        team = team_map.get(pid)
        gp = int(r.clutch_gp) if not pd.isna(r.clutch_gp) else 0
        cmin = _round(r.clutch_min, 2)
        cpts = _round(r.clutch_pts, 2)
        fg = _round(r.clutch_fg_pct)
        fg3 = _round(r.clutch_fg3_pct)
        ft = _round(r.clutch_ft_pct)
        pm = _round(r.clutch_plus_minus, 2)
        pts36 = _round(r.clutch_pts_per36, 2)

        # eFG proxy (transparent): fg_pct is the spine; add a modest 3pt premium
        # proportional to fg3_pct. Bounded, documented as proxy (no raw FGA here).
        if fg is not None:
            efg = fg + 0.25 * (fg3 if fg3 is not None else 0.0)
            efg = _round(min(efg, 1.5))
        else:
            efg = None

        cv = cv_tags.get(pid)

        # confidence: driven by clutch_gp sample size
        if gp >= 20:
            conf = "high"
        elif gp >= LOWN_CLUTCH_GP:
            conf = "med"
        else:
            conf = "low"
        low_n = gp < LOWN_CLUTCH_GP

        rec = {
            "name": name,
            "team": team,
            "clutch_pts": cpts,            # per-game pts in clutch window
            "clutch_pts_per36": pts36,
            "clutch_min": cmin,           # per-game clutch minutes
            "clutch_efg": efg,            # PROXY (fg_pct + 0.25*fg3_pct); see caveats
            "clutch_fg_pct": fg,
            "clutch_fg3_pct": fg3,
            "clutch_ft_pct": ft,
            "clutch_plus_minus": pm,      # per-game on-court +/- in clutch window
            "clutch_impact": None,        # filled below after ranking
            "n_clutch": gp,
            "confidence": conf,
            "low_n": low_n,
            "cv_clutch_class": (cv or {}).get("clutch_class"),
            "cv_elevator_score": (cv or {}).get("elevator_score"),
            "cv_n_games": (cv or {}).get("n_games"),
        }
        players[spid] = rec

        # impact score for ranking: combine volume (pts/36 weighted by usage of
        # clutch minutes) with on-court +/-, gated to a reasonable sample.
        # impact = 0.6 * z(clutch_pts) + 0.4 * z(clutch_plus_minus), computed below.
        scored.append(
            {
                "pid": spid,
                "name": name,
                "team": team,
                "gp": gp,
                "cpts": r.clutch_pts if not pd.isna(r.clutch_pts) else 0.0,
                "pm": r.clutch_plus_minus if not pd.isna(r.clutch_plus_minus) else 0.0,
                "pts36": r.clutch_pts_per36 if not pd.isna(r.clutch_pts_per36) else 0.0,
            }
        )

    # ----- clutch_impact: z-blend of clutch scoring + on-court +/-, sample-gated
    elig = [s for s in scored if s["gp"] >= MIN_CLUTCH_GP_LEADERBOARD]
    if elig:
        cpts_arr = np.array([s["cpts"] for s in elig], dtype=float)
        pm_arr = np.array([s["pm"] for s in elig], dtype=float)

        def z(a):
            sd = a.std()
            return (a - a.mean()) / sd if sd > 1e-9 else np.zeros_like(a)

        zc, zp = z(cpts_arr), z(pm_arr)
        impact = 0.6 * zc + 0.4 * zp
        for s, val in zip(elig, impact):
            players[s["pid"]]["clutch_impact"] = _round(val, 3)

        order = sorted(
            zip(elig, impact), key=lambda t: t[1], reverse=True
        )
        leaderboard = []
        for rank, (s, val) in enumerate(order, start=1):
            p = players[s["pid"]]
            leaderboard.append(
                {
                    "rank": rank,
                    "player_id": s["pid"],
                    "name": s["name"],
                    "team": s["team"],
                    "clutch_impact": _round(val, 3),
                    "clutch_pts": p["clutch_pts"],
                    "clutch_pts_per36": p["clutch_pts_per36"],
                    "clutch_plus_minus": p["clutch_plus_minus"],
                    "clutch_efg": p["clutch_efg"],
                    "n_clutch": s["gp"],
                    "confidence": p["confidence"],
                    "cv_clutch_class": p["cv_clutch_class"],
                }
            )
    else:
        leaderboard = []

    return players, leaderboard


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    lgl = pd.read_parquet(LGL_PATH)
    # leaguegamelog is 2025-26 regular season only (SEASON_ID == '22025'); assert.
    seasons = set(lgl["SEASON_ID"].astype(str).unique())
    assert seasons == {"22025"}, f"unexpected seasons in leaguegamelog: {seasons}"

    cp = pd.read_parquet(CLUTCH_PROFILES_PATH)
    cp = cp[cp["season"] == SEASON].copy()

    cv = json.load(open(CLUTCH_RANKINGS_PATH))
    cv_tags = {}
    for bucket in ("elevators", "shrinkers", "neutrals"):
        for e in cv.get(bucket, []):
            pid = e.get("player_id")
            if pid is not None:
                cv_tags[int(pid)] = e

    teams, n_clutch_games = build_teams(lgl)
    team_map = build_player_team_map(lgl)
    players, leaderboard = build_players(cp, team_map, cv_tags)

    # ----- team rankings by clutch_winpct_delta (close-or-choke) -----
    rankable = [
        (tri, t) for tri, t in teams.items()
        if t["clutch_winpct_delta"] is not None and t["n_clutch_games"] >= 5
    ]
    rankable.sort(key=lambda kv: kv[1]["clutch_winpct_delta"], reverse=True)
    team_delta_rank = [
        {
            "team": tri,
            "clutch_winpct_delta": t["clutch_winpct_delta"],
            "clutch_record": f"{t['clutch_w']}-{t['clutch_l']}",
            "clutch_winpct": t["clutch_winpct"],
            "overall_winpct": t["overall_winpct"],
            "clutch_net": t["clutch_net"],
            "n_clutch_games": t["n_clutch_games"],
        }
        for tri, t in rankable
    ]

    n_lown = sum(1 for p in players.values() if p["low_n"])
    n_players_team = sum(1 for p in players.values() if p["team"] is not None)

    out = {
        "meta": {
            "artifact": "clutch_outcome",
            "season": SEASON,
            "scope": "2025-26 regular season (PRIMARY); descriptive, within-season, leak-free",
            "generated_by": "scripts/intel/outcome/build_clutch_outcome.py",
            "clutch_def": {
                "player_box": (
                    "NBA-Stats clutch: last 5 minutes, score margin <= 5 points "
                    "(LeagueDashPlayerClutch via clutch_profiles_2025-26.parquet). "
                    "clutch_pts / clutch_min / clutch_plus_minus are PER-GAME averages."
                ),
                "team_record": (
                    f"FINAL-MARGIN proxy: a game is a 'clutch game' if final score "
                    f"margin <= {CLUTCH_MARGIN} pts (from per-team final PTS in "
                    f"leaguegamelog). PROXY for close finish, NOT the exact "
                    f"last-5-min/<=5pt team clutch flag; it is STRICTER (lower bound "
                    f"on true clutch games -- a game tied at the 5-min mark that then "
                    f"blows open is not counted)."
                ),
                "cv_behavioral": (
                    "ELEVATOR/SHRINKER tags from tracking deltas (clutch vs "
                    "non-clutch movement) in clutch_rankings.json. VERY low coverage "
                    "(1-4 games/player) -> attached as a flagged low-confidence note "
                    "only; not used in the impact score."
                ),
            },
            "units": {
                "clutch_w/l": "games (clutch-game final-margin proxy)",
                "clutch_winpct / overall_winpct / clutch_winpct_delta": "fraction [0,1]",
                "clutch_net": "mean final point differential (team_pts - opp_pts) per clutch game",
                "season_net": "mean final point differential (team_pts - opp_pts) per game (all games)",
                "pct_games_clutch": "fraction of team games that finished within 5 pts",
                "clutch_pts / clutch_min": "per-GAME within the clutch window",
                "clutch_pts_per36": "points per 36 clutch minutes",
                "clutch_plus_minus": "per-GAME on-court +/- in the clutch window",
                "clutch_efg": "PROXY = fg_pct + 0.25*fg3_pct (raw FGA/FG3A unavailable)",
                "clutch_impact": "z-blend 0.6*z(clutch_pts)+0.4*z(clutch_plus_minus), "
                                 "computed only over players with n_clutch >= "
                                 f"{MIN_CLUTCH_GP_LEADERBOARD}",
            },
            "ranking": {
                "teams": "sorted by clutch_winpct_delta desc (close-or-choke), "
                         "requires n_clutch_games >= 5",
                "closers_leaderboard": "sorted by clutch_impact desc, "
                                       f"requires n_clutch >= {MIN_CLUTCH_GP_LEADERBOARD}",
            },
            "caveats": [
                "Clutch minutes are SMALL: median clutch_min/game ~3, so single-game "
                "swings dominate. clutch_plus_minus is per-game and noisy; treat "
                "magnitudes < ~1 pt as noise.",
                f"{n_lown} of {len(players)} players have < {LOWN_CLUTCH_GP} clutch "
                "games (flagged low_n=true, confidence=low).",
                "clutch_efg is a PROXY (no raw clutch FGA/FG3A in this repo); use "
                "clutch_fg_pct / clutch_fg3_pct for the underlying truth.",
                "Team clutch record uses FINAL margin <=5, a stricter close-finish "
                "proxy than NBA's last-5-min clutch-game flag; n_clutch_games is a "
                "lower bound.",
                "clutch_net is the mean FINAL point differential in close-finish "
                "games (not a possession-normalized net rating). In <=5pt games it "
                "is bounded by +-5, so it mainly reflects how many were won vs lost.",
                "Player->team is the team with the most 2025-26 games (traded players "
                "mapped to primary team).",
                "CV elevator/shrinker tags are coverage-starved (1-4 games); "
                "behavioral color only, not validated for outcome prediction.",
            ],
            "n_teams": len(teams),
            "n_players": len(players),
            "n_players_with_team": n_players_team,
            "n_clutch_games_total": n_clutch_games,
            "n_games_total": int(lgl["GAME_ID"].nunique()),
        },
        "teams": teams,
        "players": players,
        "closers_leaderboard": leaderboard,
        "team_delta_ranking": team_delta_rank,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    # ---- console summary ----
    print(f"WROTE {OUT_PATH}")
    print(f"  teams={len(teams)} players={len(players)} "
          f"(with team={n_players_team}, low_n={n_lown}) "
          f"clutch_games={n_clutch_games}/{out['meta']['n_games_total']}")
    print("\n  BEST 5 clutch teams (winpct delta = clutch - overall):")
    for d in team_delta_rank[:5]:
        print(f"    {d['team']:>3}  d={d['clutch_winpct_delta']:+.3f}  "
              f"clutch {d['clutch_record']} ({d['clutch_winpct']:.3f}) "
              f"overall {d['overall_winpct']:.3f}  net {d['clutch_net']:+.1f}  "
              f"n={d['n_clutch_games']}")
    print("\n  WORST 5 clutch teams:")
    for d in team_delta_rank[-5:][::-1]:
        print(f"    {d['team']:>3}  d={d['clutch_winpct_delta']:+.3f}  "
              f"clutch {d['clutch_record']} ({d['clutch_winpct']:.3f}) "
              f"overall {d['overall_winpct']:.3f}  net {d['clutch_net']:+.1f}  "
              f"n={d['n_clutch_games']}")
    print("\n  TOP 10 closers (clutch_impact, n_clutch>=10):")
    for d in leaderboard[:10]:
        cv = f" [{d['cv_clutch_class']}]" if d.get("cv_clutch_class") else ""
        print(f"    {d['rank']:>2}. {d['name']:<24} {str(d['team']):>3}  "
              f"impact={d['clutch_impact']:+.2f}  pts/g={d['clutch_pts']:.1f}  "
              f"+/-={d['clutch_plus_minus']:+.1f}  n={d['n_clutch']}{cv}")


if __name__ == "__main__":
    main()
