"""Team DEFENSIVE traits (turnover-forcing, FT/foul environment, offensive rebounding) -> sim multipliers.

The film of NYK-SAS G1/G2 shows NYK's edge is forcing turnovers + offensive rebounding -- but the sim
only modeled defense suppressing MAKES (INTERIOR_D/PERIMETER_D), not forcing turnovers. This computes
each team's full-season DEFENSIVE turnover-forcing rate (opponent TOV% when they play this team) relative
to the league baseline, lightly shrunk. NYK forces 15.6% vs a 14.4% baseline (x1.08, stable split-half
15.1/16.1) -> applied to an opponent's turnover rate it predicts SAS ~15.5% TOV vs NYK (actual G1/G2 15.7%).

ALSO computes the DEFENSIVE FT/foul environment (`ft_force`): how much a team's defense inflates or
suppresses opponent free-throw RATE (opponent FTA / opponent FGA), opponent-adjusted and shrunk. The
sim modulated FT only by the offensive player's ft_share with NO defense -- yet this is a real, stable,
opponent-adjusted trait (validated leak-free in measure_ft_defense.py: it cuts opponent-FTA bias from
~+/-1.9 to ~+/-0.3 for both NYK and SAS). NYK ALLOWS more (x1.07: high shooting-foul D; the personal-foul
z-score is misleading) while SAS SUPPRESSES (x0.94: Wemby deters the rim -> blocks not fouls). Applied to
a player's FT scoring vs this defense -> SAS draws more FT at NYK, NYK draws fewer at SAS.

Output: data/cache/team_system/team_defense.parquet (team, tov_force, ft_force, oreb_strength, n)

  python scripts/team_system/build_team_defense.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")
K = 10.0     # light shrinkage toward 1.0 for tov/oreb (team rates stable over ~100 games)
K_FT = 8.0   # FT-defense shrinkage (slightly tighter; opponent-adjusted)


def _ft_force():
    """Per-team DEFENSIVE FT/foul-environment factor from boxscores: opponent FTA/FGA allowed,
    opponent-adjusted (vs each opponent's own offensive FTr) and shrunk toward 1.0. {team: (factor, raw)}."""
    rows = []
    for f in glob.glob(f"{BOX}/*.json"):
        d = json.load(open(f)); g = d.get("game", d)
        h, a = g["homeTeam"], g["awayTeam"]
        for me, opp in ((h, a), (a, h)):
            ms, os_ = me.get("statistics", {}), opp.get("statistics", {})
            try:
                rows.append((g["gameId"], me["teamTricode"], opp["teamTricode"],
                             ms["freeThrowsAttempted"], ms["fieldGoalsAttempted"],
                             os_["freeThrowsAttempted"], os_["fieldGoalsAttempted"]))
            except Exception:
                pass
    G = pd.DataFrame(rows, columns=["gid", "team", "opp", "fta", "fga", "opp_fta", "opp_fga"]).drop_duplicates(["gid", "team"])
    if not len(G):
        return {}
    league = G.fta.sum() / G.fga.sum()
    off_ftr = (G.groupby("team").fta.sum() / G.groupby("team").fga.sum()).to_dict()  # each team's OWN offensive FTr
    out = {}
    for t, sub in G.groupby("team"):
        n = len(sub)
        allowed = sub.opp_fta.sum() / sub.opp_fga.sum()
        exp = np.mean([off_ftr.get(o, league) for o in sub.opp]) or league   # expected opp FTr from opponent mix
        raw = allowed / exp
        w = n / (n + K_FT)
        out[t] = (round(1 + w * (raw - 1), 4), round(raw, 4))
    return out


def main():
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    base_tov = tg.opp_tov.sum() / tg.opp_poss.sum()          # league baseline opponent TOV rate
    ftf = _ft_force()
    rows = []
    for t, g in tg.groupby("team"):
        n = len(g)
        force_raw = (g.opp_tov.sum() / g.opp_poss.sum()) / base_tov          # >1 forces more turnovers
        oreb_raw = g.oreb.sum() / (g.oreb.sum() + g.opp_dreb.sum())          # offensive rebound rate
        w = n / (n + K)
        ft_force, ft_raw = ftf.get(t, (1.0, 1.0))
        rows.append({"team": t, "n": n,
                     "tov_force": round(1 + w * (force_raw - 1), 4),
                     "tov_force_raw": round(force_raw, 4),
                     "ft_force": ft_force, "ft_force_raw": ft_raw,
                     "oreb_strength": round(oreb_raw, 4)})
    df = pd.DataFrame(rows).sort_values("tov_force", ascending=False)
    df.to_parquet(os.path.join(TS, "team_defense.parquet"), index=False)
    print(f"DONE: {len(df)} teams; league baseline opp TOV% {base_tov*100:.1f}%  (shrink K={K:.0f}, K_FT={K_FT:.0f})")
    for r in df.itertuples():
        print(f"  {r.team}: tov_force {r.tov_force:.3f} (raw {r.tov_force_raw:.3f})  "
              f"ft_force {r.ft_force:.3f} (raw {r.ft_force_raw:.3f})  OREB% {r.oreb_strength*100:.1f}  n={r.n}")


if __name__ == "__main__":
    main()
