"""Measure whether a TURNOVER->POINTS drag in the anchor improves opponent-total prediction (leak-free).

The sensitivity tool exposed that the per-game anchor is ~invariant to turnover-forcing: tov_force moves
the (unanchored) turnover stat but NOT the win prob, because the anchor re-pins each player's per-game pts.
Yet a forced turnover is a lost scoring possession (~1.1 pts). So facing a defense that forces f x the
league turnover rate, a team's scoring possessions go (1-t) -> (1-t*f), i.e. pts scale by
  tov_drag = (1 - t*f) / (1 - t)        [t = league TOV rate ~0.146]
This tests, leave-one-game-out, whether multiplying the opponent's expected total by this defending-team
drag (f = defending team's tov_force from OTHER games) improves the opponent-total prediction. If yes (or
bias-reducing toward 0 with neutral MAE), it is worth wiring into _matchup_mult next to the FT factor.
ascii-only prints.
"""
import os
import numpy as np
import pandas as pd

TS = "data/cache/team_system"
T = 0.146   # league baseline TOV rate (per possession), from build_team_defense baseline 14.6%


def main():
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    base_tov = tg.opp_tov.sum() / tg.opp_poss.sum()
    # each team's OWN season offensive pts/game (the opponent's expectation) and defending-team tov_force
    off_pts = tg.groupby("team").apply(lambda x: x.pts.mean(), include_groups=False).to_dict()
    print(f"league baseline opp TOV%={base_tov*100:.1f}  (drag uses t={T})")
    for tri in ["NYK", "SAS"]:
        sub = tg[tg.team == tri].sort_values("date").reset_index(drop=True)
        base_err, drag_err, base_bias, drag_bias = [], [], [], []
        for i in range(len(sub)):
            g = sub.iloc[i]; other = sub.drop(i)
            f = (other.opp_tov.sum() / other.opp_poss.sum()) / base_tov          # defending team's tov_force, LOO
            drag = (1 - T * f) / (1 - T)
            # opponent's own season offensive pts from games OTHER than this one (leak-free)
            opp_rows = tg[(tg.team == g.opp) & (tg.gid != g.gid)]
            exp = opp_rows.pts.mean() if len(opp_rows) else off_pts.get(g.opp, tg.pts.mean())
            base_pred = exp
            drag_pred = exp * drag
            actual = g.opp_pts
            base_err.append(abs(base_pred - actual)); drag_err.append(abs(drag_pred - actual))
            base_bias.append(base_pred - actual); drag_bias.append(drag_pred - actual)
        f_full = (sub.opp_tov.sum() / sub.opp_poss.sum()) / base_tov
        drag_full = (1 - T * f_full) / (1 - T)
        print(f"\n=== {tri} D ===  tov_force={f_full:.3f} -> tov_drag on opp pts={drag_full:.4f} ({100*(drag_full-1):+.1f}%)")
        print(f"  LOO opp-TOTAL pred:  baseline MAE {np.mean(base_err):.2f} bias {np.mean(base_bias):+.2f}"
              f"  | +tov_drag MAE {np.mean(drag_err):.2f} bias {np.mean(drag_bias):+.2f}"
              f"  | dMAE {np.mean(drag_err)-np.mean(base_err):+.3f}")


if __name__ == "__main__":
    main()
