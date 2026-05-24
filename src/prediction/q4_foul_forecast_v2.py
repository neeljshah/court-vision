"""q4_foul_forecast_v2.py -- cycle 97e (loop 5). NNLS-fit Q4 PF forecast.

WHY: cycle 96c v1 (``q4_foul_forecast.py``) was REJECTED because its
heuristic coefficient table biased +0.38 PF high, pushing borderline pf=3
players over the pf=4 band and OVER-shrinking projections. PTS MAE on
the foul_change stratum got WORSE by +0.039 instead of the required
-0.10 improvement. The dominant residual failure mode is STILL UNFIXED.

V2 changes
----------
1. **Fit, don't hand-tune.** Coefficients come from a non-negative least
   squares fit on the 50-game retro corpus
   (``data/player_quarter_stats.parquet``). NNLS keeps every coefficient
   >= 0, which matches the physical interpretation: more fouls / more
   minutes / center / fouler opponents -> more Q4 fouls.

2. **Gate.** The forecast only fires when
   ``pf_through_q3 >= 2 AND min_q3 >= 6.0``. Below that floor the signal
   is too sparse (forecast variance > signal) and we return 0.0 so the
   downstream foul_trouble_factor falls back to the raw snapshot pf.

3. **Round DOWN, not round.** v1 used ``int(round(forecasted_pf))``
   which pushed forecast=3.62 into the pf=4 band. v2 uses
   ``int(forecasted_pf)`` (truncate) so the projector only crosses a
   band when the forecast is fully past it. This directly addresses
   v1's +0.38 over-bias.

4. **Position-conditional.** A binary ``is_center`` indicator -- per
   cycle 96e, centers behave differently than guards/forwards on Q4
   fouls.

5. **Opponent foul tendency.** ``opp_foul_rate_l5`` (proxy: mean total
   PF charged by the player's opponent across the 50-game corpus,
   defaults to corpus average when unknown).

Wiring
------
This module is a STAND-ALONE helper. ``probe_q4_foul_forecast_v2.py``
validates against the cycle-95b foul_change stratum. v1 stays in-tree
but is deprecated; v2 is the only forecast wired into
``predict_in_game.project_snapshot`` once the probe ships.

Strictly read-only at import time. Coefficients are fit lazily on the
first call to ``fit_default_coefficients()`` and cached in the module.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_QUARTER_PARQUET = os.path.join(
    PROJECT_DIR, "data", "player_quarter_stats.parquet")
_POSITIONS_PARQUET = os.path.join(
    PROJECT_DIR, "data", "player_positions.parquet")

# Gate floors -- below these the forecast is too noisy to apply.
GATE_MIN_PF = 2
GATE_MIN_Q3 = 6.0

# Default fallback opp_foul_rate when caller can't supply one.
_DEFAULT_OPP_FOUL_RATE = 20.0  # ~league avg team PF / game

# Feature names in fixed order -- the NNLS coefficient vector is parallel.
FEATURE_NAMES: Tuple[str, ...] = (
    "pf_through_q3", "q3_pf", "min_q3", "is_center", "opp_foul_rate_l5",
)


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_center(position_proxy: Optional[str]) -> int:
    if not position_proxy:
        return 0
    s = str(position_proxy).strip().lower()
    if not s:
        return 0
    if "center" in s:
        return 1
    if s.upper() == "C":
        return 1
    return 0


def passes_gate(pf_through_q3: Any, min_q3: Any) -> bool:
    """Forecast only fires when both floors clear -- otherwise too noisy."""
    pf = _safe_int(pf_through_q3)
    m = _safe_float(min_q3)
    return (pf >= GATE_MIN_PF) and (m >= GATE_MIN_Q3)


def build_feature_row(
    pf_through_q3: Any,
    q3_pf: Any,
    min_q3: Any,
    position_proxy: Optional[str],
    opp_foul_rate_l5: Optional[float] = None,
) -> List[float]:
    """Build the 5-element feature vector in FEATURE_NAMES order."""
    pf = max(0, _safe_int(pf_through_q3))
    q3 = max(0, _safe_int(q3_pf))
    m = max(0.0, _safe_float(min_q3))
    c = _is_center(position_proxy)
    opp = opp_foul_rate_l5
    if opp is None:
        opp = _DEFAULT_OPP_FOUL_RATE
    opp = max(0.0, _safe_float(opp, default=_DEFAULT_OPP_FOUL_RATE))
    return [float(pf), float(q3), float(m), float(c), float(opp)]


# ── coefficient fit ────────────────────────────────────────────────────────────

def fit_coefficients(
    feature_rows: Sequence[Sequence[float]],
    targets: Sequence[float],
) -> List[float]:
    """Fit non-negative least squares coefficients.

    Parameters
    ----------
    feature_rows : sequence of 5-element sequences
        Each row in FEATURE_NAMES order.
    targets : sequence of float
        Actual Q4 PF additions.

    Returns
    -------
    list of float, length 5
        NNLS coefficients (>= 0) in FEATURE_NAMES order.
    """
    import numpy as np
    from scipy.optimize import nnls

    if not feature_rows or not targets:
        return [0.0] * len(FEATURE_NAMES)
    A = np.asarray(feature_rows, dtype=float)
    b = np.asarray(targets, dtype=float)
    if A.ndim != 2 or A.shape[1] != len(FEATURE_NAMES):
        raise ValueError(
            f"feature_rows must be 2D with {len(FEATURE_NAMES)} cols, "
            f"got {A.shape}"
        )
    if A.shape[0] != b.shape[0]:
        raise ValueError("feature_rows and targets length mismatch")
    coef, _resid = nnls(A, b)
    return [float(x) for x in coef]


def kfold_indices(n: int, k: int = 5, seed: int = 0) -> List[List[int]]:
    """Deterministic k-fold split returning a list of test-index lists."""
    import random
    rng = random.Random(seed)
    idx = list(range(n))
    rng.shuffle(idx)
    folds: List[List[int]] = [[] for _ in range(k)]
    for i, ix in enumerate(idx):
        folds[i % k].append(ix)
    return folds


def cross_val_mae(
    feature_rows: Sequence[Sequence[float]],
    targets: Sequence[float],
    k: int = 5,
    seed: int = 0,
) -> float:
    """K-fold CV MAE for the NNLS forecast on Q4 PF additions.

    Returns ``float("nan")`` if there's not enough data to split.
    """
    n = len(feature_rows)
    if n < k * 2:
        return float("nan")
    folds = kfold_indices(n, k=k, seed=seed)
    total_err = 0.0
    total_n = 0
    for f_i in range(k):
        test_ix = set(folds[f_i])
        train_X = [feature_rows[i] for i in range(n) if i not in test_ix]
        train_y = [targets[i] for i in range(n) if i not in test_ix]
        if not train_X:
            continue
        coef = fit_coefficients(train_X, train_y)
        for i in folds[f_i]:
            pred = sum(c * x for c, x in zip(coef, feature_rows[i]))
            total_err += abs(pred - targets[i])
            total_n += 1
    return (total_err / total_n) if total_n else float("nan")


# ── training-corpus loader ────────────────────────────────────────────────────

def _load_positions() -> Dict[int, str]:
    if not os.path.exists(_POSITIONS_PARQUET):
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(_POSITIONS_PARQUET)
    except Exception:
        return {}
    out: Dict[int, str] = {}
    for _, r in df.iterrows():
        try:
            pid = int(r["player_id"])
        except (TypeError, ValueError):
            continue
        pos = str(r.get("position") or "")
        if pos:
            out[pid] = pos
    return out


def _load_opp_foul_rates() -> Dict[Tuple[str, int], float]:
    """Approximate ``opp_foul_rate_l5`` per (game_id, player_id) from retro
    corpus.

    For each (game, player) we look up the player's team via the cycle-93c
    ``retro_inplay_mae.load_team_map`` cache, identify the OPPONENT team,
    and use that opponent team's TOTAL PF in this same game as a per-game
    foul-rate proxy. With 50 games this still won't be a true L5 average,
    but it varies row-to-row so NNLS won't absorb it as a flat intercept.
    Production wiring will swap this for the real team-L5 from
    ``team_game_logs.parquet``.

    Returns {} (empty) on any I/O failure. Falls back per call to the
    league-average constant when an opponent can't be resolved.
    """
    if not os.path.exists(_QUARTER_PARQUET):
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(_QUARTER_PARQUET)
    except Exception:
        return {}
    if df.empty:
        return {}

    # Need scripts/ on path to reach retro_inplay_mae.load_team_map.
    import sys as _sys
    scripts_dir = os.path.join(PROJECT_DIR, "scripts")
    if scripts_dir not in _sys.path:
        _sys.path.insert(0, scripts_dir)
    try:
        import retro_inplay_mae as _v1
    except Exception:
        return {}

    out: Dict[Tuple[str, int], float] = {}
    for gid, gdf in df.groupby("game_id"):
        try:
            pid_to_team, _home, _away = _v1.load_team_map(str(gid))
        except Exception:
            continue
        if not pid_to_team:
            continue
        # Total team PF in this game, per team.
        team_pf: Dict[str, float] = {}
        team_pf_sum: Dict[str, float] = {}
        for pid, pdf in gdf.groupby("player_id"):
            team = pid_to_team.get(int(pid), "")
            if not team:
                continue
            team_pf_sum[team] = team_pf_sum.get(team, 0.0) + float(pdf["pf"].sum())
        team_pf = team_pf_sum
        teams_in_game = list(team_pf.keys())
        if len(teams_in_game) < 2:
            continue
        # opp_foul_rate for a player = OPPONENT team's PF in this game.
        for pid in gdf["player_id"].unique():
            team = pid_to_team.get(int(pid), "")
            if not team:
                continue
            opp_pf = sum(
                v for t, v in team_pf.items() if t != team
            ) / max(1, len(teams_in_game) - 1)
            out[(str(gid), int(pid))] = float(opp_pf)
    return out


def build_training_data(
    parquet_path: str = _QUARTER_PARQUET,
) -> Tuple[List[List[float]], List[float], List[int]]:
    """Build (feature_rows, targets, player_ids) from the retro parquet.

    Only includes (player, game) rows where ALL 4 quarters are present
    AND the player passes the gate at endQ3 (pf>=2, min_q3>=6).
    """
    if not os.path.exists(parquet_path):
        return [], [], []
    import pandas as pd
    df = pd.read_parquet(parquet_path)
    positions = _load_positions()
    opp_rates = _load_opp_foul_rates()

    X: List[List[float]] = []
    y: List[float] = []
    pids: List[int] = []
    for gid, gdf in df.groupby("game_id"):
        for pid, pdf in gdf.groupby("player_id"):
            pf_by_q = {int(r.period): float(r.pf) for r in pdf.itertuples()}
            min_by_q = {int(r.period): float(r.min) for r in pdf.itertuples()}
            if not all(q in pf_by_q for q in (1, 2, 3, 4)):
                continue
            pf_q3 = pf_by_q[1] + pf_by_q[2] + pf_by_q[3]
            q3_pf = pf_by_q[3]
            min_q3 = min_by_q[3]
            actual_q4_pf = pf_by_q[4]
            if not passes_gate(pf_q3, min_q3):
                continue
            pos = positions.get(int(pid))
            opp = opp_rates.get((str(gid), int(pid)))
            X.append(build_feature_row(pf_q3, q3_pf, min_q3, pos, opp))
            y.append(float(actual_q4_pf))
            pids.append(int(pid))
    return X, y, pids


# ── default cached coefficients ────────────────────────────────────────────────

_CACHED_COEFS: Optional[List[float]] = None


def fit_default_coefficients() -> List[float]:
    """Fit (or return cached) NNLS coefficients on the retro corpus.

    Returns ``[0.0] * 5`` if the parquet is missing or empty.
    Cached after first call -- subsequent calls are O(1).
    """
    global _CACHED_COEFS
    if _CACHED_COEFS is not None:
        return _CACHED_COEFS
    X, y, _ = build_training_data()
    if not X:
        _CACHED_COEFS = [0.0] * len(FEATURE_NAMES)
        return _CACHED_COEFS
    _CACHED_COEFS = fit_coefficients(X, y)
    return _CACHED_COEFS


def reset_cache() -> None:
    """Reset cached coefficients (test helper)."""
    global _CACHED_COEFS
    _CACHED_COEFS = None


# ── public API ────────────────────────────────────────────────────────────────

def forecast_q4_pf_addition_v2(
    pf_through_q3: Any,
    q3_pf: Any = 0,
    min_q3: Any = 0.0,
    position_proxy: Optional[str] = None,
    opp_foul_rate_l5: Optional[float] = None,
    coefficients: Optional[Sequence[float]] = None,
) -> float:
    """V2 forecast: NNLS-fit + gated Q4 PF addition.

    Returns 0.0 (no adjustment) when the gate doesn't clear OR when no
    coefficients are available. Output is clamped to [0.0, 3.0].

    Parameters
    ----------
    pf_through_q3, q3_pf : int-like
        Cumulative + per-Q3 PF.
    min_q3 : float-like
        Q3 minutes played (gate input).
    position_proxy : str, optional
        Free-text position (Guard, Center, ...).
    opp_foul_rate_l5 : float, optional
        Opponent's recent total-PF average; defaults to corpus mean.
    coefficients : sequence of float, optional
        Override the cached coefficients (mainly for tests).
    """
    if not passes_gate(pf_through_q3, min_q3):
        return 0.0
    coef = coefficients if coefficients is not None else fit_default_coefficients()
    feats = build_feature_row(
        pf_through_q3, q3_pf, min_q3, position_proxy, opp_foul_rate_l5)
    pred = sum(c * x for c, x in zip(coef, feats))
    if pred < 0.0:
        pred = 0.0
    if pred > 3.0:
        pred = 3.0
    return float(pred)


def forecasted_endgame_pf_v2(
    pf_through_q3: Any,
    q3_pf: Any = 0,
    min_q3: Any = 0.0,
    position_proxy: Optional[str] = None,
    opp_foul_rate_l5: Optional[float] = None,
    coefficients: Optional[Sequence[float]] = None,
) -> int:
    """snapshot_pf + forecasted_q4_pf -- ROUNDED DOWN (truncate).

    The round-down (vs v1's round-to-nearest) is the cycle-97e fix for
    v1's +0.38 over-bias: forecast=3.62 -> integer 3, not 4, so a player
    only crosses into a new foul band when the model is fully confident.
    """
    pf = max(0, _safe_int(pf_through_q3))
    add = forecast_q4_pf_addition_v2(
        pf_through_q3=pf,
        q3_pf=q3_pf,
        min_q3=min_q3,
        position_proxy=position_proxy,
        opp_foul_rate_l5=opp_foul_rate_l5,
        coefficients=coefficients,
    )
    end = float(pf) + float(add)
    # ROUND DOWN (truncate) -- key v2 fix.
    out = int(end)  # int() truncates toward zero for non-negative floats
    if out > 6:
        out = 6
    if out < 0:
        out = 0
    return out


__all__ = [
    "FEATURE_NAMES",
    "GATE_MIN_PF",
    "GATE_MIN_Q3",
    "passes_gate",
    "build_feature_row",
    "fit_coefficients",
    "kfold_indices",
    "cross_val_mae",
    "build_training_data",
    "fit_default_coefficients",
    "reset_cache",
    "forecast_q4_pf_addition_v2",
    "forecasted_endgame_pf_v2",
]
