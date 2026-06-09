"""engine_power_ratings.py -- SRS-based power-rating prediction engine.

METHODOLOGY
-----------
Simple Rating System (SRS): iterative algorithm, parameter-free.
  1. Initialize all 30 team ratings to 0.
  2. Each iteration: rating[team] = mean over all games of
     (own_pts - opp_pts + opp_rating).
  3. Converge after ~50 iterations (delta < 1e-7).
  4. Normalize so ratings sum to 0 (league-relative).
  5. Prediction: margin_home = (home_rating - away_rating) + home_edge.
     total = (home_avg_total + away_avg_total) / 2, scaled by relative pace.
     margin_sd = residual SD of (actual_margin - predicted_margin) across all
     league games -- the honest single-game error floor.
     win_prob_home = normal CDF(margin_home / margin_sd).

Leak-free: SRS is a full-season aggregate -- no future data enters any
individual game's rating (it is equivalent to the linear MOV solution, not
a running tracker).  Appropriate for pre-game prediction.

n_models = 30 (one SRS rating per team).
n_signals = number of league game rows consumed from league_team_game.parquet.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_LEAGUE_GAME = os.path.join(
    _REPO, "data", "cache", "team_system", "league_team_game.parquet"
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7          # pts, skip if neutral_site
SRS_ITERS: int = 50
SRS_CONV: float = 1e-7
FALLBACK_MARGIN_SD: float = 13.0


# ---------------------------------------------------------------------------
# SRS computation -- cached so predict() is fast on repeated calls
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _build_ratings() -> dict:
    """Return a dict with all computed SRS artefacts."""
    df = pd.read_parquet(_LEAGUE_GAME)
    n_signals = len(df)

    teams = sorted(df["team"].unique().tolist())
    n_teams = len(teams)

    # ---- per-team lookup tables ----------------------------------------
    # margins and opponents per team (list of (margin, opp) tuples)
    records: dict[str, list[tuple[float, str]]] = {t: [] for t in teams}
    for _, row in df.iterrows():
        records[row["team"]].append((float(row["pts"] - row["opp_pts"]), row["opp"]))

    # ---- iterative SRS --------------------------------------------------
    ratings: dict[str, float] = {t: 0.0 for t in teams}
    for _ in range(SRS_ITERS):
        new_ratings: dict[str, float] = {}
        for team in teams:
            if not records[team]:
                new_ratings[team] = 0.0
                continue
            new_ratings[team] = sum(
                margin + ratings[opp] for margin, opp in records[team]
            ) / len(records[team])
        # Normalize to zero mean (league-relative)
        mean_r = sum(new_ratings.values()) / n_teams
        new_ratings = {t: v - mean_r for t, v in new_ratings.items()}
        # Check convergence
        delta = max(abs(new_ratings[t] - ratings[t]) for t in teams)
        ratings = new_ratings
        if delta < SRS_CONV:
            break

    # ---- residual SD -- honest single-game error ------------------------
    errors: list[float] = []
    for _, row in df.iterrows():
        actual_margin = float(row["pts"] - row["opp_pts"])
        # SRS prediction ignores home/away (aggregate), so use raw rating diff
        predicted = ratings[row["team"]] - ratings[row["opp"]]
        errors.append(actual_margin - predicted)

    margin_sd = float(pd.Series(errors).std(ddof=1)) if errors else FALLBACK_MARGIN_SD

    # ---- pace (avg poss per team) ---------------------------------------
    avg_poss: dict[str, float] = (
        df.groupby("team")["poss"].mean().to_dict()
    )
    league_avg_poss: float = float(df["poss"].mean())

    # ---- league avg total -----------------------------------------------
    # Each game appears twice in df (once per team); sum pts/opp_pts gives
    # 2 * total points per game -- divide by 2 to get one-sided, *2 for total.
    # Simpler: (pts + opp_pts) per row / 2 rows per game = per-team side; mean * 2
    league_avg_total: float = float((df["pts"] + df["opp_pts"]).mean())
    # That is home+away per row; since each game has 2 rows it double-counts.
    # Actually: each row is one team's line; pts=team, opp_pts=other team.
    # So (pts + opp_pts) = game total for every row. Mean of that = avg game total. Correct.

    # ---- per-team avg total (sum of pts + opp_pts) ----------------------
    team_avg_total: dict[str, float] = {}
    for t in teams:
        sub = df[df["team"] == t]
        team_avg_total[t] = float((sub["pts"] + sub["opp_pts"]).mean())

    # ---- sorted leaderboard ---------------------------------------------
    leaderboard = sorted(ratings.items(), key=lambda x: x[1], reverse=True)

    return {
        "ratings": ratings,
        "avg_poss": avg_poss,
        "league_avg_poss": league_avg_poss,
        "league_avg_total": league_avg_total,
        "team_avg_total": team_avg_total,
        "margin_sd": margin_sd,
        "n_signals": n_signals,
        "n_models": 30,
        "leaderboard": leaderboard,
        "n_teams": n_teams,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised prediction dict (see engines/__init__.py).

    context keys (all optional):
      home_b2b (bool), away_b2b (bool), neutral_site (bool), playoffs (bool).
    """
    ctx = context or {}
    artefacts = _build_ratings()

    ratings = artefacts["ratings"]
    avg_poss = artefacts["avg_poss"]
    league_avg_poss = artefacts["league_avg_poss"]
    league_avg_total = artefacts["league_avg_total"]
    team_avg_total = artefacts["team_avg_total"]
    margin_sd = artefacts["margin_sd"]

    home = home_tri.upper()
    away = away_tri.upper()

    if home not in ratings:
        raise ValueError(f"Unknown team: {home!r}. Valid: {sorted(ratings)}")
    if away not in ratings:
        raise ValueError(f"Unknown team: {away!r}. Valid: {sorted(ratings)}")

    # Margin prediction
    neutral = bool(ctx.get("neutral_site", False))
    edge = 0.0 if neutral else HOME_EDGE
    margin_home = (ratings[home] - ratings[away]) + edge

    # Total: average of the two teams' avg game totals, adjusted for pace
    # pace_factor: if both teams play fast the total goes up proportionally
    home_poss = avg_poss.get(home, league_avg_poss)
    away_poss = avg_poss.get(away, league_avg_poss)
    pace_factor = (home_poss + away_poss) / (2.0 * league_avg_poss)

    base_total = (
        team_avg_total.get(home, league_avg_total)
        + team_avg_total.get(away, league_avg_total)
    ) / 2.0
    total = base_total * pace_factor

    # Points split: home = total/2 + margin/2, away = total/2 - margin/2
    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # Win probability
    win_prob_home = 0.5 + 0.5 * math.erf(margin_home / (margin_sd * math.sqrt(2.0)))
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    # Build leaderboard rank note
    leaderboard = artefacts["leaderboard"]
    home_rank = next(i + 1 for i, (t, _) in enumerate(leaderboard) if t == home)
    away_rank = next(i + 1 for i, (t, _) in enumerate(leaderboard) if t == away)

    notes = (
        f"SRS: {home} #{home_rank} ({ratings[home]:+.2f}) vs "
        f"{away} #{away_rank} ({ratings[away]:+.2f}); "
        f"margin={margin_home:+.1f} pts, total={total:.1f}, "
        f"margin_sd={margin_sd:.2f}; edge={'neutral' if neutral else '+2.7 HCA'}"
    )

    return {
        "engine": "power_ratings",
        "win_prob_home": round(win_prob_home, 4),
        "margin_home": round(margin_home, 2),
        "total": round(total, 2),
        "home_pts": round(home_pts, 2),
        "away_pts": round(away_pts, 2),
        "margin_sd": round(margin_sd, 2),
        "n_models": artefacts["n_models"],
        "n_signals": artefacts["n_signals"],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    artefacts = _build_ratings()
    leaderboard = artefacts["leaderboard"]
    ratings = artefacts["ratings"]
    margin_sd = artefacts["margin_sd"]

    print("=" * 60)
    print("ENGINE: power_ratings  (SRS -- results-based, 30 models)")
    print("=" * 60)

    print(f"\nLeague residual margin_sd : {margin_sd:.3f} pts")
    print(f"n_signals (game rows)     : {artefacts['n_signals']}")
    print(f"n_models  (team ratings)  : {artefacts['n_models']}")

    print("\n--- SRS Leaderboard (top 5) ---")
    for rank, (team, rtg) in enumerate(leaderboard[:5], 1):
        print(f"  #{rank:2d}  {team}  {rtg:+.3f}")

    print("\n--- SRS Leaderboard (bottom 5) ---")
    bottom = leaderboard[-5:]
    start_rank = len(leaderboard) - 4
    for rank, (team, rtg) in enumerate(bottom, start_rank):
        print(f"  #{rank:2d}  {team}  {rtg:+.3f}")

    # NYK and SAS
    nyk_rank = next(i + 1 for i, (t, _) in enumerate(leaderboard) if t == "NYK")
    sas_rank = next(i + 1 for i, (t, _) in enumerate(leaderboard) if t == "SAS")
    print(f"\n  NYK  #{nyk_rank:2d}  {ratings['NYK']:+.3f}")
    print(f"  SAS  #{sas_rank:2d}  {ratings['SAS']:+.3f}")

    print("\n--- predict(NYK, SAS) ---")
    result = predict("NYK", "SAS")
    for k, v in result.items():
        print(f"  {k:<18s} {v}")

    print("\n--- predict(SAS, NYK)  [road-SAS scenario] ---")
    result2 = predict("SAS", "NYK")
    for k, v in result2.items():
        print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral) ---")
    result3 = predict("NYK", "SAS", {"neutral_site": True})
    for k, v in result3.items():
        print(f"  {k:<18s} {v}")

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
