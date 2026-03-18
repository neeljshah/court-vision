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
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")

# Bump this whenever the season_games cache schema changes (new fields, etc.)
# Cached files with a different or absent version are automatically re-fetched.
_SEASON_GAMES_VERSION = 3

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
]


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
        season: str = "2024-25",
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
        X     = np.array([[feats[c] for c in FEATURE_COLS]], dtype=np.float32)
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
        path = path or os.path.join(_MODEL_DIR, "win_probability.pkl")
        with open(path, "wb") as f:
            pickle.dump({"model": self.model, "threshold": self.threshold,
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


# ── Training ───────────────────────────────────────────────────────────────────

def train(
    seasons: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    n_estimators: int = 300,
    learning_rate: float = 0.05,
    max_depth: int = 4,
) -> WinProbModel:
    """
    Train XGBoost win probability model on 3 seasons of NBA data.

    Fetches game logs from NBA Stats API, constructs feature vectors,
    trains classifier with 80/20 split.

    Args:
        seasons:       Seasons to train on (default last 3).
        output_path:   Where to save model (auto if None).
        n_estimators:  XGBoost trees.
        learning_rate: XGBoost lr.
        max_depth:     XGBoost depth.

    Returns:
        Trained WinProbModel.
    """
    from xgboost import XGBClassifier
    from sklearn.model_selection import train_test_split
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

    df = pd.DataFrame(rows).dropna(subset=FEATURE_COLS + ["home_win"])

    # Sort chronologically so the validation split is truly future games.
    # Random split leaks future games into training (October 2024 in train
    # while October 2023 is in val), inflating reported accuracy.
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    X  = df[FEATURE_COLS].values.astype(np.float32)
    y  = df["home_win"].values.astype(int)
    print(f"Dataset: {len(df)} games | home win rate {y.mean():.1%}")

    split = int(len(df) * 0.8)
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]

    clf = XGBClassifier(
        n_estimators=n_estimators, learning_rate=learning_rate,
        max_depth=max_depth, subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, n_jobs=-1,
        early_stopping_rounds=20,
    )
    clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=50)

    val_probs = clf.predict_proba(X_val)[:, 1]
    acc   = accuracy_score(y_val, (val_probs >= 0.5).astype(int))
    brier = brier_score_loss(y_val, val_probs)
    print(f"Val accuracy: {acc:.3f}  |  Brier: {brier:.4f}")

    model = WinProbModel(model=clf)
    model._feature_importance = dict(zip(FEATURE_COLS, clf.feature_importances_.tolist()))
    model.save(output_path)
    _save_metrics({"accuracy": acc, "brier": brier,
                   "n_games": len(df), "seasons": seasons})
    return model


def load(model_path: Optional[str] = None) -> WinProbModel:
    """Load saved WinProbModel from disk."""
    import pickle
    path = model_path or os.path.join(_MODEL_DIR, "win_probability.pkl")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found: {path} — run train() first")
    with open(path, "rb") as f:
        data = pickle.load(f)
    m = WinProbModel(model=data["model"], threshold=data.get("threshold", 0.5))
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

    df = pd.DataFrame(rows).dropna(subset=FEATURE_COLS + ["home_win"])

    # Sort chronologically so TimeSeriesSplit folds are truly walk-forward.
    # Without this, API-return order mixes games across seasons randomly,
    # letting the model train on March data and validate on October data.
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    X  = df[FEATURE_COLS].values.astype(np.float32)
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
        "net_rtg_diff":        ht["net_rtg"] - at["net_rtg"],
        "pace_diff":           ht["pace"]    - at["pace"],
        "home_advantage":      1.0,
        "home_top_lineup_net_rtg": h_lineup_nr,
        "away_top_lineup_net_rtg": a_lineup_nr,
        "ref_avg_fouls":       ref_avg_fouls,
        "ref_home_win_pct":    ref_home_win_pct,
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

    # Build rest-day and recent-form lookups from game log (no extra API call)
    rest_lookup  = _compute_rest_days(gl)
    wins5_lookup = _compute_last5_wins(gl)

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
            "home_season_win_pct": ht["win_pct"],
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
            "away_season_win_pct": at["win_pct"],
            # Derived
            "net_rtg_diff":   ht["net_rtg"] - at["net_rtg"],
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
    ap.add_argument("--season",   default="2024-25")
    ap.add_argument("--seasons",  nargs="+", default=["2022-23", "2023-24", "2024-25"])
    args = ap.parse_args()

    if args.train:
        train(seasons=args.seasons)
    elif args.backtest:
        backtest(seasons=args.seasons)
    elif args.predict:
        m = load()
        print(json.dumps(m.predict(args.predict[0], args.predict[1], args.season), indent=2))
    else:
        ap.print_help()
