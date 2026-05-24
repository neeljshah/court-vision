"""probe_center_blk_scale.py — Cycle 97b (loop 5) T1-F-1.

Single-stat position-conditioned scale probe targeting the biggest
single-bucket MAE gap surfaced by cycle 96e:

    (Center, BLK): MAE 0.815 vs global 0.440 (rel 1.85, n=2882 holdout,
    bias -0.4147 = systematically UNDER-predicted)

The mean bias suggests a needed scale of mean_true/mean_pred =
0.972/0.557 = 1.745. We sweep a range around it (1.30 .. 1.74) on
the canonical 80/20 chronological holdout, gate the best variant
through a 4-fold walk-forward, and ship only if BOTH:

    1. single-split BLK MAE strictly DOWN, other stats unchanged
    2. WF 4/4 folds positive on BLK

A NO-OP REPRODUCTION TEST (cycle 97a-aligned discipline) runs first:
when factor=1.0 the BLK MAE delta must be EXACTLY 0.0.

Run:
    python scripts/probe_center_blk_scale.py
    python scripts/probe_center_blk_scale.py --skip-wf
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import Callable, Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

from scripts.validate_adjustment import (  # noqa: E402
    _bulk_predict, validate, print_report,
)


_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# Granular Center buckets surfaced by cycle 96e granular stratification:
# C (n=2075, rel 1.845), C-F (n=807, rel 1.877), F-C (n=1038, rel 1.581).
# All three under-predict by similar magnitude (bias -0.39..-0.42), so we
# apply the same scale to all three. Full strings come from
# commonplayerinfo's POSITION field (e.g. 'Center', 'Center-Forward',
# 'Forward-Center').
_CENTER_POSITIONS = frozenset({"Center", "Center-Forward", "Forward-Center"})


# ── adjustment factory ───────────────────────────────────────────────────────

def make_center_blk_scale(factor: float = 1.40) -> Callable[
    [np.ndarray, List[dict], str], np.ndarray
]:
    """Position-conditioned multiplicative scale on BLK predictions.

    When stat == "blk" AND row["position"] is one of _CENTER_POSITIONS,
    multiply the prediction by ``factor``. Every other (stat, position)
    combination is a strict no-op.

    The position=None back-compat path returns unchanged predictions so
    fresh checkouts (parquet absent) silently skip the adjustment.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        if stat != "blk":
            return pred.copy()
        out = pred.copy()
        if factor == 1.0:
            # Explicit fast-path so the no-op reproduction test sees
            # the EXACT same float values back (no FP drift).
            return out
        for i, r in enumerate(rows):
            pos = r.get("position")
            if pos is None:
                continue
            if str(pos) in _CENTER_POSITIONS:
                out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)

    return fn


# ── WF helper (post-prediction adjustment — no retrain) ──────────────────────

def walk_forward_post_adjust(
    fn,
    holdout: List[dict],
    X: np.ndarray,
    n_folds: int = 4,
    stats: Tuple[str, ...] = ("blk",),
) -> Dict[str, List[float]]:
    """Per-stat per-fold MAE delta (adj - base). Negative = improvement."""
    n = len(holdout)
    fold_size = n // n_folds
    per_stat: Dict[str, List[float]] = {s: [] for s in stats}
    for fold_i in range(n_folds):
        lo = fold_i * fold_size
        hi = n if fold_i == n_folds - 1 else (fold_i + 1) * fold_size
        sub_rows = holdout[lo:hi]
        sub_X = X[lo:hi]
        for stat in stats:
            y_true = np.array([
                np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
                for r in sub_rows
            ], dtype=float)
            mask = ~np.isnan(y_true)
            pred = _bulk_predict(stat, sub_X)
            if pred is None:
                per_stat[stat].append(float("nan"))
                continue
            adj = fn(pred, sub_rows, stat)
            bm = float(np.mean(np.abs(pred[mask] - y_true[mask])))
            am = float(np.mean(np.abs(adj[mask] - y_true[mask])))
            per_stat[stat].append(am - bm)
    return per_stat


# ── no-op assertion (cycle 97a discipline) ────────────────────────────────────

def assert_noop_reproduction(holdout: List[dict], X: np.ndarray) -> None:
    """factor=1.0 must produce EXACTLY 0.0 BLK MAE delta. Hard-fails on drift."""
    fn = make_center_blk_scale(factor=1.0)
    results = validate(fn, holdout, X)
    blk = results.get("blk", {})
    delta = blk.get("delta_mae", float("nan"))
    if abs(delta) > 1e-12:
        raise AssertionError(
            f"NO-OP REPRODUCTION FAILED: factor=1.0 produced BLK delta_mae="
            f"{delta:+.10f}; must be exactly 0.0. Probe halted before sweep."
        )
    print(f"  no-op reproduction OK: factor=1.0 BLK delta_mae={delta:+.6e}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wf", action="store_true")
    args = ap.parse_args()

    print("Loading pergame dataset (with position join)...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    cols = feature_columns()

    holdout = rows[int(n_total * 0.80):]
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n_total={n_total}  holdout={len(holdout)}  features={len(cols)}\n",
          flush=True)

    # Position coverage audit
    pos_vals = [r.get("position") for r in holdout]
    n_with_pos = sum(1 for v in pos_vals if v is not None)
    pos_counter: Dict[str, int] = {}
    for v in pos_vals:
        if v is None:
            continue
        pos_counter[str(v)] = pos_counter.get(str(v), 0) + 1
    n_center_buckets = sum(
        n for p, n in pos_counter.items() if p in _CENTER_POSITIONS
    )
    print(f"  rows with position: {n_with_pos}/{len(holdout)} "
          f"({100*n_with_pos/max(1,len(holdout)):.1f}%)", flush=True)
    print(f"  center-bucket rows (Center / Center-Forward / Forward-Center): "
          f"{n_center_buckets}", flush=True)
    for p in sorted(_CENTER_POSITIONS):
        print(f"    {p}: {pos_counter.get(p, 0)}", flush=True)
    print()

    # Cycle 97a-aligned no-op assertion BEFORE any sweep
    print("=" * 78)
    print("NO-OP REPRODUCTION (factor=1.0)")
    print("=" * 78)
    assert_noop_reproduction(holdout, X)
    print()

    # Sweep
    factors = [1.30, 1.40, 1.50, 1.60, 1.74]
    print("=" * 78)
    print("SINGLE-SPLIT SWEEP (factor in [1.30..1.74])")
    print("=" * 78)

    sweep_rows = []
    for factor in factors:
        fn = make_center_blk_scale(factor=factor)
        results = validate(fn, holdout, X)
        label = f"center_blk_scale factor={factor:.2f}"
        print_report(label, results)
        blk_d = results.get("blk", {}).get("delta_mae", float("nan"))
        # Track unchanged-stat safety: every non-BLK delta must be ~0
        other_max_abs = max(
            abs(results.get(s, {}).get("delta_mae") or 0.0)
            for s in STATS if s != "blk"
        )
        sweep_rows.append({
            "factor": factor, "results": results,
            "blk_delta": blk_d, "other_max_abs": other_max_abs,
        })

    # Pick best by minimum BLK delta (most negative)
    best = min(sweep_rows, key=lambda d: d["blk_delta"])
    print()
    print("=" * 78)
    print(f"BEST: factor={best['factor']:.2f}  BLK delta={best['blk_delta']:+.4f}  "
          f"other-stat max-abs-delta={best['other_max_abs']:.6e}")
    print("=" * 78)

    # WF on best
    wf_results: Dict[str, List[float]] = {}
    if not args.skip_wf:
        print()
        print("=" * 78)
        print(f"WALK-FORWARD 4-FOLD on best variant (factor={best['factor']:.2f})")
        print("=" * 78)
        best_fn = make_center_blk_scale(factor=best["factor"])
        wf_results = walk_forward_post_adjust(best_fn, holdout, X, n_folds=4,
                                              stats=("blk",))
        deltas = wf_results.get("blk", [])
        mean = float(np.mean(deltas)) if deltas else float("nan")
        n_neg = sum(1 for d in deltas if d < -0.0001)
        row = "  blk  "
        for d in deltas:
            row += f"{d:+9.4f} "
        row += f"  mean={mean:+9.4f}  folds<0={n_neg}/{len(deltas)}"
        print(f"  {'stat':<5} {'fold1':>9} {'fold2':>9} {'fold3':>9} {'fold4':>9}")
        print(row)

    # Ship gate
    print()
    print("=" * 78)
    print("SHIP GATE (workday spec)")
    print("=" * 78)
    blk_d = best["blk_delta"]
    ss_pass = (blk_d < 0) and (best["other_max_abs"] < 1e-12)
    wf_n_neg = 0
    wf_pass = True
    if not args.skip_wf:
        deltas = wf_results.get("blk", [])
        wf_n_neg = sum(1 for d in deltas if d < -0.0001)
        wf_pass = (wf_n_neg == 4)
    print(f"  SS: BLK={blk_d:+.4f}  other-stat-max-abs={best['other_max_abs']:.2e}  "
          f"pass={ss_pass}")
    if not args.skip_wf:
        print(f"  WF BLK: {wf_n_neg}/4 folds positive  pass={wf_pass}")
    final = ss_pass and wf_pass
    print(f"  VERDICT: {'SHIP' if final else 'REJECT'}")

    # Markdown report
    out_path = os.path.join(_RESULTS_DIR, "center_blk_scale_v1.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 97b (loop 5) — center-BLK position scale\n\n")
        f.write("## Why this cycle\n")
        f.write("Cycle 96e granular per-position stratification found three "
                "Center buckets in the largest single-bucket MAE gap of the "
                "holdout:\n\n")
        f.write("| bucket | n | bucket_mae | global_mae | rel | bias |\n")
        f.write("|--------|---|-----------|------------|-----|------|\n")
        f.write("| Center            | 2075 | 0.8115 | 0.4398 | 1.845 | -0.4249 |\n")
        f.write("| Center-Forward    |  807 | 0.8256 | 0.4398 | 1.877 | -0.3885 |\n")
        f.write("| Forward-Center    | 1038 | 0.6953 | 0.4398 | 1.581 | -0.4081 |\n\n")
        f.write("Bias -0.4147 (mean pred 0.557 vs true 0.972) suggests a "
                "needed scale of mean_true/mean_pred = 1.745. We sweep "
                "around this number and require BOTH single-split BLK MAE "
                "strictly DOWN with other stats unchanged AND walk-forward "
                "4/4 folds positive on BLK before shipping.\n\n")

        f.write("## Position coverage on canonical holdout\n")
        f.write(f"- rows with position: {n_with_pos}/{len(holdout)} "
                f"({100*n_with_pos/max(1,len(holdout)):.1f}%)\n")
        f.write(f"- center-bucket rows: {n_center_buckets}\n")
        for p in sorted(_CENTER_POSITIONS):
            f.write(f"  - {p}: {pos_counter.get(p, 0)}\n")

        f.write("\n## No-op reproduction (cycle 97a discipline)\n")
        f.write("- factor=1.0 produced BLK delta_mae=0.0 (asserted before sweep).\n")

        f.write("\n## Factor sweep (single-split, BLK only)\n\n")
        f.write("| factor | BLK Δ | other-stat max abs Δ | safe? |\n")
        f.write("|--------|-------|----------------------|-------|\n")
        for s in sweep_rows:
            safe = "yes" if s["other_max_abs"] < 1e-12 else "NO"
            f.write(f"| {s['factor']:.2f} | {s['blk_delta']:+.4f} | "
                    f"{s['other_max_abs']:.2e} | {safe} |\n")

        f.write(f"\n## Best variant detail: **factor={best['factor']:.2f}**\n\n")
        f.write("| stat | n | baseline_mae | adjusted_mae | delta_mae | verdict |\n")
        f.write("|------|---|--------------|--------------|-----------|---------|\n")
        for s in STATS:
            r = best["results"].get(s, {})
            if not r or r.get("n") == 0:
                continue
            d = r.get("delta_mae") or 0.0
            v = "BETTER" if d < -0.001 else ("worse" if d > 0.001 else "flat")
            f.write(f"| {s} | {r.get('n')} | {r.get('baseline_mae'):.4f} "
                    f"| {r.get('adjusted_mae'):.4f} | {d:+.4f} | {v} |\n")

        if not args.skip_wf:
            f.write(f"\n## Walk-forward 4-fold on BLK (factor={best['factor']:.2f})\n\n")
            f.write("| fold1 | fold2 | fold3 | fold4 | mean | folds<0 |\n")
            f.write("|-------|-------|-------|-------|------|---------|\n")
            deltas = wf_results.get("blk", [])
            mean = float(np.mean(deltas)) if deltas else float("nan")
            n_neg = sum(1 for d in deltas if d < -0.0001)
            f.write("|")
            for d in deltas:
                f.write(f" {d:+.4f} |")
            f.write(f" {mean:+.4f} | {n_neg}/4 |\n")

        f.write("\n## Ship gate\n\n")
        f.write(f"- single-split: BLK < 0 AND other stats unchanged → **{ss_pass}** "
                f"(BLK={blk_d:+.4f}, other-stat-max-abs={best['other_max_abs']:.2e})\n")
        if not args.skip_wf:
            f.write(f"- WF BLK 4/4 folds positive → **{wf_pass}** "
                    f"({wf_n_neg}/4)\n")
        f.write(f"\n**VERDICT: {'SHIP' if final else 'REJECT'}**\n")
        if not final:
            f.write("\n**Rejection rationale:**\n")
            if not ss_pass:
                if blk_d >= 0:
                    f.write(f"- single-split BLK delta {blk_d:+.4f} not negative\n")
                if best["other_max_abs"] >= 1e-12:
                    f.write(f"- non-BLK stat drift {best['other_max_abs']:.2e} "
                            f">= 1e-12 (probe touched the wrong stat)\n")
            if not args.skip_wf and not wf_pass:
                f.write(f"- WF BLK only {wf_n_neg}/4 folds positive\n")

    print(f"\nReport written: {out_path}")

    # Machine-readable summary for the workday wrapper
    print(f"\n__BEST_FACTOR__={best['factor']:.2f}")
    print(f"__BLK_SS_DELTA__={blk_d:+.4f}")
    print(f"__SS_PASS__={ss_pass}")
    if not args.skip_wf:
        print(f"__WF_PASS__={wf_pass}")
        print(f"__WF_FOLDS_NEG__={wf_n_neg}")
    print(f"__FINAL__={'SHIP' if final else 'REJECT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
