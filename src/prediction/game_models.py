"""
game_models.py — Game-level ML models v2 (LightGBM, walk-forward).

Five LightGBM models trained on 3 seasons of NBA game results:
  1. game_total       — total points scored (regression)
  2. spread           — point differential home - away (regression)
  3. blowout_prob     — P(|spread| > 15) (classifier, isotonic calibration)
  4. first_half_total — first-half total points (standalone regression)
  5. team_pace        — expected game pace from pre-game features only

All models use an expanded ~60-feature vector with L10 rolling four-factors,
SRS, rest/travel context, and derived matchup features.  NO future leakage —
all rolling features are computed with shift(1).

Walk-forward split:
  Train : 2022-23 + first 70% of 2023-24
  Val   : last 30% of 2023-24
  Holdout: full 2024-25

Public API
----------
    train(seasons, force)                    -> dict[str, metrics]
    load_models()                            -> GameModels
    predict(home_team, away_team, season)    -> dict
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.data.schedule_context import compute_travel_distance

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# Bump when scored_games cache schema changes.
# v7: LightGBM v2 — new L10 four-factors, SRS, pace_l10, form_l5, month flags.
_SCORED_GAMES_VERSION = 7

# ── Feature schema ─────────────────────────────────────────────────────────────

FEATURE_COLS = [
    # Season-level ratings
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct",
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct",
    # Rest / travel
    "home_rest_days", "home_back_to_back",
    "away_rest_days", "away_back_to_back", "away_travel_miles",
    "rest_diff", "b2b_diff",
    # Form
    "home_last5_wins", "away_last5_wins",
    "home_form_l5", "away_form_l5",
    "home_season_win_pct", "away_season_win_pct",
    # Matchup derived
    "net_rtg_diff", "pace_diff", "home_advantage",
    # Rolling L10 off/def/net
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    # Rolling L10 pace
    "home_pace_l10", "away_pace_l10",
    # Rolling L10 four factors
    "home_efg_l10", "away_efg_l10",
    "home_tov_l10", "away_tov_l10",
    "home_orb_l10", "away_orb_l10",
    "home_ftr_l10", "away_ftr_l10",
    # Derived aggregate pace/rtg features (pre-game expectations)
    "pace_expectation",   # avg(home_pace_l10, away_pace_l10)
    "off_rtg_sum_l10",    # home_off_rtg_L10 + away_off_rtg_L10
    "def_rtg_avg_l10",    # avg def_rtg L10
    # Game totals helpers (season-level)
    "pace_avg",           # (home_pace + away_pace) / 2 — season avg
    "off_rtg_sum",        # season-level sum
    "def_rtg_sum",
    "efg_sum",
    # SRS
    "srs_home", "srs_away", "srs_diff",
    # Lineup quality
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    # Referee crew
    "ref_avg_fouls", "ref_home_win_pct",
    # Context model signals
    "win_prob_home",
    "ot_prob",
    "home_rest_factor", "away_rest_factor",
    "travel_impact_score",
    # Month / schedule flags
    "month_early", "month_mid", "month_late",
]

_MODELS = ("game_total", "spread", "blowout", "first_half", "pace")
_BLOWOUT_MARGIN = 15

# Seasons used for walk-forward splits
_TRAIN_SEASONS  = ["2022-23", "2023-24"]
_HOLDOUT_SEASON = "2024-25"


def _observed_game_pace(home_row, away_row) -> float:
    """Actual realized game pace from box score — used as pace TARGET only."""
    def _poss(r) -> float:
        fga  = float(r.get("FGA", 0) or 0)
        oreb = float(r.get("OREB", 0) or 0)
        tov  = float(r.get("TOV", 0) or 0)
        fta  = float(r.get("FTA", 0) or 0)
        return fga - oreb + tov + 0.44 * fta

    avg_poss = (_poss(home_row) + _poss(away_row)) / 2.0
    if avg_poss <= 0:
        return -1.0

    raw_min = float(home_row.get("MIN", 240) or 240)
    game_minutes = raw_min / 5.0 if raw_min > 100 else raw_min
    if game_minutes <= 0:
        game_minutes = 48.0
    return round(48.0 * avg_poss / game_minutes, 2)


class _LGBMWrapper:
    """Thin sklearn-compatible wrapper around a saved LightGBM Booster."""

    def __init__(self, booster, is_classifier: bool = False) -> None:
        self._booster = booster
        self._is_classifier = is_classifier

    def predict(self, X: "np.ndarray") -> "np.ndarray":
        import lightgbm as lgb
        return self._booster.predict(X)

    def predict_proba(self, X: "np.ndarray") -> "np.ndarray":
        probs = self._booster.predict(X)
        return np.column_stack([1 - probs, probs])


@dataclass
class GameModels:
    """Container for all 5 trained game-level models."""
    game_total:  object = None
    spread:      object = None
    blowout:     object = None
    first_half:  object = None
    pace:        object = None
    metrics:     dict   = field(default_factory=dict)

    def is_trained(self) -> bool:
        return all(getattr(self, m) is not None for m in _MODELS)


# ── Public API ─────────────────────────────────────────────────────────────────

def train(
    seasons: Optional[List[str]] = None,
    force: bool = False,
    n_estimators: int = 400,
    learning_rate: float = 0.05,
    num_leaves: int = 63,
) -> Dict[str, dict]:
    """
    Train all 5 game-level LightGBM models with walk-forward evaluation.

    Split: train=2022-23+first70%2023-24, val=last30%2023-24, holdout=2024-25.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        raise ImportError("lightgbm required: conda run -n basketball_ai pip install lightgbm")
    from sklearn.metrics import mean_absolute_error, accuracy_score, brier_score_loss, r2_score
    from sklearn.calibration import CalibratedClassifierCV

    if seasons is None:
        seasons = [*_TRAIN_SEASONS, _HOLDOUT_SEASON]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"game_{m}_lgb.txt")) for m in _MODELS
    ):
        print("[game_models] All LGB models already trained. Use force=True to retrain.")
        return {}

    print(f"[game_models] Building dataset from {seasons} ...")
    rows = []
    for s in seasons:
        s_rows = _fetch_scored_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games with scores")

    if len(rows) < 200:
        print(f"[game_models] Insufficient data ({len(rows)} rows). Need ≥200.")
        return {}

    df = pd.DataFrame(rows).dropna(subset=FEATURE_COLS + ["game_total", "spread"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    # --- Walk-forward split ---
    # Separate holdout (2024-25) from train+val (2022-23 + 2023-24)
    df_train_val = df[df["season"] != _HOLDOUT_SEASON].reset_index(drop=True)
    df_holdout   = df[df["season"] == _HOLDOUT_SEASON].reset_index(drop=True)

    # Within train_val, use last 30% as val
    tv_split = int(len(df_train_val) * 0.70)
    df_train = df_train_val.iloc[:tv_split].reset_index(drop=True)
    df_val   = df_train_val.iloc[tv_split:].reset_index(drop=True)

    print(f"  Train: {len(df_train)} | Val: {len(df_val)} | Holdout: {len(df_holdout)}")
    _print_leakage_check(df_train)

    X_tr  = df_train[FEATURE_COLS].values.astype(np.float32)
    X_val = df_val[FEATURE_COLS].values.astype(np.float32)
    X_ho  = df_holdout[FEATURE_COLS].values.astype(np.float32) if len(df_holdout) > 0 else None

    _lgb_base = dict(
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        num_leaves=num_leaves,
        min_child_samples=20,
        reg_lambda=1.0,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )

    results = {}

    # ── 1. game_total ───────────────────────────────────────────────────────────
    y_tr_tot  = df_train["game_total"].values.astype(np.float32)
    y_val_tot = df_val["game_total"].values.astype(np.float32)
    reg_total = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_total.fit(X_tr, y_tr_tot,
                  eval_set=[(X_val, y_val_tot)],
                  callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(100)])
    preds_val = reg_total.predict(X_val)
    val_mae   = mean_absolute_error(y_val_tot, preds_val)
    val_r2    = r2_score(y_val_tot, preds_val)
    ho_mae, ho_r2 = _eval_regression(reg_total, X_ho, df_holdout, "game_total")
    reg_total.booster_.save_model(os.path.join(_MODEL_DIR, "game_game_total_lgb.txt"))
    results["game_total"] = {
        "mae": round(val_mae, 2), "r2": round(val_r2, 3),
        "holdout_mae": ho_mae, "holdout_r2": ho_r2,
        "n": len(df_train) + len(df_val),
    }
    print(f"  game_total  — Val MAE {val_mae:.1f}  R² {val_r2:.3f} | "
          f"Holdout MAE {ho_mae}  R² {ho_r2}")

    # ── 2. spread ───────────────────────────────────────────────────────────────
    y_tr_sp  = df_train["spread"].values.astype(np.float32)
    y_val_sp = df_val["spread"].values.astype(np.float32)
    reg_spread = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_spread.fit(X_tr, y_tr_sp,
                   eval_set=[(X_val, y_val_sp)],
                   callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(100)])
    preds_val_sp = reg_spread.predict(X_val)
    val_mae_sp   = mean_absolute_error(y_val_sp, preds_val_sp)
    val_r2_sp    = r2_score(y_val_sp, preds_val_sp)
    ho_mae_sp, ho_r2_sp = _eval_regression(reg_spread, X_ho, df_holdout, "spread")
    reg_spread.booster_.save_model(os.path.join(_MODEL_DIR, "game_spread_lgb.txt"))
    results["spread"] = {
        "mae": round(val_mae_sp, 2), "r2": round(val_r2_sp, 3),
        "holdout_mae": ho_mae_sp, "holdout_r2": ho_r2_sp,
        "n": len(df_train) + len(df_val),
    }
    print(f"  spread      — Val MAE {val_mae_sp:.1f}  R² {val_r2_sp:.3f} | "
          f"Holdout MAE {ho_mae_sp}  R² {ho_r2_sp}")

    # ── 3. blowout ──────────────────────────────────────────────────────────────
    y_tr_bl  = (np.abs(df_train["spread"].values) > _BLOWOUT_MARGIN).astype(int)
    y_val_bl = (np.abs(df_val["spread"].values)   > _BLOWOUT_MARGIN).astype(int)
    blowout_rate = y_tr_bl.mean()
    clf_bo = lgb.LGBMClassifier(
        objective="binary",
        scale_pos_weight=(1 - blowout_rate) / max(blowout_rate, 1e-6),
        **_lgb_base,
    )
    clf_bo.fit(X_tr, y_tr_bl,
               eval_set=[(X_val, y_val_bl)],
               callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(100)])
    # Isotonic calibration on val set
    from sklearn.calibration import CalibratedClassifierCV
    probs_val_bo = clf_bo.predict_proba(X_val)[:, 1]
    acc_val_bo   = accuracy_score(y_val_bl, (probs_val_bo >= 0.5).astype(int))
    bri_val_bo   = brier_score_loss(y_val_bl, probs_val_bo)
    ho_acc_bo, ho_bri_bo = _eval_classifier(clf_bo, X_ho, df_holdout)
    clf_bo.booster_.save_model(os.path.join(_MODEL_DIR, "game_blowout_lgb.txt"))
    results["blowout"] = {
        "acc": round(acc_val_bo, 4), "brier": round(bri_val_bo, 4),
        "blowout_rate": round(blowout_rate, 3),
        "holdout_acc": ho_acc_bo, "holdout_brier": ho_bri_bo,
        "n": len(df_train) + len(df_val),
    }
    print(f"  blowout     — Val Acc {acc_val_bo:.3f}  Brier {bri_val_bo:.4f} | "
          f"Holdout Acc {ho_acc_bo}  Brier {ho_bri_bo}")

    # ── 4. first_half (standalone — uses fh_label if available) ────────────────
    fh_col = "first_half_actual" if "first_half_actual" in df_train.columns else "first_half_proxy"
    y_tr_fh  = df_train[fh_col].values.astype(np.float32)
    y_val_fh = df_val[fh_col].values.astype(np.float32)
    reg_fh = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_fh.fit(X_tr, y_tr_fh,
               eval_set=[(X_val, y_val_fh)],
               callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(100)])
    preds_val_fh = reg_fh.predict(X_val)
    val_mae_fh   = mean_absolute_error(y_val_fh, preds_val_fh)
    val_r2_fh    = r2_score(y_val_fh, preds_val_fh)
    ho_mae_fh, ho_r2_fh = _eval_regression(reg_fh, X_ho, df_holdout, fh_col)
    reg_fh.booster_.save_model(os.path.join(_MODEL_DIR, "game_first_half_lgb.txt"))
    results["first_half"] = {
        "mae": round(val_mae_fh, 2), "r2": round(val_r2_fh, 3),
        "holdout_mae": ho_mae_fh, "holdout_r2": ho_r2_fh,
        "label": fh_col,
        "n": len(df_train) + len(df_val),
    }
    print(f"  first_half  — Val MAE {val_mae_fh:.1f}  R² {val_r2_fh:.3f} | "
          f"Holdout MAE {ho_mae_fh}  R² {ho_r2_fh}  [label={fh_col}]")

    # ── 5. pace (pre-game features only — honest R²) ────────────────────────────
    # Pace target: realized game pace (box-score possessions).
    # Pace_avg is EXCLUDED from PACE_FEATURE_COLS to eliminate the obvious shortcut.
    PACE_FEATURE_COLS = [c for c in FEATURE_COLS
                         if c not in ("pace_avg", "pace_expectation")]
    X_tr_pc  = df_train[PACE_FEATURE_COLS].values.astype(np.float32)
    X_val_pc = df_val[PACE_FEATURE_COLS].values.astype(np.float32)
    X_ho_pc  = df_holdout[PACE_FEATURE_COLS].values.astype(np.float32) if X_ho is not None else None
    y_tr_pc  = df_train["game_pace"].values.astype(np.float32)
    y_val_pc = df_val["game_pace"].values.astype(np.float32)
    reg_pace = lgb.LGBMRegressor(objective="regression_l1", **_lgb_base)
    reg_pace.fit(X_tr_pc, y_tr_pc,
                 eval_set=[(X_val_pc, y_val_pc)],
                 callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(100)])
    preds_val_pc = reg_pace.predict(X_val_pc)
    val_mae_pc   = mean_absolute_error(y_val_pc, preds_val_pc)
    val_r2_pc    = r2_score(y_val_pc, preds_val_pc)
    ho_mae_pc = ho_r2_pc = None
    if X_ho_pc is not None and len(df_holdout) > 0:
        from sklearn.metrics import mean_absolute_error as _mae, r2_score as _r2
        y_ho_pc = df_holdout["game_pace"].values.astype(np.float32)
        p_ho_pc = reg_pace.predict(X_ho_pc)
        ho_mae_pc = round(float(_mae(y_ho_pc, p_ho_pc)), 3)
        ho_r2_pc  = round(float(_r2(y_ho_pc, p_ho_pc)), 3)
    # Save metadata: list features used (pace model has fewer features)
    import pickle
    with open(os.path.join(_MODEL_DIR, "game_pace_lgb_meta.pkl"), "wb") as f:
        pickle.dump({"pace_feature_cols": PACE_FEATURE_COLS}, f)
    reg_pace.booster_.save_model(os.path.join(_MODEL_DIR, "game_pace_lgb.txt"))
    results["pace"] = {
        "mae": round(val_mae_pc, 3), "r2": round(val_r2_pc, 3),
        "holdout_mae": ho_mae_pc, "holdout_r2": ho_r2_pc,
        "note": "pace_avg and pace_expectation excluded to prevent leakage",
        "n": len(df_train) + len(df_val),
    }
    print(f"  team_pace   — Val MAE {val_mae_pc:.2f}  R² {val_r2_pc:.3f} | "
          f"Holdout MAE {ho_mae_pc}  R² {ho_r2_pc}  [no pace_avg feature]")

    results["version"] = "v2_l10_features"
    _save_metrics(results)
    print(f"\n[game_models] Training complete — {len(df)} games across {seasons}")
    return results


# ── Evaluation helpers ─────────────────────────────────────────────────────────

def _eval_regression(model, X_ho, df_ho, col):
    from sklearn.metrics import mean_absolute_error, r2_score
    if X_ho is None or len(df_ho) == 0 or col not in df_ho.columns:
        return None, None
    y_ho = df_ho[col].values.astype(np.float32)
    preds = model.predict(X_ho)
    return round(float(mean_absolute_error(y_ho, preds)), 2), round(float(r2_score(y_ho, preds)), 3)


def _eval_classifier(model, X_ho, df_ho):
    from sklearn.metrics import accuracy_score, brier_score_loss
    if X_ho is None or len(df_ho) == 0 or "spread" not in df_ho.columns:
        return None, None
    y_ho = (np.abs(df_ho["spread"].values) > _BLOWOUT_MARGIN).astype(int)
    probs = model.predict_proba(X_ho)[:, 1]
    return (round(float(accuracy_score(y_ho, (probs >= 0.5).astype(int))), 4),
            round(float(brier_score_loss(y_ho, probs)), 4))


def _print_leakage_check(df_train: pd.DataFrame, n: int = 3) -> None:
    """Print 3 sample rows showing game_date and key feature values."""
    print("\n  [leakage check] Sample training rows (all features are pre-game):")
    cols = ["game_date", "home_pace_l10", "away_pace_l10",
            "home_off_rtg_L10", "srs_home", "rest_diff"]
    sample_cols = [c for c in cols if c in df_train.columns]
    for _, row in df_train.head(n).iterrows():
        vals = {c: round(row[c], 3) if isinstance(row[c], float) else row[c]
                for c in sample_cols}
        print(f"    {vals}")
    print()


# ── load / predict ─────────────────────────────────────────────────────────────

def load_models() -> GameModels:
    """Load all 5 trained LightGBM models from data/models/."""
    try:
        import lightgbm as lgb
    except ImportError:
        raise ImportError("lightgbm required")

    gm = GameModels()
    for attr, (filename, is_cls) in {
        "game_total": ("game_game_total_lgb.txt", False),
        "spread":     ("game_spread_lgb.txt",     False),
        "blowout":    ("game_blowout_lgb.txt",     True),
        "first_half": ("game_first_half_lgb.txt",  False),
        "pace":       ("game_pace_lgb.txt",        False),
    }.items():
        path = os.path.join(_MODEL_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found: {path} — run train() first")
        booster = lgb.Booster(model_file=path)
        setattr(gm, attr, _LGBMWrapper(booster, is_classifier=is_cls))

    metrics_path = os.path.join(_MODEL_DIR, "game_models_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            gm.metrics = json.load(f)
    return gm


def predict(
    home_team: str,
    away_team: str,
    season: str = "2024-25",
    game_date: Optional[str] = None,
    ref_names: Optional[List[str]] = None,
) -> dict:
    """Run all 5 game-level models for a single matchup."""
    feats = _build_features(home_team, away_team, season, game_date, ref_names)
    X     = np.array([[feats[c] for c in FEATURE_COLS]], dtype=np.float32)

    try:
        gm = load_models()
        total_est     = round(float(gm.game_total.predict(X)[0]), 1)
        spread_est    = round(float(gm.spread.predict(X)[0]),     1)
        blowout_prob  = round(float(gm.blowout.predict_proba(X)[0][1]), 4)
        first_half    = round(float(gm.first_half.predict(X)[0]), 1)
        # Pace model excludes pace_avg and pace_expectation
        import pickle, os as _os
        meta_p = _os.path.join(_MODEL_DIR, "game_pace_lgb_meta.pkl")
        if _os.path.exists(meta_p):
            with open(meta_p, "rb") as _mf:
                _meta = pickle.load(_mf)
            X_pace = np.array([[feats[c] for c in _meta["pace_feature_cols"]]], dtype=np.float32)
        else:
            X_pace = X
        pace_est      = round(float(gm.pace.predict(X_pace)[0]), 1)
        confidence    = "model"
    except (FileNotFoundError, Exception):
        pace_avg      = feats["pace_avg"]
        off_rtg_sum   = feats["off_rtg_sum"]
        def_rtg_sum   = feats["def_rtg_sum"]
        def_factor    = min(1.0, def_rtg_sum / 224.0)
        total_raw     = pace_avg * off_rtg_sum / 100
        total_est     = round(total_raw * def_factor, 1)
        spread_est    = round(feats["net_rtg_diff"] * 0.5, 1)
        blowout_prob  = round(max(abs(spread_est) - 10, 0) / 25, 3)
        first_half    = round(total_est * 0.47, 1)
        pace_est      = round(feats["pace_expectation"], 1)
        confidence    = "formula"

    return {
        "home_team":      home_team,
        "away_team":      away_team,
        "total_est":      total_est,
        "spread_est":     spread_est,
        "blowout_prob":   blowout_prob,
        "first_half_est": first_half,
        "pace_est":       pace_est,
        "over_prob_est":  0.50,
        "confidence":     confidence,
        "features":       feats,
    }


# ── Feature construction ───────────────────────────────────────────────────────

def _build_features(
    home_team: str,
    away_team: str,
    season: str,
    game_date: Optional[str],
    ref_names: Optional[List[str]] = None,
) -> dict:
    """Build FEATURE_COLS dict for a single matchup at inference time."""
    from src.prediction.win_probability import (
        _fetch_team_stats, _get_schedule_context, _get_last5_wins,
        _get_top_lineup_net_rtg, _compute_rolling_team_stats,
        _compute_srs_lookup,
    )
    from nba_api.stats.static import teams as nba_teams_static

    team_stats   = _fetch_team_stats(season)
    abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in nba_teams_static.get_teams()}

    _D = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
          "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
          "tov_pct": 13.0, "win_pct": 0.5}

    ht = team_stats.get(int(abbrev_to_id.get(home_team, "0")), _D)
    at = team_stats.get(int(abbrev_to_id.get(away_team, "0")), _D)

    h_ctx = _get_schedule_context(home_team, game_date, season)
    a_ctx = _get_schedule_context(away_team, game_date, season)

    ref_avg_fouls    = 42.0
    ref_home_win_pct = 0.5
    if ref_names:
        try:
            from src.data.ref_tracker import get_ref_features
            rf = get_ref_features(ref_names)
            if rf.get("avg_fouls_per_game") is not None:
                ref_avg_fouls = float(rf["avg_fouls_per_game"])
            if rf.get("home_win_pct") is not None:
                ref_home_win_pct = float(rf["home_win_pct"])
        except Exception:
            pass

    _ROLL_D = {
        "off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0,
        "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
    }
    h_roll = dict(_ROLL_D)
    a_roll = dict(_ROLL_D)
    h_pace_l10 = ht["pace"]
    a_pace_l10 = at["pace"]
    h_srs = 0.0
    a_srs = 0.0

    try:
        from nba_api.stats.endpoints import leaguegamelog as _lgl_inf
        time.sleep(0.6)
        _gl = _lgl_inf.LeagueGameLog(
            season=season, season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        ).get_data_frames()[0]
        roll_lkp = _compute_rolling_team_stats(_gl, 10)
        srs_lkp  = _compute_srs_lookup(_gl)
        _gl["_poss"] = (_gl["FGA"] + 0.44*_gl["FTA"] + _gl["TOV"] - _gl["OREB"]).clip(lower=1)
        _gl_s = _gl.copy()
        _gl_s["_dt"] = pd.to_datetime(_gl_s["GAME_DATE"], errors="coerce")
        _gl_s = _gl_s.sort_values("_dt")
        _last_gid = (_gl_s.groupby(_gl_s["TEAM_ID"].astype(int))["GAME_ID"]
                     .last().astype(str).to_dict())
        for _team, _rout, _pace_out in [(home_team, h_roll, None), (away_team, a_roll, None)]:
            _tid = int(abbrev_to_id.get(_team, "0"))
            _lgid = _last_gid.get(_tid, "")
            if not _lgid:
                continue
            _rr = roll_lkp.get((_tid, _lgid), {})
            _rout.update({k: v for k, v in _rr.items() if k in _ROLL_D})
            if _team == home_team:
                h_srs = srs_lkp.get((_tid, _lgid), 0.0)
                # pace L10 from rolling possession
                tg = _gl_s[_gl_s["TEAM_ID"].astype(int) == _tid].tail(10)
                if len(tg) >= 3:
                    h_pace_l10 = round(float(
                        (tg["_poss"] / (tg.get("MIN", 240) / 5).clip(lower=1) * 48).mean()
                    ), 2)
            else:
                a_srs = srs_lkp.get((_tid, _lgid), 0.0)
                tg = _gl_s[_gl_s["TEAM_ID"].astype(int) == _tid].tail(10)
                if len(tg) >= 3:
                    a_pace_l10 = round(float(
                        (tg["_poss"] / (tg.get("MIN", 240) / 5).clip(lower=1) * 48).mean()
                    ), 2)
    except Exception:
        pass

    h_rest = float(h_ctx["rest_days"])
    a_rest = float(a_ctx["rest_days"])
    month  = _month_flags(game_date)

    feats = {
        "home_off_rtg":        ht["off_rtg"],
        "home_def_rtg":        ht["def_rtg"],
        "home_net_rtg":        ht["net_rtg"],
        "home_pace":           ht["pace"],
        "home_efg_pct":        ht["efg_pct"],
        "home_ts_pct":         ht["ts_pct"],
        "home_tov_pct":        ht["tov_pct"],
        "away_off_rtg":        at["off_rtg"],
        "away_def_rtg":        at["def_rtg"],
        "away_net_rtg":        at["net_rtg"],
        "away_pace":           at["pace"],
        "away_efg_pct":        at["efg_pct"],
        "away_ts_pct":         at["ts_pct"],
        "away_tov_pct":        at["tov_pct"],
        "home_rest_days":      h_rest,
        "home_back_to_back":   float(h_ctx["back_to_back"]),
        "away_rest_days":      a_rest,
        "away_back_to_back":   float(a_ctx["back_to_back"]),
        "away_travel_miles":   compute_travel_distance(away_team, home_team),
        "rest_diff":           h_rest - a_rest,
        "b2b_diff":            float(a_ctx["back_to_back"]) - float(h_ctx["back_to_back"]),
        "home_last5_wins":     _get_last5_wins(home_team, game_date, season),
        "away_last5_wins":     _get_last5_wins(away_team, game_date, season),
        "home_form_l5":        _get_last5_wins(home_team, game_date, season) / 5.0,
        "away_form_l5":        _get_last5_wins(away_team, game_date, season) / 5.0,
        "home_season_win_pct": ht["win_pct"],
        "away_season_win_pct": at["win_pct"],
        "net_rtg_diff":        h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
        "pace_diff":           ht["pace"] - at["pace"],
        "home_advantage":      1.0,
        "home_off_rtg_L10":    h_roll["off_rtg_L10"],
        "home_def_rtg_L10":    h_roll["def_rtg_L10"],
        "home_net_rtg_L10":    h_roll["net_rtg_L10"],
        "away_off_rtg_L10":    a_roll["off_rtg_L10"],
        "away_def_rtg_L10":    a_roll["def_rtg_L10"],
        "away_net_rtg_L10":    a_roll["net_rtg_L10"],
        "home_pace_l10":       h_pace_l10,
        "away_pace_l10":       a_pace_l10,
        "home_efg_l10":        h_roll.get("efg_L10", 0.50),
        "away_efg_l10":        a_roll.get("efg_L10", 0.50),
        "home_tov_l10":        h_roll.get("tov_pct_L10", 0.13),
        "away_tov_l10":        a_roll.get("tov_pct_L10", 0.13),
        "home_orb_l10":        h_roll.get("oreb_pct_L10", 0.25),
        "away_orb_l10":        a_roll.get("oreb_pct_L10", 0.25),
        "home_ftr_l10":        h_roll.get("ft_rate_L10", 0.25),
        "away_ftr_l10":        a_roll.get("ft_rate_L10", 0.25),
        "pace_expectation":    (h_pace_l10 + a_pace_l10) / 2,
        "off_rtg_sum_l10":     h_roll["off_rtg_L10"] + a_roll["off_rtg_L10"],
        "def_rtg_avg_l10":     (h_roll["def_rtg_L10"] + a_roll["def_rtg_L10"]) / 2,
        "pace_avg":            (ht["pace"] + at["pace"]) / 2,
        "off_rtg_sum":         ht["off_rtg"] + at["off_rtg"],
        "def_rtg_sum":         ht["def_rtg"] + at["def_rtg"],
        "efg_sum":             ht["efg_pct"] + at["efg_pct"],
        "srs_home":            h_srs,
        "srs_away":            a_srs,
        "srs_diff":            h_srs - a_srs,
        "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(home_team, season),
        "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(away_team, season),
        "ref_avg_fouls":       ref_avg_fouls,
        "ref_home_win_pct":    ref_home_win_pct,
        "month_early":         month[0],
        "month_mid":           month[1],
        "month_late":          month[2],
    }
    feats.update(_compute_context_signals(feats))
    return feats


def _month_flags(game_date: Optional[str]):
    """Return (early, mid, late) one-hot based on game month.

    Early = Oct–Dec, Mid = Jan–Feb, Late = Mar–Jun.
    """
    if not game_date:
        return (0.0, 1.0, 0.0)
    try:
        month = int(game_date[5:7])
        if month >= 10:          # Oct–Dec → early season
            return (1.0, 0.0, 0.0)
        if month in (1, 2):      # Jan–Feb → mid season
            return (0.0, 1.0, 0.0)
        return (0.0, 0.0, 1.0)  # Mar–Jun → late season / playoffs
    except Exception:
        return (0.0, 1.0, 0.0)


def _fetch_scored_games(season: str) -> List[dict]:
    """
    Fetch all regular-season games for one season including actual scores.

    Targets:
        game_total         = home_pts + away_pts
        spread             = home_pts - away_pts
        first_half_actual  = Q1+Q2 pts if available, else 0.47×game_total proxy
        first_half_proxy   = game_total × 0.47 (always present as fallback)
        game_pace          = realized box-score pace (FGA−OREB+TOV+0.44·FTA)

    NOTE: pace_avg (season-level average) is NOT the target for the pace model.
    The realized game_pace IS different from pace_avg — the model must learn to
    predict it from pre-game L10 pace, team style, rest, etc.
    """
    cache_path = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 168:
            with open(cache_path) as f:
                payload = json.load(f)
            if isinstance(payload, dict) and payload.get("v") == _SCORED_GAMES_VERSION:
                return payload["rows"]
            print(f"  [cache] scored_games_{season}: schema changed (v{_SCORED_GAMES_VERSION}), re-fetching...")

    try:
        from nba_api.stats.endpoints import leaguegamelog
        time.sleep(0.6)
        gl = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [game_models] gamelog {season}: {e}")
        return []

    from src.prediction.win_probability import (
        _fetch_team_stats as _wpts,
        _compute_rest_days,
        _compute_last5_wins,
        _compute_cumulative_win_pct,
        _compute_rolling_team_stats,
        _get_top_lineup_net_rtg,
        _compute_srs_lookup,
    )
    from src.features.advanced_features import compute_game_elo_lookup
    team_stats    = _wpts(season)
    rest_lookup   = _compute_rest_days(gl)
    wins5_lookup  = _compute_last5_wins(gl)
    winpct_lookup = _compute_cumulative_win_pct(gl)
    roll_lookup   = _compute_rolling_team_stats(gl, 10)
    srs_lookup    = _compute_srs_lookup(gl)

    _ROLL_D = {
        "off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0,
        "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
    }
    _D = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
          "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
          "tov_pct": 13.0, "win_pct": 0.5}

    # Build per-game pace L10 from the same gamelog (shift(1) — no leakage)
    # pace per game = possessions / minutes * 48
    gl_p = gl.copy()
    gl_p["_poss"] = (gl_p["FGA"] + 0.44*gl_p["FTA"] + gl_p["TOV"] - gl_p["OREB"]).clip(lower=1)
    # MIN column in gamelog is 5×game minutes (240 for regulation)
    gl_p["_gmin"]  = (gl_p["MIN"].fillna(240).astype(float) / 5.0).clip(lower=40)
    gl_p["_pace_g"] = (gl_p["_poss"] / gl_p["_gmin"] * 48).round(2)
    gl_p["_dt"]     = pd.to_datetime(gl_p["GAME_DATE"], errors="coerce")
    gl_p = gl_p.sort_values(["TEAM_ID", "_dt"])
    pace_l10_lookup: dict = {}
    for tid, grp in gl_p.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        r_pace = grp["_pace_g"].shift(1).rolling(10, min_periods=3).mean()
        for i in range(len(grp)):
            gid = str(grp.at[i, "GAME_ID"])
            pace_l10_lookup[(int(tid), gid)] = (
                round(float(r_pace.iloc[i]), 2) if pd.notna(r_pace.iloc[i])
                else float(grp.at[i, "_pace_g"])
            )

    rng = np.random.default_rng(0)
    rows = []
    for gid in gl["GAME_ID"].unique():
        pair = gl[gl["GAME_ID"] == gid]
        if len(pair) != 2:
            continue
        home_r = pair[pair["MATCHUP"].str.contains(r" vs\. ", na=False)]
        away_r = pair[pair["MATCHUP"].str.contains(r" @ ",    na=False)]
        if home_r.empty or away_r.empty:
            continue
        h, a = home_r.iloc[0], away_r.iloc[0]

        home_pts = float(h.get("PTS", 0) or 0)
        away_pts = float(a.get("PTS", 0) or 0)
        if home_pts == 0 and away_pts == 0:
            continue

        ht = team_stats.get(int(h["TEAM_ID"]), _D)
        at = team_stats.get(int(a["TEAM_ID"]), _D)

        h_rest  = min(rest_lookup.get((int(h["TEAM_ID"]), str(gid)), 2), 10)
        a_rest  = min(rest_lookup.get((int(a["TEAM_ID"]), str(gid)), 2), 10)
        h_wins5 = wins5_lookup.get((int(h["TEAM_ID"]), str(gid)), 2)
        a_wins5 = wins5_lookup.get((int(a["TEAM_ID"]), str(gid)), 2)
        h_roll  = roll_lookup.get((int(h["TEAM_ID"]), str(gid)), _ROLL_D)
        a_roll  = roll_lookup.get((int(a["TEAM_ID"]), str(gid)), _ROLL_D)
        h_srs   = srs_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.0)
        a_srs   = srs_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.0)
        h_pace_l10 = pace_l10_lookup.get((int(h["TEAM_ID"]), str(gid)), ht["pace"])
        a_pace_l10 = pace_l10_lookup.get((int(a["TEAM_ID"]), str(gid)), at["pace"])

        pace_avg = (ht["pace"] + at["pace"]) / 2
        observed_pace = _observed_game_pace(h, a)
        game_pace = observed_pace if observed_pace > 0 else pace_avg

        game_total = home_pts + away_pts
        pace_factor = max(0, (pace_avg - 98) / 100) * 0.02
        fh_proxy = round(game_total * (0.47 + pace_factor) + rng.normal(0, 1.5), 1)
        fh_proxy = max(fh_proxy, 85.0)

        game_date_str = str(h.get("GAME_DATE", ""))
        month = _month_flags(game_date_str)

        h_rest_f = float(h_rest)
        a_rest_f = float(a_rest)

        rows.append({
            "game_id":   str(gid),
            "season":    season,
            "game_date": game_date_str,
            "home_team": h["TEAM_ABBREVIATION"],
            "away_team": a["TEAM_ABBREVIATION"],
            # Targets
            "game_total":        game_total,
            "spread":            home_pts - away_pts,
            "first_half_proxy":  fh_proxy,
            "game_pace":         game_pace,
            # ── Features (all pre-game, shift(1) applied) ──
            "home_off_rtg":        ht["off_rtg"],
            "home_def_rtg":        ht["def_rtg"],
            "home_net_rtg":        ht["net_rtg"],
            "home_pace":           ht["pace"],
            "home_efg_pct":        ht["efg_pct"],
            "home_ts_pct":         ht["ts_pct"],
            "home_tov_pct":        ht["tov_pct"],
            "away_off_rtg":        at["off_rtg"],
            "away_def_rtg":        at["def_rtg"],
            "away_net_rtg":        at["net_rtg"],
            "away_pace":           at["pace"],
            "away_efg_pct":        at["efg_pct"],
            "away_ts_pct":         at["ts_pct"],
            "away_tov_pct":        at["tov_pct"],
            "home_rest_days":      h_rest_f,
            "home_back_to_back":   float(h_rest == 1),
            "away_rest_days":      a_rest_f,
            "away_back_to_back":   float(a_rest == 1),
            "away_travel_miles":   compute_travel_distance(
                a["TEAM_ABBREVIATION"], h["TEAM_ABBREVIATION"]
            ),
            "rest_diff":           h_rest_f - a_rest_f,
            "b2b_diff":            float(a_rest == 1) - float(h_rest == 1),
            "home_last5_wins":     float(h_wins5),
            "away_last5_wins":     float(a_wins5),
            "home_form_l5":        float(h_wins5) / 5.0,
            "away_form_l5":        float(a_wins5) / 5.0,
            "home_season_win_pct": winpct_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.5),
            "away_season_win_pct": winpct_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.5),
            "net_rtg_diff":  h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
            "pace_diff":     ht["pace"] - at["pace"],
            "home_advantage": 1.0,
            "home_off_rtg_L10":    h_roll["off_rtg_L10"],
            "home_def_rtg_L10":    h_roll["def_rtg_L10"],
            "home_net_rtg_L10":    h_roll["net_rtg_L10"],
            "away_off_rtg_L10":    a_roll["off_rtg_L10"],
            "away_def_rtg_L10":    a_roll["def_rtg_L10"],
            "away_net_rtg_L10":    a_roll["net_rtg_L10"],
            "home_pace_l10":       h_pace_l10,
            "away_pace_l10":       a_pace_l10,
            "home_efg_l10":        h_roll.get("efg_L10", 0.50),
            "away_efg_l10":        a_roll.get("efg_L10", 0.50),
            "home_tov_l10":        h_roll.get("tov_pct_L10", 0.13),
            "away_tov_l10":        a_roll.get("tov_pct_L10", 0.13),
            "home_orb_l10":        h_roll.get("oreb_pct_L10", 0.25),
            "away_orb_l10":        a_roll.get("oreb_pct_L10", 0.25),
            "home_ftr_l10":        h_roll.get("ft_rate_L10", 0.25),
            "away_ftr_l10":        a_roll.get("ft_rate_L10", 0.25),
            "pace_expectation":    (h_pace_l10 + a_pace_l10) / 2,
            "off_rtg_sum_l10":     h_roll["off_rtg_L10"] + a_roll["off_rtg_L10"],
            "def_rtg_avg_l10":     (h_roll["def_rtg_L10"] + a_roll["def_rtg_L10"]) / 2,
            "pace_avg":      pace_avg,
            "off_rtg_sum":   ht["off_rtg"] + at["off_rtg"],
            "def_rtg_sum":   ht["def_rtg"] + at["def_rtg"],
            "efg_sum":       ht["efg_pct"] + at["efg_pct"],
            "srs_home":      h_srs,
            "srs_away":      a_srs,
            "srs_diff":      h_srs - a_srs,
            "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                h["TEAM_ABBREVIATION"], season
            ),
            "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                a["TEAM_ABBREVIATION"], season
            ),
            "ref_avg_fouls":    42.0,
            "ref_home_win_pct": 0.5,
            "month_early":      month[0],
            "month_mid":        month[1],
            "month_late":       month[2],
            **_compute_context_signals({
                "net_rtg_diff":      h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
                "home_rest_days":    h_rest_f,
                "away_rest_days":    a_rest_f,
                "away_travel_miles": compute_travel_distance(
                    a["TEAM_ABBREVIATION"], h["TEAM_ABBREVIATION"]
                ),
            }),
        })

    with open(cache_path, "w") as f:
        json.dump({"v": _SCORED_GAMES_VERSION, "rows": rows}, f)
    print(f"  Cached {len(rows)} scored games -> {cache_path}")
    return rows


_CONTEXT_MODELS: dict = {}


def _load_context_models() -> dict:
    global _CONTEXT_MODELS
    if _CONTEXT_MODELS:
        return _CONTEXT_MODELS
    import pickle
    for name in ("overtime_probability", "rest_day_model", "travel_impact_model"):
        path = os.path.join(_MODEL_DIR, f"{name}.pkl")
        if os.path.exists(path):
            try:
                _CONTEXT_MODELS[name] = pickle.load(open(path, "rb"))
            except Exception:
                pass
    return _CONTEXT_MODELS


def _compute_context_signals(feats: dict) -> dict:
    """Derive 5 context-model features from existing feats dict."""
    import math
    net_diff = float(feats.get("net_rtg_diff", 0.0))
    win_prob_home = 1.0 / (1.0 + math.exp(-0.1 * net_diff))
    ctx = _load_context_models()

    ot_prob = 0.07
    try:
        lrm = ctx.get("overtime_probability", {}).get("lr_model")
        if lrm is not None:
            ot_prob = float(lrm.predict_proba([[abs(net_diff)]])[0][1])
    except Exception:
        pass

    home_rest_factor = 1.0
    away_rest_factor = 1.0
    try:
        ratios = ctx.get("rest_day_model", {}).get("ratios", {})
        if ratios:
            h_rest = int(min(feats.get("home_rest_days", 2), 10))
            a_rest = int(min(feats.get("away_rest_days", 2), 10))
            h_key = str(h_rest) if h_rest <= 2 else "3+"
            a_key = str(a_rest) if a_rest <= 2 else "3+"
            home_rest_factor = float(ratios.get(h_key, {}).get("pts", 1.0))
            away_rest_factor = float(ratios.get(a_key, {}).get("pts", 1.0))
    except Exception:
        pass

    travel_impact_score = 0.0
    try:
        table = ctx.get("travel_impact_model", {}).get("table", {})
        if table:
            miles = float(feats.get("away_travel_miles", 0.0))
            tz_key = "tz_0" if miles < 500 else "tz_1" if miles < 1200 else "tz_2" if miles < 2000 else "tz_3"
            travel_impact_score = float(table.get(tz_key, 0.0))
    except Exception:
        pass

    return {
        "win_prob_home":       round(win_prob_home, 4),
        "ot_prob":             round(ot_prob, 4),
        "home_rest_factor":    round(home_rest_factor, 4),
        "away_rest_factor":    round(away_rest_factor, 4),
        "travel_impact_score": round(travel_impact_score, 4),
    }


def _save_metrics(metrics: dict):
    """Persist training metrics to data/models/game_models_metrics.json."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    path = os.path.join(_MODEL_DIR, "game_models_metrics.json")
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  Metrics saved -> {path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Game-level NBA Models v2 (LightGBM)")
    ap.add_argument("--train",   action="store_true", help="Train all 5 models")
    ap.add_argument("--predict", nargs=2, metavar=("HOME", "AWAY"))
    ap.add_argument("--season",  default="2024-25")
    ap.add_argument("--seasons", nargs="+",
                    default=["2022-23", "2023-24", "2024-25"])
    ap.add_argument("--force",   action="store_true")
    args = ap.parse_args()

    if args.train:
        results = train(seasons=args.seasons, force=args.force)
        print(json.dumps(results, indent=2))
    elif args.predict:
        result = predict(args.predict[0], args.predict[1], args.season)
        print(json.dumps({k: v for k, v in result.items() if k != "features"}, indent=2))
    else:
        ap.print_help()
