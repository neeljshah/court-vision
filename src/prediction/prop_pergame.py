"""
prop_pergame.py — Per-game prop models trained on real game logs (PRED-13).

The legacy prop pipeline (player_props.train_props) trains on SEASON
averages: it predicts a player's season-average stat from features that are
essentially that same season average, plus simulated noise. Its reported
R²≈0.99 is therefore meaningless — a near-identity fit. The honest holdout
(predictions vs realised box scores) is only ~0.45.

This module trains the real task, the way a sharp quant would: each row is
one game, every feature is computed strictly from the player's PRIOR games
(rolling form, EWMA recency, rest, home/away), and the target is THAT game's
actual stat line. No leakage — features never see the game they predict.

Public API
----------
    build_pergame_dataset(gamelog_dir, min_prior) -> (rows, feature_cols)
    train_pergame_models(...)                     -> dict   (honest holdout R²/MAE)
    load_pergame_model(stat)                      -> model or None
    predict_pergame(stat, feature_row)            -> float
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# Stats predicted, and their box-score column names in the gamelog JSON.
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_BOX_COL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
            "stl": "STL", "blk": "BLK", "tov": "TOV", "min": "MIN"}
_FORM_STATS = STATS + ["min"]          # min drives every counting stat

_MIN_PLAYED = 5.0                      # a game counts only if the player played
_EWMA_ALPHA = 0.30                     # recency weight — recent games dominate


# ── feature helpers ───────────────────────────────────────────────────────────

def _parse_date(raw: str) -> Optional[datetime]:
    """Parse an NBA gamelog date ('Apr 13, 2025'). Returns None on failure."""
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _ewma(vals: List[float], alpha: float = _EWMA_ALPHA) -> float:
    """Exponentially-weighted mean — most recent game weighted highest."""
    if not vals:
        return 0.0
    weighted = total_w = 0.0
    for i, v in enumerate(reversed(vals)):       # i=0 is the most recent game
        w = alpha * (1.0 - alpha) ** i
        weighted += w * v
        total_w += w
    return weighted / total_w if total_w > 0 else 0.0


def feature_columns() -> List[str]:
    """Ordered feature names — form features, game-context, opponent defence."""
    cols: List[str] = []
    for stat in _FORM_STATS:
        cols += [f"l5_{stat}", f"l10_{stat}", f"std_{stat}",
                 f"ewma_{stat}", f"prev_{stat}"]
    cols += ["rest_days", "is_home", "games_played"]
    cols += [f"opp_def_{s}" for s in STATS]      # opponent-defence factors
    return cols


# ── opponent defence (leakage-free to-date factors) ──────────────────────────

class _OpponentDefense:
    """Per-team opponent-defence factors computed strictly to-date.

    For a game on date D against team O, the factor for a stat is O's mean
    allowed value for that stat over O's games BEFORE D, divided by the
    league mean to D. >1 means O is an easier-than-average matchup. Using
    only games before D keeps the feature leakage-free.
    """

    def __init__(self, allowed: Dict[str, list], league: list):
        self._team = {t: self._index(rows) for t, rows in allowed.items()}
        self._league = self._index(league)

    @staticmethod
    def _index(rows: list) -> dict:
        rows = sorted(rows, key=lambda r: r[0])
        dates = [r[0] for r in rows]
        prefix = {s: [0.0] for s in STATS}
        for _d, line in rows:
            for s in STATS:
                prefix[s].append(prefix[s][-1] + line[s])
        return {"dates": dates, "prefix": prefix}

    @staticmethod
    def _todate_mean(idx: dict, date, stat: str) -> Optional[float]:
        i = bisect.bisect_left(idx["dates"], date)
        return idx["prefix"][stat][i] / i if i > 0 else None

    def factors(self, opponent: str, date) -> Dict[str, float]:
        """Return {opp_def_{stat}: factor} for an opponent on a date.

        Falls back to a neutral 1.0 when there is no prior history."""
        out: Dict[str, float] = {}
        team_idx = self._team.get(opponent)
        for stat in STATS:
            league_mean = self._todate_mean(self._league, date, stat)
            team_mean = self._todate_mean(team_idx, date, stat) if team_idx else None
            if team_mean and league_mean and league_mean > 0:
                out[f"opp_def_{stat}"] = round(team_mean / league_mean, 4)
            else:
                out[f"opp_def_{stat}"] = 1.0
        return out


def _opponent_from_matchup(matchup: str) -> str:
    """Opponent abbreviation — the last token of 'TEAM vs. OPP' / 'TEAM @ OPP'."""
    parts = str(matchup).split()
    return parts[-1] if parts else ""


def build_opponent_defense(gamelog_dir: str) -> _OpponentDefense:
    """Pass over every gamelog to build the to-date opponent-defence model.

    Each played game is a stat line the *opponent* allowed — aggregated per
    opponent and league-wide, sorted chronologically.
    """
    allowed: Dict[str, list] = {}
    league: list = []
    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            if _num(g.get("MIN")) < _MIN_PLAYED:
                continue
            gdate = _parse_date(g.get("GAME_DATE"))
            opp = _opponent_from_matchup(g.get("MATCHUP", ""))
            if gdate is None or not opp:
                continue
            line = {s: _num(g.get(_BOX_COL[s])) for s in STATS}
            allowed.setdefault(opp, []).append((gdate, line))
            league.append((gdate, line))
    return _OpponentDefense(allowed, league)


def _row_features(prior_played: List[dict], rest_days: float,
                  is_home: int, games_played: int) -> Dict[str, float]:
    """Build the leakage-free feature row from a player's prior played games."""
    feats: Dict[str, float] = {}
    for stat in _FORM_STATS:
        col = _BOX_COL[stat]
        vals = [_num(g.get(col)) for g in prior_played]
        feats[f"l5_{stat}"]   = _mean(vals[-5:])
        feats[f"l10_{stat}"]  = _mean(vals[-10:])
        feats[f"std_{stat}"]  = _mean(vals)              # season-to-date
        feats[f"ewma_{stat}"] = _ewma(vals)
        feats[f"prev_{stat}"] = vals[-1] if vals else 0.0
    feats["rest_days"]     = rest_days
    feats["is_home"]       = float(is_home)
    feats["games_played"]  = float(games_played)
    return feats


# ── dataset construction ──────────────────────────────────────────────────────

def build_pergame_dataset(
    gamelog_dir: Optional[str] = None,
    min_prior: int = 6,
) -> Tuple[List[dict], List[str]]:
    """Build the per-game training set from every player gamelog.

    Each emitted row holds leakage-free pre-game features and the realised
    target_{stat} values for one game.  A game is used as a row only when the
    player actually played (>= _MIN_PLAYED minutes) and has at least
    ``min_prior`` prior played games for stable rolling features.

    Returns:
        (rows, feature_cols) — rows are dicts with the feature columns,
        target_{stat} columns, and a 'date' key for the temporal split.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    feature_cols = feature_columns()
    rows: List[dict] = []

    # Leakage-free opponent-defence model, built from all gamelogs first.
    oppdef = build_opponent_defense(gamelog_dir)

    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue

        # Sort chronologically; keep games with a parseable date.
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED

            if played and len(prior_played) >= min_prior:
                rest = 3.0
                if idx > 0:
                    delta = (gdate - dated[idx - 1][0]).days
                    rest = float(min(max(delta, 0), 10))
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                feats = _row_features(prior_played, rest, is_home, len(prior_played))
                feats.update(oppdef.factors(_opponent_from_matchup(matchup), gdate))
                row = {c: feats[c] for c in feature_cols}
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                row["date"] = gdate.isoformat()
                rows.append(row)

            if played:
                prior_played.append(game)

    return rows, feature_cols


# ── training ──────────────────────────────────────────────────────────────────

def train_pergame_models(
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    *,
    min_prior: int = 6,
    holdout_frac: float = 0.2,
    val_frac: float = 0.15,
) -> dict:
    """Train one XGBoost regressor per stat on the per-game dataset.

    Three-way temporal split — train / validation / holdout, in chronological
    order. The validation slice drives early stopping (the model adds trees
    only while validation error keeps falling), which curbs overfitting
    without ever touching the holdout. The most recent ``holdout_frac`` of
    games is the honest out-of-sample test.

    Returns a metrics dict ``{stat: {train_r2, holdout_r2, train_mae,
    holdout_mae, gap, best_iteration}}`` and writes props_pg_{stat}.json.
    """
    import joblib
    import lightgbm as lgb
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error, r2_score

    model_dir = model_dir or _MODEL_DIR
    rows, feature_cols = build_pergame_dataset(gamelog_dir, min_prior=min_prior)
    if len(rows) < 200:
        return {"status": "insufficient_data", "n_rows": len(rows)}

    rows.sort(key=lambda r: r["date"])           # temporal order
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    X_all = np.array([[r[c] for c in feature_cols] for r in rows], dtype=float)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]

    os.makedirs(model_dir, exist_ok=True)
    metrics: dict = {"n_rows": n, "n_train": train_end,
                     "n_val": val_end - train_end, "n_holdout": n - val_end,
                     "stats": {}}

    for stat in STATS:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]
        is_count = stat in ("stl", "blk")

        # Base learner 1 — XGBoost, regularised, early-stopped on the val slice.
        xgb_model = xgb.XGBRegressor(
            n_estimators=800, max_depth=3 if is_count else 4, learning_rate=0.04,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
            reg_lambda=2.0, reg_alpha=0.5, gamma=0.2, random_state=42,
            objective="count:poisson" if is_count else "reg:squarederror",
            early_stopping_rounds=40, eval_metric="mae",
        )
        xgb_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        # Base learner 2 — LightGBM, a different bias-variance tradeoff.
        lgb_model = lgb.LGBMRegressor(
            n_estimators=800, max_depth=3 if is_count else 4, learning_rate=0.04,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            min_child_samples=20, reg_lambda=2.0, reg_alpha=0.5, random_state=42,
            objective="poisson" if is_count else "regression",
            n_jobs=-1, verbosity=-1,
        )
        lgb_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(40, verbose=False)])

        # Blend = mean of the two base learners — what predict_pergame uses.
        def _blend(X):
            return 0.5 * (xgb_model.predict(X) + lgb_model.predict(X))

        xgb_ho, lgb_ho = xgb_model.predict(X_ho), lgb_model.predict(X_ho)
        blend_ho = 0.5 * (xgb_ho + lgb_ho)
        blend_tr = _blend(X_tr)

        m = {
            "holdout_r2":      round(float(r2_score(y_ho, blend_ho)), 4),
            "holdout_mae":     round(float(mean_absolute_error(y_ho, blend_ho)), 4),
            "train_r2":        round(float(r2_score(y_tr, blend_tr)), 4),
            "xgb_holdout_r2":  round(float(r2_score(y_ho, xgb_ho)), 4),
            "lgb_holdout_r2":  round(float(r2_score(y_ho, lgb_ho)), 4),
        }
        m["gap"] = round(m["train_r2"] - m["holdout_r2"], 4)
        m["ensemble_lift"] = round(m["holdout_r2"] - max(m["xgb_holdout_r2"],
                                                         m["lgb_holdout_r2"]), 4)
        metrics["stats"][stat] = m
        xgb_model.save_model(os.path.join(model_dir, f"props_pg_{stat}.json"))
        joblib.dump(lgb_model, os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl"))
        print(f"  [prop_pergame] {stat.upper():4s} blend R²={m['holdout_r2']:.3f} "
              f"MAE={m['holdout_mae']:.2f}  (xgb={m['xgb_holdout_r2']:.3f}, "
              f"lgb={m['lgb_holdout_r2']:.3f}, lift={m['ensemble_lift']:+.3f})")

    metrics["feature_cols"] = feature_cols
    with open(os.path.join(model_dir, "props_pergame_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    return metrics


# ── inference ─────────────────────────────────────────────────────────────────

def load_pergame_model(stat: str, model_dir: Optional[str] = None) -> list:
    """Load the per-game base learners (XGBoost + LightGBM) for a stat.

    Returns a list of fitted models — empty when none are trained. The blend
    of whatever is present is what predict_pergame uses.
    """
    model_dir = model_dir or _MODEL_DIR
    models: list = []
    xgb_path = os.path.join(model_dir, f"props_pg_{stat}.json")
    if os.path.exists(xgb_path):
        try:
            import xgboost as xgb
            m = xgb.XGBRegressor()
            m.load_model(xgb_path)
            models.append(m)
        except Exception:
            pass
    lgb_path = os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl")
    if os.path.exists(lgb_path):
        try:
            import joblib
            models.append(joblib.load(lgb_path))
        except Exception:
            pass
    return models


def predict_pergame(stat: str, feature_row: Dict[str, float],
                    model_dir: Optional[str] = None) -> Optional[float]:
    """Predict one stat for one game — the mean of the per-game base learners."""
    import numpy as np

    models = load_pergame_model(stat, model_dir)
    if not models:
        return None
    cols = feature_columns()
    X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    preds = [float(m.predict(X)[0]) for m in models]
    return round(max(sum(preds) / len(preds), 0.0), 2)


# ── live prediction ───────────────────────────────────────────────────────────

# Process-level cache — building the opponent-defence model globs every
# gamelog, so it must not be rebuilt on every predict_props() call.
_OPP_DEF_CACHE: Dict[str, _OpponentDefense] = {}


def _get_opponent_defense(gamelog_dir: str) -> _OpponentDefense:
    """Return the (process-cached) opponent-defence model for a gamelog dir."""
    if gamelog_dir not in _OPP_DEF_CACHE:
        _OPP_DEF_CACHE[gamelog_dir] = build_opponent_defense(gamelog_dir)
    return _OPP_DEF_CACHE[gamelog_dir]


def build_prediction_row(
    player_id,
    opp_team: str,
    season: str,
    *,
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    min_prior: int = 6,
) -> Optional[Dict[str, float]]:
    """Build the per-game feature row for a player's UPCOMING game.

    Reads the player's season gamelog, treats every played game as prior
    form, and assembles the same feature row the models were trained on.
    Returns None when the gamelog is missing or the player has too little
    history — the caller then falls back to the legacy models.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        return None
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(games, list):
        return None

    dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
    dated.sort(key=lambda x: x[0])
    prior_played = [g for _d, g in dated if _num(g.get("MIN")) >= _MIN_PLAYED]
    if len(prior_played) < min_prior:
        return None

    feats = _row_features(prior_played, float(rest_days), int(is_home),
                          len(prior_played))
    factor_date = dated[-1][0] if dated else datetime.now()
    feats.update(_get_opponent_defense(gamelog_dir).factors(opp_team, factor_date))
    return feats


def predict_player_pergame(
    player_id,
    opp_team: str,
    season: str,
    *,
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """Predict all 7 prop stats for a player's upcoming game.

    Returns ``{stat: value}`` from the honest per-game models, or None when
    the per-game models or the player's gamelog are unavailable.
    """
    row = build_prediction_row(player_id, opp_team, season, is_home=is_home,
                               rest_days=rest_days, gamelog_dir=gamelog_dir)
    if row is None:
        return None
    out: Dict[str, float] = {}
    for stat in STATS:
        val = predict_pergame(stat, row, model_dir)
        if val is None:
            return None
        out[stat] = val
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Per-game prop models")
    ap.add_argument("--train", action="store_true", help="Build dataset + train all stats")
    args = ap.parse_args()
    if args.train:
        print(json.dumps(train_pergame_models(), indent=2))
    else:
        ap.print_help()
