"""_pts_oof_harness.py — shared leak-free OOF A/B harness for pregame per-stat
model experiments (PTS / REB).

Every experiment imports this so the fold structure, feature extraction, and
baseline comparison are byte-for-byte identical across experiments — the A/B is
therefore exact (same holdout rows, same baseline predictions).

Contract
--------
    from scripts._pts_oof_harness import (
        build_folds, feature_matrix, col_array, targets, recency_weights,
        load_base, score_and_report,
    )
    rows, folds = build_folds(stat="pts")          # folds = [(fi, tr_end, va_end, te_end), ...]
    base = load_base("pts")                          # cached production-stack OOF (oof_pred_base)
    recs = []
    for fi, tr_end, va_end, te_end in folds:
        # train ONLY on rows[:tr_end] (+ optionally rows[tr_end:va_end] for val/early-stop)
        # predict on ho = rows[va_end:te_end]
        for r, pred in zip(rows[va_end:te_end], my_preds):
            recs.append({"player_id": int(r.get("player_id",0)),
                         "game_date": str(r["date"])[:10],   # REQUIRED — unique join key
                         "fold": fi, "pred": float(pred)})
    score_and_report(recs, base, rows, label="my_experiment")

NOTE: game_id is EMPTY in build_pergame_dataset rows, so the unique join key is
(player_id, game_date, fold). Always put "game_date": str(r["date"])[:10] in each
rec. score_and_report HARD-FAILS on a non-1:1 join (no silent cartesian corruption).

The fold math mirrors scripts/cache_pergame_oof.py EXACTLY (N_SPLITS=4,
tr_end/va_end/te_end, skip thresholds). Do not change it — it must align with
the cached baseline.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import List, Tuple, Dict, Optional

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns,
)

N_SPLITS = 4
_BASE_PATH = {
    "pts": os.path.join(_ROOT, "data", "cache", "pregame_oof_pts_minmodel.parquet"),
    "reb": os.path.join(_ROOT, "data", "cache", "pregame_oof_reb_oppmodel.parquet"),
}

_rows_cache: Dict[str, list] = {}


def build_folds(stat: str = "pts", max_rows: Optional[int] = None
                ) -> Tuple[list, List[Tuple[int, int, int, int]]]:
    """Return (rows_sorted, folds). folds = list of (fold_idx_1based, tr_end, va_end, te_end).
    Identical fold geometry to cache_pergame_oof.run_oof."""
    # Row set + fold geometry are stat-INDEPENDENT (only the feature columns
    # differ per stat), so cache the built dataset once per max_rows.
    key = f"rows:{max_rows}"
    if key in _rows_cache:
        rows = _rows_cache[key]
    else:
        rows, _ = build_pergame_dataset(min_prior=0)
        rows.sort(key=lambda r: r["date"])
        if max_rows is not None and max_rows < len(rows):
            rows = rows[:max_rows]
        _rows_cache[key] = rows
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]
    folds: List[Tuple[int, int, int, int]] = []
    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == N_SPLITS - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        min_tr = max(500, int(n * 0.05))
        min_ho = max(50, int(n * 0.02))
        if tr_end < min_tr or (te_end - va_end) < min_ho:
            continue
        folds.append((fold_idx + 1, tr_end, va_end, te_end))
    return rows, folds


def col_array(rows_slice: list, cols: List[str]) -> np.ndarray:
    """Feature matrix for an arbitrary column list (handles None/NaN -> 0.0)."""
    return np.array(
        [[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows_slice],
        dtype=float,
    )


def feature_matrix(rows_slice: list, stat: str = "pts") -> Tuple[np.ndarray, List[str]]:
    """Production feature matrix for `stat` (uses feature_columns(stat))."""
    cols = feature_columns(stat=stat)
    return col_array(rows_slice, cols), cols


def targets(rows_slice: list, key: str) -> np.ndarray:
    """e.g. key='target_pts' or 'target_min'."""
    return np.array([float(r.get(key, 0.0) or 0.0) for r in rows_slice], dtype=float)


def recency_weights(rows: list, tr_end: int) -> np.ndarray:
    """Recency sample weights on rows[:tr_end] (matches cache_pergame_oof)."""
    tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    return np.exp(-0.5 * age)


def load_base(stat: str = "pts"):
    import pandas as pd
    df = pd.read_parquet(_BASE_PATH[stat])
    df["game_id"] = df["game_id"].astype(str)
    df["player_id"] = df["player_id"].astype(int)
    df["fold"] = df["fold"].astype(int)
    return df


def _fan(df, pred_col: str) -> str:
    """Bias-by-ACTUAL-minutes fan table string for pred_col vs actual."""
    import pandas as pd
    b = df.copy()
    bins = [-1, 12, 24, 32, 999]
    labels = ["<12", "12-24", "24-32", "32+"]
    b["mb"] = pd.cut(b["target_min"], bins=bins, labels=labels)
    out = []
    for lab in labels:
        s = b[b["mb"] == lab]
        if len(s) == 0:
            continue
        bias = (s[pred_col] - s["actual"]).mean()
        amae = (s[pred_col] - s["actual"]).abs().mean()
        out.append(f"    {lab:>6}: n={len(s):5d}  bias={bias:+.3f}  |bias|={abs(bias):.3f}  mae={amae:.3f}")
    return "\n".join(out)


def _slope(df, pred_col: str) -> Tuple[float, float, float]:
    """actual = a + b*pred ; returns (a, b, corr)."""
    x = df[pred_col].to_numpy(float)
    y = df["actual"].to_numpy(float)
    if x.std() < 1e-9:
        return (float("nan"), float("nan"), float("nan"))
    b, a = np.polyfit(x, y, 1)
    corr = float(np.corrcoef(x, y)[0, 1])
    return (float(a), float(b), corr)


def score_and_report(recs: List[dict], base, rows: list, label: str) -> dict:
    """Join experiment predictions to the cached baseline on (game_id, player_id,
    fold), then print + return an exact A/B report on the IDENTICAL holdout rows.
    """
    import pandas as pd
    new = pd.DataFrame(recs)
    if new.empty:
        print(f"[{label}] NO PREDICTIONS — abort"); return {}
    new["player_id"] = new["player_id"].astype(int)
    new["fold"] = new["fold"].astype(int)

    # ── JOIN KEY (must be UNIQUE per row) ──────────────────────────────────────
    # game_id is empty ("") in build_pergame_dataset rows, so (game_id, player_id,
    # fold) is NOT unique (a player has ~22 games/fold) and a naive merge cartesian-
    # explodes. The reliable unique key is (player_id, game_date[, fold]) — a player
    # plays at most one game per date. Callers SHOULD include "game_date" in each
    # rec (str(r["date"])[:10]); we fall back to game_id only if it is genuinely
    # populated, and HARD-FAIL on any non-1:1 join so corruption can never be silent.
    if "game_date" in new.columns:
        new["game_date"] = new["game_date"].astype(str).str[:10]
        base = base.copy(); base["game_date"] = base["game_date"].astype(str).str[:10]
        key = ["player_id", "game_date", "fold"]
    elif (base["game_id"].astype(str).str.len() > 0).all() and \
         not base.duplicated(["game_id", "player_id", "fold"]).any():
        new["game_id"] = new["game_id"].astype(str)
        key = ["game_id", "player_id", "fold"]
    else:
        raise ValueError(
            f"[{label}] cannot form a UNIQUE join key — game_id is empty and recs "
            f"lack 'game_date'. Add \"game_date\": str(r['date'])[:10] to each rec.")

    if base.duplicated(key).any() or new.duplicated(key).any():
        raise ValueError(f"[{label}] join key {key} is not unique on base/new — "
                         f"would cartesian-explode; aborting (no silent corruption).")

    m = base.merge(new, on=key, how="inner")
    if len(m) > len(new):
        raise ValueError(f"[{label}] join exploded ({len(m)} > {len(new)}) — bug.")
    cov = len(m) / len(base) if len(base) else 0.0

    mae_base = float((m["oof_pred_base"] - m["actual"]).abs().mean())
    mae_new = float((m["pred"] - m["actual"]).abs().mean())
    delta = mae_new - mae_base
    pct = delta / mae_base * 100.0

    print(f"\n================ {label} ================")
    print(f"join coverage: {cov*100:.1f}%  ({len(m):,} / {len(base):,} baseline rows)")
    print(f"OVERALL MAE   base={mae_base:.4f}  new={mae_new:.4f}  "
          f"delta={delta:+.4f} ({pct:+.2f}%)  "
          f"{'*** NEW WINS ***' if delta < 0 else 'baseline wins'}")

    print("per-fold MAE (base / new / delta):")
    for fi in sorted(m["fold"].unique()):
        s = m[m["fold"] == fi]
        mb = float((s["oof_pred_base"] - s["actual"]).abs().mean())
        mn = float((s["pred"] - s["actual"]).abs().mean())
        print(f"    fold {fi}: n={len(s):6d}  base={mb:.4f}  new={mn:.4f}  delta={mn-mb:+.4f}")

    print("BIAS-BY-ACTUAL-MINUTES fan — BASE:")
    print(_fan(m, "oof_pred_base"))
    print("BIAS-BY-ACTUAL-MINUTES fan — NEW:")
    print(_fan(m, "pred"))

    ab, bb, cb = _slope(m, "oof_pred_base")
    an, bn, cn = _slope(m, "pred")
    print(f"shrinkage slope  base: actual={ab:.3f}+{bb:.3f}*pred (corr {cb:.3f})")
    print(f"shrinkage slope  new : actual={an:.3f}+{bn:.3f}*pred (corr {cn:.3f})")

    # degeneracy snapshot
    p = m["pred"].to_numpy(float)
    nan = int(np.isnan(p).sum() + np.isinf(p).sum())
    print(f"degeneracy: nan/inf={nan}  range=[{p.min():.2f},{p.max():.2f}]  std={p.std():.3f}")
    print(f"GATE: {'PASS (new<base)' if delta < 0 else 'FAIL (new>=base)'}")

    return {"label": label, "coverage": cov, "mae_base": mae_base, "mae_new": mae_new,
            "delta": delta, "pct": pct, "n": len(m), "nan": nan,
            "slope_base": bb, "slope_new": bn, "pass": bool(delta < 0)}
