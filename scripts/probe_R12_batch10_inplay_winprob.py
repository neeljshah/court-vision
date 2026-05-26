"""probe_R12_batch10_inplay_winprob.py — in-play (mid-game) winprob update.

Base = 136-feat B5 + interactions_only (142 feats) + B6 OOF-stack architecture.

NEW: simulate snapshots at endQ1 / endQ2 / endQ3 using per-quarter linescores.
At each snapshot, augment pre-game features with:
  - cum_home_score, cum_away_score, cum_score_diff, cum_total
  - q_remaining (4 - snapshot_q)
  - cum_pace_proxy = total_pts_so_far / (snapshot_q * 12 min * 2 teams) — rough
  - score_margin_abs (|cum_score_diff|)

Targets per snapshot:
  - P(home_wins) binary
  - remaining_total_pts regression (at endQ2 only — already large enough)

Baselines (naive in-play):
  - winprob: empirical-margin-curve P(home_wins | cum_diff, q_remaining)
  - remaining_total: extrapolation from cumulative pace (cum_total * (4 - q) / q)

Records beat_b6 vs pregame B6 baseline (in-play SHOULD beat pregame at later snapshots).
"""
from __future__ import annotations
import importlib.util, json, os, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b5)
add_b3_features = _b5.add_b3_features
add_recency_features = _b5.add_recency_features
add_quality_features = _b5.add_quality_features
FEAT_COLS_BASE = _b5.FEAT_COLS_BASE

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


# B6 pregame baselines for AH3 / O230 comparison
B6_BASELINE_PREGAME = {
    "home_wins_pregame":  {"approx_brier": 0.20, "approx_auc": 0.71},  # rough pregame
    "remaining_total_pregame": {"approx_delta_pct": -15.0},
}


def load_data_with_linescores():
    """Load season-games + linescores including per-quarter splits."""
    rows = []
    for f in ["season_games_2022-23.json", "season_games_2023-24.json",
              "season_games_2024-25.json", "season_games_2025-26.json"]:
        p = os.path.join(DATA_NBA, f)
        if not os.path.exists(p): continue
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        rows.extend(d.get("rows", d) if isinstance(d, dict) else d)
    sg = pd.DataFrame(rows)
    with open(os.path.join(DATA_NBA, "linescores_all.json"), encoding="utf-8") as fh:
        ld = json.load(fh)
    ls_rows = []
    for gid, ls in ld.items():
        try:
            h1, h2, h3, h4 = (float(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5))
            a1, a2, a3, a4 = (float(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5))
        except Exception:
            continue
        h_total = h1 + h2 + h3 + h4
        a_total = a1 + a2 + a3 + a4
        if h_total <= 0 or a_total <= 0:
            continue
        ls_rows.append({
            "game_id": gid,
            "home_score": h_total, "away_score": a_total,
            "score_diff": h_total - a_total, "total_pts_box": h_total + a_total,
            "home_q1": h1, "home_q2": h2, "home_q3": h3, "home_q4": h4,
            "away_q1": a1, "away_q2": a2, "away_q3": a3, "away_q4": a4,
        })
    ls = pd.DataFrame(ls_rows)
    m = sg.merge(ls, on="game_id", how="inner")
    for c in ["home_off_rtg", "away_off_rtg", "home_pace", "away_pace"]:
        m = m[m[c] > 0]
    m = m.sort_values("game_date").reset_index(drop=True)
    return m


def add_snapshot_features(merged: pd.DataFrame, snap_q: int) -> pd.DataFrame:
    """Add cumulative features through end of quarter `snap_q` (1, 2, or 3)."""
    m = merged.copy()
    h_cum = sum(m[f"home_q{i}"] for i in range(1, snap_q + 1))
    a_cum = sum(m[f"away_q{i}"] for i in range(1, snap_q + 1))
    m["cum_home_score"] = h_cum
    m["cum_away_score"] = a_cum
    m["cum_score_diff"] = h_cum - a_cum
    m["cum_total"] = h_cum + a_cum
    m["score_margin_abs"] = (h_cum - a_cum).abs()
    m["q_remaining"] = 4 - snap_q
    minutes_played = snap_q * 12
    m["cum_pace_proxy"] = (h_cum + a_cum) / (minutes_played * 2 / 48)  # pts per 48 (2 teams)
    return m


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


def run_oof_stack(merged, label, naive_pred, fc, name, kind, desc=None):
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
                "status": "REJECT", "n_features": n_features}
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
    return {"probe": name, "kind": "regression", "label": label,
            "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results}


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label,
                "status": "REJECT", "n_features": n_features}
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
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_features": n_features, "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_, "fold_results": fold_results}


def naive_winprob_from_margin(cum_diff, q_remaining):
    """Logistic with slope tuned per quarter remaining.
    Approx: for 1 q remaining, slope ~0.30 per pt; for 3q, slope ~0.10."""
    slope = {3: 0.08, 2: 0.16, 1: 0.30}.get(int(q_remaining), 0.10)
    z = slope * cum_diff
    return 1.0 / (1.0 + np.exp(-z))


def naive_remaining_total(cum_total, snap_q):
    """Linear extrapolation: cum_total * (4 - snap_q) / snap_q."""
    return cum_total * (4 - snap_q) / snap_q


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-10 — in-play winprob update at endQ1/Q2/Q3", flush=True)
    print("=" * 70, flush=True)

    merged = load_data_with_linescores()
    print(f"[1] loaded {len(merged)} games with linescores", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    merged = add_interactions(merged)
    fc_pregame = _build_b5_feature_columns(merged)
    INTERACT_COLS = ["home_rest_x_travel", "away_rest_x_travel", "rest_x_travel_diff",
                     "b2b_x_pace_diff", "rest_diff_x_elo_diff"]
    INTERACT_COLS = [c for c in INTERACT_COLS if c in merged.columns]
    fc_pregame = fc_pregame + INTERACT_COLS
    merged[fc_pregame] = merged[fc_pregame].fillna(0.0)
    print(f"[2] pregame feature cols (B5+interactions): {len(fc_pregame)}", flush=True)

    merged["home_wins"] = (merged["score_diff"] > 0).astype(int)

    SNAPSHOTS = [1, 2, 3]
    SNAP_FEATURES = ["cum_home_score", "cum_away_score", "cum_score_diff",
                     "cum_total", "score_margin_abs", "q_remaining",
                     "cum_pace_proxy"]

    results = {}
    for snap_q in SNAPSHOTS:
        snap_merged = add_snapshot_features(merged, snap_q)
        snap_merged[SNAP_FEATURES] = snap_merged[SNAP_FEATURES].fillna(0.0)
        fc_full = fc_pregame + SNAP_FEATURES

        # Naive winprob from margin
        naive_wp = naive_winprob_from_margin(snap_merged["cum_score_diff"].values, 4 - snap_q)
        name = f"R12_B10_inplay_winprob_endQ{snap_q}"
        t_v = time.time()
        folds = run_oof_stack(snap_merged, "home_wins", naive_wp, fc_full, name, "bin")
        out = _summarize_bin(folds, name, "home_wins",
                              f"P(home_wins) at endQ{snap_q}",
                              len(fc_full) + 1, len(snap_merged),
                              float(snap_merged["home_wins"].mean()))
        out["snap_q"] = snap_q
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        print(f"  {name}: {out['status']} feats={out['n_features']} "
              f"Brier {out['pooled_lgb_brier']:.4f} "
              f"AUC {out['pooled_lgb_auc']:.4f} "
              f"({out['brier_delta_pct']:+.2f}%) [{out['elapsed_s']}s]", flush=True)

        # Regression: remaining_total_pts (target = total_pts_box - cum_total)
        if snap_q == 2:
            snap_merged["remaining_total"] = snap_merged["total_pts_box"] - snap_merged["cum_total"]
            naive_rem = naive_remaining_total(snap_merged["cum_total"].values, snap_q)
            name_r = f"R12_B10_inplay_remaining_total_endQ{snap_q}"
            t_v2 = time.time()
            folds_r = run_oof_stack(snap_merged, "remaining_total", naive_rem,
                                     fc_full, name_r, "reg")
            out_r = _summarize_reg(folds_r, name_r, "remaining_total", len(fc_full) + 1)
            out_r["snap_q"] = snap_q
            out_r["elapsed_s"] = round(time.time() - t_v2, 1)
            outp_r = os.path.join(DATA_CACHE, f"probe_{name_r}_results.json")
            with open(outp_r, "w") as f:
                json.dump(out_r, f, indent=2)
            results[name_r] = out_r["status"]
            print(f"  {name_r}: {out_r['status']} feats={out_r['n_features']} "
                  f"delta {out_r['pooled_delta_pct']:+.2f}% "
                  f"({out_r['n_folds_positive']}/{out_r['n_valid_folds']}) "
                  f"[{out_r['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
