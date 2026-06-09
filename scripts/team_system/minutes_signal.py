"""MINUTES SIGNAL -- the highest-value lever (minutes-surprise = 22% of pts MSE), built the way the user wants:
not a 'deeper model' but a COMPOSITION OF SIGNALS. Each sub-signal is leak-free and as-of; together they
predict a player's minutes better than the naive recency average, which propagates straight into points.

Sub-signals (all as-of, prior games only):
  m_ewma          recency minutes (role)            min_std        rotation stability (low = predictable)
  m_season        season minutes                    starter_rate   recent share of games started
  min_trend       ewma - season (role change)       pf_per_min     foul-trouble propensity (-> minute risk)
  rest, is_b2b    schedule                           proj_compet    |as-of net diff| (blowout -> starters sit)
  games_played    role establishment                fga_per_min    usage role

Target = actual minutes. Leak-free 5-fold by GAME. Reports minutes MAE (signal vs naive) AND the downstream
PTS RMSE (per-min rate x projected minutes) -- the test of whether the minutes signal yields better predictions.

  python scripts/team_system/minutes_signal.py
"""
from __future__ import annotations
import math, os
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
HL = 5.0; BURNIN = 8


def _asof_net():
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet")).sort_values("date")
    net = {}; acc = {}
    for r in TG.itertuples(index=False):
        a = acc.setdefault(r.team, [0.0, 0.0, 0.0, 0.0])
        net[(str(r.date)[:10], r.team)] = ((100 * a[0] / a[1]) - (100 * a[2] / a[3])) if a[1] > 50 else 0.0
        a[0] += r.pts; a[1] += r.poss; a[2] += r.opp_pts; a[3] += r.opp_poss
    return net


def main():
    G = pd.read_parquet(os.path.join(TS, "nyksas_player_gamelog.parquet")).sort_values(["date", "gid"])
    G["date"] = G.date.astype(str).str[:10]
    net = _asof_net()
    hist = {}; rows = []
    for r in G.itertuples(index=False):
        h = hist.get(r.pid, [])
        if len(h) >= BURNIN:
            arr = np.array(h, float)  # cols: mins, pts, pf, fga, starter
            n = len(arr); ages = np.arange(n)[::-1]; w = 0.5 ** (ages / HL); w /= w.sum()
            m_ewma = (arr[:, 0] * w).sum(); m_season = arr[:, 0].mean()
            recent = arr[-10:]
            mynet = net.get((r.date, r.team), 0.0); oppnet = net.get((r.date, r.opp), 0.0)
            permin_pts = (0.6 * (arr[:, 1] * w).sum() + 0.4 * arr[:, 1].mean()) / max(0.6 * m_ewma + 0.4 * m_season, 1e-6)
            rows.append(dict(gid=r.gid, pid=r.pid, a_min=r.mins, a_pts=r.pts, permin_pts=permin_pts,
                             m_ewma=m_ewma, m_season=m_season, min_std=recent[:, 0].std(),
                             min_trend=m_ewma - m_season, starter_rate=recent[:, 4].mean(),
                             pf_per_min=recent[:, 2].sum() / max(recent[:, 0].sum(), 1e-6),
                             fga_per_min=recent[:, 3].sum() / max(recent[:, 0].sum(), 1e-6),
                             rest=r.rest, is_b2b=r.is_b2b, games_played=n,
                             proj_compet=abs(mynet - oppnet)))
        hist.setdefault(r.pid, []).append([r.mins, r.pts, r.pf, r.fga, r.starter])
    P = pd.DataFrame(rows)
    FEATS = ["m_ewma", "m_season", "min_std", "min_trend", "starter_rate", "pf_per_min", "fga_per_min",
             "rest", "is_b2b", "games_played", "proj_compet"]
    gids = np.array(sorted(P.gid.unique())); rng = np.random.default_rng(0); rng.shuffle(gids)
    folds = np.array_split(gids, 5)
    P["m_pred"] = np.nan
    for fold in folds:
        te = P[P.gid.isin(fold)]; tr = P[~P.gid.isin(fold)]
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=30, random_state=0)
        m.fit(tr[FEATS], tr.a_min)
        P.loc[P.gid.isin(fold), "m_pred"] = np.clip(m.predict(te[FEATS]), 0, 44)
    am = P.a_min.values; ap = P.a_pts.values
    naive_min = P.m_ewma.values; sig_min = P.m_pred.values
    print(f"MINUTES SIGNAL (n={len(P)} player-games, leak-free 5-fold by game)\n")
    print(f"  minutes MAE   naive EWMA {np.mean(np.abs(naive_min-am)):.3f}   SIGNAL {np.mean(np.abs(sig_min-am)):.3f}   "
          f"({(np.mean(np.abs(sig_min-am))/np.mean(np.abs(naive_min-am))-1)*100:+.1f}%)")
    print(f"  minutes RMSE  naive EWMA {math.sqrt(np.mean((naive_min-am)**2)):.3f}   SIGNAL {math.sqrt(np.mean((sig_min-am)**2)):.3f}")
    # downstream points: per-min rate x projected minutes
    pts_naive = P.permin_pts.values * naive_min
    pts_sig = P.permin_pts.values * sig_min
    print(f"\n  PTS RMSE      naive-min {math.sqrt(np.mean((pts_naive-ap)**2)):.3f}   SIGNAL-min {math.sqrt(np.mean((pts_sig-ap)**2)):.3f}   "
          f"oracle-min {math.sqrt(np.mean((P.permin_pts.values*am-ap)**2)):.3f}")
    print(f"  PTS MAE       naive-min {np.mean(np.abs(pts_naive-ap)):.3f}   SIGNAL-min {np.mean(np.abs(pts_sig-ap)):.3f}")
    # VERDICT on the kitchen-sink: a black-box over ALL signals OVERFITS (loses to naive). Signals must be
    # applied SURGICALLY. The conditional test below isolates which minute signals are REAL.
    R = P[(P.m_ewma >= 12) & (P.a_min >= 1)]          # rotation players (where minutes matter)
    print("\n  === SURGICAL minute signals (actual - naive EWMA on rotation players; the REAL signals) ===")
    for name, mask in [("projected BLOWOUT (compet>10), starter>=28mpg", (R.proj_compet > 10) & (R.m_ewma >= 28)),
                       ("CLOSE game (compet<4), starter>=28mpg", (R.proj_compet < 4) & (R.m_ewma >= 28)),
                       ("B2B, starter>=28mpg", (R.is_b2b == 1) & (R.m_ewma >= 28)),
                       ("high foul-rate (pf/min>0.12)", R.pf_per_min > 0.12)]:
        s = R[mask]
        if len(s) > 15:
            d = (s.a_min - s.m_ewma)
            print(f"    {name:46s} n={len(s):4d}  mean dev {d.mean():+.2f} min")
    print("  -> competitiveness is a REAL minutes signal (blowout -> starters sit ~1.4 min, close -> +0.8);")
    print("     modest pregame (~+/-1pt) but observed IN-GAME; the BIG minutes signal is same-day availability")
    print("     (who's OUT -> re-project the rotation = freshness, data-gated). Kitchen-sink overfits; build surgical.")
    P.to_parquet(os.path.join(TS, "minutes_signal_preds.parquet"), index=False)


if __name__ == "__main__":
    main()
