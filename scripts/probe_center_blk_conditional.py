"""probe_center_blk_conditional.py — Cycle 98b (loop 5) T1-F-1.

REJECT verdict on run-1 (best factor=1.25): single-split BLK delta -0.0001
(passes SS gate marginally) but WF 4-fold only 2/4 folds negative (mean
-0.0001). The opp_def_blk proxy is too noisy a signal for paint-shot
opportunity; recommend building data/team_advanced_stats.parquet with
opp_paint_fga_rate (from boxscore_adv team entries) before re-running.

Cycle 97b REJECTED a flat center-BLK scale (factor 1.30..1.74 all REGRESSED:
+0.0031 .. +0.0137 BLK delta). Root cause: BLK uses q50 (median-optimal) head,
so the +85% MAE in center buckets is a RIGHT-TAIL OUTLIER problem, not a
median shift. A flat multiplicative scale moves the median (wrong direction)
instead of expanding the tail.

This probe replaces flat scaling with an OPPORTUNITY-CONDITIONAL scale:
fire ONLY on center rows where the opponent presents the high-BLK-opportunity
signal (top-quartile by opp_def_blk on the training portion). High opp_def_blk
means the opponent surrenders more blocks per game than league average — the
exact rows where a center's outlier BLK games happen.

Diagnostic-first contract:
  1) audit which opp_* features build_pergame_dataset puts on the row dict
  2) if NO direct paint/rim proxy AND no fallback proxy → REJECT cleanly
  3) only then sweep the conditional factor

Ship gate (BOTH required):
  - single-split BLK MAE STRICTLY DOWN, other stats unchanged
  - WF 4/4 folds positive on BLK

Run:
    python scripts/probe_center_blk_conditional.py
    python scripts/probe_center_blk_conditional.py --skip-wf
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import Callable, Dict, List, Optional, Tuple

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

_CENTER_POSITIONS = frozenset({"Center", "Center-Forward", "Forward-Center"})

# Candidate opp-BLK opportunity proxies, in preference order:
#   opp_def_blk — opponent's BLK-allowed factor (>1 = gives up more blocks).
#     This is the single best direct proxy in the row dict. High value =
#     opponent shoots more blockable shots (paint attempts vs no rim
#     protector pressure), which is exactly when center BLK outliers fire.
#   opp_def_fg3m — inverse proxy (low value means opp doesn't shoot 3s,
#     hence shoots more 2s/paint → more BLK chances). Used only as a
#     fallback if opp_def_blk is missing or constant on the holdout.
_PROXY_CANDIDATES = ("opp_def_blk", "opp_def_fg3m")


# ── proxy availability audit ─────────────────────────────────────────────────

def audit_proxies(rows: List[dict]) -> Dict[str, dict]:
    """For each candidate proxy, report presence/missing/variance on rows."""
    report: Dict[str, dict] = {}
    for k in _PROXY_CANDIDATES:
        vals = [r.get(k) for r in rows]
        non_null = [float(v) for v in vals if v is not None]
        if not non_null:
            report[k] = {"present": False, "n_nonnull": 0,
                         "variance": 0.0, "min": None, "max": None}
            continue
        arr = np.array(non_null, dtype=float)
        report[k] = {
            "present": True,
            "n_nonnull": len(arr),
            "variance": float(arr.var()),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "median": float(np.median(arr)),
        }
    return report


def pick_proxy(audit: Dict[str, dict]) -> Optional[str]:
    """Pick the highest-priority proxy with present=True AND variance > 0."""
    for k in _PROXY_CANDIDATES:
        info = audit.get(k, {})
        if info.get("present") and info.get("variance", 0.0) > 1e-9:
            return k
    return None


# ── adjustment factory ──────────────────────────────────────────────────────

def make_center_blk_conditional(
    top_quartile_cutoff: float,
    proxy_feature: str,
    factor: float = 1.30,
    invert_proxy: bool = False,
) -> Callable[[np.ndarray, List[dict], str], np.ndarray]:
    """Position + opp-opportunity conditional BLK scale.

    Fires multiplicative ``factor`` ONLY when ALL of:
      - stat == "blk"
      - row["position"] in _CENTER_POSITIONS
      - row[proxy_feature] is not None AND in TOP QUARTILE
        (>= top_quartile_cutoff). If ``invert_proxy``, the rule flips
        to BOTTOM quartile (used for inverse proxies like opp_def_fg3m).

    Every other (stat, position, opp) combo is a strict no-op.

    The factor == 1.0 fast-path returns predictions unchanged (no FP drift)
    so the no-op reproduction test passes by construction.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        if stat != "blk":
            return pred.copy()
        out = pred.copy()
        if factor == 1.0:
            return out
        for i, r in enumerate(rows):
            pos = r.get("position")
            if pos is None or str(pos) not in _CENTER_POSITIONS:
                continue
            v = r.get(proxy_feature)
            if v is None:
                continue
            try:
                vf = float(v)
            except (TypeError, ValueError):
                continue
            in_window = (vf <= top_quartile_cutoff) if invert_proxy else (
                vf >= top_quartile_cutoff)
            if in_window:
                out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)
    return fn


# ── WF helper (post-prediction adjustment, no retrain) ──────────────────────

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


# ── no-op assertion ──────────────────────────────────────────────────────────

def assert_noop_reproduction(holdout: List[dict], X: np.ndarray,
                             proxy: str, cutoff: float,
                             invert: bool) -> None:
    """factor=1.0 must produce EXACTLY 0.0 BLK MAE delta."""
    fn = make_center_blk_conditional(
        top_quartile_cutoff=cutoff, proxy_feature=proxy,
        factor=1.0, invert_proxy=invert)
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

    print("Loading pergame dataset (with position + opp_def join)...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    cols = feature_columns()
    train_end = int(n_total * 0.80)
    train_portion = rows[:train_end]
    holdout = rows[train_end:]
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n_total={n_total}  holdout={len(holdout)}  "
          f"train_portion={len(train_portion)}  features={len(cols)}\n",
          flush=True)

    # ── diagnostic phase: which opp_* proxies are usable?
    print("=" * 78)
    print("DIAGNOSTIC: opp_* proxy availability on training portion")
    print("=" * 78)
    audit = audit_proxies(train_portion)
    for k, info in audit.items():
        if info["present"]:
            print(f"  {k}: n_nonnull={info['n_nonnull']}  "
                  f"range=[{info['min']:.4f}, {info['max']:.4f}]  "
                  f"median={info['median']:.4f}  variance={info['variance']:.4e}")
        else:
            print(f"  {k}: MISSING")

    proxy = pick_proxy(audit)
    if proxy is None:
        msg = ("REJECT: no usable opp-BLK-opportunity proxy on the row dict. "
               "Recommend adding opp_paint_fg_rate (built from boxscore_adv "
               "team entries) before re-running this probe.")
        print()
        print("=" * 78)
        print(msg)
        print("=" * 78)
        out_path = os.path.join(_RESULTS_DIR, "center_blk_conditional_v1.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Cycle 98b (loop 5) — center-BLK opp-conditional scale\n\n")
            f.write("## Diagnostic phase: REJECT — no usable proxy\n\n")
            f.write("Candidate proxies audited on training portion:\n\n")
            f.write("| proxy | present | n_nonnull | variance | min | max |\n")
            f.write("|-------|---------|-----------|----------|-----|-----|\n")
            for k, info in audit.items():
                if info["present"]:
                    f.write(f"| {k} | yes | {info['n_nonnull']} "
                            f"| {info['variance']:.4e} "
                            f"| {info['min']:.4f} | {info['max']:.4f} |\n")
                else:
                    f.write(f"| {k} | no | 0 | 0 | — | — |\n")
            f.write(f"\n**VERDICT: REJECT**  \n{msg}\n")
        print(f"\nReport written: {out_path}")
        print("\n__FINAL__=REJECT")
        print("__REJECT_REASON__=no_proxy_available")
        return 0

    # Determine direction. opp_def_blk: high == high opportunity (use top-Q).
    # opp_def_fg3m: low == high opportunity (use bottom-Q, invert=True).
    invert = (proxy == "opp_def_fg3m")
    print(f"\n  selected proxy: {proxy}  invert={invert}", flush=True)

    # Compute top-quartile cutoff on TRAINING portion only (avoids holdout leak).
    train_vals = np.array([
        float(r[proxy]) for r in train_portion
        if r.get(proxy) is not None
    ], dtype=float)
    if invert:
        cutoff = float(np.percentile(train_vals, 25.0))
        print(f"  bottom-quartile cutoff (q25): {cutoff:.4f}", flush=True)
    else:
        cutoff = float(np.percentile(train_vals, 75.0))
        print(f"  top-quartile cutoff (q75):    {cutoff:.4f}", flush=True)

    # Coverage on holdout: how many center rows satisfy the gate?
    n_center_total = 0
    n_center_gated = 0
    for r in holdout:
        pos = r.get("position")
        if pos is None or str(pos) not in _CENTER_POSITIONS:
            continue
        n_center_total += 1
        v = r.get(proxy)
        if v is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if invert:
            if vf <= cutoff:
                n_center_gated += 1
        else:
            if vf >= cutoff:
                n_center_gated += 1
    print(f"  holdout center rows: {n_center_total}; "
          f"gated (in window): {n_center_gated} "
          f"({100*n_center_gated/max(1,n_center_total):.1f}%)\n", flush=True)

    # No-op reproduction
    print("=" * 78)
    print("NO-OP REPRODUCTION (factor=1.0)")
    print("=" * 78)
    assert_noop_reproduction(holdout, X, proxy, cutoff, invert)
    print()

    # Sweep
    factors = [1.15, 1.20, 1.25, 1.30, 1.40]
    print("=" * 78)
    print(f"SINGLE-SPLIT SWEEP — proxy={proxy}, cutoff={cutoff:.4f}")
    print("=" * 78)

    sweep_rows = []
    for factor in factors:
        fn = make_center_blk_conditional(
            top_quartile_cutoff=cutoff, proxy_feature=proxy,
            factor=factor, invert_proxy=invert)
        results = validate(fn, holdout, X)
        label = f"center_blk_conditional factor={factor:.2f}"
        print_report(label, results)
        blk_d = results.get("blk", {}).get("delta_mae", float("nan"))
        other_max_abs = max(
            abs(results.get(s, {}).get("delta_mae") or 0.0)
            for s in STATS if s != "blk"
        )
        sweep_rows.append({
            "factor": factor, "results": results,
            "blk_delta": blk_d, "other_max_abs": other_max_abs,
        })

    best = min(sweep_rows, key=lambda d: d["blk_delta"])
    print()
    print("=" * 78)
    print(f"BEST: factor={best['factor']:.2f}  BLK delta={best['blk_delta']:+.4f}  "
          f"other-stat max-abs-delta={best['other_max_abs']:.6e}")
    print("=" * 78)

    # WF
    wf_results: Dict[str, List[float]] = {}
    if not args.skip_wf:
        print()
        print("=" * 78)
        print(f"WALK-FORWARD 4-FOLD on best variant (factor={best['factor']:.2f})")
        print("=" * 78)
        best_fn = make_center_blk_conditional(
            top_quartile_cutoff=cutoff, proxy_feature=proxy,
            factor=best["factor"], invert_proxy=invert)
        wf_results = walk_forward_post_adjust(best_fn, holdout, X, n_folds=4,
                                              stats=("blk",))
        deltas = wf_results.get("blk", [])
        mean = float(np.mean(deltas)) if deltas else float("nan")
        n_neg = sum(1 for d in deltas if d < -0.0001)
        print(f"  {'stat':<5} {'fold1':>9} {'fold2':>9} {'fold3':>9} {'fold4':>9}")
        row = "  blk  "
        for d in deltas:
            row += f"{d:+9.4f} "
        row += f"  mean={mean:+9.4f}  folds<0={n_neg}/{len(deltas)}"
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
    out_path = os.path.join(_RESULTS_DIR, "center_blk_conditional_v1.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 98b (loop 5) — center-BLK opp-conditional scale\n\n")
        f.write("## Why this cycle\n")
        f.write("Cycle 97b REJECTED flat center-BLK scale (factor 1.30..1.74 "
                "all REGRESSED BLK MAE +0.0031 .. +0.0137). Root cause: BLK "
                "uses q50 head (median-optimal), so the center +85% MAE gap "
                "is a right-tail OUTLIER problem, not a median shift. A flat "
                "scale moves the median (wrong) — this probe expands ONLY the "
                "high-opportunity tail.\n\n")
        f.write("## Proxy availability (training portion)\n\n")
        f.write("| proxy | present | n_nonnull | variance | min | max | median |\n")
        f.write("|-------|---------|-----------|----------|-----|-----|--------|\n")
        for k, info in audit.items():
            if info["present"]:
                f.write(f"| {k} | yes | {info['n_nonnull']} | "
                        f"{info['variance']:.4e} | {info['min']:.4f} | "
                        f"{info['max']:.4f} | {info['median']:.4f} |\n")
            else:
                f.write(f"| {k} | no | 0 | 0 | — | — | — |\n")
        f.write(f"\n- selected proxy: **{proxy}**, invert={invert}\n")
        f.write(f"- {'bottom' if invert else 'top'}-quartile cutoff: "
                f"**{cutoff:.4f}**\n")
        f.write(f"- holdout center rows: {n_center_total}; in window: "
                f"{n_center_gated} ({100*n_center_gated/max(1,n_center_total):.1f}%)\n")
        f.write("\n## No-op reproduction\n- factor=1.0 → BLK delta_mae=0.0 "
                "(asserted before sweep)\n")
        f.write("\n## Factor sweep (single-split, BLK only)\n\n")
        f.write("| factor | BLK Δ | other-stat max abs Δ | safe? |\n")
        f.write("|--------|-------|----------------------|-------|\n")
        for s in sweep_rows:
            safe = "yes" if s["other_max_abs"] < 1e-12 else "NO"
            f.write(f"| {s['factor']:.2f} | {s['blk_delta']:+.4f} | "
                    f"{s['other_max_abs']:.2e} | {safe} |\n")
        f.write(f"\n## Best variant: **factor={best['factor']:.2f}**\n\n")
        f.write("| stat | n | baseline_mae | adjusted_mae | delta_mae | verdict |\n")
        f.write("|------|---|--------------|--------------|-----------|---------|\n")
        for s in STATS:
            r = best["results"].get(s, {})
            if not r or r.get("n") == 0:
                continue
            d = r.get("delta_mae") or 0.0
            v = "BETTER" if d < -0.001 else ("worse" if d > 0.001 else "flat")
            f.write(f"| {s} | {r.get('n')} | {r.get('baseline_mae'):.4f} | "
                    f"{r.get('adjusted_mae'):.4f} | {d:+.4f} | {v} |\n")
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
        f.write(f"- SS: BLK<0 AND others unchanged → **{ss_pass}** "
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
                    f.write(f"- non-BLK stat drift {best['other_max_abs']:.2e}\n")
            if not args.skip_wf and not wf_pass:
                f.write(f"- WF BLK only {wf_n_neg}/4 folds positive\n")

    print(f"\nReport written: {out_path}")
    print(f"\n__PROXY__={proxy}")
    print(f"__CUTOFF__={cutoff:.4f}")
    print(f"__BEST_FACTOR__={best['factor']:.2f}")
    print(f"__BLK_SS_DELTA__={blk_d:+.4f}")
    print(f"__SS_PASS__={ss_pass}")
    if not args.skip_wf:
        print(f"__WF_PASS__={wf_pass}")
        print(f"__WF_FOLDS_NEG__={wf_n_neg}")
    print(f"__FINAL__={'SHIP' if final else 'REJECT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
