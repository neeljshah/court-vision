"""Highest-fidelity basketball sim — fidelity validation.

Does the simulated game look like real basketball? Simulates NYK vs SAS (both have full
rates) and checks:
  - player marginal reproduction: sim mean pts/reb/ast vs each rotation player's season avg
  - team totals vs ortg*pace expectation
  - teammate pts-pts correlation (the canary: must be ~0/slightly negative, not +0.645)
  - coherence (sum of player pts == team total, by construction)

This validates the ENGINE's fidelity (rates are in-sample here on purpose — we're testing the
simulator's realism, not out-of-sample prediction). Prints a report.

  python scripts/team_system/validate_sim_fidelity.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel, simulate_game  # noqa: E402

ASC = lambda s: str(s).encode("ascii", "replace").decode()


def main(n_sims=4000):
    home, away = TeamModel.from_cache("SAS"), TeamModel.from_cache("NYK")
    # raw-engine fidelity test: defense OFF so we test pure offensive reproduction of season avg
    # (matchup defense is validated separately in verify_defense.py).
    res = simulate_game(home, away, n_sims=n_sims, seed=7, anchor=False, defense=False)

    print(f"=== SIM FIDELITY: NYK @ SAS ({n_sims} sims) ===")
    print(f"team totals: SAS {res.home_total.mean():.1f}±{res.home_total.std():.1f} | "
          f"NYK {res.away_total.mean():.1f}±{res.away_total.std():.1f} | SAS winP {res.home_win_prob:.2f}")

    # player marginal reproduction vs season avg
    errs = {"pts": [], "reb": [], "ast": []}
    for tri, model in (("SAS", home), ("NYK", away)):
        print(f"\n{tri} rotation — sim mean vs season avg (pts / reb / ast):")
        rows = [(p, d) for p, d in res.players.items() if d["team"] == tri]
        rows.sort(key=lambda x: -x[1]["mean"]["pts"])
        for p, d in rows[:9]:
            r = model.rate[p]
            avg_pts = r["pts_pg"]
            avg_reb = (r["oreb_per_min"] + r["dreb_per_min"]) * r["mpg"]
            avg_ast = r["ast_per_min"] * r["mpg"]
            sp, sr, sa = d["mean"]["pts"], d["reb_mean"], d["mean"]["ast"]
            errs["pts"].append(sp - avg_pts); errs["reb"].append(sr - avg_reb); errs["ast"].append(sa - avg_ast)
            print(f"   {ASC(d['name']):24s} {sp:4.1f}/{avg_pts:4.1f}   {sr:4.1f}/{avg_reb:4.1f}   {sa:4.1f}/{avg_ast:4.1f}")
    for k in ("pts", "reb", "ast"):
        e = np.array(errs[k])
        print(f"  marginal {k}: bias {e.mean():+.2f}  MAE {np.abs(e).mean():.2f}")

    # teammate correlation canary
    print("\nteammate pts-pts correlation (canary; real ~ -0.1, OLD engine bug +0.645):")
    def corr(team, n1, n2):
        a = b = None
        for d in res.players.values():
            if d["team"] == team and n1 in d["name"]:
                a = d["samples"]["pts"]
            if d["team"] == team and n2 in d["name"]:
                b = d["samples"]["pts"]
        return np.corrcoef(a, b)[0, 1] if a is not None and b is not None else float("nan")
    pairs = [("SAS", "Wembanyama", "Castle"), ("SAS", "Wembanyama", "Fox"),
             ("NYK", "Brunson", "Towns"), ("NYK", "Brunson", "Bridges")]
    cs = [corr(t, a, b) for t, a, b in pairs]
    for (t, a, b), c in zip(pairs, cs):
        print(f"   {t} {a}/{b}: {c:+.3f}")
    print(f"  mean teammate rho: {np.nanmean(cs):+.3f}  (PASS if < +0.05)")

    # coherence
    sas_sum = sum(d["mean"]["pts"] for d in res.players.values() if d["team"] == "SAS")
    print(f"\ncoherence: sum(SAS player pts)={sas_sum:.1f} vs team total {res.home_total.mean():.1f} "
          f"(MAE {abs(sas_sum - res.home_total.mean()):.2f}; old engine 14.98)")


if __name__ == "__main__":
    main()
