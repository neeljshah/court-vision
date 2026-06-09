"""DEMONSTRATION: do transition signals that REJECT individually lift as a CLUSTER (a domain model)?

The user's insight (correct): a single signal can fail the marginal gate alone yet carry real signal in
COMBINATION with related signals -- 'a jump of transition signals -> a transition model'. This tests it
honestly on the 560k-possession legacy corpus, leak-free, per independent season:

  base            = [period, grem]                       (pure game-state)
  each individual = base + ONE transition signal         (the marginal gate -- one at a time)
  the CLUSTER     = base + [poss_dur, after_to, dead_ball] (the 'transition/origin MODEL' -- together)

If the cluster's OOS lift exceeds the BEST individual's, then composing weak-but-related signals into a
model beats gating them one-at-a-time -- exactly the user's point. The catch (honesty): the cluster is ONE
registered, ONE FDR-counted test (model_id = hash of its signal set), and it must still REPLICATE across BOTH
seasons -- you don't get to try 1000 combinations free.

  python scripts/team_system/demo_transition_cluster.py
"""
from __future__ import annotations
import math
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY = os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")
BASE = ["period", "grem"]
TRANSITION = ["poss_dur", "after_to", "dead_ball"]   # the transition/origin family
SEASONS = ("2022-23", "2023-24")


def _oos_rmse(S: pd.DataFrame, feats: list, seed: int = 0) -> float:
    gids = np.array(sorted(S.gid.unique())); rng = np.random.default_rng(seed); rng.shuffle(gids)
    errs = []
    for fold in np.array_split(gids, 5):
        te = S[S.gid.isin(fold)]; tr = S[~S.gid.isin(fold)]
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                          min_samples_leaf=80, random_state=seed)
        m.fit(tr[feats], tr.pts)
        errs.append(math.sqrt(np.mean((m.predict(te[feats]) - te.pts.values) ** 2)))
    return float(np.mean(errs))


def main():
    D = pd.read_parquet(LEGACY)
    D = D[(D.pts <= 4) & (D.poss_dur >= 0)]
    print("=== TRANSITION: individual signals vs the CLUSTER (leak-free, per season) ===\n")
    print(f"{'season':9s} {'config':22s} {'base_rmse':>9s} {'full_rmse':>9s} {'rel_lift':>9s}")
    cluster_repl = 0
    best_single_repl = {f: 0 for f in TRANSITION}
    for season in SEASONS:
        S = D[D.season == season]
        if S.gid.nunique() < 50:
            continue
        base = _oos_rmse(S, BASE)
        # individuals
        rels = {}
        for f in TRANSITION:
            full = _oos_rmse(S, BASE + [f])
            rel = (full - base) / base
            rels[f] = rel
            if rel < -0.002:
                best_single_repl[f] += 1
            print(f"{season:9s} {'base + ' + f:22s} {base:9.4f} {full:9.4f} {rel:+8.3%}")
        # the cluster (the transition MODEL)
        full_c = _oos_rmse(S, BASE + TRANSITION)
        rel_c = (full_c - base) / base
        if rel_c < -0.002:
            cluster_repl += 1
        best_single = min(rels.values())
        print(f"{season:9s} {'base + CLUSTER(3)':22s} {base:9.4f} {full_c:9.4f} {rel_c:+8.3%}  "
              f"(best single {best_single:+.3%}; cluster beats best single: {rel_c < best_single})")
        print()
    print("=== VERDICT ===")
    for f in TRANSITION:
        print(f"  individual '{f}': replicates {best_single_repl[f]}/2 seasons")
    print(f"  CLUSTER (transition model): replicates {cluster_repl}/2 seasons")
    print("\nREAD: if a signal is 0/2 alone but the cluster is 2/2 and beats the best single, composing weak")
    print("related signals into a domain MODEL beats one-at-a-time gating -- validated as ONE cross-season unit.")


if __name__ == "__main__":
    main()
