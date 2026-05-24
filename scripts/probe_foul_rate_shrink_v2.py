"""probe_foul_rate_shrink_v2.py -- cycle 92d (loop 5) T1-B probe with REAL PF.

Same hypothesis as cycle 90c (probe_foul_rate_shrink.py): top-quintile
foul-per-36 players have a fatter LEFT tail on MIN-coupled box-score
realisations than the pre-game model captures (early-foul bench yanks).
Apply an asymmetric multiplicative shrink to PTS / REB / BLK predictions
for those top-quintile players.

KEY DIFFERENCE FROM v1 (cycle 90c):
    v1 had to degrade to a BLK/36 PROXY because the cached gamelogs
    didn't carry PF and data/season_games.parquet was absent. Cycle 91b
    landed a real `pf` column + `season_pf_per_36` rolling-prior-only
    helper, joined into build_pergame_dataset per-row from
    data/player_pf.parquet + data/player_pf_per36.parquet. We now probe
    the REAL hypothesis with the REAL signal — no proxy.

Coverage caveat (per cycle 91b):
    PF coverage is sparse (boxscore cache only covers part of the
    holdout). If <100 rows in the holdout have `season_pf_per_36`
    populated, the probe REJECTS with "PF coverage too sparse" and
    defers to cycle 92c daemon (which should expand the boxscore cache).

Selection bias caveat (per cycle 90b):
    gamelog_*.json only contains games the player actually PLAYED.
    "Top-quintile foul-rate" players are conditioned on playing — we're
    asking whether THEIR played games are systematically over-predicted
    on PTS/REB/BLK because the model misses early-foul shortenings. The
    sit-rate signal is absent from this dataset. The directional read
    is honest for played games only.

Workflow:
    1. Load holdout via build_pergame_dataset. Verify pf /
       season_pf_per_36 are now per-row available; report coverage
       fractions.
    2. If <100 holdout rows have season_pf_per_36: REJECT.
    3. Compute top-quintile cutoff of season_pf_per_36 on the TRAINING
       portion ONLY (rows[:train_end], no leakage).
    4. Adjustment: shrink PTS/REB/BLK predictions by `factor` when
       (season_pf_per_36 >= top_quintile_threshold). All other rows
       pass through unchanged.
    5. Sweep factor in {0.94, 0.96, 0.97, 0.98}.
    6. For best factor: per-stat single-split MAE delta + walk-forward
       4-fold deltas.
    7. Ship gate (BOTH):
         - Single-split MAE STRICTLY DOWN on >=2 of {PTS, REB, BLK} AND
           aggregate (PTS+REB+BLK) delta <= -0.003.
         - WF 4/4 positive on the SAME stats (4 of 4 folds negative).
    8. Write scripts/_results/foul_rate_shrink_v2_real_pf.md.

Run:
    python scripts/probe_foul_rate_shrink_v2.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)
from scripts.validate_adjustment import _bulk_predict  # noqa: E402

_SHRINK_STATS = ("pts", "reb", "blk")
_RESULTS_PATH = os.path.join(
    PROJECT_DIR, "scripts", "_results", "foul_rate_shrink_v2_real_pf.md"
)


def make_pf_rate_shrink(threshold_pf36: float, factor: float):
    """Return a callable (pred_arr, holdout_rows, stat) -> adjusted_arr.

    Multiplicative shrink only when:
      - stat in _SHRINK_STATS, AND
      - row['season_pf_per_36'] is not None AND >= threshold.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        if stat not in _SHRINK_STATS:
            return pred.copy()
        out = pred.copy()
        for i, r in enumerate(rows):
            v = r.get("season_pf_per_36")
            if v is None:
                continue
            try:
                vf = float(v)
            except (TypeError, ValueError):
                continue
            if vf >= threshold_pf36:
                out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)
    return fn


def measure_single_split(holdout: List[dict], X_ho: np.ndarray,
                         threshold: float, factor: float) -> Dict[str, dict]:
    fn = make_pf_rate_shrink(threshold, factor)
    n_treated = sum(
        1 for r in holdout
        if (r.get("season_pf_per_36") is not None
            and float(r.get("season_pf_per_36") or 0.0) >= threshold)
    )
    out: Dict[str, dict] = {}
    for stat in STATS:
        y = np.array([
            np.nan if r.get(f"target_{stat}") is None
            else float(r[f"target_{stat}"])
            for r in holdout
        ], dtype=float)
        mask = ~np.isnan(y)
        pred = _bulk_predict(stat, X_ho)
        if pred is None:
            out[stat] = {"base": float("nan"), "adj": float("nan"),
                         "delta": float("nan"), "n": 0,
                         "n_treated": n_treated}
            continue
        adj = fn(pred, holdout, stat)
        base_mae = float(np.mean(np.abs(pred[mask] - y[mask])))
        adj_mae = float(np.mean(np.abs(adj[mask] - y[mask])))
        out[stat] = {"base": base_mae, "adj": adj_mae,
                     "delta": adj_mae - base_mae,
                     "n": int(mask.sum()), "n_treated": n_treated}
    return out


def measure_walk_forward(holdout: List[dict], X_ho: np.ndarray,
                         threshold: float, factor: float,
                         n_splits: int = 4) -> Dict[str, List[float]]:
    n = len(holdout)
    edges = [int(round(n * i / n_splits)) for i in range(n_splits + 1)]
    preds_by_stat = {s: _bulk_predict(s, X_ho) for s in STATS}
    fn = make_pf_rate_shrink(threshold, factor)
    per_stat_deltas: Dict[str, List[float]] = {s: [] for s in STATS}
    for k in range(n_splits):
        lo, hi = edges[k], edges[k + 1]
        sl_rows = holdout[lo:hi]
        for stat in STATS:
            pred = preds_by_stat[stat]
            if pred is None:
                per_stat_deltas[stat].append(float("nan"))
                continue
            y = np.array([
                np.nan if r.get(f"target_{stat}") is None
                else float(r[f"target_{stat}"])
                for r in sl_rows
            ], dtype=float)
            mask = ~np.isnan(y)
            base_seg = pred[lo:hi]
            adj_seg = fn(base_seg, sl_rows, stat)
            if not mask.any():
                per_stat_deltas[stat].append(float("nan"))
                continue
            base_mae = float(np.mean(np.abs(base_seg[mask] - y[mask])))
            adj_mae = float(np.mean(np.abs(adj_seg[mask] - y[mask])))
            per_stat_deltas[stat].append(adj_mae - base_mae)
    return per_stat_deltas


def _write_report(lines: List[str]) -> None:
    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {_RESULTS_PATH}")


def main() -> int:
    report: List[str] = []
    report.append("# cycle 92d (loop 5) -- T1-B foul-rate MIN shrink v2 "
                  "(REAL PF)")
    report.append("")
    print("=== cycle 92d v2 -- foul-rate shrink with REAL season_pf_per_36 ===",
          flush=True)
    print("\nBuilding pergame dataset (with pf + season_pf_per_36)...",
          flush=True)
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)

    # Coverage stats
    n_pf = sum(1 for r in rows if r.get("pf") is not None)
    n_per36 = sum(1 for r in rows if r.get("season_pf_per_36") is not None)
    print(f"  n={n}  rows with pf: {n_pf} ({100*n_pf/max(n,1):.1f}%)  "
          f"rows with season_pf_per_36: {n_per36} "
          f"({100*n_per36/max(n,1):.1f}%)", flush=True)

    train_end = int(n * 0.80)
    holdout = rows[train_end:]
    n_ho = len(holdout)
    n_ho_pf = sum(1 for r in holdout if r.get("pf") is not None)
    n_ho_per36 = sum(1 for r in holdout
                     if r.get("season_pf_per_36") is not None)
    print(f"  holdout n={n_ho}  with pf: {n_ho_pf}  "
          f"with season_pf_per_36: {n_ho_per36}", flush=True)

    report.append("## Coverage")
    report.append("")
    report.append(f"- total rows: {n}")
    report.append(f"- rows with `pf`: {n_pf} ({100*n_pf/max(n,1):.2f}%)")
    report.append(f"- rows with `season_pf_per_36`: {n_per36} "
                  f"({100*n_per36/max(n,1):.2f}%)")
    report.append(f"- holdout n: {n_ho}")
    report.append(f"- holdout rows with `pf`: {n_ho_pf}")
    report.append(f"- holdout rows with `season_pf_per_36`: {n_ho_per36}")
    report.append("")

    # Coverage gate
    if n_ho_per36 < 100:
        msg = (f"PF coverage too sparse for honest probe "
               f"(holdout rows with season_pf_per_36={n_ho_per36}, need >=100); "
               f"need cycle 92c daemon to expand boxscore cache or "
               f"re-fetch with full pf coverage")
        print(f"\nVERDICT: REJECT -- {msg}", flush=True)
        report.append("## Verdict")
        report.append("")
        report.append(f"**REJECT** -- {msg}")
        _write_report(report)
        return 1

    # Threshold from TRAINING portion only
    train_rates = np.array([
        rows[i].get("season_pf_per_36")
        for i in range(train_end)
        if rows[i].get("season_pf_per_36") is not None
    ], dtype=float)
    train_rates = train_rates[~np.isnan(train_rates)]
    nonzero = train_rates[train_rates > 0]
    print(f"\n=== season_pf_per_36 distribution (training portion) ===",
          flush=True)
    print(f"  training rows with per36: {len(train_rates)}  "
          f"non-zero: {len(nonzero)}", flush=True)
    if len(nonzero) < 50:
        msg = (f"too few non-zero training rows (n={len(nonzero)}) "
               f"to derive a stable top-quintile cutoff")
        print(f"\nVERDICT: REJECT -- {msg}", flush=True)
        report.append("## Verdict")
        report.append("")
        report.append(f"**REJECT** -- {msg}")
        _write_report(report)
        return 1

    q_median = float(np.quantile(nonzero, 0.50))
    q_quartile = float(np.quantile(nonzero, 0.75))
    q_quintile = float(np.quantile(nonzero, 0.80))
    q_max = float(nonzero.max())
    print(f"  median       = {q_median:.3f}")
    print(f"  top-quartile = {q_quartile:.3f}")
    print(f"  top-quintile = {q_quintile:.3f}  (cutoff)")
    print(f"  max          = {q_max:.3f}", flush=True)
    threshold = q_quintile

    n_treated_ho = sum(
        1 for r in holdout
        if (r.get("season_pf_per_36") is not None
            and float(r["season_pf_per_36"]) >= threshold)
    )
    print(f"\nHoldout treated rows (season_pf_per_36 >= {threshold:.3f}): "
          f"{n_treated_ho}/{n_ho} ({100*n_treated_ho/max(n_ho,1):.1f}%)",
          flush=True)

    report.append("## Threshold (training-only, top quintile)")
    report.append("")
    report.append(f"- training rows considered: {len(train_rates)} "
                  f"(non-zero: {len(nonzero)})")
    report.append(f"- median: {q_median:.4f}")
    report.append(f"- top-quartile: {q_quartile:.4f}")
    report.append(f"- top-quintile: **{q_quintile:.4f}** (cutoff)")
    report.append(f"- max: {q_max:.4f}")
    report.append(f"- holdout treated rows: {n_treated_ho}/{n_ho} "
                  f"({100*n_treated_ho/max(n_ho,1):.2f}%)")
    report.append("")

    # Feature matrix
    X_ho = np.array([[float(r.get(c, 0.0) or 0.0) for c in fc]
                     for r in holdout], dtype=float)

    # --- Single-split sweep -------------------------------------------------
    factors = (0.94, 0.96, 0.97, 0.98)
    print("\n=== SINGLE-SPLIT sweep (delta MAE per stat) ===", flush=True)
    print(f"  {'factor':>6}  {'PTS d':>8}  {'REB d':>8}  {'BLK d':>8}  "
          f"{'agg':>10}", flush=True)
    print("  " + "-" * 50, flush=True)
    sweep_results: Dict[float, Dict[str, dict]] = {}
    best_factor = None
    best_agg = float("inf")

    report.append("## Single-split sweep (delta MAE per stat)")
    report.append("")
    report.append("| factor | PTS d | REB d | BLK d | agg(PTS+REB+BLK) d |")
    report.append("|-------:|------:|------:|------:|-------------------:|")

    for f in factors:
        res = measure_single_split(holdout, X_ho, threshold, f)
        sweep_results[f] = res
        agg = sum(res[s]["delta"] for s in _SHRINK_STATS
                  if not np.isnan(res[s]["delta"]))
        print(f"  {f:>6.2f}  {res['pts']['delta']:>+8.4f}  "
              f"{res['reb']['delta']:>+8.4f}  {res['blk']['delta']:>+8.4f}  "
              f"{agg:>+10.4f}", flush=True)
        report.append(f"| {f:.2f} | {res['pts']['delta']:+.4f} | "
                      f"{res['reb']['delta']:+.4f} | "
                      f"{res['blk']['delta']:+.4f} | {agg:+.4f} |")
        if agg < best_agg:
            best_agg = agg
            best_factor = f

    print(f"\n  Best factor (min aggregate delta): {best_factor}  "
          f"(agg delta = {best_agg:+.4f})", flush=True)
    report.append("")
    report.append(f"**Best factor:** `{best_factor}`  "
                  f"(aggregate {best_agg:+.4f})")
    report.append("")

    # --- Single-split detail at best factor --------------------------------
    res = sweep_results[best_factor]
    print(f"\n=== SINGLE-SPLIT detail @ factor={best_factor} ===", flush=True)
    print(f"  {'stat':<6} {'n':>6} {'base':>10} {'adj':>10} {'delta':>10}",
          flush=True)
    print("  " + "-" * 50, flush=True)

    report.append(f"## Single-split detail @ factor={best_factor}")
    report.append("")
    report.append("| stat | n | base | adj | delta |")
    report.append("|------|--:|-----:|----:|------:|")

    n_improved_shrink = 0
    for stat in STATS:
        r = res[stat]
        if r["n"] == 0 or np.isnan(r["delta"]):
            print(f"  {stat:<6} (no data)", flush=True)
            report.append(f"| {stat} | 0 | - | - | - |")
            continue
        verdict = ("BETTER" if r["delta"] < -0.0005
                   else "worse" if r["delta"] > 0.0005 else "flat")
        if stat in _SHRINK_STATS and r["delta"] < -0.0005:
            n_improved_shrink += 1
        print(f"  {stat:<6} {r['n']:>6d} {r['base']:>10.4f} "
              f"{r['adj']:>10.4f} {r['delta']:>+10.4f}  {verdict}",
              flush=True)
        report.append(f"| {stat} | {r['n']} | {r['base']:.4f} | "
                      f"{r['adj']:.4f} | {r['delta']:+.4f} |")
    report.append("")

    # --- Walk-forward ------------------------------------------------------
    print(f"\n=== WALK-FORWARD (4 folds) @ factor={best_factor} ===",
          flush=True)
    wf = measure_walk_forward(holdout, X_ho, threshold, best_factor,
                              n_splits=4)
    report.append(f"## Walk-forward (4 folds) @ factor={best_factor}")
    report.append("")
    report.append("| stat | f1 | f2 | f3 | f4 | mean | pos/4 |")
    report.append("|------|---:|---:|---:|---:|-----:|------:|")

    n_4of4_in_shrink = 0
    for stat in STATS:
        deltas = wf[stat]
        if not deltas or all(np.isnan(d) for d in deltas):
            print(f"  {stat:<6} (no data)", flush=True)
            report.append(f"| {stat} | - | - | - | - | - | - |")
            continue
        n_pos_folds = sum(1 for d in deltas if not np.isnan(d) and d < 0)
        valid = [d for d in deltas if not np.isnan(d)]
        mean_d = float(np.mean(valid)) if valid else float("nan")
        marker = " [4/4]" if n_pos_folds == 4 else ""
        deltas_str = [(f"{d:+.4f}" if not np.isnan(d) else "nan")
                      for d in deltas]
        print(f"  {stat:<6} folds={deltas_str}  mean={mean_d:+.4f}  "
              f"pos={n_pos_folds}/4{marker}", flush=True)
        # Pad to 4 fold cells
        cells = deltas_str + ["-"] * (4 - len(deltas_str))
        report.append(f"| {stat} | {cells[0]} | {cells[1]} | {cells[2]} | "
                      f"{cells[3]} | {mean_d:+.4f} | {n_pos_folds}/4 |")
        if stat in _SHRINK_STATS and n_pos_folds == 4:
            n_4of4_in_shrink += 1
    report.append("")

    # --- Ship gate ---------------------------------------------------------
    print("\n=== SHIP GATE ===", flush=True)
    agg_shrink_delta = sum(res[s]["delta"] for s in _SHRINK_STATS
                           if not np.isnan(res[s]["delta"]))
    gate_a = (n_improved_shrink >= 2 and agg_shrink_delta <= -0.003)
    gate_b = (n_4of4_in_shrink >= 2)
    print(f"  Gate A (single-split): {n_improved_shrink}/3 improved AND "
          f"agg {agg_shrink_delta:+.4f} <= -0.003  =>  "
          f"{'PASS' if gate_a else 'FAIL'}", flush=True)
    print(f"  Gate B (WF):           {n_4of4_in_shrink}/3 stats 4/4 folds  "
          f"=>  {'PASS' if gate_b else 'FAIL'}", flush=True)

    report.append("## Ship gate")
    report.append("")
    report.append(f"- Gate A (single-split): "
                  f"{n_improved_shrink}/3 of (PTS,REB,BLK) improved AND "
                  f"aggregate {agg_shrink_delta:+.4f} <= -0.003 -> "
                  f"**{'PASS' if gate_a else 'FAIL'}**")
    report.append(f"- Gate B (walk-forward): "
                  f"{n_4of4_in_shrink}/3 stats 4/4 folds negative -> "
                  f"**{'PASS' if gate_b else 'FAIL'}**")
    report.append("")

    if gate_a and gate_b:
        verdict = (f"SHIP factor={best_factor} "
                   f"threshold_season_pf_per_36={threshold:.4f}")
        print(f"\n  VERDICT: {verdict}", flush=True)
        report.append("## Verdict")
        report.append("")
        report.append(f"**SHIP** -- factor={best_factor}, "
                      f"threshold_season_pf_per_36={threshold:.4f}")
        report.append("")
        report.append("Gate A+B both pass with real PF signal. Wire as a "
                      "post-prediction shrink in `src/prediction/prop_pergame.py` "
                      "(constant `_APPLY_FOUL_SHRINK = True` + threshold + "
                      "factor) and dispatch from `apply_post_prediction_"
                      "adjustments` or equivalent inference call site.")
    else:
        if not gate_a and not gate_b:
            reason = "both gates failed"
        elif not gate_a:
            reason = "single-split gate failed"
        else:
            reason = "walk-forward gate failed"
        verdict = f"REJECT ({reason})"
        print(f"\n  VERDICT: {verdict}", flush=True)
        report.append("## Verdict")
        report.append("")
        report.append(f"**REJECT** -- {reason}. Even with the real "
                      f"`season_pf_per_36` signal joined per-row (cycle 91b), "
                      f"the top-quintile shrink does not survive the dual "
                      f"gate on the held-out portion. See cycle 90b lesson: "
                      f"gamelog selection bias filters out the very rows "
                      f"(early-foul bench-yanks under target minutes) that "
                      f"the hypothesis predicts -- the played rows we DO see "
                      f"are not systematically over-predicted by the model.")

    print(f"\n[probe_foul_rate_shrink_v2] verdict: {verdict}", flush=True)

    _write_report(report)
    return 0 if (gate_a and gate_b) else 0  # always 0 — verdict in stdout


if __name__ == "__main__":
    sys.exit(main())
