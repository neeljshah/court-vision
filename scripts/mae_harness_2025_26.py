"""mae_harness_2025_26.py — iter-15 CV-lift validation on temporally-aligned frame.

Bypasses the 2024-playoffs closing-line gap by using 2025-26 gamelog actuals
as the OOS target. Both the CV training corpus AND the OOS validation actuals
live in the dense 2025-26 window, so the leak-safe shift(1).expanding().mean()
CV priors actually have signal at prediction time.

Pipeline:
  1) Build prop_pergame dataset once.
  2) Filter pre-cutoff (training+val) and post-cutoff (OOS) rows.
  3) Build leak-safe CV priors (shift(1).expanding().mean() by nba_player_id).
  4) Train baseline q50 (85 features) AND augmented q50 (85 + 8 cvb_prior_*)
     on pre-cutoff rows with same HPs and sample-weight as production.
  5) Predict every OOS row with both models; compute per-row absolute error vs
     actual gamelog target. Aggregate MAE per stat.
  6) Stratify BLK by with/without CV prior to localize where lift lives.

Writes models to data/models/oos_pre_2026_01/ and a JSON summary alongside.
Does not touch production. Does not call NBA API. Does not push to git.
"""
from __future__ import annotations

import argparse, json, os, sys, time, warnings
from collections import defaultdict
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params
from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

CUTOFF_DATE = "2026-01-01"
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
CV_PATH = os.path.join(PROJECT_DIR, "data", "player_cv_per_game.parquet")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_2026_01")

CV_FEATURES = [
    "cvb_avg_defender_dist",
    "cvb_avg_spacing",
    "cvb_off_ball_dist",
    "cvb_avg_velocity",
    "cvb_fatigue_score",
    "cvb_paint_time_pct",
    "cvb_near_basket_pct",
    "cvb_avg_dist_to_basket",
]


def load_gid_to_date():
    gid2date = {}
    for season in ("2021-22", "2022-23", "2023-24", "2024-25", "2025-26"):
        p = os.path.join(GAMELOG_DIR, f"season_games_{season}.json")
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        for r in d.get("rows", []):
            gid2date[str(r["game_id"])] = r["game_date"]
    return gid2date


def build_cv_priors(gid2date):
    cv = pd.read_parquet(CV_PATH)
    cv["date"] = cv["game_id"].astype(str).map(gid2date)
    cv = cv.dropna(subset=["date", "nba_player_id"]).copy()
    cv["nba_player_id"] = cv["nba_player_id"].astype(int)
    cv = cv.sort_values(["nba_player_id", "date"]).reset_index(drop=True)
    print(f"  CV rows after dating: {len(cv)} | unique players: {cv['nba_player_id'].nunique()}")
    print(f"  CV date range: {cv['date'].min()} -> {cv['date'].max()}")
    grouped = cv.groupby("nba_player_id", sort=False)
    prior_frames = []
    for pid, sub in grouped:
        sub = sub.sort_values("date").reset_index(drop=True)
        priors = {}
        for c in CV_FEATURES:
            priors[f"cvb_prior_{c[4:]}"] = sub[c].shift(1).expanding().mean().values
        out = pd.DataFrame(priors)
        out["nba_player_id"] = pid
        out["date"] = sub["date"].values
        prior_frames.append(out)
    priors_df = pd.concat(prior_frames, ignore_index=True)
    return priors_df


def build_player_prior_index(priors_df):
    """Build {pid: [(date, priors_dict), ...]} sorted by date for binary search."""
    cv_cols = [c for c in priors_df.columns if c.startswith("cvb_prior_")]
    by_player = defaultdict(list)
    for _, r in priors_df.iterrows():
        by_player[int(r["nba_player_id"])].append((r["date"], {c: r[c] for c in cv_cols}))
    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])
    return by_player, cv_cols


def lookup_prior(by_player, pid, target_date):
    """Most-recent prior row strictly before target_date. None if no usable prior."""
    if pid not in by_player:
        return None
    lst = by_player[pid]
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid][0] < target_date:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    return lst[lo - 1][1]


def attach_cv(rows, by_player, cv_cols, medians=None):
    """Attach cvb_prior_* to each row. medians used to impute NaNs (if provided)."""
    n_with = 0
    out = []
    for r in rows:
        pid = int(r.get("player_id") or 0)
        date = r.get("date")
        priors = lookup_prior(by_player, pid, date) if pid and date else None
        if priors is not None and any(pd.notna(v) for v in priors.values()):
            n_with += 1
        rcopy = dict(r)
        if priors is None:
            for c in cv_cols:
                rcopy[c] = np.nan
            rcopy["_has_cv_prior"] = False
        else:
            for c in cv_cols:
                v = priors[c]
                rcopy[c] = float(v) if pd.notna(v) else np.nan
            rcopy["_has_cv_prior"] = True
        out.append(rcopy)
    if medians is not None:
        for r in out:
            for c in cv_cols:
                v = r.get(c)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    r[c] = medians[c]
    return out, n_with


def compute_medians(rows, cv_cols):
    mat = np.array([[r.get(c) for c in cv_cols] for r in rows], dtype=float)
    medians = {}
    for j, c in enumerate(cv_cols):
        col = mat[:, j]
        valid = col[~np.isnan(col)]
        medians[c] = float(np.median(valid)) if len(valid) else 0.0
    return medians


def train_xgb(X_tr, X_val, yt_tr, yt_val, sw, params):
    import xgboost as xgb
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric="mae",
    )
    t0 = time.time()
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    return m, time.time() - t0, int(getattr(m, "best_iteration", -1) or -1)


def predict(model, rows, cols, stat):
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows], dtype=float)
    pred_t = model.predict(X)
    return np.maximum(_inverse(stat, pred_t), 0.0)


def run_stat(stat, pre_rows, oos_rows, by_player, cv_cols, cols_base):
    print(f"\n  ===== {stat.upper()} =====")
    cols_aug = cols_base + cv_cols

    # Filter rows to those that have a target for this stat
    tgt = f"target_{stat}"
    pre_s = [r for r in pre_rows if tgt in r and r.get(tgt) is not None]
    oos_s = [r for r in oos_rows if tgt in r and r.get(tgt) is not None]
    print(f"  pre-cutoff rows: {len(pre_s)} | OOS rows: {len(oos_s)}")

    # Median impute on pre-cutoff first; reuse those medians for OOS
    medians = compute_medians(pre_s, cv_cols)
    pre_imp, n_with_train = attach_cv(pre_s, by_player, cv_cols, medians=medians)
    oos_imp, n_with_oos = attach_cv(oos_s, by_player, cv_cols, medians=medians)
    print(f"  Train rows w/ CV prior: {n_with_train}/{len(pre_s)} ({n_with_train/max(1,len(pre_s))*100:.2f}%)")
    print(f"  OOS rows w/ CV prior:   {n_with_oos}/{len(oos_s)} ({n_with_oos/max(1,len(oos_s))*100:.2f}%)")

    # Train/val split on pre-cutoff (chronological, 85/15)
    pre_imp.sort(key=lambda r: r["date"])
    n_pre = len(pre_imp)
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    train_dates = [datetime.fromisoformat(pre_imp[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates) if train_dates else datetime.now()
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    y = np.array([float(r[tgt]) for r in pre_imp], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr); yt_val = _transform(stat, y_val)
    params = _per_stat_xgb_params(stat)

    # Baseline (85 feats)
    X_base = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols_base] for r in pre_imp], dtype=float)
    Xb_tr, Xb_val = X_base[:train_end], X_base[train_end:]
    base_m, t_base, bi_base = train_xgb(Xb_tr, Xb_val, yt_tr, yt_val, sw, params)
    print(f"  baseline  fit {t_base:.1f}s best_iter={bi_base}")

    # Augmented (85+8 feats)
    X_aug = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols_aug] for r in pre_imp], dtype=float)
    Xa_tr, Xa_val = X_aug[:train_end], X_aug[train_end:]
    aug_m, t_aug, bi_aug = train_xgb(Xa_tr, Xa_val, yt_tr, yt_val, sw, params)
    print(f"  augmented fit {t_aug:.1f}s best_iter={bi_aug}")

    # Save both
    os.makedirs(OUT_DIR, exist_ok=True)
    base_path = os.path.join(OUT_DIR, f"quantile_pergame_{stat}_q50_baseline.json")
    aug_path  = os.path.join(OUT_DIR, f"quantile_pergame_{stat}_q50_augmented.json")
    base_m.save_model(base_path)
    aug_m.save_model(aug_path)

    # OOS predict
    y_oos = np.array([float(r[tgt]) for r in oos_imp], dtype=float)
    pred_base = predict(base_m, oos_imp, cols_base, stat)
    pred_aug  = predict(aug_m,  oos_imp, cols_aug,  stat)

    base_mae = float(mean_absolute_error(y_oos, pred_base))
    aug_mae  = float(mean_absolute_error(y_oos, pred_aug))
    delta = base_mae - aug_mae
    rel_pct = (delta / base_mae * 100.0) if base_mae > 0 else 0.0

    # Verdict thresholds: 0.005 absolute or 1% relative — whichever larger for BLK
    if delta >= max(0.005, 0.01 * base_mae):
        verdict = "VALIDATED"
    elif delta <= -max(0.005, 0.01 * base_mae):
        verdict = "REGRESSED"
    else:
        verdict = "WASH"

    print(f"  OOS baseline MAE:  {base_mae:.4f}")
    print(f"  OOS augmented MAE: {aug_mae:.4f}")
    print(f"  delta (base-aug):  {delta:+.4f}  ({rel_pct:+.2f}% rel)  -> {verdict}")

    # Subset stratification (always do — useful diagnostic)
    has_cv_mask = np.array([r["_has_cv_prior"] for r in oos_imp])
    sub_with = {"n": int(has_cv_mask.sum())}
    sub_without = {"n": int((~has_cv_mask).sum())}
    if sub_with["n"] > 0:
        sub_with["base_mae"] = float(mean_absolute_error(y_oos[has_cv_mask], pred_base[has_cv_mask]))
        sub_with["aug_mae"]  = float(mean_absolute_error(y_oos[has_cv_mask], pred_aug[has_cv_mask]))
        sub_with["delta"]    = sub_with["base_mae"] - sub_with["aug_mae"]
    if sub_without["n"] > 0:
        sub_without["base_mae"] = float(mean_absolute_error(y_oos[~has_cv_mask], pred_base[~has_cv_mask]))
        sub_without["aug_mae"]  = float(mean_absolute_error(y_oos[~has_cv_mask], pred_aug[~has_cv_mask]))
        sub_without["delta"]    = sub_without["base_mae"] - sub_without["aug_mae"]
    print(f"  WITH-CV    subset: n={sub_with['n']:>5} | base_MAE={sub_with.get('base_mae',float('nan')):.4f} | aug_MAE={sub_with.get('aug_mae',float('nan')):.4f} | delta={sub_with.get('delta',float('nan')):+.4f}")
    print(f"  WITHOUT-CV subset: n={sub_without['n']:>5} | base_MAE={sub_without.get('base_mae',float('nan')):.4f} | aug_MAE={sub_without.get('aug_mae',float('nan')):.4f} | delta={sub_without.get('delta',float('nan')):+.4f}")

    return {
        "stat": stat,
        "n_pre": len(pre_s),
        "n_oos": len(oos_s),
        "train_cv_cov_pct": n_with_train / max(1, len(pre_s)) * 100.0,
        "oos_cv_cov_pct":   n_with_oos   / max(1, len(oos_s))   * 100.0,
        "base_mae": base_mae,
        "aug_mae":  aug_mae,
        "delta":    delta,
        "rel_pct":  rel_pct,
        "verdict":  verdict,
        "sub_with":    sub_with,
        "sub_without": sub_without,
        "base_iter": bi_base,
        "aug_iter":  bi_aug,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default="blk,fg3m,stl")
    ap.add_argument("--cutoff", default=CUTOFF_DATE)
    args = ap.parse_args()
    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]
    print(f"  iter-15 MAE harness — stats={stats} cutoff={args.cutoff}")

    t0 = time.time()
    gid2date = load_gid_to_date()
    print(f"  gid2date: {len(gid2date)} games")
    priors_df = build_cv_priors(gid2date)
    print(f"  CV priors: {len(priors_df)} (player,date) rows")
    by_player, cv_cols = build_player_prior_index(priors_df)
    print(f"  cv_cols: {len(cv_cols)}")

    print("  Building pergame dataset (one-time)...")
    rows, fcols = build_pergame_dataset(None)
    print(f"  Total rows: {len(rows)} | feature cols: {len(fcols)}")

    cutoff = args.cutoff
    pre_rows = [r for r in rows if r["date"] < cutoff]
    oos_rows = [r for r in rows if r["date"] >= cutoff]
    print(f"  pre-cutoff: {len(pre_rows)} | OOS (>= {cutoff}): {len(oos_rows)}")

    cols_base = feature_columns()

    results = []
    for stat in stats:
        try:
            res = run_stat(stat, pre_rows, oos_rows, by_player, cv_cols, cols_base)
            results.append(res)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  [error] {stat}: {e}")

    print("\n  ====== SUMMARY ======")
    print("  | Stat | n_oos | CV cov % | base MAE | aug MAE | dMAE | rel% | verdict |")
    print("  |---|---:|---:|---:|---:|---:|---:|---|")
    for r in results:
        print(f"  | {r['stat'].upper()} | {r['n_oos']} | {r['oos_cv_cov_pct']:.1f}% "
              f"| {r['base_mae']:.4f} | {r['aug_mae']:.4f} | {r['delta']:+.4f} "
              f"| {r['rel_pct']:+.2f}% | {r['verdict']} |")

    out = {
        "generated_at": datetime.now().isoformat(),
        "cutoff": args.cutoff,
        "n_pre_total": len(pre_rows),
        "n_oos_total": len(oos_rows),
        "elapsed_s": time.time() - t0,
        "results": results,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "iter15_mae_harness_summary.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\n  Summary -> {out_path}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
