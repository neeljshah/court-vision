"""serve_ridge_point.py -- Leak-free ridge POINT estimate for live team score.

CONTRACT (expected by src/prediction/live_engine.py):
    predict_serve_ridge(snap, as_of=None) -> {"home_final": float, "away_final": float} | None

The returned dict is injected by live_engine as the ``ridge_point`` arg to
``project_unified`` -> ``project_score_ensemble``.  ``None`` means the
artifact is unavailable or the snapshot can't be featurized; live_engine then
falls back to sim-mean (``point_source="sim_fallback"``).

LEAK DISCIPLINE
---------------
* The artifact (data/models/ingame_serve_ridge.pkl) is trained ONLY on games
  strictly before its recorded cutoff date (see scripts/ingame/train_serve_ridge.py).
* At serve time we featurize ONLY the CURRENT live-snapshot in-game state:
  (home_score, away_score, elapsed time, four-factor rates accumulated SO FAR).
  We read NO future stat; we read NO as-of-today season aggregate for the
  current game.  The ``as_of`` parameter is accepted for API symmetry with
  other serve-time callers but is NOT used in the feature vector (no external
  data lookup is performed).
* Feature vector is IDENTICAL to TEAM_FEATS in eval_second_by_second.py:
      played_share, home_score, away_score, score_margin,
      pace_poss_per_min, home_efg, away_efg, home_tov_pct, away_tov_pct,
      home_ft_rate, away_ft_rate, game_remaining_sec

ARTIFACT SCHEMA (pickle)
-------------------------
    {
        "version": 1,
        "cutoff": "YYYY-MM-DD",
        "n_train": int,
        "feature_spec": [str, ...],  # must == TEAM_FEATS
        "grid_sec": [int, ...],
        "ridge_w": {                 # per-bucket weight vectors
            360: {"home": ndarray(F+1,), "away": ndarray(F+1,)},
            ...
        },
    }
"""
from __future__ import annotations

import os
import pickle
from typing import Any, Dict, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants — must mirror eval_second_by_second.TEAM_FEATS exactly.
# ---------------------------------------------------------------------------
TEAM_FEATS = [
    "played_share", "home_score", "away_score", "score_margin",
    "pace_poss_per_min", "home_efg", "away_efg", "home_tov_pct", "away_tov_pct",
    "home_ft_rate", "away_ft_rate", "game_remaining_sec",
]

# Grid in elapsed seconds (must match eval_second_by_second.GRID_SEC).
GRID_SEC = [360, 720, 1080, 1440, 1800, 2160, 2520]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_ARTIFACT_PATH = os.path.join(_ROOT, "data", "models", "ingame_serve_ridge.pkl")

# ---------------------------------------------------------------------------
# Module-level artifact cache (loaded once; thread-safe for read-only use).
# ---------------------------------------------------------------------------
_ARTIFACT: Optional[Dict[str, Any]] = None
_LOAD_FAILED: bool = False
# Allow tests to override the path without touching the real filesystem.
_ARTIFACT_PATH: str = _DEFAULT_ARTIFACT_PATH


def _load_artifact() -> Optional[Dict[str, Any]]:
    """Load and validate the persisted ridge artifact (module-level cache)."""
    global _ARTIFACT, _LOAD_FAILED
    if _ARTIFACT is not None:
        return _ARTIFACT
    if _LOAD_FAILED:
        return None
    path = _ARTIFACT_PATH
    if not os.path.exists(path):
        _LOAD_FAILED = True
        return None
    try:
        with open(path, "rb") as fh:
            obj = pickle.load(fh)
        # Validate schema
        if not isinstance(obj, dict):
            raise ValueError("artifact is not a dict")
        ridge_w = obj.get("ridge_w")
        if not isinstance(ridge_w, dict) or not ridge_w:
            raise ValueError("ridge_w missing or empty")
        feat_spec = obj.get("feature_spec", [])
        if feat_spec and list(feat_spec) != TEAM_FEATS:
            raise ValueError(
                f"feature_spec mismatch: artifact has {feat_spec}, expected {TEAM_FEATS}"
            )
        _ARTIFACT = obj
        return _ARTIFACT
    except Exception as exc:
        _LOAD_FAILED = True
        # Silently absorb — caller returns None and live_engine uses sim-mean.
        try:
            import warnings
            warnings.warn(
                f"[serve_ridge_point] artifact load failed ({exc!r}); "
                "team score will use sim-mean fallback.",
                stacklevel=2,
            )
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Clock parsing (mirrors state_featurizer._parse_clock_remaining)
# ---------------------------------------------------------------------------
def _parse_clock_remaining(clock: str) -> int:
    """Parse remaining clock string -> seconds.  Accepts 'MM:SS' or ISO 'PTmmMss.ssS'."""
    import re
    if not clock:
        return 0
    clock = str(clock).strip()
    iso = re.match(r"PT0?(\d+)M([\d.]+)S", clock)
    if iso:
        return int(int(iso.group(1)) * 60 + float(iso.group(2)))
    if ":" in clock:
        try:
            mm, ss = clock.split(":")
            return int(float(mm)) * 60 + int(float(ss))
        except (ValueError, TypeError):
            return 0
    try:
        return int(float(clock))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Ridge prediction helper (mirrors eval_second_by_second._ridge_pred)
# ---------------------------------------------------------------------------
def _ridge_pred(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Predict: prepend bias column and dot with weight vector."""
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return Xb @ w


# ---------------------------------------------------------------------------
# Featurizer: live snapshot -> TEAM_FEATS vector
# ---------------------------------------------------------------------------
def _featurize_snap(snap: Dict[str, Any]) -> Optional[np.ndarray]:
    """Produce a (1, F) feature array from a live snapshot.

    Only uses CURRENT in-game state fields from ``snap``; does NOT read any
    external data (no future info, no season aggregates for the live game).
    Returns None if the snapshot is missing required fields or has invalid values.
    """
    try:
        # Clock / elapsed time
        period = int(snap.get("period", 1) or 1)
        REG_PERIOD_LEN = 720
        OT_PERIOD_LEN = 300
        REG_GAME_LEN_SEC = 2880

        clock = snap.get("clock", "12:00") or "12:00"
        rem_in_period = _parse_clock_remaining(clock)
        period_len = REG_PERIOD_LEN if period <= 4 else OT_PERIOD_LEN
        elapsed_in_period = max(0, period_len - rem_in_period)

        if period <= 4:
            game_sec = REG_PERIOD_LEN * (period - 1) + elapsed_in_period
            game_total = REG_GAME_LEN_SEC
        else:
            game_sec = REG_GAME_LEN_SEC + OT_PERIOD_LEN * (period - 5) + elapsed_in_period
            game_total = REG_GAME_LEN_SEC + OT_PERIOD_LEN * (period - 4)

        game_rem = max(0, game_total - game_sec)
        if game_sec <= 0:
            return None  # too early to use ridge; no signal
        played_share = game_sec / game_total if game_total else 0.0

        # Scores
        home_score = float(snap.get("home_score", 0) or 0)
        away_score = float(snap.get("away_score", 0) or 0)
        score_margin = home_score - away_score

        # Pace: live snapshots usually don't carry team four-factors; use 0.0
        # for those fields (same as what featurize_live_snapshot does for the sim).
        pace_poss_per_min = float(snap.get("pace_poss_per_min", 0.0) or 0.0)
        home_efg = float(snap.get("home_efg", 0.0) or 0.0)
        away_efg = float(snap.get("away_efg", 0.0) or 0.0)
        home_tov_pct = float(snap.get("home_tov_pct", 0.0) or 0.0)
        away_tov_pct = float(snap.get("away_tov_pct", 0.0) or 0.0)
        home_ft_rate = float(snap.get("home_ft_rate", 0.0) or 0.0)
        away_ft_rate = float(snap.get("away_ft_rate", 0.0) or 0.0)

        feat = np.array([[
            played_share,
            home_score,
            away_score,
            score_margin,
            pace_poss_per_min,
            home_efg,
            away_efg,
            home_tov_pct,
            away_tov_pct,
            home_ft_rate,
            away_ft_rate,
            float(game_rem),
        ]], dtype=np.float64)

        if not np.all(np.isfinite(feat)):
            return None
        return feat, int(game_sec)

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def predict_serve_ridge(
    snap: Dict[str, Any],
    as_of: Optional[str] = None,  # noqa: ARG001 — accepted but not used
) -> Optional[Dict[str, float]]:
    """Predict the final home/away score from the current live snapshot.

    Uses the persisted per-bucket ridge artifact (trained on games strictly
    before its cutoff date).  Selects the bucket nearest (<=) the current
    game-elapsed time.

    Args:
        snap: canonical live snapshot dict (see src/data/live.py schema).
            Required keys: period, clock, home_score, away_score.
            Optional four-factor keys (home_efg, etc.) are used when present.
        as_of: accepted for API compatibility but NOT used in featurization
            (no external lookup; feature is current in-game state only).

    Returns:
        {"home_final": float, "away_final": float} on success, or None if:
          - the artifact is absent / unreadable,
          - the snapshot is missing required fields,
          - any ridge output is non-finite,
          - the game hasn't started (game_sec <= 0).
    """
    artifact = _load_artifact()
    if artifact is None:
        return None

    # CV_RIDGE_FF_FALLBACK (sweep INGAME_SIM HIGH, default OFF = byte-identical).
    # The ridge was trained on REAL accumulated in-game four-factors (pace/efg/
    # tov_pct/ft_rate, state_featurizer.py:618-667) but the canonical LIVE snapshot
    # (src/data/live.py) never emits them, so _featurize_snap zero-fills all 7 →
    # the projected team TOTAL is biased ~-23.5 pts LOW mid/late game (pace coef
    # +3.39 alone loses ~14.6 pts/side). The snapshot's per-player box carries only
    # pts/reb/ast/fg3m/stl/blk/tov/pf/min — NO fgm/fga/fta/oreb/dreb — so the four
    # factors CANNOT be reconstructed live. When ON, abstain (return None) if the
    # snapshot lacks the four-factor keys, so score_ensemble uses the un-biased sim
    # mean (point_source="sim_fallback", MAE ~10.9) instead of the ~22-MAE zeroed
    # ridge. Default OFF preserves today's (biased) zero-fill behavior byte-identically.
    if os.environ.get("CV_RIDGE_FF_FALLBACK", "0") == "1":
        _ff_keys = ("pace_poss_per_min", "home_efg", "away_efg", "home_tov_pct",
                    "away_tov_pct", "home_ft_rate", "away_ft_rate")
        if not any(k in snap for k in _ff_keys):
            return None

    result = _featurize_snap(snap)
    if result is None:
        return None
    feat, game_sec = result

    ridge_w = artifact["ridge_w"]

    # Select the nearest grid bucket that we've already reached (elapsed >= bucket).
    eligible = [t for t in sorted(ridge_w.keys()) if t <= game_sec]
    if not eligible:
        # Game is before the first grid bucket (< 6 min elapsed) — no ridge yet.
        return None
    bucket = max(eligible)

    bw = ridge_w.get(bucket)
    if bw is None:
        return None

    try:
        home_pred = float(_ridge_pred(bw["home"], feat)[0])
        away_pred = float(_ridge_pred(bw["away"], feat)[0])
    except Exception:
        return None

    if not (np.isfinite(home_pred) and np.isfinite(away_pred)):
        return None

    # Clamp to sane NBA final-score range (avoid wild extrapolations).
    home_pred = float(np.clip(home_pred, 60.0, 180.0))
    away_pred = float(np.clip(away_pred, 60.0, 180.0))

    # Floor each side at the current score: a counting final can never be
    # below the score already on the board.  Read the same snap fields the
    # featurizer used so the floor is always consistent with the feature vector.
    home_score = float(snap.get("home_score", 0) or 0)
    away_score = float(snap.get("away_score", 0) or 0)
    home_pred = max(home_pred, home_score)
    away_pred = max(away_pred, away_score)

    return {"home_final": home_pred, "away_final": away_pred}


__all__ = ["predict_serve_ridge"]
