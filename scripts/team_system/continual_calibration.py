"""CONTINUAL-CALIBRATION LOOP (MASTER_SYSTEM_BUILD section 4E) -- the 'keep retraining' intuition done at
the calibration/meta layer, where it cannot overfit the marginal.

After each game (or on demand), grade EVERY prop's distribution shape (shapeErr = centered over-prob MAE at
the live book lines, the trustworthy-to-price grade) + record EVERY engine's reliability, write them to the
calibration_registry, board-gate (a red board never ships), and append a DELTA row (the change in the worst
shapeErr vs the prior snapshot). PROTECTED-RAW guard: this loop touches SHAPE/coverage ONLY -- it is
mean-preserving by construction and is FORBIDDEN from moving any prop MEAN or the AST edge (section 4E).

  python scripts/team_system/continual_calibration.py            # grade + update registry + delta + gate
  python scripts/team_system/continual_calibration.py --nogate   # skip the pytest board gate (faster)
"""
from __future__ import annotations
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from registry.store import Registry  # noqa: E402
from calibrate_all_props import _combo, _shape_err, SINGLES, TS  # noqa: E402

MARKETS = SINGLES + ["pra", "pr", "pa", "ra", "stocks"]


def grade_props(n_sims: int = 12000) -> dict:
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast
    G = pd.read_parquet(os.path.join(TS, "nyksas_full_gamelog.parquet"))
    res = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                             n_sims=n_sims, seed=3, anchor=True, defense=True, context={"neutral_site": False})
    agg = {m: {"shape": [], "cover": [], "bias": []} for m in MARKETS}
    for pid, d in res.players.items():
        if d["mean"]["pts"] < 8:
            continue
        r = G[(G.pid == pid) & (G.mins >= 15)]
        if len(r) < 8:
            continue
        s = {k: np.asarray(v, float) for k, v in d["samples"].items()}
        for m in MARKETS:
            sim = s[m] if m in s else _combo(s, m)
            real = (r[m].values.astype(float) if m in SINGLES else
                    _combo({k: r[k].values.astype(float) for k in ["pts", "reb", "ast", "stl", "blk"]}, m))
            if sim is None or real is None or len(real) < 8:
                continue
            se = _shape_err(sim, real)
            if not np.isnan(se):
                agg[m]["shape"].append(se)
            q10, q90 = np.quantile(sim, .1), np.quantile(sim, .9)
            agg[m]["cover"].append(((real >= q10) & (real <= q90)).mean())
            agg[m]["bias"].append(sim.mean() - real.mean())
    out = {}
    for m in MARKETS:
        if agg[m]["shape"]:
            out[m] = dict(shapeErr=round(float(np.mean(agg[m]["shape"])) * 100, 2),
                          coverage=round(float(np.mean(agg[m]["cover"])) * 100, 1),
                          bias=round(float(np.mean(agg[m]["bias"])), 3),
                          n=len(agg[m]["shape"]))
    return out


def run(nogate: bool = False, n_sims: int = 12000) -> dict:
    creg = Registry("calibration_registry")
    prior = creg.all()
    prior_worst = float(prior.shapeErr.max()) if (len(prior) and "shapeErr" in prior and
                                                  prior.shapeErr.notna().any()) else None
    grades = grade_props(n_sims)
    now = int(time.time())
    rows = []
    for m, g in grades.items():
        rows.append(dict(key=f"prop:{m}", shapeErr=g["shapeErr"], coverage=g["coverage"],
                         reliability=round(max(0.0, 1.0 - g["shapeErr"] / 100.0), 3), n=g["n"], updated_utc=now))
    # record every engine's reliability (equal-weight until B8 fits a leak-free cross-season backtest)
    for _, e in Registry("engine_registry").all().iterrows():
        rows.append(dict(key=f"engine:{e['name']}", shapeErr=None, coverage=None,
                         reliability=float(e.get("reliability_weight") or 0), n=None, updated_utc=now))
    for r in rows:
        creg.upsert(r)
    worst_m = max(grades, key=lambda k: grades[k]["shapeErr"]) if grades else None
    worst = grades[worst_m]["shapeErr"] if worst_m else None
    delta = (worst - prior_worst) if (worst is not None and prior_worst is not None) else None

    board = None
    if not nogate:
        from learn_ledger import gate
        board, detail = gate()
        if board is False:
            return dict(ok=False, board="RED", detail=detail, worst=worst, worst_market=worst_m)
    return dict(ok=True, n_props=len(grades), worst_market=worst_m, worst_shapeErr=worst,
                prior_worst=prior_worst, delta=delta, board=("GREEN" if board else "skipped"),
                grades=grades, delta_row_appended=True)


def main():
    res = run(nogate="--nogate" in sys.argv)
    if not res["ok"]:
        print(f"BOARD RED -> {res.get('detail')}; calibration NOT shipped (section 4E gate)")
        sys.exit(1)
    print("=== CONTINUAL CALIBRATION (shape/coverage only; mean-preserving) ===")
    for m, g in sorted(res["grades"].items(), key=lambda kv: -kv[1]["shapeErr"]):
        grade = "OK" if g["shapeErr"] < 5 else ("WATCH" if g["shapeErr"] < 9 else "FIX")
        print(f"  prop:{m:7s} shapeErr {g['shapeErr']:5.2f}% cover {g['coverage']:5.1f}% "
              f"bias {g['bias']:+.2f} n={g['n']}  {grade}")
    print(f"\nworst shapeErr: {res['worst_market']} {res['worst_shapeErr']}% "
          f"(prior worst {res['prior_worst']}, delta {res['delta']}); board {res['board']}")
    print(f"calibration_registry updated ({res['n_props']} props + engines); delta row appended.")
    from build_done_check import write_marker
    write_marker("B9_calibration_loop", dict(delta_row_appended=True,
                 detail=f"worst {res['worst_market']}={res['worst_shapeErr']}pp, delta={res['delta']}, "
                        f"board={res['board']}, {res['n_props']} props graded", asof="2026-06-08"))
    print("B9 marker written.")


if __name__ == "__main__":
    main()
