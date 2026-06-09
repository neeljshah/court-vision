"""STRUCTURAL FIDELITY: does the possession-MC ENGINE reproduce the validated M2 team-composition?

The 840-game walk-forward (walkforward_league.py) proves the team-level matchup COMPOSITION generalizes
leak-free. This ties that result to the actual engine: run `simulate_game_fast` on a spread of real league
matchups and check the engine's predicted margin/total tracks (a) the composition and (b) the actual result.
If engine == composition, then validating the composition validates the engine's team-level behavior; the
engine then adds the player-prop + joint structure the composition cannot express.

HONEST LABEL: uses FULL-SEASON identities (in-sample) -> this is a STRUCTURAL agreement check, not a
generalization number (that is the leak-free 840-game walk-forward). Injects clean league pace + the
30-team team_defense so the engine is not fed the thin team_rates for non-NYK/SAS teams.

  python scripts/team_system/engine_vs_composition.py --n 50
"""
from __future__ import annotations
import argparse, json, os, math, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
TS = os.path.join(ROOT, "data", "cache", "team_system")
import sim.basketball_sim as bs            # noqa: E402
from sim.basketball_sim import TeamModel   # noqa: E402
from sim.fast_sim import simulate_game_fast, device  # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--nsims", type=int, default=3000); a = ap.parse_args()

    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    L_ORTG = 100 * TG.pts.sum() / TG.poss.sum()
    # full-season clean identities
    ident = {}
    for t, g in TG.groupby("team"):
        ident[t] = dict(ortg=100 * g.pts.sum() / g.poss.sum(), drtg=100 * g.opp_pts.sum() / g.opp_poss.sum(),
                        pace=g.poss.mean())
    # inject clean 30-team defense (validated NYK/SAS + league 28) and clean pace into the engine globals
    dfl = pd.read_parquet(os.path.join(TS, "team_defense_league.parquet")).set_index("team")
    val = pd.read_parquet(os.path.join(TS, "team_defense.parquet")).set_index("team")
    bs._TEAM_DEF = {}
    for t in ident:
        src = val if t in val.index else dfl
        bs._TEAM_DEF[t] = dict(tov_force=float(src.loc[t, "tov_force"]), ft_force=float(src.loc[t, "ft_force"]),
                               oreb_strength=float(dfl.loc[t, "oreb_strength"]))
    tr = json.load(open(os.path.join(TS, "team_rates.json")))
    for t in ident:                                   # clean pace, keep lineups
        if t in tr:
            tr[t]["pace"] = ident[t]["pace"]
    rates_df = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))

    sg = {r["game_id"]: r for r in json.load(open(os.path.join(ROOT, "data", "nba", "season_games_2025-26.json")))["rows"]
          if "home_win" in r}
    # one row per game with actuals
    rows = []
    for gid, g in TG.groupby("gid"):
        s = sg.get(gid)
        if not s:
            continue
        ht, at = s["home_team"], s["away_team"]
        hr = g[g.team == ht]; ar = g[g.team == at]
        if len(hr) == 1 and len(ar) == 1:
            rows.append((gid, ht, at, int(hr.iloc[0].pts), int(ar.iloc[0].pts)))
    rng = np.random.default_rng(7)
    idx = rng.choice(len(rows), size=min(a.n, len(rows)), replace=False)
    sample = [rows[i] for i in idx]

    out = []
    for gid, ht, at, hp, ap_ in sample:
        try:
            home = TeamModel.from_cache(ht, rates_df=rates_df, team_rates=tr)
            away = TeamModel.from_cache(at, rates_df=rates_df, team_rates=tr)
            res = simulate_game_fast(home, away, n_sims=a.nsims, seed=2026, anchor=True, defense=True,
                                     context={"neutral_site": False})
            e_h, e_a = float(np.median(res.home_total)), float(np.median(res.away_total))
        except Exception as e:
            continue
        poss = 0.5 * (ident[ht]["pace"] + ident[at]["pace"])
        c_h = (ident[ht]["ortg"] + ident[at]["drtg"] - L_ORTG) / 100 * poss
        c_a = (ident[at]["ortg"] + ident[ht]["drtg"] - L_ORTG) / 100 * poss
        out.append(dict(gid=gid, ht=ht, at=at,
                        e_margin=e_h - e_a, e_total=e_h + e_a, e_wp=float(res.home_win_prob),
                        c_margin=c_h - c_a, c_total=c_h + c_a,
                        a_margin=hp - ap_, a_total=hp + ap_, home_win=int(hp > ap_)))
    D = pd.DataFrame(out)
    print(f"device {device()}  |  {len(D)} matchups  |  {a.nsims} sims each")
    print(f"corr(engine_margin, composition_margin) = {D.e_margin.corr(D.c_margin):.3f}")
    print(f"corr(engine_total,  composition_total)  = {D.e_total.corr(D.c_total):.3f}")
    print(f"engine margin vs actual:      RMSE {math.sqrt(((D.e_margin-D.a_margin)**2).mean()):5.2f}  bias {(D.e_margin-D.a_margin).mean():+5.2f}")
    print(f"composition margin vs actual: RMSE {math.sqrt(((D.c_margin-D.a_margin)**2).mean()):5.2f}  bias {(D.c_margin-D.a_margin).mean():+5.2f}")
    print(f"engine total  vs actual:      RMSE {math.sqrt(((D.e_total-D.a_total)**2).mean()):5.2f}  bias {(D.e_total-D.a_total).mean():+5.2f}")
    print(f"composition total vs actual:  RMSE {math.sqrt(((D.c_total-D.a_total)**2).mean()):5.2f}  bias {(D.c_total-D.a_total).mean():+5.2f}")
    print(f"engine straight-up accuracy (in-sample identities): {np.mean((D.e_wp>=0.5)==D.home_win):.3f}")
    print(f"mean |engine_margin - composition_margin| = {(D.e_margin-D.c_margin).abs().mean():.2f} pts")


if __name__ == "__main__":
    main()
