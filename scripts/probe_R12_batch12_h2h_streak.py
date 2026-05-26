"""probe_R12_batch12_h2h_streak.py — head-to-head L5 matchup features.

Base = 163-feat B11 opp_full (B5 + interactions + opp_pts/pace/rate L5 features)
+ B6 OOF-stack architecture.

NEW: per-(home_team, away_team) ordered-pair history (chronological — no leak):
  - h2h_l5_home_score_mean  (avg home_score in last 5 H2H games with same orientation)
  - h2h_l5_away_score_mean  (avg away_score in last 5 H2H games)
  - h2h_l5_total_mean
  - h2h_l5_spread_mean
  - h2h_last_meeting_score_diff (most recent meeting; 0 if none)
  - h2h_n_meetings_in_window     (count of prior meetings — confidence)
  - h2h_home_win_pct_l5
Also unordered-pair (any orientation):
  - h2h_any_l5_total_mean
  - h2h_any_n_meetings

Variants:
  - h2h_ordered_only  : just ordered-pair features (7)
  - h2h_with_any      : ordered + unordered features (9)

Records beat_canonical vs current per-target best.
"""
from __future__ import annotations
import importlib.util, json, os, time
from collections import defaultdict
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b5)
load_data = _b5.load_data
add_b3_features = _b5.add_b3_features
add_recency_features = _b5.add_recency_features
add_quality_features = _b5.add_quality_features

_B6_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch6_bagging_variance.py")
_spec6 = importlib.util.spec_from_file_location("probe_R12_batch6_bagging_variance", _B6_PATH)
_b6 = importlib.util.module_from_spec(_spec6)
_spec6.loader.exec_module(_b6)
_build_b5_feature_columns = _b6._build_b5_feature_columns

_B9_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch9_rest_travel_halflife2.py")
_spec9 = importlib.util.spec_from_file_location("probe_R12_batch9_rest_travel_halflife2", _B9_PATH)
_b9 = importlib.util.module_from_spec(_spec9)
_spec9.loader.exec_module(_b9)
add_interactions = _b9.add_interactions

_B11_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch11_opp_allowed_stat_specific.py")
_spec11 = importlib.util.spec_from_file_location("probe_R12_batch11_opp_allowed_stat_specific", _B11_PATH)
_b11 = importlib.util.module_from_spec(_spec11)
_spec11.loader.exec_module(_b11)
add_opp_allowed_features = _b11.add_opp_allowed_features


# Per-target canonical winners after B11
CANONICAL_BASELINE = {
    "total_pts_box":   {"pooled_delta_pct": -16.27, "src": "B9 interactions_only"},
    "score_diff":      {"pooled_delta_pct": -17.44, "src": "B11 opp_full"},
    "home_score":      {"pooled_delta_pct": -16.10, "src": "B9 all"},
    "away_score":      {"pooled_delta_pct": -14.35, "src": "B9 halflife2_only"},
    "over_230":        {"pooled_lgb_brier": 0.2383, "pooled_lgb_auc": 0.6804, "src": "B11 opp_full"},
    "home_cover_AH3":  {"pooled_lgb_brier": 0.2294, "pooled_lgb_auc": 0.7058, "src": "B11 opp_pts_pace"},
}


def add_h2h_features(merged: pd.DataFrame) -> pd.DataFrame:
    """Chronological pass — for each (h,a) ordered pair AND each unordered pair,
    build matchup history and look up prior L5 at game time."""
    merged = merged.reset_index(drop=True).copy()
    ord_hist = defaultdict(list)   # (h,a) → [{home_score, away_score, score_diff, total}]
    any_hist = defaultdict(list)   # frozenset((h,a)) → [{total}]
    n = len(merged)

    out_ord_keys = ["h2h_l5_home_score_mean", "h2h_l5_away_score_mean",
                    "h2h_l5_total_mean", "h2h_l5_spread_mean",
                    "h2h_last_meeting_score_diff", "h2h_n_meetings_in_window",
                    "h2h_home_win_pct_l5"]
    out_any_keys = ["h2h_any_l5_total_mean", "h2h_any_n_meetings"]
    arrs = {k: np.zeros(n) for k in (out_ord_keys + out_any_keys)}

    league_pts_total = 226.0
    league_score = 113.0

    for idx in range(n):
        row = merged.iloc[idx]
        h, a = str(row["home_team"]), str(row["away_team"])
        ord_key = (h, a)
        any_key = frozenset([h, a])

        # Ordered (h,a) lookup
        oh = ord_hist[ord_key]
        if oh:
            last5 = oh[-5:]
            arrs["h2h_l5_home_score_mean"][idx] = float(np.mean([g["home_score"] for g in last5]))
            arrs["h2h_l5_away_score_mean"][idx] = float(np.mean([g["away_score"] for g in last5]))
            arrs["h2h_l5_total_mean"][idx]      = float(np.mean([g["total"] for g in last5]))
            arrs["h2h_l5_spread_mean"][idx]     = float(np.mean([g["score_diff"] for g in last5]))
            arrs["h2h_last_meeting_score_diff"][idx] = float(oh[-1]["score_diff"])
            arrs["h2h_n_meetings_in_window"][idx]    = float(len(last5))
            arrs["h2h_home_win_pct_l5"][idx]    = float(np.mean([1.0 if g["score_diff"] > 0 else 0.0 for g in last5]))
        else:
            arrs["h2h_l5_home_score_mean"][idx] = league_score
            arrs["h2h_l5_away_score_mean"][idx] = league_score
            arrs["h2h_l5_total_mean"][idx]      = league_pts_total
            arrs["h2h_l5_spread_mean"][idx]     = 0.0
            arrs["h2h_last_meeting_score_diff"][idx] = 0.0
            arrs["h2h_n_meetings_in_window"][idx]    = 0.0
            arrs["h2h_home_win_pct_l5"][idx]    = 0.5

        # Unordered (any orientation)
        ah = any_hist[any_key]
        if ah:
            last5a = ah[-5:]
            arrs["h2h_any_l5_total_mean"][idx] = float(np.mean([g["total"] for g in last5a]))
            arrs["h2h_any_n_meetings"][idx]    = float(len(last5a))
        else:
            arrs["h2h_any_l5_total_mean"][idx] = league_pts_total
            arrs["h2h_any_n_meetings"][idx]    = 0.0

        # Append this game's outcome
        g = {"home_score": float(row["home_score"]),
             "away_score": float(row["away_score"]),
             "score_diff": float(row["score_diff"]),
             "total":      float(row["total_pts_box"])}
        ord_hist[ord_key].append(g)
        any_hist[any_key].append(g)

    for k, v in arrs.items():
        merged[k] = v
    return merged


def _lgb_reg():
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)


def _lgb_clf():
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)


def _xgb_reg():
    import xgboost as xgb
    return xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0)


def _xgb_clf():
    import xgboost as xgb
    return xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0, eval_metric="logloss")


def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def run_oof_stack(merged, label, naive_pred, fc, kind):
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        X_tr_base = merged[fc].iloc[tr].values
        X_te_base = merged[fc].iloc[ti].values
        y_tr = y_all[tr]
        n_tr = len(tr)
        oof = np.zeros(n_tr, dtype=float)
        inner_k = 5; inner_fs = n_tr // inner_k
        for ki in range(inner_k):
            its = ki * inner_fs
            ite = (ki + 1) * inner_fs if ki < inner_k - 1 else n_tr
            itr = list(range(0, its)) + list(range(ite, n_tr))
            iti = list(range(its, ite))
            if len(itr) < 50 or len(iti) < 5:
                continue
            if kind == "reg":
                m = _lgb_reg(); m.fit(X_tr_base[itr], y_tr[itr])
                oof[iti] = m.predict(X_tr_base[iti])
            else:
                m = _lgb_clf(); m.fit(X_tr_base[itr], y_tr[itr])
                oof[iti] = m.predict_proba(X_tr_base[iti])[:, 1]
        if kind == "reg":
            mf = _lgb_reg(); mf.fit(X_tr_base, y_tr)
            test_l1 = mf.predict(X_te_base)
        else:
            mf = _lgb_clf(); mf.fit(X_tr_base, y_tr)
            test_l1 = mf.predict_proba(X_te_base)[:, 1]
        X_tr_aug = np.hstack([X_tr_base, oof.reshape(-1, 1)])
        X_te_aug = np.hstack([X_te_base, test_l1.reshape(-1, 1)])
        if kind == "reg":
            l2_l = _lgb_reg(); l2_l.fit(X_tr_aug, y_tr)
            l2_x = _xgb_reg(); l2_x.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_l.predict(X_te_aug) + 0.5 * l2_x.predict(X_te_aug)
        else:
            l2_l = _lgb_clf(); l2_l.fit(X_tr_aug, y_tr)
            l2_x = _xgb_clf(); l2_x.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_l.predict_proba(X_te_aug)[:, 1] + \
                     0.5 * l2_x.predict_proba(X_te_aug)[:, 1]
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    return folds


def _summarize_reg(folds, name, label, n_features):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label,
                "status": "REJECT", "n_features": n_features, "beat_canonical": False}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    an = np.concatenate([f["y_naive"] for f in folds])
    pn = float(np.mean(np.abs(an - aa)))
    pl = float(np.mean(np.abs(al - aa)))
    dp = (pl - pn) / pn * 100.0
    fold_results = []
    for f in folds:
        lm = float(np.mean(np.abs(f["y_pred"] - f["y_true"])))
        nm = float(np.mean(np.abs(f["y_naive"] - f["y_true"])))
        d = lm - nm
        fold_results.append({"fold": f["fold"], "naive_mae": round(nm, 4),
                             "lgb_mae": round(lm, 4), "delta": round(d, 4),
                             "delta_pct": round(d / nm * 100, 2)})
    nv = len(folds)
    np_ = sum(1 for f in fold_results if f["delta"] < 0)
    ship = (nv >= 3) and (np_ == nv) and (dp <= -5.0)
    can = CANONICAL_BASELINE.get(label, {})
    beat = (dp < can.get("pooled_delta_pct", 0.0)) if "pooled_delta_pct" in can else None
    return {"probe": name, "kind": "regression", "label": label, "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results,
            "beat_canonical": bool(beat) if beat is not None else None,
            "canonical_src": can.get("src"),
            "vs_canonical_pp": round(dp - can.get("pooled_delta_pct", 0.0), 2) if "pooled_delta_pct" in can else None}


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_canonical": False}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    an = np.concatenate([f["y_naive"] for f in folds])
    pnb = float(brier_score_loss(aa, an))
    plb = float(brier_score_loss(aa, al))
    try:
        plu = float(roc_auc_score(aa, al))
    except Exception:
        plu = float("nan")
    bdp = (plb - pnb) / pnb * 100.0
    fold_results = []
    for f in folds:
        fold_results.append({"fold": f["fold"],
                             "naive_brier": round(float(brier_score_loss(f["y_true"], f["y_naive"])), 5),
                             "lgb_brier": round(float(brier_score_loss(f["y_true"], f["y_pred"])), 5)})
    nv_ = len(folds)
    ship = ((plb <= pnb * 0.95) or (plu >= 0.60)) and nv_ >= 3
    can = CANONICAL_BASELINE.get(label, {})
    beat = None
    if "pooled_lgb_brier" in can:
        beat = (plb < can["pooled_lgb_brier"]) or (plu > can["pooled_lgb_auc"])
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_features": n_features, "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_, "fold_results": fold_results,
            "beat_canonical": bool(beat) if beat is not None else None,
            "canonical_src": can.get("src")}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-12 — head-to-head L5 streak features", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    merged = add_interactions(merged)
    merged = add_opp_allowed_features(merged)
    merged = add_h2h_features(merged)
    fc_b5 = _build_b5_feature_columns(merged)
    INTERACT_COLS = [c for c in ["home_rest_x_travel", "away_rest_x_travel",
                                  "rest_x_travel_diff", "b2b_x_pace_diff",
                                  "rest_diff_x_elo_diff"] if c in merged.columns]
    OPP_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
                  "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3",
                  "opp_l5_pace", "opp_l5_oreb_pct_against", "opp_l5_tov_pct_against"]:
            OPP_COLS.append(f"{prefix}{k}")
    for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
              "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3",
              "opp_l5_pace", "opp_l5_oreb_pct_against", "opp_l5_tov_pct_against"]:
        OPP_COLS.append(f"{k}_diff")
    OPP_COLS = [c for c in OPP_COLS if c in merged.columns]
    fc_b11_full = fc_b5 + INTERACT_COLS + OPP_COLS

    H2H_ORD_COLS = ["h2h_l5_home_score_mean", "h2h_l5_away_score_mean",
                    "h2h_l5_total_mean", "h2h_l5_spread_mean",
                    "h2h_last_meeting_score_diff", "h2h_n_meetings_in_window",
                    "h2h_home_win_pct_l5"]
    H2H_ANY_COLS = ["h2h_any_l5_total_mean", "h2h_any_n_meetings"]

    fc_h2h_ord = fc_b11_full + H2H_ORD_COLS
    fc_h2h_full = fc_b11_full + H2H_ORD_COLS + H2H_ANY_COLS

    for cols in [fc_b11_full, fc_h2h_ord, fc_h2h_full]:
        merged[cols] = merged[cols].fillna(0.0)

    print(f"[2] base (B11 opp_full): {len(fc_b11_full)} feats", flush=True)
    print(f"    +h2h_ordered: {len(fc_h2h_ord)} feats", flush=True)
    print(f"    +h2h_full:    {len(fc_h2h_full)} feats", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    targets = [
        ("reg", "total_pts_box", None),
        ("reg", "score_diff", None),
        ("reg", "home_score", None),
        ("reg", "away_score", None),
        ("bin", "over_230", "P(total > 230)"),
        ("bin", "home_cover_AH3", "P(home covers -3)"),
    ]
    variants = [
        ("h2h_ordered_only", fc_h2h_ord),
        ("h2h_full",          fc_h2h_full),
    ]

    results = {}
    n_beat = 0; n_total = 0
    for vname, fc in variants:
        for kind, label, desc in targets:
            t_v = time.time()
            naive = naive_l5_mean(label) if kind == "reg" else naive_l5_prop(label)
            name = f"R12_B12_{vname}_{label}"
            folds = run_oof_stack(merged, label, naive, fc, kind)
            if kind == "reg":
                out = _summarize_reg(folds, name, label, len(fc) + 1)
            else:
                y_all = merged[label].astype(int).values
                out = _summarize_bin(folds, name, label, desc, len(fc) + 1,
                                      len(merged), float(np.mean(y_all)))
            out["elapsed_s"] = round(time.time() - t_v, 1)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]
            n_total += 1
            beat_str = ""
            if out.get("beat_canonical") is True:
                n_beat += 1; beat_str = " BEAT_CANONICAL"
            elif out.get("beat_canonical") is False:
                beat_str = f" (canon {out.get('canonical_src','?')} wins)"
            if out["kind"] == "regression":
                vs = out.get("vs_canonical_pp")
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"delta {out['pooled_delta_pct']:+.2f}% "
                      f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                      f"vs_canon={vs:+.2f}pp{beat_str} [{out['elapsed_s']}s]", flush=True)
            else:
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"Brier {out['pooled_lgb_brier']:.4f} "
                      f"AUC {out['pooled_lgb_auc']:.4f}{beat_str} [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS, {n_beat}/{n_total} BEAT_CANONICAL in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
