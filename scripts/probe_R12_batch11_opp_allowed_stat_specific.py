"""probe_R12_batch11_opp_allowed_stat_specific.py — count-based opp-allowed L5.

Base = 142-feat pregame (B5 + interactions_only from B9 winner) + B6 OOF-stack.

NEW: per-team L5 "allowed" features computed chronologically (no leakage):
  - opp_allowed_PTS_l5         (avg pts scored AGAINST team in last 5 games)
  - opp_allowed_PTS_home_l5    (last 5 HOME games for that team)
  - opp_allowed_PTS_away_l5    (last 5 ROAD games for that team)
  - opp_allowed_PTS_l3         (last 3 games — sharper recency)
  - opp_l5_pace                (avg pace in opp's last 5 games)
  - opp_l5_oreb_pct_against    (mean rate from opponent's L10 oreb_pct as proxy)
  - opp_l5_tov_pct_against     (mean rate from opponent's L10 tov_pct as proxy)

These complement the rate-based opp_def_rtg + L10 splits with count-based context.

Variants:
  - opp_pts_only        : just opp_allowed_PTS_* (8 features)
  - opp_pts_plus_pace   : above + opp_l5_pace (10 features)
  - opp_full            : all features above + oreb + tov (14 features)

Records beat_b9 vs B9 best-per-target baselines.
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


# B9 best-per-target baselines (production canonical winners)
B9_BASELINE = {
    "total_pts_box":   {"pooled_delta_pct": -16.27},  # interactions_only
    "score_diff":      {"pooled_delta_pct": -17.23},  # both_halflives
    "home_score":      {"pooled_delta_pct": -16.10},  # all
    "away_score":      {"pooled_delta_pct": -14.35},  # halflife2_only
    "over_230":        {"pooled_lgb_brier": 0.2383, "pooled_lgb_auc": 0.6737},  # B6 still wins
    "home_cover_AH3":  {"pooled_lgb_brier": 0.2302, "pooled_lgb_auc": 0.7065},  # both_halflives
}


def add_opp_allowed_features(merged: pd.DataFrame) -> pd.DataFrame:
    """Chronological pass — for each team, build allowed-PTS history and look up
    prior L5 averages at game time. No leakage (uses only prior games)."""
    merged = merged.reset_index(drop=True).copy()
    th = defaultdict(list)  # team_id → list of dicts {date, pts_against, is_home, pace}
    n = len(merged)

    out_keys = ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
                "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3",
                "opp_l5_pace", "opp_l5_oreb_pct_against",
                "opp_l5_tov_pct_against"]
    home_arrs = {k: np.zeros(n) for k in out_keys}
    away_arrs = {k: np.zeros(n) for k in out_keys}

    # League means for cold-start
    league_pts_mean = 113.0
    league_pace_mean = 100.0
    league_oreb_mean = 0.25
    league_tov_mean = 0.13

    def _agg(hist):
        if not hist:
            return None
        last5 = hist[-5:]
        last3 = hist[-3:]
        home5 = [h for h in hist[-15:] if h["is_home"]][-5:]
        away5 = [h for h in hist[-15:] if not h["is_home"]][-5:]
        return {
            "opp_allowed_PTS_l5": np.mean([h["pts_against"] for h in last5]),
            "opp_allowed_PTS_home_l5": np.mean([h["pts_against"] for h in home5]) if home5 else league_pts_mean,
            "opp_allowed_PTS_away_l5": np.mean([h["pts_against"] for h in away5]) if away5 else league_pts_mean,
            "opp_allowed_PTS_l3": np.mean([h["pts_against"] for h in last3]),
            "opp_l5_pace": np.mean([h["pace"] for h in last5 if h.get("pace") is not None]) if any(h.get("pace") is not None for h in last5) else league_pace_mean,
            "opp_l5_oreb_pct_against": np.mean([h["oreb_pct"] for h in last5 if h.get("oreb_pct") is not None]) if any(h.get("oreb_pct") is not None for h in last5) else league_oreb_mean,
            "opp_l5_tov_pct_against": np.mean([h["tov_pct"] for h in last5 if h.get("tov_pct") is not None]) if any(h.get("tov_pct") is not None for h in last5) else league_tov_mean,
        }

    for idx in range(n):
        row = merged.iloc[idx]
        h, a = str(row["home_team"]), str(row["away_team"])
        # OPPONENT's allowed stats are what matters for THIS team's expected production.
        # For home team's prediction: use AWAY team's allowed stats (what they let opponents score).
        # For away team's prediction: use HOME team's allowed stats.
        a_hist = th[a]; h_hist = th[h]
        af = _agg(a_hist)  # away team's allowed history → for home team's prediction
        hf = _agg(h_hist)  # home team's allowed history → for away team's prediction
        if af:
            for k, v in af.items(): home_arrs[k][idx] = v
        if hf:
            for k, v in hf.items(): away_arrs[k][idx] = v
        # Update history with THIS game's outcome for both teams
        th[h].append({
            "date": row["game_date"],
            "pts_against": float(row["away_score"]),
            "is_home": True,
            "pace": float(row.get("home_pace", league_pace_mean)) if row.get("home_pace") else None,
            "oreb_pct": float(row.get("away_oreb_pct_L10", league_oreb_mean)) if row.get("away_oreb_pct_L10") else None,
            "tov_pct": float(row.get("away_tov_pct_L10", league_tov_mean)) if row.get("away_tov_pct_L10") else None,
        })
        th[a].append({
            "date": row["game_date"],
            "pts_against": float(row["home_score"]),
            "is_home": False,
            "pace": float(row.get("away_pace", league_pace_mean)) if row.get("away_pace") else None,
            "oreb_pct": float(row.get("home_oreb_pct_L10", league_oreb_mean)) if row.get("home_oreb_pct_L10") else None,
            "tov_pct": float(row.get("home_tov_pct_L10", league_tov_mean)) if row.get("home_tov_pct_L10") else None,
        })

    for k in out_keys:
        merged[f"home_{k}"] = home_arrs[k]
        merged[f"away_{k}"] = away_arrs[k]
        merged[f"{k}_diff"] = home_arrs[k] - away_arrs[k]
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
        return {"probe": name, "kind": "regression", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_b9": False}
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
    b9 = B9_BASELINE.get(label, {})
    beat = (dp < b9.get("pooled_delta_pct", 0.0)) if "pooled_delta_pct" in b9 else None
    return {"probe": name, "kind": "regression", "label": label,
            "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results,
            "beat_b9": bool(beat) if beat is not None else None,
            "b9_baseline_delta_pct": b9.get("pooled_delta_pct"),
            "vs_b9_pp": round(dp - b9.get("pooled_delta_pct", 0.0), 2) if "pooled_delta_pct" in b9 else None}


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_b9": False}
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
    b9 = B9_BASELINE.get(label, {})
    beat = None
    if "pooled_lgb_brier" in b9:
        beat = (plb < b9["pooled_lgb_brier"]) or (plu > b9["pooled_lgb_auc"])
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_features": n_features, "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_, "fold_results": fold_results,
            "beat_b9": bool(beat) if beat is not None else None,
            "b9_baseline_brier": b9.get("pooled_lgb_brier"),
            "b9_baseline_auc": b9.get("pooled_lgb_auc")}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-11 — count-based opp-allowed L5 features", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    merged = add_interactions(merged)
    merged = add_opp_allowed_features(merged)
    fc_b5 = _build_b5_feature_columns(merged)
    INTERACT_COLS = [c for c in ["home_rest_x_travel", "away_rest_x_travel",
                                  "rest_x_travel_diff", "b2b_x_pace_diff",
                                  "rest_diff_x_elo_diff"] if c in merged.columns]
    fc_pregame = fc_b5 + INTERACT_COLS
    OPP_PTS_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
                  "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3"]:
            OPP_PTS_COLS.append(f"{prefix}{k}")
    for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
              "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3"]:
        OPP_PTS_COLS.append(f"{k}_diff")
    OPP_PACE_COLS = ["home_opp_l5_pace", "away_opp_l5_pace", "opp_l5_pace_diff"]
    OPP_RATE_COLS = ["home_opp_l5_oreb_pct_against", "away_opp_l5_oreb_pct_against",
                     "opp_l5_oreb_pct_against_diff", "home_opp_l5_tov_pct_against",
                     "away_opp_l5_tov_pct_against", "opp_l5_tov_pct_against_diff"]
    OPP_PTS_COLS = [c for c in OPP_PTS_COLS if c in merged.columns]
    OPP_PACE_COLS = [c for c in OPP_PACE_COLS if c in merged.columns]
    OPP_RATE_COLS = [c for c in OPP_RATE_COLS if c in merged.columns]

    fc_pts_only = fc_pregame + OPP_PTS_COLS
    fc_pts_pace = fc_pregame + OPP_PTS_COLS + OPP_PACE_COLS
    fc_full = fc_pregame + OPP_PTS_COLS + OPP_PACE_COLS + OPP_RATE_COLS

    for cols in [fc_pts_only, fc_pts_pace, fc_full]:
        merged[cols] = merged[cols].fillna(0.0)

    print(f"[2] base pregame (B5+interactions): {len(fc_pregame)}", flush=True)
    print(f"    opp_pts cols: {len(OPP_PTS_COLS)}", flush=True)
    print(f"    opp_pace cols: {len(OPP_PACE_COLS)}", flush=True)
    print(f"    opp_rate cols: {len(OPP_RATE_COLS)}", flush=True)

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
        ("opp_pts_only", fc_pts_only),
        ("opp_pts_pace", fc_pts_pace),
        ("opp_full", fc_full),
    ]

    results = {}
    n_beat_b9 = 0
    n_total = 0
    for vname, fc in variants:
        for kind, label, desc in targets:
            t_v = time.time()
            naive = naive_l5_mean(label) if kind == "reg" else naive_l5_prop(label)
            name = f"R12_B11_{vname}_{label}"
            folds = run_oof_stack(merged, label, naive, fc, name, kind, desc)
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
            if out.get("beat_b9") is True:
                n_beat_b9 += 1
                beat_str = " BEAT_B9"
            elif out.get("beat_b9") is False:
                beat_str = " (B9 wins)"
            if out["kind"] == "regression":
                vs = out.get("vs_b9_pp")
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"delta {out['pooled_delta_pct']:+.2f}% "
                      f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                      f"vs_B9={vs:+.2f}pp{beat_str} [{out['elapsed_s']}s]", flush=True)
            else:
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"Brier {out['pooled_lgb_brier']:.4f} "
                      f"AUC {out['pooled_lgb_auc']:.4f} "
                      f"({out['brier_delta_pct']:+.2f}%){beat_str} [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS, {n_beat_b9}/{n_total} BEAT_B9 in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
