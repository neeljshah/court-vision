"""scripts/probe_R7_A_pregame_residual_heads.py -- R7-A probe.

Applies the heads trained by scripts/train_pregame_residual_heads.py to the
held-out OOF predictions and compares MAE vs the raw OOF baseline.

For each (stat, fold) we hold out that fold, train a fresh LightGBM head on
the remaining 3 folds, and predict the residual on the held-out fold. Adjusted
prediction = oof_pred + residual_pred. The probe MAE compares
|adjusted - actual| vs |oof_pred - actual|.

Ship gate
---------
- PTS WF MAE delta <= -0.005 (PTS ~ 4.6, so -0.005 ≈ -0.11 %)
- >= 4 / 7 stats with negative WF mean delta
- WF 4 / 4 folds negative (for shipped stats)

Writes
------
    scripts/_results/improve_R7_A_pregame_residual_heads.md
    scripts/_results/improve_R7_A_pregame_residual_heads.json

Usage
-----
    python scripts/probe_R7_A_pregame_residual_heads.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS as _STATS_LIST,
    build_pergame_dataset,
    feature_columns,
)

STATS = tuple(_STATS_LIST)
OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "pregame_residual_heads")

LGB_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "objective": "regression_l1",
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

# Ship gate
GATE_PTS_DELTA = -0.005
GATE_STAT_WINS_REQUIRED = 4


def _load_oof():
    import pandas as pd
    df = pd.read_parquet(OOF_PATH)
    df["date_short"] = df["game_date"].astype(str).str[:10]
    return df


def _build_feature_lookup(rows, stat: str) -> Tuple[Dict[Tuple[int, str], np.ndarray], List[str]]:
    fc = feature_columns(stat=stat)
    out: Dict[Tuple[int, str], np.ndarray] = {}
    for r in rows:
        pid = r.get("player_id")
        date_full = r.get("date")
        if pid is None or not date_full:
            continue
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            continue
        out[(pid_int, str(date_full)[:10])] = np.array(
            [float(r.get(c) if r.get(c) is not None else 0.0) for c in fc],
            dtype=np.float32,
        )
    return out, fc


def _wf_eval_stat(
    stat: str,
    X: np.ndarray,
    folds: np.ndarray,
    oof_pred: np.ndarray,
    actual: np.ndarray,
    feature_names: List[str],
) -> Dict:
    """For each fold, train head on the OTHER 3 folds; predict on held-out
    fold; compare |adjusted - actual| vs |oof_pred - actual|."""
    import lightgbm as lgb

    fold_records = []
    fold_wins = 0
    deltas = []

    for k in (1, 2, 3, 4):
        tr_mask = folds != k
        va_mask = folds == k
        if tr_mask.sum() == 0 or va_mask.sum() == 0:
            fold_records.append({"fold": k, "skip": True})
            continue

        y_resid_tr = actual[tr_mask] - oof_pred[tr_mask]

        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(X[tr_mask], y_resid_tr, feature_name=feature_names)
        resid_pred = model.predict(X[va_mask])

        adjusted = oof_pred[va_mask] + resid_pred
        mae_adj = float(np.mean(np.abs(adjusted - actual[va_mask])))
        mae_base = float(np.mean(np.abs(oof_pred[va_mask] - actual[va_mask])))
        delta = mae_adj - mae_base
        deltas.append(delta)
        fold_records.append({
            "fold": k,
            "n": int(va_mask.sum()),
            "mae_adj": round(mae_adj, 5),
            "mae_base": round(mae_base, 5),
            "delta": round(delta, 5),
        })
        if mae_adj < mae_base:
            fold_wins += 1

    mean_delta = float(np.mean(deltas)) if deltas else 0.0
    return {
        "stat": stat,
        "fold_wins": fold_wins,
        "mean_delta": round(mean_delta, 5),
        "folds": fold_records,
    }


def main() -> int:
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Loading OOF cache ...")
    oof = _load_oof()
    print(f"  OOF rows: {len(oof)}")

    print("Building pergame dataset ...")
    t0 = time.time()
    rows, _ = build_pergame_dataset(min_prior=0)
    print(f"  dataset rows: {len(rows)}  ({time.time()-t0:.1f}s)")

    per_stat: List[Dict] = []

    for stat in STATS:
        print(f"\n=== {stat.upper()} probe ===")
        sub = oof[oof["stat"] == stat].copy()
        if len(sub) < 500:
            per_stat.append({"stat": stat, "skip": True, "reason": "few_rows"})
            continue

        feat_lookup, fc = _build_feature_lookup(rows, stat)

        X_list, oof_list, act_list, fold_list = [], [], [], []
        miss = 0
        for _, r in sub.iterrows():
            key = (int(r["player_id"]), str(r["date_short"]))
            vec = feat_lookup.get(key)
            if vec is None:
                miss += 1
                continue
            X_list.append(vec)
            oof_list.append(float(r["oof_pred"]))
            act_list.append(float(r["actual"]))
            fold_list.append(int(r["fold"]))

        X = np.vstack(X_list).astype(np.float32)
        oof_p = np.array(oof_list, dtype=np.float32)
        actual = np.array(act_list, dtype=np.float32)
        folds = np.array(fold_list, dtype=np.int32)

        rec = _wf_eval_stat(stat, X, folds, oof_p, actual, fc)
        per_stat.append(rec)
        for f in rec["folds"]:
            if "skip" in f:
                continue
            sign = "WIN" if f["delta"] < 0 else "loss"
            print(f"  fold {f['fold']}: adj={f['mae_adj']:.4f} base={f['mae_base']:.4f} "
                  f"delta={f['delta']:+.4f} {sign}")
        print(f"  -> {stat}: {rec['fold_wins']}/4 wins, mean delta={rec['mean_delta']:+.4f}")

    # ── ship verdict ──────────────────────────────────────────────────────────
    pts_rec = next((r for r in per_stat if r.get("stat") == "pts"), None)
    pts_delta = float(pts_rec.get("mean_delta", 0.0)) if pts_rec else 0.0
    pts_pass = pts_delta <= GATE_PTS_DELTA
    stat_wins = sum(1 for r in per_stat
                    if not r.get("skip") and r.get("mean_delta", 0.0) < 0)
    wins_pass = stat_wins >= GATE_STAT_WINS_REQUIRED

    # 4/4 folds negative for shipped stats (anyone passing >=3/4 was saved by trainer)
    ship_verdict = "SHIP" if (pts_pass and wins_pass) else "REJECT"

    print(f"\n=== VERDICT ===")
    print(f"PTS mean delta = {pts_delta:+.4f}  gate <= {GATE_PTS_DELTA:+.4f}  "
          f"=> {'PASS' if pts_pass else 'FAIL'}")
    print(f"Stats with negative WF mean delta: {stat_wins}/7  "
          f"gate >= {GATE_STAT_WINS_REQUIRED}/7  => {'PASS' if wins_pass else 'FAIL'}")
    print(f"Overall: {ship_verdict}")

    out_json = {
        "verdict": ship_verdict,
        "pts_delta": pts_delta,
        "pts_gate": GATE_PTS_DELTA,
        "stat_wins": stat_wins,
        "stat_wins_gate": GATE_STAT_WINS_REQUIRED,
        "per_stat": per_stat,
    }
    with open(os.path.join(RESULTS_DIR, "improve_R7_A_pregame_residual_heads.json"),
              "w", encoding="utf-8") as fh:
        json.dump(out_json, fh, indent=2)

    md_lines = [
        "# R7-A — Pregame Residual Heads Probe",
        "",
        f"**Verdict:** {ship_verdict}",
        f"- PTS mean delta = {pts_delta:+.4f} (gate ≤ {GATE_PTS_DELTA:+.4f}) → "
        f"{'PASS' if pts_pass else 'FAIL'}",
        f"- Stats with negative mean delta: {stat_wins}/7 (gate ≥ "
        f"{GATE_STAT_WINS_REQUIRED}/7) → {'PASS' if wins_pass else 'FAIL'}",
        "",
        "| stat | folds won | mean delta | f1 | f2 | f3 | f4 |",
        "|------|-----------|------------|------|------|------|------|",
    ]
    for r in per_stat:
        if r.get("skip"):
            md_lines.append(f"| {r['stat']} | skipped | — | | | | |")
            continue
        fds = {f["fold"]: f["delta"] for f in r["folds"] if "skip" not in f}
        md_lines.append(
            f"| {r['stat']} | {r['fold_wins']}/4 | {r['mean_delta']:+.4f} | "
            f"{fds.get(1, 0):+.4f} | {fds.get(2, 0):+.4f} | "
            f"{fds.get(3, 0):+.4f} | {fds.get(4, 0):+.4f} |"
        )
    with open(os.path.join(RESULTS_DIR, "improve_R7_A_pregame_residual_heads.md"),
              "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
