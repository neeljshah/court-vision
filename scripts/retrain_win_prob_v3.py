"""
retrain_win_prob_v3.py — Train win probability model v3 with all new feature modules.

Extends v2 (ELO + injury) with:
  - referee crew features (7 keys)
  - news/injury features (9 keys)
  - schedule pressure (24 keys)
  - team form (14 keys)
  - coach features (22 keys)
  - ELO v2 (re-surfaced consistently, 3 keys)

Walk-forward: train 2022-23 + 2023-24 first 80%, holdout last 20% (2024-25 heavy).
Classifier: LightGBM binary + isotonic calibration.

Usage:
    conda run -n basketball_ai python scripts/retrain_win_prob_v3.py

Produces:
    data/models/win_prob_v3.pkl
    data/models/win_prob_v3_metrics.json
"""

from __future__ import annotations

import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_METRICS_V2_PATH = os.path.join(PROJECT_DIR, "data", "models", "win_prob_metrics.json")
_MODEL_V3_PATH   = os.path.join(PROJECT_DIR, "data", "models", "win_prob_v3.pkl")
_METRICS_V3_PATH = os.path.join(PROJECT_DIR, "data", "models", "win_prob_v3_metrics.json")
_SEASONS = ["2022-23", "2023-24", "2024-25"]
_BASELINE_ACC   = 0.6985
_BASELINE_BRIER = 0.2025


def _load_v3_overlay(df, seasons):
    """
    Attach v3 new features — TRAINING MODE (fully offline, no live NBA API).

    Strategy:
      - ELO: pre-built game lookup from season_games cache (fast, pure JSON)
      - Schedule pressure: reads per-team schedule JSON caches directly
      - Team form: reads per-team schedule JSON caches directly
      - Coach: reads coach_history.json (pre-built) or hard-coded tenure map
      - News/Ref: zeros (no live feed for historical games — safe defaults)

    Zero live NBA API calls per row.
    """
    import numpy as np
    import pandas as pd
    from src.features.v3_game_features import (
        _REF_DEFAULTS, _NEWS_DEFAULTS, _COACH_DEFAULTS,
        _sched_defaults, _form_defaults,
    )

    print("  Building v3 overlay (training mode - fully offline) ...")

    # ── 1. ELO game lookup — pure JSON, no API ────────────────────────────────
    elo_lkp: dict = {}
    try:
        from src.features.elo import compute_game_elo_lookup_v2
        elo_lkp = compute_game_elo_lookup_v2(seasons)
        print(f"    ELO v2: {len(elo_lkp)} game entries")
    except Exception as e:
        print(f"    [warn] ELO: {e}")

    # ── 2. Team abbrev → NBA ID (static list, no API) ─────────────────────────
    abbrev_to_id: dict = {}
    try:
        from nba_api.stats.static import teams as nba_static
        abbrev_to_id = {t["abbreviation"]: t["id"] for t in nba_static.get_teams()}
    except Exception:
        pass  # if nba_api static fails, schedule_pressure will use defaults

    # ── 3. Per-row assembly ───────────────────────────────────────────────────
    v3_rows = []
    n = len(df)
    skip_sched = frozenset({"team_id", "game_date"})
    skip_form  = frozenset({"team_form_games", "team_abbrev"})

    for i, (_, row) in enumerate(df.iterrows()):
        home   = str(row.get("home_team", ""))
        away   = str(row.get("away_team", ""))
        gdate  = str(row.get("game_date", ""))
        season = str(row.get("season", seasons[-1]))
        gid    = str(row.get("game_id", ""))

        feats: dict = {}

        # Ref + News: training-time zeros (historical games have no live feed)
        feats.update(_REF_DEFAULTS)
        feats.update(_NEWS_DEFAULTS)

        # Schedule pressure — reads cached JSON, no live call
        htid = int(abbrev_to_id.get(home, 0))
        atid = int(abbrev_to_id.get(away, 0))
        for prefix, tid in [("home", htid), ("away", atid)]:
            try:
                if tid and gdate:
                    from src.features.schedule_pressure import (
                        _load_schedule as _load_sched,
                        get_team_schedule_features,
                    )
                    raw = get_team_schedule_features(tid, gdate, season)
                    for k, v in raw.items():
                        if k not in skip_sched:
                            feats[f"{prefix}_{k}"] = v
                else:
                    feats.update(_sched_defaults(prefix))
            except Exception:
                feats.update(_sched_defaults(prefix))

        # Team form — reads cached JSON, no live call
        window = 10
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

        # Coach — reads coach_history.json or hard-coded tenure (no API)
        try:
            from src.features.coach_features import get_coach_features
            cf = get_coach_features(home, away, season, gdate)
            feats.update({k: v for k, v in cf.items() if not isinstance(v, str)})
        except Exception:
            feats.update(_COACH_DEFAULTS)

        # ELO v2 — pre-built lookup
        elo_entry = elo_lkp.get(gid, {})
        h_elo = float(elo_entry.get("home_elo", 1500.0))
        a_elo = float(elo_entry.get("away_elo", 1500.0))
        feats["v3_home_elo_v2"] = round(h_elo, 2)
        feats["v3_away_elo_v2"] = round(a_elo, 2)
        feats["v3_elo_diff_v2"] = round(h_elo - a_elo, 2)

        v3_rows.append(feats)
        if (i + 1) % 500 == 0:
            print(f"    {i+1}/{n} rows processed ...")

    v3_df = pd.DataFrame(v3_rows, index=df.index).fillna(0.0)
    print(f"  v3 overlay done: {len(v3_df.columns)} new columns")
    return v3_df


def main():
    import pickle
    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import accuracy_score, brier_score_loss

    start_t = time.time()

    print("=" * 60)
    print("Win Probability Model Retrain - v3 (+ Ref/News/Schedule/Form/Coach)")
    print(f"Baseline v2: acc={_BASELINE_ACC:.4f}  brier={_BASELINE_BRIER:.4f}")
    print("=" * 60)
    print()

    # ── Load v2 training data ────────────────────────────────────────────────
    print(f"Building base dataset from {_SEASONS} ...")
    from src.prediction.win_probability import (
        _fetch_season_games,
        _MODEL_FEATURE_COLS as V2_FEATURE_COLS,
    )
    rows = []
    for s in _SEASONS:
        s_rows = _fetch_season_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games")

    if not rows:
        raise RuntimeError("No data — check NBA API connectivity")

    df = pd.DataFrame(rows).dropna(subset=["home_win"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    # ── v2 overlay: ELO + injury ─────────────────────────────────────────────
    print("  Computing v2 ELO ...")
    try:
        from src.features.elo import compute_game_elo_lookup_v2
        elo_v2 = compute_game_elo_lookup_v2(_SEASONS)
        df["home_elo_v2"] = df["game_id"].apply(lambda g: elo_v2.get(str(g), {}).get("home_elo", 1500.0))
        df["away_elo_v2"] = df["game_id"].apply(lambda g: elo_v2.get(str(g), {}).get("away_elo", 1500.0))
        df["elo_diff_v2"] = (df["home_elo_v2"] - df["away_elo_v2"]).round(2)
    except Exception as e:
        print(f"  [warn] ELO v2: {e}")
        df["home_elo_v2"] = 1500.0; df["away_elo_v2"] = 1500.0; df["elo_diff_v2"] = 0.0

    print("  Computing injury impact ...")
    try:
        from src.features.injury_impact import build_injury_lookup
        inj_lkp = build_injury_lookup(_SEASONS)
        df["home_inj_ws"] = df["game_id"].apply(lambda g: inj_lkp.get(str(g), {}).get("home_inj_ws", 0.0))
        df["away_inj_ws"] = df["game_id"].apply(lambda g: inj_lkp.get(str(g), {}).get("away_inj_ws", 0.0))
        df["inj_ws_diff"] = df["game_id"].apply(lambda g: inj_lkp.get(str(g), {}).get("inj_ws_diff", 0.0))
    except Exception as e:
        print(f"  [warn] injury: {e}")
        df["home_inj_ws"] = 0.0; df["away_inj_ws"] = 0.0; df["inj_ws_diff"] = 0.0

    for col in V2_FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0

    # ── v3 overlay ───────────────────────────────────────────────────────────
    v3_df = _load_v3_overlay(df, _SEASONS)

    # Combine: v2 features + v3 new features
    all_feature_cols = list(V2_FEATURE_COLS) + [c for c in v3_df.columns if c not in df.columns]
    for col in v3_df.columns:
        df[col] = v3_df[col].values

    for col in all_feature_cols:
        if col not in df.columns:
            df[col] = 0.0

    X = df[all_feature_cols].values.astype(np.float32)
    y = df["home_win"].values.astype(int)
    print(f"\nDataset: {len(df)} games | home win rate {y.mean():.1%} | features={len(all_feature_cols)}")

    # ── Walk-forward split ────────────────────────────────────────────────────
    split   = int(len(df) * 0.8)
    X_tr    = X[:split];  y_tr  = y[:split]
    X_val   = X[split:];  y_val = y[split:]
    print(f"  Train: {len(X_tr)}  Val: {len(X_val)}")

    # Slice masks for 2024-25 H1 / H2
    slice_metrics: dict = {}
    if "season" in df.columns and "game_date" in df.columns:
        mask_2425 = df["season"] == "2024-25"
        g2425 = df[mask_2425].reset_index(drop=True)
        mid_date = g2425.iloc[len(g2425)//2]["game_date"] if len(g2425) else "2025-01-15"
        mask_h1  = mask_2425 & (df["game_date"] < mid_date)
        mask_h2  = mask_2425 & (df["game_date"] >= mid_date)
    else:
        mid_date = mask_h1 = mask_h2 = None

    # ── LightGBM training ─────────────────────────────────────────────────────
    print("\nTraining LightGBM binary classifier ...")
    clf = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=600,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=20,
        reg_lambda=1.0,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    clf.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)],
    )

    # ── Isotonic calibration ──────────────────────────────────────────────────
    print("Calibrating with isotonic (cv=3) ...")
    cal_clf = CalibratedClassifierCV(clf, method="isotonic", cv=3)
    cal_clf.fit(X_tr, y_tr)

    # ── Evaluation ────────────────────────────────────────────────────────────
    print("\n-- Walk-forward evaluation ------------------------------------------")
    for name, Xs, ys in [("train_80pct", X_tr, y_tr), ("val_20pct", X_val, y_val)]:
        probs = cal_clf.predict_proba(Xs)[:, 1]
        acc_s   = accuracy_score(ys, (probs >= 0.5).astype(int))
        brier_s = brier_score_loss(ys, probs)
        slice_metrics[name] = {"acc": round(acc_s, 4), "brier": round(brier_s, 4), "n": len(ys)}
        print(f"  {name:14s}: acc={acc_s:.4f}  brier={brier_s:.4f}  n={len(ys)}")

    if mask_h1 is not None:
        for sname, mask in [("2024-25 H1", mask_h1), ("2024-25 H2", mask_h2)]:
            Xs_sl = df[mask][all_feature_cols].fillna(0.0).values.astype(np.float32)
            ys_sl = df[mask]["home_win"].values.astype(int)
            if len(ys_sl) < 10:
                continue
            probs_sl = cal_clf.predict_proba(Xs_sl)[:, 1]
            key = sname.replace(" ", "_").lower()
            slice_metrics[key] = {
                "acc":   round(accuracy_score(ys_sl, (probs_sl >= 0.5).astype(int)), 4),
                "brier": round(brier_score_loss(ys_sl, probs_sl), 4),
                "n":     len(ys_sl),
            }
            print(f"  {sname:14s}: acc={slice_metrics[key]['acc']:.4f}  "
                  f"brier={slice_metrics[key]['brier']:.4f}  n={len(ys_sl)}")

    val_probs = cal_clf.predict_proba(X_val)[:, 1]
    final_acc   = round(accuracy_score(y_val, (val_probs >= 0.5).astype(int)), 4)
    final_brier = round(brier_score_loss(y_val, val_probs), 4)
    print(f"\nFinal (20% val): acc={final_acc:.4f}  brier={final_brier:.4f}")

    # ── Feature importance (top 20) ───────────────────────────────────────────
    fi = dict(zip(all_feature_cols, clf.feature_importances_.tolist()))
    top20 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:20]
    print("\nTop 20 features:")
    for feat, imp in top20:
        print(f"  {feat:<45s}  {imp:.0f}")

    # ── Save model ────────────────────────────────────────────────────────────
    os.makedirs(os.path.join(PROJECT_DIR, "data", "models"), exist_ok=True)
    with open(_MODEL_V3_PATH, "wb") as f:
        pickle.dump({
            "model": cal_clf,
            "feature_cols": all_feature_cols,
            "version": "v3_integration",
        }, f)
    print(f"\nModel saved -> {_MODEL_V3_PATH}")

    # ── Save metrics ──────────────────────────────────────────────────────────
    metrics = {
        "version":          "v3_integration",
        "accuracy":         final_acc,
        "brier":            final_brier,
        "baseline_v2_acc":  _BASELINE_ACC,
        "baseline_v2_brier":_BASELINE_BRIER,
        "n_games":          len(df),
        "seasons":          _SEASONS,
        "features":         all_feature_cols,
        "n_features":       len(all_feature_cols),
        "slices":           slice_metrics,
        "top20_features":   dict(top20),
        "wall_time_sec":    round(time.time() - start_t, 1),
    }
    with open(_METRICS_V3_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics    -> {_METRICS_V3_PATH}")

    # ── Before / After ────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("BEFORE / AFTER COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<12} {'v2 baseline':>12} {'v3 new':>12} {'Delta':>12}")
    print("-" * 50)
    print(f"{'Accuracy':<12} {_BASELINE_ACC:>12.4f} {final_acc:>12.4f} {final_acc - _BASELINE_ACC:>+12.4f}")
    print(f"{'Brier':<12} {_BASELINE_BRIER:>12.4f} {final_brier:>12.4f} {final_brier - _BASELINE_BRIER:>+12.4f}")
    print(f"\nWall-clock: {round(time.time() - start_t, 0):.0f}s")


if __name__ == "__main__":
    main()
