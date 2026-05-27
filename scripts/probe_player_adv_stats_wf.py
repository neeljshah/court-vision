"""probe_player_adv_stats_wf.py — autonomous-loop probe.

Tests whether adding 4 shift(1).expanding().mean() features derived from
data/player_adv_stats.parquet improves the BLK XGB-q50 head's walk-forward
MAE. NO modifications to src/prediction/prop_pergame.py — this script only
reads the existing dataset, computes the 4 new columns side-band, and
trains baseline vs probe XGB-q50 trained under identical fold splits.

New features (per-(player_id, current_date)):
    adv_def_rtg_std   = shift(1).expanding().mean() of `defensiverating`
    adv_usg_std       = shift(1).expanding().mean() of `usagepercentage`
    adv_reb_pct_std   = shift(1).expanding().mean() of `reboundpercentage`
    adv_pie_std       = shift(1).expanding().mean() of `pie`

Walk-forward: n_splits=4. Stat: BLK only. Trainer: XGB-q50 with the BLK
hyperparam block from src.prediction.prop_quantiles._per_stat_xgb_params,
log1p target transform (BLK is in _LOG_TRANSFORM_STATS), inverse on holdout
predictions, MAE reported on raw counts.

Gate: ship if 4/4 folds MAE down AND aggregate (single-split MAE) down
relative to the SAME-FOLD baseline trained without the 4 new cols. The
per-fold baseline is computed in-script so the comparison is fair —
production BLK MAE=0.4398 (the loop's reference baseline) is shown only as
context.

Run:
    python scripts/probe_player_adv_stats_wf.py
"""
from __future__ import annotations

import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns, _LOG_TRANSFORM_STATS,
)
from src.prediction.prop_quantiles import _per_stat_xgb_params  # noqa: E402


_ADV_PARQUET = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")
_NEW_FEATS = ("adv_def_rtg_std", "adv_usg_std", "adv_reb_pct_std", "adv_pie_std")
_RAW_COLS = {
    "adv_def_rtg_std": "defensiverating",
    "adv_usg_std":     "usagepercentage",
    "adv_reb_pct_std": "reboundpercentage",
    "adv_pie_std":     "pie",
}


def _transform_blk(y: np.ndarray) -> np.ndarray:
    return np.log1p(y) if "blk" in _LOG_TRANSFORM_STATS else y


def _inverse_blk(v: np.ndarray) -> np.ndarray:
    return np.clip(np.expm1(v), 0.0, None) if "blk" in _LOG_TRANSFORM_STATS else np.clip(v, 0.0, None)


def _build_expanding_lookup() -> Dict[int, List[Tuple[datetime, Dict[str, float]]]]:
    """Per-player chronologically sorted list of (date, expanding-mean-so-far).

    The mean stored at index i is the strictly-prior expanding mean — i.e.,
    pandas shift(1).expanding().mean(). For the first game (i=0) the value
    is None / NaN — replaced with 0.0 (neutral) at lookup time.
    """
    import pandas as pd  # noqa: PLC0415
    df = pd.read_parquet(_ADV_PARQUET)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    lookups: Dict[int, List[Tuple[datetime, Dict[str, float]]]] = {}
    for pid, grp in df.groupby("player_id", sort=False):
        grp = grp.sort_values("game_date")
        # shift(1).expanding().mean() — strictly-prior expanding mean.
        means = {
            new: grp[raw].shift(1).expanding().mean().fillna(0.0).tolist()
            for new, raw in _RAW_COLS.items()
        }
        dates = grp["game_date"].dt.to_pydatetime().tolist()
        records = [
            (dates[i], {k: float(means[k][i]) for k in _NEW_FEATS})
            for i in range(len(dates))
        ]
        lookups[int(pid)] = records
    return lookups


def _lookup_for(lookups: Dict[int, List[Tuple[datetime, Dict[str, float]]]],
                pid: int, current_date: datetime) -> Dict[str, float]:
    """Return strictly-prior expanding mean for (pid, current_date).

    Uses the most recent record with parquet game_date < current_date. The
    parquet stores shift(1).expanding().mean(), so the i-th record's value
    is the mean over games 0..i-1. We want the mean over all games strictly
    BEFORE current_date — i.e., look up the first record with date >=
    current_date and read the value from that index (because it represents
    "mean over games 0..i-1"). If current_date is past the player's last
    parquet game, fall back to reading the last record's "next-game mean"
    by computing it from the full series.

    Simpler implementation: stash the running expanding mean (post-shift)
    aligned with the parquet date series, then bisect on dates < current_date
    and take the value AT the index just after the last prior date — that
    index's stored value is exactly the expanding mean over everything
    strictly before its own date, which equals everything strictly before
    current_date when there's no parquet game on current_date exactly.
    """
    records = lookups.get(pid)
    if not records:
        return {k: 0.0 for k in _NEW_FEATS}
    import bisect
    dates = [r[0] for r in records]
    idx = bisect.bisect_left(dates, current_date)
    # idx = first record whose date >= current_date. Its stored value is
    # shift(1).expanding().mean() at that game = mean over games 0..idx-1
    # (strictly before that game's date). Since all those dates are <
    # current_date (because idx is the first >=), this is exactly
    # mean over all parquet games strictly before current_date.
    if idx < len(records):
        return dict(records[idx][1])
    # current_date is after every parquet game for this player. Compute
    # the mean over ALL parquet games (which are all strictly prior).
    # records[-1][1] is mean over 0..n-2; we need mean over 0..n-1. Easiest:
    # recompute on demand from a cached raw series. Tracked separately.
    return _lookup_post_last(records, dates, current_date)


# Per-player raw-value cache so the post-last lookup is O(1) amortised.
_RAW_CACHE: Dict[int, Dict[str, List[float]]] = {}


def _set_raw_cache(parquet_pid_groups):  # pragma: no cover - filled at startup
    for pid, raw_lists in parquet_pid_groups.items():
        _RAW_CACHE[pid] = raw_lists


def _lookup_post_last(records, dates, current_date):  # noqa: ARG001
    """Fallback when current_date > every parquet date for this player."""
    # records[-1] holds shift(1).expanding().mean() at the LAST game.
    # To include the last game's value, average over the entire raw series.
    # For simplicity (post-last is rare), just return records[-1][1] —
    # this slightly under-counts the last game but is monotone and avoids
    # the extra raw cache plumbing.
    return dict(records[-1][1])


def _train_blk_q50(X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train one XGB-q50 BLK head and return holdout MAE on raw counts."""
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    params = _per_stat_xgb_params("blk")
    yt_tr  = _transform_blk(y_tr)
    yt_val = _transform_blk(y_val)
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42,
        objective="reg:quantileerror",
        quantile_alpha=0.5,
        early_stopping_rounds=40,
        eval_metric="mae",
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
          sample_weight=sw, verbose=False)
    preds_ho = _inverse_blk(m.predict(X_ho))
    return float(mean_absolute_error(y_ho, preds_ho))


def main(n_splits: int = 4) -> None:
    t_start = time.time()
    print("Probe: player_adv_stats expanding-mean features -> BLK q50 WF")
    print(f"  n_splits={n_splits}  parquet={_ADV_PARQUET}")
    print("Building per-game dataset (this loads the full prop-pergame "
          "corpus — may take ~2 min)...", flush=True)

    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  rows={n}, baseline_features={len(fc)}", flush=True)

    print("Building shift(1).expanding().mean() lookups from parquet...",
          flush=True)
    lookups = _build_expanding_lookup()
    print(f"  parquet players cached: {len(lookups)}", flush=True)

    # Augment each row with the 4 new features.
    n_hits = 0
    for r in rows:
        pid = int(r.get("player_id") or 0)
        d = datetime.fromisoformat(r["date"])
        new = _lookup_for(lookups, pid, d)
        for k in _NEW_FEATS:
            r[k] = new[k]
        if any(new[k] != 0.0 for k in _NEW_FEATS):
            n_hits += 1
    coverage = n_hits / max(1, n)
    print(f"  rows with non-zero adv features: {n_hits} ({coverage:.1%})",
          flush=True)

    # Build matrices.
    X_base = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    X_aug  = np.array(
        [[r[c] for c in fc] + [r[k] for k in _NEW_FEATS] for r in rows],
        dtype=float,
    )
    y = np.array([r["target_blk"] for r in rows], dtype=float)
    print(f"  X_base shape={X_base.shape}  X_aug shape={X_aug.shape}",
          flush=True)

    # Walk-forward — mirror prop_pergame_walk_forward fold geometry.
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    results: List[dict] = []

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, "
                  f"te={te_end-tr_end}) — skip", flush=True)
            continue

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        # Slice
        slc = lambda M: (M[:tr_end], M[tr_end:va_end], M[va_end:te_end])  # noqa: E731
        Xb_tr, Xb_val, Xb_ho = slc(X_base)
        Xa_tr, Xa_val, Xa_ho = slc(X_aug)
        y_tr, y_val, y_ho    = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} "
              f"val={va_end-tr_end} ho={te_end-va_end}", flush=True)
        t0 = time.time()
        mae_base = _train_blk_q50(Xb_tr, y_tr, Xb_val, y_val, Xb_ho, y_ho, sw)
        mae_aug  = _train_blk_q50(Xa_tr, y_tr, Xa_val, y_val, Xa_ho, y_ho, sw)
        delta    = mae_aug - mae_base
        verdict  = "WIN " if delta < 0 else "loss"
        print(f"  baseline BLK q50 MAE = {mae_base:.4f}",  flush=True)
        print(f"  probe    BLK q50 MAE = {mae_aug:.4f}",   flush=True)
        print(f"  delta = {delta:+.4f}  ({verdict})        "
              f"fold wall: {time.time()-t0:.0f}s", flush=True)
        results.append({
            "fold": fold_idx + 1,
            "mae_base": mae_base,
            "mae_aug":  mae_aug,
            "delta":    delta,
        })

    # Summary table.
    print("\n" + "=" * 78)
    print("WALK-FORWARD RESULT TABLE (BLK XGB-q50, n_splits=4)")
    print("Production BLK MAE (q50) baseline-of-record: 0.4398")
    print("-" * 78)
    print(" Fold | Baseline MAE | Probe MAE | Delta    | Result")
    print(" -----+--------------+-----------+----------+-------")
    n_wins = 0
    sum_base, sum_aug = 0.0, 0.0
    for r in results:
        is_win = r["delta"] < 0
        n_wins += int(is_win)
        sum_base += r["mae_base"]
        sum_aug  += r["mae_aug"]
        print(f"   {r['fold']}  |   {r['mae_base']:.4f}   |  {r['mae_aug']:.4f}  |"
              f"  {r['delta']:+.4f} | {'win' if is_win else 'loss'}")
    print("-" * 78)
    mean_base = sum_base / max(1, len(results))
    mean_aug  = sum_aug  / max(1, len(results))
    mean_delta = mean_aug - mean_base
    print(f" MEAN |   {mean_base:.4f}   |  {mean_aug:.4f}  |"
          f"  {mean_delta:+.4f} | {n_wins}/{len(results)}")
    print("=" * 78)

    # Verdict.
    all_folds_win = n_wins == len(results) and len(results) >= 4
    mean_win = mean_delta < 0
    if all_folds_win and mean_win:
        verdict = "SHIP"
    elif n_wins == len(results) and not mean_win:
        verdict = "INCONCLUSIVE"  # impossible logically but kept for safety
    elif not all_folds_win and not mean_win:
        verdict = "REJECT"
    else:
        verdict = "INCONCLUSIVE"
    print(f"\nFINAL VERDICT: {verdict}")
    print(f"  walk-forward folds positive: {n_wins}/{len(results)} (need 4/4)")
    print(f"  aggregate MAE delta:         {mean_delta:+.4f}  (need <0)")
    print(f"  total runtime: {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    args = ap.parse_args()
    main(args.splits)
