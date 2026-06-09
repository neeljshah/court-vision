"""MATCHUP RESOLVER — when team A faces team B, resolve EVERY player metric from the composition.

The thesis: a prediction is not one number from one model -- it is many per-entity models composing.
This makes that composition EXPLICIT for a specific matchup. For each rotation player it resolves the
scoring projection as a decomposition the eye can follow:

    base (recency-blended season) -> x matchup-DEFENSE (opp rim_d/perim_d weighted by his shot diet)
      -> x FT environment (opp foul tendency x his FT reliance) -> x home/road -> = projection

and layers the per-entity CONTEXT SPINE (descriptive matchup intelligence, not double-counted into the
number): this opponent's defense TIER x his vs-tier eFG sensitivity, the rest situation x his B2B
sensitivity, the game pace x his pace sensitivity, and the likely primary defender. The validated point
projection is the anchored sim (predict path); this layer shows WHY and HOW the matchup shapes it, and
surfaces the matchup-specific tilts the marginal can't.

Folds `## Matchup Resolution` into the War Room. Leak-free (season/recency snapshot + opponent identity).
Honest: the composed point is the sim's; the spine effects are scouting intelligence (EDGE_GATE: vs-opp/
pace are not standalone marginal edges) -- they sharpen the matchup READ and the sim's joint/shape.

  python scripts/team_system/build_matchup_resolution.py [--home NYK --away SAS]
"""
from __future__ import annotations
import argparse, os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel, _matchup_mult, RECENCY_W  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
WARROOM = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
S, E = "<!-- SIGNALS:matchup-resolution START -->", "<!-- SIGNALS:matchup-resolution END -->"


def _def_tier(team_def, opp_tri):
    vals = list(team_def.values()); q1, q3 = np.quantile(vals, [1/3, 2/3])
    d = team_def.get(opp_tri)
    if d is None:
        return "avg", None
    return ("TOUGH" if d <= q1 else "WEAK" if d >= q3 else "avg"), d


def _pts_base(r):
    rec = r.get("pts_pg_rec")
    return (1 - RECENCY_W) * r["pts_pg"] + RECENCY_W * rec if rec is not None else r["pts_pg"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    a = ap.parse_args()
    home, away = TeamModel.from_cache(a.home), TeamModel.from_cache(a.away)
    res = simulate_game_fast(home, away, n_sims=15000, seed=7, anchor=True, defense=True,
                             context={"neutral_site": False})

    lg = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    _ag = lg.groupby("team").agg(oa=("opp_pts", "sum"), op=("opp_poss", "sum"))
    team_def = (_ag["oa"] / _ag["op"].clip(lower=1) * 100).to_dict()
    try:
        spine = pd.read_parquet(os.path.join(TS, "player_effects_full.parquet")).set_index("pid")
    except Exception:
        spine = None

    lines = [S, "", "## Matchup Resolution — every metric, composed",
             f"*{a.away} @ {a.home}. Each player's scoring projection decomposed: base (recency-blended "
             f"season) -> x matchup-defense -> x FT environment -> = projection, with the per-entity context "
             f"spine (opp defense tier, pace, rest, defender) layered as matchup intelligence. One sim, every "
             f"model composing. Validated point = the anchored sim; spine = scouting tilt.*", ""]

    for off, deff, label in ((home, away, a.home), (away, home, a.away)):
        opp_tri = deff.tri
        tier, drtg = _def_tier(team_def, opp_tri)
        lines += ["", f"### {label} vs {opp_tri} defense ({tier} D" + (f", {drtg:.1f} pts/100)" if drtg else ")"),
                  "", "| player | base | xDef | xFT | proj | vs-tier | pace | matchup read |",
                  "|---|--:|--:|--:|--:|--:|--:|---|"]
        rot = [p for p in off.rate if (off.rate[p].get("mpg", 0) or 0) >= 15]
        rot.sort(key=lambda p: -(res.players[p]["mean"]["pts"] if p in res.players else 0))
        for pid in rot:
            r = off.rate[pid]
            base = _pts_base(r)
            mdef = _matchup_mult(r, deff, True)
            ft_fac = 1.0 + (r.get("ft_pts_share", 0.0) or 0.0) * (getattr(deff, "ft_force", 1.0) - 1.0)
            proj = res.players[pid]["mean"]["pts"] if pid in res.players else base * mdef
            # context spine
            vt = pace = ""
            read = []
            if spine is not None and pid in spine.index:
                s = spine.loc[pid]
                vtx = s.vs_strongD_xfg if tier == "TOUGH" else s.vs_weakD_xfg if tier == "WEAK" else 1.0
                vt = f"x{vtx:.3f}"
                pace = f"x{s.fast_xfg:.3f}"
                if tier == "TOUGH" and s.matchup_sensitivity > 0.06:
                    read.append("matchup-sensitive -> elite D dampens him")
                elif tier == "WEAK" and s.matchup_sensitivity > 0.06:
                    read.append("feasts on weak D")
                if s.b2b_xfg < 0.97:
                    read.append("rest-sensitive (fades on B2B)")
            if mdef < 0.97:
                read.append(f"shot diet hit by {opp_tri} D (x{mdef:.3f})")
            elif mdef > 1.03:
                read.append(f"shot diet exploits {opp_tri} D (x{mdef:.3f})")
            if ft_fac > 1.02:
                read.append("draws extra FT here")
            elif ft_fac < 0.98:
                read.append("FT suppressed here")
            name = r.get("player", str(pid))[:18]
            lines.append(f"| {name} | {base:.1f} | {mdef:.3f} | {ft_fac:.3f} | **{proj:.1f}** | {vt} | "
                         f"{pace} | {'; '.join(read) or '-'} |")

    lines += ["", f"*Resolver composes: rates + roles + 87-attr vault + ratings + per-shot defense + ft_force "
              f"+ home/road + recency + the context spine. Team totals/win-prob from the same sim "
              f"({res.home_total.mean():.0f}-{res.away_total.mean():.0f}, {a.home} win {res.home_win_prob:.0%}).*",
              "", E, ""]
    block = "\n".join(lines)

    if os.path.exists(WARROOM):
        import re
        txt = open(WARROOM, encoding="utf-8").read()
        if S in txt and E in txt:
            txt = re.sub(re.escape(S) + r".*?" + re.escape(E), block, txt, flags=re.S)
        else:
            txt = txt.rstrip() + "\n\n" + block + "\n"
        open(WARROOM, "w", encoding="utf-8").write(txt)
        print(f"folded ## Matchup Resolution into the War Room ({a.away} @ {a.home}).")
    else:
        print("War Room not found; resolution block:\n")
        print(block[:1500])


if __name__ == "__main__":
    main()
