"""sweep_winprob_common.py — shared scaffold for per-knob WinProb sweeps.

The per-knob sweep drivers (sweep_winprob_<knob>.py) all share the same
moving parts: read cached season-game rows, drop any FEATURE_COL absent
from the cache (schema drift), train XGBClassifier with one knob varied
across a grid, score val accuracy + Brier, write a results JSON, evaluate
the workday-loop ship gate vs an in-sweep apples-to-apples baseline.

This module exposes `run_sweep(knob, grid, baseline_value, fixed_params,
result_filename)` so each driver becomes ~30 LOC: declare the knob name,
grid, prod default, fixed params, and the result file. Everything else
lives here.

Read-only on production state: never overwrites win_prob_metrics.json and
never saves a model. Ship gate (workday-loop spec): Brier improves by
>0.001 OR accuracy improves by >=0.5pp vs in-sweep baseline.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.win_probability import (  # noqa: E402
    _MODEL_DIR,
    _MODEL_FEATURE_COLS,
    _fetch_season_games,
)


# Training seasons (matches win_probability.train() default).
SEASONS: List[str] = ["2022-23", "2023-24", "2024-25"]


def _prod_metrics() -> Tuple[float, float]:
    """Read accuracy/brier from the saved metrics JSON (informational only)."""
    path = os.path.join(_MODEL_DIR, "win_prob_metrics.json")
    if os.path.exists(path):
        with open(path) as f:
            m = json.load(f)
        return float(m.get("accuracy", 0.685)), float(m.get("brier", 0.209))
    return 0.685, 0.209


def _build_dataset() -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Materialize the chronologically-ordered X/y for the win-prob model.

    Drops `_MODEL_FEATURE_COLS` entries not present in every cached row so
    that schema drift (e.g. sim_* missing from v8 cache) does not crash.
    """
    rows: list = []
    for s in SEASONS:
        s_rows = _fetch_season_games(s)
        if not s_rows:
            raise RuntimeError(f"empty cache for {s} — run train() first to warm")
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games")

    df = pd.DataFrame(rows).dropna(subset=["home_win"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    available = [c for c in _MODEL_FEATURE_COLS if c in df.columns]
    missing   = [c for c in _MODEL_FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  [warn] {len(missing)} feature(s) absent from cache "
              f"(schema drift); sweep will use {len(available)} of "
              f"{len(_MODEL_FEATURE_COLS)}: missing={missing}")

    X = df[available].values.astype(np.float32)
    y = df["home_win"].values.astype(int)
    return X, y, available


def _fit_eval(
    X: np.ndarray,
    y: np.ndarray,
    knob_value: Any,
    knob: str,
    fixed_params: Dict[str, Any],
) -> Tuple[float, float]:
    """Train XGB with knob=knob_value and fixed_params; return (acc, brier).

    The split is the same chronological 80/20 production uses. No model is
    saved.
    """
    params = dict(fixed_params)
    params[knob] = knob_value
    return _fit_eval_config(X, y, params)


def _fit_eval_config(
    X: np.ndarray,
    y: np.ndarray,
    params: Dict[str, Any],
) -> Tuple[float, float]:
    """Train XGB with a fully-specified params dict; return (acc, brier).

    Same chronological 80/20 split as production. No model saved. Used by
    both `run_sweep` (via `_fit_eval`) and `compare_configs`.
    """
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss

    split = int(len(X) * 0.8)
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]

    clf = XGBClassifier(**params)
    clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    probs = clf.predict_proba(X_val)[:, 1]
    acc   = float(accuracy_score(y_val, (probs >= 0.5).astype(int)))
    brier = float(brier_score_loss(y_val, probs))
    return acc, brier


def run_sweep(
    knob: str,
    grid: Sequence[Any],
    baseline_value: Any,
    fixed_params: Dict[str, Any],
    result_filename: str,
    knob_fmt: str = "{:.3f}",
) -> Dict[str, Any]:
    """Drive a single-knob sweep over `grid` for the WinProbability model.

    Args:
        knob: XGB param name being swept (must NOT be in fixed_params).
        grid: Values to try. `baseline_value` MUST be in `grid`.
        baseline_value: Production default for `knob` — used as the
            in-sweep apples-to-apples baseline for the ship-gate check.
        fixed_params: XGB kwargs held constant across the sweep.
        result_filename: Filename (just basename) inside `_MODEL_DIR` to
            write the JSON results to.
        knob_fmt: Format spec for printing knob values.

    Returns:
        The result payload dict that also gets written to disk.
    """
    if baseline_value not in grid:
        raise RuntimeError(
            f"grid {list(grid)} must include baseline {baseline_value!r}"
        )
    if knob in fixed_params:
        raise RuntimeError(f"knob {knob!r} must not be in fixed_params")

    print(f"Win-Probability {knob} sweep (grid={list(grid)})\n")
    file_acc, file_brier = _prod_metrics()
    print(f"Prod metrics file: accuracy={file_acc:.4f}  Brier={file_brier:.4f} "
          f"(informational only)")

    print("\nBuilding dataset from cached season games...")
    X, y, features_used = _build_dataset()
    print(f"  Dataset: n={len(X)} games | home win rate {y.mean():.1%} "
          f"| features={X.shape[1]}\n")

    results: Dict[Any, Tuple[float, float]] = {}
    for v in grid:
        acc, brier = _fit_eval(X, y, v, knob, fixed_params)
        results[v] = (acc, brier)
        print(f"  {knob}={knob_fmt.format(v)}  "
              f"acc {acc:.4f}  brier {brier:.4f}")

    base_acc, base_brier = results[baseline_value]
    print(f"\nIn-sweep baseline ({knob}={knob_fmt.format(baseline_value)}): "
          f"acc {base_acc:.4f}  brier {base_brier:.4f}")
    print("Deltas vs in-sweep baseline:")
    for v in grid:
        a, b = results[v]
        d_acc_pp = (a - base_acc) * 100
        d_brier  = b - base_brier
        print(f"  {knob}={knob_fmt.format(v)}  "
              f"d_acc {d_acc_pp:+.2f}pp  d_brier {d_brier:+.4f}")

    best_v = min(results, key=lambda x: results[x][1])
    best_acc, best_brier = results[best_v]
    d_acc_pp = (best_acc - base_acc) * 100
    d_brier  = best_brier - base_brier
    print("\n=== Winner (by Brier) ===")
    print(f"  {knob}={knob_fmt.format(best_v)}  "
          f"acc {best_acc:.4f}  brier {best_brier:.4f}")
    print(f"  vs {knob}={knob_fmt.format(baseline_value)}: "
          f"d_acc {d_acc_pp:+.2f}pp  d_brier {d_brier:+.4f}")

    ships = (d_brier < -0.001) or (d_acc_pp >= 0.5)
    print(f"  Ship gate: {'PASS' if ships else 'FAIL'}  "
          f"(needs d_brier < -0.001 OR d_acc >= +0.5pp)")

    payload: Dict[str, Any] = {
        "knob": knob,
        "grid": list(grid),
        "seasons": SEASONS,
        "fixed_params": fixed_params,
        "features_used": features_used,
        "n_features_used": len(features_used),
        "prod_metrics_file": {"accuracy": file_acc, "brier": file_brier},
        "in_sweep_baseline_value": baseline_value,
        "in_sweep_baseline": {"accuracy": base_acc, "brier": base_brier},
        "results": {str(v): {"accuracy": a, "brier": b}
                    for v, (a, b) in results.items()},
        "winner": {"value": best_v,
                   "accuracy": best_acc, "brier": best_brier,
                   "delta_acc_pp": d_acc_pp,
                   "delta_brier": d_brier,
                   "ships": bool(ships)},
    }
    out_path = os.path.join(_MODEL_DIR, result_filename)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {out_path}")
    return payload


def compare_configs(
    configs: Dict[str, Dict[str, Any]],
    baseline_name: str,
    result_filename: str,
) -> Dict[str, Any]:
    """Compare N named full XGB configs against one named as baseline.

    Each entry in `configs` is a complete kwargs dict for XGBClassifier
    (unlike `run_sweep` which holds most params fixed and varies one). Trains
    every config on the same chronological 80/20 split, reports val accuracy
    + Brier, and evaluates the workday-loop ship gate vs the baseline.

    Args:
        configs: Mapping from human label -> XGB kwargs dict.
        baseline_name: Key into `configs` to use as the comparator. Must be
            present.
        result_filename: Basename inside `_MODEL_DIR` to write JSON to.

    Returns:
        The payload dict that also lands on disk.
    """
    if baseline_name not in configs:
        raise RuntimeError(
            f"baseline {baseline_name!r} not in configs={list(configs)}"
        )

    print(f"Win-Probability config comparison "
          f"(configs={list(configs)}, baseline={baseline_name!r})\n")
    file_acc, file_brier = _prod_metrics()
    print(f"Prod metrics file: accuracy={file_acc:.4f}  Brier={file_brier:.4f} "
          f"(informational only)")

    print("\nBuilding dataset from cached season games...")
    X, y, features_used = _build_dataset()
    print(f"  Dataset: n={len(X)} games | home win rate {y.mean():.1%} "
          f"| features={X.shape[1]}\n")

    results: Dict[str, Tuple[float, float]] = {}
    for name, params in configs.items():
        acc, brier = _fit_eval_config(X, y, params)
        results[name] = (acc, brier)
        print(f"  {name:>20s}  acc {acc:.4f}  brier {brier:.4f}")

    base_acc, base_brier = results[baseline_name]
    print(f"\nBaseline ({baseline_name}): acc {base_acc:.4f}  brier {base_brier:.4f}")
    print("Deltas vs baseline:")
    deltas: Dict[str, Dict[str, float]] = {}
    ships_any = False
    for name, (a, b) in results.items():
        d_acc_pp = (a - base_acc) * 100
        d_brier  = b - base_brier
        ships    = (d_brier < -0.001) or (d_acc_pp >= 0.5)
        deltas[name] = {"d_acc_pp": d_acc_pp, "d_brier": d_brier,
                        "ships": bool(ships)}
        flag = "SHIPS" if ships and name != baseline_name else (
            "BASE " if name == baseline_name else "     ")
        print(f"  {name:>20s}  d_acc {d_acc_pp:+.2f}pp  "
              f"d_brier {d_brier:+.4f}  {flag}")
        if ships and name != baseline_name:
            ships_any = True

    print(f"\nShip gate (any non-baseline beats it): "
          f"{'PASS' if ships_any else 'FAIL'}")

    payload: Dict[str, Any] = {
        "configs": configs,
        "baseline_name": baseline_name,
        "seasons": SEASONS,
        "features_used": features_used,
        "n_features_used": len(features_used),
        "prod_metrics_file": {"accuracy": file_acc, "brier": file_brier},
        "results": {n: {"accuracy": a, "brier": b}
                    for n, (a, b) in results.items()},
        "deltas_vs_baseline": deltas,
        "any_config_ships": bool(ships_any),
    }
    out_path = os.path.join(_MODEL_DIR, result_filename)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {out_path}")
    return payload
