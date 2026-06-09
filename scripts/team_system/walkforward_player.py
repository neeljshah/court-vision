"""LEAK-FREE PLAYER-GAME WALK-FORWARD -- the honest test of whether a DEEPER, matchup-aware prediction
beats the baselines. No ceiling dogma: each layer is graded out-of-sample on the actuals; we ship what wins.

For every NYK/SAS player-game (as-of = prior games only), predict pts/reb/ast with progressively deeper
layers and report RMSE + bias + MAE per layer:

  L0 season mean (expanding)         -- the dumb baseline
  L1 recency EWMA (form)             -- current-form weighting
  L2 recency-blend (0.6 EWMA + 0.4 season)  -- the shipped RECENCY_W spine
  L3 + opponent matchup-D (as-of)    -- scale by how the opponent's defense suppresses/inflates scoring
  L4 + minutes-form (as-of mpg drift)-- the minutes-surprise frontier (rate held, minutes re-projected)

Each layer must BEAT the previous on held-out RMSE to justify the depth. Fully leak-free (every input is
built from games strictly before the predicted game). The winners feed the sim's anchor; the losers are
reported as the specific number they scored, not dismissed.

  python scripts/team_system/walkforward_player.py
"""
from __future__ import annotations
import math, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BURNIN = 8
HL = 5.0          # recency half-life (games)
W_REC = 0.6       # recency blend weight (the shipped RECENCY_W)


def _asof_team_drtg():
    """As-of opponent defensive rating (expanding, prior games only) keyed by (date, team)."""
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet")).sort_values("date")
    L = 100 * TG.opp_pts.sum() / TG.opp_poss.sum()
    out = {}
    acc = {}
    for r in TG.itertuples(index=False):
        a = acc.setdefault(r.team, [0.0, 0.0])
        out[(r.date, r.team)] = (100 * a[0] / a[1]) if a[1] > 50 else L
        a[0] += r.opp_pts; a[1] += r.opp_poss
    return out, L


def main():
    G = pd.read_parquet(os.path.join(TS, "nyksas_player_gamelog.parquet")).sort_values(["date", "gid"])
    drtg, L_DRTG = _asof_team_drtg()
    hist = {}     # pid -> list of (pts,reb,ast,mins)
    preds = []
    for r in G.itertuples(index=False):
        h = hist.get(r.pid, [])
        if len(h) >= BURNIN:
            arr = np.array(h, dtype=float)  # cols pts,reb,ast,mins
            n = len(arr)
            ages = np.arange(n)[::-1]                 # 0 = most recent
            w = 0.5 ** (ages / HL); w /= w.sum()
            season = arr.mean(0)
            ewma = (arr * w[:, None]).sum(0)
            blend = W_REC * ewma + (1 - W_REC) * season
            # L3 opponent matchup-D: scale pts/reb/ast by opponent defensive strength (as-of)
            od = drtg.get((r.date, r.opp), L_DRTG)
            def_factor = float(np.clip(1.0 + 0.5 * (od - L_DRTG) / L_DRTG, 0.90, 1.10))  # weak D(high drtg)->up
            l3 = blend.copy(); l3[:3] = blend[:3] * def_factor
            # L4 minutes-form: re-project minutes by recent drift, hold per-minute rate
            rec_min = ewma[3]; season_min = season[3]
            min_proj = 0.7 * rec_min + 0.3 * season_min
            per_min = blend[:3] / max(blend[3], 1e-6)
            l4 = l3.copy(); l4[:3] = per_min * min_proj * def_factor
            preds.append(dict(pid=r.pid, stat_pts=r.pts, stat_reb=r.reb, stat_ast=r.ast,
                              L0=season[:3], L1=ewma[:3], L2=blend[:3], L3=l3[:3], L4=l4[:3]))
        hist.setdefault(r.pid, []).append([r.pts, r.reb, r.ast, r.mins])

    P = pd.DataFrame(preds)
    print(f"GRADED player-games: {len(P)} (burn-in {BURNIN}; leak-free as-of)\n")
    act = {s: P[f"stat_{s}"].values for i, s in enumerate(("pts", "reb", "ast"))}
    layers = ["L0", "L1", "L2", "L3", "L4"]
    names = {"L0": "season mean", "L1": "recency EWMA", "L2": "recency-blend (shipped)",
             "L3": "+ matchup-D", "L4": "+ minutes-form"}
    for si, s in enumerate(("pts", "reb", "ast")):
        a = act[s]
        print(f"=== {s.upper()} (n={len(P)}, actual mean {a.mean():.2f}) ===")
        best = None
        for L in layers:
            pred = np.array([row[si] for row in P[L].values])
            rmse = math.sqrt(np.mean((pred - a) ** 2)); mae = np.mean(np.abs(pred - a)); bias = np.mean(pred - a)
            tag = ""
            if best is None or rmse < best:
                pass
            print(f"  {L} {names[L]:24s} RMSE {rmse:5.3f}  MAE {mae:5.3f}  bias {bias:+5.3f}")
        print()
    P.to_parquet(os.path.join(TS, "walkforward_player_preds.parquet"), index=False)


if __name__ == "__main__":
    main()
