"""Measure + leak-free validate the DEFENSIVE free-throw-allowed trait (foul environment).

Question: does a team's defense systematically inflate/suppress how often opponents get to the
line (opponent FTA / opponent FGA), as a STABLE, opponent-adjusted, predictive trait the sim
should model? The sim currently modulates FT only by the offensive player's ft_share (no defense).

Leak-free test (leave-one-game-out): predict each NYK/SAS game's opponent FTA two ways and grade
against the real opponent FTA:
  baseline:  exp_FTr * opp_FGA            (no defense info; exp_FTr = opponent's own FTr from OTHER games)
  +ft_force: exp_FTr * opp_FGA * force    (force = defending team's opp-FTr-allowed factor, LOO)
If +ft_force lowers MAE/bias out of sample, the trait is real and predictive.
ascii-only prints (Windows cp1252).
"""
import json, glob
import numpy as np
import pandas as pd

BOX = "data/cache/team_system/box"


def load():
    rows = []
    for f in glob.glob(f"{BOX}/*.json"):
        d = json.load(open(f)); g = d.get("game", d)
        h, a = g["homeTeam"], g["awayTeam"]
        for me, opp in ((h, a), (a, h)):
            ms, os_ = me.get("statistics", {}), opp.get("statistics", {})
            try:
                rows.append(dict(
                    gid=g["gameId"], date=g.get("gameEt", "")[:10],
                    team=me["teamTricode"], opp=opp["teamTricode"],
                    fta=ms["freeThrowsAttempted"], fga=ms["fieldGoalsAttempted"], ftm=ms["freeThrowsMade"],
                    opp_fta=os_["freeThrowsAttempted"], opp_fga=os_["fieldGoalsAttempted"], opp_ftm=os_["freeThrowsMade"]))
            except Exception:
                pass
    return pd.DataFrame(rows).drop_duplicates(["gid", "team"])


def main():
    G = load()
    league_ftr = G.fta.sum() / G.fga.sum()
    # each team's own OFFENSIVE FTr (FTA/FGA) across all its rows -> used as the opponent's expectation
    off_ftr = (G.groupby("team").fta.sum() / G.groupby("team").fga.sum()).to_dict()
    print(f"rows={len(G)}  league FTr (FTA/FGA)={league_ftr:.4f}")

    for tri in ["NYK", "SAS"]:
        sub = G[G.team == tri].sort_values("date").reset_index(drop=True)
        # full-sample factor (opponent-adjusted): allowed / expected-from-opponents
        allowed = sub.opp_fta.sum() / sub.opp_fga.sum()
        exp = np.mean([off_ftr.get(o, league_ftr) for o in sub.opp])
        full_factor = allowed / exp
        print(f"\n=== {tri}  n={len(sub)} ===")
        print(f"  opp FTr ALLOWED={allowed:.4f}  expected-from-opp={exp:.4f}  full opp-adj factor={full_factor:.3f}")

        # leak-free LOO grading of opponent FTA
        base_err, def_err, base_bias, def_bias = [], [], [], []
        for i in range(len(sub)):
            g = sub.iloc[i]
            other = sub.drop(i)
            # defending team's LOO factor (opponent-adjusted)
            loo_allowed = other.opp_fta.sum() / other.opp_fga.sum()
            loo_exp = np.mean([off_ftr.get(o, league_ftr) for o in other.opp])
            force = loo_allowed / loo_exp
            # opponent's own offensive FTr from games OTHER than this one (leak-free)
            opp_rows = G[(G.team == g.opp) & (G.gid != g.gid)]
            opp_ftr = (opp_rows.fta.sum() / opp_rows.fga.sum()) if len(opp_rows) else league_ftr
            base_pred = opp_ftr * g.opp_fga
            def_pred = opp_ftr * g.opp_fga * force
            base_err.append(abs(base_pred - g.opp_fta)); def_err.append(abs(def_pred - g.opp_fta))
            base_bias.append(base_pred - g.opp_fta); def_bias.append(def_pred - g.opp_fta)
        print(f"  LOO opp-FTA pred:  baseline MAE {np.mean(base_err):.2f} bias {np.mean(base_bias):+.2f}"
              f"  | +ft_force MAE {np.mean(def_err):.2f} bias {np.mean(def_bias):+.2f}"
              f"  | dMAE {np.mean(def_err)-np.mean(base_err):+.3f}")
        # shrunk factor recommendation (K games of prior)
        n = len(sub)
        for K in (8, 15):
            w = n / (n + K)
            shrunk = 1.0 * (1 - w) + full_factor * w
            print(f"  shrink K={K}: w={w:.2f} -> ft_force={shrunk:.3f}")


if __name__ == "__main__":
    main()
