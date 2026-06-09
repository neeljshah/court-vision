"""ast_opponent_conditioning.py — does opponent pace / defense sharpen the AST edge?

Lever-1 question (docs/VS_VEGAS_ASSESSMENT.md): is a multi-day opponent-positional-defense
build worth it for the bettable book? The bettable book is AST. So: condition the shipped
ast_high AST bets (edge>=0.75, line<=7.5) on the opponent context ALREADY available
(opp_pace, opp_def in calibration_frame_v2) and see if any slice is robustly larger.

Mechanism (pre-registered): assists scale with possessions, so the AST edge should be
LARGER in high-pace games; weak opponent defense (high opp_def rating) => more made shots
=> more assist conversion. If neither conditions the edge robustly across BOTH temporal
halves, a finer positional-defense feature is unlikely to pay off for AST betting.

Robustness bar: a slice "wins" only if early ROI > 0 AND late ROI > 0. Real benashkar
closes, actual posted odds. No production model touched. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle)

EDGE_MIN, LINE_CAP = 0.75, 7.5
FRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"


def gated_ast_with_context():
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    bets = [b for b in raw if b["stat"] == "ast"
            and abs(b["pred_oof"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    df = pd.read_parquet(FRAME)
    df = df[df["stat"] == "ast"][["player_id", "date", "opp_pace", "opp_def"]]
    ctx = {(int(r.player_id), r.date): (r.opp_pace, r.opp_def) for r in df.itertuples(index=False)}
    out = []
    for b in bets:
        c = ctx.get((b["pid"], b["gdate"].strftime("%Y-%m-%d")))
        if c is None or any(pd.isna(x) for x in c):
            continue
        b["opp_pace"], b["opp_def"] = float(c[0]), float(c[1])
        out.append(b)
    return sorted(out, key=lambda b: b["gdate"])


def roi(rows):
    if not rows:
        return 0, 0.0, 0.0
    n = len(rows)
    return n, sum(int(w) for _, w in rows) / n * 100, sum(p for _, p in rows) / (n * 100) * 100


def main():
    bets = gated_ast_with_context()
    mid = bets[len(bets) // 2]["gdate"]
    settled = []
    for b in bets:
        s = settle(b, b["pred_oof"])
        if s is None:
            continue
        _, won, pay = s
        settled.append((b, (won, pay)))
    print(f"gated AST w/ opp context: n={len(settled)}  "
          f"join {len(settled)}/{len(bets)}  mid={mid.date()}\n")

    def report(key, label):
        vals = np.array([b[key] for b, _ in settled])
        t1, t2 = np.percentile(vals, [33.33, 66.67])
        buckets = {
            f"low {label} (<= {t1:.1f})":   lambda v: v <= t1,
            f"mid {label}":                 lambda v: t1 < v <= t2,
            f"high {label} (> {t2:.1f})":   lambda v: v > t2,
        }
        print(f"── conditioned on {label} (terciles {t1:.2f}/{t2:.2f}) ──")
        print(f"  {'slice':28s} {'all ROI(n)':>14s} {'early ROI(n)':>16s} {'late ROI(n)':>16s}  robust")
        for name, pred in buckets.items():
            allr = [s for b, s in settled if pred(b[key])]
            er = [s for b, s in settled if pred(b[key]) and b["gdate"] < mid]
            lr = [s for b, s in settled if pred(b[key]) and b["gdate"] >= mid]
            na, _, ra = roi(allr)
            ne, _, re = roi(er)
            nl, _, rl = roi(lr)
            rob = "YES" if (re > 0 and rl > 0) else "no"
            print(f"  {name:28s} {ra:+6.1f}% ({na:3d}) {re:+7.1f}% ({ne:3d}) {rl:+7.1f}% ({nl:3d})  {rob}")
        print()

    report("opp_pace", "pace")
    report("opp_def", "def(hi=weak)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
