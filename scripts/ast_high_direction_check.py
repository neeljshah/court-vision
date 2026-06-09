"""ast_high_direction_check.py — does AST-OVER survive the shipped ast_high gate?

edge_direction_temporal.py found AST-OVER is early-negative (-9.85%) while AST-UNDER is
positive in both halves (+8.39% / +15.36%). But the SHIPPED policy (ast_high) already
filters to edge>=0.75 + line<=7.5. The real question for a policy change: after that gate,
is AST-OVER still the weak half, or does high-conviction fix it? Tests the exact shipped
gate (src.prediction.bet_policy) split by direction x temporal half.

Decision rule (pre-registered): add a direction restriction ONLY if AST-OVER is negative
on the EARLY (tuning) half under the gate AND AST-UNDER is positive in BOTH halves. That is
a held-out-clean refinement, not a data-snoop, because the direction split is chosen on the
early half and graded on the late half.

Real benashkar closes, actual posted odds. No production model touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle)

EDGE_MIN = 0.75   # ast_high
LINE_CAP = 7.5    # ast_high


def gated_ast():
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    out = []
    for b in raw:
        if b["stat"] != "ast":
            continue
        if abs(b["pred_oof"] - b["line"]) < EDGE_MIN:
            continue
        if b["line"] > LINE_CAP:
            continue
        out.append(b)
    return sorted(out, key=lambda b: b["gdate"])


def roi(rows):
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    return n, sum(int(w) for _, w, _ in rows) / n * 100, sum(p for _, _, p in rows) / (n * 100) * 100


def fmt(label, rows):
    n, win, r = roi(rows)
    return f"{label:18s} n={n:4d}  win={win:5.1f}%  ROI={r:+7.2f}%"


def main():
    bets = gated_ast()
    if not bets:
        print("no gated AST bets")
        return 1
    mid = bets[len(bets) // 2]["gdate"]
    rows = []
    for b in bets:
        s = settle(b, b["pred_oof"])
        if s is None:
            continue
        over, won, pay = s
        rows.append((b, over, won, pay))

    def sub(half=None, direction=None):
        out = []
        for b, over, won, pay in rows:
            if half == "early" and b["gdate"] >= mid:
                continue
            if half == "late" and b["gdate"] < mid:
                continue
            if direction == "over" and not over:
                continue
            if direction == "under" and over:
                continue
            out.append((over, won, pay))
        return out

    print(f"ast_high gate (edge>={EDGE_MIN}, line<={LINE_CAP}): n={len(rows)}  "
          f"span {bets[0]['gdate'].date()}..{bets[-1]['gdate'].date()}  mid={mid.date()}\n")
    print(fmt("ALL", sub()))
    print(fmt("  OVER", sub(direction="over")) + "   |   " + fmt("UNDER", sub(direction="under")))
    print(fmt("early", sub("early")) + "   |   " + fmt("late", sub("late")))
    print(fmt("  early-OVER", sub("early", "over")) + "   |   " + fmt("early-UNDER", sub("early", "under")))
    print(fmt("  late-OVER", sub("late", "over")) + "   |   " + fmt("late-UNDER", sub("late", "under")))

    eo = roi(sub("early", "over"))[2]
    eu = roi(sub("early", "under"))[2]
    lu = roi(sub("late", "under"))[2]
    lo = roi(sub("late", "over"))[2]
    print("\n── DECISION ──")
    over_robust = eo > 0 and lo > 0
    under_robust = eu > 0 and lu > 0
    print(f"  AST-OVER  robust (both halves >0)? {over_robust}  (early {eo:+.1f}% / late {lo:+.1f}%)")
    print(f"  AST-UNDER robust (both halves >0)? {under_robust}  (early {eu:+.1f}% / late {lu:+.1f}%)")
    if under_robust and not over_robust:
        print("  -> RECOMMEND: restrict ast_high to UNDER (OVER is not robust under the gate).")
    elif over_robust and under_robust:
        print("  -> KEEP both directions (high-conviction gate fixes the OVER weakness).")
    else:
        print("  -> INCONCLUSIVE under the gate; do not change the shipped policy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
