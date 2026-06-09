"""Learned Control Brain — Rung-0 scaffold.

ROADMAP phase : V0/V5 BUILD iter 15 — brain sub-module.
GATE to flip ON : B1 byte-identical gate (|brain_off - margins.mean()| < 1e-12
                  on a panel) + simplex invariant + missing-engine renorm green.

Fallback ladder (D03 §1):
  Rung 0 (default): equal-weight 1/n — byte-identical to margins.mean().
      Closes B8: records equal-weight as the validated default.
      engine_reliability_weights.json:beats_equal_weight=false today.
  Rung 1 (CV_BRAIN_GLS): GLS redundancy weights; delegates to
      ensemble/weights.py:redundancy_weights. No skill claim.
  Rung 2 (CV_BRAIN_REGIME): raises NotImplementedError("DATA_BLOCKED_UNTIL_SEASON_2").

DEFAULT-OFF: nothing here is imported by any live path. Numpy lazy-loaded.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import numpy as np  # pragma: no cover

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_TS_DIR = os.path.join(_ROOT, "data", "cache", "team_system")
_RELIABILITY_PATH = os.path.join(_TS_DIR, "engine_reliability_weights.json")
_DECORR_PATH = os.path.join(_TS_DIR, "engine_decorrelation_full.json")
_PROPOSAL_PATH = os.path.join(_ROOT, "data", "registry", "ensemble_weights_proposal.json")


# ---------------------------------------------------------------------------
# Public dataclasses — D03 §2.2 / §2.3
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegimeVector:
    """Leak-free pregame regime descriptor (D03 §2.2).

    All fields are coarse buckets derived from the equal-weight pass; none
    reads the game outcome.
    """
    is_playoff: bool
    pace_tier: int        # 0/1/2 = slow/avg/fast vs league terciles
    margin_bucket: int    # 0/1/2/3 = |eq_margin| in {<3,3-7,7-12,>12}
    disagree_tier: int    # 0/1/2 = margins.std() vs {<3,3-6,>6}
    coverage_flags: int   # bit0=lineup_markov, bit1=shot_quality, bit2=pbp_fresh
    n_engines: int        # 7 or 16


@dataclass(frozen=True)
class WeightBundle:
    """Output of the control brain (D03 §2.3).

    Invariant: sum(engine_weights.values()) == 1.0 ± 1e-9 over present engines.
    """
    engine_weights: Dict[str, float]  # name -> w, sums to 1.0
    factor_weights: Dict[str, float]  # {"clutch_gate": 0/1, "sd_floor": 0/1}
    rung: int    # 0=equal, 1=GLS-redundancy, 2=regime-skill
    source: str  # "equal_weight" | "gls_redundancy" | "regime_skill_v<season>"
    n_eff: float
    notes: str


# ---------------------------------------------------------------------------
# Flag helper
# ---------------------------------------------------------------------------

class _Flags:
    """Read env-var feature flags; all default OFF."""

    @staticmethod
    def is_on(flag_name: str) -> bool:
        """Return True iff env var ``flag_name`` == ``"1"``."""
        return os.environ.get(flag_name, "0") == "1"


flags = _Flags()


# ---------------------------------------------------------------------------
# Artifact loaders (single weight authority; lru_cache mirrors engine pattern)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_reliability() -> Dict[str, Any]:
    """Load engine_reliability_weights.json (single weight authority). Safe if absent."""
    if not os.path.exists(_RELIABILITY_PATH):
        return {}
    with open(_RELIABILITY_PATH, encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _load_decorr() -> Dict[str, Any]:
    """Load engine_decorrelation_full.json. Safe if absent."""
    if not os.path.exists(_DECORR_PATH):
        return {}
    with open(_DECORR_PATH, encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _load_proposal() -> Dict[str, Any]:
    """Load ensemble_weights_proposal.json. Safe if absent."""
    if not os.path.exists(_PROPOSAL_PATH):
        return {}
    with open(_PROPOSAL_PATH, encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Rung 0 — equal weight
# ---------------------------------------------------------------------------

def _rung0_equal(engine_names: List[str]) -> WeightBundle:
    """Return uniform 1/n weights. Byte-identical to margins.mean() (D03 §8 B1)."""
    n = len(engine_names)
    if n == 0:
        raise ValueError("engine_names must be non-empty")
    w = float(1.0 / n)
    n_eff = float(_load_decorr().get("n_eff_full", float(n)))
    return WeightBundle(
        engine_weights={name: w for name in engine_names},
        factor_weights={"clutch_gate": 0.0, "sd_floor": 1.0},
        rung=0,
        source="equal_weight",
        n_eff=n_eff,
        notes=(
            "B8: equal-weight is the validated default. "
            "beats_equal_weight=false -> Rung 0. "
            "1 season, n_eff~1.636, 3/7 as-of engines in net-rating cluster."
        ),
    )


# ---------------------------------------------------------------------------
# Rung 1 — GLS redundancy weights (gated CV_BRAIN_GLS; TODO-stubbed)
# ---------------------------------------------------------------------------

def gls_redundancy_weights(corr_matrix: "np.ndarray") -> "np.ndarray":
    """Non-negative GLS redundancy weights from a correlation matrix.

    Gated behind ``brain.flags.is_on("CV_BRAIN_GLS")``.  Will delegate to
    ``ensemble/weights.py:redundancy_weights`` once the Rung-1 promotion gate
    (D03 §9 B5) clears. Assumes equal per-engine skill — redundancy guard only.

    Parameters
    ----------
    corr_matrix : np.ndarray
        (n, n) pairwise engine correlation matrix.

    Returns
    -------
    np.ndarray
        Weight vector of length n, summing to 1.0.
    """
    import numpy as _np  # lazy import

    C = _np.asarray(corr_matrix, dtype=float)
    # Single source of truth: delegate to the canonical redundancy_weights (P2.2).
    try:
        import sys as _sys
        _ts = os.path.join(_ROOT, "scripts", "team_system")
        if _ts not in _sys.path:
            _sys.path.insert(0, _ts)
        from ensemble.weights import redundancy_weights as _rw  # type: ignore
        return _rw(C)
    except Exception:
        # Inline fallback (identical formula): w_i ∝ 1 / sum_j max(corr_ij, 0).
        cluster = _np.clip(C, 0.0, None).sum(axis=1)
        w = 1.0 / _np.maximum(cluster, 1e-6)
        return w / w.sum()


def _rung1_gls(engine_names: List[str]) -> WeightBundle:
    """Return GLS redundancy WeightBundle (Rung 1, gated CV_BRAIN_GLS)."""
    import numpy as _np  # lazy import

    decorr = _load_decorr()
    n = len(engine_names)
    n_eff = float(decorr.get("n_eff_full", float(n)))

    if decorr and "corr_matrix" in decorr:
        corr = _np.asarray(decorr["corr_matrix"], dtype=float)
        # TODO(P3.2): align engine ordering / clock vs clock_trajectory alias.
        raw_w = gls_redundancy_weights(corr) if corr.shape[0] == n else _np.ones(n) / n
    else:
        raw_w = _np.ones(n, dtype=float) / n

    normed = raw_w / max(float(raw_w.sum()), 1e-12)
    return WeightBundle(
        engine_weights={name: float(normed[i]) for i, name in enumerate(engine_names)},
        factor_weights={"clutch_gate": 0.0, "sd_floor": 1.0},
        rung=1,
        source="gls_redundancy",
        n_eff=n_eff,
        notes="GLS redundancy guard (equal-skill). PROPOSAL_DEFAULT_OFF; CV_BRAIN_GLS=1 required.",
    )


# ---------------------------------------------------------------------------
# Rung 2 — regime-conditioned skill weights (DATA_BLOCKED)
# ---------------------------------------------------------------------------

def regime_skill_weights(
    engine_names: List[str],
    regime: RegimeVector,
) -> "np.ndarray":
    """Regime-conditioned skill weight vector — Rung 2.

    Permanently raises until the 5-criterion + 2-season gate (D03 §4.4) clears:
    beats_equal(CV-std) AND cross_season_OOS_brier_delta<0 AND seasons>=2
    AND n_cell>=200 AND BH-FDR survivor AND ECE<0.10.

    Gate: CV_BRAIN_REGIME=1 + brain_regime_weights.json written by
    engine_brain_backtest.py with beats_equal=true in the regime cell.

    Raises
    ------
    NotImplementedError
        Always, until gate clears.
    """
    raise NotImplementedError("DATA_BLOCKED_UNTIL_SEASON_2")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_regime(
    preds: List[Dict[str, Any]],
    eq_margin: float,
    is_playoff: bool = False,
    pace_tier: int = 1,
    coverage_flags: int = 0,
) -> RegimeVector:
    """Build a leak-free RegimeVector from the equal-weight pass outputs.

    Must be called AFTER the equal-weight fusion pass (two-pass design, D03 §5)
    so margin_bucket and disagree_tier derive from the projection, not the outcome.
    """
    import numpy as _np  # lazy import

    abs_m = abs(eq_margin)
    margin_bucket = 0 if abs_m < 3 else (1 if abs_m < 7 else (2 if abs_m < 12 else 3))

    spread = float(_np.array([float(p.get("margin_home", 0.0)) for p in preds]).std()) if preds else 0.0
    disagree_tier = 0 if spread < 3 else (1 if spread < 6 else 2)

    return RegimeVector(
        is_playoff=is_playoff,
        pace_tier=pace_tier,
        margin_bucket=margin_bucket,
        disagree_tier=disagree_tier,
        coverage_flags=coverage_flags,
        n_engines=len(preds),
    )


def engine_weights(
    preds: List[Dict[str, Any]],
    regime: "Optional[RegimeVector]" = None,
) -> "np.ndarray":
    """Return per-engine weight vector mirroring the eng_w seam in predict_ensemble16.py.

    Default (all flags OFF): returns np.full(n, 1/n) — byte-identical to
    margins.mean() when dot-producted against the margin vector (D03 §8).

    Reads engine_reliability_weights.json (single authority); learned weights
    only used if beats_equal_weight is True (currently False -> equal-weight).

    Rung selection (D03 §1):
    1. CV_BRAIN_REGIME=1 AND beats_equal AND regime given -> Rung 2 (blocked).
    2. CV_BRAIN_GLS=1 AND decorr artifact present -> Rung 1.
    3. Default -> Rung 0 (equal weight).

    Parameters
    ----------
    preds : list[dict]
        Engine prediction dicts (10-key EnginePred contract, D03 §2.1). Non-empty.
    regime : RegimeVector | None
        Pre-built regime; only used for Rung-2 lookup (blocked today).

    Returns
    -------
    np.ndarray
        Shape (n,), sums to 1.0, index i corresponds to preds[i].

    Raises
    ------
    ValueError
        If preds is empty.
    """
    import numpy as _np  # lazy import

    if not preds:
        raise ValueError("preds must be non-empty")

    engine_names: List[str] = [str(p["engine"]) for p in preds]
    n = len(engine_names)

    _beats_equal = bool(_load_reliability().get("beats_equal_weight", False))

    # Rung 2 (DATA_BLOCKED today: beats_equal_weight=False)
    if flags.is_on("CV_BRAIN_REGIME") and _beats_equal and regime is not None:
        # TODO(P4.1): load brain_regime_weights.json, look up regime cell key,
        #   verify beats_equal=True + n_cell>=200, return per-cell weights.
        #   Fall back to Rung 1/0 if cell absent or beats_equal=False.
        pass

    # Rung 1 (GLS redundancy, gated)
    if flags.is_on("CV_BRAIN_GLS") and os.path.exists(_DECORR_PATH):
        bundle = _rung1_gls(engine_names)
        w = _np.array([bundle.engine_weights[name] for name in engine_names], dtype=float)
        return w / max(float(w.sum()), 1e-12)

    # Rung 0 (equal weight — default, always)
    return _np.full(n, 1.0 / n, dtype=float)


# ---------------------------------------------------------------------------
# Self-check (byte-identical proof; not a test suite)
# ---------------------------------------------------------------------------

def _selfcheck() -> None:
    """Assert Rung-0 is uniform, sums to 1, and is byte-identical to margins.mean()."""
    import numpy as _np

    dummy = [
        {"engine": f"e{i}", "margin_home": float(i), "margin_sd": 5.0,
         "win_prob_home": 0.5, "total": 220.0, "home_pts": 110.0,
         "away_pts": 110.0, "n_models": 1, "n_signals": 0, "notes": ""}
        for i in range(7)
    ]
    w = engine_weights(dummy)
    assert w.shape == (7,)
    assert abs(w.sum() - 1.0) < 1e-9
    assert _np.allclose(w, 1.0 / 7)
    margins = _np.array([float(p["margin_home"]) for p in dummy])
    assert abs(float((w * margins).sum()) - float(margins.mean())) < 1e-12


if __name__ == "__main__":
    _selfcheck()
    print("control_brain selfcheck passed.")
