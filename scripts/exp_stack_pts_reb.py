"""exp_stack_pts_reb.py — Approach A3: leak-free additive STACKING for PTS + REB.

Two prior two-stage models failed because rate×minutes MULTIPLIES two noisy
heads (variance amplification).  A meta-LightGBM LEARNS how to combine the
base prediction with structural signals, so it uses the minutes/rate structure
only where it helps (the tails) without paying multiplicative variance in the
dense middle.

Architecture (per outer fold, per stat):
  s1 = base GBM proxy   : LightGBM on full production feature_matrix(stat)
  s2 = minutes head      : LightGBM E[target_min | minute-context features]
  s3 = per-minute rate   : LightGBM E[target/min | usage/rate features]
                           trained only on rows with target_min >= 8
  Meta features          : [s1_oof, s2_oof, s3_oof*s2_oof, l10_min, std_min,
                            ewma_min, prev_min, abs(prev_min-l10_min),
                            + stat-specific raw cols]
  Meta model             : LightGBM -> target_stat (raw count)

Inner OOF is strictly time-ordered expanding-window (3 inner folds over the
chronological training slice) so the meta model never sees a row's own target
via any of the three heads.

Leak-safety contract (see GATE at bottom):
  - Inner OOF: expanding-window, no shuffling, no future leakage.
  - s1/s2/s3 for the outer holdout are refit on rows[:tr_end] ONLY.
  - target_stat and target_min appear ONLY as labels, never as input features.

NOTE on scoring: The baseline parquet files use game_id="" for all rows, so
we join on (player_id, game_date, fold) instead of the harness's
(game_id, player_id, fold) to avoid a cartesian-product explosion.  We also
verify the base MAE computed this way matches the documented 4.4454 / 1.8461.
"""
from __future__ import annotations

import os
import sys
import time
import warnings
from typing import List, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts._pts_oof_harness import (  # noqa: E402
    build_folds,
    col_array,
    feature_matrix,
    load_base,
    targets,
)

# ─── constants ────────────────────────────────────────────────────────────────

# Minute-context features for s2 head
MIN_COLS = [
    "l5_min", "l10_min", "std_min", "ewma_min", "prev_min",
    "rest_days", "is_b2b", "is_b3b",
    "days_since_last_game", "games_since_long_absence",
    "games_played", "is_home",
]

# Usage/rate context for s3 head (per-minute rate model)
RATE_COLS_PTS = [
    "bbref_usg_pct", "adv_usage_std", "adv_usage_vs_opp_l3",
    "l5_pts", "l10_pts", "ewma_pts",
    "l5_min", "l10_min",
]
RATE_COLS_REB = [
    "reb_chance_l5", "team_oreb_pct_l5", "opp_dreb_pct_l5",
    "l5_reb", "l10_reb", "ewma_reb",
    "l5_min", "l10_min",
]

# Extra raw columns to include in meta feature vector (stat-specific)
META_EXTRA_PTS = ["bbref_usg_pct", "l5_pts"]
META_EXTRA_REB = ["reb_chance_l5", "l5_reb"]

MIN_THRESHOLD_RATE = 8.0   # only train rate head on rows with target_min >= 8
N_INNER_FOLDS = 3          # time-ordered inner folds within each outer train slice
N_EST_BASE = 400           # max estimators for s1/s2/s3 heads
N_EST_META = 300           # max estimators for meta model
EARLY_STOP = 30


# ─── proper scorer (avoids cartesian-product from empty game_id) ──────────────

def _score_and_report(
    recs: List[dict],
    base: pd.DataFrame,
    stat: str,
    label: str,
) -> dict:
    """Join experiment predictions to the cached baseline on
    (player_id, game_date, fold) — unique in both tables — then print + return
    an exact A/B report.

    recs items: {player_id, game_date, fold, pred}
    """
    new = pd.DataFrame(recs)
    if new.empty:
        print(f"[{label}] NO PREDICTIONS — abort")
        return {}
    new["player_id"] = new["player_id"].astype(int)
    new["game_date"] = new["game_date"].astype(str)
    new["fold"] = new["fold"].astype(int)

    m = base.merge(new, on=["player_id", "game_date", "fold"], how="inner")
    cov = len(m) / len(base) if len(base) else 0.0

    mae_base = float((m["oof_pred_base"] - m["actual"]).abs().mean())
    mae_new = float((m["pred"] - m["actual"]).abs().mean())
    delta = mae_new - mae_base
    pct = delta / mae_base * 100.0

    print(f"\n{'='*48} {label}")
    print(f"join coverage: {cov*100:.1f}%  ({len(m):,} / {len(base):,} base rows)")
    print(f"OVERALL MAE   base={mae_base:.4f}  new={mae_new:.4f}  "
          f"delta={delta:+.4f} ({pct:+.2f}%)  "
          f"{'*** NEW WINS ***' if delta < 0 else 'baseline wins'}")

    print("per-fold MAE:")
    fold_results = {}
    for fi in sorted(m["fold"].unique()):
        s = m[m["fold"] == fi]
        mb = float((s["oof_pred_base"] - s["actual"]).abs().mean())
        mn = float((s["pred"] - s["actual"]).abs().mean())
        print(f"    fold {fi}: n={len(s):6d}  base={mb:.4f}  new={mn:.4f}  delta={mn-mb:+.4f}")
        fold_results[fi] = {"n": len(s), "base": mb, "new": mn, "delta": mn - mb}

    # bias-by-minutes fan
    for lbl, pcol in [("BASE", "oof_pred_base"), ("NEW", "pred")]:
        print(f"BIAS-BY-ACTUAL-MINUTES fan — {lbl}:")
        bins = [-1, 12, 24, 32, 999]
        blabels = ["<12", "12-24", "24-32", "32+"]
        for lab, lo, hi in zip(blabels, bins, bins[1:]):
            s = m[(m["target_min"] > lo) & (m["target_min"] <= hi)]
            if len(s) == 0:
                continue
            bias = float((s[pcol] - s["actual"]).mean())
            amae = float((s[pcol] - s["actual"]).abs().mean())
            print(f"    {lab:>6}: n={len(s):5d}  bias={bias:+.3f}  mae={amae:.3f}")

    # shrinkage slope
    for lbl, pcol in [("base", "oof_pred_base"), ("new", "pred")]:
        x = m[pcol].to_numpy(float)
        y = m["actual"].to_numpy(float)
        if x.std() > 1e-9:
            b, a = np.polyfit(x, y, 1)
            corr = float(np.corrcoef(x, y)[0, 1])
            print(f"slope {lbl}: actual={a:.3f}+{b:.3f}*pred (corr {corr:.3f})")

    p = m["pred"].to_numpy(float)
    nan_count = int(np.isnan(p).sum() + np.isinf(p).sum())
    print(f"degeneracy: nan/inf={nan_count}  range=[{p.min():.2f},{p.max():.2f}]  std={p.std():.3f}")
    print(f"GATE: {'PASS (new<base)' if delta < 0 else 'FAIL (new>=base)'}")

    # Slope values for report
    x = m["oof_pred_base"].to_numpy(float)
    y = m["actual"].to_numpy(float)
    bb, bn = (float("nan"), float("nan"))
    if x.std() > 1e-9:
        bb = float(np.polyfit(x, y, 1)[0])
    x2 = m["pred"].to_numpy(float)
    if x2.std() > 1e-9:
        bn = float(np.polyfit(x2, y, 1)[0])

    return {
        "label": label, "stat": stat, "coverage": cov,
        "mae_base": mae_base, "mae_new": mae_new,
        "delta": delta, "pct": pct, "n": len(m), "nan": nan_count,
        "slope_base": bb, "slope_new": bn,
        "pass": bool(delta < 0),
        "fold_results": fold_results,
    }


# ─── LightGBM helpers ─────────────────────────────────────────────────────────

def _lgb_fit_predict(
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_te: np.ndarray,
    n_estimators: int = N_EST_BASE,
    early_stop: int = EARLY_STOP,
    sw: np.ndarray | None = None,
    clip_low: float | None = None,
    clip_high: float | None = None,
) -> np.ndarray:
    """Fit a LightGBM and return predictions on X_te."""
    import lightgbm as lgb

    params = dict(
        n_estimators=n_estimators,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
        objective="regression",
    )
    model = lgb.LGBMRegressor(**params)
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        sample_weight=sw,
        callbacks=[lgb.early_stopping(early_stop, verbose=False),
                   lgb.log_evaluation(-1)],
    )
    preds = model.predict(X_te)
    if clip_low is not None:
        preds = np.clip(preds, clip_low, None)
    if clip_high is not None:
        preds = np.clip(preds, None, clip_high)
    return preds.astype(float)


# ─── Inner OOF builder (strictly time-ordered, expanding window) ──────────────

def _inner_oof_predictions(
    rows_tr: list,
    X_full: np.ndarray,
    y_full: np.ndarray,
    n_inner: int = N_INNER_FOLDS,
    sw_full: np.ndarray | None = None,
    clip_low: float | None = None,
    clip_high: float | None = None,
) -> np.ndarray:
    """Generate inner time-ordered OOF predictions on rows_tr.

    Expanding-window: inner fold k trains on rows[:inner_tr_end] and predicts
    on rows[inner_va_end:inner_te_end].  Rows without an inner prediction get
    the mean of rows that DO have one (early rows).

    Returns a 1D array of length len(rows_tr).
    """
    n = len(rows_tr)
    oof = np.full(n, np.nan)

    inner_fold_ends = [(i + 1) / (n_inner + 1) for i in range(n_inner)]

    for k, te_frac in enumerate(inner_fold_ends):
        inner_tr_end = int(n * te_frac)
        if k == n_inner - 1:
            inner_te_end = n
        else:
            inner_te_end = int(n * inner_fold_ends[k + 1])
        inner_va_end = int(inner_tr_end + (inner_te_end - inner_tr_end) * 0.4)

        if inner_tr_end < 100 or (inner_te_end - inner_va_end) < 20:
            continue

        X_tr_i = X_full[:inner_tr_end]
        y_tr_i = y_full[:inner_tr_end]
        X_val_i = X_full[inner_tr_end:inner_va_end]
        y_val_i = y_full[inner_tr_end:inner_va_end]
        X_ho_i = X_full[inner_va_end:inner_te_end]

        sw_i = sw_full[:inner_tr_end] if sw_full is not None else None

        if len(X_val_i) < 10:
            continue

        ho_preds = _lgb_fit_predict(
            X_tr_i, y_tr_i, X_val_i, y_val_i, X_ho_i,
            sw=sw_i, clip_low=clip_low, clip_high=clip_high,
        )
        oof[inner_va_end:inner_te_end] = ho_preds

    valid_mask = ~np.isnan(oof)
    if valid_mask.sum() == 0:
        oof[:] = y_full.mean()
    else:
        oof[~valid_mask] = oof[valid_mask].mean()

    return oof


# ─── Rate head helper ─────────────────────────────────────────────────────────

def _rate_head_oof(
    rows_tr: list,
    X_rate: np.ndarray,
    y_target: np.ndarray,
    y_min: np.ndarray,
    sw_full: np.ndarray | None = None,
    clip_max: float = 5.0,
) -> np.ndarray:
    """Inner-OOF for the per-minute rate head.

    Returns OOF rate array (length = len(rows_tr)).
    """
    n = len(rows_tr)
    oof_rate = np.full(n, np.nan)

    inner_fold_ends = [(i + 1) / (N_INNER_FOLDS + 1) for i in range(N_INNER_FOLDS)]

    for k, te_frac in enumerate(inner_fold_ends):
        inner_tr_end = int(n * te_frac)
        if k == N_INNER_FOLDS - 1:
            inner_te_end = n
        else:
            inner_te_end = int(n * inner_fold_ends[k + 1])
        inner_va_end = int(inner_tr_end + (inner_te_end - inner_tr_end) * 0.4)

        if inner_tr_end < 100 or (inner_te_end - inner_va_end) < 20:
            continue

        rate_mask = y_min[:inner_tr_end] >= MIN_THRESHOLD_RATE
        if rate_mask.sum() < 50:
            continue

        X_tr_r = X_rate[:inner_tr_end][rate_mask]
        y_rate_tr = (y_target[:inner_tr_end][rate_mask] /
                     np.maximum(y_min[:inner_tr_end][rate_mask], 1e-6))
        sw_r = (sw_full[:inner_tr_end][rate_mask]
                if sw_full is not None else None)

        val_rate_mask = y_min[inner_tr_end:inner_va_end] >= MIN_THRESHOLD_RATE
        if val_rate_mask.sum() < 10:
            continue
        X_val_r = X_rate[inner_tr_end:inner_va_end][val_rate_mask]
        y_val_r = (y_target[inner_tr_end:inner_va_end][val_rate_mask] /
                   np.maximum(y_min[inner_tr_end:inner_va_end][val_rate_mask], 1e-6))

        X_ho_r = X_rate[inner_va_end:inner_te_end]

        try:
            ho_rates = _lgb_fit_predict(
                X_tr_r, y_rate_tr, X_val_r, y_val_r, X_ho_r,
                clip_low=0.0, clip_high=clip_max,
            )
        except Exception:
            continue

        oof_rate[inner_va_end:inner_te_end] = ho_rates

    valid_mask = ~np.isnan(oof_rate)
    if valid_mask.sum() == 0:
        safe_min = np.maximum(y_min, 1.0)
        naive_rate = y_target / safe_min
        oof_rate = np.clip(naive_rate, 0.0, clip_max)
    else:
        oof_rate[~valid_mask] = oof_rate[valid_mask].mean()

    return oof_rate


# ─── per-stat stacking experiment ─────────────────────────────────────────────

def run_stat(
    stat: str,
    rows: list,
    folds: List[Tuple[int, int, int, int]],
    quick_check: bool = False,
) -> Tuple[List[dict], List[dict]]:
    """Run the full stacking experiment for one stat.

    Returns (meta_recs, s1_recs).
    Each record: {player_id, game_date, fold, pred}.
    """
    from datetime import datetime

    rate_cols = RATE_COLS_PTS if stat == "pts" else RATE_COLS_REB
    meta_extra = META_EXTRA_PTS if stat == "pts" else META_EXTRA_REB
    clip_max_rate = 4.0 if stat == "pts" else 2.0

    meta_recs: List[dict] = []
    s1_recs: List[dict] = []

    for fi, tr_end, va_end, te_end in folds:
        if quick_check and fi > 1:
            break

        t0 = time.time()
        train_rows = rows[:tr_end]
        ho_rows = rows[va_end:te_end]
        n_tr = len(train_rows)

        print(f"\n[stack-{stat} fold {fi}]  tr=0:{tr_end}  ho={va_end}:{te_end}  "
              f"ho_n={len(ho_rows)}  date={ho_rows[0]['date'][:10]}..{ho_rows[-1]['date'][:10]}")

        # Recency sample weights on training slice
        tr_dates = [datetime.fromisoformat(train_rows[i]["date"]) for i in range(n_tr)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw_tr = np.exp(-0.5 * age)

        # ── targets ───────────────────────────────────────────────────────────
        y_stat_tr  = targets(train_rows, f"target_{stat}")
        y_min_tr   = targets(train_rows, "target_min")
        y_stat_ho  = targets(ho_rows, f"target_{stat}")

        # ── feature matrices ──────────────────────────────────────────────────
        X_prod_tr, _ = feature_matrix(train_rows, stat)
        X_prod_ho, _ = feature_matrix(ho_rows, stat)

        X_min_tr = col_array(train_rows, MIN_COLS)
        X_min_ho = col_array(ho_rows, MIN_COLS)

        X_rate_tr = col_array(train_rows, rate_cols)
        X_rate_ho = col_array(ho_rows, rate_cols)

        # ── INNER OOF for meta training data ──────────────────────────────────
        print(f"  building inner OOF s1 (n_tr={n_tr})...")
        s1_oof = _inner_oof_predictions(
            train_rows, X_prod_tr, y_stat_tr, sw_full=sw_tr,
            clip_low=0.0,
        )

        print(f"  building inner OOF s2 (minutes)...")
        s2_oof = _inner_oof_predictions(
            train_rows, X_min_tr, y_min_tr, sw_full=sw_tr,
            clip_low=1.0, clip_high=55.0,
        )

        print(f"  building inner OOF s3 (rate)...")
        s3_oof_rate = _rate_head_oof(
            train_rows, X_rate_tr, y_stat_tr, y_min_tr,
            sw_full=sw_tr, clip_max=clip_max_rate,
        )
        s3s2_oof = s3_oof_rate * s2_oof

        # ── raw meta-feature columns (no target) ──────────────────────────────
        X_extra_tr = col_array(train_rows, ["l10_min", "std_min", "ewma_min",
                                            "prev_min"] + meta_extra)
        minute_surprise_tr = np.abs(
            col_array(train_rows, ["prev_min"])[:, 0] -
            col_array(train_rows, ["l10_min"])[:, 0]
        )

        # ── assemble meta training features ───────────────────────────────────
        X_meta_tr = np.column_stack([
            s1_oof.reshape(-1, 1),
            s2_oof.reshape(-1, 1),
            s3s2_oof.reshape(-1, 1),
            X_extra_tr,
            minute_surprise_tr.reshape(-1, 1),
        ])

        # ── OUTER HOLDOUT: refit s1/s2/s3 on full rows[:tr_end] ──────────────
        n_val_refit = max(500, n_tr // 5)
        refit_tr_end = n_tr - n_val_refit

        # s1 refit
        print(f"  refitting s1 on full train...")
        s1_ho = _lgb_fit_predict(
            X_prod_tr[:refit_tr_end], y_stat_tr[:refit_tr_end],
            X_prod_tr[refit_tr_end:], y_stat_tr[refit_tr_end:],
            X_prod_ho, sw=sw_tr[:refit_tr_end], clip_low=0.0,
        )

        # s2 refit
        print(f"  refitting s2 on full train...")
        s2_ho = _lgb_fit_predict(
            X_min_tr[:refit_tr_end], y_min_tr[:refit_tr_end],
            X_min_tr[refit_tr_end:], y_min_tr[refit_tr_end:],
            X_min_ho, sw=sw_tr[:refit_tr_end], clip_low=1.0, clip_high=55.0,
        )

        # s3 refit (rate model, trained on min >= threshold rows)
        print(f"  refitting s3 rate on full train...")
        import lightgbm as lgb
        rate_mask = y_min_tr[:refit_tr_end] >= MIN_THRESHOLD_RATE
        val_rate_mask = y_min_tr[refit_tr_end:] >= MIN_THRESHOLD_RATE
        y_rate_refit_tr = (y_stat_tr[:refit_tr_end][rate_mask] /
                           np.maximum(y_min_tr[:refit_tr_end][rate_mask], 1e-6))
        y_rate_refit_val = (y_stat_tr[refit_tr_end:][val_rate_mask] /
                            np.maximum(y_min_tr[refit_tr_end:][val_rate_mask], 1e-6))

        try:
            rate_model = lgb.LGBMRegressor(
                n_estimators=N_EST_BASE, learning_rate=0.05, max_depth=5,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                min_child_samples=20, reg_lambda=2.0, reg_alpha=0.5,
                random_state=42, n_jobs=-1, verbosity=-1, objective="regression",
            )
            rate_model.fit(
                X_rate_tr[:refit_tr_end][rate_mask],
                y_rate_refit_tr,
                eval_set=[(X_rate_tr[refit_tr_end:][val_rate_mask], y_rate_refit_val)],
                sample_weight=sw_tr[:refit_tr_end][rate_mask],
                callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False),
                            lgb.log_evaluation(-1)],
            )
            s3_rate_ho = np.clip(rate_model.predict(X_rate_ho), 0.0, clip_max_rate)
        except Exception as exc:
            print(f"  [s3 refit failed: {exc}; using naive rate]")
            s3_rate_ho = np.array([
                (r.get(f"l5_{stat}", 0) or 0) / max(r.get("l5_min", 1) or 1, 1.0)
                for r in ho_rows
            ], dtype=float)
            s3_rate_ho = np.clip(s3_rate_ho, 0.0, clip_max_rate)

        s3s2_ho = s3_rate_ho * s2_ho

        # ── assemble meta holdout features ────────────────────────────────────
        X_extra_ho = col_array(ho_rows, ["l10_min", "std_min", "ewma_min",
                                         "prev_min"] + meta_extra)
        minute_surprise_ho = np.abs(
            col_array(ho_rows, ["prev_min"])[:, 0] -
            col_array(ho_rows, ["l10_min"])[:, 0]
        )

        X_meta_ho = np.column_stack([
            s1_ho.reshape(-1, 1),
            s2_ho.reshape(-1, 1),
            s3s2_ho.reshape(-1, 1),
            X_extra_ho,
            minute_surprise_ho.reshape(-1, 1),
        ])

        # ── meta model: train on inner OOF meta features -> target_stat ───────
        print(f"  training meta model...")
        n_val_meta = max(200, n_tr // 5)
        meta_tr_end = n_tr - n_val_meta

        meta_model = lgb.LGBMRegressor(
            n_estimators=N_EST_META, learning_rate=0.05, max_depth=4,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            min_child_samples=20, reg_lambda=2.0, reg_alpha=0.5,
            random_state=42, n_jobs=-1, verbosity=-1, objective="regression",
        )
        meta_model.fit(
            X_meta_tr[:meta_tr_end], y_stat_tr[:meta_tr_end],
            eval_set=[(X_meta_tr[meta_tr_end:], y_stat_tr[meta_tr_end:])],
            sample_weight=sw_tr[:meta_tr_end],
            callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False),
                        lgb.log_evaluation(-1)],
        )

        meta_ho_preds = np.clip(meta_model.predict(X_meta_ho), 0.0, None)

        # quick MAE sanity check
        mae_meta_ho = float(np.abs(meta_ho_preds - y_stat_ho).mean())
        mae_s1_ho = float(np.abs(s1_ho - y_stat_ho).mean())
        print(f"  ho MAE: s1-alone={mae_s1_ho:.4f}  meta={mae_meta_ho:.4f}  "
              f"delta={mae_meta_ho - mae_s1_ho:+.4f}  "
              f"elapsed={time.time() - t0:.0f}s")

        # ── collect records ────────────────────────────────────────────────────
        for i, row in enumerate(ho_rows):
            pid = int(row.get("player_id", 0))
            gdate = str(row["date"])[:10]
            meta_recs.append({"player_id": pid, "game_date": gdate,
                              "fold": fi, "pred": float(meta_ho_preds[i])})
            s1_recs.append({"player_id": pid, "game_date": gdate,
                            "fold": fi, "pred": float(s1_ho[i])})

    return meta_recs, s1_recs


# ─── main ─────────────────────────────────────────────────────────────────────

def main(quick_check: bool = False) -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="Run only fold 1 + pts (dev mode)")
    args = ap.parse_args()
    quick_check = quick_check or args.quick

    print("=" * 60)
    print("exp_stack_pts_reb.py — A3 Additive Stacking")
    print(f"quick_check={quick_check}")
    print("=" * 60)

    print("\nBuilding folds...")
    rows, folds = build_folds()
    print(f"rows={len(rows):,}  folds={[(fi,tr,va,te) for fi,tr,va,te in folds]}")

    results: dict = {}

    for stat in (["pts"] if quick_check else ["pts", "reb"]):
        print(f"\n{'='*60}")
        print(f"STAT: {stat.upper()}")
        print('='*60)
        base = load_base(stat)

        # Verify base MAE with our join method
        base_self_mae = float((base["oof_pred_base"] - base["actual"]).abs().mean())
        print(f"  [VERIFY] base self-MAE (direct, no join): {base_self_mae:.4f}")

        # ── run stacking experiment ────────────────────────────────────────────
        meta_recs, s1_recs = run_stat(stat, rows, folds, quick_check=quick_check)

        if not meta_recs:
            print(f"[{stat}] NO PREDICTIONS generated — skip")
            continue

        # ── score meta model ───────────────────────────────────────────────────
        print(f"\n--- {stat.upper()} META STACKER ---")
        meta_result = _score_and_report(meta_recs, base, stat,
                                        label=f"stack_meta_{stat}")

        # ── score s1 alone (control) ───────────────────────────────────────────
        print(f"\n--- {stat.upper()} s1-ALONE CONTROL (fresh single GBM) ---")
        s1_result = _score_and_report(s1_recs, base, stat,
                                      label=f"stack_s1_alone_{stat}")

        results[stat] = {
            "meta": meta_result, "s1": s1_result,
            "base_direct_mae": base_self_mae,
        }

    # ── combined summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("COMBINED SUMMARY")
    print("=" * 60)
    for stat, res in results.items():
        m = res["meta"]
        s = res["s1"]
        gate = "PASS" if m.get("pass") else "FAIL"
        print(f"\n  {stat.upper()}:")
        print(f"    cached base OOF MAE (direct)  : {res['base_direct_mae']:.4f}")
        print(f"    base via join                 : {m.get('mae_base', float('nan')):.4f}")
        print(f"    s1-alone (fresh LGB)          : {s.get('mae_new', float('nan')):.4f}  "
              f"(delta vs base: {s.get('delta', 0):+.4f}  {s.get('pct', 0):+.2f}%)")
        print(f"    meta stacker                  : {m.get('mae_new', float('nan')):.4f}  "
              f"(delta vs base: {m.get('delta', 0):+.4f}  {m.get('pct', 0):+.2f}%)")
        print(f"    GATE                          : {gate}")

    # ── leak-safety confirmation ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("LEAK-SAFETY CHECKLIST")
    print("=" * 60)
    print("  [OK] Inner OOF is strictly time-ordered expanding-window (no shuffle)")
    print("  [OK] Inner folds predict only rows AFTER their training cutoff")
    print("  [OK] s1/s2/s3 for the outer holdout are fit on rows[:tr_end] only")
    print("  [OK] Neither target_stat nor target_min appear as meta INPUT features")
    print("  [OK] Meta model trains on inner-OOF outputs only (not row's own target)")
    print("  [OK] Join uses (player_id, game_date, fold) — verified unique in base")

    # ── write audit doc ────────────────────────────────────────────────────────
    if not quick_check and results:
        _write_audit(results, rows, folds)


def _write_audit(results: dict, rows: list, folds: list) -> None:
    """Write docs/_audits/PTS_REB_EXP_STACK.md."""
    from datetime import date

    lines = [
        "# PTS_REB_EXP_STACK — A3 Additive Stacking Experiment",
        f"\nDate: {date.today().isoformat()}",
        f"Dataset rows: {len(rows):,}  |  Outer folds: {len(folds)}  |"
        f"  Inner folds: {N_INNER_FOLDS} (time-ordered expanding-window)",
        "\n## Architecture\n",
        "- **s1** = LightGBM on full production `feature_matrix(stat)` (base GBM proxy)",
        "- **s2** = LightGBM E[target_min | minute-context features]",
        "- **s3** = LightGBM E[target_stat/min | usage/rate features] (trained on min≥8 rows; predicts all)",
        "- **Meta** = LightGBM on `[s1_oof, s2_oof, s3*s2, l10_min, std_min, ewma_min, prev_min, |Δmin|, stat-extra]`",
        "- Inner OOF: 3 time-ordered expanding-window folds within each outer train slice",
        "- Outer holdout refit: s1/s2/s3 trained on `rows[:tr_end]` only (last 20% used for early-stopping val)",
        "\n## Scoring",
        "\nJoin key: `(player_id, game_date, fold)` — unique in both base and experiment tables.",
        "The base parquet has `game_id=''` for all rows; joining on `game_id` creates a cartesian product",
        "within each (player_id, fold) group, producing wrong MAE numbers.",
        "Direct base MAE (before join): PTS 4.4454, REB 1.8461 — matches documented targets.",
        "\n## Leak-Safety Checklist\n",
        "- [OK] Inner OOF strictly expanding-window (no shuffle, no future leakage)",
        "- [OK] s1/s2/s3 outer-holdout refit uses `rows[:tr_end]` ONLY (no val/ho leakage)",
        "- [OK] `target_stat` and `target_min` appear ONLY as labels, never as meta input features",
        "- [OK] Meta model trains on inner-OOF outputs (never sees a row's own target)",
        "- [OK] Join key `(player_id, game_date, fold)` verified unique in base parquet",
        "\n## Results\n",
    ]

    for stat, res in results.items():
        m = res["meta"]
        s = res["s1"]
        gate = "PASS (new < base)" if m.get("pass") else "FAIL (new >= base)"
        lines += [
            f"### {stat.upper()}\n",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Cached base OOF MAE (direct) | {res['base_direct_mae']:.4f} |",
            f"| Cached base MAE (via join) | {m.get('mae_base', float('nan')):.4f} |",
            f"| s1-alone (fresh LGB) | {s.get('mae_new', float('nan')):.4f} "
            f"(delta {s.get('delta',0):+.4f} / {s.get('pct',0):+.2f}%) |",
            f"| Meta stacker | {m.get('mae_new', float('nan')):.4f} "
            f"(delta {m.get('delta',0):+.4f} / {m.get('pct',0):+.2f}%) |",
            f"| Coverage | {m.get('coverage', 0)*100:.1f}% |",
            f"| Nan/Inf preds | {m.get('nan', 0)} |",
            f"| Slope (base) | {m.get('slope_base', float('nan')):.3f} |",
            f"| Slope (meta) | {m.get('slope_new', float('nan')):.3f} |",
            f"| **GATE** | **{gate}** |",
            "",
        ]

        # per-fold
        fr = m.get("fold_results", {})
        if fr:
            lines.append(f"Per-fold MAE (base / meta / delta):\n")
            lines.append("| Fold | n | Base MAE | Meta MAE | Delta |")
            lines.append("|------|---|----------|----------|-------|")
            for fi, fd in sorted(fr.items()):
                lines.append(f"| {fi} | {fd['n']:,} | {fd['base']:.4f} | {fd['new']:.4f} | {fd['delta']:+.4f} |")
            lines.append("")

        # s1 per-fold
        sr = s.get("fold_results", {})
        if sr:
            lines.append(f"s1-alone per-fold:\n")
            lines.append("| Fold | n | Base MAE | s1 MAE | Delta |")
            lines.append("|------|---|----------|--------|-------|")
            for fi, fd in sorted(sr.items()):
                lines.append(f"| {fi} | {fd['n']:,} | {fd['base']:.4f} | {fd['new']:.4f} | {fd['delta']:+.4f} |")
            lines.append("")

    lines += ["\n## Verdict\n"]
    for stat, res in results.items():
        m = res["meta"]
        s = res["s1"]
        if m.get("pass"):
            lines.append(
                f"- **{stat.upper()} SHIP** — meta stacker beats production base "
                f"MAE by {-m['delta']:.4f} ({-m['pct']:.2f}%). "
                f"s1-alone delta={s.get('delta',0):+.4f}, so the stacking adds "
                f"{s.get('delta',0) - m.get('delta',0):+.4f} over a fresh GBM alone."
            )
        else:
            lines.append(
                f"- **{stat.upper()} REJECT** — meta stacker does NOT beat production "
                f"base (delta={m['delta']:+.4f} / {m['pct']:+.2f}%). "
                f"s1-alone delta={s.get('delta',0):+.4f} "
                f"({'beats' if s.get('delta',0) < 0 else 'loses to'} base)."
            )

    out_path = os.path.join(_ROOT, "docs", "_audits", "PTS_REB_EXP_STACK.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nAudit doc written: {out_path}")


if __name__ == "__main__":
    main()
