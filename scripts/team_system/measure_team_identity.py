"""Measure candidate TEAM-IDENTITY signals the possession sim may be missing.

The sim fixes #possessions at average pace and makes a forced turnover simply end the opponent's
possession at 0 pts -- it does NOT give the forcing team the high-value TRANSITION bucket off the
steal, nor model second-chance/paint efficiency edges beyond raw OREB. This sizes each candidate
from full-season boxscores (for/against/net), checks split-half stability, and compares NYK vs SAS
so we build only the one with a real, stable, non-double-counted edge.  ascii-only prints.
"""
import json, glob
import numpy as np
import pandas as pd

BOX = "data/cache/team_system/box"
CATS = ["pointsFastBreak", "pointsFromTurnovers", "pointsSecondChance", "pointsInThePaint", "benchPoints"]


def load():
    rows = []
    for f in glob.glob(f"{BOX}/*.json"):
        d = json.load(open(f)); g = d.get("game", d)
        h, a = g["homeTeam"], g["awayTeam"]
        for me, opp in ((h, a), (a, h)):
            ms, os_ = me.get("statistics", {}), opp.get("statistics", {})
            try:
                r = dict(gid=g["gameId"], date=g.get("gameEt", "")[:10],
                         team=me["teamTricode"], opp=opp["teamTricode"], poss=None,
                         pts=ms["points"], opp_pts=os_["points"])
                for c in CATS:
                    r[c] = ms.get(c, np.nan); r["opp_" + c] = os_.get(c, np.nan)
                rows.append(r)
            except Exception:
                pass
    return pd.DataFrame(rows).drop_duplicates(["gid", "team"])


def main():
    G = load()
    print(f"rows={len(G)}  teams={G.team.nunique()}")
    # league average per category (per game) for context
    print("\nLeague avg per game:  " + "  ".join(f"{c.replace('points','').replace('From','fr').replace('Fast','fb')[:9]}={G[c].mean():.1f}" for c in CATS))
    for tri in ["NYK", "SAS"]:
        sub = G[G.team == tri].sort_values("date").reset_index(drop=True)
        print(f"\n=== {tri}  n={len(sub)} ===")
        for c in CATS:
            net = sub[c].mean() - sub["opp_" + c].mean()
            lg_net = G[c].mean() - G["opp_" + c].mean()
            edge = net - lg_net
            # split-half stability of the NET
            s2 = sub.reset_index(drop=True)
            odd = s2[s2.index % 2 == 0]; even = s2[s2.index % 2 == 1]
            net_o = odd[c].mean() - odd["opp_" + c].mean(); net_e = even[c].mean() - even["opp_" + c].mean()
            print(f"  {c:22s} for {sub[c].mean():5.1f}  agst {sub['opp_'+c].mean():5.1f}  NET {net:+5.1f}"
                  f"  (lg net {lg_net:+4.1f} -> edge vs lg {edge:+4.1f})  split-half net {net_o:+4.1f}/{net_e:+4.1f}")


if __name__ == "__main__":
    main()
