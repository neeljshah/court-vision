"""Full-stat per-player game log from the boxscores = the calibration GROUND TRUTH for every prop.

The existing nyksas_player_gamelog has only pts/reb/ast/pf/fga/tov. To calibrate EVERY prop (3PM/STL/BLK/
FTM/OREB/DREB) against reality we need the full box. This walks every NYK/SAS game's boxscore and writes
`nyksas_full_gamelog.parquet` (one row per player-game, all stats), then prints sim-anchor-vs-real bias per
stat so we can see exactly which props are miscalibrated.

  python scripts/team_system/build_full_gamelog.py
"""
from __future__ import annotations
import json, os, re
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")


def _min(s):
    m = re.match(r"PT(\d+)M([\d.]+)S", str(s) or "")
    return (int(m.group(1)) + float(m.group(2)) / 60.0) if m else 0.0


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    rows = []
    for gm in games:
        bf = os.path.join(BOX, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        g = json.load(open(bf, encoding="utf-8")); g = g.get("game", g)
        for side in ("homeTeam", "awayTeam"):
            t = g.get(side, {}); tri = t.get("teamTricode")
            for p in t.get("players", []):
                st = p.get("statistics", {}) or {}
                mn = _min(st.get("minutes"))
                if mn < 0.5:
                    continue
                rows.append(dict(gid=gm["gid"], date=gm["date"], pid=int(p["personId"]),
                                 player=p.get("name"), team=tri, mins=mn,
                                 pts=st.get("points", 0), reb=st.get("reboundsTotal", st.get("reboundsPersonal", 0)),
                                 ast=st.get("assists", 0), stl=st.get("steals", 0), blk=st.get("blocks", 0),
                                 fg3m=st.get("threePointersMade", 0), ftm=st.get("freeThrowsMade", 0),
                                 oreb=st.get("reboundsOffensive", 0), dreb=st.get("reboundsDefensive", 0),
                                 tov=st.get("turnovers", 0), fga=st.get("fieldGoalsAttempted", 0),
                                 pf=st.get("foulsPersonal", 0), starter=1 if p.get("starter") else 0))
    G = pd.DataFrame(rows)
    G.to_parquet(os.path.join(TS, "nyksas_full_gamelog.parquet"), index=False)
    print(f"FULL gamelog: {len(G)} player-games, {G.gid.nunique()} games, {G.pid.nunique()} players")

    # SECONDARY-STAT TARGETS = real per-game means (rotation games >=12 min) -> the Poisson rates the engine
    # uses so count-prop FREQUENCY/tails are calibrated (the chain produces zero-clumped blk/3pm). Recency-
    # weighted (half-life 12g) so it tracks current form; season-mean fallback.
    G2 = G[G.mins >= 12].sort_values(["pid", "date"])
    trg = []
    for pid, g in G2.groupby("pid"):
        if len(g) < 3:
            continue
        ages = np.arange(len(g))[::-1]; w = 0.5 ** (ages / 12.0); w = w / w.sum()
        row = {"pid": pid, "n": len(g)}
        for s in ("blk", "stl", "fg3m", "ftm", "tov", "oreb", "dreb"):
            v = g[s].values.astype(float)
            row[s] = float(0.6 * (v * w).sum() + 0.4 * v.mean())   # recency-blend, like the pts target
            # per-game variance (empirical, ddof=1) -> the engine fits a negative-binomial when a count is
            # over-dispersed (var>mean), so blk/fg3m/ftm tails+zero-inflation are calibrated, not Poisson-smooth.
            row[f"{s}_var"] = float(np.var(v, ddof=1)) if len(v) >= 2 else float(row[s])
        trg.append(row)
    T = pd.DataFrame(trg)
    T.to_parquet(os.path.join(TS, "secondary_targets.parquet"), index=False)
    print(f"secondary_targets: {len(T)} players (recency-blended per-game means + _var for NB dispersion)")

    # ---- sim-anchor-vs-real bias per stat (rotation players, >=15 mpg) ----
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet")).set_index("pid")
    real = G[G.mins >= 15].groupby("pid").agg(mpg=("mins", "mean"), n=("gid", "count"),
                                              pts=("pts", "mean"), reb=("reb", "mean"), ast=("ast", "mean"),
                                              stl=("stl", "mean"), blk=("blk", "mean"), fg3m=("fg3m", "mean"),
                                              ftm=("ftm", "mean"), tov=("tov", "mean"))
    real = real[real.n >= 8]
    print("\n=== SIM ANCHOR TARGET vs REAL per-game mean (rotation, n>=8; bias = sim - real) ===")
    print(f"{'stat':6s} {'sim_mean':>9s} {'real_mean':>9s} {'bias':>7s} {'bias%':>7s}")
    for stat, fn in [("stl", lambda r: r.get("stl_per_min", 0) * r["mpg"]),
                     ("blk", lambda r: r.get("blk_per_min", 0) * r["mpg"]),
                     ("tov", lambda r: r.get("use_per_min", 0) * r["mpg"] * r.get("tov_share", 0)),
                     ("fg3m", lambda r: r.get("use_per_min", 0) * r["mpg"] * r.get("shot_share", 0) * r.get("fg3_rate", 0) * r.get("fg3_pct", 0)),
                     ("ftm", lambda r: r.get("use_per_min", 0) * r["mpg"] * r.get("ft_share", 0) * 2 * r.get("ft_pct", 0))]:
        sim_vals, real_vals = [], []
        for pid, rr in real.iterrows():
            if pid in rates.index:
                sim_vals.append(float(fn(rates.loc[pid]))); real_vals.append(float(rr[stat]))
        sm, rm = np.mean(sim_vals), np.mean(real_vals)
        print(f"{stat:6s} {sm:9.2f} {rm:9.2f} {sm-rm:+7.2f} {(sm/rm-1)*100 if rm else 0:+6.0f}%")


if __name__ == "__main__":
    main()
