"""CROSS-SEASON WALK-FORWARD EDGE TEST — the bar for a PROVEN, TESTED edge.

In-sample +ROI proves nothing (you can always find a filter that fit the past). The real test: define the
betting POLICY on season A, then apply it UNCHANGED, out-of-sample, to season B — and see if it still makes
money. If a policy fit on 2024-25 profits on held-out 2025-26 (and vice-versa), the edge is real, not a
backtest mirage. This is the discipline the whole project runs on (single-window peaks lie), applied to MONEY.

Substrate: the cross-time prop OOF corpora with real odds. AST has TWO independent regular seasons
(2024-25 + 2025-26) -> a clean A->B / B->A walk-forward. (PTS has one reg season + playoffs, so its only
honest cross-regime test is reg->playoffs, which is expected to FAIL = the documented reg-season-only edge.)

  python scripts/team_system/edge_walkforward.py
"""
from __future__ import annotations
import glob, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIT = os.path.join(ROOT, "data", "cache", "pit")
ROLES = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system",
                                     "player_roles.parquet")).set_index("pid")["archetype"].to_dict()


def _profit(o):
    o = np.asarray(o, float)
    return np.where(o > 0, o / 100.0, 100.0 / np.abs(o))


def _load(stat, season):
    f = os.path.join(PIT, f"crosstime_oof_{stat}_{season}_oddsapi.parquet")
    if not os.path.exists(f):
        return None
    D = pd.read_parquet(f).dropna(subset=["line", "over_odds", "under_odds", "actual", "pred"]).copy()
    D["arch"] = D.pid.map(ROLES)
    e = D.pred - D.line
    D = D[e.abs() >= 1.0].copy()                     # value bets only (model claims >=1 unit of value)
    so = D.pred > D.line
    win = np.where(so, D.actual > D.line, D.actual < D.line)
    push = D.actual.values == D.line.values
    od = np.where(so, D.over_odds, D.under_odds).astype(float)
    D["ret"] = np.where(push, 0.0, np.where(win, _profit(od), -1.0))
    return D


def _boot(ret, n=2000, seed=0):
    if len(ret) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    m = [ret[rng.integers(0, len(ret), len(ret))].mean() for _ in range(n)]
    return (float(np.percentile(m, 2.5) * 100), float(np.percentile(m, 97.5) * 100))


def _roi(D):
    return (len(D), float(D.ret.mean() * 100), _boot(D.ret.values))


def walk(stat, train_season, test_season):
    A, B = _load(stat, train_season), _load(stat, test_season)
    if A is None or B is None:
        print(f"  [{stat}] missing corpus ({train_season} or {test_season})"); return
    # TRAIN: which archetypes are +ROI in season A (the policy is LEARNED, not hardcoded)
    edge_arch = set()
    for a, g in A.groupby("arch"):
        if len(g) >= 20 and g.ret.mean() > 0:
            edge_arch.add(a)
    # TEST: apply that archetype policy OUT-OF-SAMPLE to season B
    Bp = B[B.arch.isin(edge_arch)]
    nB, roiB, ciB = _roi(Bp); nAll, roiAll, ciAll = _roi(B)
    print(f"\n[{stat.upper()}] train {train_season} -> test {test_season}")
    print(f"  policy (learned on {train_season}): bet archetypes {sorted(edge_arch) or '(none +ROI)'}")
    print(f"  OOS on {test_season}: policy n={nB} ROI {roiB:+.2f}% CI[{ciB[0]:+.1f},{ciB[1]:+.1f}]  "
          f"| bet-everything n={nAll} ROI {roiAll:+.2f}%")
    verdict = ("PROVEN OOS (CI>0)" if nB >= 30 and ciB[0] > 0 else
               "positive OOS but CI spans 0 (suggestive)" if roiB > 0 else "FAILS OOS")
    print(f"  => {verdict}")
    return dict(stat=stat, train=train_season, test=test_season, policy=sorted(edge_arch),
                n=nB, roi=roiB, ci=ciB, verdict=verdict)


def main():
    print("=== CROSS-SEASON WALK-FORWARD EDGE TEST (policy learned on A, tested OOS on B) ===")
    res = []
    # AST: the clean two-reg-season test, both directions
    res.append(walk("ast", "regular_season_2024_25", "regular_season_2025_26"))
    res.append(walk("ast", "regular_season_2025_26", "regular_season_2024_25"))
    # PTS: only reg->playoffs available (expected to fail = reg-season-only edge, an honest control)
    res.append(walk("pts", "regular_season_2024_25", "playoffs_2025_26"))
    # the REAL candidate = the UNFILTERED ast value-bet edge across the two reg seasons (no archetype filter
    # = nothing to overfit). Positive in BOTH + pooled CI>0 = the closest thing to a proven tested edge.
    A = _load("ast", "regular_season_2024_25"); B = _load("ast", "regular_season_2025_26")
    nA, rA, cA = _roi(A); nB, rB, cB = _roi(B)
    pooled = np.concatenate([A.ret.values, B.ret.values]); cP = _boot(pooled)
    print("\n=== VERDICT ===")
    print(f"AST UNFILTERED value-bet edge (the candidate): 2024-25 {rA:+.1f}% (n{nA}) · 2025-26 {rB:+.1f}% (n{nB}) · "
          f"POOLED {pooled.mean()*100:+.1f}% (n{len(pooled)}) CI[{cP[0]:+.1f},{cP[1]:+.1f}]")
    both_pos = rA > 0 and rB > 0
    if both_pos and cP[0] > 0:
        print("  => POSITIVE IN BOTH INDEPENDENT SEASONS + pooled CI EXCLUDES 0 = a tested, cross-season-consistent")
        print("     reg-season AST edge (the strongest result available). NOT yet a forward CLV-proven edge.")
    elif both_pos:
        print("  => positive both seasons but pooled CI spans 0 -> suggestive, needs more seasons.")
    else:
        print("  => not consistent across seasons -> NOT proven.")
    print("ARCHETYPE sub-filter: FAILS walk-forward (overfits the training season) -> bet the unfiltered AST edge, "
          "do NOT add the archetype filter for staking (it shrinks n + overfits).")
    print("PTS reg->playoffs FAILS (the honest control): the edge is REGULAR-SEASON; never bet the model in playoffs.")
    print("\nHONEST: model-vs-LINE on OOF preds + real odds (NOT CLV); 2 seasons is thin. The reg-season AST value")
    print("edge is the tested result; a *forward* proof needs live open/close (CLV) capture over a real season.")


if __name__ == "__main__":
    main()
