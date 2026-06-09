"""Measure CLUTCH / close-game execution as a team-identity trait the average-possession sim misses.

The Monte Carlo scores every possession at average efficiency, so its win prob is the full-game
point distribution. But close playoff games (this series: G1 +10, G2 +1) are decided by late-game
execution. If a team is reliably better in the clutch, the model under-credits it in close games.
This sizes each team's clutch net (clutch_pts - clutch_opp), how often games reach clutch, the
clutch W-L record, and split-half stability -- to decide whether a (small, validated) close-game
win-prob tilt is warranted or whether clutch is too noisy to model.  ascii-only prints.
"""
import json, glob
import numpy as np
import pandas as pd

TG = "data/cache/team_system/team_game.parquet"
BOX = "data/cache/team_system/box"


def time_leading():
    """Fraction of game each team led, from boxscore 'timeLeading' (a game-control proxy)."""
    out = {}
    for f in glob.glob(f"{BOX}/*.json"):
        d = json.load(open(f)); g = d.get("game", d)
        for side in ("homeTeam", "awayTeam"):
            t = g[side]; tl = t.get("statistics", {}).get("timeLeading", "PT0M")
            import re
            m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", str(tl))
            mins = (float(m.group(1) or 0) + float(m.group(2) or 0) / 60.0) if m else 0.0
            out.setdefault(t["teamTricode"], []).append(mins)
    return out


def main():
    tg = pd.read_parquet(TG)
    tl = time_leading()
    # league clutch baseline
    cl = tg[(tg.clutch_pts + tg.clutch_opp) > 0]
    print(f"team-games={len(tg)}  reached clutch={len(cl)} ({100*len(cl)/len(tg):.0f}%)  "
          f"league clutch net/g={cl.clutch_pts.mean()-cl.clutch_opp.mean():+.2f}")
    for tri in ["NYK", "SAS"]:
        sub = tg[tg.team == tri].sort_values("date").reset_index(drop=True)
        c = sub[(sub.clutch_pts + sub.clutch_opp) > 0]
        net = c.clutch_pts.mean() - c.clutch_opp.mean()
        wins = (c.clutch_pts > c.clutch_opp).sum(); losses = (c.clutch_pts < c.clutch_opp).sum()
        # clutch W-L = the game-level result among games that reached clutch
        gw = (c.win == 1).sum(); gl = (c.win == 0).sum()
        # split-half stability of clutch net
        c2 = c.reset_index(drop=True)
        o = c2[c2.index % 2 == 0]; e = c2[c2.index % 2 == 1]
        no = o.clutch_pts.mean() - o.clutch_opp.mean(); ne = e.clutch_pts.mean() - e.clutch_opp.mean()
        print(f"\n=== {tri} ===  reached clutch {len(c)}/{len(sub)} games")
        print(f"  clutch pts for {c.clutch_pts.mean():.2f}  against {c.clutch_opp.mean():.2f}  NET {net:+.2f}/g"
              f"  (split-half {no:+.2f}/{ne:+.2f})")
        print(f"  clutch-segment won {wins}/lost {losses}  |  GAME record in clutch games {gw}-{gl} ({100*gw/(gw+gl):.0f}%)")
        print(f"  full-game record {(sub.win==1).sum()}-{(sub.win==0).sum()} ({100*(sub.win==1).mean():.0f}%)  "
              f"avg margin {(sub.pts-sub.opp_pts).mean():+.1f}  |  time leading/g {np.mean(tl.get(tri,[0])):.1f} min")


if __name__ == "__main__":
    main()
