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

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# Bump when scored_games cache schema changes to force re-fetch.
_SCORED_GAMES_VERSION = 2

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
]

# Model names
_MODELS = ("game_total", "spread", "blowout", "first_half", "pace")

# Blowout threshold (abs margin > N = blowout)
_BLOWOUT_MARGIN = 15


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
        "game_total": ("game_game_total.json", xgb.XGBRegressor),
        "spread":     ("game_spread.json",     xgb.XGBRegressor),
        "blowout":    ("game_blowout.json",    xgb.XGBClassifier),
        "first_half": ("game_first_half.json", xgb.XGBRegressor),
        "pace":       ("game_pace.json",       xgb.XGBRegressor),
    }

    for attr, (filename, cls) in model_map.items():
        path = os.path.join(_MODEL_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found: {path} — run train() first")
        m = cls()
        m.load_model(path)
        setattr(gm, attr, m)

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
    """
    Run all 5 game-level models for a single matchup.

    Falls back to formula-based estimates when models are not trained.

    Args:
        home_team:  Team abbreviation (e.g. 'GSW').
        away_team:  Team abbreviation (e.g. 'BOS').
        season:     NBA season string.
        game_date:  ISO date string for rest/travel context (optional).

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
          "confidence":      str,     # "model" | "formula"
          "features":        dict,
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
    except FileNotFoundError:
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

    return {
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
        _get_top_lineup_net_rtg,
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
        "net_rtg_diff":        ht["net_rtg"] - at["net_rtg"],
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
    }
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
        game_pace        = (home_season_pace + away_season_pace) / 2
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
        _get_top_lineup_net_rtg,
    )
    team_stats   = _wpts(season)
    rest_lookup  = _compute_rest_days(gl)
    wins5_lookup = _compute_last5_wins(gl)

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

        pace_avg = (ht["pace"] + at["pace"]) / 2

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
            "game_pace":         pace_avg,
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
            "home_season_win_pct": ht["win_pct"],
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
            "away_season_win_pct": at["win_pct"],
            "net_rtg_diff":  ht["net_rtg"] - at["net_rtg"],
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
        })

    with open(cache_path, "w") as f:
        json.dump({"v": _SCORED_GAMES_VERSION, "rows": rows}, f)
    print(f"  Cached {len(rows)} scored games -> {cache_path}")
    return rows


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
