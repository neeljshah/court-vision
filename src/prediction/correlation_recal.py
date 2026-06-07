"""correlation_recal.py — Playstyle-conditioned + globally-recalibrated prop correlations.

Flag: CV_ARCHETYPE_CORR (default OFF = byte-identical to existing parlay_engine).

When ON, replaces the flat _SAME_PLAYER_RHO and _TEAMMATE_RHO lookup tables with
archetype-conditioned + globally-recalibrated residual correlations validated by
scripts/analyze_playstyle_corr_sameplayer.py + scripts/playstyle_corr_teammate.py.

Priority order for same_player_rho(stat_a, stat_b, player_id):
  1. Surviving archetype-specific cell for that player's archetype (refined=True in JSON)
  2. Global recalibrated residual rho (n-weighted average across all archetypes)
  3. Existing naive rho from parlay_engine._SAME_PLAYER_RHO (byte-identical fallback)

Priority order for teammate_rho(stat_a, stat_b, player_id_a, player_id_b):
  1. Surviving archetype-pair cell (in surviving_cells list in JSON)
  2. Stable global flat baseline from the teammate JSON (stable=True)
  3. Naive rho from parlay_engine._TEAMMATE_RHO (byte-identical fallback)

PHYSICAL INTERPRETATION:
  - SPOT_UP_SHOOTER fg3m_pts 0.55->0.74: player's scoring is dominated by threes;
    pts and fg3m share nearly all variance (pts = ~3*fg3m for spot-up players).
  - ast_tov 0.40->0.11: creators don't systematically turn the ball over MORE when
    they assist more; the naive 0.40 overestimates this coupling once player means
    are residualized.
  - pts_pts teammate ~0 (not -0.15): teammate scoring residuals are near-uncorrelated;
    the "usage competition" anti-correlation assumed by the naive value is a role/minutes
    effect that vanishes once residuals are taken.
  - creator_AST->catch_shoot_FG3M +0.113: drive-and-kick structure; when a creator
    dishes assists above their mean, catch-shoot teammates make more threes above their
    mean in the same game.

ACCURACY CAVEAT:
  No SGP price history is available. These are joint-distribution accuracy improvements
  (better model of the covariance between stat outcomes) NOT validated ROI improvements.
  Default OFF. Recommend-don't-auto-flip.
"""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Optional

_MODELS = Path(__file__).resolve().parents[2] / "data" / "models"

_SAME_PLAYER_CORR_PATH = _MODELS / "prop_corr_archetype_sameplayer.json"
_TEAMMATE_CORR_PATH    = _MODELS / "prop_corr_archetype_teammate.json"
_SAME_PLAYER_ARCH_PATH = _MODELS / "player_archetype_sameplayer.json"
_TEAMMATE_ARCH_PATH    = _MODELS / "player_archetype_teammate.json"

# Naive flat rhos from parlay_engine (byte-identical fallback).
# Keep in sync with parlay_engine._SAME_PLAYER_RHO and _TEAMMATE_RHO.
_NAIVE_SAME_PLAYER_RHO: dict[frozenset, float] = {
    frozenset(("pts", "ast")): 0.30,
    frozenset(("pts", "reb")): 0.40,
    frozenset(("pts", "fg3m")): 0.55,
    frozenset(("pts", "stl")): 0.20,
    frozenset(("pts", "blk")): 0.10,
    frozenset(("pts", "tov")): 0.35,
    frozenset(("reb", "blk")): 0.35,
    frozenset(("reb", "ast")): 0.15,
    frozenset(("ast", "tov")): 0.40,
    frozenset(("fg3m", "ast")): 0.20,
    frozenset(("stl", "blk")): 0.15,
}
_NAIVE_TEAMMATE_RHO: dict[frozenset, float] = {
    frozenset(("pts", "pts")): -0.15,
    frozenset(("pts", "ast")): 0.20,
    frozenset(("reb", "reb")): -0.10,
    frozenset(("ast", "ast")): -0.10,
}


def recal_enabled() -> bool:
    """Return True iff CV_ARCHETYPE_CORR env var is truthy."""
    return os.environ.get("CV_ARCHETYPE_CORR", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ── Loaders (lru_cache so each JSON is read once per process) ─────────────────

@functools.lru_cache(maxsize=1)
def _load_sameplayer_corr() -> dict:
    """Load prop_corr_archetype_sameplayer.json."""
    if not _SAME_PLAYER_CORR_PATH.exists():
        return {}
    try:
        return json.loads(_SAME_PLAYER_CORR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _load_teammate_corr() -> dict:
    """Load prop_corr_archetype_teammate.json."""
    if not _TEAMMATE_CORR_PATH.exists():
        return {}
    try:
        return json.loads(_TEAMMATE_CORR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _load_sameplayer_arch_map() -> dict[int, str]:
    """Load player_archetype_sameplayer.json -> {player_id (int): archetype}."""
    if not _SAME_PLAYER_ARCH_PATH.exists():
        return {}
    try:
        raw = json.loads(_SAME_PLAYER_ARCH_PATH.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _load_teammate_arch_map() -> dict[int, str]:
    """Load player_archetype_teammate.json -> {player_id (int): archetype}."""
    if not _TEAMMATE_ARCH_PATH.exists():
        return {}
    try:
        raw = json.loads(_TEAMMATE_ARCH_PATH.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    except Exception:
        return {}


# ── Pre-built lookup tables (computed once from JSON, cached) ─────────────────

@functools.lru_cache(maxsize=1)
def _sameplayer_archetype_cells() -> dict[tuple[str, frozenset], float]:
    """Build {(archetype, frozenset(stat_a, stat_b)): rho} for refined=True cells only."""
    data = _load_sameplayer_corr()
    out: dict[tuple[str, frozenset], float] = {}
    for arch, cells in data.get("archetypes", {}).items():
        for pair_key, cell in cells.items():
            if not cell.get("refined", False):
                continue
            rho = cell.get("rho")
            if rho is None:
                continue
            # pair_key is like "ast_pts", "fg3m_pts" etc.
            parts = pair_key.split("_")
            if len(parts) == 2:
                sa, sb = parts
                out[(arch, frozenset((sa, sb)))] = float(rho)
    return out


@functools.lru_cache(maxsize=1)
def _sameplayer_global_rho() -> dict[frozenset, float]:
    """Build n-weighted global average rho per stat pair from all archetypes."""
    data = _load_sameplayer_corr()
    import numpy as np
    pair_rhos: dict[frozenset, list[float]] = {}
    pair_nobs: dict[frozenset, list[float]] = {}
    for arch, cells in data.get("archetypes", {}).items():
        for pair_key, cell in cells.items():
            rho = cell.get("rho")
            n = cell.get("n_obs", cell.get("r_measured") and 1) or 0
            if rho is None:
                continue
            parts = pair_key.split("_")
            if len(parts) != 2:
                continue
            sa, sb = parts
            key = frozenset((sa, sb))
            pair_rhos.setdefault(key, []).append(float(rho))
            pair_nobs.setdefault(key, []).append(float(n) if n else 1.0)
    out: dict[frozenset, float] = {}
    for key in pair_rhos:
        rhos_arr = pair_rhos[key]
        nobs_arr = pair_nobs[key]
        total_n = sum(nobs_arr)
        if total_n > 0:
            w_avg = sum(r * n for r, n in zip(rhos_arr, nobs_arr)) / total_n
        else:
            w_avg = sum(rhos_arr) / len(rhos_arr)
        out[key] = float(w_avg)
    return out


@functools.lru_cache(maxsize=1)
def _teammate_surviving_cells() -> dict[tuple[str, str, frozenset], float]:
    """Build {(arch_a, arch_b, frozenset(stat_a, stat_b)): rho} for surviving cells."""
    data = _load_teammate_corr()
    out: dict[tuple[str, str, frozenset], float] = {}
    for cell_key in data.get("surviving_cells", []):
        cell = data.get("archetype_pair_cells", {}).get(cell_key)
        if not cell:
            continue
        rho = cell.get("rho")
        if rho is None:
            continue
        arch_a = cell["archetype_a"]
        arch_b = cell["archetype_b"]
        sa = cell["stat_a"]
        sb = cell["stat_b"]
        # Store both orderings so lookup is direction-agnostic for symmetric pairs.
        out[(arch_a, arch_b, frozenset((sa, sb)))] = float(rho)
        if arch_a != arch_b:
            out[(arch_b, arch_a, frozenset((sa, sb)))] = float(rho)
    return out


@functools.lru_cache(maxsize=1)
def _teammate_global_baselines() -> dict[frozenset, float]:
    """Build {frozenset(stat_a, stat_b): rho} from stable flat baselines."""
    data = _load_teammate_corr()
    out: dict[frozenset, float] = {}
    for pair_key, baseline in data.get("flat_baselines", {}).items():
        if not baseline.get("stable", False):
            continue
        rho = baseline.get("rho")
        if rho is None:
            continue
        # pair_key like "pts_ast", "reb_reb"
        parts = pair_key.split("_")
        if len(parts) == 2:
            sa, sb = parts
            out[frozenset((sa, sb))] = float(rho)
    return out


# ── Public API ────────────────────────────────────────────────────────────────

def same_player_rho(stat_a: str, stat_b: str,
                    player_id: Optional[int] = None) -> Optional[float]:
    """Return recalibrated same-player correlation rho.

    Priority:
      1. Archetype-specific refined cell (if player_id known + archetype has a
         refined=True cell for this pair).
      2. Global n-weighted average rho across all archetypes.
      3. None (caller falls back to naive).

    Returns None if this pair has no recalibration data at all.
    """
    key = frozenset((stat_a.lower(), stat_b.lower()))

    # Priority 1: archetype cell
    if player_id is not None:
        arch = _load_sameplayer_arch_map().get(int(player_id))
        if arch:
            arch_cells = _sameplayer_archetype_cells()
            cell_rho = arch_cells.get((arch, key))
            if cell_rho is not None:
                return max(-0.95, min(0.95, cell_rho))

    # Priority 2: global average
    global_rho = _sameplayer_global_rho().get(key)
    if global_rho is not None:
        return max(-0.95, min(0.95, global_rho))

    # Priority 3: caller uses naive
    return None


def teammate_rho(stat_a: str, stat_b: str,
                 player_id_a: Optional[int] = None,
                 player_id_b: Optional[int] = None) -> Optional[float]:
    """Return recalibrated teammate correlation rho.

    Priority:
      1. Archetype-pair surviving cell (both player_ids known + archetypes known).
      2. Stable global flat baseline for this stat pair.
      3. None (caller falls back to naive).
    """
    sa, sb = stat_a.lower(), stat_b.lower()
    key = frozenset((sa, sb))

    # Priority 1: archetype-pair surviving cell
    if player_id_a is not None and player_id_b is not None:
        arch_map = _load_teammate_arch_map()
        arch_a = arch_map.get(int(player_id_a))
        arch_b = arch_map.get(int(player_id_b))
        if arch_a and arch_b:
            surviving = _teammate_surviving_cells()
            cell_rho = surviving.get((arch_a, arch_b, key))
            if cell_rho is not None:
                return max(-0.95, min(0.95, cell_rho))

    # Priority 2: stable global baseline
    global_rho = _teammate_global_baselines().get(key)
    if global_rho is not None:
        return max(-0.95, min(0.95, global_rho))

    # Priority 3: caller uses naive
    return None


def clear_caches() -> None:
    """Clear all lru_cache entries (useful for testing with mock paths)."""
    _load_sameplayer_corr.cache_clear()
    _load_teammate_corr.cache_clear()
    _load_sameplayer_arch_map.cache_clear()
    _load_teammate_arch_map.cache_clear()
    _sameplayer_archetype_cells.cache_clear()
    _sameplayer_global_rho.cache_clear()
    _teammate_surviving_cells.cache_clear()
    _teammate_global_baselines.cache_clear()
