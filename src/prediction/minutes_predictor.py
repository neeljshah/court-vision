"""
minutes_predictor.py — Minutes-aware projection combining DNP, load management,
and minutes floor models into a single expected-minutes distribution.

Public API
----------
    MinutesPredictor.predict_minutes_distribution(player_id, game_context) -> dict
    MinutesPredictor.expected_minutes(player_id, game_context) -> float
"""
from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import re
import sys
from collections import defaultdict
from typing import Dict, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

log = logging.getLogger(__name__)

# Load-management feature keys (from load_management.pkl coefs)
_LM_FEAT_KEYS = [
    "age", "games_played", "minutes_per_game", "is_b2b",
    "days_rest", "games_last_7", "usage_rate", "injury_history",
    "contract_year", "is_star",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_min(val) -> Optional[float]:
    if val is None or val == "":
        return None
    s = str(val).strip()
    if s in ("0", "0:00", "None", "null"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return None
    try:
        return float(s)
    except Exception:
        return None


def _load_gamelogs_for_player(player_id: int) -> list:
    """Return list of (game_date_str, minutes_float_or_None) sorted ascending."""
    pid = str(player_id)
    pattern = re.compile(rf"gamelog_full_{re.escape(pid)}_[\d-]+\.json$")
    files = glob.glob(os.path.join(_NBA_CACHE, f"gamelog_full_{pid}_*.json"))
    games: list = []
    for fpath in files:
        if not pattern.match(os.path.basename(fpath)):
            continue
        try:
            data = json.load(open(fpath, encoding="utf-8"))
            rows = data if isinstance(data, list) else list(data.values())
        except Exception:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            date = row.get("game_date", row.get("GAME_DATE", ""))
            minutes = _parse_min(row.get("min", row.get("MIN")))
            if date:
                games.append((str(date), minutes))
    games.sort(key=lambda x: x[0])
    return games


def _recent_min_features(games: list) -> dict:
    """Build DNP/minutes features from gamelog list."""
    played = [(d, m) for d, m in games if m is not None and m > 0]
    recent5 = [m for _, m in played[-5:]] if played else []
    recent10 = [m for _, m in played[-10:]] if played else []
    recent20 = [m for _, m in played[-20:]] if played else []

    recent_min_avg = float(np.mean(recent5)) if recent5 else 24.0
    min_l10 = float(np.mean(recent10)) if recent10 else recent_min_avg
    min_l20 = float(np.mean(recent20)) if recent20 else min_l10

    # Trend: slope over last 10 raw entries (DNPs = 0)
    window10 = [m if (m is not None and m > 0) else 0.0 for _, m in games[-10:]]
    if len(window10) >= 3:
        min_trend = float(np.polyfit(np.arange(len(window10), dtype=float), window10, 1)[0])
    else:
        min_trend = 0.0

    # Variance among played games
    var_full = float(np.var(recent5)) if len(recent5) > 1 else 4.0

    n_total = len(games)
    n_played = len(played)
    season_gp_pct = n_played / max(n_total, 1)

    return {
        "recent_min_avg": recent_min_avg,
        "min_l5": recent_min_avg,
        "min_l10": min_l10,
        "min_l20": min_l20,
        "min_trend": min_trend,
        "season_gp_pct": season_gp_pct,
        "var_full": var_full,
        "n_played": n_played,
    }


# ── Main class ────────────────────────────────────────────────────────────────

class MinutesPredictor:
    """
    Combines DNP predictor, load management model, and minutes floor model
    to produce a full expected-minutes distribution for any player/game context.
    """

    def __init__(self, model_dir: str = _MODEL_DIR) -> None:
        self._model_dir = model_dir
        self._dnp: Optional[dict] = None
        self._lm: Optional[dict] = None
        self._mf: Optional[dict] = None

    # ── Lazy model loaders ────────────────────────────────────────────────

    def _load_dnp(self) -> dict:
        if self._dnp is None:
            path = os.path.join(self._model_dir, "dnp_model.pkl")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._dnp = pickle.load(f)
            else:
                self._dnp = {}
        return self._dnp

    def _load_lm(self) -> dict:
        if self._lm is None:
            # Prefer .pkl (has coefs dict); fall back to .json
            pkl_path = os.path.join(self._model_dir, "load_management.pkl")
            json_path = os.path.join(self._model_dir, "load_management.json")
            if os.path.exists(pkl_path):
                with open(pkl_path, "rb") as f:
                    self._lm = pickle.load(f)
            elif os.path.exists(json_path):
                self._lm = json.load(open(json_path))
            else:
                self._lm = {}
        return self._lm

    def _load_mf(self) -> dict:
        if self._mf is None:
            path = os.path.join(self._model_dir, "minutes_floor.pkl")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._mf = pickle.load(f)
            else:
                self._mf = {}
        return self._mf

    # ── Internal scorers ──────────────────────────────────────────────────

    def _score_dnp(self, min_feats: dict, game_context: dict) -> float:
        """Return P(DNP) using logistic model + scaler."""
        dnp = self._load_dnp()
        if not dnp or "model" not in dnp:
            return 0.05

        # Clamp recent_min_avg: if player is a known regular (>20 min avg) use
        # raw features without the scaler bias that scores high-usage players as DNP.
        recent_min_avg = min_feats.get("recent_min_avg", 24.0)
        min_trend = min_feats.get("min_trend", 0.0)
        games_in_last_7 = float(game_context.get("games_in_last_7",
                                 min(int(min_feats.get("n_played", 3) / 10), 4)))
        season_gp_pct = min_feats.get("season_gp_pct", 0.85)

        feat = np.array([[recent_min_avg, min_trend, games_in_last_7, season_gp_pct, 0.0]])
        try:
            scaler = dnp.get("scaler")
            if scaler is not None:
                feat_s = scaler.transform(feat)
            else:
                feat_s = feat
            prob = float(dnp["model"].predict_proba(feat_s)[0][1])
        except Exception as exc:
            log.debug("DNP score error: %s", exc)
            return 0.05

        # Guard: the DNP scaler was trained on data that includes DNP rows (MIN=0),
        # so for healthy high-minute regulars the scaler shift can push the score
        # implausibly high.  Only apply the recalibration guard when recent_min_avg
        # is high (>25) AND season_gp_pct is very high (healthy regular) — those are
        # the exactly the cases where the scaler miscalibrates.
        if recent_min_avg > 25.0 and season_gp_pct >= 0.90:
            injury_prior = max(0.0, 1.0 - season_gp_pct)
            prob = min(prob, injury_prior + 0.15)

        return float(np.clip(prob, 0.0, 1.0))

    def _score_load_mgmt(self, min_feats: dict, game_context: dict) -> float:
        """Return P(load-managed = reduced minutes game) via heuristic logistic."""
        lm = self._load_lm()
        coefs = lm.get("coefs", {})
        intercept = float(lm.get("intercept", -3.5))

        feats: dict = {
            "age": float(game_context.get("age", 0)),
            "games_played": float(min_feats.get("n_played", 50)),
            "minutes_per_game": min_feats.get("recent_min_avg", 24.0),
            "is_b2b": float(game_context.get("is_b2b", 0)),
            "days_rest": float(game_context.get("rest_days", 2)),
            "games_last_7": float(game_context.get("games_in_last_7",
                                   min(int(min_feats.get("n_played", 3) / 10), 4))),
            "usage_rate": float(game_context.get("usage_rate", 0)),
            "injury_history": float(game_context.get("injury_history", 0)),
            "contract_year": float(game_context.get("contract_year", 0)),
            "is_star": 1.0 if float(game_context.get("usage_rate", 0)) > 28 else 0.0,
        }

        score = intercept + sum(coefs.get(k, 0.0) * v for k, v in feats.items())
        prob = 1.0 / (1.0 + np.exp(-score))
        return float(np.clip(prob, 0.0, 1.0))

    def _score_proj_minutes(self, min_feats: dict, game_context: dict) -> float:
        """Use minutes_floor XGBoost to predict baseline full-load minutes."""
        mf = self._load_mf()
        model = mf.get("model")
        if model is None:
            return min_feats.get("recent_min_avg", 24.0)

        min_l5 = min_feats.get("min_l5", 24.0)
        min_l10 = min_feats.get("min_l10", min_l5)
        min_l20 = min_feats.get("min_l20", min_l10)
        rest = min(max(float(game_context.get("rest_days", 1)), 0), 5)
        is_b2b = int(game_context.get("is_b2b", 0))

        X = np.array([[min_l5, min_l10, min_l20, rest, is_b2b]])
        try:
            proj = float(model.predict(X)[0])
        except Exception:
            proj = min_l5
        return float(np.clip(proj, 0.0, 42.0))

    # ── Public API ────────────────────────────────────────────────────────

    def predict_minutes_distribution(
        self, player_id: int, game_context: dict
    ) -> Dict:
        """
        Returns full minutes distribution dict:
            expected_minutes, floor, ceiling, p_dnp, p_load_mgmt,
            p_full_load, minutes_std
        """
        games = _load_gamelogs_for_player(player_id)
        if not games:
            # Fallback for players with no cached gamelogs
            base_avg = float(game_context.get("season_avg_minutes", 28.0))
            return {
                "expected_minutes": base_avg * 0.9,
                "floor": base_avg * 0.6,
                "ceiling": min(42.0, base_avg * 1.1),
                "p_dnp": 0.05,
                "p_load_mgmt": 0.05,
                "p_full_load": 0.90,
                "minutes_std": 4.0,
            }

        min_feats = _recent_min_features(games)
        recent_avg = min_feats["recent_min_avg"]

        p_dnp = self._score_dnp(min_feats, game_context)
        p_load_raw = self._score_load_mgmt(min_feats, game_context)

        # Ensure probabilities sum ≤ 1
        p_load = float(np.clip(p_load_raw, 0.0, max(0.0, 1.0 - p_dnp)))
        p_full = float(np.clip(1.0 - p_dnp - p_load, 0.0, 1.0))

        # Full-load projected minutes via XGBoost model
        proj_full = self._score_proj_minutes(min_feats, game_context)

        # Load-managed minutes: roughly 8 fewer minutes
        load_managed_min = max(0.0, proj_full - 8.0)

        # Expected minutes across all scenarios
        expected = p_full * proj_full + p_load * load_managed_min + p_dnp * 0.0

        # Floor = minutes_floor model output (hard lower bound when playing)
        floor_min = float(np.clip(proj_full * 0.70, 0.0, proj_full))

        # Ceiling = capped at 42
        ceiling_min = float(min(42.0, proj_full * 1.05))

        # Std dev via mixture-of-Gaussians variance
        var_full = min_feats.get("var_full", 9.0)
        var_load = (load_managed_min * 0.15) ** 2
        var_dnp = 0.0
        minutes_std = float(np.sqrt(
            p_full * (var_full + (proj_full - expected) ** 2)
            + p_load * (var_load + (load_managed_min - expected) ** 2)
            + p_dnp * (expected ** 2)  # DNP scenario: 0 - expected
        ))

        return {
            "expected_minutes": round(expected, 2),
            "floor": round(floor_min, 2),
            "ceiling": round(ceiling_min, 2),
            "p_dnp": round(p_dnp, 4),
            "p_load_mgmt": round(p_load, 4),
            "p_full_load": round(p_full, 4),
            "minutes_std": round(minutes_std, 2),
        }

    def expected_minutes(self, player_id: int, game_context: dict) -> float:
        """Convenience: single expected-minutes float."""
        dist = self.predict_minutes_distribution(player_id, game_context)
        return dist["expected_minutes"]
