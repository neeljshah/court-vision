"""probe_high_min_bidirectional.py - cycle 94c (loop 5) H2 from error_strata_v2.

Hypothesis (from scripts/_results/error_strata_v2.md H2):
    On l10_min >= 30 rows, the model has DIVERGING bias signs:
      * PTS / AST / TOV : positive bias (overshoot) of +0.05 to +0.57
      * REB / BLK / STL : negative bias (undershoot) of -0.27 to -0.53
    FG3M sits near neutral (-0.07 to -0.20) - skip.
    A single global multiplier cannot fix both directions. A stat-family-split
    adjustment can: shrink volume stats (PTS/AST/TOV) by a small factor and
    inflate defensive counts (REB/BLK/STL) by the symmetric inverse, only on
    high l10_min rows.

Adjustment factory:
    make_high_min_bidir(min_threshold, shrink, inflate) where for each row with
    l10_min >= min_threshold:
        pts, ast, tov : pred *= shrink     (correct overshoot)
        reb, blk, stl : pred *= inflate    (correct undershoot)
        fg3m          : unchanged

Sweep:
    thresholds = (28, 30, 32)
    (shrink, inflate) tuples = ((0.97,1.03), (0.96,1.04), (0.98,1.02))
    => 9 combos

Ship gate (BOTH):
    - Single-split: >=4 of (PTS, AST, TOV, REB, BLK, STL) strictly DOWN AND
      aggregate of those 6 stats <= -0.005
    - WF 4-fold positive on >=3 of the 6

Output: scripts/_results/high_min_bidir_v1.md
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

_VOLUME_STATS = ("pts", "ast", "tov")     # shrink (correct overshoot)
_DEFENSE_STATS = ("reb", "blk", "stl")    # inflate (correct undershoot)
_AFFECTED = _VOLUME_STATS + _DEFENSE_STATS  # 6 stats touched (fg3m untouched)


# ── adjustment ───────────────────────────────────────────────────────────────


def apply_high_min_bidir(
    pred: np.ndarray,
    rows: List[dict],
    stat: str,
    min_threshold: float,
    shrink: float,
    inflate: float,
) -> Tuple[np.ndarray, int]:
    """Apply stat-family-split factor on rows where l10_min >= min_threshold.
    Returns (adjusted_pred, n_affected). fg3m and any non-affected stat passes
    through unchanged with n_affected=0.
    """
    if stat not in _AFFECTED:
        return pred.copy(), 0
    factor = shrink if stat in _VOLUME_STATS else inflate
    out = pred.copy()
    n_aff = 0
    for i, r in enumerate(rows):
        try:
            l10_m = float(r.get("l10_min", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if l10_m >= min_threshold:
            out[i] = pred[i] * factor
            n_aff += 1
    return np.clip(out, 0.0, None), n_aff


# ── eval ────────────────────────────────────────────────────────────────────


def _y_true(holdout: List[dict], stat: str) -> np.ndarray:
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in holdout
    ], dtype=float)


def _mae(pred: np.ndarray, y: np.ndarray) -> float:
    mask = ~np.isnan(y)
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs(pred[mask] - y[mask])))


def run_single_split(
    holdout: List[dict],
    X: np.ndarray,
    min_threshold: float,
    shrink: float,
    inflate: float,
    preds_cache: Dict[str, np.ndarray],
) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}
    for stat in STATS:
        pred = preds_cache.get(stat)
        if pred is None:
            results[stat] = None
            continue
        y = _y_true(holdout, stat)
        adj, n_aff = apply_high_min_bidir(
            pred, holdout, stat, min_threshold, shrink, inflate
        )
        bm = _mae(pred, y)
        am = _mae(adj, y)
        results[stat] = {
            "base_mae": bm,
            "adj_mae":  am,
            "delta":    am - bm,
            "n":        int((~np.isnan(y)).sum()),
            "n_affected": n_aff,
        }
    return results


def run_wf_chronological(
    holdout: List[dict],
    X: np.ndarray,
    min_threshold: float,
    shrink: float,
    inflate: float,
    preds_cache: Dict[str, np.ndarray],
    n_folds: int = 4,
) -> Dict[str, List]:
    """4-fold chronological WF on holdout. Production predicts on full slice,
    each fold's rows get the adjustment applied independently and MAE measured.
    """
    n = len(holdout)
    fold_size = n // n_folds
    wf: Dict[str, List] = {s: [] for s in _AFFECTED}
    for stat in _AFFECTED:
        pred = preds_cache.get(stat)
        if pred is None:
            wf[stat] = [None] * n_folds
            continue
        y = _y_true(holdout, stat)
        for f in range(n_folds):
            lo = f * fold_size
            hi = (f + 1) * fold_size if f < n_folds - 1 else n
            sl_rows = holdout[lo:hi]
            sl_pred = pred[lo:hi]
            sl_y = y[lo:hi]
            sl_adj, _ = apply_high_min_bidir(
                sl_pred, sl_rows, stat, min_threshold, shrink, inflate
            )
            wf[stat].append({
                "base": _mae(sl_pred, sl_y),
                "adj":  _mae(sl_adj, sl_y),
                "delta": _mae(sl_adj, sl_y) - _mae(sl_pred, sl_y),
                "n": int((~np.isnan(sl_y)).sum()),
            })
    return wf


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    cut = int(n * 0.80)
    holdout = rows[cut:]
    n_ho = len(holdout)
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
                 dtype=float)
    print(f"  full n={n}  holdout={n_ho}  features={len(cols)}", flush=True)

    # Coverage stats on l10_min
    l10m = np.array([float(r.get("l10_min", 0.0) or 0.0) for r in holdout],
                    dtype=float)
    n_28 = int((l10m >= 28).sum())
    n_30 = int((l10m >= 30).sum())
    n_32 = int((l10m >= 32).sum())
    print(f"  l10_min coverage: >=28: {n_28} ({100*n_28/n_ho:.1f}%)  "
          f">=30: {n_30} ({100*n_30/n_ho:.1f}%)  "
          f">=32: {n_32} ({100*n_32/n_ho:.1f}%)",
          flush=True)

    # Cache baseline predictions ONCE
    print("Running production predictions (cached)...", flush=True)
    preds_cache: Dict[str, np.ndarray] = {}
    for stat in STATS:
        p = _bulk_predict(stat, X)
        if p is not None:
            preds_cache[stat] = p
    print(f"  predictions cached for {len(preds_cache)}/{len(STATS)} stats",
          flush=True)

    # 9-combo sweep
    thresholds = (28, 30, 32)
    factor_pairs = ((0.97, 1.03), (0.96, 1.04), (0.98, 1.02))

    all_results: Dict[Tuple[int, float, float], Dict] = {}
    print("\n=== Sweep (9 combos) ===", flush=True)
    print(f"{'thr':>4} {'shr':>5} {'inf':>5} {'PTS':>8} {'AST':>8} {'TOV':>8} "
          f"{'REB':>8} {'BLK':>8} {'STL':>8} {'agg6':>8}", flush=True)
    for thr in thresholds:
        for (shr, inf) in factor_pairs:
            r = run_single_split(holdout, X, thr, shr, inf, preds_cache)
            all_results[(thr, shr, inf)] = r
            agg = sum(r[s]["delta"] for s in _AFFECTED if r.get(s))
            print(f"{thr:>4} {shr:>5.2f} {inf:>5.2f} " + " ".join(
                f"{r[s]['delta']:>+8.4f}" if r.get(s) else f"{'n/a':>8}"
                for s in _AFFECTED
            ) + f" {agg:>+8.4f}", flush=True)

    # Pick best combo by aggregate of the 6 stats
    def _agg(rr):
        return sum(rr[s]["delta"] for s in _AFFECTED if rr.get(s))

    best_key = min(all_results.keys(), key=lambda k: _agg(all_results[k]))
    best_res = all_results[best_key]
    best_agg = _agg(best_res)
    best_thr, best_shr, best_inf = best_key
    n_down = sum(1 for s in _AFFECTED
                 if best_res.get(s) and best_res[s]["delta"] < -0.001)
    print(f"\nBest combo: thr={best_thr} shr={best_shr:.2f} inf={best_inf:.2f}  "
          f"agg6={best_agg:+.4f}  n_down={n_down}/6", flush=True)

    # Gate 1: single-split
    gate_ss = (n_down >= 4) and (best_agg <= -0.005)
    print(f"Single-split ship gate (>=4/6 strictly down AND agg6 <= -0.005): "
          f"{'PASS' if gate_ss else 'FAIL'}", flush=True)

    # Gate 2: WF on best combo only if aggregate is at least mildly positive
    wf_results = None
    gate_wf = False
    wf_pos: Dict[str, int] = {}
    if best_agg <= -0.001:
        print(f"\n=== WF 4-fold chronological (no retrain) on best combo ===",
              flush=True)
        wf_results = run_wf_chronological(
            holdout, X, best_thr, best_shr, best_inf, preds_cache, n_folds=4
        )
        for s in _AFFECTED:
            n_pos = sum(1 for fr in wf_results[s] if fr and fr["delta"] < 0)
            wf_pos[s] = n_pos
            print(f"  {s.upper():<4} folds positive: {n_pos}/4", flush=True)
        n_stats_4of4 = sum(1 for s in _AFFECTED if wf_pos.get(s, 0) == 4)
        gate_wf = n_stats_4of4 >= 3
        print(f"WF ship gate (>=3 of 6 with 4/4 folds positive): "
              f"{'PASS' if gate_wf else 'FAIL'}  ({n_stats_4of4}/6 stats hit 4/4)",
              flush=True)

    gate_ship = gate_ss and gate_wf

    # Write markdown report
    out_path = os.path.join(PROJECT_DIR, "scripts", "_results",
                            "high_min_bidir_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    L: List[str] = []
    L.append("# cycle 94c (loop 5) - high-min bidirectional bias probe (H2)")
    L.append("")
    L.append("## Hypothesis source")
    L.append("error_strata_v2.md H2: on l10_min >= 30 rows, PTS/AST/TOV overshoot")
    L.append("(positive bias) while REB/BLK/STL undershoot (negative bias). A")
    L.append("stat-family-split adjustment can correct both directions; a single")
    L.append("global multiplier cannot. FG3M is skipped (no clear bias direction).")
    L.append("")
    L.append("## Setup")
    L.append(f"- holdout: chronological 80/20 (n={n_ho} of full n={n})")
    L.append(f"- l10_min coverage in holdout:")
    L.append(f"  - >= 28: {n_28} rows ({100*n_28/n_ho:.1f}%)")
    L.append(f"  - >= 30: {n_30} rows ({100*n_30/n_ho:.1f}%)")
    L.append(f"  - >= 32: {n_32} rows ({100*n_32/n_ho:.1f}%)")
    L.append(f"- affected stats: {', '.join(s.upper() for s in _AFFECTED)} (fg3m skipped)")
    L.append("- volume stats (PTS/AST/TOV): pred *= shrink")
    L.append("- defense stats (REB/BLK/STL): pred *= inflate")
    L.append("")
    L.append("## 9-combo sweep (per-stat MAE delta on single-split)")
    L.append("")
    L.append("| thr | shrink | inflate | PTS | AST | TOV | REB | BLK | STL | agg6 |")
    L.append("|----:|-------:|--------:|----:|----:|----:|----:|----:|----:|-----:|")
    for thr in thresholds:
        for (shr, inf) in factor_pairs:
            r = all_results[(thr, shr, inf)]
            agg = _agg(r)
            cells = []
            for s in _AFFECTED:
                if r.get(s):
                    cells.append(f"{r[s]['delta']:+.4f}")
                else:
                    cells.append("n/a")
            L.append(f"| {thr} | {shr:.2f} | {inf:.2f} | " +
                     " | ".join(cells) + f" | **{agg:+.4f}** |")
    L.append("")
    L.append(f"## Best combo")
    L.append(f"- threshold: **{best_thr}** (l10_min >= {best_thr})")
    L.append(f"- shrink (PTS/AST/TOV): **{best_shr:.2f}**")
    L.append(f"- inflate (REB/BLK/STL): **{best_inf:.2f}**")
    L.append(f"- aggregate-6 MAE delta: **{best_agg:+.4f}**")
    L.append(f"- stats strictly down (delta < -0.001): **{n_down}/6**")
    L.append("")
    L.append("## Per-stat single-split detail (best combo)")
    L.append("")
    L.append("| stat | n_affected | base_mae | adj_mae | delta |")
    L.append("|------|-----------:|---------:|--------:|------:|")
    for s in _AFFECTED:
        rr = best_res.get(s)
        if rr is None:
            L.append(f"| {s.upper()} | - | n/a | n/a | n/a |")
            continue
        L.append(f"| {s.upper()} | {rr['n_affected']} | {rr['base_mae']:.4f} | "
                 f"{rr['adj_mae']:.4f} | {rr['delta']:+.4f} |")
    L.append("")
    L.append(f"## Single-split ship gate: **{'PASS' if gate_ss else 'FAIL'}**")
    L.append("- gate: >=4 of 6 strictly DOWN AND agg6 <= -0.005")
    L.append(f"- result: {n_down}/6 strictly down, agg6 = {best_agg:+.4f}")
    L.append("")

    if wf_results is not None:
        L.append("## WF 4-fold chronological (best combo, no retrain)")
        L.append("")
        L.append("| stat | fold | base | adj | delta | positive? |")
        L.append("|------|-----:|----:|----:|------:|:---------:|")
        for s in _AFFECTED:
            for fi, fr in enumerate(wf_results[s]):
                if fr is None:
                    continue
                pos = fr["delta"] < 0
                L.append(f"| {s.upper()} | {fi+1} | {fr['base']:.4f} | "
                         f"{fr['adj']:.4f} | {fr['delta']:+.4f} | "
                         f"{'YES' if pos else 'no'} |")
        L.append("")
        L.append("WF folds positive per stat:")
        for s in _AFFECTED:
            L.append(f"- {s.upper()}: {wf_pos.get(s, 0)}/4")
        n_stats_4of4 = sum(1 for s in _AFFECTED if wf_pos.get(s, 0) == 4)
        L.append("")
        L.append(f"## WF ship gate: **{'PASS' if gate_wf else 'FAIL'}**")
        L.append(f"- gate: >=3 of 6 stats with 4/4 folds positive")
        L.append(f"- result: {n_stats_4of4}/6 stats achieved 4/4")
    else:
        L.append("## WF: SKIPPED")
        L.append("- single-split aggregate not even mildly positive (agg6 > -0.001)")

    L.append("")
    L.append("## Verdict")
    if gate_ship:
        L.append(f"**SHIP** at threshold={best_thr}, shrink={best_shr:.2f}, "
                 f"inflate={best_inf:.2f}.")
        L.append("Wire-in: post-prediction hook in `src/prediction/prop_pergame.py`.")
        L.append("Extend (do not replace) the same hook cycles 94a/94b are wiring.")
    else:
        reasons = []
        if not gate_ss:
            reasons.append(f"single-split gate failed "
                           f"(need >=4/6 down AND agg6 <= -0.005; "
                           f"got {n_down}/6 down, agg6={best_agg:+.4f})")
        if wf_results is None:
            reasons.append("aggregate not mildly positive - WF skipped")
        elif not gate_wf:
            n_stats_4of4 = sum(1 for s in _AFFECTED if wf_pos.get(s, 0) == 4)
            reasons.append(f"WF gate failed (need >=3/6 stats at 4/4 folds; "
                           f"got {n_stats_4of4}/6)")
        L.append(f"**REJECT** - {'; '.join(reasons)}.")
        L.append("")
        L.append("Interpretation: per-row bias signs in strata table are population")
        L.append("averages on a holdout slice. Applying a uniform stat-family")
        L.append("factor compresses the SCALE of every prediction in the cell, which")
        L.append("only helps when most rows share the bias direction. On individual")
        L.append("rows the residual sign is mixed, so a small uniform factor often")
        L.append("trades intra-cell winners for losers and the aggregate barely moves.")

    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(L) + "\n")
    print(f"\nWrote {out_path}", flush=True)
    print(f"Final verdict: {'SHIP' if gate_ship else 'REJECT'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
