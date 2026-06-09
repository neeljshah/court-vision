"""Pre-registered edge-concentration / selection conditioners on the AST book.

The campaign lesson: point features reject; wins are SELECTION/SIZING on the AST
edge. H1 (pace) confirmed. Here we test two MORE pre-registered mechanisms on the
primary coherent window (extended_oos), both temporal halves:

  C-nout : teammate(s) ruled OUT (n_out>0) -> the playmaker inherits ball-handling
           -> AST volume up & model may under-account. PRE-REG: AST edge stronger
           when n_out>0.  (workstream #5: role re-assignment, not vacated volume.)
  C-stab : role stability (low std_min) -> the model's projection is more reliable
           -> its AST edge should be sharper.  PRE-REG: low-std_min AST ROI > high.

Bar: must hold in BOTH halves with the pre-registered sign, on a non-trivial n,
else REJECT (thin sub-splits + multiple comparisons => skeptical).
"""
from __future__ import annotations

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402


def gated_ast(bets):
    out = []
    for b in bets:
        if b["stat"] != "ast":
            continue
        p = b.get("pred")
        if p is None or not np.isfinite(p):
            continue
        if abs(p - b["line"]) < 0.75 or b["line"] > 7.5:
            continue
        out.append(b)
    return out


def all_ast(bets):
    return [b for b in bets if b["stat"] == "ast" and np.isfinite(b.get("pred", np.nan))]


def halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def split_report(label, bets, keyfn, names):
    groups = {nm: [] for nm in names}
    for b in bets:
        g = keyfn(b)
        if g in groups:
            groups[g].append(b)
    parts = []
    for nm in names:
        r = ig.roi(groups[nm], predictor="pred")
        parts.append(f"{nm}={r['roi_pct']:+.1f}%(n{r['n']},w{r['win_pct']:.0f})")
    print(f"    {label}: " + "  ".join(parts))
    return {nm: ig.roi(groups[nm], predictor="pred") for nm in names}


def nout_key(b):
    v = b.get("n_out", np.nan)
    if not np.isfinite(v):
        return "na"
    return "out>0" if v > 0 else "out=0"


def make_stab_key(bets):
    sm = np.array([b.get("std_min", np.nan) for b in bets], float)
    med = np.nanmedian(sm[np.isfinite(sm)])

    def k(b):
        v = b.get("std_min", np.nan)
        if not np.isfinite(v):
            return "na"
        return "low_std" if v <= med else "high_std"
    return k, med


def run(corpus):
    print(f"\n{'='*68}\n {corpus}\n{'='*68}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f" coherence {coh['sum']:+.1f}% ({'OK' if coh['coherent'] else 'CORRUPT'})")
    for setname, sel in [("GATED-AST", gated_ast), ("ALL-AST", all_ast)]:
        sub = sel(bets)
        e, l = halves(sub)
        print(f"\n  [{setname}] n={len(sub)}")
        print("   C-nout (PRE-REG: out>0 stronger):")
        split_report("full", sub, nout_key, ["out>0", "out=0"])
        split_report("early", e, nout_key, ["out>0", "out=0"])
        split_report("late", l, nout_key, ["out>0", "out=0"])
        kstab, med = make_stab_key(sub)
        print(f"   C-stab (PRE-REG: low_std > high_std)  [std_min median={med:.1f}]:")
        split_report("full", sub, kstab, ["low_std", "high_std"])
        ke, _ = make_stab_key(e)
        kl, _ = make_stab_key(l)
        split_report("early", e, ke, ["low_std", "high_std"])
        split_report("late", l, kl, ["low_std", "high_std"])


if __name__ == "__main__":
    run("extended_oos_canonical.csv")
