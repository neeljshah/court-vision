"""edge_direction_temporal.py — cross-stat direction decomposition with temporal held-out.

The AST deep-dive (ast_edge_decomposition.py) showed the AST edge is real discrimination
(both directions positive, UNDER +11.4% >> OVER +3.0%) but temporally lumpy (early +0.06%
/ late +13.85%). Two open questions this answers, both with a clean early(tune)/late(held-out)
split so nothing is data-snooped:

  Q1. Is the OVER/UNDER asymmetry ROBUST? If UNDER carries the edge in BOTH halves for AST,
      a direction-aware policy is justified; if it sign-flips, it's noise.
  Q2. Is FG3M a real SECOND edge (to diversify the single-stat book), and on which side?

For each stat: pooled / early / late ROI, split by model direction, + bootstrap CI.
Then a held-out book test: does adding FG3M (or going AST-UNDER-only) beat AST-all out-of-sample?

Real benashkar closes, ACTUAL posted odds. No production model touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle)

RNG = np.random.default_rng(20260601)
STATS = ("ast", "fg3m", "reb", "pts")


def all_bets():
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    return sorted(raw, key=lambda b: b["gdate"])


def settle_model(b):
    r = settle(b, b["pred_oof"])
    if r is None:
        return None
    over, won, pay = r
    return over, won, pay


def roi(rows):
    """rows: list of (over, won, pay). Returns (n, win%, ROI%)."""
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    return n, sum(int(w) for _, w, _ in rows) / n * 100, sum(p for _, _, p in rows) / (n * 100) * 100


def boot_ci(rows, n_boot=4000):
    if not rows:
        return (0.0, 0.0, 1.0)
    pays = np.array([p for _, _, p in rows])
    b = [RNG.choice(pays, size=len(pays), replace=True).sum() / (len(pays) * 100) * 100
         for _ in range(n_boot)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), float((np.array(b) <= 0).mean())


def line(label, rows):
    n, win, r = roi(rows)
    return f"{label:24s} n={n:4d}  win={win:5.1f}%  ROI={r:+7.2f}%"


def main():
    bets = all_bets()
    mid = bets[len(bets) // 2]["gdate"]
    print(f"corpus n={len(bets):,}  span {bets[0]['gdate'].date()}..{bets[-1]['gdate'].date()}  "
          f"mid={mid.date()}\n")

    for stat in STATS:
        sb = [(b, settle_model(b)) for b in bets if b["stat"] == stat]
        sb = [(b, s) for b, s in sb if s is not None]
        allr = [s for _, s in sb]
        over = [s for _, s in sb if s[0]]
        under = [s for _, s in sb if not s[0]]
        early = [s for b, s in sb if b["gdate"] < mid]
        late = [s for b, s in sb if b["gdate"] >= mid]
        eo = [s for b, s in sb if b["gdate"] < mid and s[0]]
        eu = [s for b, s in sb if b["gdate"] < mid and not s[0]]
        lo = [s for b, s in sb if b["gdate"] >= mid and s[0]]
        lu = [s for b, s in sb if b["gdate"] >= mid and not s[0]]
        cilo, cihi, ple0 = boot_ci(allr)
        print(f"=== {stat.upper()} ===")
        print("  " + line("ALL", allr) + f"   95%CI=[{cilo:+.1f},{cihi:+.1f}] P(<=0)={ple0:.3f}")
        print("  " + line("  OVER", over) + "   |   " + line("UNDER", under))
        print("  " + line("early", early) + "   |   " + line("late", late))
        print("  " + line("  early-OVER", eo) + "   |   " + line("early-UNDER", eu))
        print("  " + line("  late-OVER", lo) + "   |   " + line("late-UNDER", lu))
        print()

    # ── held-out book comparison ─────────────────────────────────────
    # tune nothing on late; just compare candidate books' late-half ROI,
    # requiring each to also be >0 on early (the robustness bar).
    def book(rows_pred):
        return rows_pred
    def select(stats_dirs, half):
        out = []
        for b in bets:
            if (half == "early" and b["gdate"] >= mid) or (half == "late" and b["gdate"] < mid):
                continue
            if b["stat"] not in stats_dirs:
                continue
            s = settle_model(b)
            if s is None:
                continue
            want = stats_dirs[b["stat"]]  # 'both' | 'under' | 'over'
            if want == "under" and s[0]:
                continue
            if want == "over" and not s[0]:
                continue
            out.append(s)
        return out

    candidates = {
        "AST both":          {"ast": "both"},
        "AST under-only":    {"ast": "under"},
        "AST + FG3M both":   {"ast": "both", "fg3m": "both"},
        "AST + FG3M under":  {"ast": "both", "fg3m": "under"},
        "AST under+FG3M und":{"ast": "under", "fg3m": "under"},
    }
    print("── HELD-OUT BOOK COMPARISON (early=tune/sanity, late=held-out) ──")
    print(f"  {'book':22s} {'early ROI(n)':>16s}   {'late ROI(n)':>16s}   robust?")
    for name, sd in candidates.items():
        ne, _, re = roi(select(sd, "early"))
        nl, _, rl = roi(select(sd, "late"))
        robust = "YES" if (re > 0 and rl > 0) else "no"
        print(f"  {name:22s} {re:+7.2f}% (n={ne:4d})   {rl:+7.2f}% (n={nl:4d})   {robust}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
