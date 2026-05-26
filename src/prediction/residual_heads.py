"""src/prediction/residual_heads.py -- cycle R2_F (loop 5) + R3_A + R4_A + R10_M16.

Helper module: load + apply the 7 per-stat residual LightGBM heads trained
by train_residual_heads.py. Wired into live_engine.project_from_snapshot
at endQ3 (period=4) via _apply_residual_correction, at endQ2 (period=3)
via apply_residual_correction_endq2, and at endQ1 (period=2) via
apply_residual_correction_endq1.

Artifacts (endQ3): data/models/residual_heads/{pts,reb,ast,fg3m,stl,blk,tov}.lgb
Probe reference: scripts/probe_R2_F_residual_heads.py (SHIP=True)
Result: PTS MAE -0.0965, 7/7 stats win, WF 4/4 folds negative.

R10_M16 hot-hand streak features (this module ONLY -- endQ3 path):
  PER-STAT SHIP for fg3m / stl / blk / tov (4/4 WF folds positive).
  PTS / REB / AST keep the legacy 14-feature schema (probe REJECT).
  Streak inputs (z-score L3 vs L20, consec-above-mean, n_prior) come
  from src.prediction.streak_features; loader detects per-stat feature
  schema via data/models/residual_heads/<stat>_meta.json. Stats with no
  meta JSON fall back to the legacy 14-feature schema (back-compat).

Artifacts (endQ2): data/models/residual_heads_endq2/{pts,reb,ast,fg3m,stl,blk,tov}.lgb
Probe reference: scripts/probe_R3_A_residual_heads_endq2.py (SHIP=True)
Result: PTS MAE -0.1095, 7/7 stats win, WF 4/4 folds negative (-0.10 to -0.11).
Features: cur_{pts,reb,ast,fg3m,stl,blk,tov,pf}, min_through_q2,
          score_margin_abs, is_leading, pos_C, pos_F, pos_G.

Artifacts (endQ1): data/models/residual_heads_endq1/{pts,reb,ast,fg3m,stl,blk,tov}.lgb
Probe reference: scripts/probe_R4_A_residual_heads_endq1.py (SHIP=True)
Result: PTS MAE -0.1182, 7/7 stats win, WF 4/4 folds negative.
Features: same 14-feature schema as endQ2 but min_through_q1 (Q1 only).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
HEAD_DIR_ENDQ2 = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_endq2")
HEAD_DIR_ENDQ1 = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_endq1")
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Legacy 14-feature schema used by R2_F endQ3 heads. PER-STAT meta JSON
# (data/models/residual_heads/<stat>_meta.json) can override this on a
# per-stat basis to add R10_M16 streak features.
_LEGACY_ENDQ3_FEATURES: Tuple[str, ...] = (
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
)

# Module-level lazy caches.
_HEAD_CACHE: Optional[Dict[str, object]] = None
_HEAD_META_CACHE: Optional[Dict[str, Dict]] = None
_HEAD_CACHE_ENDQ2: Optional[Dict[str, object]] = None
_HEAD_CACHE_ENDQ1: Optional[Dict[str, object]] = None
_POSITIONS_CACHE: Optional[Dict[int, str]] = None


def load_heads() -> Dict[str, object]:
    """Load all available .lgb residual heads (lazy, cached).

    Returns {} if the artifact directory is missing or lightgbm is absent.
    Any individual missing/corrupt file is silently skipped.
    """
    global _HEAD_CACHE
    if _HEAD_CACHE is not None:
        return _HEAD_CACHE
    try:
        import lightgbm as lgb
    except ImportError:
        _HEAD_CACHE = {}
        return _HEAD_CACHE
    heads: Dict[str, object] = {}
    if os.path.isdir(HEAD_DIR):
        for stat in STATS:
            path = os.path.join(HEAD_DIR, f"{stat}.lgb")
            if os.path.exists(path):
                try:
                    heads[stat] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN residual_heads: could not load {path}: {exc}")
    _HEAD_CACHE = heads
    return _HEAD_CACHE


def load_head_metas() -> Dict[str, Dict]:
    """Load per-stat endQ3 head meta JSONs (lazy, cached).

    File format: data/models/residual_heads/<stat>_meta.json containing
    at minimum {"features": [name, ...]}. Stats without a meta JSON fall
    back to the legacy 14-feature schema at predict time.
    """
    global _HEAD_META_CACHE
    if _HEAD_META_CACHE is not None:
        return _HEAD_META_CACHE
    metas: Dict[str, Dict] = {}
    if os.path.isdir(HEAD_DIR):
        for stat in STATS:
            path = os.path.join(HEAD_DIR, f"{stat}_meta.json")
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        metas[stat] = json.load(fh) or {}
                except Exception as exc:
                    print(f"  WARN residual_heads: could not load meta {path}: {exc}")
    _HEAD_META_CACHE = metas
    return _HEAD_META_CACHE


def _feature_names_for_stat(stat: str) -> Tuple[str, ...]:
    """Return the feature schema for stat's endQ3 head.

    If a meta JSON declares a 'features' list, use it; otherwise fall back
    to the legacy 14-feature schema. This lets us extend ONLY fg3m/stl/blk/tov
    with R10_M16 streak features while pts/reb/ast keep the legacy schema.
    """
    metas = load_head_metas()
    meta = metas.get(stat) or {}
    features = meta.get("features")
    if isinstance(features, (list, tuple)) and features:
        return tuple(features)
    return _LEGACY_ENDQ3_FEATURES


def reset_head_caches() -> None:
    """Drop the lazy head + meta caches. Test-only."""
    global _HEAD_CACHE, _HEAD_META_CACHE, _HEAD_CACHE_ENDQ2, _HEAD_CACHE_ENDQ1
    _HEAD_CACHE = None
    _HEAD_META_CACHE = None
    _HEAD_CACHE_ENDQ2 = None
    _HEAD_CACHE_ENDQ1 = None


def load_heads_endq2() -> Dict[str, object]:
    """Load all available .lgb residual heads for endQ2 (lazy, cached).

    Returns {} if the artifact directory is missing or lightgbm is absent.
    Any individual missing/corrupt file is silently skipped.
    """
    global _HEAD_CACHE_ENDQ2
    if _HEAD_CACHE_ENDQ2 is not None:
        return _HEAD_CACHE_ENDQ2
    try:
        import lightgbm as lgb
    except ImportError:
        _HEAD_CACHE_ENDQ2 = {}
        return _HEAD_CACHE_ENDQ2
    heads: Dict[str, object] = {}
    if os.path.isdir(HEAD_DIR_ENDQ2):
        for stat in STATS:
            path = os.path.join(HEAD_DIR_ENDQ2, f"{stat}.lgb")
            if os.path.exists(path):
                try:
                    heads[stat] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN residual_heads_endq2: could not load {path}: {exc}")
    _HEAD_CACHE_ENDQ2 = heads
    return _HEAD_CACHE_ENDQ2


def _load_positions() -> Dict[int, str]:
    global _POSITIONS_CACHE
    if _POSITIONS_CACHE is not None:
        return _POSITIONS_CACHE
    try:
        from scripts.train_minute_trajectory import load_positions
        _POSITIONS_CACHE = load_positions() or {}
    except Exception:
        _POSITIONS_CACHE = {}
    return _POSITIONS_CACHE


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot flags matching probe logic."""
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def _build_base_feature_map(
    player: dict,
    margin: float,
    raw_margin: float,
    pos_c: float,
    pos_f: float,
    pos_g: float,
) -> Dict[str, float]:
    """Build the legacy 14-feature lookup map for one player at endQ3."""
    return {
        "cur_pts":          float(player.get("pts",  0) or 0),
        "cur_reb":          float(player.get("reb",  0) or 0),
        "cur_ast":          float(player.get("ast",  0) or 0),
        "cur_fg3m":         float(player.get("fg3m", 0) or 0),
        "cur_stl":          float(player.get("stl",  0) or 0),
        "cur_blk":          float(player.get("blk",  0) or 0),
        "cur_tov":          float(player.get("tov",  0) or 0),
        "cur_pf":           float(player.get("pf",   0) or 0),
        "min_through_q3":   float(player.get("min",  0) or 0),
        "score_margin_abs": float(margin),
        "is_leading":       float(raw_margin > 0),
        "pos_C":            float(pos_c),
        "pos_F":            float(pos_f),
        "pos_G":            float(pos_g),
    }


def apply_residual_correction(
    snap: dict,
    projs: Dict[Tuple[int, str], float],
) -> Dict[Tuple[int, str], float]:
    """Apply per-(player, stat) residual head correction to projections.

    For each (pid, stat) at endQ3, if a head exists, adds the head's
    predicted residual to the BASELINE projection. Correction is clipped to
    [-cur_stat, 2 * projected] so the adjusted value stays non-negative and
    doesn't balloon more than 2x the incoming projection.

    R10_M16 ship: per-stat schema selection. fg3m / stl / blk / tov heads
    additionally consume hot_streak / cold_streak / consec_above / n_prior
    streak features when their meta JSON declares them. pts / reb / ast
    heads always use the legacy 14-feature schema (probe REJECT for streaks).

    Parameters
    ----------
    snap : dict
        Canonical snapshot dict (same shape as live_engine uses). May
        include ``game_date`` (ISO 'YYYY-MM-DD') used for streak lookups.
    projs : dict[(pid, stat) -> float]
        Current projected_final values keyed by (player_id int, stat str).
        Updated copy is returned; caller's dict is not mutated.

    Returns
    -------
    dict[(pid, stat) -> float]
        Updated projections. Stats without a head artifact are unchanged.
    """
    heads = load_heads()
    if not heads:
        return projs

    try:
        import numpy as np
    except ImportError:
        return projs

    positions = _load_positions()

    # Lazy-load streak machinery only if any shipping head needs it.
    streak_stats_active: List[str] = []
    try:
        from src.prediction import streak_features as _sf
        for stat in heads:
            if stat in _sf.SHIP_STREAK_STATS:
                feat_names = _feature_names_for_stat(stat)
                if any(name in feat_names for name in _sf.STREAK_FEATURE_NAMES_PER_STAT[stat]):
                    streak_stats_active.append(stat)
    except Exception:
        _sf = None  # type: ignore[assignment]
        streak_stats_active = []

    histories: Dict[int, list] = {}
    target_date = None
    if streak_stats_active and _sf is not None:
        target_date = _sf.coerce_target_date(snap.get("game_date"))
        if target_date is not None:
            try:
                histories = _sf.load_player_histories()
            except Exception:
                histories = {}
        else:
            # No game_date => no streak inputs available. Zero-fill so the
            # head still evaluates (graceful no-op rather than skip).
            streak_stats_active = []

    home_pts = float(snap.get("home_score", 0) or 0)
    away_pts = float(snap.get("away_score", 0) or 0)
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", "") or "")
    away_team = str(snap.get("away_team", "") or "")

    out = dict(projs)

    for player in snap.get("players") or []:
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError, KeyError):
            continue

        team = str(player.get("team", "") or "")
        if team == home_team:
            raw_margin = home_pts - away_pts
        elif team == away_team:
            raw_margin = away_pts - home_pts
        else:
            raw_margin = 0.0

        pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

        base_map = _build_base_feature_map(
            player, margin, raw_margin, pos_c, pos_f, pos_g
        )

        # Pre-compute streak feature map for this player ONCE per snap,
        # gated to the active streak stats. Missing history -> zero-fill
        # so downstream feature lookup still finds the names.
        streak_map: Dict[str, float] = {}
        if streak_stats_active and _sf is not None and target_date is not None:
            history = histories.get(pid) or []
            for stat in streak_stats_active:
                if history:
                    streak_map.update(
                        _sf.compute_streak_features_for_stat(history, target_date, stat)
                    )
                else:
                    for name in _sf.STREAK_FEATURE_NAMES_PER_STAT[stat]:
                        streak_map[name] = 0.0

        for stat in STATS:
            head = heads.get(stat)
            if head is None:
                continue
            key = (pid, stat)
            projected = out.get(key)
            if projected is None:
                continue

            feat_names = _feature_names_for_stat(stat)
            row = [0.0] * len(feat_names)
            for i, name in enumerate(feat_names):
                if name in base_map:
                    row[i] = base_map[name]
                elif name in streak_map:
                    row[i] = streak_map[name]
                # else: leave 0.0 (forward-compat for unknown feature names)
            feat = np.array([row], dtype=np.float32)

            residual_pred = float(head.predict(feat)[0])
            cur_stat = float(player.get(stat, 0) or 0)

            # Clip: adjusted must stay >= 0 and <= 2x projected.
            lo = -cur_stat
            hi = max(0.0, 2.0 * projected)
            adjusted = float(projected) + residual_pred
            adjusted = max(float(projected) + lo, min(float(projected) + hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


def apply_residual_correction_endq2(
    snap: dict,
    projs: Dict[Tuple[int, str], float],
) -> Dict[Tuple[int, str], float]:
    """Apply per-(player, stat) residual head correction to projections at endQ2.

    Mirror of apply_residual_correction but uses endQ2 artifacts and features:
    min_through_q2 (sum of min_q1 + min_q2) instead of player `min`, and
    score_margin_abs / is_leading computed from the endQ2 snapshot.

    14 features: cur_{pts,reb,ast,fg3m,stl,blk,tov,pf}, min_through_q2,
                 score_margin_abs, is_leading, pos_C, pos_F, pos_G.

    Parameters
    ----------
    snap : dict
        Canonical snapshot dict at endQ2.
    projs : dict[(pid, stat) -> float]
        Current projected_final values keyed by (player_id int, stat str).
        Updated copy is returned; caller's dict is not mutated.

    Returns
    -------
    dict[(pid, stat) -> float]
        Updated projections. Stats without a head artifact are unchanged.
    """
    heads = load_heads_endq2()
    if not heads:
        return projs

    try:
        import numpy as np
    except ImportError:
        return projs

    positions = _load_positions()

    home_pts = float(snap.get("home_score", 0) or 0)
    away_pts = float(snap.get("away_score", 0) or 0)
    margin_abs = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", "") or "")
    away_team = str(snap.get("away_team", "") or "")

    out = dict(projs)

    for player in snap.get("players") or []:
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError, KeyError):
            continue

        team = str(player.get("team", "") or "")
        if team == home_team:
            raw_margin = home_pts - away_pts
        elif team == away_team:
            raw_margin = away_pts - home_pts
        else:
            raw_margin = 0.0

        # min_through_q2: sum of per-quarter minutes for Q1+Q2.
        min_through_q2 = 0.0
        for q in (1, 2):
            v = player.get(f"min_q{q}")
            if v is not None:
                try:
                    min_through_q2 += float(v or 0)
                except (TypeError, ValueError):
                    pass
        # Fall back to player's reported `min` when per-quarter splits absent.
        if min_through_q2 == 0.0:
            try:
                min_through_q2 = float(player.get("min") or 0)
            except (TypeError, ValueError):
                min_through_q2 = 0.0

        pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

        feat = np.array([[
            float(player.get("pts", 0) or 0),
            float(player.get("reb", 0) or 0),
            float(player.get("ast", 0) or 0),
            float(player.get("fg3m", 0) or 0),
            float(player.get("stl", 0) or 0),
            float(player.get("blk", 0) or 0),
            float(player.get("tov", 0) or 0),
            float(player.get("pf", 0) or 0),
            min_through_q2,
            margin_abs,
            float(raw_margin > 0),
            pos_c,
            pos_f,
            pos_g,
        ]], dtype=np.float32)

        for stat in STATS:
            head = heads.get(stat)
            if head is None:
                continue
            key = (pid, stat)
            projected = out.get(key)
            if projected is None:
                continue

            residual_pred = float(head.predict(feat)[0])
            cur_stat = float(player.get(stat, 0) or 0)

            # Clip: adjusted must stay >= 0 and <= 2x projected.
            lo = -cur_stat
            hi = max(0.0, 2.0 * projected)
            adjusted = float(projected) + residual_pred
            adjusted = max(float(projected) + lo, min(float(projected) + hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out
