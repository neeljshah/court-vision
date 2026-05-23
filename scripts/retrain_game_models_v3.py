"""
retrain_game_models_v3.py — Retrain all 5 game-level LightGBM models with v3 features.

Extends v2 (L10 features) with the same 6 new modules as win_prob_v3:
  referee crew, news, schedule pressure, team form, coach features, ELO v2.

Walk-forward:
  Train   : 2022-23 + first 70% of 2023-24
  Val     : last 30% of 2023-24
  Holdout : full 2024-25

Usage:
    conda run -n basketball_ai python scripts/retrain_game_models_v3.py

Produces:
    data/models/game_total_v3_lgb.txt
    data/models/game_spread_v3_lgb.txt
    data/models/game_blowout_v3_lgb.txt
    data/models/game_first_half_v3_lgb.txt
    data/models/game_pace_v3_lgb.txt
    data/models/game_models_v3_metrics.json
"""

from __future__ import annotations

import json
import os
import sys
import time
import pickle

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_METRICS_PATH = os.path.join(_MODEL_DIR, "game_models_v3_metrics.json")
_SEASONS      = ["2022-23", "2023-24", "2024-25"]
_HOLDOUT      = "2024-25"
_BLOWOUT_MARGIN = 15

# v2 baselines from retrain_game_models.py
_V2_BASELINES = {
    "game_total": {"mae": 14.08, "r2": 0.173},
    "spread":     {"mae": 11.23, "r2": 0.239},
    "blowout":    {"acc": 0.6201, "brier": 0.2395},
    "first_half": {"mae": 6.66, "r2": 0.182},
    "pace":       {"mae": "LEAKAGE", "r2": 1.0, "note": "v2 had leakage"},
}


def _attach_v3_features(df, seasons):
    """
    Compute v3 feature overlay for training — cache-only, no live API calls.

    Uses pre-built ELO game lookup, cached schedule files for schedule_pressure
    and team_form, and pre-loaded coach_history.json.  Ref and news features
    default to zeros for historical training rows.
    """
    import numpy as np
    import pandas as pd
    from src.features.v3_game_features import (
        _REF_DEFAULTS, _NEWS_DEFAULTS, _COACH_DEFAULTS,
        _sched_defaults, _form_defaults,
    )

    print(f"  Building v3 features for {len(df)} rows ...")

    # Pre-build ELO lookup
    elo_lkp: dict = {}
    try:
        from src.features.elo import compute_game_elo_lookup_v2
        elo_lkp = compute_game_elo_lookup_v2(seasons)
        print(f"    ELO v2 lookup: {len(elo_lkp)} games")
    except Exception as e:
        print(f"    [warn] ELO: {e}")

    # Team ID lookup
    abbrev_to_id: dict = {}
    try:
        from nba_api.stats.static import teams as nba_static
        abbrev_to_id = {t["abbreviation"]: t["id"] for t in nba_static.get_teams()}
    except Exception:
        pass

    v3_rows = []
    n = len(df)
    for i, (_, row) in enumerate(df.iterrows()):
        home   = str(row.get("home_team", ""))
        away   = str(row.get("away_team", ""))
        gdate  = str(row.get("game_date", ""))
        season = str(row.get("season", seasons[-1]))
        gid    = str(row.get("game_id", ""))

        feats: dict = {}
        feats.update(_REF_DEFAULTS)
        feats.update(_NEWS_DEFAULTS)

        # Schedule pressure (cache-based)
        htid = int(abbrev_to_id.get(home, 0))
        atid = int(abbrev_to_id.get(away, 0))
        for prefix, tid, team in [("home", htid, home), ("away", atid, away)]:
            try:
                if tid and gdate:
                    from src.features.schedule_pressure import get_team_schedule_features
                    raw = get_team_schedule_features(tid, gdate, season)
                    skip = {"team_id", "game_date"}
                    for k, v in raw.items():
                        if k not in skip:
                            feats[f"{prefix}_{k}"] = v
                else:
                    feats.update(_sched_defaults(prefix))
            except Exception:
                feats.update(_sched_defaults(prefix))

        # Team form (cache-based)
        window = 10
        skip_form = {"team_form_games", "team_abbrev"}
        for prefix, team in [("home", home), ("away", away)]:
            try:
                from src.features.team_form import get_team_form_features
                raw = get_team_form_features(team, gdate, season, window)
                for k, v in raw.items():
                    if k in skip_form:
                        continue
                    feats[f"{prefix}_{k.replace('team_', '', 1)}"] = v
            except Exception:
                feats.update(_form_defaults(prefix, window))

        # Coach
        try:
            from src.features.coach_features import get_coach_features
            cf = get_coach_features(home, away, season, gdate)
            feats.update({k: v for k, v in cf.items() if not isinstance(v, str)})
        except Exception:
            feats.update(_COACH_DEFAULTS)

        # ELO v2
        elo_entry = elo_lkp.get(str(gid), {})
        h_elo = float(elo_entry.get("home_elo", 1500.0))
        a_elo = float(elo_entry.get("away_elo", 1500.0))
        feats["v3_home_elo_v2"] = round(h_elo, 2)
        feats["v3_away_elo_v2"] = round(a_elo, 2)
        feats["v3_elo_diff_v2"] = round(h_elo - a_elo, 2)

        v3_rows.append(feats)
        if (i + 1) % 500 == 0:
            print(f"    {i+1}/{n} rows done ...")

    v3_df = pd.DataFrame(v3_rows, index=df.index).fillna(0.0)
    print(f"  v3 overlay: {len(v3_df.columns)} new cols")
    return v3_df


def _eval_reg(model, X_ho, df_ho, col):
    from sklearn.metrics import mean_absolute_error, r2_score
    import numpy as np
    if X_ho is None or len(df_ho) == 0 or col not in df_ho.columns:
        return None, None
    y_ho  = df_ho[col].values.astype(np.float32)
    preds = model.predict(X_ho)
    return round(float(mean_absolute_error(y_ho, preds)), 2), round(float(r2_score(y_ho, preds)), 3)


def _eval_clf(model, X_ho, df_ho):
    from sklearn.metrics import accuracy_score, brier_score_loss
    import numpy as np
    if X_ho is None or len(df_ho) == 0:
        return None, None
    y_ho  = (np.abs(df_ho["spread"].values) > _BLOWOUT_MARGIN).astype(int)
    probs = model.predict_proba(X_ho)[:, 1]
    return (round(float(accuracy_score(y_ho, (probs >= 0.5).astype(int))), 4),
            round(float(brier_score_loss(y_ho, probs)), 4))


def main():
    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, brier_score_loss

    start_t = time.time()

    print("=" * 60)
    print("Game Models v3 — LightGBM + v3 features + Walk-Forward")
    print("=" * 60)

    # ── Load scored games dataset ─────────────────────────────────────────────
    from src.prediction.game_models import _fetch_scored_games, FEATURE_COLS as V2_FEATURE_COLS
    rows = []
    for s in _SEASONS:
        s_rows = _fetch_scored_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} scored games")

    if len(rows) < 200:
        raise RuntimeError(f"Insufficient data: {len(rows)} rows")

    df = pd.DataFrame(rows).dropna(subset=V2_FEATURE_COLS + ["game_total", "spread"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    # ── Attach v3 features ────────────────────────────────────────────────────
    v3_df = _attach_v3_features(df, _SEASONS)
    v3_new_cols = [c for c in v3_df.columns if c not in df.columns]
    for col in v3_new_cols:
        df[col] = v3_df[col].values
    for col in v3_new_cols:
        if col not in df.columns:
            df[col] = 0.0

    all_feature_cols = list(V2_FEATURE_COLS) + v3_new_cols
    for col in all_feature_cols:
        if col not in df.columns:
            df[col] = 0.0

    # ── Walk-forward split ────────────────────────────────────────────────────
    df_tv = df[df["season"] != _HOLDOUT].reset_index(drop=True)
    df_ho = df[df["season"] == _HOLDOUT].reset_index(drop=True)
    tv_split = int(len(df_tv) * 0.70)
    df_tr = df_tv.iloc[:tv_split].reset_index(drop=True)
    df_vl = df_tv.iloc[tv_split:].reset_index(drop=True)
    print(f"\nTrain:{len(df_tr)}  Val:{len(df_vl)}  Holdout:{len(df_ho)}")

    X_tr  = df_tr[all_feature_cols].values.astype(np.float32)
    X_val = df_vl[all_feature_cols].values.astype(np.float32)
    X_ho  = df_ho[all_feature_cols].values.astype(np.float32) if len(df_ho) > 0 else None

    _lgb_base = dict(
        n_estimators=400, learning_rate=0.05, num_leaves=63,
        min_child_samples=20, reg_lambda=1.0, subsample=0.8,
        colsample_bytree=0.8, random_state=42, n_jobs=-1, verbose=-1,
    )
    _cb = [lgb.early_stopping(30, verbose=False), lgb.log_evaluation(100)]
    os.makedirs(_MODEL_DIR, exist_ok=True)
    results: dict = {}

    # ── 1. game_total ─────────────────────────────────────────────────────────
    y_tr_tot  = df_tr["game_total"].values.astype(np.float32)
    y_val_tot = df_vl["game_total"].values.astype(np.float32)
    reg_tot = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_tot.fit(X_tr, y_tr_tot, eval_set=[(X_val, y_val_tot)], callbacks=_cb)
    vp = reg_tot.predict(X_val)
    vmae = mean_absolute_error(y_val_tot, vp);  vr2 = r2_score(y_val_tot, vp)
    h_mae, h_r2 = _eval_reg(reg_tot, X_ho, df_ho, "game_total")
    reg_tot.booster_.save_model(os.path.join(_MODEL_DIR, "game_total_v3_lgb.txt"))
    results["game_total"] = {"mae": round(vmae, 2), "r2": round(vr2, 3),
                             "holdout_mae": h_mae, "holdout_r2": h_r2}
    print(f"  game_total  val MAE={vmae:.1f} R²={vr2:.3f} | hold MAE={h_mae} R²={h_r2}")

    # ── 2. spread ─────────────────────────────────────────────────────────────
    y_tr_sp  = df_tr["spread"].values.astype(np.float32)
    y_val_sp = df_vl["spread"].values.astype(np.float32)
    reg_sp = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_sp.fit(X_tr, y_tr_sp, eval_set=[(X_val, y_val_sp)], callbacks=_cb)
    vp_sp = reg_sp.predict(X_val)
    vmae_sp = mean_absolute_error(y_val_sp, vp_sp); vr2_sp = r2_score(y_val_sp, vp_sp)
    h_mae_sp, h_r2_sp = _eval_reg(reg_sp, X_ho, df_ho, "spread")
    reg_sp.booster_.save_model(os.path.join(_MODEL_DIR, "game_spread_v3_lgb.txt"))
    results["spread"] = {"mae": round(vmae_sp, 2), "r2": round(vr2_sp, 3),
                         "holdout_mae": h_mae_sp, "holdout_r2": h_r2_sp}
    print(f"  spread      val MAE={vmae_sp:.1f} R²={vr2_sp:.3f} | hold MAE={h_mae_sp} R²={h_r2_sp}")

    # ── 3. blowout ────────────────────────────────────────────────────────────
    y_tr_bl  = (np.abs(df_tr["spread"].values) > _BLOWOUT_MARGIN).astype(int)
    y_val_bl = (np.abs(df_vl["spread"].values) > _BLOWOUT_MARGIN).astype(int)
    bl_rate  = y_tr_bl.mean()
    clf_bo = lgb.LGBMClassifier(
        objective="binary",
        scale_pos_weight=(1 - bl_rate) / max(bl_rate, 1e-6),
        **_lgb_base,
    )
    clf_bo.fit(X_tr, y_tr_bl, eval_set=[(X_val, y_val_bl)], callbacks=_cb)
    probs_val_bo = clf_bo.predict_proba(X_val)[:, 1]
    acc_bo  = accuracy_score(y_val_bl, (probs_val_bo >= 0.5).astype(int))
    bri_bo  = brier_score_loss(y_val_bl, probs_val_bo)
    h_acc_bo, h_bri_bo = _eval_clf(clf_bo, X_ho, df_ho)
    clf_bo.booster_.save_model(os.path.join(_MODEL_DIR, "game_blowout_v3_lgb.txt"))
    results["blowout"] = {"acc": round(acc_bo, 4), "brier": round(bri_bo, 4),
                          "holdout_acc": h_acc_bo, "holdout_brier": h_bri_bo}
    print(f"  blowout     val acc={acc_bo:.3f} Brier={bri_bo:.4f} | hold acc={h_acc_bo} Brier={h_bri_bo}")

    # ── 4. first_half (proxy 0.47× — v3 standalone is in parallel branch) ────
    fh_col = "first_half_actual" if "first_half_actual" in df_tr.columns else "first_half_proxy"
    y_tr_fh  = df_tr[fh_col].values.astype(np.float32)
    y_val_fh = df_vl[fh_col].values.astype(np.float32)
    reg_fh = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_fh.fit(X_tr, y_tr_fh, eval_set=[(X_val, y_val_fh)], callbacks=_cb)
    vp_fh = reg_fh.predict(X_val)
    vmae_fh = mean_absolute_error(y_val_fh, vp_fh); vr2_fh = r2_score(y_val_fh, vp_fh)
    h_mae_fh, h_r2_fh = _eval_reg(reg_fh, X_ho, df_ho, fh_col)
    reg_fh.booster_.save_model(os.path.join(_MODEL_DIR, "game_first_half_v3_lgb.txt"))
    results["first_half"] = {"mae": round(vmae_fh, 2), "r2": round(vr2_fh, 3),
                             "holdout_mae": h_mae_fh, "holdout_r2": h_r2_fh,
                             "label": fh_col}
    print(f"  first_half  val MAE={vmae_fh:.1f} R²={vr2_fh:.3f} | hold MAE={h_mae_fh} R²={h_r2_fh}")

    # ── 5. pace (exclude pace_avg / pace_expectation) ─────────────────────────
    _PACE_EXCLUDE = {"pace_avg", "pace_expectation"}
    pace_cols = [c for c in all_feature_cols if c not in _PACE_EXCLUDE]
    X_tr_pc  = df_tr[pace_cols].values.astype(np.float32)
    X_val_pc = df_vl[pace_cols].values.astype(np.float32)
    X_ho_pc  = df_ho[pace_cols].values.astype(np.float32) if X_ho is not None else None
    y_tr_pc  = df_tr["game_pace"].values.astype(np.float32)
    y_val_pc = df_vl["game_pace"].values.astype(np.float32)
    reg_pc = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_pc.fit(X_tr_pc, y_tr_pc, eval_set=[(X_val_pc, y_val_pc)], callbacks=_cb)
    vp_pc = reg_pc.predict(X_val_pc)
    vmae_pc = mean_absolute_error(y_val_pc, vp_pc); vr2_pc = r2_score(y_val_pc, vp_pc)
    h_mae_pc = h_r2_pc = None
    if X_ho_pc is not None and len(df_ho) > 0:
        y_ho_pc  = df_ho["game_pace"].values.astype(np.float32)
        p_ho_pc  = reg_pc.predict(X_ho_pc)
        h_mae_pc = round(float(mean_absolute_error(y_ho_pc, p_ho_pc)), 3)
        h_r2_pc  = round(float(r2_score(y_ho_pc, p_ho_pc)), 3)
    reg_pc.booster_.save_model(os.path.join(_MODEL_DIR, "game_pace_v3_lgb.txt"))
    with open(os.path.join(_MODEL_DIR, "game_pace_v3_lgb_meta.pkl"), "wb") as f:
        pickle.dump({"pace_feature_cols": pace_cols}, f)
    results["pace"] = {"mae": round(vmae_pc, 3), "r2": round(vr2_pc, 3),
                       "holdout_mae": h_mae_pc, "holdout_r2": h_r2_pc}
    print(f"  pace        val MAE={vmae_pc:.2f} R²={vr2_pc:.3f} | hold MAE={h_mae_pc} R²={h_r2_pc}")

    # ── Feature importance (combined) ─────────────────────────────────────────
    fi_tot  = dict(zip(all_feature_cols, reg_tot.feature_importances_.tolist()))
    fi_sp   = dict(zip(all_feature_cols, reg_sp.feature_importances_.tolist()))
    combined_fi = {k: fi_tot.get(k, 0) + fi_sp.get(k, 0) for k in all_feature_cols}
    top25 = sorted(combined_fi.items(), key=lambda x: x[1], reverse=True)[:25]
    print("\nTop 25 features (total+spread combined importance):")
    for feat, imp in top25:
        print(f"  {feat:<50s}  {imp:.0f}")

    # ── Save metrics ──────────────────────────────────────────────────────────
    results["version"]        = "v3_integration"
    results["n_features"]     = len(all_feature_cols)
    results["baseline_v2"]    = _V2_BASELINES
    results["top25_features"] = dict(top25)
    results["wall_time_sec"]  = round(time.time() - start_t, 1)
    with open(_METRICS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nMetrics -> {_METRICS_PATH}")

    # ── Before / After table ──────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("BEFORE / AFTER COMPARISON")
    print("=" * 65)
    print(f"{'Model':<14} {'Metric':<8} {'v2 Before':>10} {'v3 Val':>10} {'v3 Hold':>10}")
    print("-" * 60)
    for model, res in results.items():
        if model in ("version", "n_features", "baseline_v2", "top25_features", "wall_time_sec"):
            continue
        base = _V2_BASELINES.get(model, {})
        if model == "blowout":
            print(f"{'blowout':<14} {'acc':<8} {str(base.get('acc','?')):>10} "
                  f"{str(res.get('acc','?')):>10} {str(res.get('holdout_acc','N/A')):>10}")
            print(f"{'':14} {'brier':<8} {str(base.get('brier','?')):>10} "
                  f"{str(res.get('brier','?')):>10} {str(res.get('holdout_brier','N/A')):>10}")
        elif model == "pace":
            print(f"{'pace':<14} {'MAE':<8} {str(base.get('mae','?')):>10} "
                  f"{str(res.get('mae','?')):>10} {str(res.get('holdout_mae','N/A')):>10}")
        else:
            print(f"{model:<14} {'MAE':<8} {str(base.get('mae','?')):>10} "
                  f"{str(res.get('mae','?')):>10} {str(res.get('holdout_mae','N/A')):>10}")
            print(f"{'':14} {'R²':<8} {str(base.get('r2','?')):>10} "
                  f"{str(res.get('r2','?')):>10} {str(res.get('holdout_r2','N/A')):>10}")

    print(f"\nWall-clock: {round(time.time()-start_t,0):.0f}s")


if __name__ == "__main__":
    main()
