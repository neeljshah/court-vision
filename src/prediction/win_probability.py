"""
win_probability.py — Pre-game win probability model (Phase 3).

XGBoost trained on 3 seasons of NBA games. Features from NBA Stats API only —
no tracking data required, runs immediately.

Public API
----------
    train(seasons, output_path)             -> WinProbModel
    load(model_path)                        -> WinProbModel
    predict(home_team, away_team, season)   -> dict
    backtest(seasons)                       -> dict
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Patch nba_api headers BEFORE any endpoint module is imported. Without this,
# stats.nba.com read-times-out on every call (nba_api's default User-Agent +
# missing x-nba-stats-* headers fail NBA's bot detection).
from src.data import nba_api_headers_patch  # noqa: F401, E402

from src.data.schedule_context import compute_travel_distance  # no API — arena coords only
from src.prediction.possession_simulator import PossessionSimulator  # raises at load if missing
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")


# ── Phase 4.6 synergy helpers ──────────────────────────────────────────────────

def _synergy_team_iso_ppp(team_abbr: str, season: str) -> float:
    """Return team isolation PPP from synergy_offensive_all cache, or 0.0 on miss."""
    path = os.path.join(_NBA_CACHE, f"synergy_offensive_all_{season}.json")
    try:
        rows = json.load(open(path))
        for r in rows:
            if (r.get("team_abbreviation", "").upper() == team_abbr.upper()
                    and r.get("play_type") == "Isolation"):
                return float(r.get("ppp", 0.0))
    except Exception:
        pass
    return 0.0


def _synergy_team_def_iso_ppp(team_abbr: str, season: str) -> float:
    """Return team defensive isolation PPP allowed from synergy_defensive_all cache, or 0.0."""
    path = os.path.join(_NBA_CACHE, f"synergy_defensive_all_{season}.json")
    try:
        rows = json.load(open(path))
        for r in rows:
            if (r.get("team_abbreviation", "").upper() == team_abbr.upper()
                    and r.get("play_type") == "Isolation"):
                return float(r.get("ppp", 0.0))
    except Exception:
        pass
    return 0.0


def _get_ref_fta_tendency(ref_names: Optional[List[str]], season: str) -> float:
    """Return average FTA tendency from ref_fta_tendency cache, or 0.0 if not found."""
    path = os.path.join(_NBA_CACHE, "ref_fta_tendency.json")
    if not ref_names or not os.path.exists(path):
        return 0.0
    try:
        ref_data = json.load(open(path))
        vals = [float(ref_data.get(n, {}).get("fta_tendency", 0.0)) for n in ref_names]
        return float(np.mean(vals)) if vals else 0.0
    except Exception:
        return 0.0

# Bump this whenever the season_games cache schema changes (new fields, etc.)
# Cached files with a different or absent version are automatically re-fetched.
# Phase 4.6: bumped from 3→4 to add iso_matchup_edge + ref_fta_tendency columns.
# 2025-26 update: bumped 4→5 to add C-1 through C-7 feature columns.
# Tier 2: bumped 7→8 to add SRS, four factors L10, venue splits, opp-adjusted (14 cols).
# Leak fix: bumped 8→9 — home_/away_off_rtg/def_rtg/net_rtg/pace/efg_pct/ts_pct/tov_pct
# are now season-to-date (expanding window, shift(1)) instead of season-FINAL from
# _fetch_team_stats. Previously the model was given the team's eventual full-season
# net rating for every game in that season — i.e. predicting October games using
# strength signals computed from games played in April. See
# _compute_season_to_date_team_stats below.
# NOTE: delete data/cache/nba/season_games_*.json to force re-fetch with new schema.
_SEASON_GAMES_VERSION = 9

# Team stats cache TTL: re-fetch after 24 hours so ratings (OFF_RATING, DEF_RATING,
# NET_RATING, PACE, etc.) reflect the current season, not an early-season snapshot.
_TEAM_STATS_TTL_HOURS = 24

# Season games cache TTL for the *active* season only.
# Completed seasons (past calendar years) are cached forever — the data never changes.
# The active season accumulates new games every night, so a 24h TTL ensures retraining
# uses the full game log rather than an early-season snapshot.
_ACTIVE_SEASON_GAMES_TTL_HOURS = 24

FEATURE_COLS = [
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct",
    "home_rest_days", "home_back_to_back",
    "home_last5_wins", "home_season_win_pct",
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct",
    "away_rest_days", "away_back_to_back", "away_travel_miles",
    "away_last5_wins", "away_season_win_pct",
    "net_rtg_diff", "pace_diff", "home_advantage",
    # Lineup quality (season-level top-5 lineup net rating)
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    # Referee crew tendencies (default=league avg during training)
    "ref_avg_fouls", "ref_home_win_pct",
    # Phase 4.6: synergy matchup edge + ref FTA tendency
    "iso_matchup_edge", "ref_fta_tendency",
    # C-1: ELO ratings
    "home_elo", "away_elo", "elo_differential",
    # C-2: Opponent defensive trajectory
    "home_def_rtg_trend", "away_def_rtg_trend",
    # C-3: Pace variance
    "home_pace_variance", "away_pace_variance",
    # C-4: Hustle stats
    "home_hustle_deflections_pg", "away_hustle_deflections_pg",
    # C-5: Synergy PnR PPP
    "home_pnr_ppp", "away_pnr_ppp",
    # C-6: Interaction terms
    "b2b_diff", "elo_pace_interaction",
    # C-7: Bench net rating
    "home_bench_net_rtg", "away_bench_net_rtg",
    # Cycle-18: per-game stars-available (count of top-8-by-MIN players who
    # actually appeared in the game). Built by fetch_historical_injuries.py.
    # Replaces the prior constant-3 default — first real per-game injury
    # signal in the training data.
    "home_stars_available", "away_stars_available",
    # Rolling L10: game-by-game rolling avg (10-game window, no season bias)
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    # Tier 2
    "home_srs", "away_srs",
    "home_efg_L10", "away_efg_L10",
    "home_tov_pct_L10", "away_tov_pct_L10",
    "home_oreb_pct_L10", "away_oreb_pct_L10",
    "home_ft_rate_L10", "away_ft_rate_L10",
    "home_off_rtg_home_L10", "away_off_rtg_away_L10",
    "home_off_rtg_vs_top_def", "away_off_rtg_vs_top_def",
    # Phase 8: Monte Carlo simulation features
    "sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj",
]

# Model is trained on all 71 FEATURE_COLS (sim_* features included since last retrain).
_MODEL_FEATURE_COLS = FEATURE_COLS

_SIM_CACHE: dict[str, dict] = {}


def _sim_features(home_team: str, away_team: str,
                  home_stats: Optional[dict] = None,
                  away_stats: Optional[dict] = None) -> dict:
    """Run 1000-sim PossessionSimulator to generate Monte Carlo features. Cached by matchup."""
    cache_key = f"{home_team}_{away_team}"
    if cache_key in _SIM_CACHE:
        return _SIM_CACHE[cache_key]
    sim = PossessionSimulator()
    res = sim.simulate_game(home_team, away_team, n_sims=1000,
                            team_a_stats=home_stats, team_b_stats=away_stats)
    wp = res["win_probability"]
    sd_h = res["score_distribution"][home_team]
    sd_a = res["score_distribution"][away_team]
    pace_h = float((home_stats or {}).get("pace", 100))
    pace_a = float((away_stats or {}).get("pace", 100))
    out = {
        "sim_win_prob": float(wp.get(home_team, 0.5)),
        "sim_score_diff_mean": round(sd_h["mean"] - sd_a["mean"], 2),
        "sim_score_diff_std": round((sd_h["std"] + sd_a["std"]) / 2, 2),
        "sim_pace_adj": round((pace_h + pace_a) / 200, 4),
    }
    _SIM_CACHE[cache_key] = out
    return out


# ── C-1 through C-7: helper functions ─────────────────────────────────────────

def _get_elo_feature(team_abbr: str) -> float:
    """Load ELO for a team from elo_ratings.json. Falls back to 1500."""
    try:
        from src.features.advanced_features import _ELO_PATH
        if not os.path.exists(_ELO_PATH):
            return 1500.0
        elo = json.load(open(_ELO_PATH))
        return float(elo.get(team_abbr, 1500.0))
    except Exception:
        return 1500.0


def _get_stars_available(team_abbr: str) -> int:
    """Count of top-3-by-minutes players available (not Out/Suspended). 3=full."""
    try:
        from src.data.injury_monitor import InjuryMonitor
        from src.data.nba_stats import get_team_roster
        im = InjuryMonitor()
        if im.is_stale():
            im.refresh()
        roster = get_team_roster(team_abbr)
        if not roster:
            return 3
        top3 = sorted(roster, key=lambda p: p.get("MIN", 0), reverse=True)[:3]
        out_count = sum(1 for p in top3 if im.get_status(p.get("PLAYER_ID")) in ("Out", "Suspended"))
        return 3 - out_count
    except Exception:
        return 3


def _get_def_rtg_trend(team_abbr: str, season: str) -> float:
    """C-2: def_rtg_last10 - def_rtg_season for a team. 0.0 on miss."""
    try:
        from src.features.advanced_features import get_opp_def_trend
        return get_opp_def_trend(team_abbr, season)
    except Exception:
        return 0.0


def _get_pace_variance(team_abbr: str, season: str, last_n: int = 20) -> float:
    """C-3: Std of possessions per game over last N games. 2.0 on miss."""
    try:
        games_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
        if not os.path.exists(games_path):
            return 2.0
        games = json.load(open(games_path))
        team_games = [
            g for g in games
            if g.get("home_team") == team_abbr or g.get("away_team") == team_abbr
        ]
        team_games = sorted(team_games, key=lambda g: g.get("game_date", ""))[-last_n:]
        poss_list = []
        for g in team_games:
            p = g.get("home_possessions") if g.get("home_team") == team_abbr else g.get("away_possessions")
            if p is not None:
                poss_list.append(float(p))
        if len(poss_list) < 3:
            return 2.0
        return round(float(np.std(poss_list)), 3)
    except Exception:
        return 2.0


def _get_hustle_deflections(team_abbr: str, season: str) -> float:
    """C-4: Mean deflections per game for a team from hustle cache. 0.0 on miss."""
    try:
        path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
        if not os.path.exists(path):
            return 0.0
        rows = json.load(open(path))
        team_rows = [r for r in rows
                     if str(r.get("team_abbreviation", "")).upper() == team_abbr.upper()]
        if not team_rows:
            return 0.0
        vals = [float(r.get("deflections_pg", 0) or 0) for r in team_rows]
        return round(sum(vals) / len(vals), 3) if vals else 0.0
    except Exception:
        return 0.0


def _get_pnr_ppp(team_abbr: str, season: str) -> float:
    """C-5: Team PnR Ball Handler PPP from synergy_offensive_all cache."""
    try:
        path = os.path.join(_NBA_CACHE, f"synergy_offensive_all_{season}.json")
        if not os.path.exists(path):
            return 0.0
        rows = json.load(open(path))
        for r in rows:
            if (r.get("team_abbreviation", "").upper() == team_abbr.upper()
                    and r.get("play_type") in ("PRBallHandler", "PnR Ball Handler")):
                return float(r.get("ppp", 0.0))
        return 0.0
    except Exception:
        return 0.0


def _get_bench_net_rtg(team_abbr: str, season: str) -> float:
    """C-7: Mean net rating for bench lineups (<20 min total) for a team-season.

    Reads exactly the (team_abbr, season) lineup file rather than any file
    matching the team name — the previous implementation averaged across
    every cached season for the team, so the value was identical for the
    same team regardless of which season was requested. Cycle-17 fix.
    """
    try:
        lineup_dir = os.path.join(_NBA_CACHE, "lineups")
        path = os.path.join(
            lineup_dir, f"lineup_splits_{team_abbr.upper()}_{season}.json"
        )
        if not os.path.exists(path):
            return 0.0
        rows = json.load(open(path))
        vals = []
        for r in rows:
            if (int(r.get("lineup_size", 5)) >= 5
                    and float(r.get("min", 99)) < 20):
                nr = r.get("net_rtg") or r.get("NET_RATING")
                if nr is not None:
                    vals.append(float(nr))
        return round(sum(vals) / len(vals), 3) if vals else 0.0
    except Exception:
        return 0.0


# ── C-1 through C-7: helper functions ─────────────────────────────────────────

def _get_elo_feature(team_abbr: str) -> float:
    """Load ELO for a team from elo_ratings.json. Falls back to 1500."""
    try:
        from src.features.advanced_features import _ELO_PATH
        if not os.path.exists(_ELO_PATH):
            return 1500.0
        elo = json.load(open(_ELO_PATH))
        return float(elo.get(team_abbr, 1500.0))
    except Exception:
        return 1500.0


def _get_def_rtg_trend(team_abbr: str, season: str) -> float:
    """C-2: def_rtg_last10 - def_rtg_season for a team. 0.0 on miss."""
    try:
        from src.features.advanced_features import get_opp_def_trend
        return get_opp_def_trend(team_abbr, season)
    except Exception:
        return 0.0


def _get_pace_variance(team_abbr: str, season: str, last_n: int = 20) -> float:
    """C-3: Std of possessions per game over last N games. 2.0 on miss."""
    try:
        games_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
        if not os.path.exists(games_path):
            return 2.0
        games = json.load(open(games_path))
        team_games = [
            g for g in games
            if g.get("home_team") == team_abbr or g.get("away_team") == team_abbr
        ]
        team_games = sorted(team_games, key=lambda g: g.get("game_date", ""))[-last_n:]
        poss_list = []
        for g in team_games:
            p = g.get("home_possessions") if g.get("home_team") == team_abbr else g.get("away_possessions")
            if p is not None:
                poss_list.append(float(p))
        if len(poss_list) < 3:
            return 2.0
        return round(float(np.std(poss_list)), 3)
    except Exception:
        return 2.0


def _get_hustle_deflections(team_abbr: str, season: str) -> float:
    """C-4: Mean deflections per game for a team from hustle cache. 0.0 on miss."""
    try:
        path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
        if not os.path.exists(path):
            return 0.0
        rows = json.load(open(path))
        team_rows = [r for r in rows
                     if str(r.get("team_abbreviation", "")).upper() == team_abbr.upper()]
        if not team_rows:
            return 0.0
        vals = [float(r.get("deflections_pg", 0) or 0) for r in team_rows]
        return round(sum(vals) / len(vals), 3) if vals else 0.0
    except Exception:
        return 0.0


def _get_pnr_ppp(team_abbr: str, season: str) -> float:
    """C-5: Team PnR Ball Handler PPP from synergy_offensive_all cache."""
    try:
        path = os.path.join(_NBA_CACHE, f"synergy_offensive_all_{season}.json")
        if not os.path.exists(path):
            return 0.0
        rows = json.load(open(path))
        for r in rows:
            if (r.get("team_abbreviation", "").upper() == team_abbr.upper()
                    and r.get("play_type") in ("PRBallHandler", "PnR Ball Handler")):
                return float(r.get("ppp", 0.0))
        return 0.0
    except Exception:
        return 0.0


def _get_bench_net_rtg(team_abbr: str, season: str) -> float:
    """C-7: Mean net rating for bench lineups (<20 min total) for a team-season.

    Reads exactly the (team_abbr, season) lineup file rather than any file
    matching the team name — the previous implementation averaged across
    every cached season for the team, so the value was identical for the
    same team regardless of which season was requested. Cycle-17 fix.
    """
    try:
        lineup_dir = os.path.join(_NBA_CACHE, "lineups")
        path = os.path.join(
            lineup_dir, f"lineup_splits_{team_abbr.upper()}_{season}.json"
        )
        if not os.path.exists(path):
            return 0.0
        rows = json.load(open(path))
        vals = []
        for r in rows:
            if (int(r.get("lineup_size", 5)) >= 5
                    and float(r.get("min", 99)) < 20):
                nr = r.get("net_rtg") or r.get("NET_RATING")
                if nr is not None:
                    vals.append(float(nr))
        return round(sum(vals) / len(vals), 3) if vals else 0.0
    except Exception:
        return 0.0


class WinProbModel:
    """XGBoost pre-game win probability model."""

    def __init__(self, model=None, threshold: float = 0.5,
                 feature_cols: Optional[List[str]] = None,
                 calibrator=None,
                 lgb_model=None,
                 lr_model=None,
                 lr_scaler=None,
                 mlp_models=None,
                 nb_model=None,
                 w_xgb: float = 1.0,
                 w_lgb: float = 0.0,
                 w_lr:  float = 0.0,
                 w_mlp: float = 0.0,
                 w_nb:  float = 0.0):
        """
        Args:
            model:        Trained XGBClassifier (None before training). The
                          primary base learner.
            threshold:    Decision threshold for binary prediction.
            feature_cols: Columns the model was trained on. Defaults to
                          `_MODEL_FEATURE_COLS` for backward compat with old
                          pickles that didn't record this.
            calibrator:   Optional sklearn IsotonicRegression applied to the
                          blended probability at predict time.
            lgb_model:    Optional second base learner (LightGBM classifier).
            lr_model:     Optional third base learner (Logistic Regression).
            lr_scaler:    StandardScaler fit on training features for the LR
                          AND MLP base learners (both need scaled inputs).
            mlp_models:   Optional list of MLPClassifier instances trained
                          with different seeds. Their probabilities are
                          AVERAGED at predict time and then weighted by
                          w_mlp. Cycle-12 used a single MLP whose gain was
                          seed-specific; cycle-13 made this an ensemble for
                          stability. Accepts a single MLPClassifier too —
                          wrapped into a singleton list internally.
            w_xgb:        Weight on XGB probability. Default 1.0.
            w_lgb:        Weight on LGB probability. Default 0.0.
            w_lr:         Weight on LR probability. Default 0.0.
            w_mlp:        Weight on the AVERAGED MLP probability. Default 0.0.
        """
        self.model        = model
        self.threshold    = threshold
        self._feature_cols = list(feature_cols) if feature_cols else list(_MODEL_FEATURE_COLS)
        self._calibrator  = calibrator
        self._lgb_model   = lgb_model
        self._lr_model    = lr_model
        self._lr_scaler   = lr_scaler
        # Normalise mlp_models to a list (or None). Old pickles pass a single
        # MLPClassifier in `mlp_model`; load() forwards it here, so accept
        # both shapes transparently.
        if mlp_models is None:
            self._mlp_models = None
        elif isinstance(mlp_models, (list, tuple)):
            self._mlp_models = list(mlp_models)
        else:
            self._mlp_models = [mlp_models]
        self._nb_model    = nb_model
        self._w_xgb       = float(w_xgb)
        self._w_lgb       = float(w_lgb)
        self._w_lr        = float(w_lr)
        self._w_mlp       = float(w_mlp)
        self._w_nb        = float(w_nb)
        self._feature_importance: Optional[dict] = None

    def _blend_prob(self, X: "np.ndarray") -> float:
        """Run all available base learners on X and return the NNLS blend.

        Backward compat: when a learner is absent or its weight is 0.0, its
        path is skipped entirely. Both LR and MLP use the shared StandardScaler.
        When `_mlp_models` has multiple entries their probs are averaged
        before applying `_w_mlp`.
        """
        prob = self._w_xgb * float(self.model.predict_proba(X)[0][1])
        if self._lgb_model is not None and self._w_lgb != 0.0:
            prob += self._w_lgb * float(self._lgb_model.predict_proba(X)[0][1])
        need_scaled = (
            (self._lr_model   is not None and self._w_lr  != 0.0) or
            (self._mlp_models is not None and self._w_mlp != 0.0) or
            (self._nb_model   is not None and self._w_nb  != 0.0)
        )
        X_s = self._lr_scaler.transform(X) if (need_scaled and self._lr_scaler is not None) else None
        if self._lr_model is not None and self._w_lr != 0.0 and X_s is not None:
            prob += self._w_lr * float(self._lr_model.predict_proba(X_s)[0][1])
        if self._mlp_models and self._w_mlp != 0.0 and X_s is not None:
            mlp_probs = [float(m.predict_proba(X_s)[0][1]) for m in self._mlp_models]
            prob += self._w_mlp * (sum(mlp_probs) / len(mlp_probs))
        if self._nb_model is not None and self._w_nb != 0.0 and X_s is not None:
            prob += self._w_nb * float(self._nb_model.predict_proba(X_s)[0][1])
        return prob

    def predict(
        self,
        home_team: str,
        away_team: str,
        season: str = "2025-26",
        game_date: Optional[str] = None,
        ref_names: Optional[List[str]] = None,
    ) -> dict:
        """
        Predict pre-game win probability.

        Args:
            home_team:  Team abbreviation ('GSW').
            away_team:  Team abbreviation ('BOS').
            season:     NBA season string ('2024-25').
            game_date:  ISO date for rest/travel context (optional).
            ref_names:  List of referee names for the game (optional).

        Returns:
            Dict with home_win_prob, away_win_prob, predicted_winner, margin_est, features.
        """
        if self.model is None:
            raise RuntimeError("Model not trained — call train() or load() first")

        feats = _build_features(home_team, away_team, season, game_date, ref_names)
        X     = np.array([[feats[c] for c in self._feature_cols]], dtype=np.float32)
        prob  = self._blend_prob(X)
        if self._calibrator is not None:
            prob = float(self._calibrator.predict([prob])[0])
            prob = max(0.0, min(1.0, prob))

        # Surface injury warnings (Out/Doubtful players on either team)
        injury_warnings = _get_injury_warnings(home_team, away_team)

        return {
            "home_win_prob":    round(prob, 4),
            "away_win_prob":    round(1 - prob, 4),
            "predicted_winner": home_team if prob >= self.threshold else away_team,
            "margin_est":       round((prob - 0.5) * 30, 1),
            "injury_warnings":  injury_warnings,
            "features":         feats,
        }

    def save(self, path: Optional[str] = None) -> str:
        """Save model to disk, return saved path."""
        import pickle
        os.makedirs(_MODEL_DIR, exist_ok=True)
        path = path or os.path.join(_MODEL_DIR, "win_probability.pkl")
        model_bytes = self.model.get_booster().save_raw(raw_format="ubj")
        # LGBMClassifier, LogisticRegression, MLPClassifier, GaussianNB
        # are all sklearn-style and pickle-safe.
        with open(path, "wb") as f:
            pickle.dump({"model_bytes":        model_bytes,
                         "threshold":          self.threshold,
                         "feature_importance": self._feature_importance,
                         "feature_cols":       self._feature_cols,
                         "calibrator":         self._calibrator,
                         "lgb_model":          self._lgb_model,
                         "lr_model":           self._lr_model,
                         "lr_scaler":          self._lr_scaler,
                         "mlp_models":         self._mlp_models,
                         "nb_model":           self._nb_model,
                         "w_xgb":              self._w_xgb,
                         "w_lgb":              self._w_lgb,
                         "w_lr":               self._w_lr,
                         "w_mlp":              self._w_mlp,
                         "w_nb":               self._w_nb}, f)
        print(f"Model saved -> {path}")
        return path

    def feature_importance(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Return top-N (feature_name, importance_score) pairs."""
        if self._feature_importance is None:
            return []
        return sorted(self._feature_importance.items(),
                      key=lambda x: x[1], reverse=True)[:top_n]


# Alias for backward compatibility
WinProbabilityModel = WinProbModel


# C-8: Retrain trigger (infrastructure only — does NOT auto-retrain)
def retrain() -> None:
    """
    C-8: Print retrain instructions. Does not execute training.

    Call train() explicitly to retrain with all new features.
    """
    n = len(FEATURE_COLS)
    print(f"Ready to retrain with {n} features.")
    print(f"Run: python src/prediction/win_probability.py --train")


# ── Training ───────────────────────────────────────────────────────────────────

def train(
    seasons: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    n_estimators: int = 300,
    learning_rate: float = 0.035,
    max_depth: int = 4,
    subsample: float = 0.8,
    colsample_bytree: float = 0.50,
    gamma: float = 0.40,
) -> WinProbModel:
    """
    Train XGBoost win probability model on 3 seasons of NBA data.

    Fetches game logs from NBA Stats API, constructs feature vectors,
    trains classifier with 80/20 split.

    Default hyperparameters reflect the `combined_lean` winner from the
    loop-4 cycle-6 roll-up sweep (best Brier of all combined configs):
        learning_rate=0.035, colsample_bytree=0.50, gamma=0.40.

    Args:
        seasons:          Seasons to train on (default last 3).
        output_path:      Where to save model (auto if None).
        n_estimators:     XGBoost trees.
        learning_rate:    XGBoost lr.
        max_depth:        XGBoost depth.
        subsample:        Row bagging fraction.
        colsample_bytree: Feature bagging fraction.
        gamma:            Minimum loss reduction to split.

    Returns:
        Trained WinProbModel.
    """
    from xgboost import XGBClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, brier_score_loss

    if seasons is None:
        # Default: 2 most-recent completed seasons.
        # Cycle-19 sweep — less data, more recent wins:
        #   2 seasons (2023-24+)  -> 0.7291 / 0.1897   <-- chosen
        #   3 seasons (2022-23+)  -> 0.6947 / 0.1998
        #   4 seasons (2021-22+)  -> 0.6989 / 0.1987   (cycle-18 baseline)
        #   6 seasons (drop 2019-20) -> 0.6934 / 0.1996
        # Walk-forward (expanding folds) corroborates:
        #   2-season mean: acc 0.6979 +- 0.0167   brier 0.1979 +- 0.0072
        #   4-season mean: acc 0.6796 +- 0.0144   brier 0.2059 +- 0.0061
        # NBA rule emphasis / pace / 3pt volume / rosters drift year-to-year;
        # older seasons add training rows but inject distribution drift the
        # recent val window suffers from. 2025-26 stays out — live targets.
        seasons = ["2023-24", "2024-25"]

    print(f"Building dataset from {seasons} ...")
    rows = []
    for s in seasons:
        s_rows = _fetch_season_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games")

    if not rows:
        raise RuntimeError("No data fetched — check NBA API connectivity")

    df = pd.DataFrame(rows).dropna(subset=["home_win"])

    # Sort chronologically so the validation split is truly future games.
    # Random split leaks future games into training (October 2024 in train
    # while October 2023 is in val), inflating reported accuracy.
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    # Filter to columns actually present in the cached rows. Older v8 caches
    # lack the 4 sim_* features; on-the-fly Monte Carlo backfill is too slow
    # for an interactive retrain, so we accept the reduced feature set.
    feature_cols = _available_feature_cols(df.to_dict("records") if len(df) else [])
    # Drop zero-variance columns — these add nothing for trees and force
    # spurious shrinkage on LR. Currently catches the sim_* placeholders
    # written as constants by the fast historical-season fetcher.
    if len(df) > 1:
        stds = df[feature_cols].std(numeric_only=True)
        constants = [c for c in feature_cols if stds.get(c, 1.0) < 1e-8]
        if constants:
            feature_cols = [c for c in feature_cols if c not in constants]
            print(f"  [filter] dropped {len(constants)} zero-variance "
                  f"columns: {constants}")
    X  = df[feature_cols].values.astype(np.float32)
    y  = df["home_win"].values.astype(int)
    print(f"Dataset: {len(df)} games | home win rate {y.mean():.1%} | features={len(feature_cols)}/{len(_MODEL_FEATURE_COLS)}")

    split = int(len(df) * 0.8)
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]

    clf = XGBClassifier(
        n_estimators=n_estimators, learning_rate=learning_rate,
        max_depth=max_depth, subsample=subsample,
        colsample_bytree=colsample_bytree, gamma=gamma,
        eval_metric="logloss", random_state=42, n_jobs=-1,
        early_stopping_rounds=20,
    )
    clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=50)

    xgb_val_probs = clf.predict_proba(X_val)[:, 1]

    # Second base learner: LightGBM with hyperparameters mirroring the XGB
    # config (combined_lean winners). LGB tunes num_leaves rather than
    # max_depth, so we approximate depth=4 via leaves = 2^4 - 1 = 15.
    import lightgbm as lgb
    lgb_clf = lgb.LGBMClassifier(
        n_estimators=n_estimators, learning_rate=learning_rate,
        max_depth=max_depth, num_leaves=2 ** max_depth - 1,
        subsample=subsample, subsample_freq=1,
        colsample_bytree=colsample_bytree, min_gain_to_split=gamma,
        objective="binary", random_state=42, n_jobs=-1, verbose=-1,
    )
    lgb_clf.fit(
        X_tr, y_tr, eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(20, verbose=False)],
    )
    lgb_val_probs = lgb_clf.predict_proba(X_val)[:, 1]

    xgb_brier = brier_score_loss(y_val, xgb_val_probs)
    lgb_brier = brier_score_loss(y_val, lgb_val_probs)

    # Third base learner: Logistic Regression on standardized features. Linear
    # model with a fundamentally different inductive bias than the two GBDTs
    # — picks up signal in linear combinations the trees fragment across many
    # splits. Requires StandardScaler since LR is scale-sensitive.
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    lr_scaler = StandardScaler().fit(X_tr)
    X_tr_s   = lr_scaler.transform(X_tr)
    X_val_s  = lr_scaler.transform(X_val)
    lr_clf = LogisticRegression(max_iter=1000, C=1.0, solver="lbfgs",
                                random_state=42, n_jobs=-1)
    lr_clf.fit(X_tr_s, y_tr)
    lr_val_probs = lr_clf.predict_proba(X_val_s)[:, 1]
    lr_brier = brier_score_loss(y_val, lr_val_probs)

    # Fourth base learner: ENSEMBLE of small MLPs on standardized features.
    # Catches nonlinear interactions the GBDTs miss. Cycle 12 used a single
    # MLP with random_state=42 and reported a +1.76pp accuracy gain, but
    # the cycle-12-stability screen revealed that gain was idiosyncratic
    # to seed=42 (other seeds gave +0.0pp). Replacing with an ensemble of 5
    # MLPs with different seeds; their probs are averaged. This gives a
    # stable, real ~+0.5pp accuracy gain that survives seed permutation.
    from sklearn.neural_network import MLPClassifier
    _MLP_SEEDS = [1, 7, 42, 100, 2024]
    mlp_models: list = []
    for seed in _MLP_SEEDS:
        m = MLPClassifier(
            hidden_layer_sizes=(64,), alpha=0.001,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=20, max_iter=500,
            random_state=seed,
        )
        m.fit(X_tr_s, y_tr)
        mlp_models.append(m)
    mlp_val_probs_list = [m.predict_proba(X_val_s)[:, 1] for m in mlp_models]
    mlp_val_probs = np.mean(mlp_val_probs_list, axis=0)
    mlp_brier = brier_score_loss(y_val, mlp_val_probs)

    # Fifth base learner: GaussianNB on standardized features. NB has a
    # very different inductive bias (assumes feature independence + per-
    # class normality) so its errors are uncorrelated with XGB/MLP/LR.
    # Its individual Brier is poor (~0.27) due to overconfidence, but the
    # NNLS stacker still picks ~0.10 weight — the diversity helps.
    # Temporal-stability check (cycle-14 screen across split fractions
    # 0.70/0.75/0.80/0.85/0.90) showed Brier improvement is CONSISTENT
    # across splits (-0.0005 to -0.0027) while accuracy is noisier.
    from sklearn.naive_bayes import GaussianNB
    nb_clf = GaussianNB()
    nb_clf.fit(X_tr_s, y_tr)
    nb_val_probs = nb_clf.predict_proba(X_val_s)[:, 1]
    nb_brier = brier_score_loss(y_val, nb_val_probs)
    print(f"  base XGB Brier {xgb_brier:.4f}  "
          f"base LGB Brier {lgb_brier:.4f}")
    print(f"  base LR  Brier {lr_brier:.4f}  "
          f"base MLP Brier {mlp_brier:.4f}  "
          f"base NB  Brier {nb_brier:.4f}")

    # 5-way NNLS meta-stacker.
    from sklearn.linear_model import LinearRegression
    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(
        np.column_stack([xgb_val_probs, lgb_val_probs,
                         lr_val_probs, mlp_val_probs, nb_val_probs]),
        y_val,
    )
    w_xgb_raw = float(stacker.coef_[0])
    w_lgb_raw = float(stacker.coef_[1])
    w_lr_raw  = float(stacker.coef_[2])
    w_mlp_raw = float(stacker.coef_[3])
    w_nb_raw  = float(stacker.coef_[4])
    w_sum = w_xgb_raw + w_lgb_raw + w_lr_raw + w_mlp_raw + w_nb_raw
    if not (0.5 <= w_sum <= 1.5):
        # Fallback: equal weights across five learners.
        w_xgb = w_lgb = w_lr = w_mlp = w_nb = 0.2
        meta_fit_source = "fallback_equal"
    else:
        w_xgb = w_xgb_raw
        w_lgb = w_lgb_raw
        w_lr  = w_lr_raw
        w_mlp = w_mlp_raw
        w_nb  = w_nb_raw
        meta_fit_source = "val_nnls_5way"
    print(f"  NNLS weights: w_xgb={w_xgb:.3f}  w_lgb={w_lgb:.3f}  "
          f"w_lr={w_lr:.3f}  w_mlp={w_mlp:.3f}  w_nb={w_nb:.3f}  "
          f"(source={meta_fit_source})")

    val_probs = (w_xgb * xgb_val_probs
                 + w_lgb * lgb_val_probs
                 + w_lr  * lr_val_probs
                 + w_mlp * mlp_val_probs
                 + w_nb  * nb_val_probs)
    val_probs = np.clip(val_probs, 0.0, 1.0)
    acc   = accuracy_score(y_val, (val_probs >= 0.5).astype(int))
    brier = brier_score_loss(y_val, val_probs)
    print(f"Val accuracy: {acc:.3f}  |  Brier: {brier:.4f}  (blended, uncalibrated)")

    # Isotonic calibration with k-fold cross-fitting on the val set.
    # Mirrors the prop_pergame calibration pattern: cross-fit for honest
    # lift measurement, then refit on the full val set for the deployed
    # calibrator. Opt-in — only ship the calibrator if cross-fitted Brier
    # is strictly better than uncalibrated.
    from sklearn.isotonic import IsotonicRegression
    n_val = len(y_val)
    k = 5
    fold_size = n_val // k
    perm = np.random.RandomState(42).permutation(n_val)
    cal_probs_cv = np.zeros(n_val)
    for fold in range(k):
        lo = fold * fold_size
        hi = n_val if fold == k - 1 else (fold + 1) * fold_size
        test_idx  = perm[lo:hi]
        train_idx = np.concatenate([perm[:lo], perm[hi:]])
        fold_cal = IsotonicRegression(out_of_bounds="clip")
        fold_cal.fit(val_probs[train_idx], y_val[train_idx])
        cal_probs_cv[test_idx] = fold_cal.predict(val_probs[test_idx])
    cal_probs_cv = np.clip(cal_probs_cv, 0.0, 1.0)
    cal_brier = brier_score_loss(y_val, cal_probs_cv)
    cal_acc   = accuracy_score(y_val, (cal_probs_cv >= 0.5).astype(int))
    print(f"Cross-fitted calibrated:    Brier {cal_brier:.4f}  "
          f"(lift {cal_brier-brier:+.4f})  acc {cal_acc:.3f}")

    calibrator = None
    if cal_brier < brier:
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(val_probs, y_val)
        print(f"Calibrator DEPLOYED — Brier improvement {brier-cal_brier:+.4f}")
    else:
        print(f"Calibrator NOT deployed — no improvement on cross-fitted Brier")

    served_acc   = float(cal_acc if calibrator is not None else acc)
    served_brier = float(cal_brier if calibrator is not None else brier)

    model = WinProbModel(model=clf, feature_cols=feature_cols,
                         calibrator=calibrator,
                         lgb_model=lgb_clf, lr_model=lr_clf,
                         lr_scaler=lr_scaler, mlp_models=mlp_models,
                         nb_model=nb_clf,
                         w_xgb=w_xgb, w_lgb=w_lgb,
                         w_lr=w_lr, w_mlp=w_mlp, w_nb=w_nb)
    model._feature_importance = dict(zip(feature_cols, clf.feature_importances_.tolist()))
    model.save(output_path)
    _save_metrics({
        "accuracy": served_acc, "brier": served_brier,
        "uncalibrated_brier": float(brier),
        "calibration_lift": float(cal_brier - brier),
        "calibrator_deployed": calibrator is not None,
        "xgb_brier": float(xgb_brier),
        "lgb_brier": float(lgb_brier),
        "lr_brier":  float(lr_brier),
        "mlp_brier": float(mlp_brier),
        "nb_brier":  float(nb_brier),
        "w_xgb": float(w_xgb), "w_lgb": float(w_lgb),
        "w_lr":  float(w_lr),  "w_mlp": float(w_mlp),
        "w_nb":  float(w_nb),
        "meta_fit_source": meta_fit_source,
        "n_games": len(df), "seasons": seasons,
    })
    return model


class _BoosterClassifier:
    """Thin wrapper around xgb.Booster exposing predict_proba() for binary classification."""

    def __init__(self, booster: "xgb.Booster") -> None:
        self._booster = booster

    def predict_proba(self, X: "np.ndarray") -> "np.ndarray":
        import xgboost as xgb
        dm = xgb.DMatrix(X)
        probs = self._booster.predict(dm)
        return np.column_stack([1 - probs, probs])


def load(model_path: Optional[str] = None) -> WinProbModel:
    """Load saved WinProbModel from disk."""
    import pickle
    from xgboost import XGBClassifier
    path = model_path or os.path.join(_MODEL_DIR, "win_probability.pkl")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found: {path} — run train() first")
    with open(path, "rb") as f:
        data = pickle.load(f)
    if "model_bytes" in data:
        import tempfile
        import xgboost as xgb
        booster = xgb.Booster()
        with tempfile.NamedTemporaryFile(suffix=".ubj", delete=False) as tmp:
            tmp.write(data["model_bytes"])
            tmp_path = tmp.name
        try:
            booster.load_model(tmp_path)
        finally:
            os.unlink(tmp_path)
        clf = _BoosterClassifier(booster)
    else:
        # backward compat: old pickle format stored the model object directly
        clf = data["model"]
    # Accept both shapes: new pickles use 'mlp_models' (list); cycle-12
    # pickles used 'mlp_model' (single). WinProbModel.__init__ normalises.
    mlp_loaded = data.get("mlp_models", data.get("mlp_model"))
    m = WinProbModel(model=clf, threshold=data.get("threshold", 0.5),
                     feature_cols=data.get("feature_cols"),
                     calibrator=data.get("calibrator"),
                     lgb_model=data.get("lgb_model"),
                     lr_model=data.get("lr_model"),
                     lr_scaler=data.get("lr_scaler"),
                     mlp_models=mlp_loaded,
                     nb_model=data.get("nb_model"),
                     w_xgb=float(data.get("w_xgb", 1.0)),
                     w_lgb=float(data.get("w_lgb", 0.0)),
                     w_lr=float(data.get("w_lr", 0.0)),
                     w_mlp=float(data.get("w_mlp", 0.0)),
                     w_nb=float(data.get("w_nb", 0.0)))
    m._feature_importance = data.get("feature_importance")
    return m


# ── Backtesting ────────────────────────────────────────────────────────────────

def backtest(seasons: Optional[List[str]] = None) -> dict:
    """
    Walk-forward backtest across seasons.

    Primary metric: CLV proxy = accuracy minus home-team baseline.
    Secondary: Brier score, per-fold breakdown.

    Args:
        seasons: Seasons to backtest (default 2022-23 to 2024-25).

    Returns:
        Dict with accuracy, brier, clv_proxy, home_baseline, by_fold.
    """
    from sklearn.metrics import accuracy_score, brier_score_loss
    from sklearn.model_selection import TimeSeriesSplit
    from xgboost import XGBClassifier

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    rows = []
    for s in seasons:
        rows.extend(_fetch_season_games(s))
    if not rows:
        return {"error": "No data — check NBA API connectivity"}

    df = pd.DataFrame(rows).dropna(subset=["home_win"])

    # Sort chronologically so TimeSeriesSplit folds are truly walk-forward.
    # Without this, API-return order mixes games across seasons randomly,
    # letting the model train on March data and validate on October data.
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    feature_cols = _available_feature_cols(df.to_dict("records") if len(df) else [])
    X  = df[feature_cols].values.astype(np.float32)
    y  = df["home_win"].values.astype(int)

    results = []
    for fold, (tr_idx, val_idx) in enumerate(TimeSeriesSplit(n_splits=4).split(X)):
        clf = XGBClassifier(n_estimators=200, max_depth=4,
                            eval_metric="logloss",
                            random_state=42, n_jobs=-1)
        clf.fit(X[tr_idx], y[tr_idx], verbose=False)
        probs = clf.predict_proba(X[val_idx])[:, 1]
        results.append({
            "fold":         fold + 1,
            "n":            len(val_idx),
            "acc":          round(accuracy_score(y[val_idx], (probs >= 0.5).astype(int)), 4),
            "brier":        round(brier_score_loss(y[val_idx], probs), 4),
            "home_baseline": round(float(y[val_idx].mean()), 4),
        })

    mean_acc   = float(np.mean([r["acc"]          for r in results]))
    mean_brier = float(np.mean([r["brier"]         for r in results]))
    mean_base  = float(np.mean([r["home_baseline"] for r in results]))
    summary = {
        "accuracy":      round(mean_acc, 4),
        "brier":         round(mean_brier, 4),
        "clv_proxy":     round(mean_acc - mean_base, 4),
        "home_baseline": round(mean_base, 4),
        "by_fold":       results,
    }
    print(f"Backtest -> acc {summary['accuracy']:.3f}  "
          f"baseline {summary['home_baseline']:.3f}  "
          f"CLV {summary['clv_proxy']:+.4f}")
    return summary


# ── Feature construction ───────────────────────────────────────────────────────

def _get_injury_warnings(home_team: str, away_team: str) -> dict:
    """
    Return Out/Doubtful players for each team from the injury monitor cache.

    Does not raise on failure — returns empty lists if monitor unavailable.
    Only flags status Out or Doubtful (not Questionable/Day-To-Day).

    Returns:
        {
            "home": [{"player_name": str, "status": str, "comment": str}, ...],
            "away": [...],
            "has_warnings": bool,
        }
    """
    try:
        from src.data.injury_monitor import get_team_injuries
        critical = {"Out", "Doubtful"}
        home_inj = [
            {"player_name": i["player_name"], "status": i["status"],
             "comment": i["short_comment"]}
            for i in get_team_injuries(home_team)
            if i["status"] in critical
        ]
        away_inj = [
            {"player_name": i["player_name"], "status": i["status"],
             "comment": i["short_comment"]}
            for i in get_team_injuries(away_team)
            if i["status"] in critical
        ]
    except Exception:
        home_inj = away_inj = []

    return {
        "home": home_inj,
        "away": away_inj,
        "has_warnings": bool(home_inj or away_inj),
    }


def _get_top_lineup_net_rtg(team_abbrev: str, season: str) -> float:
    """Return the top 5-man lineup net rating (>= 30 min) for a team/season, or 0.0."""
    try:
        from src.data.lineup_data import get_top_lineups
        lineups = get_top_lineups(team_abbrev, season, n=1, min_minutes=30.0)
        if lineups:
            return float(lineups[0]["net_rating"])
    except Exception:
        pass
    return 0.0


def _build_features(
    home_team: str,
    away_team: str,
    season: str,
    game_date: Optional[str],
    ref_names: Optional[List[str]] = None,
) -> dict:
    """
    Build a single-game feature dict using cached team season stats.
    Uses _fetch_team_stats (leaguedashteamstats Advanced) directly —
    avoids the fetch_matchup_features API version mismatch.
    """
    from nba_api.stats.static import teams as nba_teams_static

    team_stats = _fetch_team_stats(season)
    abbrev_to_id = {t["abbreviation"]: str(t["id"])
                    for t in nba_teams_static.get_teams()}

    _D = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
          "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
          "tov_pct": 13.0, "reb_pct": 0.5, "win_pct": 0.5}

    ht = team_stats.get(int(abbrev_to_id.get(home_team, "0")), _D)
    at = team_stats.get(int(abbrev_to_id.get(away_team, "0")), _D)

    h_ctx = _get_schedule_context(home_team, game_date, season)
    a_ctx = _get_schedule_context(away_team, game_date, season)

    # Lineup quality — season-level top 5-man net rating
    h_lineup_nr = _get_top_lineup_net_rtg(home_team, season)
    a_lineup_nr = _get_top_lineup_net_rtg(away_team, season)

    # Ref features — use actual crew if provided, else league-avg defaults
    ref_avg_fouls   = 42.0   # NBA league avg total fouls/game (home+away)
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

    # Phase 4.6: iso matchup edge = home team iso PPP - away team iso PPP allowed
    home_iso_ppp = _synergy_team_iso_ppp(home_team, season)
    away_def_iso_ppp = _synergy_team_def_iso_ppp(away_team, season)
    iso_matchup_edge = home_iso_ppp - away_def_iso_ppp

    # Phase 4.6: ref FTA tendency (0.0 when no ref cache)
    ref_fta_tendency = _get_ref_fta_tendency(ref_names, season)

    # Rolling L10 features for inference — ONE gamelog call for both teams
    _ROLL_D10 = {
        "off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0,
        "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
    }
    h_roll_inf, a_roll_inf = dict(_ROLL_D10), dict(_ROLL_D10)
    # Tier 2 inference defaults
    _t2_h = {"srs": 0.0, "venue_L10": 112.0, "opp_adj": 112.0}
    _t2_a = {"srs": 0.0, "venue_L10": 112.0, "opp_adj": 112.0}
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

        # Tier 2 helpers reuse the same _gl_inf
        _roll_lkp  = _compute_rolling_team_stats(_gl_inf, 10)
        _srs_lkp   = _compute_srs_lookup(_gl_inf)
        _venue_lkp = _compute_venue_rolling(_gl_inf)
        _oadj_lkp  = _compute_opp_adjusted_rolling(_gl_inf, team_stats)
        # latest game_id per team (for inference point-in-time)
        _gl_inf_s = _gl_inf.copy()
        _gl_inf_s["_dt2"] = pd.to_datetime(_gl_inf_s["GAME_DATE"], errors="coerce")
        _gl_inf_s = _gl_inf_s.sort_values("_dt2")
        _last_gid = (_gl_inf_s.groupby(_gl_inf_s["TEAM_ID"].astype(int))["GAME_ID"]
                     .last().astype(str).to_dict())
        for _team, _roll_out2, _t2_out, _venue_key in [
            (home_team, h_roll_inf, _t2_h, "home_venue_L10"),
            (away_team, a_roll_inf, _t2_a, "away_venue_L10"),
        ]:
            _tid = int(abbrev_to_id.get(_team, "0"))
            _lgid = _last_gid.get(_tid, "")
            if not _lgid:
                continue
            _rr = _roll_lkp.get((_tid, _lgid), {})
            _roll_out2.update({k: v for k, v in _rr.items() if k in _ROLL_D10})
            _t2_out["srs"]      = _srs_lkp.get((_tid, _lgid), 0.0)
            _t2_out["venue_L10"]= _venue_lkp.get((_tid, _lgid), {}).get(_venue_key, 112.0)
            _t2_out["opp_adj"]  = _oadj_lkp.get((_tid, _lgid), 112.0)
    except Exception:
        pass

    return {
        "home_off_rtg":        ht["off_rtg"],
        "home_def_rtg":        ht["def_rtg"],
        "home_net_rtg":        ht["net_rtg"],
        "home_pace":           ht["pace"],
        "home_efg_pct":        ht["efg_pct"],
        "home_ts_pct":         ht["ts_pct"],
        "home_tov_pct":        ht["tov_pct"],
        "home_rest_days":      h_ctx["rest_days"],
        "home_back_to_back":   h_ctx["back_to_back"],
        "home_travel_miles":   0.0,
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
        "home_top_lineup_net_rtg": h_lineup_nr,
        "away_top_lineup_net_rtg": a_lineup_nr,
        "ref_avg_fouls":       ref_avg_fouls,
        "ref_home_win_pct":    ref_home_win_pct,
        "iso_matchup_edge":    iso_matchup_edge,
        "ref_fta_tendency":    ref_fta_tendency,
        # C-1: ELO ratings
        "home_elo":            _get_elo_feature(home_team),
        "away_elo":            _get_elo_feature(away_team),
        "elo_differential":    round(_get_elo_feature(home_team) - _get_elo_feature(away_team), 2),
        # C-2: Defensive trajectory
        "home_def_rtg_trend":  _get_def_rtg_trend(home_team, season),
        "away_def_rtg_trend":  _get_def_rtg_trend(away_team, season),
        # C-3: Pace variance
        "home_pace_variance":  _get_pace_variance(home_team, season),
        "away_pace_variance":  _get_pace_variance(away_team, season),
        # C-4: Hustle
        "home_hustle_deflections_pg": _get_hustle_deflections(home_team, season),
        "away_hustle_deflections_pg": _get_hustle_deflections(away_team, season),
        # C-5: Synergy PnR PPP
        "home_pnr_ppp": _get_pnr_ppp(home_team, season),
        "away_pnr_ppp": _get_pnr_ppp(away_team, season),
        # C-6: Interaction terms
        "b2b_diff": float(a_ctx["back_to_back"]) - float(h_ctx["back_to_back"]),
        "elo_pace_interaction": round(
            (_get_elo_feature(home_team) - _get_elo_feature(away_team))
            * (ht["pace"] - at["pace"]) / 100.0, 4
        ),
        # C-7: Bench net rating
        "home_bench_net_rtg": _get_bench_net_rtg(home_team, season),
        "away_bench_net_rtg": _get_bench_net_rtg(away_team, season),
        # Rolling L10
        "home_off_rtg_L10":   h_roll_inf["off_rtg_L10"],
        "home_def_rtg_L10":   h_roll_inf["def_rtg_L10"],
        "home_net_rtg_L10":   h_roll_inf["net_rtg_L10"],
        "away_off_rtg_L10":   a_roll_inf["off_rtg_L10"],
        "away_def_rtg_L10":   a_roll_inf["def_rtg_L10"],
        "away_net_rtg_L10":   a_roll_inf["net_rtg_L10"],
        # Tier 2 — SRS
        "home_srs":           _t2_h["srs"],
        "away_srs":           _t2_a["srs"],
        # Tier 2 — Four Factors L10
        "home_efg_L10":        h_roll_inf.get("efg_L10",      0.50),
        "away_efg_L10":        a_roll_inf.get("efg_L10",      0.50),
        "home_tov_pct_L10":    h_roll_inf.get("tov_pct_L10",  0.13),
        "away_tov_pct_L10":    a_roll_inf.get("tov_pct_L10",  0.13),
        "home_oreb_pct_L10":   h_roll_inf.get("oreb_pct_L10", 0.25),
        "away_oreb_pct_L10":   a_roll_inf.get("oreb_pct_L10", 0.25),
        "home_ft_rate_L10":    h_roll_inf.get("ft_rate_L10",  0.25),
        "away_ft_rate_L10":    a_roll_inf.get("ft_rate_L10",  0.25),
        # Tier 2 — Home/away venue splits
        "home_off_rtg_home_L10": _t2_h["venue_L10"],
        "away_off_rtg_away_L10": _t2_a["venue_L10"],
        # Tier 2 — Opponent-adjusted
        "home_off_rtg_vs_top_def": _t2_h["opp_adj"],
        "away_off_rtg_vs_top_def": _t2_a["opp_adj"],
    }


def _get_schedule_context(
    team_abbrev: str,
    game_date: Optional[str],
    season: str,
) -> dict:
    """
    Return rest_days and back_to_back for a team on a given game date.

    Looks up the team's cached season schedule (populated by schedule_context).
    Falls back to neutral defaults (2 days rest, not B2B) when:
      - game_date is None
      - schedule is unavailable (API down, team unknown)
      - game_date not found in schedule (pre-season, playoffs)

    Args:
        team_abbrev: NBA team abbreviation e.g. "GSW"
        game_date:   ISO date string "YYYY-MM-DD", or None
        season:      Season string "2024-25"

    Returns:
        Dict with "rest_days" (float) and "back_to_back" (float 0/1).
    """
    _DEFAULTS = {"rest_days": 2.0, "back_to_back": 0.0}
    if not game_date:
        return _DEFAULTS
    try:
        from src.data.schedule_context import get_season_schedule
        schedule = get_season_schedule(team_abbrev, season)
        for game in schedule:
            if game.get("date") == game_date:
                raw_rest = int(game.get("rest_days", 2))
                return {
                    "rest_days":    float(min(raw_rest, 10)) if raw_rest < 99 else 3.0,
                    "back_to_back": float(bool(game.get("back_to_back", False))),
                }
    except Exception:
        pass
    return _DEFAULTS


def _get_last5_wins(team_abbrev: str, game_date: Optional[str], season: str) -> float:
    """
    Return wins_in_last_5 for a team on game_date from the cached season games.

    Reads season_games_{season}.json (written by _fetch_season_games).
    Falls back to 2.5 (neutral mid-point of 0–5) when:
      - game_date is None
      - cache not found
      - team/date not in cache (pre-season, playoffs)

    Args:
        team_abbrev: NBA team abbreviation e.g. "GSW"
        game_date:   ISO date string "YYYY-MM-DD", or None
        season:      Season string "2024-25"

    Returns:
        Float wins in last 5 games (0.0 – 5.0), or 2.5 as neutral default.
    """
    _DEFAULT = 2.5
    if not game_date:
        return _DEFAULT
    cache_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(cache_path):
        return _DEFAULT
    try:
        with open(cache_path) as f:
            payload = json.load(f)
        # Cache is versioned: {"v": N, "rows": [...]}. Unwrap rows; fall back
        # to treating the payload as a plain list for any legacy format.
        games = payload.get("rows", payload) if isinstance(payload, dict) else payload
        for g in games:
            if g.get("game_date") == game_date:
                if g.get("home_team") == team_abbrev:
                    return float(g.get("home_last5_wins", _DEFAULT))
                if g.get("away_team") == team_abbrev:
                    return float(g.get("away_last5_wins", _DEFAULT))
    except Exception:
        pass
    return _DEFAULT


def _fetch_team_stats(season: str) -> dict:
    """
    Fetch season-level advanced team stats (OFF_RATING, DEF_RATING, etc.)
    from leaguedashteamstats. Returns dict keyed by TEAM_ID.
    """
    cache_path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    os.makedirs(_NBA_CACHE, exist_ok=True)
    _stats_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _TEAM_STATS_TTL_HOURS * 3600
    )
    if _stats_fresh:
        with open(cache_path) as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}

    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        time.sleep(0.8)
        df = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",
            measure_type_detailed_defense="Advanced",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] team_stats {season}: {e}")
        return {}

    stats = {}
    for _, row in df.iterrows():
        tid = int(row["TEAM_ID"])
        stats[tid] = {
            "off_rtg":  float(row.get("OFF_RATING", 112)),
            "def_rtg":  float(row.get("DEF_RATING", 112)),
            "net_rtg":  float(row.get("NET_RATING", 0)),
            "pace":     float(row.get("PACE", 99)),
            "efg_pct":  float(row.get("EFG_PCT", 0.53)),
            "ts_pct":   float(row.get("TS_PCT", 0.57)),
            "tov_pct":  float(row.get("TM_TOV_PCT", 13)),
            "reb_pct":  float(row.get("REB_PCT", 0.5)),
            "win_pct":  float(row.get("W_PCT", 0.5)),
        }

    # Second pass: Base stats for STL → stl_per_poss = stl_pg / pace
    # stl_per_poss is needed by player_props._get_opp_stl_rate(); without it
    # that function always returns the league-avg constant 0.08 (no variance).
    try:
        time.sleep(0.8)
        base_df = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",
            measure_type_detailed_defense="Base",
        ).get_data_frames()[0]
        for _, row in base_df.iterrows():
            tid = int(row["TEAM_ID"])
            if tid in stats:
                stl_pg = float(row.get("STL", 7.5))
                pace   = stats[tid]["pace"]
                stats[tid]["stl_per_poss"] = round(stl_pg / max(pace, 1.0), 4)
    except Exception as _e:
        print(f"  [warn] team base stats {season}: {_e} — stl_per_poss will use fallback")

    with open(cache_path, "w") as f:
        json.dump({str(k): v for k, v in stats.items()}, f)
    print(f"  Cached team stats for {len(stats)} teams ({season})")
    return stats


def _is_active_season(season: str) -> bool:
    """Return True if *season* overlaps the current calendar year.

    Examples (assuming today is 2025-03-16):
      "2024-25" → True   (end year 2025 == current year)
      "2023-24" → False  (end year 2024 < current year)
      "2025-26" → True   (start year 2025 == current year — future/pre-season)

    Args:
        season: Season string in "YYYY-YY" format (e.g. "2024-25").

    Returns:
        True when the season is the current or upcoming season; False for
        completed past seasons whose game log will never change.
    """
    from datetime import date as _date
    current_year = _date.today().year
    try:
        parts = season.split("-")
        start_year = int(parts[0])
        end_year   = 2000 + int(parts[1]) if len(parts[1]) == 2 else int(parts[1])
        return start_year >= current_year or end_year >= current_year
    except (IndexError, ValueError):
        return True  # default to active if format is unrecognised


def _available_feature_cols(rows: List[dict]) -> List[str]:
    """Return the subset of `_MODEL_FEATURE_COLS` actually present in `rows`.

    Older v8 caches were written before _sim_features landed in the row
    builder, so they lack the 4 sim_* columns. Running 1000-sim Monte Carlo
    per matchup at train time to backfill is prohibitively slow (~15 min for
    900 unique matchups) so we accept the reduced feature set instead. The
    sweep evidence shows the 67-feature configuration already produces the
    same baseline metrics as the prod metrics file, so dropping these is
    not a regression.
    """
    if not rows:
        return list(_MODEL_FEATURE_COLS)
    sample = rows[0]
    return [c for c in _MODEL_FEATURE_COLS if c in sample]


def _fetch_season_games(season: str) -> List[dict]:
    """
    Fetch all regular-season games for one season.

    Game list from leaguegamelog (home/away/result).
    Team ratings joined from leaguedashteamstats by TEAM_ID.
    """
    cache_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    os.makedirs(_NBA_CACHE, exist_ok=True)
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            payload = json.load(f)
        # payload is either a versioned dict {"v": N, "rows": [...]} or a legacy list
        if isinstance(payload, dict) and payload.get("v") == _SEASON_GAMES_VERSION:
            # For the active season apply a TTL so new games are included when retraining.
            # Completed past seasons never change — cache them forever.
            if _is_active_season(season):
                age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
                if age_h <= _ACTIVE_SEASON_GAMES_TTL_HOURS:
                    return payload["rows"]
                print(f"  [cache] season_games_{season}: TTL expired, re-fetching active season...")
            else:
                return payload["rows"]
        else:
            # Version mismatch or legacy format — bust cache and re-fetch
            print(f"  [cache] season_games_{season}: schema changed (v{_SEASON_GAMES_VERSION}), re-fetching...")

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
        print(f"  [warn] gamelog {season}: {e}")
        return []

    # Fetch team season ratings (keyed by TEAM_ID)
    team_stats = _fetch_team_stats(season)

    # Build rest-day, recent-form, and rolling-rating lookups from game log (no extra API call)
    from src.features.advanced_features import compute_game_elo_lookup
    rest_lookup    = _compute_rest_days(gl)
    wins5_lookup   = _compute_last5_wins(gl)
    winpct_lookup  = _compute_cumulative_win_pct(gl)
    elo_lookup     = compute_game_elo_lookup([season])
    roll_lookup    = _compute_rolling_team_stats(gl, 10)
    srs_lookup     = _compute_srs_lookup(gl)
    venue_lookup   = _compute_venue_rolling(gl)
    opp_adj_lookup = _compute_opp_adjusted_rolling(gl, team_stats)
    # Season-to-date team ratings — the leakage-free replacement for the
    # season-FINAL leaguedashteamstats lookup that previously filled
    # home_/away_off_rtg/def_rtg/net_rtg/pace/efg_pct/ts_pct/tov_pct. The
    # team_stats dict (season-final) is still used as a fallback for early-
    # season games where the expanding-window sample is too small (<3 prior
    # games), but using season-final on the first few games of the year is
    # still a minor leak — TODO replace with prior-season carryover.
    std_lookup     = _compute_season_to_date_team_stats(gl)
    _ROLL_D10 = {
        "off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0,
        "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
    }

    _DEFAULT = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
                "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
                "tov_pct": 13.0, "reb_pct": 0.5, "win_pct": 0.5}

    rows = []
    for gid in gl["GAME_ID"].unique():
        pair = gl[gl["GAME_ID"] == gid]
        if len(pair) != 2:
            continue
        home_r = pair[pair["MATCHUP"].str.contains(r" vs\. ", na=False)]
        away_r = pair[pair["MATCHUP"].str.contains(r" @ ",    na=False)]
        if home_r.empty or away_r.empty:
            continue
        h, a   = home_r.iloc[0], away_r.iloc[0]
        # Point-in-time team strength: expanding window through games strictly
        # prior to this game_id, NOT season-final from leaguedashteamstats.
        # Falls back to neutral league averages (_DEFAULT) — never to the
        # season-final team_stats dict, which would re-introduce the leak.
        ht     = std_lookup.get((int(h["TEAM_ID"]), str(gid)), _DEFAULT)
        at     = std_lookup.get((int(a["TEAM_ID"]), str(gid)), _DEFAULT)

        # Cap at 10 to match _get_schedule_context (inference) — keeps train/inference aligned.
        h_rest  = min(rest_lookup.get((int(h["TEAM_ID"]), str(gid)), 2), 10)
        a_rest  = min(rest_lookup.get((int(a["TEAM_ID"]), str(gid)), 2), 10)
        h_wins5 = wins5_lookup.get((int(h["TEAM_ID"]), str(gid)), 2)
        a_wins5 = wins5_lookup.get((int(a["TEAM_ID"]), str(gid)), 2)
        h_roll  = roll_lookup.get((int(h["TEAM_ID"]), str(gid)), _ROLL_D10)
        a_roll  = roll_lookup.get((int(a["TEAM_ID"]), str(gid)), _ROLL_D10)

        rows.append({
            "game_id": gid, "season": season,
            "game_date": str(h.get("GAME_DATE", "")),
            "home_team": h["TEAM_ABBREVIATION"], "away_team": a["TEAM_ABBREVIATION"],
            "home_win":  int(h["WL"] == "W"),
            # Home team season ratings
            "home_off_rtg":        ht["off_rtg"],
            "home_def_rtg":        ht["def_rtg"],
            "home_net_rtg":        ht["net_rtg"],
            "home_pace":           ht["pace"],
            "home_efg_pct":        ht["efg_pct"],
            "home_ts_pct":         ht["ts_pct"],
            "home_tov_pct":        ht["tov_pct"],
            "home_rest_days":      float(h_rest),
            "home_back_to_back":   float(h_rest == 1),
            "home_travel_miles":   0.0,
            "home_last5_wins":     float(h_wins5),
            "home_season_win_pct": winpct_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.5),
            # Away team season ratings
            "away_off_rtg":        at["off_rtg"],
            "away_def_rtg":        at["def_rtg"],
            "away_net_rtg":        at["net_rtg"],
            "away_pace":           at["pace"],
            "away_efg_pct":        at["efg_pct"],
            "away_ts_pct":         at["ts_pct"],
            "away_tov_pct":        at["tov_pct"],
            "away_rest_days":      float(a_rest),
            "away_back_to_back":   float(a_rest == 1),
            # Away team flew to the home arena — real distance, no API call needed.
            "away_travel_miles":   compute_travel_distance(
                a["TEAM_ABBREVIATION"], h["TEAM_ABBREVIATION"]
            ),
            "away_last5_wins":     float(a_wins5),
            "away_season_win_pct": winpct_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.5),
            # Derived (net_rtg_diff uses rolling values; pace_diff stays season-level)
            "net_rtg_diff":   h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
            "pace_diff":      ht["pace"]    - at["pace"],
            "home_advantage": 1.0,
            # Lineup quality (season-level; same value for all games in same season)
            "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                h["TEAM_ABBREVIATION"], season
            ),
            "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                a["TEAM_ABBREVIATION"], season
            ),
            # Ref crew tendencies — unknown per historical game; use league averages
            "ref_avg_fouls":    42.0,
            "ref_home_win_pct": 0.5,
            # Phase 4.6: iso matchup edge (home iso PPP - away def iso PPP allowed)
            "iso_matchup_edge": (
                _synergy_team_iso_ppp(h["TEAM_ABBREVIATION"], season)
                - _synergy_team_def_iso_ppp(a["TEAM_ABBREVIATION"], season)
            ),
            # Phase 4.6: ref FTA tendency — unknown historically; 0.0 default
            "ref_fta_tendency": 0.0,
            # C-1: ELO — point-in-time (snapshot before each game, no leakage)
            "home_elo":          elo_lookup.get(str(gid), {}).get("home_elo", 1500.0),
            "away_elo":          elo_lookup.get(str(gid), {}).get("away_elo", 1500.0),
            "elo_differential":  (
                elo_lookup.get(str(gid), {}).get("home_elo", 1500.0)
                - elo_lookup.get(str(gid), {}).get("away_elo", 1500.0)
            ),
            # C-2: Defensive trajectory — 0.0 default for historical training rows
            "home_def_rtg_trend":  0.0,
            "away_def_rtg_trend":  0.0,
            # C-3: Pace variance — 2.0 neutral default
            "home_pace_variance":  2.0,
            "away_pace_variance":  2.0,
            # C-4: Hustle deflections — 0.0 when not available
            "home_hustle_deflections_pg": 0.0,
            "away_hustle_deflections_pg": 0.0,
            # C-5: PnR PPP — season-level from synergy cache
            "home_pnr_ppp": _get_pnr_ppp(h["TEAM_ABBREVIATION"], season),
            "away_pnr_ppp": _get_pnr_ppp(a["TEAM_ABBREVIATION"], season),
            # C-6: Interaction terms
            "b2b_diff":            float(h_rest == 1) - float(a_rest == 1),
            "elo_pace_interaction": (
                elo_lookup.get(str(gid), {}).get("home_elo", 1500.0) * ht["pace"]
                - elo_lookup.get(str(gid), {}).get("away_elo", 1500.0) * at["pace"]
            ),
            # Star availability — historical injury data not tracked; default 3 (full)
            "home_stars_available": 3,
            "away_stars_available": 3,
            # C-7: Bench net rating — 0.0 when not available
            "home_bench_net_rtg":  0.0,
            "away_bench_net_rtg":  0.0,
            # Rolling L10: game-by-game rolling avg (10-game window)
            "home_off_rtg_L10":    h_roll["off_rtg_L10"],
            "home_def_rtg_L10":    h_roll["def_rtg_L10"],
            "home_net_rtg_L10":    h_roll["net_rtg_L10"],
            "away_off_rtg_L10":    a_roll["off_rtg_L10"],
            "away_def_rtg_L10":    a_roll["def_rtg_L10"],
            "away_net_rtg_L10":    a_roll["net_rtg_L10"],
            # Tier 2 — SRS
            "home_srs":            srs_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.0),
            "away_srs":            srs_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.0),
            # Tier 2 — Four Factors L10
            "home_efg_L10":        h_roll.get("efg_L10",      0.50),
            "away_efg_L10":        a_roll.get("efg_L10",      0.50),
            "home_tov_pct_L10":    h_roll.get("tov_pct_L10",  0.13),
            "away_tov_pct_L10":    a_roll.get("tov_pct_L10",  0.13),
            "home_oreb_pct_L10":   h_roll.get("oreb_pct_L10", 0.25),
            "away_oreb_pct_L10":   a_roll.get("oreb_pct_L10", 0.25),
            "home_ft_rate_L10":    h_roll.get("ft_rate_L10",  0.25),
            "away_ft_rate_L10":    a_roll.get("ft_rate_L10",  0.25),
            # Tier 2 — Home/away venue splits
            "home_off_rtg_home_L10": venue_lookup.get((int(h["TEAM_ID"]), str(gid)), {}).get("home_venue_L10", 112.0),
            "away_off_rtg_away_L10": venue_lookup.get((int(a["TEAM_ID"]), str(gid)), {}).get("away_venue_L10", 112.0),
            # Tier 2 — Opponent-adjusted
            "home_off_rtg_vs_top_def": opp_adj_lookup.get((int(h["TEAM_ID"]), str(gid)), 112.0),
            "away_off_rtg_vs_top_def": opp_adj_lookup.get((int(a["TEAM_ID"]), str(gid)), 112.0),
            # Phase 8: Monte Carlo simulation features
            **_sim_features(
                h["TEAM_ABBREVIATION"], a["TEAM_ABBREVIATION"],
                home_stats=ht, away_stats=at,
            ),
        })

    with open(cache_path, "w") as f:
        json.dump({"v": _SEASON_GAMES_VERSION, "rows": rows}, f)
    print(f"  Cached {len(rows)} games -> {cache_path}")
    return rows


def _compute_last5_wins(gl: "pd.DataFrame") -> dict:
    """
    Build a (team_id, game_id) → wins_in_last_5 lookup from a league game log.

    For each game the value is the number of wins in the 5 games played
    *before* that game.

    Early-season scaling: when fewer than 5 prior games exist, the raw count
    is rate-scaled to the full 5-game window (``sum/len * 5``) so a team
    that went 1-for-1 gets 5.0, not 1. Season openers (no prior games) get
    the neutral default 2.5.

    Args:
        gl: DataFrame with columns TEAM_ID, GAME_ID, GAME_DATE, WL.

    Returns:
        Dict mapping (int team_id, str game_id) → int wins_in_last_5.
    """
    from collections import deque
    from datetime import datetime

    def _parse(d: str):
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(d.strip(), fmt)
            except ValueError:
                continue
        return None

    lookup: dict = {}
    tmp = gl[["TEAM_ID", "GAME_ID", "GAME_DATE", "WL"]].copy()
    tmp["_date"] = tmp["GAME_DATE"].apply(_parse)
    tmp = tmp.sort_values(["TEAM_ID", "_date"])

    history: dict = {}  # team_id → deque(maxlen=5) of win flags
    for _, row in tmp.iterrows():
        tid = int(row["TEAM_ID"])
        gid = str(row["GAME_ID"])
        wl  = str(row.get("WL", ""))
        buf = history.setdefault(tid, deque(maxlen=5))
        # Record wins in the last 5 *before* this game.
        # Rate-scale when fewer than 5 games buffered to avoid count bias.
        if not buf:
            lookup[(tid, gid)] = 2.5          # season opener — neutral
        elif len(buf) < 5:
            lookup[(tid, gid)] = round(sum(buf) / len(buf) * 5, 1)  # rate-scaled
        else:
            lookup[(tid, gid)] = int(sum(buf))  # full window — exact count
        buf.append(1 if wl == "W" else 0)

    return lookup


def _compute_cumulative_win_pct(gl: "pd.DataFrame") -> dict:
    """
    Build a (team_id, game_id) → cumulative_win_pct lookup from a league game log.

    For each game the value is W / G for all games played *before* that game.
    Season opener defaults to 0.5 (neutral prior).

    Args:
        gl: DataFrame with columns TEAM_ID, GAME_ID, GAME_DATE, WL.

    Returns:
        Dict mapping (int team_id, str game_id) → float win_pct.
    """
    from datetime import datetime

    def _parse(d: str):
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(d.strip(), fmt)
            except ValueError:
                continue
        return None

    lookup: dict = {}
    tmp = gl[["TEAM_ID", "GAME_ID", "GAME_DATE", "WL"]].copy()
    tmp["_date"] = tmp["GAME_DATE"].apply(_parse)
    tmp = tmp.sort_values(["TEAM_ID", "_date"])

    wins:  dict = {}  # team_id → cumulative wins
    games: dict = {}  # team_id → cumulative games played
    for _, row in tmp.iterrows():
        tid = int(row["TEAM_ID"])
        gid = str(row["GAME_ID"])
        wl  = str(row.get("WL", ""))
        w = wins.get(tid, 0)
        g = games.get(tid, 0)
        lookup[(tid, gid)] = round(w / g, 4) if g > 0 else 0.5
        wins[tid]  = w + (1 if wl == "W" else 0)
        games[tid] = g + 1

    return lookup


def _compute_rest_days(gl: "pd.DataFrame") -> dict:
    """
    Build a (team_id, game_id) → rest_days lookup from a league game log.

    Processes each team's games in chronological order and computes the number
    of calendar days since their previous game.  Season openers default to 3.

    Args:
        gl: DataFrame from LeagueGameLog with columns TEAM_ID, GAME_ID, GAME_DATE.

    Returns:
        Dict mapping (int team_id, str game_id) → int rest_days.
    """
    from datetime import datetime

    def _parse(d: str):
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(d.strip(), fmt)
            except ValueError:
                continue
        return None

    lookup: dict = {}
    tmp = gl[["TEAM_ID", "GAME_ID", "GAME_DATE"]].copy()
    tmp["_date"] = tmp["GAME_DATE"].apply(_parse)
    tmp = tmp.sort_values(["TEAM_ID", "_date"])

    prev: dict = {}  # team_id → last parsed date
    for _, row in tmp.iterrows():
        tid  = int(row["TEAM_ID"])
        gid  = str(row["GAME_ID"])
        date = row["_date"]
        if date is None:
            lookup[(tid, gid)] = 2
            continue
        rest = int((date - prev[tid]).days) if tid in prev else 3
        lookup[(tid, gid)] = rest
        prev[tid] = date

    return lookup


def _compute_season_to_date_team_stats(gl: "pd.DataFrame") -> "dict[tuple, dict]":
    """Build (team_id, game_id) → expanding-window team advanced ratings.

    For each game N, returns ratings computed from the team's games 1..N-1
    only (shift(1)). Matches the 7-field shape of _fetch_team_stats:
    {off_rtg, def_rtg, net_rtg, pace, efg_pct, ts_pct, tov_pct}.

    Why this exists: _fetch_team_stats returns the team's season-FINAL
    leaguedashteamstats ratings — using those as features at training time
    leaks future games (predicting October on an April-stable signal).
    This function rebuilds the same fields from the regular game log using
    only strictly-prior games, eliminating the leak.

    Falls back to league averages for the first three games of a team's
    season (no qualifying prior sample).
    """
    needed = {"TEAM_ID", "GAME_ID", "GAME_DATE", "PTS", "MIN",
              "FGM", "FGA", "FG3M", "FTA", "OREB", "TOV"}
    if not needed.issubset(gl.columns):
        return {}

    # tov_pct is a fraction (0.13), not a percent — matches the
    # leaguedashteamstats TM_TOV_PCT scale that the cached rows use.
    _DEF = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
            "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57, "tov_pct": 0.13}

    df = gl[list(needed)].copy()
    df["TEAM_ID"] = df["TEAM_ID"].astype(int)
    df["GAME_ID"] = df["GAME_ID"].astype(str)
    df["_dt"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df["poss"] = (df["FGA"] + 0.44 * df["FTA"] + df["TOV"] - df["OREB"]).clip(lower=1)

    # Per-game lookup of opponent PTS + POSS for def_rtg.
    by_game: dict = {}
    for _, r in df.iterrows():
        by_game.setdefault(r["GAME_ID"], {})[int(r["TEAM_ID"])] = {
            "pts": float(r["PTS"]), "poss": float(r["poss"]),
        }

    def _opp(r):
        d = {t: v for t, v in by_game.get(r["GAME_ID"], {}).items()
             if t != int(r["TEAM_ID"])}
        if d:
            v = next(iter(d.values()))
            return v["pts"], v["poss"]
        return 0.0, 0.0

    df[["_opp_pts", "_opp_poss"]] = df.apply(_opp, axis=1, result_type="expand")
    df = df.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)

    lookup: dict = {}
    for tid, grp in df.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        # shift(1) so game N's lookup uses cumulative stats through games 1..N-1.
        cum_pts      = grp["PTS"].shift(1).expanding().sum()
        cum_poss     = grp["poss"].shift(1).expanding().sum()
        cum_opp_pts  = grp["_opp_pts"].shift(1).expanding().sum()
        cum_opp_poss = grp["_opp_poss"].shift(1).expanding().sum()
        cum_min      = grp["MIN"].shift(1).expanding().sum()
        cum_fgm      = grp["FGM"].shift(1).expanding().sum()
        cum_fga      = grp["FGA"].shift(1).expanding().sum()
        cum_fg3m     = grp["FG3M"].shift(1).expanding().sum()
        cum_fta      = grp["FTA"].shift(1).expanding().sum()
        cum_tov      = grp["TOV"].shift(1).expanding().sum()
        n_prior      = grp["PTS"].shift(1).expanding().count()

        for i in range(len(grp)):
            gid = str(grp.at[i, "GAME_ID"])
            if int(n_prior.iloc[i]) < 3:
                lookup[(int(tid), gid)] = dict(_DEF)
                continue
            poss      = float(cum_poss.iloc[i])
            opp_poss  = float(cum_opp_poss.iloc[i])
            mn        = float(cum_min.iloc[i])
            fga       = float(cum_fga.iloc[i])
            fta       = float(cum_fta.iloc[i])
            if poss <= 0 or opp_poss <= 0 or mn <= 0 or fga <= 0:
                lookup[(int(tid), gid)] = dict(_DEF)
                continue
            off_rtg = float(cum_pts.iloc[i]) / poss * 100.0
            def_rtg = float(cum_opp_pts.iloc[i]) / opp_poss * 100.0
            # MIN is team-minutes (5 players × 48 = 240 per regulation game),
            # not game-minutes. Standard NBA pace is poss per 48 game-minutes,
            # so divide by (MIN / 5) and rescale: poss * 240 / MIN.
            pace    = poss * 240.0 / mn
            efg     = (float(cum_fgm.iloc[i]) + 0.5 * float(cum_fg3m.iloc[i])) / fga
            ts_den  = 2.0 * (fga + 0.44 * fta)
            ts_pct  = float(cum_pts.iloc[i]) / ts_den if ts_den > 0 else 0.57
            # TM_TOV_PCT from leaguedashteamstats is a fraction (0.12), not a
            # percentage (12) — the cached training rows store the fraction.
            tov_pct = float(cum_tov.iloc[i]) / poss
            lookup[(int(tid), gid)] = {
                "off_rtg": round(off_rtg, 2),
                "def_rtg": round(def_rtg, 2),
                "net_rtg": round(off_rtg - def_rtg, 2),
                "pace":    round(pace, 2),
                "efg_pct": round(efg, 4),
                "ts_pct":  round(ts_pct, 4),
                "tov_pct": round(tov_pct, 4),
            }
    return lookup


def _compute_rolling_team_stats(
    gl: "pd.DataFrame", window: int = 10
) -> "dict[tuple, dict]":
    """
    Build (team_id, game_id) → rolling-window rating lookup from game log.

    Off/def rating proxy per game, then rolling mean of prior *window* games
    (shift(1) prevents leakage).  Falls back to 112/112/0 when < 3 prior games.

    Args:
        gl:     LeagueGameLog DataFrame with TEAM_ID, GAME_ID, GAME_DATE,
                PTS, FGA, FTA, TOV, OREB cols.
        window: Look-back window (default 10).

    Returns:
        Dict mapping (int team_id, str game_id) → {off_rtg_LN, def_rtg_LN, net_rtg_LN}.
    """
    suffix = f"L{window}"
    _DEF = {
        f"off_rtg_{suffix}": 112.0, f"def_rtg_{suffix}": 112.0, f"net_rtg_{suffix}": 0.0,
        "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
    }

    needed = {"TEAM_ID", "GAME_ID", "GAME_DATE", "PTS", "FGA", "FTA", "TOV", "OREB"}
    ff_cols = {"FGM", "FG3M", "DREB"}
    has_ff  = ff_cols.issubset(gl.columns)
    if not needed.issubset(gl.columns):
        return {}

    load_cols = list(needed | (ff_cols if has_ff else set()))
    df = gl[load_cols].copy()
    df["TEAM_ID"] = df["TEAM_ID"].astype(int)
    df["GAME_ID"] = df["GAME_ID"].astype(str)
    df["poss"] = (df["FGA"] + 0.44 * df["FTA"] + df["TOV"] - df["OREB"]).clip(lower=1)
    df["off_raw"] = (df["PTS"] / df["poss"] * 100).round(2)

    # Build GAME_ID → {team_id: (off_raw, DREB)} for opponent lookups
    opp: dict = {}
    for _, r in df.iterrows():
        opp.setdefault(r["GAME_ID"], {})[r["TEAM_ID"]] = {
            "off": r["off_raw"],
            "dreb": float(r["DREB"]) if has_ff else 0.0,
        }

    def _def_raw(r) -> float:
        vals = [v["off"] for t, v in opp.get(r["GAME_ID"], {}).items() if t != r["TEAM_ID"]]
        return vals[0] if vals else 112.0

    def _opp_dreb(r) -> float:
        vals = [v["dreb"] for t, v in opp.get(r["GAME_ID"], {}).items() if t != r["TEAM_ID"]]
        return vals[0] if vals else 0.0

    df["def_raw"] = df.apply(_def_raw, axis=1)
    if has_ff:
        df["opp_dreb"] = df.apply(_opp_dreb, axis=1)
        df["efg_raw"]     = ((df["FGM"] + 0.5 * df["FG3M"]) / df["FGA"].clip(lower=1)).round(4)
        df["tov_pct_raw"] = (df["TOV"] / (df["FGA"] + 0.44 * df["FTA"] + df["TOV"]).clip(lower=1)).round(4)
        df["oreb_pct_raw"]= (df["OREB"] / (df["OREB"] + df["opp_dreb"]).clip(lower=1)).round(4)
        df["ft_rate_raw"] = (df["FTA"] / df["FGA"].clip(lower=1)).round(4)

    df["_date"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df = df.sort_values(["TEAM_ID", "_date"])

    lookup: dict = {}
    for tid, grp in df.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        r_off   = grp["off_raw"].shift(1).rolling(window, min_periods=1).mean()
        r_def   = grp["def_raw"].shift(1).rolling(window, min_periods=1).mean()
        n_prior = grp["off_raw"].expanding().count() - 1  # games before this one
        if has_ff:
            r_efg  = grp["efg_raw"].shift(1).rolling(window, min_periods=1).mean()
            r_tov  = grp["tov_pct_raw"].shift(1).rolling(window, min_periods=1).mean()
            r_oreb = grp["oreb_pct_raw"].shift(1).rolling(window, min_periods=1).mean()
            r_ftr  = grp["ft_rate_raw"].shift(1).rolling(window, min_periods=1).mean()
        for i in range(len(grp)):
            gid = str(grp.at[i, "GAME_ID"])
            if int(n_prior.iloc[i]) < 3:
                lookup[(int(tid), gid)] = dict(_DEF)
            else:
                off = round(float(r_off.iloc[i]), 2)
                de  = round(float(r_def.iloc[i]), 2)
                entry = {
                    f"off_rtg_{suffix}": off,
                    f"def_rtg_{suffix}": de,
                    f"net_rtg_{suffix}": round(off - de, 2),
                    "efg_L10":     round(float(r_efg.iloc[i]),  4) if has_ff else 0.50,
                    "tov_pct_L10": round(float(r_tov.iloc[i]),  4) if has_ff else 0.13,
                    "oreb_pct_L10":round(float(r_oreb.iloc[i]), 4) if has_ff else 0.25,
                    "ft_rate_L10": round(float(r_ftr.iloc[i]),  4) if has_ff else 0.25,
                }
                lookup[(int(tid), gid)] = entry
    return lookup


def _compute_srs_lookup(gl: "pd.DataFrame", iterations: int = 10) -> dict:
    """
    Build (team_id, game_id) → SRS (Simple Rating System) at that point in time.

    SRS = cumulative avg margin + strength of schedule (damped season-level SOS).
    shift(1) prevents leakage. Default 0.0.
    """
    needed = {"TEAM_ID", "GAME_ID", "GAME_DATE", "PTS"}
    if not needed.issubset(gl.columns):
        return {}
    df = gl[["TEAM_ID", "GAME_ID", "GAME_DATE", "PTS"]].copy()
    df["TEAM_ID"] = df["TEAM_ID"].astype(int)
    df["GAME_ID"] = df["GAME_ID"].astype(str)
    df["_dt"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")

    pts_map: dict = {}
    for _, r in df.iterrows():
        pts_map.setdefault(r["GAME_ID"], {})[r["TEAM_ID"]] = float(r["PTS"])

    def _opp_info(r):
        d = {t: p for t, p in pts_map.get(r["GAME_ID"], {}).items() if t != r["TEAM_ID"]}
        pair = list(d.items())
        return (pair[0][0], pair[0][1]) if pair else (0, float(r["PTS"]))

    df[["_opp_tid", "_opp_pts"]] = df.apply(_opp_info, axis=1, result_type="expand")
    df["_margin"] = df["PTS"] - df["_opp_pts"]
    df = df.sort_values(["TEAM_ID", "_dt"])

    teams = list(df["TEAM_ID"].unique())
    opp_dict = {t: df[df["TEAM_ID"] == t]["_opp_tid"].astype(int).tolist() for t in teams}
    avg_m    = {t: float(df[df["TEAM_ID"] == t]["_margin"].mean()) for t in teams}
    srs = {t: 0.0 for t in teams}
    for _ in range(iterations):
        srs = {t: avg_m[t] + (np.mean([srs.get(o, 0.0) for o in opp_dict[t]]) if opp_dict[t] else 0.0)
               for t in teams}

    lookup: dict = {}
    for tid, grp in df.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        cum_m = grp["_margin"].shift(1).expanding().mean().fillna(0.0)
        for i, row in grp.iterrows():
            sos = srs.get(int(row["_opp_tid"]), 0.0) * 0.5
            lookup[(int(tid), str(row["GAME_ID"]))] = round(float(cum_m.iloc[i]) + sos, 3)
    return lookup


def _compute_venue_rolling(gl: "pd.DataFrame") -> dict:
    """
    Build (team_id, game_id) → {"home_venue_L10": float, "away_venue_L10": float}.

    home_venue_L10: rolling off_rtg of last 10 home games (MATCHUP "vs."), shift(1).
    away_venue_L10: rolling off_rtg of last 10 away games (MATCHUP "@"), shift(1).
    Default 112.0.
    """
    needed = {"TEAM_ID", "GAME_ID", "GAME_DATE", "PTS", "FGA", "FTA", "TOV", "OREB", "MATCHUP"}
    if not needed.issubset(gl.columns):
        return {}
    df = gl[list(needed)].copy()
    df["TEAM_ID"] = df["TEAM_ID"].astype(int)
    df["GAME_ID"] = df["GAME_ID"].astype(str)
    df["_dt"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df["poss"]    = (df["FGA"] + 0.44 * df["FTA"] + df["TOV"] - df["OREB"]).clip(lower=1)
    df["off_raw"] = (df["PTS"] / df["poss"] * 100).round(2)
    df = df.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)

    lookup: dict = {}
    for tid, grp in df.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        h = grp[grp["MATCHUP"].str.contains(r" vs\. ", na=False)].copy().reset_index(drop=True)
        a = grp[grp["MATCHUP"].str.contains(r" @ ",    na=False)].copy().reset_index(drop=True)
        h["_hv"] = h["off_raw"].shift(1).rolling(10, min_periods=1).mean().fillna(112.0).round(2)
        a["_av"] = a["off_raw"].shift(1).rolling(10, min_periods=1).mean().fillna(112.0).round(2)
        h_map = dict(zip(h["GAME_ID"], h["_hv"]))
        a_map = dict(zip(a["GAME_ID"], a["_av"]))
        for _, row in grp.iterrows():
            gid = str(row["GAME_ID"])
            lookup[(int(tid), gid)] = {
                "home_venue_L10": float(h_map.get(gid, 112.0)),
                "away_venue_L10": float(a_map.get(gid, 112.0)),
            }
    return lookup


def _compute_opp_adjusted_rolling(gl: "pd.DataFrame", team_stats: dict) -> dict:
    """
    Build (team_id, game_id) → rolling off_rtg vs top-10 defensive teams (last 10 qualifying).

    Per-date top-10 ranking: for each game's date D, the top-10 def_rtg teams are
    re-determined using each team's expanding-window def_rtg through games strictly
    before D (shift(1)). This eliminates the loop-5-cycle-3 secondary leak where
    the ranking used season-FINAL def_rtg from team_stats — the team_stats
    parameter is now ignored (kept in the signature for back-compat).
    """
    needed = {"TEAM_ID", "GAME_ID", "GAME_DATE", "PTS", "FGA", "FTA", "TOV", "OREB"}
    if not needed.issubset(gl.columns):
        return {}
    df = gl[list(needed)].copy()
    df["TEAM_ID"] = df["TEAM_ID"].astype(int)
    df["GAME_ID"] = df["GAME_ID"].astype(str)
    df["_dt"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df["poss"]    = (df["FGA"] + 0.44 * df["FTA"] + df["TOV"] - df["OREB"]).clip(lower=1)
    df["off_raw"] = (df["PTS"] / df["poss"] * 100).round(2)

    # Build (game_id) -> {team_id: {pts, poss}} for opp_pts/opp_poss lookup.
    by_game: dict = {}
    for _, r in df.iterrows():
        by_game.setdefault(r["GAME_ID"], {})[int(r["TEAM_ID"])] = {
            "pts":  float(r["PTS"]),
            "poss": float(r["poss"]),
        }

    def _opp_info(r):
        d = {t: v for t, v in by_game.get(r["GAME_ID"], {}).items()
             if t != int(r["TEAM_ID"])}
        if d:
            v = next(iter(d.values()))
            return v["pts"], v["poss"], next(iter(d.keys()))
        return 0.0, 0.0, 0

    df[["_opp_pts", "_opp_poss", "_opp_tid"]] = df.apply(
        _opp_info, axis=1, result_type="expand"
    )
    df["_opp_tid"] = df["_opp_tid"].astype(int)

    # Per-team expanding def_rtg (cumulative opp_pts / cumulative opp_poss) at the
    # time-of-game level. shift(1) so we get the def_rtg through games strictly
    # PRIOR to the current one. >= 5 prior games required to be ranked at all
    # (otherwise the team can't be in/out of the top-10 set).
    df = df.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)
    df["_cum_opp_pts"]  = df.groupby("TEAM_ID")["_opp_pts"].shift(1).groupby(df["TEAM_ID"]).cumsum()
    df["_cum_opp_poss"] = df.groupby("TEAM_ID")["_opp_poss"].shift(1).groupby(df["TEAM_ID"]).cumsum()
    df["_n_prior"]      = df.groupby("TEAM_ID").cumcount()
    df["_def_rtg_pit"]  = (df["_cum_opp_pts"] / df["_cum_opp_poss"].clip(lower=1) * 100.0).round(2)
    df.loc[df["_n_prior"] < 5, "_def_rtg_pit"] = float("nan")

    # For each unique game date D, snapshot each team's most-recent _def_rtg_pit
    # entry where _dt < D and rank the top-10 lowest. Date snapshots speed up
    # the per-game vs-top lookup that follows.
    df_sorted_date = df.sort_values("_dt")
    team_last_def: dict = {}            # team_id -> latest def_rtg seen
    date_snapshots: dict = {}            # date -> set of top-10 team_ids
    seen_dates: set = set()
    prev_date = None
    for _, r in df_sorted_date.iterrows():
        cur_date = r["_dt"]
        if cur_date != prev_date:
            # Compute top-10 snapshot for the NEW date using whatever team_last_def
            # values are recorded from games on STRICTLY earlier dates. Teams with
            # NaN (fewer than 5 prior games) are excluded from the ranking.
            ranked = sorted(
                [(t, v) for t, v in team_last_def.items() if not (v != v)],
                key=lambda kv: kv[1],
            )
            date_snapshots[cur_date] = {t for t, _ in ranked[:10]}
            prev_date = cur_date
        # After snapshot is taken for cur_date, record this row's def_rtg (which
        # applies to FUTURE dates' snapshots).
        if not (r["_def_rtg_pit"] != r["_def_rtg_pit"]):
            team_last_def[int(r["TEAM_ID"])] = float(r["_def_rtg_pit"])

    # Each row: is its opponent in the top-10 set AS OF this game's date?
    df["_vs_top"] = df.apply(
        lambda r: int(r["_opp_tid"]) in date_snapshots.get(r["_dt"], set()),
        axis=1,
    )

    lookup: dict = {}
    for tid, grp in df.groupby("TEAM_ID"):
        grp = grp.sort_values("_dt").reset_index(drop=True)
        top = grp[grp["_vs_top"]].copy().reset_index(drop=True)
        top["_roll"] = top["off_raw"].shift(1).rolling(10, min_periods=1).mean().fillna(112.0).round(2)
        top_map = dict(zip(top["GAME_ID"].astype(str), top["_roll"]))
        for _, row in grp.iterrows():
            gid = str(row["GAME_ID"])
            lookup[(int(tid), gid)] = float(top_map.get(gid, 112.0))
    return lookup


def _save_metrics(metrics: dict):
    """Write training metrics to data/models/win_prob_metrics.json."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(os.path.join(_MODEL_DIR, "win_prob_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Win Probability Model")
    ap.add_argument("--train",    action="store_true", help="Train on 3 seasons")
    ap.add_argument("--backtest", action="store_true", help="Walk-forward backtest")
    ap.add_argument("--predict",  nargs=2, metavar=("HOME", "AWAY"))
    ap.add_argument("--season",   default="2025-26")
    ap.add_argument("--seasons",  nargs="+", default=["2022-23", "2023-24", "2024-25"])
    ap.add_argument("--retrain-with-sim", action="store_true",
                    help="Retrain including Phase 8 Monte Carlo sim features")
    args = ap.parse_args()

    if args.retrain_with_sim or args.train:
        # Clear sim cache so fresh sims run for each matchup
        _SIM_CACHE.clear()
        train(seasons=args.seasons)
    elif args.backtest:
        backtest(seasons=args.seasons)
    elif args.predict:
        m = load()
        print(json.dumps(m.predict(args.predict[0], args.predict[1], args.season), indent=2))
    else:
        ap.print_help()
