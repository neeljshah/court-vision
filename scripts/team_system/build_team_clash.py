"""TEAM CLASH — when team A faces team B, resolve the team-level metrics head-to-head.

The player matchup resolver (§13) + attribute clash (§13b) resolve the player layer. This resolves the
TEAM layer: each team's identity metric clashed against the other's, so the game-level numbers are
determined by the composition of the two teams' season identities (pace control, offense vs the other's
defense both ways, the turnover battle, the FT/foul environment, rim defense, the rebounding battle).

Uses clean numeric team rates (league_team_game season splits + TeamModel rim_d/perim_d/pace/ortg +
team_defense tov_force/ft_force). Folds `## Team Clash` into the War Room. Descriptive composition of the
validated team identities; the point/win-prob come from the sim (§8a).

  python scripts/team_system/build_team_clash.py [--home NYK --away SAS]
"""
from __future__ import annotations
import argparse, os, re, sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
WARROOM = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
S, E = "<!-- SIGNALS:team-clash START -->", "<!-- SIGNALS:team-clash END -->"


def _rates(lg, tri):
    d = lg[lg.team == tri]
    return {
        "off100": d.pts.sum() / max(d.poss.sum(), 1) * 100,
        "def100": d.opp_pts.sum() / max(d.opp_poss.sum(), 1) * 100,
        "own_tov": d.tov.sum() / max(d.poss.sum(), 1) * 100,
        "force_tov": d.opp_tov.sum() / max(d.opp_poss.sum(), 1) * 100,
        "pace": d.poss.mean(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    a = ap.parse_args()
    lg = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    H, A = _rates(lg, a.home), _rates(lg, a.away)
    hm, am = TeamModel.from_cache(a.home), TeamModel.from_cache(a.away)
    game_pace = (H["pace"] + A["pace"]) / 2

    def proj(off, deff):                       # projected pts/100 = blend of off's offense + opp's defense
        return (off["off100"] + deff["def100"]) / 2
    h_proj100, a_proj100 = proj(H, A), proj(A, H)
    poss = game_pace
    h_pts, a_pts = h_proj100 * poss / 100, a_proj100 * poss / 100

    def edge(label, hv, av, fmt="{:.1f}", higher_better=True, note=""):
        d = hv - av
        who = a.home if (d > 0) == higher_better else a.away
        mark = a.home if (d > 0) == higher_better else a.away
        return f"| {label} | {fmt.format(hv)} | {fmt.format(av)} | **{mark}**{(' ' + note) if note else ''} |"

    lines = [S, "", "## Team Clash — head-to-head identities resolved",
             f"*{a.away} @ {a.home}. Each team identity metric clashed against the other's; the game numbers "
             f"emerge from the composition of two season identities. Point/win-prob = the sim.*", "",
             "| metric | " + a.home + " | " + a.away + " | edge |", "|---|--:|--:|---|",
             edge("Pace (poss/48)", H["pace"], A["pace"], note=f"-> game ~{game_pace:.0f}"),
             edge("Offense (pts/100)", H["off100"], A["off100"]),
             edge("Defense (pts allowed/100)", H["def100"], A["def100"], higher_better=False),
             f"| Proj. pts (off vs opp D) | {h_pts:.1f} | {a_pts:.1f} | **{a.home if h_pts>a_pts else a.away}** |",
             edge("Forces TOV (opp tov%)", H["force_tov"], A["force_tov"]),
             edge("Own TOV% (lower better)", H["own_tov"], A["own_tov"], higher_better=False),
             edge("Rim defense (0-99)", getattr(hm, "rim_d", 50), getattr(am, "rim_d", 50)),
             edge("Perimeter defense (0-99)", getattr(hm, "perim_d", 50), getattr(am, "perim_d", 50)),
             edge("TOV-force mult", getattr(hm, "tov_force", 1), getattr(am, "tov_force", 1), fmt="{:.3f}"),
             edge("FT-allowed mult (lower=suppress)", getattr(hm, "ft_force", 1), getattr(am, "ft_force", 1),
                  fmt="{:.3f}", higher_better=False)]
    # narrative read
    reads = []
    if H["force_tov"] - A["own_tov"] > 0.8:
        reads.append(f"{a.home} TO-forcing ({H['force_tov']:.1f}%) vs {a.away} ball security ({A['own_tov']:.1f}%) = {a.home} wins the turnover battle")
    if getattr(am, "rim_d", 50) - getattr(hm, "rim_d", 50) > 4:
        reads.append(f"{a.away} rim D ({getattr(am,'rim_d',0):.0f}) >> {a.home} ({getattr(hm,'rim_d',0):.0f}) -> {a.home} interior scoring suppressed")
    if getattr(am, "ft_force", 1) < 0.97:
        reads.append(f"{a.away} suppresses FT ({getattr(am,'ft_force',1):.3f}) -> {a.home} foul-drawing muted")
    if getattr(hm, "ft_force", 1) > 1.03:
        reads.append(f"{a.home} allows more FT ({getattr(hm,'ft_force',1):.3f}) -> {a.away} gets to the line")
    lines += ["", "**Read:** " + " · ".join(reads) if reads else "", "",
              f"*Composition of the two season identities; the sim resolves the point estimate "
              f"(projected ~{h_pts:.0f}-{a_pts:.0f} from identities alone, before clutch/availability).*", "", E, ""]
    block = "\n".join([l for l in lines if l is not None])

    if os.path.exists(WARROOM):
        txt = open(WARROOM, encoding="utf-8").read()
        txt = re.sub(re.escape(S) + r".*?" + re.escape(E), block, txt, flags=re.S) if (S in txt and E in txt) \
            else txt.rstrip() + "\n\n" + block + "\n"
        open(WARROOM, "w", encoding="utf-8").write(txt)
        print(f"folded ## Team Clash into the War Room ({a.away} @ {a.home}). proj ~{h_pts:.0f}-{a_pts:.0f}, pace {game_pace:.0f}")
    else:
        print(block[:1500])


if __name__ == "__main__":
    main()
