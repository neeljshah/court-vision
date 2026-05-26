"""
game_models.py — Game-level ML models (Phase 4).

Five XGBoost models trained on 3 seasons of NBA game results:
  1. game_total       — total points scored (regression, MAE ~8-10 pts)
  2. spread           — point differential home - away (regression, MAE ~10-12 pts)
  3. blowout_prob     — P(|spread| > 15) (classifier)
  4. first_half_total — first-half total points (regression, proxy: 0.47 × game_total)
  5. team_pace        — expected game pace possessions (regression)

All models share a common 30-feature vector built from team season ratings,
rest/travel context, and derived matchup features.

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
from src.prediction._paths import resolve_data_dir, resolve_model_dir

# R31_X2: worktree-aware resolver. `_MODEL_DIR` resolves the legacy
# single-XGB heads (game_*.json, *.pkl), `_M2_FAMILY_DIR` resolves the
# 20-model ensemble. Both honour `NBA_MODEL_DIR` / `NBA_DATA_DIR` env
# overrides and fall back to the host repo when this worktree's
# `data/models/` is empty. `_NBA_CACHE` participates in the same scheme
# so season_games_*.json lookups also resolve to host artifacts.
# Canary `game_game_total.json` is the smallest legacy artifact present
# whenever the host has trained game-level models; if missing, the dir is
# still returned (callers raise FileNotFoundError as before).
_MODEL_DIR = resolve_model_dir(
    canary="game_game_total.json",
    project_dir=PROJECT_DIR,
)
_NBA_CACHE = resolve_data_dir("nba", project_dir=PROJECT_DIR)

# Bump when scored_games cache schema changes to force re-fetch.
# v6: game_pace target switched from season-pace average to realised
#     box-score pace (PRED-01 leakage fix) — old caches must be rebuilt.
_SCORED_GAMES_VERSION = 6

# ── Feature schema ─────────────────────────────────────────────────────────────

FEATURE_COLS = [
    # Home team ratings
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct",
    "home_rest_days", "home_back_to_back",
    "home_last5_wins", "home_season_win_pct",
    # Away team ratings
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct",
    "away_rest_days", "away_back_to_back", "away_travel_miles",
    "away_last5_wins", "away_season_win_pct",
    # Derived matchup features
    "net_rtg_diff",     # home_net_rtg - away_net_rtg
    "pace_diff",        # home_pace - away_pace
    "home_advantage",   # constant 1.0
    # Game-level totals features (extra vs win_prob)
    "pace_avg",         # (home_pace + away_pace) / 2
    "off_rtg_sum",      # home_off_rtg + away_off_rtg
    "def_rtg_sum",      # home_def_rtg + away_def_rtg
    "efg_sum",          # home_efg_pct + away_efg_pct
    # Lineup quality (season-level top 5-man lineup net rating)
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    # Referee crew tendencies (default=league avg during training)
    "ref_avg_fouls", "ref_home_win_pct",
    # Rolling L10: game-by-game rolling avg (10-game window, no season bias)
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    # Context model signals
    "win_prob_home",        # logistic of net_rtg_diff (proxy for pre-game win prob)
    "ot_prob",              # overtime_probability.pkl LR model
    "home_rest_factor",     # rest_day_model.pkl pts ratio for home rest bucket
    "away_rest_factor",     # rest_day_model.pkl pts ratio for away rest bucket
    "travel_impact_score",  # travel_impact_model.pkl tz-based adjustment
]

# Model names
_MODELS = ("game_total", "spread", "blowout", "first_half", "pace")

# Blowout threshold (abs margin > N = blowout)
_BLOWOUT_MARGIN = 15


def _observed_game_pace(home_row, away_row) -> float:
    """Actual game pace — possessions per 48 minutes — from the box score.

    Possessions use Dean Oliver's estimator: FGA − OREB + TOV + 0.44·FTA.
    The result is the *realised* pace of that specific game, not the average
    of the two teams' season paces.  Using the season-pace average as the
    target made it identical to the `pace_avg` feature — a 100% leakage that
    inflated the pace model's R² to a meaningless 1.0 (fixed: task PRED-01).

    OT games are normalised back to a per-48 pace via the team MIN column.
    Falls back to the season-pace average only when box-score stats are absent.
    """
    def _poss(r) -> float:
        fga  = float(r.get("FGA", 0) or 0)
        oreb = float(r.get("OREB", 0) or 0)
        tov  = float(r.get("TOV", 0) or 0)
        fta  = float(r.get("FTA", 0) or 0)
        return fga - oreb + tov + 0.44 * fta

    avg_poss = (_poss(home_row) + _poss(away_row)) / 2.0
    if avg_poss <= 0:
        return -1.0  # sentinel — caller substitutes the season-pace prior

    raw_min = float(home_row.get("MIN", 240) or 240)
    # Team MIN is 5×game minutes (240 for regulation); some feeds report 48.
    game_minutes = raw_min / 5.0 if raw_min > 100 else raw_min
    if game_minutes <= 0:
        game_minutes = 48.0
    return round(48.0 * avg_poss / game_minutes, 2)


class _BoosterWrapper:
    """Thin wrapper around xgb.Booster exposing predict() and predict_proba()."""

    def __init__(self, booster: "xgb.Booster", is_classifier: bool = False) -> None:
        self._booster = booster
        self._is_classifier = is_classifier

    def predict(self, X: "np.ndarray") -> "np.ndarray":
        import xgboost as xgb
        dm = xgb.DMatrix(X)
        return self._booster.predict(dm)

    def predict_proba(self, X: "np.ndarray") -> "np.ndarray":
        import xgboost as xgb
        dm = xgb.DMatrix(X)
        probs = self._booster.predict(dm)
        return np.column_stack([1 - probs, probs])


@dataclass
class GameModels:
    """Container for all 5 trained game-level models."""

    game_total:  object = None   # XGBRegressor
    spread:      object = None   # XGBRegressor
    blowout:     object = None   # XGBClassifier
    first_half:  object = None   # XGBRegressor
    pace:        object = None   # XGBRegressor
    metrics:     dict   = field(default_factory=dict)

    def is_trained(self) -> bool:
        """Return True if all 5 models are loaded."""
        return all(
            getattr(self, m) is not None for m in _MODELS
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def train(
    seasons: Optional[List[str]] = None,
    force: bool = False,
    n_estimators: int = 300,
    learning_rate: float = 0.05,
    max_depth: int = 4,
) -> Dict[str, dict]:
    """
    Train all 5 game-level XGBoost models on historical game data.

    Fetches season game logs from NBA Stats API, constructs feature vectors
    with actual scores as targets, trains each model with 80/20 chrono split.

    Args:
        seasons:       Seasons to train on (default 3 most recent).
        force:         Retrain even if models already saved.
        n_estimators:  XGBoost trees.
        learning_rate: XGBoost lr.
        max_depth:     XGBoost depth.

    Returns:
        Dict mapping model_name → {"mae"/"acc": float, "n": int}.
    """
    from xgboost import XGBRegressor, XGBClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, accuracy_score, brier_score_loss, r2_score

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    # Check if already trained
    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"game_{m}.json")) for m in _MODELS
    ):
        print("[game_models] All models already trained. Use force=True to retrain.")
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

    # Chronological sort — no future leakage into validation
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    X  = df[FEATURE_COLS].values.astype(np.float32)
    split = int(len(df) * 0.8)

    results = {}
    _xgb_kw = dict(
        n_estimators=n_estimators, learning_rate=learning_rate,
        max_depth=max_depth, subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1,
    )

    # 1. Game total (regression)
    y_total = df["game_total"].values.astype(np.float32)
    reg_total = XGBRegressor(**_xgb_kw, eval_metric="rmse", early_stopping_rounds=20)
    reg_total.fit(X[:split], y_total[:split],
                  eval_set=[(X[split:], y_total[split:])], verbose=50)
    preds = reg_total.predict(X[split:])
    mae = mean_absolute_error(y_total[split:], preds)
    r2  = r2_score(y_total[split:], preds)
    reg_total.save_model(os.path.join(_MODEL_DIR, "game_game_total.json"))
    results["game_total"] = {"mae": round(mae, 2), "r2": round(r2, 3), "n": len(y_total)}
    print(f"  game_total  — MAE {mae:.1f} pts  R² {r2:.3f}")

    # 2. Spread / point differential (regression)
    y_spread = df["spread"].values.astype(np.float32)
    reg_spread = XGBRegressor(**_xgb_kw, eval_metric="rmse", early_stopping_rounds=20)
    reg_spread.fit(X[:split], y_spread[:split],
                   eval_set=[(X[split:], y_spread[split:])], verbose=50)
    preds_sp = reg_spread.predict(X[split:])
    mae_sp = mean_absolute_error(y_spread[split:], preds_sp)
    r2_sp  = r2_score(y_spread[split:], preds_sp)
    reg_spread.save_model(os.path.join(_MODEL_DIR, "game_spread.json"))
    results["spread"] = {"mae": round(mae_sp, 2), "r2": round(r2_sp, 3), "n": len(y_spread)}
    print(f"  spread      — MAE {mae_sp:.1f} pts  R² {r2_sp:.3f}")

    # 3. Blowout probability (classifier)
    y_blowout = (np.abs(y_spread) > _BLOWOUT_MARGIN).astype(int)
    blowout_rate = y_blowout.mean()
    clf_blowout = XGBClassifier(
        **_xgb_kw, eval_metric="logloss", early_stopping_rounds=20,
        scale_pos_weight=(1 - blowout_rate) / blowout_rate,
    )
    clf_blowout.fit(X[:split], y_blowout[:split],
                    eval_set=[(X[split:], y_blowout[split:])], verbose=50)
    probs_b = clf_blowout.predict_proba(X[split:])[:, 1]
    acc_b   = accuracy_score(y_blowout[split:], (probs_b >= 0.5).astype(int))
    brier_b = brier_score_loss(y_blowout[split:], probs_b)
    clf_blowout.save_model(os.path.join(_MODEL_DIR, "game_blowout.json"))
    results["blowout"] = {"acc": round(acc_b, 4), "brier": round(brier_b, 4),
                          "blowout_rate": round(blowout_rate, 3), "n": len(y_blowout)}
    print(f"  blowout     — Acc {acc_b:.3f}  Brier {brier_b:.4f}  rate {blowout_rate:.2%}")

    # 4. First-half total (proxy: game_total × 0.47 with noise baked in from real variance)
    # NBA first halves average 46-48% of game total.  We don't have halftime scores
    # in the free NBA API, so we train on this proxy.  The model learns team-specific
    # patterns (high-pace teams tend to push above 0.47 in the first half).
    y_first_half = df["first_half_proxy"].values.astype(np.float32)
    reg_fh = XGBRegressor(**_xgb_kw, eval_metric="rmse", early_stopping_rounds=20)
    reg_fh.fit(X[:split], y_first_half[:split],
               eval_set=[(X[split:], y_first_half[split:])], verbose=50)
    preds_fh = reg_fh.predict(X[split:])
    mae_fh = mean_absolute_error(y_first_half[split:], preds_fh)
    r2_fh  = r2_score(y_first_half[split:], preds_fh)
    reg_fh.save_model(os.path.join(_MODEL_DIR, "game_first_half.json"))
    results["first_half"] = {"mae": round(mae_fh, 2), "r2": round(r2_fh, 3), "n": len(y_first_half)}
    print(f"  first_half  — MAE {mae_fh:.1f} pts  R² {r2_fh:.3f}  (proxy label)")

    # 5. Team pace predictor (regression — predicts expected game pace)
    y_pace = df["game_pace"].values.astype(np.float32)
    reg_pace = XGBRegressor(**_xgb_kw, eval_metric="rmse", early_stopping_rounds=20)
    reg_pace.fit(X[:split], y_pace[:split],
                 eval_set=[(X[split:], y_pace[split:])], verbose=50)
    preds_pc = reg_pace.predict(X[split:])
    mae_pc = mean_absolute_error(y_pace[split:], preds_pc)
    r2_pc  = r2_score(y_pace[split:], preds_pc)
    reg_pace.save_model(os.path.join(_MODEL_DIR, "game_pace.json"))
    results["pace"] = {"mae": round(mae_pc, 2), "r2": round(r2_pc, 3), "n": len(y_pace)}
    print(f"  team_pace   — MAE {mae_pc:.2f} pos  R² {r2_pc:.3f}")

    # Save aggregate metrics
    _save_metrics(results)
    print(f"\n[game_models] Training complete — {len(df)} games across {seasons}")
    return results


def load_models() -> GameModels:
    """
    Load all 5 trained models from data/models/.

    Returns:
        GameModels with all 5 models populated.

    Raises:
        FileNotFoundError: If any model file is missing — run train() first.
    """
    import xgboost as xgb

    gm = GameModels()
    model_map = {
        "game_total": ("game_game_total.json", False),
        "spread":     ("game_spread.json",     False),
        "blowout":    ("game_blowout.json",    True),
        "first_half": ("game_first_half.json", False),
        "pace":       ("game_pace.json",       False),
    }

    for attr, (filename, is_cls) in model_map.items():
        path = os.path.join(_MODEL_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found: {path} — run train() first")
        booster = xgb.Booster()
        booster.load_model(path)
        setattr(gm, attr, _BoosterWrapper(booster, is_classifier=is_cls))

    metrics_path = os.path.join(_MODEL_DIR, "game_models_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            gm.metrics = json.load(f)

    return gm


# ── R20_M7: M2 family multi5 ensemble loader (R11 BATCH-6/7 ship) ─────────────
# The 20-model M2 family ensemble (5 models × 4 targets = total/spread/home_pts/
# away_pts) lives in data/models/m2_family/ and was trained by
# scripts/train_final_M2_family.py — see manifest.json for ancestry. Prior to
# R20_M7 it was ONLY callable from scripts/predict_game.py CLI; every production
# caller (api/predictions_router → game_orchestrator → game_models.predict,
# scripts/run_daily_slate.py team-total normalization) was still loading the
# legacy single-XGB game_game_total.json / game_spread.json artifacts.
#
# Wire policy: when a game_id is supplied OR we can resolve one from
# (home_team, away_team, game_date) via season_games_*.json, AND the 74-col
# feature row is fully populated, the m2_family ensemble overrides total_est /
# spread_est on the predict() return. blowout_prob, first_half_est, pace_est
# stay on the legacy single-XGB heads (no m2 ship for those yet).
# R31_X2: m2_family resolves INDEPENDENTLY of the legacy `_MODEL_DIR` so
# a worktree that happens to have legacy single-XGB heads but not the 20-
# model ensemble still finds the host-repo m2_family. Canary is the
# manifest.json that _try_load_m2_family below requires anyway.
_M2_FAMILY_DIR = os.path.join(
    resolve_model_dir(
        canary=os.path.join("m2_family", "manifest.json"),
        project_dir=PROJECT_DIR,
    ),
    "m2_family",
)
_M2_FAMILY_CACHE: Optional[Dict[str, list]] = None
_M2_FAMILY_FEATS: Optional[List[str]] = None
_M2_FAMILY_MANIFEST: Optional[dict] = None

# R31_X3: parallel multitask MLP path. Activated by env var
#   M2_FAMILY_USE_MLP=1
# Loads from data/models/m2_family_mlp/ (does NOT overwrite m2_family/).
# Architecture: shared trunk (74->128->64) + 4 heads, seed-ensemble of 3.
# On the 2025-26 holdout it improves all 4 targets vs the multi5 ensemble
# (total -1.80%, spread -2.85%, home_pts -1.90%, away_pts -6.15%) and wins
# all 8 head-to-head walk-forward folds.
_M2_FAMILY_MLP_DIR = os.path.join(_MODEL_DIR, "m2_family_mlp")
_M2_FAMILY_MLP_CACHE: Optional[List] = None     # list of (seed, model, mu_y, sd_y)
_M2_FAMILY_MLP_SCALER = None                     # sklearn StandardScaler
_M2_FAMILY_MLP_FEATS: Optional[List[str]] = None
_M2_FAMILY_MLP_MANIFEST: Optional[dict] = None
_M2_FAMILY_MLP_TARGET_ORDER: Optional[List[str]] = None


def _m2_family_use_mlp() -> bool:
    """Read env var fresh each call so tests can flip it without re-import."""
    return os.environ.get("M2_FAMILY_USE_MLP", "").strip().lower() in ("1", "true", "yes")

# R21_N5: per-(game_id, models_mtime) prediction cache. Skips feature build +
# 20 model `.predict` calls when the artifact dir hasn't changed since the
# cached value was written. Cache lives in data/cache/ (gitignored) and is
# written atomically (tmpfile + os.replace) so concurrent callers can't tear
# the JSON.
# R31_X2: prediction cache writes ALWAYS go to the local worktree's
# data/cache (never to a host-repo dir we may have only READ models from).
# This preserves isolation — each worktree's cache stays its own.
_M2_PRED_CACHE_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "m2_family_predictions_cache.json"
)


def _m2_family_models_mtime() -> float:
    """Max mtime across files in data/models/m2_family/. Returns 0.0 when
    the dir doesn't exist (cache key will still be deterministic)."""
    if not os.path.isdir(_M2_FAMILY_DIR):
        return 0.0
    max_mt = 0.0
    try:
        for fn in os.listdir(_M2_FAMILY_DIR):
            p = os.path.join(_M2_FAMILY_DIR, fn)
            try:
                mt = os.path.getmtime(p)
                if mt > max_mt:
                    max_mt = mt
            except OSError:
                continue
    except OSError:
        return 0.0
    return max_mt


def _load_m2_pred_cache() -> dict:
    """Read the on-disk JSON cache. Returns {} on any read error so callers
    treat it as cold miss instead of crashing."""
    if not os.path.exists(_M2_PRED_CACHE_PATH):
        return {}
    try:
        with open(_M2_PRED_CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _save_m2_pred_cache(cache: dict) -> None:
    """Atomic write: tmp + os.replace so a crashed writer never leaves a
    half-written JSON behind for the next reader."""
    os.makedirs(os.path.dirname(_M2_PRED_CACHE_PATH), exist_ok=True)
    tmp = _M2_PRED_CACHE_PATH + f".tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, _M2_PRED_CACHE_PATH)
    except OSError:
        # Best-effort cleanup; never raise from the cache writer.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def clear_m2_pred_cache() -> bool:
    """Delete the on-disk cache. Returns True iff something was removed."""
    if os.path.exists(_M2_PRED_CACHE_PATH):
        try:
            os.remove(_M2_PRED_CACHE_PATH)
            return True
        except OSError:
            return False
    return False


def _build_mlp_module(n_features: int, n_targets: int, dropout: float = 0.2):
    """Mirror of probe_R31_X3 _build_torch_model. Kept local so callers don't
    need the probe script on PYTHONPATH."""
    import torch.nn as nn  # noqa: PLC0415

    class MultitaskMLP(nn.Module):
        def __init__(self, n_in: int, n_tgt: int, p_drop: float):
            super().__init__()
            self.trunk = nn.Sequential(
                nn.Linear(n_in, 128), nn.ReLU(), nn.Dropout(p_drop),
                nn.Linear(128, 64),  nn.ReLU(), nn.Dropout(p_drop),
            )
            self.heads = nn.ModuleList([nn.Linear(64, 1) for _ in range(n_tgt)])

        def forward(self, x):
            import torch  # noqa: PLC0415
            h = self.trunk(x)
            outs = [head(h).squeeze(-1) for head in self.heads]
            return torch.stack(outs, dim=1)

    return MultitaskMLP(n_features, n_targets, dropout)


def _try_load_m2_family_mlp() -> bool:
    """Lazy-load the R31_X3 multitask MLP ensemble. Returns True iff usable."""
    global _M2_FAMILY_MLP_CACHE, _M2_FAMILY_MLP_SCALER, _M2_FAMILY_MLP_FEATS
    global _M2_FAMILY_MLP_MANIFEST, _M2_FAMILY_MLP_TARGET_ORDER
    if _M2_FAMILY_MLP_CACHE is not None:
        return bool(_M2_FAMILY_MLP_CACHE)
    manifest_p = os.path.join(_M2_FAMILY_MLP_DIR, "manifest.json")
    cols_p     = os.path.join(_M2_FAMILY_MLP_DIR, "feature_cols.json")
    scaler_p   = os.path.join(_M2_FAMILY_MLP_DIR, "feature_scaler.joblib")
    if not (os.path.exists(manifest_p) and os.path.exists(cols_p) and os.path.exists(scaler_p)):
        _M2_FAMILY_MLP_CACHE = []
        return False
    try:
        import joblib  # noqa: PLC0415
        import torch   # noqa: PLC0415
        with open(manifest_p, encoding="utf-8") as f:
            man = json.load(f)
        with open(cols_p, encoding="utf-8") as f:
            cols = json.load(f)
        scaler = joblib.load(scaler_p)
        loaded = []
        for lab in man.get("seed_models", []):
            ckpt_p = os.path.join(_M2_FAMILY_MLP_DIR, f"{lab}.pt")
            if not os.path.exists(ckpt_p):
                raise FileNotFoundError(ckpt_p)
            ckpt = torch.load(ckpt_p, map_location="cpu", weights_only=False)
            model = _build_mlp_module(
                n_features=int(ckpt["n_features"]),
                n_targets=int(ckpt["n_targets"]),
                dropout=0.2,
            )
            model.load_state_dict(ckpt["state_dict"])
            model.eval()
            loaded.append((
                lab,
                model,
                np.asarray(ckpt["mu_y"], dtype=np.float64),
                np.asarray(ckpt["sd_y"], dtype=np.float64),
            ))
        if not loaded:
            _M2_FAMILY_MLP_CACHE = []
            return False
        _M2_FAMILY_MLP_CACHE = loaded
        _M2_FAMILY_MLP_SCALER = scaler
        _M2_FAMILY_MLP_FEATS = cols
        _M2_FAMILY_MLP_MANIFEST = man
        _M2_FAMILY_MLP_TARGET_ORDER = man.get("target_order",
                                              ["total", "spread", "home_pts", "away_pts"])
        return True
    except Exception:
        _M2_FAMILY_MLP_CACHE = []
        return False


def _predict_m2_family_mlp(row: dict) -> Optional[Dict[str, float]]:
    """Run the R31_X3 multitask MLP ensemble on a season_games row.
    Returns {total_est, spread_est, home_pts_est, away_pts_est} or None."""
    if not _try_load_m2_family_mlp():
        return None
    if (_M2_FAMILY_MLP_FEATS is None or _M2_FAMILY_MLP_SCALER is None
            or not _M2_FAMILY_MLP_CACHE or _M2_FAMILY_MLP_TARGET_ORDER is None):
        return None
    try:
        import torch  # noqa: PLC0415
        vals = []
        for c in _M2_FAMILY_MLP_FEATS:
            v = row.get(c, 0.0)
            try:
                vals.append(float(v) if v is not None else 0.0)
            except (TypeError, ValueError):
                vals.append(0.0)
        X_raw = np.array([vals], dtype=np.float64)
        X = _M2_FAMILY_MLP_SCALER.transform(X_raw).astype(np.float32)
        xt = torch.from_numpy(X)
        preds = None
        with torch.no_grad():
            for _lab, model, mu_y, sd_y in _M2_FAMILY_MLP_CACHE:
                pz = model(xt).cpu().numpy()
                p = pz * sd_y + mu_y
                preds = p if preds is None else preds + p
        preds = preds / len(_M2_FAMILY_MLP_CACHE)
        # Map target order -> est keys
        idx = {t: i for i, t in enumerate(_M2_FAMILY_MLP_TARGET_ORDER)}
        return {
            "total_est":    round(float(preds[0, idx["total"]]), 1),
            "spread_est":   round(float(preds[0, idx["spread"]]), 1),
            "home_pts_est": round(float(preds[0, idx["home_pts"]]), 1),
            "away_pts_est": round(float(preds[0, idx["away_pts"]]), 1),
        }
    except Exception:
        return None


def _try_load_m2_family() -> bool:
    """Lazy-load the M2 family ensemble. Returns True iff usable."""
    global _M2_FAMILY_CACHE, _M2_FAMILY_FEATS, _M2_FAMILY_MANIFEST
    if _M2_FAMILY_CACHE is not None:
        return bool(_M2_FAMILY_CACHE)
    manifest_path = os.path.join(_M2_FAMILY_DIR, "manifest.json")
    cols_path     = os.path.join(_M2_FAMILY_DIR, "feature_cols.json")
    if not (os.path.exists(manifest_path) and os.path.exists(cols_path)):
        _M2_FAMILY_CACHE = {}
        return False
    try:
        import joblib  # noqa: PLC0415
        with open(manifest_path, encoding="utf-8") as f:
            man = json.load(f)
        with open(cols_path, encoding="utf-8") as f:
            cols = json.load(f)
        bundle: Dict[str, list] = {}
        for target in ("total", "spread", "home_pts", "away_pts"):
            labels = man["targets"][target]["models"]
            models = []
            for lab in labels:
                p = os.path.join(_M2_FAMILY_DIR, f"{target}_{lab}.joblib")
                if not os.path.exists(p):
                    raise FileNotFoundError(p)
                models.append(joblib.load(p))
            bundle[target] = models
        _M2_FAMILY_CACHE = bundle
        _M2_FAMILY_FEATS = cols
        _M2_FAMILY_MANIFEST = man
        return True
    except Exception:
        _M2_FAMILY_CACHE = {}
        return False


def _lookup_season_games_row(
    game_id: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
    game_date: Optional[str],
) -> Optional[dict]:
    """Resolve a fully-featured row from season_games_*.json.

    Tries (in order): explicit game_id → (home, away, date) match → None.
    Returns the raw row dict or None when not found / missing required cols.
    """
    candidate_files = [
        "season_games_2025-26.json",
        "season_games_2024-25.json",
        "season_games_2023-24.json",
        "season_games_2022-23.json",
    ]
    for fname in candidate_files:
        p = os.path.join(_NBA_CACHE, fname)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        rows = d.get("rows", d) if isinstance(d, dict) else d
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            if game_id and str(r.get("game_id", "")) == str(game_id):
                # Require minimum feature presence (m2 fails on near-empty rows).
                if "home_off_rtg" in r:
                    return r
                return None
            if (home_team and away_team
                    and str(r.get("home_team", "")).upper() == home_team.upper()
                    and str(r.get("away_team", "")).upper() == away_team.upper()):
                if game_date is None or str(r.get("game_date", ""))[:10] == str(game_date)[:10]:
                    if "home_off_rtg" in r:
                        return r
    return None


def _predict_m2_family(
    row: dict, game_id: Optional[str] = None
) -> Optional[Dict[str, float]]:
    """Run the 4-target m2_family ensemble on a season_games row. Returns
    {total_est, spread_est, home_pts_est, away_pts_est} or None on failure.

    R21_N5: caches the 4-value tuple per (game_id, models_mtime). On cache
    hit (same models_mtime) we skip the 20 model `.predict` calls + the
    feature vector build entirely. Cache invalidates automatically when any
    file in data/models/m2_family/ is rewritten (re-trained).

    R31_X3: when env var M2_FAMILY_USE_MLP=1, route to the multitask MLP
    ensemble in data/models/m2_family_mlp/ instead. The cache is bypassed
    on the MLP path (the .pt files have separate mtimes from the multi5
    .joblibs so cache keys would collide otherwise).
    """
    if _m2_family_use_mlp():
        return _predict_m2_family_mlp(row)

    if not _try_load_m2_family() or _M2_FAMILY_FEATS is None:
        return None

    # ── R21_N5 cache hit path ────────────────────────────────────────────────
    gid = str(game_id) if game_id else (str(row.get("game_id")) if row.get("game_id") else None)
    current_mtime = _m2_family_models_mtime()
    cache: dict = {}
    if gid:
        cache = _load_m2_pred_cache()
        entry = cache.get(gid)
        if (
            isinstance(entry, dict)
            and entry.get("models_mtime") == current_mtime
            and all(k in entry for k in ("total_est", "spread_est",
                                         "home_pts_est", "away_pts_est"))
        ):
            return {
                "total_est":    float(entry["total_est"]),
                "spread_est":   float(entry["spread_est"]),
                "home_pts_est": float(entry["home_pts_est"]),
                "away_pts_est": float(entry["away_pts_est"]),
            }

    # ── Cold path: build features + run 20 model predict calls ───────────────
    try:
        vals = []
        for c in _M2_FAMILY_FEATS:
            v = row.get(c, 0.0)
            try:
                vals.append(float(v) if v is not None else 0.0)
            except (TypeError, ValueError):
                vals.append(0.0)
        X = np.array([vals], dtype=np.float32)
        out: Dict[str, float] = {}
        for target_key, out_key in (("total", "total_est"), ("spread", "spread_est"),
                                     ("home_pts", "home_pts_est"),
                                     ("away_pts", "away_pts_est")):
            models = _M2_FAMILY_CACHE.get(target_key) if _M2_FAMILY_CACHE else None
            if not models:
                return None
            preds = np.zeros(X.shape[0])
            for m in models:
                preds += m.predict(X)
            out[out_key] = round(float(preds[0]) / len(models), 1)
    except Exception:
        return None

    # ── Persist into cache (best-effort; never break the prediction) ─────────
    if gid:
        try:
            from datetime import datetime, timezone
            # Re-read just before write to avoid clobbering another writer's
            # row for a different game_id.
            fresh = _load_m2_pred_cache()
            fresh[gid] = {
                "models_mtime": current_mtime,
                "total_est":    out["total_est"],
                "spread_est":   out["spread_est"],
                "home_pts_est": out["home_pts_est"],
                "away_pts_est": out["away_pts_est"],
                "computed_at":  datetime.now(timezone.utc).isoformat(),
            }
            _save_m2_pred_cache(fresh)
        except Exception:
            pass

    return out


def predict(
    home_team: str,
    away_team: str,
    season: str = "2024-25",
    game_date: Optional[str] = None,
    ref_names: Optional[List[str]] = None,
    game_id: Optional[str] = None,
) -> dict:
    """
    Run all 5 game-level models for a single matchup.

    Falls back to formula-based estimates when models are not trained.

    R20_M7: when game_id (or a (home, away, date) match) resolves a populated
    season_games row, the M2-family multi5 ensemble (R11 BATCH-6/7 ship) overrides
    total_est + spread_est. blowout_prob / first_half / pace stay on the legacy
    single-XGB heads. Result dict gains "ensemble" and "home_pts_est" / "away_pts_est"
    keys when the m2 path fires.

    Args:
        home_team:  Team abbreviation (e.g. 'GSW').
        away_team:  Team abbreviation (e.g. 'BOS').
        season:     NBA season string.
        game_date:  ISO date string for rest/travel context (optional).
        game_id:    NBA game_id, enables the m2_family ensemble override when
                    a featured row is available.

    Returns:
        {
          "home_team":       str,
          "away_team":       str,
          "total_est":       float,   # projected game total
          "spread_est":      float,   # home - away projection
          "blowout_prob":    float,   # P(|margin| > 15)
          "first_half_est":  float,   # projected first-half total
          "pace_est":        float,   # projected game pace (possessions)
          "over_prob_est":   float,   # stub — 0.50 until odds wired in Phase 11
          "confidence":      str,     # "model" | "formula" | "model+m2_family"
          "features":        dict,
          # Added when m2_family fires:
          "ensemble":        str,
          "home_pts_est":    float,
          "away_pts_est":    float,
          "m2_family_used":  bool,
        }
    """
    feats = _build_features(home_team, away_team, season, game_date, ref_names)
    X     = np.array([[feats[c] for c in FEATURE_COLS]], dtype=np.float32)

    try:
        gm = load_models()
        total_est     = round(float(gm.game_total.predict(X)[0]), 1)
        spread_est    = round(float(gm.spread.predict(X)[0]),     1)
        blowout_prob  = round(float(gm.blowout.predict_proba(X)[0][1]), 4)
        first_half    = round(float(gm.first_half.predict(X)[0]), 1)
        pace_est      = round(float(gm.pace.predict(X)[0]), 1)
        confidence    = "model"
    except (FileNotFoundError, Exception):
        # Formula fallback (same as predict_total in game_prediction.py)
        pace_avg      = feats["pace_avg"]
        off_rtg_sum   = feats["off_rtg_sum"]
        def_rtg_sum   = feats["def_rtg_sum"]
        def_factor    = min(1.0, def_rtg_sum / 224.0)
        total_raw     = pace_avg * off_rtg_sum / 100
        total_est     = round(total_raw * def_factor, 1)
        spread_est    = round(feats["net_rtg_diff"] * 0.5, 1)
        blowout_prob  = round(max(abs(spread_est) - 10, 0) / 25, 3)
        first_half    = round(total_est * 0.47, 1)
        pace_est      = round(feats["pace_avg"], 1)
        confidence    = "formula"

    # R20_M7: try m2_family ensemble override (only when a season_games row is
    # available). Never raises — falls back to legacy values on any failure.
    m2_out: Optional[Dict[str, float]] = None
    m2_extras: Dict[str, float] = {}
    try:
        row = _lookup_season_games_row(game_id, home_team, away_team, game_date)
        if row is not None:
            # Prefer the explicit caller-supplied game_id; fall back to the
            # row's own game_id so cache keys stay stable when callers pass
            # (home, away, date) tuples instead of game_id directly.
            gid_for_cache = game_id or row.get("game_id")
            m2_pred = _predict_m2_family(row, game_id=gid_for_cache)
            if m2_pred is not None:
                m2_out = m2_pred
                # Override total + spread with the multi5 ensemble.
                total_est = m2_pred["total_est"]
                spread_est = m2_pred["spread_est"]
                # Recompute the derived blowout_prob from the new spread when
                # we fell back to formula (keep model blowout_prob otherwise).
                if confidence == "formula":
                    blowout_prob = round(max(abs(spread_est) - 10, 0) / 25, 3)
                _ens_label = (
                    "M2_family_mlp_v1_R31_X3 (multitask MLP, 3-seed ensemble)"
                    if _m2_family_use_mlp()
                    else "M2_family_v1 (5 models × 4 targets, equal-weight)"
                )
                m2_extras = {
                    "home_pts_est":  m2_pred["home_pts_est"],
                    "away_pts_est":  m2_pred["away_pts_est"],
                    "ensemble":      _ens_label,
                    "m2_family_used": True,
                }
                confidence = (confidence + "+m2_family") if confidence == "model" else "m2_family"
    except Exception:
        m2_out = None

    result = {
        "home_team":      home_team,
        "away_team":      away_team,
        "total_est":      total_est,
        "spread_est":     spread_est,
        "blowout_prob":   blowout_prob,
        "first_half_est": first_half,
        "pace_est":       pace_est,
        "over_prob_est":  0.50,   # stub — needs odds feed (Phase 11)
        "confidence":     confidence,
        "features":       feats,
    }
    if m2_extras:
        result.update(m2_extras)
    return result


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

    # Ref features
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

    # Rolling L10 features for inference — ONE gamelog call, both teams
    _ROLL_D10 = {"off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0}
    h_roll_inf, a_roll_inf = dict(_ROLL_D10), dict(_ROLL_D10)
    try:
        from nba_api.stats.endpoints import leaguegamelog as _lgl_inf
        time.sleep(0.6)
        _gl_inf = _lgl_inf.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        ).get_data_frames()[0]
        _gl_inf = _gl_inf.copy()
        _gl_inf["_poss"] = (
            _gl_inf["FGA"] + 0.44 * _gl_inf["FTA"] + _gl_inf["TOV"] - _gl_inf["OREB"]
        ).clip(lower=1)
        _gl_inf["_off_r"] = _gl_inf["PTS"] / _gl_inf["_poss"] * 100
        _opp_m: dict = {}
        for _, _r in _gl_inf.iterrows():
            _opp_m.setdefault(str(_r["GAME_ID"]), {})[int(_r["TEAM_ID"])] = float(_r["_off_r"])
        for _team, _roll_out in [(home_team, h_roll_inf), (away_team, a_roll_inf)]:
            _tid = int(abbrev_to_id.get(_team, "0"))
            _tg  = _gl_inf[_gl_inf["TEAM_ID"].astype(int) == _tid].copy()
            if len(_tg) < 3:
                continue
            _tg["_def_r"] = [
                ([v for t, v in _opp_m.get(str(r["GAME_ID"]), {}).items() if t != _tid] or [112.0])[0]
                for _, r in _tg.iterrows()
            ]
            _tg["_dt"] = pd.to_datetime(_tg["GAME_DATE"], errors="coerce")
            _tg = _tg.sort_values("_dt").tail(10)
            _off = round(float(_tg["_off_r"].mean()), 2)
            _de  = round(float(_tg["_def_r"].mean()), 2)
            _roll_out.update({"off_rtg_L10": _off, "def_rtg_L10": _de,
                              "net_rtg_L10": round(_off - _de, 2)})
    except Exception:
        pass

    feats = {
        "home_off_rtg":        ht["off_rtg"],
        "home_def_rtg":        ht["def_rtg"],
        "home_net_rtg":        ht["net_rtg"],
        "home_pace":           ht["pace"],
        "home_efg_pct":        ht["efg_pct"],
        "home_ts_pct":         ht["ts_pct"],
        "home_tov_pct":        ht["tov_pct"],
        "home_rest_days":      h_ctx["rest_days"],
        "home_back_to_back":   h_ctx["back_to_back"],
        "home_last5_wins":     _get_last5_wins(home_team, game_date, season),
        "home_season_win_pct": ht["win_pct"],
        "away_off_rtg":        at["off_rtg"],
        "away_def_rtg":        at["def_rtg"],
        "away_net_rtg":        at["net_rtg"],
        "away_pace":           at["pace"],
        "away_efg_pct":        at["efg_pct"],
        "away_ts_pct":         at["ts_pct"],
        "away_tov_pct":        at["tov_pct"],
        "away_rest_days":      a_ctx["rest_days"],
        "away_back_to_back":   a_ctx["back_to_back"],
        "away_travel_miles":   compute_travel_distance(away_team, home_team),
        "away_last5_wins":     _get_last5_wins(away_team, game_date, season),
        "away_season_win_pct": at["win_pct"],
        "net_rtg_diff":        h_roll_inf["net_rtg_L10"] - a_roll_inf["net_rtg_L10"],
        "pace_diff":           ht["pace"]    - at["pace"],
        "home_advantage":      1.0,
        "pace_avg":            (ht["pace"]    + at["pace"])    / 2,
        "off_rtg_sum":         ht["off_rtg"]  + at["off_rtg"],
        "def_rtg_sum":         ht["def_rtg"]  + at["def_rtg"],
        "efg_sum":             ht["efg_pct"]  + at["efg_pct"],
        "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(home_team, season),
        "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(away_team, season),
        "ref_avg_fouls":       ref_avg_fouls,
        "ref_home_win_pct":    ref_home_win_pct,
        # Rolling L10
        "home_off_rtg_L10":    h_roll_inf["off_rtg_L10"],
        "home_def_rtg_L10":    h_roll_inf["def_rtg_L10"],
        "home_net_rtg_L10":    h_roll_inf["net_rtg_L10"],
        "away_off_rtg_L10":    a_roll_inf["off_rtg_L10"],
        "away_def_rtg_L10":    a_roll_inf["def_rtg_L10"],
        "away_net_rtg_L10":    a_roll_inf["net_rtg_L10"],
    }
    feats.update(_compute_context_signals(feats))
    return feats


def _fetch_scored_games(season: str) -> List[dict]:
    """
    Fetch all regular-season games for one season including actual scores.

    Re-processes leaguegamelog to get home_pts + away_pts for training targets.
    Merges with team season ratings from _fetch_team_stats.

    Targets produced:
        game_total       = home_pts + away_pts
        spread           = home_pts - away_pts
        first_half_proxy = game_total * 0.47 + pace_noise (team-specific)
        game_pace        = realised box-score pace, possessions per 48 min
                           (FGA − OREB + TOV + 0.44·FTA), OT-normalised
    """
    cache_path = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
    if os.path.exists(cache_path):
        age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
        if age_h < 168:  # 7-day TTL (completed seasons don't change)
            with open(cache_path) as f:
                payload = json.load(f)
            # Version check — if v field present and matches, use cache
            if isinstance(payload, dict) and payload.get("v") == _SCORED_GAMES_VERSION:
                return payload["rows"]
            # Legacy list or version mismatch — bust cache
            print(f"  [cache] scored_games_{season}: schema changed, re-fetching...")

    # Fetch game log
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

    # Import helpers from win_probability to avoid duplication
    from src.prediction.win_probability import (
        _fetch_team_stats as _wpts,
        _compute_rest_days,
        _compute_last5_wins,
        _compute_cumulative_win_pct,
        _compute_rolling_team_stats,
        _get_top_lineup_net_rtg,
    )
    from src.features.advanced_features import compute_game_elo_lookup
    team_stats    = _wpts(season)
    rest_lookup   = _compute_rest_days(gl)
    wins5_lookup  = _compute_last5_wins(gl)
    winpct_lookup = _compute_cumulative_win_pct(gl)
    elo_lookup    = compute_game_elo_lookup([season])
    roll_lookup   = _compute_rolling_team_stats(gl, 10)
    _ROLL_D10    = {"off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0}

    _D = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
          "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
          "tov_pct": 13.0, "win_pct": 0.5}

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

        # Skip games with no score (pre-season stubs, postponements)
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
        h_roll  = roll_lookup.get((int(h["TEAM_ID"]), str(gid)), _ROLL_D10)
        a_roll  = roll_lookup.get((int(a["TEAM_ID"]), str(gid)), _ROLL_D10)

        pace_avg = (ht["pace"] + at["pace"]) / 2

        # Realised game pace from the box score; fall back to the season-pace
        # average only when box-score stats are missing (task PRED-01).
        observed_pace = _observed_game_pace(h, a)
        game_pace = observed_pace if observed_pace > 0 else pace_avg

        # first_half_proxy: 0.47 × game_total + small pace-correlated noise.
        # High-pace games tend to have slightly more first-half action (faster early tempo).
        game_total = home_pts + away_pts
        pace_factor = max(0, (pace_avg - 98) / 100) * 0.02  # ±1 pt at pace extremes
        fh_proxy = round(game_total * (0.47 + pace_factor) + rng.normal(0, 1.5), 1)
        fh_proxy = max(fh_proxy, 85.0)  # floor: no NBA first half under 85 pts

        rows.append({
            "game_id":    str(gid),
            "season":     season,
            "game_date":  str(h.get("GAME_DATE", "")),
            "home_team":  h["TEAM_ABBREVIATION"],
            "away_team":  a["TEAM_ABBREVIATION"],
            # Targets
            "game_total":        game_total,
            "spread":            home_pts - away_pts,
            "first_half_proxy":  fh_proxy,
            # Realised game pace from the box score — NOT the season-pace
            # average (that was identical to the pace_avg feature → leakage).
            "game_pace":         game_pace,
            # Features (mirrors win_probability.py FEATURE_COLS + extras)
            "home_off_rtg":        ht["off_rtg"],
            "home_def_rtg":        ht["def_rtg"],
            "home_net_rtg":        ht["net_rtg"],
            "home_pace":           ht["pace"],
            "home_efg_pct":        ht["efg_pct"],
            "home_ts_pct":         ht["ts_pct"],
            "home_tov_pct":        ht["tov_pct"],
            "home_rest_days":      float(h_rest),
            "home_back_to_back":   float(h_rest == 1),
            "home_last5_wins":     float(h_wins5),
            "home_season_win_pct": winpct_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.5),
            "away_off_rtg":        at["off_rtg"],
            "away_def_rtg":        at["def_rtg"],
            "away_net_rtg":        at["net_rtg"],
            "away_pace":           at["pace"],
            "away_efg_pct":        at["efg_pct"],
            "away_ts_pct":         at["ts_pct"],
            "away_tov_pct":        at["tov_pct"],
            "away_rest_days":      float(a_rest),
            "away_back_to_back":   float(a_rest == 1),
            "away_travel_miles":   compute_travel_distance(
                a["TEAM_ABBREVIATION"], h["TEAM_ABBREVIATION"]
            ),
            "away_last5_wins":     float(a_wins5),
            "away_season_win_pct": winpct_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.5),
            "net_rtg_diff":  h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
            "pace_diff":     ht["pace"]    - at["pace"],
            "home_advantage": 1.0,
            "pace_avg":      (ht["pace"] + at["pace"]) / 2,
            "off_rtg_sum":   ht["off_rtg"] + at["off_rtg"],
            "def_rtg_sum":   ht["def_rtg"] + at["def_rtg"],
            "efg_sum":       ht["efg_pct"] + at["efg_pct"],
            # Lineup quality (season-level)
            "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                h["TEAM_ABBREVIATION"], season
            ),
            "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                a["TEAM_ABBREVIATION"], season
            ),
            # Ref crew unknown for historical games — use league averages
            "ref_avg_fouls":    42.0,
            "ref_home_win_pct": 0.5,
            # Rolling L10
            "home_off_rtg_L10":    h_roll["off_rtg_L10"],
            "home_def_rtg_L10":    h_roll["def_rtg_L10"],
            "home_net_rtg_L10":    h_roll["net_rtg_L10"],
            "away_off_rtg_L10":    a_roll["off_rtg_L10"],
            "away_def_rtg_L10":    a_roll["def_rtg_L10"],
            "away_net_rtg_L10":    a_roll["net_rtg_L10"],
            # Context model signals (computed from already-available row fields)
            **_compute_context_signals({
                "net_rtg_diff":      h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
                "home_rest_days":    float(h_rest),
                "away_rest_days":    float(a_rest),
                "away_travel_miles": compute_travel_distance(
                    a["TEAM_ABBREVIATION"], h["TEAM_ABBREVIATION"]
                ),
            }),
            # ELO — point-in-time (snapshot before each game, no leakage)
            "home_elo":          elo_lookup.get(str(gid), {}).get("home_elo", 1500.0),
            "away_elo":          elo_lookup.get(str(gid), {}).get("away_elo", 1500.0),
            "elo_differential":  (
                elo_lookup.get(str(gid), {}).get("home_elo", 1500.0)
                - elo_lookup.get(str(gid), {}).get("away_elo", 1500.0)
            ),
            "elo_pace_interaction": (
                elo_lookup.get(str(gid), {}).get("home_elo", 1500.0) * ht["pace"]
                - elo_lookup.get(str(gid), {}).get("away_elo", 1500.0) * at["pace"]
            ),
            # Star availability — historical injury data not tracked; default 3 (full)
            "home_stars_available": 3,
            "away_stars_available": 3,
        })

    with open(cache_path, "w") as f:
        json.dump({"v": _SCORED_GAMES_VERSION, "rows": rows}, f)
    print(f"  Cached {len(rows)} scored games -> {cache_path}")
    return rows


_CONTEXT_MODELS: dict = {}


def _load_context_models() -> dict:
    """Load context pkl models once per process; cache in module-level dict."""
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
    """
    Derive 5 context-model features from existing feats dict.

    Uses overtime_probability.pkl, rest_day_model.pkl, travel_impact_model.pkl.
    All lookups are graceful — returns defaults on any error.
    """
    import math

    net_diff = float(feats.get("net_rtg_diff", 0.0))

    # 1. win_prob_home: logistic of net_rtg_diff (fast; no extra API calls)
    win_prob_home = 1.0 / (1.0 + math.exp(-0.1 * net_diff))

    ctx = _load_context_models()

    # 2. ot_prob from LR model (single feature: abs net_rtg_diff)
    ot_prob = 0.07
    try:
        lrm = ctx.get("overtime_probability", {}).get("lr_model")
        if lrm is not None:
            ot_prob = float(lrm.predict_proba([[abs(net_diff)]])[0][1])
    except Exception:
        pass

    # 3 & 4. rest factors from rest_day_model ratios
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

    # 5. travel_impact_score: tz-bucket from away_travel_miles
    travel_impact_score = 0.0
    try:
        table = ctx.get("travel_impact_model", {}).get("table", {})
        if table:
            miles = float(feats.get("away_travel_miles", 0.0))
            if miles < 500:
                tz_key = "tz_0"
            elif miles < 1200:
                tz_key = "tz_1"
            elif miles < 2000:
                tz_key = "tz_2"
            else:
                tz_key = "tz_3"
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

    ap = argparse.ArgumentParser(description="Game-level NBA Models")
    ap.add_argument("--train",   action="store_true", help="Train all 5 models")
    ap.add_argument("--predict", nargs=2, metavar=("HOME", "AWAY"))
    ap.add_argument("--season",  default="2024-25")
    ap.add_argument("--seasons", nargs="+", default=["2022-23", "2023-24", "2024-25"])
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
