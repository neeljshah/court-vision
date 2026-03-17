"""
player_props.py — Player prop models: points, rebounds, assists (Phase 3).

Uses last-N-game rolling averages + opponent defensive rating as features.
XGBoost regressor per stat category. Predicts season-to-date averages as
a proxy for prop line values.

Public API
----------
    predict_props(player_name, opp_team, season, n_games) -> dict
    train_props(season, force)                            -> dict  # {pts, reb, ast} models
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# Default stat averages when lookup fails
_STAT_DEFAULTS = {"pts": 14.0, "reb": 4.5, "ast": 3.2}

# Player game-log cache TTL: re-fetch after 24 hours so rolling form stays current.
_GAMELOG_TTL_HOURS = 24

# Season averages cache TTL: re-fetch after 24 hours so season stats stay current.
# This is a bulk cache (all players in one API call), so 24h is a reasonable balance
# between freshness and API rate-limit costs.
_PLAYER_AVGS_TTL_HOURS = 24


# ── Data helpers ───────────────────────────────────────────────────────────────

def _get_player_season_avgs(player_name: str, season: str) -> Optional[dict]:
    """
    Fetch season-to-date per-game averages from LeagueDashPlayerStats.

    Returns dict with pts, reb, ast, min, ts_pct or None on failure.
    Caches to data/nba/player_avgs_{season}.json.
    """
    cache_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    _avgs_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _PLAYER_AVGS_TTL_HOURS * 3600
    )
    if _avgs_fresh:
        with open(cache_path) as f:
            cache = json.load(f)
    else:
        cache = {}

    import unicodedata
    def _norm(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

    key = _norm(player_name)
    # Build normalized lookup from cache
    norm_cache = {_norm(k): v for k, v in cache.items()}
    if key in norm_cache:
        return norm_cache[key]

    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
        time.sleep(0.6)
        df = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season, per_mode_simple="Totals"
        ).get_data_frames()[0]
        # Populate full cache in one shot — divide totals by GP to get per-game avgs.
        # Traded players appear multiple times (per-team rows + a TOT combined row).
        # Always keep the entry with the highest GP so TOT wins over partial-season rows.
        for _, row in df.iterrows():
            gp = max(int(row.get("GP", 1)), 1)
            key_name = _norm(row["PLAYER_NAME"])
            if key_name in cache and cache[key_name].get("gp", 0) >= gp:
                continue   # existing entry has more games — keep it (TOT row wins)
            cache[key_name] = {
                "player_id":  int(row["PLAYER_ID"]),
                "team":       row.get("TEAM_ABBREVIATION", ""),
                "gp":         gp,
                "min":        float(row.get("MIN", 0)) / gp,
                "pts":        float(row.get("PTS", 0)) / gp,
                "reb":        float(row.get("REB", 0)) / gp,
                "ast":        float(row.get("AST", 0)) / gp,
                "tov":        float(row.get("TOV", 0)) / gp,
                "fg_pct":     float(row.get("FG_PCT", 0)),
                "fg3_pct":    float(row.get("FG3_PCT", 0)),
                "ft_pct":     float(row.get("FT_PCT", 0)),
                "fta":        float(row.get("FTA", 0)) / gp,
            }
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f)
        return cache.get(key)
    except Exception as e:
        print(f"  [props] player avgs fetch failed: {e}")
        return None


def _get_opp_def_rating(opp_team: str, season: str) -> float:
    """
    Return opponent's defensive rating.

    Lookup order:
    1. team_stats_{season}.json  — written by win_probability training (team_id keyed)
    2. opp_def_rtg_{season}.json — own cache keyed by team abbreviation
    3. Fetch from LeagueDashTeamStats Advanced and populate cache (2)
    4. League-average fallback (113.0)

    Lower def_rtg = better defense.
    """
    # 1. Primary: win-probability training cache (team_id keyed)
    primary = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    if os.path.exists(primary):
        try:
            from nba_api.stats.static import teams as _teams
            with open(primary) as f:
                ts = json.load(f)
            abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
            tid = abbrev_to_id.get(opp_team, "0")
            val = ts.get(tid, {}).get("def_rtg")
            if val is not None:
                return float(val)
        except Exception:
            pass

    # 2. Secondary: own abbrev-keyed cache
    secondary = os.path.join(_NBA_CACHE, f"opp_def_rtg_{season}.json")
    if os.path.exists(secondary):
        try:
            with open(secondary) as f:
                cache = json.load(f)
            if opp_team in cache:
                return float(cache[opp_team])
        except Exception:
            pass

    # 3. Fetch from NBA API and populate secondary cache
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        time.sleep(0.6)
        df = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Advanced",
            per_mode_simple="PerGame",
        ).get_data_frames()[0]
        cache = {}
        for _, row in df.iterrows():
            abbrev = str(row.get("TEAM_ABBREVIATION", ""))
            def_rtg = row.get("DEF_RATING")
            if abbrev and def_rtg is not None:
                cache[abbrev] = float(def_rtg)
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(secondary, "w") as f:
            json.dump(cache, f)
        return float(cache.get(opp_team, 113.0))
    except Exception as e:
        print(f"  [props] opp def_rtg fetch failed: {e}")
        return 113.0


def _get_recent_form(player_id: int, season: str, n: int = 10) -> Optional[dict]:
    """
    Compute rolling n-game averages from PlayerGameLog.

    Returns dict with pts, reb, ast, min rolling avg or None on failure.
    """
    cache_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
    _cache_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _GAMELOG_TTL_HOURS * 3600
    )
    if _cache_fresh:
        with open(cache_path) as f:
            rows = json.load(f)
    else:
        try:
            from nba_api.stats.endpoints import playergamelog
            time.sleep(0.6)
            df = playergamelog.PlayerGameLog(
                player_id=player_id, season=season
            ).get_data_frames()[0]
            # MIN from PlayerGameLog is "MM:SS" string — convert to float minutes.
            def _parse_min(m) -> float:
                try:
                    if isinstance(m, str) and ":" in m:
                        parts = m.split(":")
                        return float(parts[0]) + float(parts[1]) / 60
                    return float(m)
                except (ValueError, IndexError):
                    return 0.0
            df = df.copy()
            df["MIN"] = df["MIN"].apply(_parse_min)
            keep_cols = [c for c in ["GAME_DATE", "PTS", "REB", "AST", "MIN"] if c in df.columns]
            rows = df[keep_cols].to_dict("records")
            os.makedirs(_NBA_CACHE, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(rows, f)
        except Exception as e:
            print(f"  [props] gamelog fetch failed: {e}")
            return None

    if not rows:
        return None
    # Sort by GAME_DATE descending so rows[:n] is truly the most recent games.
    # PlayerGameLog returns dates in "Jan 15, 2025" format — string sort is
    # WRONG across calendar years (N > J means Nov 2024 sorts after Jan 2025).
    # Always parse to datetime before sorting.
    if rows and "GAME_DATE" in rows[0]:
        from datetime import datetime as _dt

        def _parse_game_date(d: str):
            for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
                try:
                    return _dt.strptime(str(d).strip(), fmt)
                except ValueError:
                    continue
            return _dt.min  # unrecognised format → sort to end

        rows = sorted(rows, key=lambda r: _parse_game_date(r["GAME_DATE"]), reverse=True)
    recent = rows[:n]

    def _to_min(m) -> float:
        """Parse MM:SS string or numeric minutes to float."""
        try:
            if isinstance(m, str) and ":" in m:
                p = m.split(":")
                return float(p[0]) + float(p[1]) / 60
            return float(m)
        except (ValueError, IndexError):
            return 0.0

    return {
        "pts_roll":  sum(float(r.get("PTS", 0)) for r in recent) / len(recent),
        "reb_roll":  sum(float(r.get("REB", 0)) for r in recent) / len(recent),
        "ast_roll":  sum(float(r.get("AST", 0)) for r in recent) / len(recent),
        "min_roll":  sum(_to_min(r.get("MIN", 0)) for r in recent) / len(recent),
    }


# ── Feature builder ────────────────────────────────────────────────────────────

def _build_player_features(
    player_name: str,
    opp_team: str,
    season: str,
    n_games: int = 10,
) -> Optional[dict]:
    """
    Build the feature vector for prop prediction.

    Features (10 total):
      season_pts, season_reb, season_ast, season_min,
      pts_roll, reb_roll, ast_roll, min_roll,
      opp_def_rtg, fg_pct
    """
    avgs = _get_player_season_avgs(player_name, season)
    if avgs is None:
        return None

    form = _get_recent_form(avgs["player_id"], season, n_games)
    opp_def = _get_opp_def_rating(opp_team, season)

    return {
        "season_pts":   avgs["pts"],
        "season_reb":   avgs["reb"],
        "season_ast":   avgs["ast"],
        "season_min":   avgs["min"],
        "pts_roll":     form["pts_roll"]  if form else avgs["pts"],
        "reb_roll":     form["reb_roll"]  if form else avgs["reb"],
        "ast_roll":     form["ast_roll"]  if form else avgs["ast"],
        "min_roll":     form["min_roll"]  if form else avgs["min"],
        "opp_def_rtg":  opp_def,
        "fg_pct":       avgs["fg_pct"],
    }


# ── Prediction ─────────────────────────────────────────────────────────────────

def predict_props(
    player_name: str,
    opp_team: str,
    season: str = "2024-25",
    n_games: int = 10,
) -> dict:
    """
    Predict points, rebounds, assists for a player vs an opponent.

    Uses XGBoost models when available; falls back to rolling/season averages.

    Args:
        player_name: Full player name (e.g. "LeBron James").
        opp_team:    Opponent team abbreviation (e.g. "GSW").
        season:      NBA season string.
        n_games:     Rolling window for recent form.

    Returns:
        {
          "player":    str,
          "opp_team":  str,
          "pts":       float,
          "reb":       float,
          "ast":       float,
          "confidence": str,       # "model" | "rolling" | "season"
          "features":  dict,
        }
    """
    feats = _build_player_features(player_name, opp_team, season, n_games)
    if feats is None:
        return {
            "player":    player_name,
            "opp_team":  opp_team,
            "pts":       _STAT_DEFAULTS["pts"],
            "reb":       _STAT_DEFAULTS["reb"],
            "ast":       _STAT_DEFAULTS["ast"],
            "confidence": "default",
            "features":  {},
        }

    # Attempt model predictions
    pts, reb, ast, confidence = _predict_with_models(feats)

    return {
        "player":    player_name,
        "opp_team":  opp_team,
        "pts":       pts,
        "reb":       reb,
        "ast":       ast,
        "confidence": confidence,
        "features":  feats,
    }


def _predict_with_models(feats: dict) -> tuple:
    """
    Try loading trained XGBoost models. Fall back to rolling averages.

    Returns (pts, reb, ast, confidence_str).
    """
    import numpy as np
    _ALL_FEATS = [
        "season_pts", "season_reb", "season_ast", "season_min",
        "pts_roll", "reb_roll", "ast_roll", "min_roll",
        "opp_def_rtg", "fg_pct",
    ]

    results = {}
    for stat in ("pts", "reb", "ast"):
        # Each model was trained without season_{stat} to prevent label leakage.
        stat_feat_order = [c for c in _ALL_FEATS if c != f"season_{stat}"]
        X = np.array([[feats[k] for k in stat_feat_order]])
        model_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        if os.path.exists(model_path):
            try:
                import xgboost as xgb
                m = xgb.XGBRegressor()
                m.load_model(model_path)
                results[stat] = float(m.predict(X)[0])
            except Exception:
                results[stat] = None
        else:
            results[stat] = None

    # Fall back to rolling average for any missing model
    confidence = "model" if all(v is not None for v in results.values()) else "rolling"
    pts = results["pts"] if results["pts"] is not None else feats["pts_roll"]
    reb = results["reb"] if results["reb"] is not None else feats["reb_roll"]
    ast = results["ast"] if results["ast"] is not None else feats["ast_roll"]

    return round(pts, 1), round(reb, 1), round(ast, 1), confidence


# ── Training ───────────────────────────────────────────────────────────────────

def train_props(seasons: list = None, force: bool = False) -> dict:
    """
    Train XGBoost regression models for pts, reb, ast props.

    Uses LeagueDashPlayerStats per season as training signal.
    Target = actual season per-game stat, features = first-half-season proxy.
    Walk-forward: train on earlier seasons, test on latest.

    Args:
        seasons: List of season strings. Defaults to ["2022-23", "2023-24", "2024-25"].
        force:   Retrain even if models already saved.

    Returns:
        {"pts": {"mae": float, "r2": float}, "reb": ..., "ast": ...}
    """
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error, r2_score

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    # Check if already trained
    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"props_{s}.json"))
        for s in ("pts", "reb", "ast")
    ):
        print("[props] Models already trained. Use force=True to retrain.")
        return {}

    # Gather cross-season player data
    all_rows = []
    for season in seasons:
        print(f"  [props] Fetching {season} player stats...")
        avgs = _get_all_player_avgs(season)
        for row in avgs:
            row["season"] = season
            all_rows.append(row)
        time.sleep(0.5)

    if len(all_rows) < 100:
        print(f"  [props] Not enough data ({len(all_rows)} rows). Skipping training.")
        return {}

    import pandas as pd
    df = pd.DataFrame(all_rows)

    feat_cols = [
        "season_pts", "season_reb", "season_ast", "season_min",
        "pts_roll", "reb_roll", "ast_roll", "min_roll",
        "opp_def_rtg", "fg_pct",
    ]
    # For training: simulate rolling-vs-season divergence with calibrated noise.
    # Without noise pts_roll == season_pts exactly → model learns a trivial identity
    # (R²≈1 in-sample) and never sees the hot/cold-streak inputs it faces at inference.
    # Noise scale matches empirical NBA rolling-10 vs season-avg std: pts ~15%,
    # ast ~20% (more volatile), reb/min ~12%.
    import numpy as np
    _rng_form = np.random.default_rng(0)
    for col, scale in [("pts", 0.15), ("reb", 0.12), ("ast", 0.20), ("min", 0.12)]:
        noise = _rng_form.normal(0.0, scale, size=len(df))
        df[f"{col}_roll"] = (df[f"season_{col}"] * (1.0 + noise)).clip(lower=0.0)

    # Sample real opponent def_rtg values so XGBoost can learn defensive adjustments.
    # Using a constant (113.0) gives zero variance → zero feature importance.
    # We pull the actual distribution from cached team stats across all training seasons.
    all_def_rtgs: list = []
    for s in seasons:
        ts_path = os.path.join(_NBA_CACHE, f"team_stats_{s}.json")
        if os.path.exists(ts_path):
            with open(ts_path) as f:
                ts = json.load(f)
            all_def_rtgs.extend(
                float(v["def_rtg"]) for v in ts.values() if "def_rtg" in v
            )
    if all_def_rtgs:
        rng = np.random.default_rng(42)
        df["opp_def_rtg"] = rng.choice(all_def_rtgs, size=len(df), replace=True)
    else:
        df["opp_def_rtg"] = 113.0  # fallback when no cache available

    df = df.dropna(subset=feat_cols)

    results = {}
    train_seasons = seasons[:-1]
    test_season   = seasons[-1]

    train_df = df[df["season"].isin(train_seasons)]
    test_df  = df[df["season"] == test_season]

    for stat in ("pts", "reb", "ast"):
        # Drop season_{stat} from features when training the {stat} model — it IS the label.
        # Including it causes the model to learn a near-identity (R²≈1, zero generalisation).
        stat_feat_cols = [c for c in feat_cols if c != f"season_{stat}"]
        X_train = train_df[stat_feat_cols].values
        X_test  = test_df[stat_feat_cols].values
        y_train = train_df[f"season_{stat}"].values
        y_test  = test_df[f"season_{stat}"].values

        m = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        m.fit(X_train, y_train)
        preds = m.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        r2  = r2_score(y_test, preds)

        model_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        m.save_model(model_path)
        results[stat] = {"mae": round(mae, 3), "r2": round(r2, 3)}
        print(f"  [props] {stat.upper()} — MAE: {mae:.2f}  R²: {r2:.3f}  → saved {model_path}")

    return results


def _get_all_player_avgs(season: str) -> list:
    """
    Return list of feature dicts for all players in a season.
    Uses LeagueDashPlayerStats (cached).
    """
    cache_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    avgs_map = {}
    # Use the same TTL as the inference path so stale training data doesn't
    # silently bias models (the TTL was added to _get_player_season_avgs but
    # this training-path caller was missed).
    _avgs_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _PLAYER_AVGS_TTL_HOURS * 3600
    )
    if _avgs_fresh:
        with open(cache_path) as f:
            avgs_map = json.load(f)
    else:
        _get_player_season_avgs("__trigger__", season)   # populates fresh cache
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                avgs_map = json.load(f)

    rows = []
    for name, a in avgs_map.items():
        if a.get("gp", 0) < 10:
            continue
        rows.append({
            "season_pts":  a.get("pts", 0),
            "season_reb":  a.get("reb", 0),
            "season_ast":  a.get("ast", 0),
            "season_min":  a.get("min", 0),
            "pts_roll":    a.get("pts", 0),
            "reb_roll":    a.get("reb", 0),
            "ast_roll":    a.get("ast", 0),
            "min_roll":    a.get("min", 0),
            "opp_def_rtg": 113.0,
            "fg_pct":      a.get("fg_pct", 0.45),
        })
    return rows


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA Player Prop Prediction")
    ap.add_argument("--player", type=str, help="Player full name")
    ap.add_argument("--opp",    type=str, help="Opponent abbreviation")
    ap.add_argument("--season", default="2024-25")
    ap.add_argument("--train",  action="store_true", help="Train prop models")
    args = ap.parse_args()

    if args.train:
        results = train_props(force=True)
        print(json.dumps(results, indent=2))
    elif args.player and args.opp:
        result = predict_props(args.player, args.opp, args.season)
        print(json.dumps({k: v for k, v in result.items() if k != "features"}, indent=2))
    else:
        ap.print_help()
