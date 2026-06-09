"""gate1_filtered_vs_vegas.py — does the SHIPPED filter stack beat real Vegas?

run_gate1_full_analysis.py grades the production OOF predictions against real
DK/FD/MGM/BetRivers closing lines, but it bets EVERYTHING past a flat edge cut.
That unfiltered reading is -2.00% ROI (4,221 bets) — the strawman.

The shipped product does NOT bet everything. It applies the post-Iter-57 filter
stack in src/prediction/bet_thresholds.py:
  1. edge_threshold_for(stat)          — per-stat min |pred - line|
  2. allowed_directions_for(stat)      — BLK under-only (Iter-51)
  3. is_line_excluded(stat, line)      — zero-EV line buckets (Iter-54)
  4. is_direction_line_excluded(...)   — 2D direction x bucket (Iter-55/57)

This script applies that EXACT stack to the SAME real-Vegas bet universe loaded
by run_gate1_full_analysis, so we get an apples-to-apples answer to the only
question that matters: does the shipped edge survive on real closing lines?

No model is touched. Pure grading. Output -> data/cache/gate1_filtered_vs_vegas.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Reuse the exact loaders/grading the canonical harness uses.
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_playoffs_2024_bets,
    load_benashkar_bets,
    attach_actuals_and_l10,
    attach_oof,
    settle,
)
from src.prediction.bet_thresholds import (  # noqa: E402
    edge_threshold_for,
    allowed_directions_for,
    is_line_excluded,
    is_direction_line_excluded,
)

_OUT = _ROOT / "data" / "cache" / "gate1_filtered_vs_vegas.json"


def passes_filter_stack(stat: str, pred: float, line: float) -> bool:
    """True iff this bet survives the full shipped Iter-57 filter stack."""
    edge = abs(pred - line)
    if edge < edge_threshold_for(stat):
        return False
    direction = "over" if pred > line else "under"
    if direction not in allowed_directions_for(stat):
        return False
    if is_line_excluded(stat, line):
        return False
    if is_direction_line_excluded(stat, direction, line):
        return False
    return True


def aggregate_filtered(bets, predictor_key):
    by_stat = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
    total_n = total_w = 0
    total_pnl = 0.0
    for b in bets:
        pred = b.get(predictor_key)
        if pred is None:
            continue
        if not passes_filter_stack(b["stat"], pred, b["line"]):
            continue
        res = settle(b, pred)
        if res is None:
            continue
        _bet_over, won, pnl = res
        total_n += 1
        total_w += int(won)
        total_pnl += pnl
        a = by_stat[b["stat"]]
        a["n"] += 1
        a["w"] += int(won)
        a["pnl"] += pnl
    return {
        "n": total_n,
        "w": total_w,
        "beat_pct": total_w / total_n * 100 if total_n else 0.0,
        "roi_pct": total_pnl / (total_n * 100.0) * 100 if total_n else 0.0,
        "pnl": total_pnl,
        "per_stat": {
            s: {**v,
                "beat_pct": v["w"] / v["n"] * 100 if v["n"] else 0.0,
                "roi_pct": v["pnl"] / (v["n"] * 100.0) * 100 if v["n"] else 0.0}
            for s, v in by_stat.items()
        },
    }


def _print_block(title, r):
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(f"  N={r['n']:,}  beat={r['beat_pct']:.2f}%  ROI={r['roi_pct']:+.2f}%  PnL=${r['pnl']:+,.0f}")
    for stat, v in sorted(r["per_stat"].items()):
        print(f"    {stat:<6} n={v['n']:>6,d}  beat={v['beat_pct']:>6.2f}%  ROI={v['roi_pct']:>+6.2f}%")
    print()


def main():
    print("Loading real-Vegas bet universe (same as run_gate1_full_analysis)...")
    p24 = attach_actuals_and_l10(load_playoffs_2024_bets())
    p2526 = attach_actuals_and_l10(load_benashkar_bets(mainline_only=True))
    p2526_oof = attach_oof(list(p2526))
    print(f"  2024 playoffs: {len(p24):,} | 2025-26 mainline: {len(p2526):,} | "
          f"with prod OOF: {len(p2526_oof):,}\n")

    # The shipped product runs the model (OOF), not L10. Grade prod OOF through
    # the filter stack on the 2025-26 real closes.
    r_oof_filtered = aggregate_filtered(p2526_oof, "pred_oof")
    _print_block("2025-26 real Vegas — PROD OOF + FULL Iter-57 FILTER STACK", r_oof_filtered)

    # For reference: L10 baseline through the same filter (no model edge).
    r_l10_filtered = aggregate_filtered(p24 + p2526, "pred_l10")
    _print_block("Combined real Vegas — L10 baseline + filter stack (reference)", r_l10_filtered)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({
        "p2526_prod_oof_filtered": r_oof_filtered,
        "combined_l10_filtered": r_l10_filtered,
        "filter_stack": "edge_threshold + allowed_directions + line_exclusions + dir_line_exclusions (Iter-51/54/55/57)",
        "bet_universe": "real DK/FD/MGM/BetRivers closing lines (benashkar 2025-26 + reisneriv 2024 playoffs)",
        "note": "Apples-to-apples: shipped filter stack applied to the SAME real-Vegas bets that run_gate1_full_analysis grades unfiltered.",
    }, open(_OUT, "w", encoding="utf-8"), indent=2)
    print(f"Results: {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
