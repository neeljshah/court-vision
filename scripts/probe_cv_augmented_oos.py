"""probe_cv_augmented_oos.py — iter-14 CV moat test.

Headline test: does broadcast CV add real prop-prediction signal?

For each VALIDATED stat (BLK, FG3M, STL):
  1) Load OOS baseline model from data/models/oos_pre_playoffs/.
  2) Build leak-safe (nba_player_id, target_date) CV prior aggregates
     from data/player_cv_per_game.parquet using shift(1).expanding().mean().
  3) Retrain "augmented" model with 85 baseline features + cvb_prior_* features.
     Same hyperparams. Write to data/models/oos_cv_augmented/.
  4) Backtest both baseline and augmented vs playoffs_2024_canonical.csv.
  5) Compare hit rate, ROI, edge distribution, per-row prediction delta.

No production files touched. Read-only against gamelog cache.
"""
from __future__ import annotations

import argparse, csv, json, os, sys, time, warnings
from collections import defaultdict
from datetime import datetime
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params
from src.prediction.prop_pergame import build_pergame_dataset, feature_columns
from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row, _resolve_player_id, _season_for_date,
    _classify_result, _recommend, _odds_to_decimal_profit,
)

CUTOFF_DATE = "2024-04-21"
BASE_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
AUG_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models", "oos_cv_augmented")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2024_canonical.csv")
CV_PATH = os.path.join(PROJECT_DIR, "data", "player_cv_per_game.parquet")
THRESHOLD = 0.5

# Dense cvb_* signals (filter to >= 50% non-null below). We start with the
# 8 mentioned in the iter-14 spec.
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
    """Build {game_id: date} from local season_games_*.json files."""
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
    """Return DataFrame keyed by (nba_player_id, target_date) with cvb_prior_* cols.

    Leak-safe: for each (player, target_date), aggregates mean of cvb_* across
    all CV games STRICTLY BEFORE target_date. Implementation: explode every CV
    row into (pid, future_target_date) buckets, then for each unique
    (player, date) compute prior mean. Simpler: for OOS prediction we just need
    one prior per (player, target_date), so we sort by date and use cumulative
    means up to (but not including) the target row.

    Output schema: nba_player_id (int), date (str ISO), cvb_prior_<feat>.
    The 'date' here is the EFFECTIVE date a join would use — i.e. for any
    target_date strictly AFTER one of these dates, that row's priors are valid.

    Strategy: for join-time, callers will pick the most-recent prior row
    per (player, target_date) — we expose a helper for that.
    """
    cv = pd.read_parquet(CV_PATH)
    cv["date"] = cv["game_id"].astype(str).map(gid2date)
    # drop CV rows we couldn't date (none currently expected)
    cv = cv.dropna(subset=["date", "nba_player_id"]).copy()
    cv["nba_player_id"] = cv["nba_player_id"].astype(int)
    cv = cv.sort_values(["nba_player_id", "date"]).reset_index(drop=True)
    # Coverage report on raw signals.
    print("  CV raw non-null %% (of 1231 rows):")
    for c in CV_FEATURES:
        nn = cv[c].notna().sum()
        print(f"    {c}: {nn} ({nn/len(cv)*100:.1f}%)")
    # Prior cumulative-mean per player using shift(1).expanding().mean().
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


def lookup_prior(priors_df, pid, target_date):
    """Return dict of cvb_prior_* values: most recent (player, date < target) row.

    If no row exists, returns all-NaN dict (caller imputes).
    """
    sub = priors_df[(priors_df["nba_player_id"] == pid) & (priors_df["date"] < target_date)]
    cols = [c for c in priors_df.columns if c.startswith("cvb_prior_")]
    if len(sub) == 0:
        return {c: np.nan for c in cols}
    last = sub.iloc[-1]
    return {c: last[c] for c in cols}


def attach_cv_priors_to_rows(rows, priors_df, pid_lookup_by_name):
    """For each row, attach cvb_prior_* via (nba_player_id, date).

    rows have keys: 'player_id' (nba_api id), 'date'.
    Returns: list of dicts (mutated copies) + n_with_priors count.
    """
    cv_cols = [c for c in priors_df.columns if c.startswith("cvb_prior_")]
    pri_idx = {(int(r["nba_player_id"]), r["date"]): {c: r[c] for c in cv_cols} for _, r in priors_df.iterrows()}
    # Group priors by player for quick "latest prior" lookup
    by_player = defaultdict(list)
    for _, r in priors_df.iterrows():
        by_player[int(r["nba_player_id"])].append((r["date"], {c: r[c] for c in cv_cols}))
    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])

    n_with = 0
    out_rows = []
    for r in rows:
        pid = int(r.get("player_id") or 0)
        date = r.get("date")
        if pid in by_player and date is not None:
            # binary search for last entry strictly before date
            lst = by_player[pid]
            lo, hi = 0, len(lst)
            while lo < hi:
                mid = (lo + hi) // 2
                if lst[mid][0] < date:
                    lo = mid + 1
                else:
                    hi = mid
            if lo > 0:
                priors = lst[lo - 1][1]
                # all None means we still have no usable prior
                valid = any(v is not None and not (isinstance(v, float) and np.isnan(v)) for v in priors.values())
                if valid:
                    n_with += 1
                rcopy = dict(r)
                for c, v in priors.items():
                    rcopy[c] = v
                out_rows.append(rcopy)
                continue
        rcopy = dict(r)
        for c in cv_cols:
            rcopy[c] = np.nan
        out_rows.append(rcopy)
    return out_rows, n_with, cv_cols


def median_impute(rows, cols):
    """Impute NaN cvb_prior_* cols with the column median over rows. Returns medians dict."""
    mat = np.array([[r.get(c) for c in cols] for r in rows], dtype=float)
    medians = {}
    for j, c in enumerate(cols):
        col = mat[:, j]
        valid = col[~np.isnan(col)]
        med = float(np.median(valid)) if len(valid) else 0.0
        medians[c] = med
        for i, r in enumerate(rows):
            v = r.get(c)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                r[c] = med
    return medians


def train_xgb(stat, X_tr, X_val, yt_tr, yt_val, sw, params):
    import xgboost as xgb
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric="mae",
    )
    t0 = time.time()
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    return m, time.time() - t0, int(getattr(m, "best_iteration", -1) or -1)


def load_baseline_model(stat):
    import xgboost as xgb
    path = os.path.join(BASE_MODEL_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        raise SystemExit(f"baseline missing: {path}")
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def backtest(stat, predict_fn, label, csv_rows, name2pid):
    """Run backtest. predict_fn(feat_row, date) -> float pred."""
    row_cache = {}
    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    per_bet = []
    for r in csv_rows:
        try:
            line = float(r["closing_line"]); actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1; continue
        pid = name2pid.get(r["player"])
        if pid is None: skip["no_pid"] += 1; continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(pid, r["opp"], d, season, is_home=is_home, rest_days=2.0, gamelog_dir=GAMELOG_DIR)
        feat = row_cache[key]
        if feat is None: skip["no_history"] += 1; continue
        try:
            pred = predict_fn(feat, r["date"], pid)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1; continue
        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)
        n_pred += 1
        bet_info = {
            "player": r["player"], "date": r["date"], "line": line, "actual": actual,
            "pred": pred, "edge": edge, "rec": rec, "result": actual_result,
        }
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
                bet_info["outcome"] = "PUSH"
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1; bet_info["outcome"] = "WIN"
                else:
                    losses += 1; bet_info["outcome"] = "LOSS"
            per_bet.append(bet_info)
    profit = _odds_to_decimal_profit(-110)
    roi_u = wins * profit - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_u / n_bets * 100.0) if n_bets else 0.0
    return {
        "label": label, "stat": stat,
        "n_pred": n_pred, "n_bets": n_bets, "wins": wins, "losses": losses, "pushes": pushes,
        "hit_rate": hit, "roi_pct": roi_pct, "roi_units": roi_u,
        "per_bet": per_bet, "skip": dict(skip),
    }


def run_stat(stat, priors_df, gid2date):
    print(f"\n  ===== {stat.upper()} =====")
    method = "xgb"  # BLK, FG3M, STL all xgb
    cols_base = feature_columns()
    cv_cols = [c for c in priors_df.columns if c.startswith("cvb_prior_")]
    print(f"  baseline features: {len(cols_base)} | cv features: {len(cv_cols)}")

    # 1) Build training dataset.
    print("  Building pergame dataset...")
    t0 = time.time()
    rows, _fcols = build_pergame_dataset(None)
    print(f"  Total rows: {len(rows)} ({time.time()-t0:.1f}s)")
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    n_pre = len(pre_rows)
    print(f"  Pre-cutoff: {n_pre}")

    # 2) Attach CV priors and impute.
    pre_rows, n_with, cv_cols = attach_cv_priors_to_rows(pre_rows, priors_df, None)
    print(f"  Train rows w/ CV prior: {n_with} ({n_with/n_pre*100:.2f}%)")
    medians = median_impute(pre_rows, cv_cols)

    # 3) Train baseline (re-load existing) + augmented.
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    cols_aug = cols_base + cv_cols
    X_all = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols_aug] for r in pre_rows], dtype=float)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    n_train, n_val = len(X_tr), len(X_val)
    print(f"  Train/Val: {n_train}/{n_val}")
    train_dates = [datetime.fromisoformat(pre_rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)
    y = np.array([r[f"target_{stat}"] for r in pre_rows], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr); yt_val = _transform(stat, y_val)
    params = _per_stat_xgb_params(stat)
    aug_model, fit_secs, best_iter = train_xgb(stat, X_tr, X_val, yt_tr, yt_val, sw, params)
    print(f"  Aug fit {fit_secs:.1f}s best_iter={best_iter}")

    # val metrics
    from sklearn.metrics import mean_absolute_error
    pred_val_t = aug_model.predict(X_val)
    pred_val_raw = _inverse(stat, pred_val_t)
    val_mae = float(mean_absolute_error(y_val, pred_val_raw))
    print(f"  Aug val_MAE: {val_mae:.4f}")

    os.makedirs(AUG_MODEL_DIR, exist_ok=True)
    aug_path = os.path.join(AUG_MODEL_DIR, f"quantile_pergame_{stat}_q50.json")
    aug_model.save_model(aug_path)
    print(f"  saved -> {aug_path}")

    # 4) Backtest both.
    base_model = load_baseline_model(stat)
    all_rows_csv = []
    with open(CSV_PATH, encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == stat:
                all_rows_csv.append(r)
    print(f"  CSV rows for {stat}: {len(all_rows_csv)}")
    name2pid = {nm: _resolve_player_id(nm) for nm in sorted({r["player"] for r in all_rows_csv})}

    # OOS prior coverage
    n_oos_with_cv = 0
    for r in all_rows_csv:
        pid = name2pid.get(r["player"])
        if pid is None: continue
        sub = priors_df[(priors_df["nba_player_id"] == pid) & (priors_df["date"] < r["date"])]
        if len(sub) > 0:
            row = sub.iloc[-1]
            if any(pd.notna(row[c]) for c in cv_cols):
                n_oos_with_cv += 1
    print(f"  OOS rows w/ CV prior: {n_oos_with_cv}/{len(all_rows_csv)} ({n_oos_with_cv/len(all_rows_csv)*100:.2f}%)")

    def predict_baseline(feat, date, pid):
        X = np.array([[float(feat.get(c, 0.0) or 0.0) for c in cols_base]], dtype=float)
        pred_t = float(base_model.predict(X)[0])
        return max(0.0, float(_inverse(stat, np.array([pred_t]))[0]))

    def predict_augmented(feat, date, pid):
        # build CV priors at prediction time (leak-safe: date is target_date)
        sub = priors_df[(priors_df["nba_player_id"] == pid) & (priors_df["date"] < date)]
        if len(sub) > 0:
            row = sub.iloc[-1]
            cv_feats = {c: (float(row[c]) if pd.notna(row[c]) else medians[c]) for c in cv_cols}
        else:
            cv_feats = {c: medians[c] for c in cv_cols}
        feat_full = dict(feat); feat_full.update(cv_feats)
        X = np.array([[float(feat_full.get(c, 0.0) or 0.0) for c in cols_aug]], dtype=float)
        pred_t = float(aug_model.predict(X)[0])
        return max(0.0, float(_inverse(stat, np.array([pred_t]))[0]))

    base_res = backtest(stat, predict_baseline, "baseline", all_rows_csv, name2pid)
    aug_res = backtest(stat, predict_augmented, "augmented", all_rows_csv, name2pid)

    # Per-row prediction delta on the subset with CV priors
    pred_deltas_cv = []
    pred_deltas_nocv = []
    for r in all_rows_csv:
        pid = name2pid.get(r["player"])
        if pid is None: continue
        d = datetime.fromisoformat(r["date"])
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        feat = _build_asof_row(pid, r["opp"], d, season, is_home=is_home, rest_days=2.0, gamelog_dir=GAMELOG_DIR)
        if feat is None: continue
        try:
            pb = predict_baseline(feat, r["date"], pid)
            pa = predict_augmented(feat, r["date"], pid)
        except Exception:
            continue
        sub = priors_df[(priors_df["nba_player_id"] == pid) & (priors_df["date"] < r["date"])]
        has_cv = (len(sub) > 0) and any(pd.notna(sub.iloc[-1][c]) for c in cv_cols)
        if has_cv:
            pred_deltas_cv.append(pa - pb)
        else:
            pred_deltas_nocv.append(pa - pb)
    import statistics as stx
    if pred_deltas_cv:
        print(f"  pred delta (CV-covered) n={len(pred_deltas_cv)} mean={stx.fmean(pred_deltas_cv):+.4f} stdev={stx.pstdev(pred_deltas_cv):.4f} maxabs={max(abs(x) for x in pred_deltas_cv):.4f}")
    if pred_deltas_nocv:
        print(f"  pred delta (no-CV)      n={len(pred_deltas_nocv)} mean={stx.fmean(pred_deltas_nocv):+.4f} stdev={stx.pstdev(pred_deltas_nocv):.4f} maxabs={max(abs(x) for x in pred_deltas_nocv):.4f}")

    # 5) Compare side-by-side at row level
    base_by_key = {(b["player"], b["date"]): b for b in base_res["per_bet"]}
    aug_by_key = {(b["player"], b["date"]): b for b in aug_res["per_bet"]}
    flips = 0; agree = 0; new_aug = 0; dropped_aug = 0
    for k, b in base_by_key.items():
        a = aug_by_key.get(k)
        if a is None: dropped_aug += 1; continue
        if a["rec"] == b["rec"]: agree += 1
        else: flips += 1
    for k, a in aug_by_key.items():
        if k not in base_by_key: new_aug += 1

    print(f"\n  {stat.upper()} BACKTEST:")
    print(f"    baseline:  n_pred={base_res['n_pred']} n_bets={base_res['n_bets']} hit={base_res['hit_rate']*100:.2f}% ROI={base_res['roi_pct']:+.2f}%")
    print(f"    augmented: n_pred={aug_res['n_pred']} n_bets={aug_res['n_bets']} hit={aug_res['hit_rate']*100:.2f}% ROI={aug_res['roi_pct']:+.2f}%")
    print(f"    agree={agree} flips={flips} dropped={dropped_aug} new_aug={new_aug}")

    return {
        "stat": stat,
        "n_train_with_cv": n_with,
        "n_train_total": n_pre,
        "n_oos_with_cv": n_oos_with_cv,
        "n_oos_total": len(all_rows_csv),
        "baseline": {"n_bets": base_res["n_bets"], "hit": base_res["hit_rate"], "roi_pct": base_res["roi_pct"]},
        "augmented": {"n_bets": aug_res["n_bets"], "hit": aug_res["hit_rate"], "roi_pct": aug_res["roi_pct"]},
        "delta_hit_pp": (aug_res["hit_rate"] - base_res["hit_rate"]) * 100.0,
        "delta_roi_pp": aug_res["roi_pct"] - base_res["roi_pct"],
        "agree": agree, "flips": flips, "new_aug": new_aug, "dropped_aug": dropped_aug,
        "base_bets": base_res["per_bet"], "aug_bets": aug_res["per_bet"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default="blk,fg3m,stl", help="comma-separated stat list")
    args = ap.parse_args()
    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]

    print(f"  iter-14 CV moat probe — stats: {stats}")
    gid2date = load_gid_to_date()
    print(f"  game_id->date map: {len(gid2date)} games from local season_games_*.json")
    priors = build_cv_priors(gid2date)
    print(f"  CV priors built: {len(priors)} (player,date) rows")

    results = []
    for stat in stats:
        try:
            res = run_stat(stat, priors, gid2date)
            results.append(res)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  [error] {stat}: {e}")
            continue

    print("\n  ====== SUMMARY ======")
    print("  | Stat | baseline n | base hit% | aug n | aug hit% | d_hit | d_ROI |")
    print("  |---|---:|---:|---:|---:|---:|---:|")
    for r in results:
        print(f"  | {r['stat'].upper()} | {r['baseline']['n_bets']} | {r['baseline']['hit']*100:.2f}% | "
              f"{r['augmented']['n_bets']} | {r['augmented']['hit']*100:.2f}% | "
              f"{r['delta_hit_pp']:+.2f}pp | {r['delta_roi_pp']:+.2f}pp |")
    print()
    for r in results:
        print(f"  {r['stat'].upper()}: train_cv_cov={r['n_train_with_cv']}/{r['n_train_total']} "
              f"({r['n_train_with_cv']/r['n_train_total']*100:.2f}%), "
              f"oos_cv_cov={r['n_oos_with_cv']}/{r['n_oos_total']} "
              f"({r['n_oos_with_cv']/r['n_oos_total']*100:.2f}%), "
              f"agree={r['agree']} flips={r['flips']} new={r['new_aug']} dropped={r['dropped_aug']}")
    # Verdict
    print("\n  ====== VERDICT ======")
    for r in results:
        dh = r["delta_hit_pp"]
        if abs(dh) < 0.5: v = "WASH"
        elif dh > 1.0:    v = "VALIDATED CV LIFT"
        elif dh > 0:      v = "PARTIAL"
        elif dh < -0.5:   v = "REGRESSED"
        else:             v = "WASH"
        print(f"  {r['stat'].upper()}: {v}  (d_hit={dh:+.2f}pp on aug={r['augmented']['n_bets']} bets)")

    # Save JSON
    out = {"generated_at": datetime.now().isoformat(), "results": [
        {k: v for k, v in r.items() if k not in ("base_bets", "aug_bets")} for r in results
    ]}
    out_path = os.path.join(PROJECT_DIR, "data", "models", "oos_cv_augmented", "iter14_probe_summary.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"  Summary -> {out_path}")

    # BLK detail dump
    blk = next((r for r in results if r["stat"] == "blk"), None)
    if blk is not None:
        detail_path = os.path.join(PROJECT_DIR, "data", "models", "oos_cv_augmented", "iter14_blk_detail.json")
        base_idx = {(b["player"], b["date"]): b for b in blk["base_bets"]}
        aug_idx = {(b["player"], b["date"]): b for b in blk["aug_bets"]}
        keys = sorted(set(base_idx) | set(aug_idx))
        detail = []
        for k in keys:
            b = base_idx.get(k); a = aug_idx.get(k)
            detail.append({
                "player": k[0], "date": k[1],
                "base_pred": b["pred"] if b else None, "base_edge": b["edge"] if b else None,
                "base_rec": b["rec"] if b else None, "base_outcome": b.get("outcome") if b else None,
                "aug_pred": a["pred"] if a else None, "aug_edge": a["edge"] if a else None,
                "aug_rec": a["rec"] if a else None, "aug_outcome": a.get("outcome") if a else None,
                "line": (b or a)["line"], "actual": (b or a)["actual"],
                "flipped": (b is not None and a is not None and b["rec"] != a["rec"]),
            })
        with open(detail_path, "w", encoding="utf-8") as fh:
            json.dump(detail, fh, indent=2, default=str)
        print(f"  BLK detail -> {detail_path}")


if __name__ == "__main__":
    main()
