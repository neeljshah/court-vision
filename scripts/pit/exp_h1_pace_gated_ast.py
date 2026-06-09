"""H1: does opp_pace concentrate the GATED ast_high edge, robustly + leak-free?

The proposed wiring is a Kelly tilt / soft selection on AST bets that pass the
shipped ast_high gate (|pred-line|>=0.75 AND line<=7.5), conditioned on high
opp_pace tercile. EX-9/MEMORY claims +43.8% (n=73) high vs +6.7% low+mid on the
benashkar window. Re-validate: extended_oos (both halves) + cross-season 2024-25
+ playoffs (must break). Pace terciles are computed on the GATED bets.

Skeptic's bars: high-pace must beat low+mid in BOTH halves; the gated-high n must
be non-trivial; magnitude must be treated as regime-inflated (size on durable
core, not the peak); AST in playoffs must be excluded.
"""
from __future__ import annotations

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

GATE_EDGE = 0.75
GATE_LINE_MAX = 7.5


def gated_ast(bets):
    out = []
    for b in bets:
        if b["stat"] != "ast":
            continue
        pred = b.get("pred")
        if pred is None or not np.isfinite(pred):
            continue
        if abs(pred - b["line"]) < GATE_EDGE:
            continue
        if b["line"] > GATE_LINE_MAX:
            continue
        if not np.isfinite(b.get("opp_pace", np.nan)):
            continue
        out.append(b)
    return out


def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def pace_split(gated, pace_thresh=None):
    """High = top opp_pace tercile (or > fixed thresh); low+mid = rest."""
    if not gated:
        return [], []
    pace = np.array([b["opp_pace"] for b in gated], float)
    thr = pace_thresh if pace_thresh is not None else np.nanpercentile(pace, 66.667)
    high = [b for b in gated if b["opp_pace"] > thr]
    lowmid = [b for b in gated if b["opp_pace"] <= thr]
    return high, lowmid, thr


def report(label, bets):
    gated = gated_ast(bets)
    if len(gated) < 20:
        print(f"  [{label}] gated AST n={len(gated)} (too few)")
        return
    full = ig.roi(gated, predictor="pred")
    high, lowmid, thr = pace_split(gated)
    rh = ig.roi(high, predictor="pred")
    rl = ig.roi(lowmid, predictor="pred")
    print(f"  [{label}] gated AST n={len(gated)} ROI {full['roi_pct']:+.1f}% | "
          f"pace_thr={thr:.1f} | HIGH {rh['roi_pct']:+.1f}%(n{rh['n']},win{rh['win_pct']:.0f}) "
          f"vs LOW+MID {rl['roi_pct']:+.1f}%(n{rl['n']})  diff={rh['roi_pct']-rl['roi_pct']:+.1f}pp")
    return thr


if __name__ == "__main__":
    print("=== extended_oos (primary, reg+2026po mixed) ===")
    prim = ig.prepare("extended_oos_canonical.csv")
    thr = report("FULL", prim)
    early, late = split_halves(prim)
    print("  both-halves (high-pace must win BOTH):")
    report("EARLY", early)
    report("LATE", late)

    print("\n=== cross-season 2024-25 (independent) ===")
    cross = ig.prepare("regular_season_2024_25_oddsapi.csv")
    report("2024-25", cross)

    print("\n=== 2026 PLAYOFFS (must break / exclude) ===")
    po = ig.prepare("playoffs_2024_canonical.csv")
    report("PO2024", po)
