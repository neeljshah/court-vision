"""context_fusion_walkforward.py — leak-free walk-forward: context-conditional vs static fusion.

The central V6 question (architecture-law gate): does CONTEXT-CONDITIONAL fusion of the
three as-of engine arms (m_power / m_team / m_ff) beat STATIC fusion on a leak-free
walk-forward?  If YES -> the context-router may apply a gated marginal.  If NO -> the
LLM read stays SCOUTING / NARRATION only (still the product value) and the marginal is
untouched.  Either verdict is recorded honestly.

Substrate (NO future leakage — every arm prediction is as-of the game date):
    data/cache/team_system/engine_asof_preds.parquet   (1002 games, m_*/wp_*/sd_*)
    margin = actual home margin (the target)

Walk-forward protocol:
    * sort by date; expanding-window, retrain at each step boundary (monthly blocks).
    * STATIC  : one fixed NNLS weight vector over (m_power,m_team,m_ff) fit on train.
    * CONTEXT : SEPARATE NNLS weight vectors per leak-free context bucket fit on train,
                selected forward by the SAME pre-tip context of the eval game.
                Context dimension tested = home-favored vs road-favored (sign of mean arm),
                a strictly pre-tip signal.  This is the honest "does conditioning the
                fusion on context help?" question.
    * Compare per-game |error| ; bootstrap 95% CI on (context - static).
      CI upper < 0  => context beats static (CONDITIONAL_MARGINAL_ALLOWED).
      else          => SCOUTING_ONLY (honest null; LLM stays narration).

Py3.9, type hints.  honesty_class = "research".  Writes context/_fusion_walkforward.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_TS = os.path.join(_ROOT, "data", "cache", "team_system")
_CONTEXT_DIR = os.path.join(_TS, "context")
HONESTY_CLASS = "research"

_ARMS = ["m_power", "m_team", "m_ff"]


def _nnls_weights(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Non-negative least squares blend weights (sum-to-1 normalised). Leak-free: train only."""
    from scipy.optimize import nnls
    if len(y) < 4:
        return np.ones(X.shape[1]) / X.shape[1]
    try:
        w, _ = nnls(X, y)
        if w.sum() <= 1e-9:
            return np.ones(X.shape[1]) / X.shape[1]
        return w / w.sum()
    except Exception:
        return np.ones(X.shape[1]) / X.shape[1]


def _context_bucket(row: pd.Series) -> str:
    """Leak-free pre-tip context: is the (arm-consensus) home margin positive or negative?
    Uses only the as-of arm predictions — never the outcome."""
    consensus = float(np.mean([row[a] for a in _ARMS]))
    return "home_fav" if consensus >= 0 else "road_fav"


def run(seed: int = 7, n_boot: int = 4000) -> Dict:
    path = os.path.join(_TS, "engine_asof_preds.parquet")
    if not os.path.exists(path):
        return {"error": f"substrate not found: {path}"}
    df = pd.read_parquet(path).sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=_ARMS + ["margin"]).reset_index(drop=True)
    df["context"] = df.apply(_context_bucket, axis=1)

    # Monthly expanding-window walk-forward boundaries.
    df["ym"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    months = sorted(df["ym"].unique())
    # Need a warm-up train block; start evaluating from the 3rd month onward.
    static_err: List[float] = []
    context_err: List[float] = []
    n_eval = 0

    for i in range(2, len(months)):
        train = df[df["ym"].isin(months[:i])]
        eval_ = df[df["ym"] == months[i]]
        if len(train) < 30 or len(eval_) == 0:
            continue

        Xtr = train[_ARMS].values
        ytr = train["margin"].values

        # STATIC: one weight vector over all train.
        w_static = _nnls_weights(Xtr, ytr)

        # CONTEXT: separate weight vector per context bucket (train-only).
        w_ctx: Dict[str, np.ndarray] = {}
        for b in ("home_fav", "road_fav"):
            tb = train[train["context"] == b]
            if len(tb) >= 8:
                w_ctx[b] = _nnls_weights(tb[_ARMS].values, tb["margin"].values)
            else:
                w_ctx[b] = w_static  # fall back to static if bucket too thin (leak-free)

        for _, r in eval_.iterrows():
            x = r[_ARMS].values.astype(float)
            y = float(r["margin"])
            p_static = float(np.dot(w_static, x))
            p_ctx = float(np.dot(w_ctx[r["context"]], x))
            static_err.append(abs(y - p_static))
            context_err.append(abs(y - p_ctx))
            n_eval += 1

    static_err_a = np.array(static_err)
    context_err_a = np.array(context_err)
    diffs = context_err_a - static_err_a  # negative => context better

    rng = np.random.default_rng(seed)
    boots = np.array([
        np.mean(rng.choice(diffs, size=len(diffs), replace=True))
        for _ in range(n_boot)
    ])
    ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    beats = ci_hi < 0.0

    verdict = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "substrate": "engine_asof_preds.parquet",
        "n_eval": int(n_eval),
        "static_mae": round(float(static_err_a.mean()), 4),
        "context_mae": round(float(context_err_a.mean()), 4),
        "delta_mean": round(float(diffs.mean()), 4),
        "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "context_beats_static": bool(beats),
        "decision": "CONDITIONAL_MARGINAL_ALLOWED" if beats else "SCOUTING_ONLY",
        "context_dimension": "home_fav vs road_fav (sign of as-of arm consensus, pre-tip)",
        "note": (
            "Context-conditional fusion beats static (CI excludes 0). Gated marginal allowed."
            if beats else
            "Context-conditional fusion does NOT beat static fusion on a leak-free "
            "walk-forward (CI includes/above 0). HONEST VERDICT: SCOUTING-NARRATION-ONLY. "
            "The LLM context read (context vector + war-room brief) is the product value; "
            "the marginal point model stays untouched. This is a SUCCESS per the architecture."
        ),
        "honesty_class": HONESTY_CLASS,
    }
    os.makedirs(_CONTEXT_DIR, exist_ok=True)
    with open(os.path.join(_CONTEXT_DIR, "_fusion_walkforward.json"), "w") as f:
        json.dump(verdict, f, indent=2)
    return verdict


if __name__ == "__main__":
    v = run()
    print(json.dumps(v, indent=2))
