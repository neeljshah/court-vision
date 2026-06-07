"""Clutch / close-game reconciliation layer (intelligence on top of the validated talent sim).

WHY: the possession Monte Carlo scores every possession at average efficiency, so its win prob is the
full-game point distribution -- it is blind to LATE-GAME execution. Measured full-season (measure_clutch.py),
NYK is the better clutch team and SAS the worse, *despite* SAS being the better team over 48 minutes:
  NYK clutch net +1.32/g, wins 63% of clutch segments;  SAS clutch net -1.02/g, wins 41%.
That gap is a stable team-IDENTITY trait (40-43 clutch games each, full season -- not 4-game H2H noise) and
it is the mechanism behind NYK's 2-0 series lead that the talent model structurally cannot see: SAS wins by
leading/blowout, but in a close game NYK executes better late. Against an evenly-matched playoff opponent,
games are close -- exactly where NYK's edge lives.

HOW: a small, shrunk MARGIN TILT applied ONLY to competitive simulated games (clutch is irrelevant in a
blowout), ramped by how close the game is. The core sim is unchanged and still validated; this only
re-reads the margin distribution it already produced. Honest limit: the underlying clutch TRAIT is
validated (stable split-half, large NYK>SAS gap), but the win-prob ADJUSTMENT itself cannot be graded
leak-free on only 4 NYK-vs-SAS games -- so it is conservative (heavy shrink) and reported, not folded
into the core win prob.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TG = os.path.join(ROOT, "data", "cache", "team_system", "team_game.parquet")

SHRINK = 0.6      # split-half clutch-net is noisy -> shrink the raw differential
COMPETITIVE = 8.0  # final |margin| <= this counts as "was decided late" (clutch-reachable)


def clutch_net(tri: str, tg: pd.DataFrame = None) -> float:
    """Full-season clutch net points/game (clutch_pts - clutch_opp) for games that reached clutch."""
    if tg is None:
        tg = pd.read_parquet(TG)
    sub = tg[tg.team == tri]
    c = sub[(sub.clutch_pts + sub.clutch_opp) > 0]
    if not len(c):
        return 0.0
    return float(c.clutch_pts.mean() - c.clutch_opp.mean())


def clutch_tilt(home_tri: str, away_tri: str, tg: pd.DataFrame = None) -> float:
    """Expected clutch margin shift toward HOME when these two play, shrunk. Each team's clutch net is
    measured vs league-average opponents, so the head-to-head differential is their difference."""
    diff = clutch_net(home_tri, tg) - clutch_net(away_tri, tg)
    return SHRINK * diff


def adjust_margin(margin: np.ndarray, tilt: float, competitive: float = COMPETITIVE) -> np.ndarray:
    """Apply the clutch tilt to competitive games only, ramped to zero by `competitive` margin.
    delta(m) = tilt * max(0, 1 - |m|/competitive). Blowouts are untouched."""
    ramp = np.clip(1.0 - np.abs(margin) / competitive, 0.0, 1.0)
    return margin + tilt * ramp


def clutch_adjusted_winprob(margin: np.ndarray, home_tri: str, away_tri: str, tg: pd.DataFrame = None):
    """Return (base_wp, adj_wp, tilt) for HOME from the sim's margin samples (HOME - AWAY)."""
    tilt = clutch_tilt(home_tri, away_tri, tg)
    base_wp = float((margin > 0).mean())
    adj_wp = float((adjust_margin(margin, tilt) > 0).mean())
    return base_wp, adj_wp, tilt


def _clutch_winrate(tri: str, tg: pd.DataFrame) -> float:
    """Share of clutch SEGMENTS this team won (clutch_pts > clutch_opp) -- a more stable view than net pts."""
    c = tg[(tg.team == tri) & ((tg.clutch_pts + tg.clutch_opp) > 0)]
    if not len(c):
        return 0.5
    return float((c.clutch_pts > c.clutch_opp).mean())


PREVIEW = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
MARK = ("<!-- SIGNALS:clutch-reconciliation START -->", "<!-- SIGNALS:clutch-reconciliation END -->")


def fold_warroom(home: str, away: str, base: float, adj: float, tilt: float, frac: float, tg: pd.DataFrame):
    if not os.path.exists(PREVIEW):
        return
    blk = (f"{MARK[0]}\n\n## Clutch & Series Reconciliation\n"
           f"*The possession sim scores every possession at average efficiency, so its win prob is blind to "
           f"LATE-GAME execution. Full-season clutch (last 5 min, margin <=5) is a stable team-identity trait "
           f"that reconciles the talent model (SAS-leaning) with the series reality (NYK 2-0).*\n\n"
           f"| | full-game | clutch net/g | clutch-segment W% | reads as |\n|---|---|---|---|---|\n"
           f"| **NYK** | 68% (+8.2) | **{clutch_net(home,tg):+.2f}** | **{_clutch_winrate(home,tg):.0%}** | good AND clutch |\n"
           f"| **SAS** | 73% (+8.4) | **{clutch_net(away,tg):+.2f}** | **{_clutch_winrate(away,tg):.0%}** | wins by leading, weaker late |\n\n"
           f"**The reconciliation:** SAS is the better team over 48 min (the model's SAS {1-base:.0%}), but NYK is "
           f"the better team in the clutch — and an evenly-matched playoff game is *close*, exactly where NYK's edge "
           f"lives. Applying a conservative, shrunk clutch margin tilt (+{tilt:.1f} pts toward NYK in the {frac:.0%} of "
           f"sims that stay competitive) lifts **NYK {base:.0%} -> {adj:.0%}**. The remaining gap to the series-implied "
           f"NYK favorite is the per-matchup edge the talent model cannot learn from only 4 H2H games (LOO-rejected).\n\n"
           f"> Honest limit: the clutch TRAIT is validated (full season, 40-43 clutch games each, stable, large NYK>SAS "
           f"gap); the win-prob ADJUSTMENT can't be graded leak-free on 4 NYK-vs-SAS games, so it is reported, not "
           f"folded into the core sim. Direction (toward NYK) is corroborated by the 2-0 series.\n\n{MARK[1]}")
    txt = open(PREVIEW, encoding="utf-8").read()
    import re
    if MARK[0] in txt:
        txt = re.sub(re.escape(MARK[0]) + r".*?" + re.escape(MARK[1]), blk, txt, flags=re.S)
    else:
        txt = txt.rstrip() + "\n\n" + blk + "\n"
    open(PREVIEW, "w", encoding="utf-8").write(txt)
    print(f"  folded ## Clutch & Series Reconciliation into {os.path.relpath(PREVIEW, ROOT)}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    tg = pd.read_parquet(TG)
    home, away = "NYK", "SAS"
    res = simulate_game_fast(TeamModel.from_cache(home), TeamModel.from_cache(away),
                             n_sims=40000, seed=2026, anchor=True, defense=True,
                             context={"neutral_site": False})
    margin = res.home_total - res.away_total
    base, adj, tilt = clutch_adjusted_winprob(margin, home, away, tg)
    frac = float((np.abs(margin) <= COMPETITIVE).mean())
    print(f"=== CLUTCH RECONCILIATION: {away} @ {home} ===")
    print(f"  clutch net/g: {home} {clutch_net(home,tg):+.2f}  {away} {clutch_net(away,tg):+.2f}  "
          f"-> shrunk tilt toward {home} {tilt:+.2f} pts in close games")
    print(f"  clutch-segment W%: {home} {_clutch_winrate(home,tg):.0%}  {away} {_clutch_winrate(away,tg):.0%}")
    print(f"  win prob {home}: talent-model {base:.0%}  ->  clutch-adjusted {adj:.0%}  ({frac:.0%} competitive sims)")
    fold_warroom(home, away, base, adj, tilt, frac, tg)
