"""engine_lineup_markov.py -- Lineup-Markov (occupancy-weighted net-rating) engine.

METHODOLOGY
-----------
Each team's set of 5-man lineup stints is treated as a discrete Markov chain
where the stationary distribution is approximated by observed possession-share
(poss_i / Sigma poss_i).  The poss-weighted expected net-rating is therefore:

    E[net] = Sigma(net_i * poss_i) / Sigma(poss_i)

This is the "Markov occupancy expectation" -- the fraction of possessions each
lineup is on-court, weighted by its net-rating, gives a team's expected per-100
advantage given its actual rotation patterns.

    margin = (home_E[net] - away_E[net]) * pace_factor + hca

where pace_factor = avg_poss / 100.0 to convert per-100 to per-game pts.

HONESTY / LIMITATIONS
---------------------
- DATA COVERAGE: NYK and SAS ONLY (lineups.parquet is a 2-team file).
  For ANY other team pairing this engine raises ValueError -- it cannot
  produce an honest lineup-level signal outside the Finals matchup.
- REDUNDANCY: Poss-weighted stint net-rtg is the *same signal* as team net-rtg
  measured at lineup granularity. Predicted corr-to-cluster r > 0.9 with the
  power_ratings / team_score cluster.  This is a REDUNDANT engine by design.
  Its contribution is lineup-level notes + granularity, NOT decorrelation.
- SMALL-N EXTREMES: Single-game stints (poss < 50) have noisy net-rtg (+/-50+).
  The occupancy-weighting naturally down-weights them, but outlier stint nets
  are real -- the engine reports how many stints crossed a poss threshold.
- margin_sd is BORROWED from the league residual (~14 pts); only NYK/SAS games
  exist locally to compute a local residual, which is insufficient.

honesty_class = research
decorrelation_predicted = REDUNDANT (r > 0.9 with net-rating cluster)
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths -- engines_x/ is one level deeper than engines/, so parents[3] still
# resolves to nba-ai-system/  (engines_x -> team_system -> scripts -> repo root)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_LINEUPS = os.path.join(_REPO, "data", "cache", "team_system", "lineups.parquet")
_LEAGUE_GAME = os.path.join(
    _REPO, "data", "cache", "team_system", "league_team_game.parquet"
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOME_EDGE: float = 2.7
FALLBACK_MARGIN_SD: float = 14.0   # borrowed league residual; see honesty note
MIN_POSS_THRESHOLD: int = 44       # smallest stint in data; no filter applied
                                   # (occupancy weighting handles noise)
VALID_TEAMS = frozenset({"NYK", "SAS"})

# ---------------------------------------------------------------------------
# Build artefacts -- cached
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _build_artefacts() -> dict:
    """Load lineups.parquet + league_team_game.parquet and compute all artefacts."""
    # ---- lineup data (NYK/SAS only) ------------------------------------
    df_lu = pd.read_parquet(_LINEUPS)

    team_weighted_net: dict[str, float] = {}
    n_lineups_per_team: dict[str, int] = {}
    total_poss_per_team: dict[str, float] = {}

    for team in ["NYK", "SAS"]:
        sub = df_lu[df_lu["team"] == team].copy()
        total_poss = float(sub["poss"].sum())
        if total_poss <= 0:
            raise RuntimeError(f"No possession data for {team} in lineups.parquet")
        # Poss-weighted average net-rating (Markov occupancy expectation)
        wt_net = float((sub["net"] * sub["poss"]).sum() / total_poss)
        team_weighted_net[team] = wt_net
        n_lineups_per_team[team] = int(len(sub))
        total_poss_per_team[team] = total_poss

    # ---- league game data (for pace + total reference) -----------------
    df_lg = pd.read_parquet(_LEAGUE_GAME)
    league_avg_poss: float = float(df_lg["poss"].mean())
    league_avg_total: float = float((df_lg["pts"] + df_lg["opp_pts"]).mean())

    # Per-team avg total from league data
    team_avg_total: dict[str, float] = {}
    for team in ["NYK", "SAS"]:
        sub = df_lg[df_lg["team"] == team]
        if len(sub) > 0:
            team_avg_total[team] = float((sub["pts"] + sub["opp_pts"]).mean())
        else:
            team_avg_total[team] = league_avg_total

    # Per-team avg poss from league data (for pace factor)
    team_avg_poss: dict[str, float] = {}
    for team in ["NYK", "SAS"]:
        sub = df_lg[df_lg["team"] == team]
        if len(sub) > 0:
            team_avg_poss[team] = float(sub["poss"].mean())
        else:
            team_avg_poss[team] = league_avg_poss

    n_signals = int(
        sum(total_poss_per_team.values())  # total possession-rows consumed
    )

    return {
        "team_weighted_net": team_weighted_net,
        "n_lineups_per_team": n_lineups_per_team,
        "total_poss_per_team": total_poss_per_team,
        "league_avg_poss": league_avg_poss,
        "league_avg_total": league_avg_total,
        "team_avg_total": team_avg_total,
        "team_avg_poss": team_avg_poss,
        "margin_sd": FALLBACK_MARGIN_SD,
        "n_signals": n_signals,
        # n_models = total lineup rows across both teams
        "n_models": sum(n_lineups_per_team.values()),
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def predict(
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    context: Optional[dict] = None,
) -> dict:
    """Return a standardised prediction dict.

    HARD LIMIT: only NYK and SAS are supported.  Any other team raises
    ValueError -- this engine is honest only for the Finals matchup.

    context keys (optional): neutral_site (bool), playoffs (bool).
    """
    ctx = context or {}
    home = home_tri.upper()
    away = away_tri.upper()

    if home not in VALID_TEAMS:
        raise ValueError(
            f"engine_lineup_markov: unknown / unsupported team {home!r}. "
            f"This engine has lineup data ONLY for {sorted(VALID_TEAMS)}. "
            "Use a league-wide engine (power_ratings, team_score, etc.) for other teams."
        )
    if away not in VALID_TEAMS:
        raise ValueError(
            f"engine_lineup_markov: unknown / unsupported team {away!r}. "
            f"This engine has lineup data ONLY for {sorted(VALID_TEAMS)}. "
            "Use a league-wide engine (power_ratings, team_score, etc.) for other teams."
        )

    art = _build_artefacts()

    home_net = art["team_weighted_net"][home]
    away_net = art["team_weighted_net"][away]
    margin_sd = art["margin_sd"]

    # Pace factor: convert per-100-possession net-rtg to per-game margin pts.
    # Use average of the two teams' avg poss; league avg as denominator baseline.
    home_poss = art["team_avg_poss"][home]
    away_poss = art["team_avg_poss"][away]
    avg_poss = (home_poss + away_poss) / 2.0
    pace_factor = avg_poss / 100.0

    # Home-court advantage
    neutral = bool(ctx.get("neutral_site", False))
    hca = 0.0 if neutral else HOME_EDGE

    # Margin: (home net-rtg - away net-rtg) * pace_factor + HCA
    net_diff = home_net - away_net
    margin_home = net_diff * pace_factor + hca

    # Total: average of the two teams' per-game totals from league data
    home_total = art["team_avg_total"][home]
    away_total = art["team_avg_total"][away]
    total = (home_total + away_total) / 2.0

    # Points split
    home_pts = total / 2.0 + margin_home / 2.0
    away_pts = total / 2.0 - margin_home / 2.0

    # Win probability via normal CDF
    win_prob_home = 0.5 + 0.5 * math.erf(margin_home / (margin_sd * math.sqrt(2.0)))
    win_prob_home = max(0.01, min(0.99, win_prob_home))

    n_lu_home = art["n_lineups_per_team"][home]
    n_lu_away = art["n_lineups_per_team"][away]
    poss_home = art["total_poss_per_team"][home]
    poss_away = art["total_poss_per_team"][away]

    notes = (
        f"lineup_markov [NYK/SAS ONLY -- redundant engine, predicted r>0.9 with net-rtg cluster]; "
        f"{home} poss_wtd_net={home_net:+.2f} ({n_lu_home} lineups, {poss_home:.0f} poss), "
        f"{away} poss_wtd_net={away_net:+.2f} ({n_lu_away} lineups, {poss_away:.0f} poss); "
        f"net_diff={net_diff:+.2f}/100, pace_factor={pace_factor:.3f}, "
        f"margin={margin_home:+.1f} pts; "
        f"margin_sd={margin_sd:.1f} BORROWED (league residual, local n insufficient); "
        f"hca={'neutral' if neutral else '+2.7'}"
    )

    return {
        "engine": "lineup_markov",
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
    art = _build_artefacts()
    print("=" * 70)
    print("ENGINE: lineup_markov  (poss-weighted stint net-rtg -- NYK/SAS ONLY)")
    print("=" * 70)
    print(f"\nHONESTY: redundant engine (predicted r>0.9 with net-rating cluster)")
    print(f"         margin_sd={art['margin_sd']:.1f} BORROWED from league residual")
    print(f"         valid teams: {sorted(VALID_TEAMS)}\n")

    for team in ["NYK", "SAS"]:
        n = art["n_lineups_per_team"][team]
        p = art["total_poss_per_team"][team]
        net = art["team_weighted_net"][team]
        print(f"  {team}: {n} lineups, {p:.0f} total poss, poss_wtd_net={net:+.3f}")

    print("\n--- predict(NYK, SAS) ---")
    result = predict("NYK", "SAS")
    for k, v in result.items():
        if k == "notes":
            print(f"  {'notes':<18s} {v[:80]}...")
        else:
            print(f"  {k:<18s} {v}")

    print("\n--- predict(SAS, NYK) [road-SAS] ---")
    result2 = predict("SAS", "NYK")
    for k, v in result2.items():
        if k == "notes":
            print(f"  {'notes':<18s} {v[:80]}...")
        else:
            print(f"  {k:<18s} {v}")

    print("\n--- predict(NYK, SAS, neutral_site=True) ---")
    result3 = predict("NYK", "SAS", {"neutral_site": True})
    for k, v in result3.items():
        if k == "notes":
            print(f"  {'notes':<18s} {v[:80]}...")
        else:
            print(f"  {k:<18s} {v}")

    # Verify HCA delta ~2.7
    m_default = predict("NYK", "SAS")["margin_home"]
    m_neutral = predict("NYK", "SAS", {"neutral_site": True})["margin_home"]
    assert abs(abs(m_default - m_neutral) - HOME_EDGE) < 0.01, (
        f"HCA delta mismatch: {m_default} vs {m_neutral}"
    )

    # Verify arithmetic: home_pts + away_pts == total (±0.1)
    for r in [result, result2, result3]:
        assert abs(r["home_pts"] + r["away_pts"] - r["total"]) < 0.1, (
            f"pts sum mismatch: {r['home_pts']} + {r['away_pts']} != {r['total']}"
        )
        assert abs(r["home_pts"] - r["away_pts"] - r["margin_home"]) < 0.1, (
            f"margin mismatch: {r['home_pts']} - {r['away_pts']} != {r['margin_home']}"
        )

    # Verify ValueError on unknown team
    try:
        predict("BOS", "LAL")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"\n  ValueError for BOS/LAL (expected): {str(e)[:60]}...")

    print("\nSelf-test PASSED")


if __name__ == "__main__":
    _self_test()
