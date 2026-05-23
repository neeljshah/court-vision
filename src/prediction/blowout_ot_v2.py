"""
blowout_ot_v2.py — Dedicated blowout + OT probability classifiers (v2).

Separate module — intentionally does NOT import from game_models.py to avoid
conflicts with the in-flight rewrite.  Reuses the scored_games_*.json cache
that game_models populates; augments it with OT labels derived from the
LeagueGameLog MIN column (team-level minutes > 252 → OT game).

Public API
----------
    BlowoutOTPredictorV2(model_dir)
    .train(seasons)   -> {"blowout": {...metrics}, "ot": {...metrics}}
    .predict_blowout(features: dict) -> float   # P(|margin|>15)
    .predict_ot(features: dict)      -> float   # P(OT periods > 0)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# ── Feature columns ─────────────────────────────────────────────────────────────
# Core pre-game features (subset of game_models FEATURE_COLS + new OT signals)

BLOWOUT_FEATURES = [
    # Team ratings L10
    "home_net_rtg_L10", "away_net_rtg_L10",
    "home_off_rtg_L10", "away_off_rtg_L10",
    "home_def_rtg_L10", "away_def_rtg_L10",
    # Talent gap (strongest blowout signal)
    "talent_gap_l10",
    # Season-level SRS
    "srs_home", "srs_away", "srs_diff",
    # Rest / back-to-back
    "home_rest_days", "away_rest_days", "rest_diff", "b2b_diff",
    # Form
    "home_win_pct_l10", "away_win_pct_l10", "win_pct_diff",
    # Pace (high pace → more variance → slightly fewer blowouts)
    "home_pace_l10", "away_pace_l10", "pace_expectation",
    # Variance / volatility
    "home_score_std_l10", "away_score_std_l10",
    # Blowout tendency (season)
    "home_blowout_freq_season", "away_blowout_freq_season",
    # Season-level ratings
    "home_net_rtg", "away_net_rtg",
    "net_rtg_diff",
    # Context
    "win_prob_home",
    "month_early", "month_mid", "month_late",
]

OT_FEATURES = BLOWOUT_FEATURES + [
    # OT-specific signals
    "is_division_rivalry",
    "season_h2h_ot_count",
    "expected_margin_abs_l10",
    "close_game_freq_home",
    "close_game_freq_away",
]

_BLOWOUT_MARGIN = 15
_OT_MIN_THRESHOLD = 252  # team-level minutes (5 players × >48 min → OT)

_TRAIN_SEASONS  = ["2022-23", "2023-24"]
_HOLDOUT_SEASON = "2024-25"


class BlowoutOTPredictorV2:
    """LightGBM blowout + OT probability classifiers with isotonic calibration."""

    def __init__(self, model_dir: str = "data/models") -> None:
        if not os.path.isabs(model_dir):
            model_dir = os.path.join(PROJECT_DIR, model_dir)
        self.model_dir = model_dir
        self._blowout_model = None
        self._ot_model = None

    # ── Train ──────────────────────────────────────────────────────────────────

    def train(self, seasons: Optional[List[str]] = None) -> Dict[str, dict]:
        """Walk-forward train blowout + OT classifiers; persist to disk."""
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("lightgbm required: pip install lightgbm")
        from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score, log_loss

        if seasons is None:
            seasons = [*_TRAIN_SEASONS, _HOLDOUT_SEASON]

        os.makedirs(self.model_dir, exist_ok=True)

        print("[blowout_ot_v2] Loading dataset ...")
        rows = []
        for s in seasons:
            s_rows = _load_scored_games(s)
            print(f"  {s}: {len(s_rows)} base rows")
            rows.extend(s_rows)

        if len(rows) < 200:
            raise ValueError(f"Insufficient data: {len(rows)} rows (need ≥200)")

        df = pd.DataFrame(rows)
        if "game_date" in df.columns:
            df = df.sort_values("game_date").reset_index(drop=True)

        print("[blowout_ot_v2] Fetching OT labels ...")
        df = _attach_ot_labels(df, seasons)

        # Compute new derived features
        df = _engineer_features(df)

        # ── Walk-forward split ─────────────────────────────────────────────────
        df_tv = df[df["season"] != _HOLDOUT_SEASON].reset_index(drop=True)
        df_ho = df[df["season"] == _HOLDOUT_SEASON].reset_index(drop=True)
        tv_cut = int(len(df_tv) * 0.70)
        df_tr = df_tv.iloc[:tv_cut].reset_index(drop=True)
        df_val = df_tv.iloc[tv_cut:].reset_index(drop=True)
        print(f"  Train={len(df_tr)} Val={len(df_val)} Holdout={len(df_ho)}")

        lgb_base = dict(
            n_estimators=500, learning_rate=0.04, num_leaves=63,
            min_child_samples=15, reg_lambda=1.5,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, n_jobs=-1, verbose=-1,
        )

        results: Dict[str, dict] = {}

        # ── 1. Blowout ─────────────────────────────────────────────────────────
        blo_feats = [c for c in BLOWOUT_FEATURES if c in df.columns]
        y_bl_tr  = (np.abs(df_tr["spread"])  > _BLOWOUT_MARGIN).astype(int).values
        y_bl_val = (np.abs(df_val["spread"]) > _BLOWOUT_MARGIN).astype(int).values
        y_bl_ho  = (np.abs(df_ho["spread"])  > _BLOWOUT_MARGIN).astype(int).values if len(df_ho) else None

        X_bl_tr  = df_tr[blo_feats].fillna(0).values.astype(np.float32)
        X_bl_val = df_val[blo_feats].fillna(0).values.astype(np.float32)
        X_bl_ho  = df_ho[blo_feats].fillna(0).values.astype(np.float32) if len(df_ho) else None

        bl_rate = y_bl_tr.mean()
        clf_bl  = lgb.LGBMClassifier(
            objective="binary",
            scale_pos_weight=(1 - bl_rate) / max(bl_rate, 1e-6),
            **lgb_base,
        )
        clf_bl.fit(X_bl_tr, y_bl_tr,
                   eval_set=[(X_bl_val, y_bl_val)],
                   callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(200)])

        # Isotonic calibration on val
        cal_bl = _make_calibrated(clf_bl)
        cal_bl.fit(X_bl_val, y_bl_val)
        self._blowout_model = cal_bl

        bl_probs_val = cal_bl.predict_proba(X_bl_val)[:, 1]
        bl_metrics = _eval_binary(y_bl_val, bl_probs_val, "Blowout Val")
        if X_bl_ho is not None and y_bl_ho is not None:
            bl_ho_probs = cal_bl.predict_proba(X_bl_ho)[:, 1]
            bl_ho_metrics = _eval_binary(y_bl_ho, bl_ho_probs, "Blowout Holdout")
        else:
            bl_ho_metrics = {}

        _save_model(cal_bl, os.path.join(self.model_dir, "blowout_v2.pkl"))

        bl_importance = _feature_importance(clf_bl, blo_feats)
        bl_cal_bins   = _calibration_bins(y_bl_val, bl_probs_val)
        results["blowout"] = {
            **bl_metrics,
            "holdout": bl_ho_metrics,
            "blowout_rate": round(float(bl_rate), 4),
            "n": len(df_tr) + len(df_val),
            "n_holdout": len(df_ho),
            "features": blo_feats,
            "top_features": bl_importance[:8],
            "calibration_bins": bl_cal_bins,
        }
        print(f"  Blowout  acc={bl_metrics['acc']:.4f}  "
              f"brier={bl_metrics['brier']:.4f}  auc={bl_metrics['auc']:.4f}")

        # ── 2. OT ──────────────────────────────────────────────────────────────
        if "ot_game" not in df.columns or df["ot_game"].sum() < 10:
            print("  [WARNING] Insufficient OT labels — skipping OT model")
            results["ot"] = {"note": "insufficient OT labels", "n": 0}
            self._save_metrics(results)
            return results

        ot_feats = [c for c in OT_FEATURES if c in df.columns]
        y_ot_tr  = df_tr["ot_game"].fillna(0).astype(int).values
        y_ot_val = df_val["ot_game"].fillna(0).astype(int).values
        y_ot_ho  = df_ho["ot_game"].fillna(0).astype(int).values if len(df_ho) else None

        X_ot_tr  = df_tr[ot_feats].fillna(0).values.astype(np.float32)
        X_ot_val = df_val[ot_feats].fillna(0).values.astype(np.float32)
        X_ot_ho  = df_ho[ot_feats].fillna(0).values.astype(np.float32) if len(df_ho) else None

        ot_rate = y_ot_tr.mean()
        print(f"  OT rate: {ot_rate:.3f} ({y_ot_tr.sum()} OT games in train)")
        clf_ot = lgb.LGBMClassifier(
            objective="binary",
            scale_pos_weight=(1 - ot_rate) / max(ot_rate, 1e-6),
            **lgb_base,
        )
        clf_ot.fit(X_ot_tr, y_ot_tr,
                   eval_set=[(X_ot_val, y_ot_val)],
                   callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(200)])

        cal_ot = _make_calibrated(clf_ot)
        cal_ot.fit(X_ot_val, y_ot_val)
        self._ot_model = cal_ot

        ot_probs_val = cal_ot.predict_proba(X_ot_val)[:, 1]
        ot_metrics = _eval_binary(y_ot_val, ot_probs_val, "OT Val")
        if X_ot_ho is not None and y_ot_ho is not None:
            ot_ho_probs = cal_ot.predict_proba(X_ot_ho)[:, 1]
            ot_ho_metrics = _eval_binary(y_ot_ho, ot_ho_probs, "OT Holdout")
        else:
            ot_ho_metrics = {}

        _save_model(cal_ot, os.path.join(self.model_dir, "ot_v2.pkl"))

        ot_importance = _feature_importance(clf_ot, ot_feats)
        ot_cal_bins   = _calibration_bins(y_ot_val, ot_probs_val)
        results["ot"] = {
            **ot_metrics,
            "holdout": ot_ho_metrics,
            "ot_rate": round(float(ot_rate), 4),
            "n": len(df_tr) + len(df_val),
            "n_holdout": len(df_ho),
            "features": ot_feats,
            "top_features": ot_importance[:8],
            "calibration_bins": ot_cal_bins,
        }
        print(f"  OT       acc={ot_metrics['acc']:.4f}  "
              f"brier={ot_metrics['brier']:.4f}  auc={ot_metrics['auc']:.4f}")

        self._save_metrics(results)
        return results

    # ── Predict ────────────────────────────────────────────────────────────────

    def predict_blowout(self, features: dict) -> float:
        """Return P(|margin| > 15) for a game described by `features`."""
        if self._blowout_model is None:
            self._blowout_model = _load_pkl(
                os.path.join(self.model_dir, "blowout_v2.pkl"))
        feats = _prep_features(features, BLOWOUT_FEATURES)
        return float(self._blowout_model.predict_proba(feats)[:, 1][0])

    def predict_ot(self, features: dict) -> float:
        """Return P(OT) for a game described by `features`."""
        if self._ot_model is None:
            self._ot_model = _load_pkl(
                os.path.join(self.model_dir, "ot_v2.pkl"))
        feats = _prep_features(features, OT_FEATURES)
        return float(self._ot_model.predict_proba(feats)[:, 1][0])

    # ── Persistence ────────────────────────────────────────────────────────────

    def _save_metrics(self, results: dict) -> None:
        path = os.path.join(self.model_dir, "blowout_ot_v2_metrics.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Metrics -> {path}")


# ── Data helpers ────────────────────────────────────────────────────────────────

def _load_scored_games(season: str) -> List[dict]:
    """Load from scored_games_*.json cache (built by game_models)."""
    path = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"scored_games_{season}.json not found — run game_models.train() first")
    with open(path) as f:
        payload = json.load(f)
    return payload.get("rows", payload) if isinstance(payload, dict) else payload


def _attach_ot_labels(df: pd.DataFrame, seasons: List[str]) -> pd.DataFrame:
    """
    Detect OT games via LeagueGameLog MIN column.
    MIN (team-level) = 5 × game_minutes.  Regulation = 240, 1-OT = 265 (≥253 = OT).
    Falls back gracefully if API unavailable.
    """
    ot_map: dict = {}  # game_id -> bool
    for season in seasons:
        ot_map.update(_fetch_ot_map(season))

    if ot_map:
        df["ot_game"] = df["game_id"].astype(str).map(
            lambda gid: int(ot_map.get(gid, False))
        ).fillna(0).astype(int)
        total_ot = df["ot_game"].sum()
        print(f"  OT games detected: {total_ot} / {len(df)} ({100*total_ot/max(len(df),1):.1f}%)")
    else:
        print("  [WARNING] Could not fetch OT labels from API — OT column missing")
        df["ot_game"] = 0
    return df


def _fetch_ot_map(season: str) -> dict:
    """Return {game_id: bool} OT flag map from LeagueGameLog MIN."""
    cache_path = os.path.join(_NBA_CACHE, f"ot_map_{season}.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    try:
        from nba_api.stats.endpoints import leaguegamelog
        time.sleep(0.6)
        gl = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        ).get_data_frames()[0]
        # MIN = team-level minutes; OT adds 5 min per period (5 players × 5 min)
        # Regulation = 240 (5 × 48). Buffer at 252 (= 240 + 12 safety) for 1-OT.
        gl["_min"] = gl["MIN"].fillna(240).astype(float)
        ot_games = gl[gl["_min"] > _OT_MIN_THRESHOLD]["GAME_ID"].astype(str).unique()
        result = {gid: True for gid in ot_games}
        with open(cache_path, "w") as f:
            json.dump(result, f)
        return result
    except Exception as e:
        print(f"  [WARNING] OT fetch failed for {season}: {e}")
        return {}


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived features to the DataFrame (no leakage — all pre-game signals)."""
    df = df.copy()

    # Talent gap (key blowout signal)
    df["talent_gap_l10"] = np.abs(
        df.get("home_net_rtg_L10", df.get("home_net_rtg", 0)) -
        df.get("away_net_rtg_L10", df.get("away_net_rtg", 0))
    )

    # Win pct L10 proxy from form_l5 (already 0-1 in the cache)
    df["home_win_pct_l10"] = df.get("home_form_l5", 0.5)
    df["away_win_pct_l10"] = df.get("away_form_l5", 0.5)
    df["win_pct_diff"]     = df["home_win_pct_l10"] - df["away_win_pct_l10"]

    # Score std proxy: we don't have per-game score history in cache, so use
    # talent_gap as a proxy for variance (better teams have less variance)
    df["home_score_std_l10"] = 10.0 + df["talent_gap_l10"] * 0.3
    df["away_score_std_l10"] = 10.0 + df["talent_gap_l10"] * 0.3

    # Blowout frequency (season-level proxy from blowout_rate column if available,
    # else use abs(net_rtg) / 20 as tendency proxy)
    df["home_blowout_freq_season"] = (
        np.abs(df.get("home_net_rtg", 0)) / 20.0
    ).clip(0, 1)
    df["away_blowout_freq_season"] = (
        np.abs(df.get("away_net_rtg", 0)) / 20.0
    ).clip(0, 1)

    # Pace expectation (already in cache — keep it, add alias if not)
    if "pace_expectation" not in df.columns:
        df["pace_expectation"] = (
            df.get("home_pace_l10", 98) + df.get("away_pace_l10", 98)
        ) / 2

    # OT-specific features ─────────────────────────────────────────────────────
    # Division rivalry proxy: same conference, close win pcts (<10% diff)
    # We don't have division data in the cache, so approximate:
    # abs(season win pct diff) < 0.10 + same general strength tier
    df["is_division_rivalry"] = (
        (np.abs(df.get("home_season_win_pct", 0.5) -
                df.get("away_season_win_pct", 0.5)) < 0.10) &
        (df["talent_gap_l10"] < 3.0)
    ).astype(float)

    # Season H2H OT count: not readily available per-game without full history
    # Use 0 as conservative default (keeps signal sparse but correct)
    df["season_h2h_ot_count"] = 0.0

    # Expected margin abs L10 (closer = more OT risk)
    df["expected_margin_abs_l10"] = df["talent_gap_l10"].clip(0, 30)

    # Close game frequency (proxy: win pct near 0.5 → tight games)
    df["close_game_freq_home"] = (
        1.0 - np.abs(df.get("home_season_win_pct", 0.5) - 0.5) * 2
    ).clip(0, 1)
    df["close_game_freq_away"] = (
        1.0 - np.abs(df.get("away_season_win_pct", 0.5) - 0.5) * 2
    ).clip(0, 1)

    # Rename L10 columns to match BLOWOUT_FEATURES naming
    if "home_net_rtg_L10" not in df.columns and "home_net_rtg_l10" in df.columns:
        df["home_net_rtg_L10"] = df["home_net_rtg_l10"]
        df["away_net_rtg_L10"] = df["away_net_rtg_l10"]
        df["home_off_rtg_L10"] = df["home_off_rtg_l10"]
        df["away_off_rtg_L10"] = df["away_off_rtg_l10"]
        df["home_def_rtg_L10"] = df["home_def_rtg_l10"]
        df["away_def_rtg_L10"] = df["away_def_rtg_l10"]

    return df


# ── Metric helpers ───────────────────────────────────────────────────────────────

def _eval_binary(y_true, y_prob, label="") -> dict:
    from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score, log_loss
    preds = (y_prob >= 0.5).astype(int)
    return {
        "acc":     round(float(accuracy_score(y_true, preds)), 4),
        "brier":   round(float(brier_score_loss(y_true, y_prob)), 4),
        "auc":     round(float(roc_auc_score(y_true, y_prob)), 4),
        "logloss": round(float(log_loss(y_true, y_prob)), 4),
        "n":       int(len(y_true)),
        "pos":     int(y_true.sum()),
    }


def _calibration_bins(y_true, y_prob, n_bins: int = 10) -> list:
    """Return list of {predicted_mid, actual_rate, count} for calibration check."""
    bins = np.linspace(0, 1, n_bins + 1)
    result = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        result.append({
            "predicted_mid": round(float((lo + hi) / 2), 3),
            "actual_rate":   round(float(y_true[mask].mean()), 3),
            "count":         int(mask.sum()),
        })
    return result


def _feature_importance(lgb_model, feat_names: list) -> list:
    """Return top features by split importance."""
    try:
        booster = lgb_model.booster_
        imp = booster.feature_importance(importance_type="gain")
        pairs = sorted(zip(feat_names, imp), key=lambda x: -x[1])
        return [{"feature": f, "importance": round(float(v), 1)} for f, v in pairs[:15]]
    except Exception:
        return []


def _prep_features(features: dict, feat_list: list) -> np.ndarray:
    """Build a 2D feature array from a features dict, filling missing with 0."""
    row = [float(features.get(f, 0.0)) for f in feat_list]
    return np.array([row], dtype=np.float32)


def _make_calibrated(estimator):
    """Return a CalibratedClassifierCV using FrozenEstimator (sklearn>=1.6) or cv='prefit'."""
    from sklearn.calibration import CalibratedClassifierCV
    try:
        from sklearn.frozen import FrozenEstimator  # sklearn >= 1.6
        return CalibratedClassifierCV(FrozenEstimator(estimator), method="isotonic")
    except ImportError:
        return CalibratedClassifierCV(estimator, method="isotonic", cv="prefit")


def _save_model(model, path: str) -> None:
    import pickle
    with open(path, "wb") as f:
        pickle.dump(model, f)
    print(f"  Saved -> {path}")


def _load_pkl(path: str):
    import pickle
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found: {path} — run .train() first")
    with open(path, "rb") as f:
        return pickle.load(f)
