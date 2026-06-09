"""engine_clutch_close.py -- Clutch/close-game-weighted team strength engine.

METHODOLOGY
-----------
Derives team strength from COMPETITIVE-GAME-STATE performance rather than
full-game averages.  Two complementary signals are blended:

  1. Close-game final-margin net (team_game.parquet, NYK/SAS; league_team_game
     for all 30 teams as fallback): mean final-margin in games decided by <=5 pts.
     This captures end-of-game execution (clock management, late possessions,
     free-throw shooting, ball-security, crunch coaching).

  2. Clutch-possession PPP net (pbp_possessions.parquet, 30-team, abs_margin<=5
     AND period>=4 AND game-remaining<=300s): (off_ppp - def_ppp) per team in
     play-in-late-tight-game possessions.  This is the most granular signal --
     shot quality, shot creation, and defense IN THE STATES THAT DECIDE GAMES.

Blend: close_net and clutch_ppp_net are in different units (pts vs PPP).
  - Convert clutch_net_ppp to pts: clutch_pts_tilt = clutch_net_ppp * PACE * SCALE
    where SCALE=0.5 downweights to a tilt (clutch n is small; regress toward 0).
  - margin_home = ALPHA*close_net_diff + (1-ALPHA)*clutch_tilt + hca
    ALPHA=0.6 (close-game final margin) / 0.4 (clutch PPP).

DATA AVAILABILITY
-----------------
- team_game.parquet: NYK/SAS ONLY (100 games each season).
- pbp_possessions.parquet: 30 teams, 196 games partial season (league-wide).
- league_team_game.parquet: 30 teams, full season (fallback for non-NYK/SAS).

For NYK/SAS: both paths are live.
For all other teams: close-game net from league_team_game; clutch PPP from pbp_possessions
  (league-wide 30-team coverage).

DECORRELATION EXPECTATION
--------------------------
honesty_class=research.  Clutch/close-state strength is a SUBSET of game-states
-- a genuinely different slice from full-game net-rating.  The existing system
found "NYK better LATE despite SAS better over 48min" (a real wedge).  Realistic
prior: r=0.4-0.6 correlation with the net-rating cluster for the Finals matchup
(where we have real data), falling back toward r~0.8 for teams using the
league-wide fallback.  Do NOT assume decorrelation -- measure with the 16x16
matrix.  margin_sd is wide (honest; clutch n is small).

SMALL-N WARNING: close games per team ~19 (NYK) / 27 (SAS) in this partial
season.  Clutch possessions per team: ~300-350 for NYK/SAS, as low as ~2 for
some teams (SAC, UTA).  Low-count teams are regularized toward league mean.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths  -- engines_x/ is one level deeper than engines/, both under
# scripts/team_system/.  parents[3] = nba-ai-system repo root.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_TEAM_GAME = os.path.join(_REPO, "data", "cache", "team_system", "team_game.parquet")
_LEAGUE_GAME = os.path.join(_REPO, "data", "cache", "team_system", "league_team_game.parquet")
_PBP = os.path.join(_REPO, "data", "cache", "team_system", "pbp_possessions.parquet")

# ---------------------------------------------------------------------------
# Hyper-parameters (calibrated on 2025-26 season aggregate; do not over-tune)
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7          # HCA pts
CLOSE_THRESH: int = 5           # abs(final_margin) <= this -> "close game"
CLUTCH_MARGIN: int = 5          # abs_margin <= this in clutch
CLUTCH_MIN_GREM: float = 300.0  # last 300s (5 min) of period 4+
ALPHA: float = 0.6              # weight on close-game final-margin signal
PACE_DEFAULT: float = 101.82    # league avg possessions per team per game
PPP_SCALE: float = 0.5          # regress clutch PPP net (small n)
CLUTCH_PPP_TO_PTS: float = 95.0 # pace multiplier for clutch net PPP -> pts/game tilt
MIN_CLOSE_N: int = 5            # min close games to trust; below -> regress 50%
MIN_CLUTCH_N: int = 20          # min clutch poss to trust; below -> heavy regress
MARGIN_SD: float = 14.5         # honest single-game error floor (clutch n is small ->
                                 # widen vs ~13 for full-game engines)
FALLBACK_TOTAL: float = 220.0   # league avg game total for total estimate


# ---------------------------------------------------------------------------
# Build -- cached so predict() is fast on repeated calls
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _build() -> dict:
    """Compute clutch/close-game strength for all available teams.

    Returns
    -------
    dict with keys:
        close_net   : {team -> float}  mean final-margin in close games
        close_n     : {team -> int}    number of close games
        clutch_net  : {team -> float}  clutch PPP net (off_ppp - def_ppp)
        clutch_n    : {team -> int}    total clutch possessions (off side)
        league_close_mean : float
        league_clutch_mean : float
        total_avg   : {team -> float}  from league_game
        league_avg_total : float
        margin_sd   : float
        n_signals   : int
        n_models    : int
    """
    # ---- league_team_game (30 teams, close-game fallback) ------------------
    ltg = pd.read_parquet(_LEAGUE_GAME)
    ltg["final_margin"] = ltg["pts"] - ltg["opp_pts"]
    ltg["final_margin_abs"] = ltg["final_margin"].abs()
    close_ltg = ltg[ltg["final_margin_abs"] <= CLOSE_THRESH]

    close_net: dict[str, float] = {}
    close_n: dict[str, int] = {}
    for team, grp in close_ltg.groupby("team"):
        close_net[str(team)] = float(grp["final_margin"].mean())
        close_n[str(team)] = int(len(grp))

    league_close_mean: float = float(close_ltg["final_margin"].mean()) if len(close_ltg) else 0.0

    # per-team avg total from league games
    total_avg: dict[str, float] = {}
    league_avg_total: float = float((ltg["pts"] + ltg["opp_pts"]).mean())
    for team, grp in ltg.groupby("team"):
        total_avg[str(team)] = float((grp["pts"] + grp["opp_pts"]).mean())

    # Regularize close_net toward league mean for thin samples
    for team in list(close_net.keys()):
        n = close_n[team]
        if n < MIN_CLOSE_N:
            w = n / (n + MIN_CLOSE_N)  # shrink toward 0 (league-relative already ~ 0)
            close_net[team] = close_net[team] * w

    n_close_signals = int(len(close_ltg))

    # ---- team_game.parquet (NYK/SAS only -- override with local data) ------
    if os.path.exists(_TEAM_GAME):
        tg = pd.read_parquet(_TEAM_GAME)
        tg["final_margin"] = tg["pts"] - tg["opp_pts"]
        tg["final_margin_abs"] = tg["final_margin"].abs()
        close_local = tg[tg["final_margin_abs"] <= CLOSE_THRESH]
        for team, grp in close_local.groupby("team"):
            close_net[str(team)] = float(grp["final_margin"].mean())
            close_n[str(team)] = int(len(grp))

    # ---- pbp_possessions (30 teams, clutch possessions) --------------------
    pbp = pd.read_parquet(_PBP)
    clutch_pbp = pbp[
        (pbp["abs_margin"] <= CLUTCH_MARGIN)
        & (pbp["period"] >= 4)
        & (pbp["grem"] <= CLUTCH_MIN_GREM)
    ].copy()

    # Offensive clutch PPP
    off_g = (
        clutch_pbp.groupby("off")
        .agg(poss_n=("pts", "count"), pts_sum=("pts", "sum"))
        .reset_index()
    )
    off_g["off_ppp"] = off_g["pts_sum"] / off_g["poss_n"]

    # Defensive clutch PPP (pts allowed to opponent while THIS team defends)
    def_g = (
        clutch_pbp.groupby("deff")
        .agg(def_poss=("pts", "count"), def_pts=("pts", "sum"))
        .reset_index()
    )
    def_g["def_ppp"] = def_g["def_pts"] / def_g["def_poss"]

    # Merge to get net
    off_map = dict(zip(off_g["off"], off_g["off_ppp"]))
    off_n_map = dict(zip(off_g["off"], off_g["poss_n"]))
    def_map = dict(zip(def_g["deff"], def_g["def_ppp"]))

    league_off_ppp: float = float(clutch_pbp["pts"].sum() / len(clutch_pbp)) if len(clutch_pbp) else 1.15
    league_def_ppp: float = league_off_ppp  # symmetric
    league_clutch_net: float = 0.0  # league-relative

    clutch_net: dict[str, float] = {}
    clutch_n: dict[str, int] = {}
    for team in sorted(off_g["off"].unique()):
        o_ppp = off_map.get(team, league_off_ppp)
        d_ppp = def_map.get(team, league_def_ppp)
        raw_net = float(o_ppp - d_ppp)
        n_poss = int(off_n_map.get(team, 0))
        # Regularize small samples toward 0
        if n_poss < MIN_CLUTCH_N:
            w = n_poss / (n_poss + MIN_CLUTCH_N)
            raw_net = raw_net * w
        clutch_net[str(team)] = PPP_SCALE * raw_net
        clutch_n[str(team)] = n_poss

    n_pbp_signals = int(len(clutch_pbp))
    all_teams_covered = set(close_net.keys()) | set(clutch_net.keys())
    n_models = len(all_teams_covered)

    return {
        "close_net": close_net,
        "close_n": close_n,
        "clutch_net": clutch_net,
        "clutch_n": clutch_n,
        "league_close_mean": league_close_mean,
        "league_clutch_net": league_clutch_net,
        "total_avg": total_avg,
        "league_avg_total": league_avg_total,
        "margin_sd": MARGIN_SD,
        "n_signals": n_close_signals + n_pbp_signals,
        "n_models": n_models,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return standardised prediction dict for the clutch/close-game engine.

    Parameters
    ----------
    home_tri : str   Three-letter team code (e.g. "NYK")
    away_tri : str   Three-letter team code (e.g. "SAS")
    context  : dict  Optional keys: neutral_site (bool), playoffs (bool)

    Notes
    -----
    - Full clutch data available for all 30 teams via pbp_possessions (30t).
    - Close-game final-margin available league-wide from league_team_game (30t).
    - NYK/SAS also have team_game local data (100 games, higher fidelity).
    - Structurally a 2-team engine for highest fidelity; 30-team capable via fallback.
    - margin_sd is WIDE (14.5) -- clutch n is small -> honest uncertainty.
    - honesty_class=research; NO claimed betting edge; playoff edge unproven.
    - Predicted correlation to net-rating cluster: r~0.4-0.6 (Finals matchup) via
      competitive-state subsetting; measure with 16x16 matrix before asserting.
    """
    ctx = context or {}
    art = _build()

    home = home_tri.upper()
    away = away_tri.upper()

    known = set(art["close_net"].keys()) | set(art["clutch_net"].keys())
    if home not in known:
        raise ValueError(f"engine_clutch_close: unknown team {home!r}. Known: {sorted(known)}")
    if away not in known:
        raise ValueError(f"engine_clutch_close: unknown team {away!r}. Known: {sorted(known)}")

    neutral = bool(ctx.get("neutral_site", False))
    hca = 0.0 if neutral else HOME_EDGE

    # --- Signal 1: close-game final-margin differential ---
    home_close = art["close_net"].get(home, art["league_close_mean"])
    away_close = art["close_net"].get(away, art["league_close_mean"])
    close_diff = home_close - away_close  # pts (home - away net in close games)

    # --- Signal 2: clutch PPP net differential -> pts tilt ---
    home_clutch = art["clutch_net"].get(home, art["league_clutch_net"])
    away_clutch = art["clutch_net"].get(away, art["league_clutch_net"])
    clutch_diff_ppp = home_clutch - away_clutch
    clutch_tilt = clutch_diff_ppp * CLUTCH_PPP_TO_PTS  # convert PPP net to pts/game tilt

    # --- Blend and add HCA ---
    margin_home = ALPHA * close_diff + (1.0 - ALPHA) * clutch_tilt + hca

    # --- Total: average of the two teams' game totals ---
    home_total = art["total_avg"].get(home, art["league_avg_total"])
    away_total = art["total_avg"].get(away, art["league_avg_total"])
    total = (home_total + away_total) / 2.0

    # --- Points split ---
    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # --- Win probability ---
    margin_sd = art["margin_sd"]
    win_prob_home = 0.5 + 0.5 * math.erf(margin_home / (margin_sd * math.sqrt(2.0)))
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    # --- Notes ---
    home_cn = art["close_n"].get(home, 0)
    away_cn = art["close_n"].get(away, 0)
    home_qn = art["clutch_n"].get(home, 0)
    away_qn = art["clutch_n"].get(away, 0)
    local_nyk_sas = all(t in {"NYK", "SAS"} for t in [home, away])
    data_note = "team_game+pbp (full local)" if local_nyk_sas else "league_game+pbp (fallback)"
    notes = (
        f"clutch_close: {home} close_net={home_close:+.2f}(n={home_cn}) "
        f"clutch_net_ppp={home_clutch:+.4f}(n={home_qn}) | "
        f"{away} close_net={away_close:+.2f}(n={away_cn}) "
        f"clutch_net_ppp={away_clutch:+.4f}(n={away_qn}) | "
        f"margin={margin_home:+.2f} total={total:.1f} "
        f"({'neutral' if neutral else 'HCA+2.7'}); "
        f"data={data_note}; margin_sd={margin_sd:.1f}(wide/honest); "
        f"honesty_class=research; NO betting edge claimed"
    )

    return {
        "engine": "clutch_close",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 2),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": round(margin_sd, 2),
        "n_models": art["n_models"],
        "n_signals": art["n_signals"],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    print("=" * 70)
    print("ENGINE: clutch_close")
    print("  Signals: close-game final-margin + clutch PPP net (off-def)")
    print("  Data: team_game (NYK/SAS) + league_team_game (30t) + pbp_possessions (30t)")
    print("  honesty_class=research; margin_sd WIDE (clutch n small)")
    print("=" * 70)

    art = _build()
    print(f"\nn_signals: {art['n_signals']}")
    print(f"n_models (teams covered): {art['n_models']}")
    print(f"margin_sd: {art['margin_sd']} (intentionally wide -- honest)")
    print(f"league_close_mean: {art['league_close_mean']:+.4f}")

    print("\n--- Close-game net (top 5 / bottom 5) ---")
    ranked = sorted(art["close_net"].items(), key=lambda x: x[1], reverse=True)
    for team, val in ranked[:5]:
        n = art["close_n"].get(team, 0)
        print(f"  {team:4s}  {val:+.3f}  (n={n} close games)")
    print("  ...")
    for team, val in ranked[-5:]:
        n = art["close_n"].get(team, 0)
        print(f"  {team:4s}  {val:+.3f}  (n={n} close games)")

    print("\n--- Clutch PPP net (top 5 / bottom 5) ---")
    crank = sorted(art["clutch_net"].items(), key=lambda x: x[1], reverse=True)
    for team, val in crank[:5]:
        n = art["clutch_n"].get(team, 0)
        print(f"  {team:4s}  {val:+.4f}  (n={n} clutch poss)")
    print("  ...")
    for team, val in crank[-5:]:
        n = art["clutch_n"].get(team, 0)
        print(f"  {team:4s}  {val:+.4f}  (n={n} clutch poss)")

    print("\n--- predict(NYK, SAS) ---")
    r1 = predict("NYK", "SAS")
    for k, v in r1.items():
        if k == "notes":
            print(f"  {k}: {v}")
        else:
            print(f"  {k:<18s} {v}")

    print("\n--- predict(SAS, NYK) [road-SAS] ---")
    r2 = predict("SAS", "NYK")
    for k, v in r2.items():
        if k == "notes":
            continue
        print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral_site=True) ---")
    r3 = predict("NYK", "SAS", {"neutral_site": True})
    for k, v in r3.items():
        if k == "notes":
            continue
        print(f"  {k:<18s} {v}")

    margin_diff = abs(r1["margin_home"] - r3["margin_home"])
    assert abs(margin_diff - HOME_EDGE) < 0.5, (
        f"HCA removal test failed: diff={margin_diff:.3f}, expected ~{HOME_EDGE}"
    )
    assert abs(r1["home_pts"] + r1["away_pts"] - r1["total"]) < 0.1, "pts split != total"
    assert abs(r1["home_pts"] - r1["away_pts"] - r1["margin_home"]) < 0.1, "pts diff != margin"
    assert 0.01 <= r1["win_prob_home"] <= 0.99, "win_prob out of range"
    assert r1["margin_sd"] > 0, "margin_sd must be positive"

    print("\n--- ValueError on unknown team ---")
    try:
        predict("XXX", "SAS")
        print("  FAIL: should have raised ValueError")
    except ValueError as e:
        print(f"  OK: {e}")

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
