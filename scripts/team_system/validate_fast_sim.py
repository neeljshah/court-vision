"""Fast GPU validation harness — fidelity + defense + engine-equivalence, all in seconds.

Runs the full sim test suite on the GPU-vectorized engine (fast_sim) so calibration/signal
iteration is interactive instead of ~45s/run:
  1. FIDELITY (raw engine, defense off): marginals vs season avg, teammate-rho, coherence
  2. DEFENSE (anchored, on vs off): tougher D suppresses more; rim scorers drop most
  3. EQUIVALENCE: GPU engine matches the CPU reference within Monte-Carlo noise

  python scripts/team_system/validate_fast_sim.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel, simulate_game  # noqa: E402
from sim.fast_sim import device, simulate_game_fast  # noqa: E402

ASC = lambda s: str(s).encode("ascii", "replace").decode()


def _rho(res, team, n1, n2):
    a = b = None
    for d in res.players.values():
        if d["team"] == team and n1 in d["name"]:
            a = d["samples"]["pts"]
        if d["team"] == team and n2 in d["name"]:
            b = d["samples"]["pts"]
    return np.corrcoef(a, b)[0, 1] if a is not None and b is not None else float("nan")


def main(n=20000):
    print(f"=== FAST GPU VALIDATION (device: {device()}, n_sims={n}) ===")
    h, a = TeamModel.from_cache("SAS"), TeamModel.from_cache("NYK")

    # 1. FIDELITY (raw engine, no matchup defense) -------------------------------------------
    t = time.time(); res = simulate_game_fast(h, a, n_sims=n, seed=7, anchor=False, defense=False)
    e = {"pts": [], "reb": [], "ast": []}
    for tm in (h, a):
        for p, d in res.players.items():
            if d["team"] != tm.tri or tm.rate[p]["mpg"] < 10:
                continue
            r = tm.rate[p]
            e["pts"].append(d["mean"]["pts"] - r["pts_pg"])
            e["reb"].append(d["reb_mean"] - (r["oreb_per_min"] + r["dreb_per_min"]) * r["mpg"])
            e["ast"].append(d["mean"]["ast"] - r["ast_per_min"] * r["mpg"])
    print(f"\n1. FIDELITY ({time.time() - t:.1f}s):")
    for k in ("pts", "reb", "ast"):
        v = np.array(e[k]); print(f"   marginal {k}: bias {v.mean():+.2f}  MAE {np.abs(v).mean():.2f}")
    pairs = [("SAS", "Wembanyama", "Castle"), ("SAS", "Wembanyama", "Fox"),
             ("NYK", "Brunson", "Towns"), ("NYK", "Brunson", "Bridges")]
    rhos = [_rho(res, *p) for p in pairs]
    sas_sum = sum(d["mean"]["pts"] for d in res.players.values() if d["team"] == "SAS")
    print(f"   teammate rho mean {np.nanmean(rhos):+.3f} (PASS<+0.05: {np.nanmean(rhos) < 0.05})  "
          f"coherence MAE {abs(sas_sum - res.home_total.mean()):.2f}")

    # 2. DEFENSE (anchored, on vs off) -------------------------------------------------------
    t = time.time()
    off = simulate_game_fast(h, a, n_sims=n, seed=11, anchor=True, defense=False)
    on = simulate_game_fast(h, a, n_sims=n, seed=11, anchor=True, defense=True)
    sas_d = off.home_total.mean() - on.home_total.mean()
    nyk_d = off.away_total.mean() - on.away_total.mean()
    print(f"\n2. DEFENSE ({time.time() - t:.1f}s): SAS rim_d {h.rim_d:.0f}/perim {h.perim_d:.0f} | "
          f"NYK rim_d {a.rim_d:.0f}/perim {a.perim_d:.0f}")
    print(f"   suppression: SAS -{sas_d:.1f}, NYK -{nyk_d:.1f} (NYK faces tougher D) -> "
          f"PASS {nyk_d > sas_d and 1 < nyk_d < 12}")

    # 3. EQUIVALENCE vs CPU reference --------------------------------------------------------
    t = time.time(); ref = simulate_game(h, a, n_sims=3000, seed=7, anchor=False, defense=False); tref = time.time() - t
    t = time.time(); fst = simulate_game_fast(h, a, n_sims=3000, seed=7, anchor=False, defense=False); tfst = time.time() - t
    d = [abs(ref.players[p]["mean"]["pts"] - fst.players[p]["mean"]["pts"]) for p in ref.players
         if ref.players[p]["mean"]["pts"] > 5]
    print(f"\n3. EQUIVALENCE: per-player pts MAE(ref vs fast) {np.mean(d):.2f} "
          f"(PASS<0.6: {np.mean(d) < 0.6})  | speedup {tref / tfst:.1f}x (ref {tref:.1f}s, fast {tfst:.1f}s)")


if __name__ == "__main__":
    main()
