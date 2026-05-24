"""probe_guard_fg3m_scale.py — Cycle 97c (loop 5) T1 position-conditioned FG3M scale.

Cycle 96e found the largest sample-size position MAE gap: Guards' FG3M MAE
is 1.019 vs global 0.894 (+14% relative, n=10,125 — the biggest n in the
position-MAE delta table, bias -0.22 = model UNDER-predicts). 96e was
research-only ("DO NOT ship") and recommended cycle 97 to validate via the
dual MAE-delta gate (single-split AND 4-fold walk-forward).

This probe:
  1. Builds the per-game holdout with the cycle-90e position join.
  2. Sweeps a multiplicative scale in {1.05, 1.10, 1.15, 1.17, 1.20} applied
     ONLY when stat == 'fg3m' AND position in {Guard, Guard-Forward,
     Forward-Guard}.
  3. Single-split per-stat MAE delta (focused on FG3M; all others must be
     unchanged because the function is no-op for stat != 'fg3m').
  4. NO-OP REPRODUCTION TEST: factor=1.0 → MAE delta exactly 0.0 across
     every stat. This guards against accidental wrapper-state pollution.
  5. Walk-forward 4-fold on the best factor; reports FG3M per-fold delta
     and folds-positive count.

Coordinates with cycle 97b (which also wires into prop_pergame.py): both
post-prediction shrink/scale functions sit on the SAME final point estimate,
so order of application matters only when both apply to the same stat. The
guard-FG3M scale never overlaps with the 97b haircut domain (PTS/REB/AST
only), so they compose cleanly.

Run:
    python scripts/probe_guard_fg3m_scale.py
    python scripts/probe_guard_fg3m_scale.py --skip-wf
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

# Hyphen-preserved positions that score from the Guard half of the floor.
# Matches the granular bucket scheme from cycle 96e: 'Guard', 'Guard-Forward',
# 'Forward-Guard'. Forward-Guard's FG3M relative MAE (96e) was 1.104 with a
# negative bias too, so it joins the guard bucket for the scale.
_GUARD_POSITIONS = frozenset({"Guard", "Guard-Forward", "Forward-Guard"})


# ── adjustment factory ───────────────────────────────────────────────────────

def make_guard_fg3m_scale(factor: float = 1.17) -> Callable[
        [np.ndarray, List[dict], str], np.ndarray]:
    """Multiplicative FG3M scale gated on stat=='fg3m' AND guard position.

    No-op for any other (stat, position) combination, for position=None
    (uncached pid), and for factor==1.0 (NO-OP reproduction test).
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        out = pred.copy()
        if stat != "fg3m":
            return out
        if factor == 1.0:
            return out
        for i, r in enumerate(rows):
            pos = r.get("position")
            if pos is None:
                continue
            if str(pos) not in _GUARD_POSITIONS:
                continue
            out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)
    return fn


# ── WF helper (post-prediction adjustment — no retrain) ──────────────────────

def walk_forward_post_adjust(
    fn,
    holdout: List[dict],
    X: np.ndarray,
    n_folds: int = 4,
    stat: str = "fg3m",
) -> List[float]:
    """Per-fold MAE delta (adj - base) for `stat`. Negative = improvement."""
    n = len(holdout)
    fold_size = n // n_folds
    deltas: List[float] = []
    for fold_i in range(n_folds):
        lo = fold_i * fold_size
        hi = n if fold_i == n_folds - 1 else (fold_i + 1) * fold_size
        sub_rows = holdout[lo:hi]
        sub_X = X[lo:hi]
        y_true = np.array([
            np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
            for r in sub_rows
        ], dtype=float)
        mask = ~np.isnan(y_true)
        pred = _bulk_predict(stat, sub_X)
        if pred is None:
            deltas.append(float("nan"))
            continue
        adj = fn(pred, sub_rows, stat)
        bm = float(np.mean(np.abs(pred[mask] - y_true[mask])))
        am = float(np.mean(np.abs(adj[mask] - y_true[mask])))
        deltas.append(am - bm)
    return deltas


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

    # Position coverage audit on holdout
    positions = [r.get("position") for r in holdout]
    n_with_pos = sum(1 for p in positions if p)
    n_guard = sum(1 for p in positions if p and str(p) in _GUARD_POSITIONS)
    print(f"  n_total={n_total} holdout={len(holdout)} features={len(cols)}",
          flush=True)
    print(f"  position coverage: {n_with_pos}/{len(holdout)} "
          f"({100*n_with_pos/max(1,len(holdout)):.1f}%)", flush=True)
    print(f"  guard rows (Guard / Guard-Forward / Forward-Guard): "
          f"{n_guard}/{len(holdout)} "
          f"({100*n_guard/max(1,len(holdout)):.1f}%)\n", flush=True)

    if n_guard < 500:
        print("WARN: insufficient guard coverage — probe is informational only.",
              flush=True)

    # ── NO-OP REPRODUCTION TEST (factor=1.0) ─────────────────────────────────
    print("=" * 78)
    print("NO-OP REPRODUCTION TEST (factor=1.0)")
    print("=" * 78)
    noop_fn = make_guard_fg3m_scale(factor=1.0)
    noop_results = validate(noop_fn, holdout, X)
    noop_max_abs = 0.0
    for s in STATS:
        d = noop_results.get(s, {}).get("delta_mae") or 0.0
        print(f"  {s:<5} delta={d:+.6f}")
        noop_max_abs = max(noop_max_abs, abs(d))
    noop_pass = noop_max_abs == 0.0
    print(f"  max |delta| = {noop_max_abs:.6f}  pass={noop_pass}")
    if not noop_pass:
        print("  ABORT: factor=1.0 must produce EXACT 0.0 delta across every stat.",
              flush=True)
        return 1

    # ── Single-split sweep ───────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("SINGLE-SPLIT SWEEP (FG3M only — other stats are no-ops by design)")
    print("=" * 78)

    factor_grid = (1.05, 1.10, 1.15, 1.17, 1.20)
    sweep_rows = []
    for factor in factor_grid:
        fn = make_guard_fg3m_scale(factor=factor)
        results = validate(fn, holdout, X)
        # Other-stats invariance check (must all be 0.0 because fn is stat-gated).
        other_max_abs = 0.0
        for s in STATS:
            if s == "fg3m":
                continue
            d = results.get(s, {}).get("delta_mae") or 0.0
            other_max_abs = max(other_max_abs, abs(d))
        fg3m_d = results.get("fg3m", {}).get("delta_mae") or 0.0
        sweep_rows.append({
            "factor": factor, "results": results,
            "fg3m_delta": fg3m_d, "other_max_abs": other_max_abs,
        })
        print(f"  factor={factor:.2f}  FG3M Δ={fg3m_d:+.4f}  "
              f"other-stat max|Δ|={other_max_abs:.6f}")

    best = min(sweep_rows, key=lambda d: d["fg3m_delta"])
    print()
    print("=" * 78)
    print(f"BEST FACTOR: {best['factor']:.2f}  FG3M Δ={best['fg3m_delta']:+.4f}")
    print("=" * 78)
    print_report(f"factor={best['factor']:.2f} detail", best["results"])

    # ── Walk-forward 4-fold on best factor ───────────────────────────────────
    wf_deltas: List[float] = []
    if not args.skip_wf:
        print()
        print("=" * 78)
        print(f"WALK-FORWARD 4-FOLD on factor={best['factor']:.2f} (FG3M)")
        print("=" * 78)
        best_fn = make_guard_fg3m_scale(factor=best["factor"])
        wf_deltas = walk_forward_post_adjust(best_fn, holdout, X,
                                              n_folds=4, stat="fg3m")
        wf_mean = float(np.mean(wf_deltas)) if wf_deltas else float("nan")
        wf_n_neg = sum(1 for d in wf_deltas if d < -0.0001)
        row = "  fg3m  "
        for d in wf_deltas:
            row += f"{d:+9.4f} "
        row += f"  mean={wf_mean:+.4f}  folds<0={wf_n_neg}/{len(wf_deltas)}"
        print(row)

    # ── Ship gate ────────────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("SHIP GATE (cycle 97c — dual MAE-delta)")
    print("=" * 78)

    fg3m_d = best["fg3m_delta"]
    ss_pass = (fg3m_d < 0)

    other_invariance_pass = (best["other_max_abs"] == 0.0)

    wf_pass = True
    wf_n_neg = 0
    if not args.skip_wf:
        wf_n_neg = sum(1 for d in wf_deltas if d < -0.0001)
        wf_pass = (wf_n_neg == 4)

    print(f"  no-op reproduction (factor=1.0 → 0.0): {noop_pass}")
    print(f"  single-split FG3M strictly DOWN: {ss_pass}  ({fg3m_d:+.4f})")
    print(f"  other stats UNCHANGED: {other_invariance_pass}  "
          f"(max|Δ|={best['other_max_abs']:.6f})")
    if not args.skip_wf:
        print(f"  WF FG3M 4/4 folds positive: {wf_pass}  ({wf_n_neg}/4)")
    final = noop_pass and ss_pass and other_invariance_pass and wf_pass
    print(f"  VERDICT: {'SHIP' if final else 'REJECT'}")

    # ── Markdown report ──────────────────────────────────────────────────────
    out_path = os.path.join(_RESULTS_DIR, "guard_fg3m_scale.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 97c (loop 5) — Guard-FG3M position-conditioned scale\n\n")
        f.write("## Why this probe\n")
        f.write("Cycle 96e found Guards' FG3M MAE = 1.019 vs global 0.894 "
                "(+14% rel, n=10,125 — largest n in the position MAE table). "
                "Mean bias -0.22 = model under-predicts. 96e was research-only; "
                "this cycle wires the dual MAE-delta validator and ships or "
                "rejects.\n\n")
        f.write("## Holdout coverage\n")
        f.write(f"- n_total={n_total} holdout={len(holdout)}\n")
        f.write(f"- position coverage: {n_with_pos}/{len(holdout)} "
                f"({100*n_with_pos/max(1,len(holdout)):.1f}%)\n")
        f.write(f"- guard rows (G / G-F / F-G): {n_guard}/{len(holdout)} "
                f"({100*n_guard/max(1,len(holdout)):.1f}%)\n\n")

        f.write("## No-op reproduction (factor=1.0)\n\n")
        f.write("| stat | delta |\n|------|-------|\n")
        for s in STATS:
            d = noop_results.get(s, {}).get("delta_mae") or 0.0
            f.write(f"| {s} | {d:+.6f} |\n")
        f.write(f"\nmax |delta| = {noop_max_abs:.6f} — pass={noop_pass}\n\n")

        f.write("## Single-split sweep (FG3M only)\n\n")
        f.write("| factor | FG3M Δ | other-stat max|Δ| |\n")
        f.write("|--------|--------|--------------------|\n")
        for sr in sweep_rows:
            f.write(f"| {sr['factor']:.2f} | {sr['fg3m_delta']:+.4f} "
                    f"| {sr['other_max_abs']:.6f} |\n")

        f.write(f"\n## Best factor detail: {best['factor']:.2f}\n\n")
        f.write("| stat | n | baseline_mae | adjusted_mae | delta_mae |\n")
        f.write("|------|---|--------------|--------------|-----------|\n")
        for s in STATS:
            r = best["results"].get(s, {})
            if not r or r.get("n") == 0:
                continue
            d = r.get("delta_mae") or 0.0
            f.write(f"| {s} | {r.get('n')} | {r.get('baseline_mae'):.4f} "
                    f"| {r.get('adjusted_mae'):.4f} | {d:+.4f} |\n")

        if not args.skip_wf:
            f.write(f"\n## Walk-forward 4-fold (factor={best['factor']:.2f}, FG3M)\n\n")
            wf_mean = float(np.mean(wf_deltas)) if wf_deltas else float("nan")
            f.write("| fold1 | fold2 | fold3 | fold4 | mean | folds<0 |\n")
            f.write("|-------|-------|-------|-------|------|---------|\n")
            row = ""
            for d in wf_deltas:
                row += f"| {d:+.4f} "
            row += f"| {wf_mean:+.4f} | {wf_n_neg}/4 |\n"
            f.write(row)

        f.write("\n## Ship gate\n\n")
        f.write(f"- no-op reproduction → **{noop_pass}**\n")
        f.write(f"- single-split FG3M strictly DOWN → **{ss_pass}** ({fg3m_d:+.4f})\n")
        f.write(f"- other stats UNCHANGED → **{other_invariance_pass}** "
                f"(max|Δ|={best['other_max_abs']:.6f})\n")
        if not args.skip_wf:
            f.write(f"- WF FG3M 4/4 folds positive → **{wf_pass}** "
                    f"({wf_n_neg}/4)\n")
        f.write(f"\n**VERDICT: {'SHIP' if final else 'REJECT'}**\n")
        if not final:
            f.write("\n**Rejection rationale:**\n")
            if not noop_pass:
                f.write("- no-op reproduction failed (factor=1.0 must yield exact 0.0 delta)\n")
            if not ss_pass:
                f.write(f"- single-split FG3M Δ={fg3m_d:+.4f} (need < 0)\n")
            if not other_invariance_pass:
                f.write(f"- other-stat invariance broken (max|Δ|={best['other_max_abs']:.6f})\n")
            if not args.skip_wf and not wf_pass:
                f.write(f"- WF FG3M only {wf_n_neg}/4 folds positive\n")

    print(f"\nReport written: {out_path}")

    # Machine-readable summary for any wrapper script.
    print(f"\n__BEST_FACTOR__={best['factor']:.2f}")
    print(f"__SS_PASS__={ss_pass}")
    if not args.skip_wf:
        print(f"__WF_PASS__={wf_pass}")
        print(f"__WF_FOLDS_NEG__={wf_n_neg}/4")
    print(f"__FINAL__={'SHIP' if final else 'REJECT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
