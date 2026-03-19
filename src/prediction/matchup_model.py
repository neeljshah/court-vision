"""
matchup_model.py — Defensive matchup impact model (M22).

Predicts how much a specific defender suppresses an offensive player's scoring,
using observable hustle and tracking stats.

Architecture
------------
Training target: ``on_off_diff`` (team net +/- delta when defender is on vs off court)
— a real, observable measure of defensive quality.

Features per defender:
  deflections_pg, screen_assists_pg, contested_shots_pg,
  charges_per_game, box_outs, minutes_on, partial_possessions (matchup volume)

At inference time, outputs adjusted ``pts_per_100`` for (off_player, def_player):
  adjusted_pts = off_player_base * (1 - clamp(predicted_on_off_diff * 0.015, -0.12, 0.12))

CLI
---
  python src/prediction/matchup_model.py --train
  python src/prediction/matchup_model.py --predict "Stephen Curry" "Jrue Holiday"

Public API
----------
  train_matchup_model(seasons, force) -> dict
  predict_matchup(off_player, def_player, season) -> dict
  get_defender_quality(player_name, season) -> dict
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_EXT_CACHE  = os.path.join(PROJECT_DIR, "data", "external")

_MODEL_PATH = os.path.join(_MODEL_DIR, "matchup_model.json")
_META_PATH  = os.path.join(_MODEL_DIR, "matchup_model_meta.json")

_LEAGUE_AVG_PTS_PER_100 = 113.0
_MAX_ADJUSTMENT          = 0.12      # ±12% max pts adjustment
_OO_SCALE                = 0.015     # 1 pt of on/off diff → 1.5% pts change


# ─────────────────────────────────────────────────────────────────────────────
# Feature helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    """Lowercase + strip accents for fuzzy player name matching."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name)
    return re.sub(r"[^a-z ]", "", nfkd.lower()).strip()


def _load_hustle(season: str) -> dict:
    """Return {player_id: hustle_record} for season."""
    path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    return {r["player_id"]: r for r in records if "player_id" in r}


def _load_on_off(season: str) -> dict:
    """Return {player_id: on_off_record} for season."""
    path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    return {r["player_id"]: r for r in records if "player_id" in r}


def _load_matchups(season: str) -> list:
    """Return raw matchup list for season."""
    path = os.path.join(_NBA_CACHE, f"matchups_{season}.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_synergy_def_avg(team_abbr: str, season: str) -> float:
    """Return average defensive PPP across all play types for a team, or 0.0 on miss.
    Lower = better defense. Play type values: 'Isolation', 'PRBallHandler', 'Spotup', etc."""
    path = os.path.join(_NBA_CACHE, f"synergy_defensive_all_{season}.json")
    try:
        rows = json.load(open(path, encoding="utf-8"))
        team_rows = [r for r in rows
                     if r.get("team_abbreviation", "").upper() == team_abbr.upper()]
        if not team_rows:
            return 0.0
        ppps = [float(r.get("ppp", 0.0)) for r in team_rows if r.get("ppp") is not None]
        return round(float(sum(ppps) / len(ppps)), 4) if ppps else 0.0
    except Exception:
        return 0.0


def _load_team_abbr_for_player(player_id: int, hustle: dict) -> str:
    """Return team abbreviation for a player from hustle dict, or '' on miss."""
    r = hustle.get(player_id, {})
    return r.get("team_abbreviation", "")


def _load_player_name_map(season: str) -> dict:
    """Return {norm_name: player_id} from hustle stats (best available league-wide list)."""
    hustle = _load_hustle(season)
    name_map: dict = {}
    for pid, r in hustle.items():
        name = r.get("player_name", "")
        if name:
            name_map[_norm(name)] = pid
    return name_map


def _build_defender_features(
    def_player_id: int,
    hustle: dict,
    on_off: dict,
    matchups: list,
    season: str = "2024-25",
) -> dict:
    """
    Build feature dict for a single defender.

    Args:
        def_player_id: Numeric player ID.
        hustle: {player_id: hustle_record} for this season.
        on_off: {player_id: on_off_record} for this season.
        matchups: raw matchup list for this season.
        season: Season string for synergy lookup.

    Returns:
        Feature dict (all floats, 0.0 fallback for missing data).
    """
    h = hustle.get(def_player_id, {})
    o = on_off.get(def_player_id, {})
    gp = max(float(h.get("games_played", 1) or 1), 1.0)

    # Per-game hustle rates
    deflections_pg     = float(h.get("deflections_pg", 0.0) or 0.0)
    screen_assists_pg  = float(h.get("screen_assists", 0.0) or 0.0) / gp
    contested_shots_pg = float(h.get("contested_shots", 0.0) or 0.0) / gp
    charges_pg         = float(h.get("charges_per_game", 0.0) or 0.0)
    box_outs_pg        = float(h.get("box_outs", 0.0) or 0.0) / gp

    # On/off impact
    on_off_diff        = float(o.get("on_off_diff", 0.0) or 0.0)
    on_court_pm        = float(o.get("on_court_plus_minus", 0.0) or 0.0)
    minutes_on         = float(o.get("minutes_on", 0.0) or 0.0)

    # Matchup volume (total partial possessions this defender accumulated)
    poss = sum(
        float(m.get("partial_possessions", 0.0) or 0.0)
        for m in matchups
        if m.get("def_player_id") == def_player_id
    )

    # Phase 4.6: team-level synergy defensive PPP (average across all play types)
    team_abbr = _load_team_abbr_for_player(def_player_id, hustle)
    team_synergy_def_ppp = _load_synergy_def_avg(team_abbr, season) if team_abbr else 0.0

    return {
        "deflections_pg":       deflections_pg,
        "screen_assists_pg":    round(screen_assists_pg, 3),
        "contested_shots_pg":   round(contested_shots_pg, 3),
        "charges_pg":           charges_pg,
        "box_outs_pg":          round(box_outs_pg, 3),
        "on_court_pm":          on_court_pm,
        "minutes_on":           minutes_on,
        "matchup_poss":         round(poss, 1),
        "team_synergy_def_ppp": round(team_synergy_def_ppp, 4),
    }


_FEAT_COLS = [
    "deflections_pg", "screen_assists_pg", "contested_shots_pg",
    "charges_pg", "box_outs_pg", "on_court_pm", "minutes_on", "matchup_poss",
    "team_synergy_def_ppp",
]


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def train_matchup_model(
    seasons: Optional[list] = None,
    force: bool = False,
) -> dict:
    """
    Train XGBoost regressor to predict on_off_diff from hustle/tracking features.

    Args:
        seasons: e.g. ["2022-23", "2023-24", "2024-25"]
        force: Retrain even if model already saved.

    Returns:
        {"mae": float, "r2": float, "n_train": int}
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    if not force and os.path.exists(_MODEL_PATH):
        print("[matchup] Model already trained. Use --force to retrain.")
        return {}

    import numpy as np
    import pandas as pd
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error, r2_score

    all_rows: list = []
    for season in seasons:
        hustle   = _load_hustle(season)
        on_off   = _load_on_off(season)
        matchups = _load_matchups(season)

        if not hustle or not on_off:
            print(f"[matchup] {season}: missing hustle or on/off data, skipping")
            continue

        for def_id, oo_rec in on_off.items():
            feats = _build_defender_features(def_id, hustle, on_off, matchups, season)
            feats["on_off_diff"] = oo_rec.get("on_off_diff", 0.0)
            feats["season"] = season
            all_rows.append(feats)

    if len(all_rows) < 50:
        print(f"[matchup] Not enough data ({len(all_rows)} rows). Abort.")
        return {}

    df = pd.DataFrame(all_rows)
    train_seasons = seasons[:-1]
    test_season   = seasons[-1]
    train_df = df[df["season"].isin(train_seasons)]
    test_df  = df[df["season"] == test_season]

    X_train = train_df[_FEAT_COLS].fillna(0.0).values
    X_test  = test_df[_FEAT_COLS].fillna(0.0).values
    y_train = train_df["on_off_diff"].values
    y_test  = test_df["on_off_diff"].values

    m = xgb.XGBRegressor(
        n_estimators=150,
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

    os.makedirs(_MODEL_DIR, exist_ok=True)
    m.save_model(_MODEL_PATH)
    meta = {
        "mae": round(mae, 3),
        "r2":  round(r2, 3),
        "n_train": len(train_df),
        "n_test":  len(test_df),
        "features": _FEAT_COLS,
        "target": "on_off_diff",
        "seasons_trained": seasons,
    }
    with open(_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(
        f"[matchup] Training complete — MAE: {mae:.3f}  R²: {r2:.3f}  "
        f"(train={len(train_df)}, test={len(test_df)})"
    )
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Inference
# ─────────────────────────────────────────────────────────────────────────────

def _load_model():
    """Load the trained XGBoost model. Returns None if not trained."""
    if not os.path.exists(_MODEL_PATH):
        return None
    import xgboost as xgb
    m = xgb.XGBRegressor()
    m.load_model(_MODEL_PATH)
    return m


def get_defender_quality(
    player_name: str,
    season: str = "2024-25",
) -> dict:
    """
    Look up or predict the defensive quality score for a player.

    Returns:
        {player_id, player_name, on_off_diff, predicted_on_off_diff,
         deflections_pg, contested_shots_pg, adjustment_pct}
    """
    hustle   = _load_hustle(season)
    on_off   = _load_on_off(season)
    matchups = _load_matchups(season)
    name_map = _load_player_name_map(season)

    key = _norm(player_name)
    pid = name_map.get(key)
    # Fuzzy match if exact fails
    if pid is None:
        for k, v in name_map.items():
            if key in k or k in key:
                pid = v
                break

    if pid is None:
        return {"player_name": player_name, "found": False, "adjustment_pct": 0.0}

    feats = _build_defender_features(pid, hustle, on_off, matchups, season)
    actual_oo = float(on_off.get(pid, {}).get("on_off_diff", 0.0))

    model = _load_model()
    if model is not None:
        import numpy as np
        X = np.array([[feats[c] for c in _FEAT_COLS]], dtype=float)
        predicted_oo = float(model.predict(X)[0])
    else:
        predicted_oo = actual_oo

    # Use actual if available, fall back to model prediction
    oo = actual_oo if actual_oo != 0.0 else predicted_oo
    adj = max(-_MAX_ADJUSTMENT, min(_MAX_ADJUSTMENT, oo * _OO_SCALE))

    return {
        "player_id":            pid,
        "player_name":          player_name,
        "found":                True,
        "on_off_diff":          round(actual_oo, 2),
        "predicted_on_off_diff": round(predicted_oo, 2),
        "deflections_pg":       feats["deflections_pg"],
        "contested_shots_pg":   feats["contested_shots_pg"],
        "adjustment_pct":       round(adj * 100, 1),   # e.g. -5.2 means 5.2% fewer pts
    }


def predict_matchup(
    off_player: str,
    def_player: str,
    season: str = "2024-25",
) -> dict:
    """
    Predict adjusted pts/100 for an offensive player against a specific defender.

    Args:
        off_player: Offensive player full name (e.g. "Stephen Curry")
        def_player: Defensive player full name (e.g. "Jrue Holiday")
        season:     Season string (e.g. "2024-25")

    Returns:
        {off_player, def_player, base_pts_per_100, adjusted_pts_per_100,
         adjustment_pct, defender_quality}
    """
    # Get offensive player's base scoring rate (pts/100 = pts/game * 40/36 approx)
    hustle_map = _load_player_name_map(season)

    # Look up off player in NBA stats cache (reuse player avgs if cached)
    off_avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    off_pts: Optional[float] = None
    if os.path.exists(off_avgs_path):
        with open(off_avgs_path, encoding="utf-8") as f:
            avgs = json.load(f)
        key = _norm(off_player)
        # avgs is a dict keyed by norm_name → record dict
        if isinstance(avgs, dict):
            row = avgs.get(key) or next(
                (v for k, v in avgs.items() if key in k or k in key), None
            )
            if row:
                off_pts = float(row.get("pts", row.get("season_pts", 0.0)) or 0.0)
        else:
            for row in avgs:
                if _norm(row.get("player_name", "")) == key or key in _norm(row.get("player_name", "")):
                    off_pts = float(row.get("pts", row.get("season_pts", 0.0)) or 0.0)
                    break

    # Fallback: league average
    if not off_pts:
        off_pts = 15.0

    base_per_100 = off_pts * (100.0 / 36.0)  # pts/game → pts/100 poss approx

    dq = get_defender_quality(def_player, season)
    adj = dq.get("adjustment_pct", 0.0) / 100.0
    adjusted = base_per_100 * (1.0 - adj)

    return {
        "off_player":           off_player,
        "def_player":           def_player,
        "season":               season,
        "base_pts_per_game":    round(off_pts, 1),
        "base_pts_per_100":     round(base_per_100, 1),
        "adjusted_pts_per_100": round(adjusted, 1),
        "adjustment_pct":       dq.get("adjustment_pct", 0.0),
        "defender_quality":     dq,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Matchup model M22")
    ap.add_argument("--train",   action="store_true", help="Train matchup model")
    ap.add_argument("--force",   action="store_true", help="Force retrain")
    ap.add_argument("--predict", nargs=2, metavar=("OFF_PLAYER", "DEF_PLAYER"),
                    help="Predict pts for off_player vs def_player")
    ap.add_argument("--season",  default="2024-25")
    args = ap.parse_args()

    if args.train:
        result = train_matchup_model(force=args.force)
        print(json.dumps(result, indent=2))
    elif args.predict:
        off_p, def_p = args.predict
        result = predict_matchup(off_p, def_p, args.season)
        print(json.dumps(result, indent=2))
    else:
        ap.print_help()
