"""engine_elo.py -- Sequential Elo prediction engine.

Algorithm: Standard Elo + MOV multiplier (FiveThirtyEight formula), processed
chronologically over league_team_game.parquet (1158 games, 30 teams, 2025-26).

  Start: 1500. K=20. MOV_mult = log(|margin|+1)*2.2/(0.001*elo_diff+2.2).
  HCA: +100 Elo to home team at prediction time only (no home col in data).
  ELO_PTS_PER_PT: OLS-calibrated from (pre-game elo_diff → actual margin).
  margin_sd: residual SD from full-season fit (optimistic; true OOS higher).

DATA NOTES
  - Each game stored as 2 rows (one per team); deduplicated by keeping win=1 row.
  - Single season only; no multi-year carry-over. honesty_class=research.
  - No home/away in source data; HCA fit is prediction-time only.

DECORRELATION FORECAST (to be confirmed by V5 measurement)
  Predicted corr-to-cluster: r ~ 0.70-0.85 (PARTIAL).
  Elo is recency/sequence-weighted; SRS is flat full-season average.
  Late-season form creates a genuine but modest wedge vs the net-rating cluster.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# engines_x/ -> team_system/ -> scripts/ -> repo root  (3 levels up)
# ---------------------------------------------------------------------------
_REPO = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
_LEAGUE_GAME = os.path.join(
    _REPO, "data", "cache", "team_system", "league_team_game.parquet"
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ELO_START: float = 1500.0
K_FACTOR: float = 20.0
HCA_ELO: float = 100.0      # Elo points added to home team for E-computation
HOME_EDGE_PTS: float = 2.7  # pts margin for non-neutral prediction
FALLBACK_MARGIN_SD: float = 14.0


def _mov_mult(margin: float, abs_elo_diff: float) -> float:
    """FiveThirtyEight MOV multiplier."""
    return math.log(abs(margin) + 1.0) * 2.2 / (0.001 * abs_elo_diff + 2.2)


@lru_cache(maxsize=1)
def _build_ratings() -> dict:
    """Process all games chronologically; return Elo artefacts."""
    df = pd.read_parquet(_LEAGUE_GAME)

    # Unique games: winner row per gid (win=1 is always exactly one per game)
    df_games = (
        df[df["win"] == 1]
        .drop_duplicates("gid")
        .sort_values("date")
        .reset_index(drop=True)
    )
    n_signals = len(df_games)

    teams = sorted(df["team"].unique().tolist())
    ratings: dict[str, float] = {t: ELO_START for t in teams}

    pre_diffs: list[float] = []
    act_margins: list[float] = []

    for _, row in df_games.iterrows():
        winner: str = row["team"]
        loser: str = row["opp"]
        margin: float = float(row["pts"] - row["opp_pts"])

        r_w = ratings.get(winner, ELO_START)
        r_l = ratings.get(loser, ELO_START)
        elo_diff = r_w - r_l

        pre_diffs.append(elo_diff)
        act_margins.append(margin)

        e_w = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
        mov = _mov_mult(margin, abs(elo_diff))
        delta = K_FACTOR * mov * (1.0 - e_w)
        ratings[winner] = r_w + delta
        ratings[loser] = r_l - delta

    # OLS calibration: elo_diff -> winner margin (winner-perspective, always > 0)
    diffs_arr = np.array(pre_diffs)
    margins_arr = np.array(act_margins)
    ols = np.linalg.lstsq(
        np.column_stack([diffs_arr, np.ones(len(diffs_arr))]),
        margins_arr,
        rcond=None,
    )
    ols_slope = float(ols[0][0])
    ols_intercept = float(ols[0][1])
    elo_pts_per_pt = 1.0 / ols_slope if abs(ols_slope) > 1e-9 else 25.0

    # Residual SD (full-season in-sample; actual OOS SD will be higher)
    residuals = margins_arr - (diffs_arr * ols_slope + ols_intercept)
    margin_sd = max(
        float(np.std(residuals, ddof=1)) if len(residuals) > 1 else FALLBACK_MARGIN_SD,
        12.0,  # realistic floor for single-game NBA error
    )

    # Totals and pace
    league_avg_total: float = float((df["pts"] + df["opp_pts"]).mean())
    team_avg_total: dict[str, float] = {
        t: float((df[df["team"] == t]["pts"] + df[df["team"] == t]["opp_pts"]).mean())
        for t in teams
    }
    avg_poss: dict[str, float] = df.groupby("team")["poss"].mean().to_dict()
    league_avg_poss: float = float(df["poss"].mean())

    leaderboard = sorted(ratings.items(), key=lambda x: x[1], reverse=True)

    return {
        "ratings": ratings,
        "elo_pts_per_pt": elo_pts_per_pt,
        "margin_sd": margin_sd,
        "league_avg_total": league_avg_total,
        "team_avg_total": team_avg_total,
        "avg_poss": avg_poss,
        "league_avg_poss": league_avg_poss,
        "n_signals": n_signals,
        "n_models": 30,
        "leaderboard": leaderboard,
    }


def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised prediction dict.

    context keys (all optional):
      neutral_site (bool) -- removes HCA.
      playoffs (bool)     -- no special treatment; ratings unchanged.
    """
    ctx = context or {}
    art = _build_ratings()

    home = home_tri.upper()
    away = away_tri.upper()
    ratings = art["ratings"]

    if home not in ratings:
        raise ValueError(f"Unknown team: {home!r}. Valid: {sorted(ratings)}")
    if away not in ratings:
        raise ValueError(f"Unknown team: {away!r}. Valid: {sorted(ratings)}")

    neutral = bool(ctx.get("neutral_site", False))
    r_home = ratings[home]
    r_away = ratings[away]

    hca_elo_adj = 0.0 if neutral else HCA_ELO
    elo_diff = (r_home + hca_elo_adj) - r_away

    win_prob_home = max(0.01, min(0.99, 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))))

    hca_pts = 0.0 if neutral else HOME_EDGE_PTS
    margin_home = (elo_diff / art["elo_pts_per_pt"]) + hca_pts

    home_poss = art["avg_poss"].get(home, art["league_avg_poss"])
    away_poss = art["avg_poss"].get(away, art["league_avg_poss"])
    pace_factor = (home_poss + away_poss) / (2.0 * art["league_avg_poss"])
    base_total = (
        art["team_avg_total"].get(home, art["league_avg_total"])
        + art["team_avg_total"].get(away, art["league_avg_total"])
    ) / 2.0
    total = base_total * pace_factor

    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    lb = art["leaderboard"]
    home_rank = next((i + 1 for i, (t, _) in enumerate(lb) if t == home), 0)
    away_rank = next((i + 1 for i, (t, _) in enumerate(lb) if t == away), 0)

    notes = (
        f"Elo(K=20,MOV): {home}#{home_rank}({r_home:.0f}) vs "
        f"{away}#{away_rank}({r_away:.0f}); "
        f"elo_diff={elo_diff:+.0f}(HCA={hca_elo_adj:.0f}Elo); "
        f"elo_pts_per_pt={art['elo_pts_per_pt']:.2f}; "
        f"margin={margin_home:+.1f} total={total:.1f} sd={art['margin_sd']:.2f}; "
        f"single-season 2025-26 only; "
        f"honesty_class=research; predicted corr-to-cluster r~0.70-0.85 (partial)"
    )

    return {
        "engine": "elo",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 2),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": round(art["margin_sd"], 2),
        "n_models": art["n_models"],
        "n_signals": art["n_signals"],
        "notes": notes,
    }


def _self_test() -> None:
    art = _build_ratings()
    lb = art["leaderboard"]
    rtgs = art["ratings"]

    print("=" * 60)
    print("ENGINE: elo  (Sequential Elo, K=20, MOV-mult, HCA=+100 Elo)")
    print("=" * 60)
    print(f"  elo_pts_per_pt (OLS)   : {art['elo_pts_per_pt']:.3f}")
    print(f"  margin_sd (in-sample)  : {art['margin_sd']:.3f} pts")
    print(f"  n_signals (games)      : {art['n_signals']}")
    print(f"  honesty_class          : research")

    print("\nLeaderboard top-5:")
    for rank, (t, r) in enumerate(lb[:5], 1):
        print(f"  #{rank:2d} {t}  {r:.1f}")
    print("  ...")
    nyk_rank = next(i + 1 for i, (t, _) in enumerate(lb) if t == "NYK")
    sas_rank = next(i + 1 for i, (t, _) in enumerate(lb) if t == "SAS")
    print(f"  NYK #{nyk_rank:2d}  {rtgs['NYK']:.1f}")
    print(f"  SAS #{sas_rank:2d}  {rtgs['SAS']:.1f}")

    r = predict("NYK", "SAS")
    print(f"\npredict(NYK, SAS):")
    for k, v in r.items():
        print(f"  {k:<18s} {v}")

    r2 = predict("SAS", "NYK")
    r3 = predict("NYK", "SAS", {"neutral_site": True})

    # Assertions
    assert abs(r["home_pts"] + r["away_pts"] - r["total"]) < 0.11
    assert abs(r["home_pts"] - r["away_pts"] - r["margin_home"]) < 0.11
    assert 0.01 <= r["win_prob_home"] <= 0.99
    assert r["margin_sd"] > 0
    hca_delta = r["margin_home"] - r3["margin_home"]
    assert 1.5 < hca_delta < 5.0, f"HCA delta unexpected: {hca_delta}"
    # SAS at home should flip win prob
    assert r2["win_prob_home"] > 0.5, "SAS home should be favored"

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
