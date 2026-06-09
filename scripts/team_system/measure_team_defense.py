"""Is there a TEAM-SCHEME defense residual beyond personnel? (opponent-controlled paired test)

Frontier #2 asks whether the sim's personnel-summed team defense (rim_d/perim_d from individual
ratings) under-credits scheme defense (the hypothesis: NYK defends better than its rim-protector-poor
personnel implies). The clean test avoids the sparse-opponent problem: teams that played BOTH NYK and
SAS form a PAIRED sample -- for each such opponent, compare its points-per-100 vs NYK vs its
points-per-100 vs SAS. The opponent's own offense cancels in the pairing, so the difference is pure
NYK-vs-SAS defensive quality, opponent-controlled. Then compare to what personnel predicts.

  python scripts/team_system/measure_team_defense.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
MINE = {"NYK", "SAS"}


def main():
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    # opponent points-per-100 against each of NYK/SAS (the opponent is the row whose team == opp)
    # team_game has one row per (game, team): opp_pts/opp_poss = what THAT team allowed.
    allowed = defaultdict(lambda: defaultdict(list))   # defender_tri -> opp_tri -> [pts/100 allowed]
    for r in tg.itertuples(index=False):
        if r.team not in MINE:
            continue
        if r.opp_poss and r.opp_poss > 50:
            allowed[r.team][r.opp].append(100.0 * r.opp_pts / r.opp_poss)

    # paired over opponents that faced BOTH NYK and SAS
    opps = set(allowed["NYK"]) & set(allowed["SAS"])
    rows = []
    for o in sorted(opps):
        vn = np.mean(allowed["NYK"][o]); vs = np.mean(allowed["SAS"][o])
        rows.append((o, vn, vs, len(allowed["NYK"][o]), len(allowed["SAS"][o])))
    print("=== TEAM-SCHEME DEFENSE: opponent-controlled paired test (pts/100 allowed) ===\n")
    print(f"  {len(opps)} opponents faced BOTH NYK and SAS (regular season + playoffs)\n")
    diffs = []
    for o, vn, vs, nn, ns in rows:
        diffs.append(vn - vs)
    diffs = np.array(diffs)
    print(f"  mean pts/100 allowed vs NYK: {np.mean([r[1] for r in rows]):.1f}")
    print(f"  mean pts/100 allowed vs SAS: {np.mean([r[2] for r in rows]):.1f}")
    print(f"  paired diff (NYK - SAS): {diffs.mean():+.2f} pts/100  (>0 => NYK allows MORE => SAS better D)")
    # paired significance (sign + bootstrap)
    rng = np.random.default_rng(7); n = len(diffs)
    boot = np.array([diffs[rng.integers(0, n, n)].mean() for _ in range(5000)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"    95% CI [{lo:+.2f}, {hi:+.2f}]  |  SAS defends better for {100*(diffs>0).mean():.0f}% of opponents")

    # what personnel predicts
    nyk, sas = TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")
    print(f"\n  PERSONNEL prediction (TeamModel): NYK rim_d {nyk.rim_d:.0f}/perim {nyk.perim_d:.0f}  |  "
          f"SAS rim_d {sas.rim_d:.0f}/perim {sas.perim_d:.0f}")
    print(f"    => personnel says {'SAS' if (sas.rim_d+sas.perim_d) > (nyk.rim_d+nyk.perim_d) else 'NYK'} "
          f"is the better defense (higher D ratings).")
    actual_better = "SAS" if diffs.mean() > 0 else "NYK"
    pers_better = "SAS" if (sas.rim_d + sas.perim_d) > (nyk.rim_d + nyk.perim_d) else "NYK"
    print(f"\n  VERDICT: opponent-controlled actual says {actual_better} is better; personnel says {pers_better}.")
    print(f"  {'AGREE -> no scheme residual; deferral confirmed.' if actual_better == pers_better else 'DISAGREE -> a real scheme residual exists; build the team-scheme blend.'}")


if __name__ == "__main__":
    main()
