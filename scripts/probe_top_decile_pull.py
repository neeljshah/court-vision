"""probe_top_decile_pull.py - cycle 94b top-decile pull-to-L10 probe (loop 5).

Cycle 93d's error_strata_v2 found that pred_d10 (top-decile prediction) dominates
the hardest strata for ALL 7 stats. Per-stat MAE delta in pred_d10 is +0.13 to
+1.72 above global. Mean signed bias is positive (overshoots) on average.

This probe tests the OPPOSITE-TAIL variant of cycle-84 pull_l10_when_low_pred:
when pred >= per-stat 90th-percentile cutoff, pull toward player L10 mean:

    adjusted = (1 - w) * pred + w * l10_<stat>

The cutoff is computed from the 80% TRAINING portion (not the holdout, to avoid
selection bias). The holdout (chronological last 20%) is the evaluation slice.

Sweeps w in {0.10, 0.15, 0.20, 0.25, 0.30}. For the best w, runs walk-forward
4-fold validation. Writes scripts/_results/top_decile_pull_v1.md.

Ship gate (BOTH):
  - Single-split: >=4 of 7 stats strictly DOWN AND sum-of-per-stat delta <= -0.005
  - WF 4/4 positive on >=3 stats
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Callable, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _y_true(rows: List[dict], stat: str) -> np.ndarray:
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in rows
    ], dtype=float)


def _features(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                     for r in rows], dtype=float)


def _compute_p90_from_train(stat: str, train_rows: List[dict],
                            cols: List[str]) -> Optional[float]:
    """Compute the 90th-percentile prediction cutoff using the 80% TRAIN slice.

    This avoids leakage from the holdout: if we sampled the p90 from the holdout
    itself we'd implicitly select for in-distribution behavior on that slice.
    """
    X_train = _features(train_rows, cols)
    p_train = _bulk_predict(stat, X_train)
    if p_train is None:
        return None
    return float(np.quantile(p_train, 0.90))


def apply_pull_top_decile(
    pred: np.ndarray, rows: List[dict], stat: str,
    cutoff_p90: float, weight: float,
) -> np.ndarray:
    """When pred >= cutoff_p90: adjusted = (1-w)*pred + w*l10_<stat>."""
    l10_key = f"l10_{stat}"
    out = pred.copy()
    for i, r in enumerate(rows):
        if pred[i] < cutoff_p90:
            continue
        l10 = r.get(l10_key)
        if l10 is None:
            continue
        try:
            l10f = float(l10)
        except (TypeError, ValueError):
            continue
        out[i] = (1.0 - weight) * pred[i] + weight * l10f
    return np.clip(out, 0.0, None)


def evaluate_per_stat(
    holdout: List[dict], cols: List[str],
    cutoffs: Dict[str, float], weight: float,
) -> Dict[str, Dict[str, float]]:
    """Per-stat baseline + adjusted MAE on the holdout slice."""
    X = _features(holdout, cols)
    results: Dict[str, Dict[str, float]] = {}
    for stat in STATS:
        yt = _y_true(holdout, stat)
        mask = ~np.isnan(yt)
        pred = _bulk_predict(stat, X)
        if pred is None or stat not in cutoffs:
            results[stat] = {"baseline_mae": float("nan"),
                              "adjusted_mae": float("nan"),
                              "delta_mae": float("nan"),
                              "n_hit": 0, "n_total": int(mask.sum())}
            continue
        adj = apply_pull_top_decile(pred, holdout, stat,
                                     cutoffs[stat], weight)
        n_hit = int(((pred >= cutoffs[stat]) & mask).sum())
        bm = float(np.mean(np.abs(pred[mask] - yt[mask])))
        am = float(np.mean(np.abs(adj[mask] - yt[mask])))
        results[stat] = {
            "baseline_mae": bm,
            "adjusted_mae": am,
            "delta_mae":    am - bm,
            "n_hit":        n_hit,
            "n_total":      int(mask.sum()),
        }
    return results


def walk_forward(
    all_rows: List[dict], cols: List[str], weight: float, n_folds: int = 4,
) -> Dict[str, List[float]]:
    """Expanding-window WF: 4 chronological folds.

    For each fold k:
      train = rows[0 : (0.6 + 0.1*k) * n]
      eval  = rows[(0.6 + 0.1*k) * n : (0.7 + 0.1*k) * n]
    p90 cutoff per stat computed from that fold's train slice.
    Returns per-stat list of deltas (one per fold).
    """
    n = len(all_rows)
    deltas: Dict[str, List[float]] = {s: [] for s in STATS}
    for k in range(n_folds):
        train_end = int(n * (0.60 + 0.10 * k))
        eval_end = int(n * (0.70 + 0.10 * k))
        if eval_end <= train_end:
            continue
        train_rows = all_rows[:train_end]
        eval_rows = all_rows[train_end:eval_end]
        cutoffs: Dict[str, float] = {}
        for stat in STATS:
            c = _compute_p90_from_train(stat, train_rows, cols)
            if c is not None:
                cutoffs[stat] = c
        res = evaluate_per_stat(eval_rows, cols, cutoffs, weight)
        for stat in STATS:
            d = res[stat].get("delta_mae")
            if d is not None and d == d:  # not NaN
                deltas[stat].append(d)
    return deltas


# ── markdown report ──────────────────────────────────────────────────────────

def _fmt(x: float) -> str:
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.4f}"


def write_report(
    out_path: str,
    n_train: int, n_holdout: int,
    cutoffs: Dict[str, float],
    sweep_results: Dict[float, Dict[str, Dict[str, float]]],
    best_w: float,
    wf_deltas: Dict[str, List[float]],
    verdict: str,
) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines: List[str] = []
    lines.append("# Top-decile Pull-to-L10 Probe v1 (cycle 94b)\n")
    lines.append("## Context\n")
    lines.append(
        "Cycle 93d's error_strata_v2 found pred_d10 dominates hardest strata "
        "for ALL 7 stats. Mean signed bias positive (overshoots). This probe "
        "tests the opposite-tail variant of cycle-84 pull_l10_when_low_pred: "
        "when pred >= per-stat p90 cutoff, blend toward L10 mean.\n"
    )
    lines.append(f"Train slice: n={n_train} (chronological first 80%)\n")
    lines.append(f"Holdout: n={n_holdout} (chronological last 20%)\n")

    lines.append("\n## Per-stat p90 cutoffs (from train slice)\n")
    lines.append("| stat | p90 cutoff |")
    lines.append("|------|------------|")
    for s in STATS:
        c = cutoffs.get(s)
        lines.append(f"| {s.upper()} | {c:.3f} |" if c is not None
                     else f"| {s.upper()} | (n/a) |")

    lines.append("\n## Sweep (per-stat MAE delta vs baseline)\n")
    header = "| w | " + " | ".join(s.upper() for s in STATS) + " | sum | n_down |"
    sep = "|---|" + "|".join(["---"] * (len(STATS) + 2)) + "|"
    lines.append(header)
    lines.append(sep)
    for w in sorted(sweep_results.keys()):
        res = sweep_results[w]
        deltas = [res[s]["delta_mae"] for s in STATS]
        n_down = sum(1 for d in deltas if d < -1e-4)
        total = sum(d for d in deltas if d == d)
        cells = " | ".join(_fmt(d) for d in deltas)
        lines.append(f"| {w:.2f} | {cells} | {_fmt(total)} | {n_down} |")

    lines.append(f"\n## Best w on single-split = {best_w:.2f}\n")
    res = sweep_results[best_w]
    lines.append("| stat | baseline_mae | adjusted_mae | delta | n_hit / n_total |")
    lines.append("|------|--------------|--------------|-------|-----------------|")
    for s in STATS:
        r = res[s]
        lines.append(
            f"| {s.upper()} | {r['baseline_mae']:.4f} | {r['adjusted_mae']:.4f} | "
            f"{_fmt(r['delta_mae'])} | {r['n_hit']}/{r['n_total']} |"
        )

    lines.append(f"\n## Walk-forward (4 expanding folds), w={best_w:.2f}\n")
    lines.append("| stat | fold deltas | mean | n_positive |")
    lines.append("|------|-------------|------|------------|")
    for s in STATS:
        ds = wf_deltas.get(s, [])
        if not ds:
            lines.append(f"| {s.upper()} | (no folds) | n/a | 0/0 |")
            continue
        fold_str = ", ".join(_fmt(d) for d in ds)
        mean_d = float(np.mean(ds))
        n_pos = sum(1 for d in ds if d < -1e-4)
        lines.append(f"| {s.upper()} | {fold_str} | {_fmt(mean_d)} | {n_pos}/{len(ds)} |")

    lines.append(f"\n## Verdict\n\n{verdict}\n")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    split = int(n * 0.80)
    train = rows[:split]
    holdout = rows[split:]
    cols = feature_columns()
    print(f"  n={n} train={len(train)} holdout={len(holdout)} "
          f"features={len(cols)}", flush=True)

    print("Computing per-stat p90 cutoffs from train slice...", flush=True)
    cutoffs: Dict[str, float] = {}
    for stat in STATS:
        c = _compute_p90_from_train(stat, train, cols)
        if c is not None:
            cutoffs[stat] = c
            print(f"  {stat:<5} p90 = {c:.3f}", flush=True)
        else:
            print(f"  {stat:<5} (no model — skipped)", flush=True)

    print("\nRunning weight sweep on holdout...", flush=True)
    weights_to_try = [0.10, 0.15, 0.20, 0.25, 0.30]
    sweep_results: Dict[float, Dict[str, Dict[str, float]]] = {}
    for w in weights_to_try:
        res = evaluate_per_stat(holdout, cols, cutoffs, w)
        sweep_results[w] = res
        deltas = [res[s]["delta_mae"] for s in STATS if res[s]["delta_mae"] == res[s]["delta_mae"]]
        total = sum(deltas)
        n_down = sum(1 for d in deltas if d < -1e-4)
        print(f"  w={w:.2f}  sum_delta={total:+.4f}  n_down={n_down}/{len(deltas)}",
              flush=True)

    # Pick best w by minimum sum delta (most negative).
    def _sum_delta(w):
        res = sweep_results[w]
        ds = [res[s]["delta_mae"] for s in STATS if res[s]["delta_mae"] == res[s]["delta_mae"]]
        return sum(ds)
    best_w = min(weights_to_try, key=_sum_delta)
    best_res = sweep_results[best_w]
    best_sum = _sum_delta(best_w)
    best_n_down = sum(1 for s in STATS
                      if best_res[s]["delta_mae"] < -1e-4)
    print(f"\nBest w = {best_w:.2f}  sum_delta = {best_sum:+.4f}  "
          f"n_stats_down = {best_n_down}/7", flush=True)

    print("\nRunning walk-forward (4 folds) for best w...", flush=True)
    wf = walk_forward(rows, cols, best_w, n_folds=4)
    for stat in STATS:
        ds = wf.get(stat, [])
        if ds:
            n_pos = sum(1 for d in ds if d < -1e-4)
            mean_d = float(np.mean(ds))
            print(f"  {stat:<5} folds={[round(d,4) for d in ds]} "
                  f"mean={mean_d:+.4f} n_pos={n_pos}/{len(ds)}",
                  flush=True)

    # Ship gate
    ss_pass = (best_n_down >= 4) and (best_sum <= -0.005)
    wf_pass_stats = sum(1 for s in STATS
                        if len(wf.get(s, [])) == 4
                        and all(d < -1e-4 for d in wf[s]))
    wf_pass = wf_pass_stats >= 3

    if ss_pass and wf_pass:
        verdict = (
            f"SHIP w={best_w:.2f}: single-split sum_delta {best_sum:+.4f} "
            f"<= -0.005 with {best_n_down}/7 stats DOWN. "
            f"WF 4/4 positive on {wf_pass_stats}/7 stats (>=3 required)."
        )
    else:
        reasons = []
        if not ss_pass:
            reasons.append(f"single-split sum_delta {best_sum:+.4f} (need <= -0.005) "
                            f"or n_down {best_n_down}/7 (need >= 4)")
        if not wf_pass:
            reasons.append(f"WF 4/4 positive on only {wf_pass_stats}/7 stats (need >= 3)")
        verdict = "REJECT: " + "; ".join(reasons)

    print(f"\n{verdict}", flush=True)

    out_path = os.path.join(PROJECT_DIR, "scripts", "_results",
                             "top_decile_pull_v1.md")
    write_report(out_path, len(train), len(holdout), cutoffs,
                 sweep_results, best_w, wf, verdict)
    print(f"\nWrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
