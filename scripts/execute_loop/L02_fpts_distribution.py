"""L02_fpts_distribution.py — Fantasy Points Distribution Engine (BUILD L2).

Converts per-stat quantile predictions into correlated FPTS sample distributions
for DraftKings and FanDuel scoring. Supports lineup simulation via Monte Carlo.

Public API
----------
    FPTSDistribution         — dataclass with mean/std/quantiles/samples/bonuses
    compute_player_fpts(...) -> FPTSDistribution | None
    simulate_lineup_fpts(players, n_samples) -> np.ndarray
    score_box_to_fpts(box, book) -> float
"""
from __future__ import annotations

import json
import logging
import unicodedata
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import src.data.nba_api_headers_patch  # noqa — must be first

from src.prediction.prop_pergame import STATS, build_prediction_row
from src.prediction.prop_quantiles import predict_pergame_quantiles
from src.prediction.quantile_calibration import apply as apply_quantile_calibration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
_MODEL_DIR = _PROJECT_DIR / "data" / "models"
_CORR_PATH = _MODEL_DIR / "prop_corr_matrix.json"

# ---------------------------------------------------------------------------
# Scoring tables
# ---------------------------------------------------------------------------
_DK_SCORING: Dict[str, float] = {
    "pts": 1.0, "reb": 1.25, "ast": 1.5,
    "stl": 2.0, "blk": 2.0, "tov": -0.5, "fg3m": 0.5,
}
_FD_SCORING: Dict[str, float] = {
    "pts": 1.0, "reb": 1.2, "ast": 1.5,
    "stl": 3.0, "blk": 3.0, "tov": -1.0, "fg3m": 0.0,
}
_BOOKS: Dict[str, Dict[str, float]] = {"DK": _DK_SCORING, "FD": _FD_SCORING}

# Stat order matches STATS = ["pts","reb","ast","fg3m","stl","blk","tov"]
_STAT_ORDER = STATS  # ["pts","reb","ast","fg3m","stl","blk","tov"]

# Double/triple-double threshold stats for DK bonuses (pts, reb, ast only)
_DD_STATS = {"pts", "reb", "ast"}
_DD_THRESHOLD = 10

# Sigma multipliers from sigma_diagnostic.md — corrects σ overconfidence
_SIGMA_MULT: Dict[str, float] = {
    "pts": 1.07, "reb": 1.07, "ast": 0.99,
    "fg3m": 1.44, "stl": 1.76, "blk": 1.95, "tov": 1.30,
}

# Stats rounded to int in samples (discrete counts)
_INT_STATS = {"blk", "stl", "fg3m", "tov", "reb", "ast"}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class FPTSDistribution:
    mean: float
    std: float
    q10: float
    q50: float
    q90: float
    samples: np.ndarray                    # shape (n_samples,)
    per_stat_means: Dict[str, float] = field(default_factory=dict)
    has_double_double_p: float = 0.0
    has_triple_double_p: float = 0.0


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------
def score_box_to_fpts(box: dict, book: str) -> float:
    """Score a single box-score dict to fantasy points.

    Parameters
    ----------
    box  : dict with keys pts, reb, ast, fg3m, stl, blk, tov (numeric).
    book : "DK" or "FD" (case-sensitive).

    Returns
    -------
    float FPTS value.

    Raises
    ------
    ValueError if book is unknown.
    """
    if book not in _BOOKS:
        raise ValueError(f"Unknown book {book!r}. Supported: {list(_BOOKS)}")

    scoring = _BOOKS[book]
    base = sum(float(box.get(stat, 0.0)) * pts for stat, pts in scoring.items())

    if book == "DK":
        base += _dk_bonus(box)

    return base


def _dk_bonus(box: dict) -> float:
    """Compute DK double-double (+1.5) and triple-double (+3.0) bonuses."""
    dd_count = sum(
        1 for s in _DD_STATS if float(box.get(s, 0.0)) >= _DD_THRESHOLD
    )
    if dd_count >= 3:
        return 3.0   # triple-double (includes DD bonus per DK rules)
    if dd_count >= 2:
        return 1.5   # double-double
    return 0.0


def _dk_bonus_samples(stat_samples: np.ndarray) -> np.ndarray:
    """Vectorised DK DD/TD bonus over (n_samples, 7) stat matrix.

    stat_samples columns follow _STAT_ORDER = [pts, reb, ast, fg3m, stl, blk, tov].
    DD/TD scored over pts(0), reb(1), ast(2).
    """
    pts_col = stat_samples[:, 0]
    reb_col = stat_samples[:, 1]
    ast_col = stat_samples[:, 2]
    dd_count = (
        (pts_col >= _DD_THRESHOLD).astype(np.int8)
        + (reb_col >= _DD_THRESHOLD).astype(np.int8)
        + (ast_col >= _DD_THRESHOLD).astype(np.int8)
    )
    bonus = np.where(dd_count >= 3, 3.0, np.where(dd_count >= 2, 1.5, 0.0))
    return bonus


# ---------------------------------------------------------------------------
# Name resolution
# ---------------------------------------------------------------------------
def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _resolve_player_id(player_name: str) -> Optional[int]:
    """Resolve a player display name to NBA player_id via nba_api static list."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except ImportError:
        logger.warning("nba_api not available — cannot resolve player name.")
        return None

    name_norm = _strip_accents(player_name.strip().lower())
    for p in players.get_players():
        if _strip_accents(p["full_name"].lower()) == name_norm:
            return int(p["id"])
    # Fallback: partial match (last name)
    parts = name_norm.split()
    if len(parts) >= 2:
        last = parts[-1]
        candidates = [
            p for p in players.get_players()
            if last in _strip_accents(p["full_name"].lower())
        ]
        if len(candidates) == 1:
            return int(candidates[0]["id"])
    return None


# ---------------------------------------------------------------------------
# Covariance / correlation matrix loading
# ---------------------------------------------------------------------------
def _load_corr_matrix() -> np.ndarray:
    """Load 7x7 correlation matrix from disk, or fall back to identity + pts/fg3m=0.6."""
    n = len(_STAT_ORDER)
    if _CORR_PATH.exists():
        try:
            raw = json.loads(_CORR_PATH.read_text(encoding="utf-8"))
            mat = np.zeros((n, n), dtype=float)
            for i, si in enumerate(_STAT_ORDER):
                for j, sj in enumerate(_STAT_ORDER):
                    mat[i, j] = float(raw.get(si, {}).get(sj, 1.0 if i == j else 0.0))
            return mat
        except Exception as exc:
            logger.warning("Failed to load corr matrix (%s): %s — using fallback.", _CORR_PATH, exc)

    mat = np.eye(n, dtype=float)
    # Hardcoded fallback: pts/fg3m correlation
    pts_i = _STAT_ORDER.index("pts")
    fg3m_i = _STAT_ORDER.index("fg3m")
    mat[pts_i, fg3m_i] = 0.6
    mat[fg3m_i, pts_i] = 0.6
    return mat


def _nearest_psd(mat: np.ndarray) -> np.ndarray:
    """Project correlation matrix to nearest PSD by clipping negative eigenvalues."""
    eigvals, eigvecs = np.linalg.eigh(mat)
    eigvals = np.clip(eigvals, 1e-8, None)
    psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    # Re-normalise diagonal to 1
    diag = np.sqrt(np.diag(psd))
    diag = np.where(diag < 1e-12, 1.0, diag)
    return psd / np.outer(diag, diag)


# ---------------------------------------------------------------------------
# Core distribution builder
# ---------------------------------------------------------------------------
def compute_player_fpts(
    player_name: str,
    opp: str,
    season: str,
    *,
    book: str = "DK",
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    n_samples: int = 1000,
) -> Optional[FPTSDistribution]:
    """Compute a correlated FPTS distribution for one player in one game.

    Parameters
    ----------
    player_name : Display name (e.g. "Nikola Jokic").
    opp         : Opponent team abbreviation (e.g. "LAL").
    season      : Season string (e.g. "2024-25").
    book        : "DK" or "FD".
    is_home     : True if the player's team is at home.
    rest_days   : Days since last game (default 2.0).
    gamelog_dir : Override gamelog cache directory (data/nba by default).
    model_dir   : Override model directory (data/models by default).
    n_samples   : Monte Carlo samples to draw (0 → analytical only).

    Returns
    -------
    FPTSDistribution or None if player/data not found.
    """
    if book not in _BOOKS:
        raise ValueError(f"Unknown book {book!r}. Supported: {list(_BOOKS)}")

    # 1. Resolve player
    pid = _resolve_player_id(player_name)
    if pid is None:
        warnings.warn(f"compute_player_fpts: player not found: {player_name!r}")
        return None

    # 2. Build feature row
    row = build_prediction_row(
        pid, opp, season,
        is_home=is_home,
        rest_days=rest_days,
        gamelog_dir=gamelog_dir,
    )
    if row is None:
        warnings.warn(
            f"compute_player_fpts: build_prediction_row returned None for "
            f"{player_name!r} (id={pid}, opp={opp}, season={season})"
        )
        return None

    model_dir_str = str(model_dir) if model_dir else str(_MODEL_DIR)

    # 3. Per-stat quantiles → mu / sigma
    mu_vec = np.zeros(len(_STAT_ORDER), dtype=float)
    sigma_vec = np.zeros(len(_STAT_ORDER), dtype=float)
    q50_vec = np.zeros(len(_STAT_ORDER), dtype=float)

    for i, stat in enumerate(_STAT_ORDER):
        qres = predict_pergame_quantiles(stat, row, model_dir=model_dir_str)
        if qres is None:
            logger.warning("No quantile model for stat=%s, player=%s", stat, player_name)
            continue

        q10_raw = float(qres.get("q10", 0.0))
        q50_raw = float(qres.get("q50", 0.0))
        q90_raw = float(qres.get("q90", 0.0))

        # Calibrate
        cal_q10, cal_q90 = apply_quantile_calibration(stat, q10_raw, q50_raw, q90_raw)
        cal_q10 = float(cal_q10)
        cal_q90 = float(cal_q90)

        mu_vec[i] = q50_raw   # point estimate = calibrated median
        q50_vec[i] = q50_raw

        raw_sigma = (cal_q90 - cal_q10) / (2.0 * 1.2816)
        sigma = max(raw_sigma * _SIGMA_MULT[stat], 1e-3)
        sigma_vec[i] = sigma

    # Handle n_samples=0 analytically
    if n_samples == 0:
        analytical_box = {s: float(q50_vec[i]) for i, s in enumerate(_STAT_ORDER)}
        ana_q50 = score_box_to_fpts(analytical_box, book)
        return FPTSDistribution(
            mean=float("nan"),
            std=float("nan"),
            q10=float("nan"),
            q50=ana_q50,
            q90=float("nan"),
            samples=np.array([], dtype=float),
            per_stat_means={s: float(q50_vec[i]) for i, s in enumerate(_STAT_ORDER)},
            has_double_double_p=0.0,
            has_triple_double_p=0.0,
        )

    # 4. Correlated sampling via Cholesky decomposition
    corr = _load_corr_matrix()
    corr = _nearest_psd(corr)

    try:
        L = np.linalg.cholesky(corr)
    except np.linalg.LinAlgError:
        logger.warning("Cholesky failed — falling back to identity correlation.")
        L = np.eye(len(_STAT_ORDER))

    # Draw (n_samples, 7) standard normals, correlate, scale, shift
    z = np.random.standard_normal((n_samples, len(_STAT_ORDER)))
    correlated = z @ L.T                             # (n_samples, 7)
    raw_samples = correlated * sigma_vec + mu_vec    # scale + shift

    # Clip negatives and discretise count stats
    raw_samples = np.clip(raw_samples, 0.0, None)
    for i, stat in enumerate(_STAT_ORDER):
        if stat in _INT_STATS:
            raw_samples[:, i] = np.round(raw_samples[:, i])

    # 5. Score each sample row
    scoring = _BOOKS[book]
    # (n_samples, 7) dot (7,) weights
    weight_vec = np.array([scoring.get(s, 0.0) for s in _STAT_ORDER], dtype=float)
    fpts_samples = raw_samples @ weight_vec

    if book == "DK":
        fpts_samples = fpts_samples + _dk_bonus_samples(raw_samples)

    # 6. Summary statistics
    fpts_mean = float(np.mean(fpts_samples))
    fpts_std = float(np.std(fpts_samples))
    fpts_q10 = float(np.quantile(fpts_samples, 0.10))
    fpts_q50 = float(np.quantile(fpts_samples, 0.50))
    fpts_q90 = float(np.quantile(fpts_samples, 0.90))

    per_stat_means = {s: float(np.mean(raw_samples[:, i])) for i, s in enumerate(_STAT_ORDER)}

    # 7. DD/TD probabilities from samples
    pts_col = raw_samples[:, _STAT_ORDER.index("pts")]
    reb_col = raw_samples[:, _STAT_ORDER.index("reb")]
    ast_col = raw_samples[:, _STAT_ORDER.index("ast")]
    dd_counts = (
        (pts_col >= _DD_THRESHOLD).astype(int)
        + (reb_col >= _DD_THRESHOLD).astype(int)
        + (ast_col >= _DD_THRESHOLD).astype(int)
    )
    has_dd_p = float(np.mean(dd_counts >= 2))
    has_td_p = float(np.mean(dd_counts >= 3))

    return FPTSDistribution(
        mean=fpts_mean,
        std=fpts_std,
        q10=fpts_q10,
        q50=fpts_q50,
        q90=fpts_q90,
        samples=fpts_samples,
        per_stat_means=per_stat_means,
        has_double_double_p=has_dd_p,
        has_triple_double_p=has_td_p,
    )


# ---------------------------------------------------------------------------
# Lineup simulation
# ---------------------------------------------------------------------------
def simulate_lineup_fpts(
    players: List[FPTSDistribution],
    n_samples: int = 10000,
) -> np.ndarray:
    """Simulate total lineup FPTS by summing independent player samples.

    Each player's sample array is resampled (with replacement) to n_samples
    length, then summed across players.  Players with empty samples contribute
    their mean (or 0 if NaN).

    Parameters
    ----------
    players   : List of FPTSDistribution instances (one per roster slot).
    n_samples : Number of Monte Carlo lineup samples.

    Returns
    -------
    np.ndarray of shape (n_samples,) with lineup FPTS totals.
    """
    if not players:
        return np.zeros(n_samples, dtype=float)

    total = np.zeros(n_samples, dtype=float)
    rng = np.random.default_rng()

    for dist in players:
        if len(dist.samples) == 0:
            # Analytical fallback
            contrib = 0.0 if np.isnan(dist.mean) else dist.mean
            total += contrib
        else:
            idx = rng.integers(0, len(dist.samples), size=n_samples)
            total += dist.samples[idx]

    return total
