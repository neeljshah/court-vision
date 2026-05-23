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
# v2 ELO + injury: these 6 new features are computed post-load via build_elo_history and
# build_injury_lookup rather than forcing a full season cache re-fetch. Version stays 8.
# NOTE: delete data/nba/season_games_*.json to force re-fetch with new schema.
_SEASON_GAMES_VERSION = 8

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
    # v2: Improved ELO (FiveThirtyEight formula: K=20 + MOV mult, home_adj=85, 25% regression)
    "home_elo_v2", "away_elo_v2", "elo_diff_v2",
    # v2: Team injury impact — estimated win-shares lost from inactive players
    "home_inj_ws", "away_inj_ws", "inj_ws_diff",
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


_SIM_NEUTRAL = {
    "sim_win_prob":        0.5,
    "sim_score_diff_mean": 0.0,
    "sim_score_diff_std":  10.0,
    "sim_pace_adj":        1.0,
}


def _sim_features_safe(home_team: str, away_team: str,
                       home_stats: Optional[dict] = None,
                       away_stats: Optional[dict] = None) -> dict:
    """Wrap _sim_features with fallback to neutral defaults on any failure."""
    try:
        return _sim_features(home_team, away_team, home_stats, away_stats)
    except Exception:
        return dict(_SIM_NEUTRAL)


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


def _get_elo_v2(team_abbr: str) -> float:
    """Load improved ELO (v2) from elo_state.json. Falls back to 1500."""
    try:
        from src.features.elo import get_current_elo
        return get_current_elo(team_abbr)
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
    """C-7: Mean net rating for bench lineups (<20 min/g) from data/nba/lineups/."""
    try:
        lineup_dir = os.path.join(_NBA_CACHE, "lineups")
        if not os.path.exists(lineup_dir):
            return 0.0
        candidates = [
            f for f in os.listdir(lineup_dir)
            if team_abbr.upper() in f.upper() and f.endswith(".json")
        ]
        if not candidates:
            return 0.0
        vals = []
        for fname in candidates:
            rows = json.load(open(os.path.join(lineup_dir, fname)))
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
    """C-7: Mean net rating for bench lineups (<20 min/g) from data/nba/lineups/."""
    try:
        lineup_dir = os.path.join(_NBA_CACHE, "lineups")
        if not os.path.exists(lineup_dir):
            return 0.0
        candidates = [
            f for f in os.listdir(lineup_dir)
            if team_abbr.upper() in f.upper() and f.endswith(".json")
        ]
        if not candidates:
            return 0.0
        vals = []
        for fname in candidates:
            rows = json.load(open(os.path.join(lineup_dir, fname)))
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

    def __init__(self, model=None, threshold: float = 0.5):
        """
        Args:
            model:     Trained XGBClassifier (None before training).
            threshold: Decision threshold for binary prediction.
        """
        self.model     = model
        self.threshold = threshold
        self._feature_importance: Optional[dict] = None

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
        X     = np.array([[feats[c] for c in _MODEL_FEATURE_COLS]], dtype=np.float32)
        prob  = float(self.model.predict_proba(X)[0][1])

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
        path = path or os.path.join(_MODEL_DIR, "win_prob.pkl")
        model_bytes = self.model.get_booster().save_raw(raw_format="ubj")
        with open(path, "wb") as f:
            pickle.dump({"model_bytes": model_bytes, "threshold": self.threshold,
                         "feature_importance": self._feature_importance}, f)
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
    n_estimators: int = 1000,
    learning_rate: float = 0.05,
    max_depth: int = 4,
) -> WinProbModel:
    """
    Train XGBoost win probability model on 3 seasons of NBA data.

    Walk-forward evaluation:
      - Train: 2022-23 + 2023-24 games
      - Validate (early stopping): 2024-25 first half (Oct 2024 – Jan 2025)
      - Holdout (reported): 2024-25 second half (Feb 2025 – end)

    Args:
        seasons:       Seasons to train on (default ["2022-23","2023-24","2024-25"]).
        output_path:   Where to save model (auto if None).
        n_estimators:  Max XGBoost trees (early stopping will find optimal).
        learning_rate: XGBoost lr.
        max_depth:     XGBoost depth.

    Returns:
        Trained WinProbModel.
    """
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    print(f"Building dataset from {seasons} ...")
    rows = []
    for s in seasons:
        s_rows = _fetch_season_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games")

    if not rows:
        raise RuntimeError("No data fetched — check NBA API connectivity")

    df = pd.DataFrame(rows).dropna(subset=["home_win"])

    # Sort chronologically — walk-forward splits must be strictly in the future
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    # ── v2: Compute improved ELO and injury features as overlay ───────────────
    print("  Computing v2 ELO (K=20 + MOV mult, home_adj=85, 25% regression) ...")
    try:
        from src.features.elo import compute_game_elo_lookup_v2
        elo_v2 = compute_game_elo_lookup_v2(seasons)
        df["home_elo_v2"] = df["game_id"].apply(
            lambda g: elo_v2.get(str(g), {}).get("home_elo", 1500.0)
        )
        df["away_elo_v2"] = df["game_id"].apply(
            lambda g: elo_v2.get(str(g), {}).get("away_elo", 1500.0)
        )
        df["elo_diff_v2"] = (df["home_elo_v2"] - df["away_elo_v2"]).round(2)
        n_nondefault = (df["home_elo_v2"] != 1500.0).sum()
        print(f"    ELO v2 populated for {n_nondefault}/{len(df)} games")
    except Exception as e:
        print(f"  [warn] ELO v2 failed: {e} — using 1500.0 defaults")
        df["home_elo_v2"] = 1500.0
        df["away_elo_v2"] = 1500.0
        df["elo_diff_v2"] = 0.0

    print("  Computing injury impact (boxscore-based inactive WS) ...")
    try:
        from src.features.injury_impact import build_injury_lookup
        inj_lkp = build_injury_lookup(seasons)
        df["home_inj_ws"]  = df["game_id"].apply(lambda g: inj_lkp.get(str(g), {}).get("home_inj_ws", 0.0))
        df["away_inj_ws"]  = df["game_id"].apply(lambda g: inj_lkp.get(str(g), {}).get("away_inj_ws", 0.0))
        df["inj_ws_diff"]  = df["game_id"].apply(lambda g: inj_lkp.get(str(g), {}).get("inj_ws_diff", 0.0))
        n_inj = (df["home_inj_ws"] > 0).sum()
        print(f"    Injury data populated for {n_inj}/{len(df)} games "
              f"(0.0 = no boxscore or no prior-season data)")
    except Exception as e:
        print(f"  [warn] Injury impact failed: {e} — using 0.0 defaults")
        df["home_inj_ws"] = 0.0
        df["away_inj_ws"] = 0.0
        df["inj_ws_diff"] = 0.0

    # Fill any remaining missing feature columns with 0.0
    for col in _MODEL_FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0

    X  = df[_MODEL_FEATURE_COLS].values.astype(np.float32)
    y  = df["home_win"].values.astype(int)
    print(f"Dataset: {len(df)} games | home win rate {y.mean():.1%} | features={len(_MODEL_FEATURE_COLS)}")

    # Walk-forward split strategy:
    #   - Fit on ALL data (80% chronological), early stopping on last 20%
    #   - Additionally report per-slice metrics: 2022-23/24 vs 2024-25 first/second half
    #   This avoids distribution-shift early stopping while still exposing per-slice performance.
    split   = int(len(df) * 0.8)
    X_tr    = X[:split]
    y_tr    = y[:split]
    X_val   = X[split:]
    y_val   = y[split:]
    print(f"  Fit: {len(X_tr)} games | Early-stop val: {len(X_val)} games")

    # Build per-slice masks for reporting (no impact on training)
    mask_train_seasons = df["season"].isin(["2022-23", "2023-24"]) if "season" in df.columns else None
    if "season" in df.columns and "game_date" in df.columns:
        mask_2425    = df["season"] == "2024-25"
        games_2425   = df[mask_2425].reset_index(drop=True)
        mid_idx      = len(games_2425) // 2
        mid_date     = games_2425.iloc[mid_idx]["game_date"] if len(games_2425) else "2025-01-15"
        mask_val_1h  = mask_2425 & (df["game_date"] < mid_date)
        mask_hold_2h = mask_2425 & (df["game_date"] >= mid_date)
        print(f"  Report slices: 2024-25 first half (<{mid_date}), second half (>={mid_date})")
    else:
        mid_date, mask_val_1h, mask_hold_2h = None, None, None

    X_hold  = X_val   # holdout = same as val for final reporting
    y_hold  = y_val

    clf = XGBClassifier(
        n_estimators=n_estimators, learning_rate=learning_rate,
        max_depth=max_depth, subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, n_jobs=-1,
        early_stopping_rounds=50,
    )
    clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=100)

    # Report per-slice metrics
    print("\n── Walk-forward evaluation ──────────────────────────────────")
    slice_metrics = {}

    base_slices = [("train_80pct", X_tr, y_tr), ("val_20pct", X_val, y_val)]
    for name, Xs, ys in base_slices:
        if len(ys) == 0:
            continue
        probs = clf.predict_proba(Xs)[:, 1]
        acc_s   = accuracy_score(ys, (probs >= 0.5).astype(int))
        brier_s = brier_score_loss(ys, probs)
        slice_metrics[name] = {"acc": round(acc_s, 4), "brier": round(brier_s, 4), "n": len(ys)}
        print(f"  {name:14s}: acc={acc_s:.4f}  brier={brier_s:.4f}  n={len(ys)}")

    # Additional season-level breakdown
    if mask_val_1h is not None:
        for slice_name, mask in [("2024-25 H1", mask_val_1h), ("2024-25 H2", mask_hold_2h)]:
            Xs_sl = df[mask][_MODEL_FEATURE_COLS].values.astype(np.float32)
            ys_sl = df[mask]["home_win"].values.astype(int)
            if len(ys_sl) < 10:
                continue
            probs_sl = clf.predict_proba(Xs_sl)[:, 1]
            acc_sl   = accuracy_score(ys_sl, (probs_sl >= 0.5).astype(int))
            brier_sl = brier_score_loss(ys_sl, probs_sl)
            key = slice_name.replace(" ", "_").lower()
            slice_metrics[key] = {"acc": round(acc_sl, 4), "brier": round(brier_sl, 4), "n": len(ys_sl)}
            print(f"  {slice_name:14s}: acc={acc_sl:.4f}  brier={brier_sl:.4f}  n={len(ys_sl)}")

    # Final reported metrics = 20% val (chronologically last 20% of all 3 seasons)
    hold_probs = clf.predict_proba(X_hold)[:, 1]
    acc   = accuracy_score(y_hold, (hold_probs >= 0.5).astype(int))
    brier = brier_score_loss(y_hold, hold_probs)
    best_n = clf.best_iteration + 1 if hasattr(clf, "best_iteration") and clf.best_iteration else n_estimators
    print(f"\nFinal (20% val): acc={acc:.4f}  brier={brier:.4f}  best_n_estimators={best_n}")

    model = WinProbModel(model=clf)
    model._feature_importance = dict(zip(_MODEL_FEATURE_COLS, clf.feature_importances_.tolist()))
    model.save(output_path)
    _save_metrics({
        "accuracy":         round(acc, 6),
        "brier":            round(brier, 6),
        "n_games":          len(df),
        "seasons":          seasons,
        "version":          "v2_elo_injury",
        "features":         _MODEL_FEATURE_COLS,
        "best_n_estimators": best_n,
        "slices":           slice_metrics,
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
    path = model_path or os.path.join(_MODEL_DIR, "win_prob.pkl")
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
    m = WinProbModel(model=clf, threshold=data.get("threshold", 0.5))
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

    X  = df[_MODEL_FEATURE_COLS].values.astype(np.float32)
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
        # v2: Improved ELO from persisted state (inference uses latest ratings)
        "home_elo_v2":  _get_elo_v2(home_team),
        "away_elo_v2":  _get_elo_v2(away_team),
        "elo_diff_v2":  round(_get_elo_v2(home_team) - _get_elo_v2(away_team), 2),
        # v2: Injury impact — 0.0 default at inference (real-time data not available)
        "home_inj_ws":  0.0,
        "away_inj_ws":  0.0,
        "inj_ws_diff":  0.0,
        # Phase 8: Monte Carlo sim features — run 1 000 sims; fall back to neutral if unavailable
        **_sim_features_safe(home_team, away_team, ht, at),
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
        ht     = team_stats.get(int(h["TEAM_ID"]), _DEFAULT)
        at     = team_stats.get(int(a["TEAM_ID"]), _DEFAULT)

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

    Top-10 = teams with lowest def_rtg in team_stats. shift(1), default 112.0.
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

    def_sorted = sorted(team_stats.items(), key=lambda x: x[1].get("def_rtg", 999.0))
    top10_def  = {int(tid) for tid, _ in def_sorted[:10]}

    opp_tid_map: dict = {}
    for _, r in df.iterrows():
        opp_tid_map.setdefault(r["GAME_ID"], {})[r["TEAM_ID"]] = True
    df["_opp_tid"] = df.apply(
        lambda r: next((t for t in opp_tid_map.get(r["GAME_ID"], {}) if t != r["TEAM_ID"]), 0),
        axis=1,
    ).astype(int)
    df["_vs_top"] = df["_opp_tid"].isin(top10_def)
    df = df.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)

    lookup: dict = {}
    for tid, grp in df.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
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
