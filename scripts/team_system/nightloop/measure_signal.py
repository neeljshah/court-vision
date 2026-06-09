"""Night-loop new-signal explorer: size a candidate team-identity signal fast + leak-free-ish.

Dispatches on a signal name. Each measurement reports magnitude, league-relative edge, and split-half
stability so the loop can judge whether it is a real, learnable team trait worth wiring (the discipline:
team-IDENTITY full-season signals validate; 4-game H2H signals are noise). Unknown names exit cleanly so
the overnight loop never crashes. ascii-only prints.

  python scripts/team_system/nightloop/measure_signal.py rest_days
  python scripts/team_system/nightloop/measure_signal.py paint_rate_def
  python scripts/team_system/nightloop/measure_signal.py three_var
  python scripts/team_system/nightloop/measure_signal.py upper_tail
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")
MINE = ["NYK", "SAS"]


def _splithalf(series_for, series_against):
    s = pd.DataFrame({"f": list(series_for), "a": list(series_against)}).reset_index(drop=True)
    o = s[s.index % 2 == 0]; e = s[s.index % 2 == 1]
    return (o.f.mean() - o.a.mean()), (e.f.mean() - e.a.mean())


def rest_days():
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    tg = tg.sort_values(["team", "date"]).copy()
    tg["date"] = pd.to_datetime(tg["date"])
    tg["rest"] = tg.groupby("team")["date"].diff().dt.days.clip(upper=4)
    lg = tg.pts.mean()
    print(f"=== rest_days ===  league pts/g {lg:.1f}")
    for tri in MINE:
        s = tg[tg.team == tri]
        for r in [1, 2, 3, 4]:
            sub = s[s.rest == r]
            if len(sub) >= 4:
                print(f"  {tri} rest={r}d: pts {sub.pts.mean():5.1f} ({len(sub)}g, {sub.pts.mean()-s.pts.mean():+.1f} vs own avg)")
    print("VERDICT: rest is a context signal; wire only if a team shows a stable >2 pt rest gradient (else noise).")


def paint_rate_def():
    """Opponent paint scoring allowed (pointsInThePaint), opponent-adjusted + split-half -- analog of ft_force."""
    rows = []
    for f in glob.glob(f"{BOX}/*.json"):
        g = json.load(open(f)).get("game", {})
        h, a = g.get("homeTeam"), g.get("awayTeam")
        if not h or not a:
            continue
        for me, opp in ((h, a), (a, h)):
            ms, os_ = me.get("statistics", {}), opp.get("statistics", {})
            rows.append((g.get("gameId"), me["teamTricode"], opp["teamTricode"],
                         ms.get("pointsInThePaint", np.nan), os_.get("pointsInThePaint", np.nan)))
    G = pd.DataFrame(rows, columns=["gid", "team", "opp", "paint", "opp_paint"]).drop_duplicates(["gid", "team"]).dropna()
    lg_allowed = G.opp_paint.mean()
    off = G.groupby("team").paint.mean().to_dict()
    print(f"=== paint_rate_def ===  league opp paint pts/g {lg_allowed:.1f}")
    for tri in MINE:
        s = G[G.team == tri]
        allowed = s.opp_paint.mean()
        exp = np.mean([off.get(o, lg_allowed) for o in s.opp])
        o, e = _splithalf(-s.opp_paint, -s.opp_paint * 0)  # stability of allowed (negate so 'for-against' = -allowed)
        oo = s.iloc[::2].opp_paint.mean(); ee = s.iloc[1::2].opp_paint.mean()
        print(f"  {tri}: opp paint allowed {allowed:5.1f}  exp-from-opp {exp:5.1f}  factor {allowed/exp:.3f}  split-half {oo:.1f}/{ee:.1f}")
    print("VERDICT: candidate if factor!=1 and split-half stable; CHECK double-count vs rim_d make-suppression before wiring.")


def three_var():
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    print("=== three_var ===  3PA volume + make-rate -> win sensitivity")
    for tri in MINE:
        s = tg[tg.team == tri].copy()
        s["fg3pct"] = s.fg3m / s.fg3a.clip(lower=1)
        win_hot = s[s.fg3pct >= s.fg3pct.median()].win.mean()
        win_cold = s[s.fg3pct < s.fg3pct.median()].win.mean()
        print(f"  {tri}: 3PA/g {s.fg3a.mean():.1f}  3P% {s.fg3pct.mean():.3f}  win when hot {win_hot:.0%} vs cold {win_cold:.0%}  (var={s.fg3pct.std():.3f})")
    print("VERDICT: descriptive variance signal (live-or-die); a high hot-vs-cold win gap = a swing team. Scouting, not a sim modulator (anchor has the mean).")


def upper_tail():
    """Run calibration on a subsample; report star >q90 over-rate (the known upper-skew residual)."""
    sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.join(ROOT, "src"))
    from build_player_rates import _pstat
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    trates = json.load(open(os.path.join(TS, "team_rates.json")))
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: g["date"])[::3]
    models = {}
    def m(t):
        if t not in models:
            try: models[t] = TeamModel.from_cache(t, rates_df=rates, team_rates=trates)
            except Exception: models[t] = None
        return models[t]
    above, below, n = [], [], 0
    for gm in games:
        bf = os.path.join(BOX, f"{gm['gid']}.json")
        if not os.path.exists(bf): continue
        bg = json.load(open(bf))["game"]
        ht, at = bg["homeTeam"]["teamTricode"], bg["awayTeam"]["teamTricode"]
        if ht not in MINE and at not in MINE: continue
        hm, am = m(ht), m(at)
        if not hm or not am: continue
        try: res = simulate_game_fast(hm, am, n_sims=4000, seed=2026, anchor=True, defense=True, context={"neutral_site": False})
        except Exception: continue
        n += 1
        for tri, side in ((ht, bg["homeTeam"]), (at, bg["awayTeam"])):
            if tri not in MINE: continue
            for p in side.get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < 28 or pid not in res.players: continue   # stars/starters
                sm = res.players[pid]["samples"]["pts"]
                above.append(1.0 if st["pts"] > np.quantile(sm, 0.9) else 0.0)
                below.append(1.0 if st["pts"] < np.quantile(sm, 0.1) else 0.0)
    print(f"=== upper_tail ===  {n} games, starters min>=28, n_pg={len(above)}")
    print(f"  pts > q90: {np.mean(above):.1%} (target 10%)   pts < q10: {np.mean(below):.1%} (target 10%)")
    print(f"VERDICT: {'RIGHT-SKEW FIX candidate (>q90 over target) -> add lognormal right-skew to star dispersion' if np.mean(above)>0.135 else 'tails ~ok, no fix needed'}")


DISPATCH = {"rest_days": rest_days, "paint_rate_def": paint_rate_def, "three_var": three_var, "upper_tail": upper_tail}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = DISPATCH.get(name)
    if fn is None:
        print(f"=== {name or '(none)'} ===  UNIMPLEMENTED signal -- loop should build a measurement for it or skip. "
              f"Known: {', '.join(DISPATCH)}")
        return
    fn()


if __name__ == "__main__":
    main()
