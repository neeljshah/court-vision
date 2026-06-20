"""scripts.platformkit.ingame.ingame_recal_producer -- fits the validated
per-time-bucket isotonic recalibration surface on the fit-season blended-prob
corpus and persists surfaces/nba_recal.json ONLY when the
ingame_served_reliability gate passes (PASS or PARTIAL).

DESIGN
------
This module closes the end-to-end orphan: ingame_recal_apply.load_recal_map
expects surfaces/nba_recal.json to exist, but nothing previously produced it.

PIPELINE
  1. Split states into A (even game_id) and B (odd game_id) using split_ab.
  2. Fit blend weight surface + per-bucket isotonic regressors on A via
     ingame_blend_recal.fit_recal.
  3. Gate via ingame_served_reliability.run_scoreboard(A, B).
  4. Verdict PASS or PARTIAL -> extract iso knots from the fitted regressors
     and write surfaces/nba_recal.json in the schema ingame_recal_apply reads:
       {
         "sport": "nba",
         "verdict": "PASS" | "PARTIAL",
         "n_buckets": 4,
         "n_fit": <int>,
         "n_eval": <int>,
         "honesty": "CALIBRATION only; no dollar edge implied",
         "EDGE_CLAIMED": false,
         "per_bucket": {...},   # from ServedReliabilityResult
         "buckets": {           # apply-module schema: str(b) -> {x, y}
           "0": {"x": [...], "y": [...]},
           ...
         }
       }
  5. Verdict REJECT or INSUFFICIENT_DATA -> writes NOTHING (no orphan file).

HONEST RAILS
  * CALIBRATION not edge. No $ key. EDGE_CLAIMED: false always.
  * do-no-harm: never writes on NOT_IMPROVED / thin / REJECT.
  * stale-never-green: verdict recomputed fresh every run() call.
  * never raises: all exceptions caught and surfaced as INSUFFICIENT_DATA.

ASCII only. <=300 LOC. stdlib + numpy + sklearn. INVARIANTS: never edit src/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
from scripts.platformkit.ingame.ingame_blend_recal import (
    SegmentRecalibrator,
    _IdentityReg,
    fit_recal,
    split_ab,
)
from scripts.platformkit.ingame.ingame_served_reliability import (
    ServedReliabilityResult,
    run_scoreboard,
)

# Verdicts from ingame_served_reliability that permit writing the artifact.
_PERSIST_VERDICTS = {"PASS", "PARTIAL"}

# Minimum samples per bucket to emit a real iso map (else identity -> None).
_MIN_CELL = 20

# Default surfaces directory relative to this file.
_SURFACES_DIR = Path(__file__).parent / "surfaces"

# Name of the persisted recal artifact (same location as ingame_recal_apply reads).
_ARTIFACT_NAME = "nba_recal.json"

_N_BUCKETS = 4


# ---------------------------------------------------------------------------
# iso-map extraction helpers
# ---------------------------------------------------------------------------

def _extract_bucket_map(reg: object) -> Optional[Dict]:
    """Extract {x, y} knots from a fitted IsotonicRegression; None for identity.

    ingame_recal_apply.load_recal_map expects {"x": [...], "y": [...]}.
    IsotonicRegression exposes X_thresholds_ (sorted ascending) and
    y_thresholds_ (non-decreasing).
    """
    if isinstance(reg, _IdentityReg):
        return None
    x_attr = getattr(reg, "X_thresholds_", None)
    y_attr = getattr(reg, "y_thresholds_", None)
    if x_attr is None or y_attr is None:
        return None
    x = [round(float(v), 8) for v in x_attr]
    y = [round(float(v), 8) for v in y_attr]
    if len(x) == 0 or len(x) != len(y):
        return None
    return {"x": x, "y": y}


def _build_apply_buckets(recal: SegmentRecalibrator) -> Dict[str, Dict]:
    """Build the 'buckets' dict in the schema ingame_recal_apply.load_recal_map reads.

    For each bucket: if the iso map exists emit {"x": [...], "y": [...]};
    otherwise emit an identity knot pair so apply_recal can still round-trip.
    """
    buckets: Dict[str, Dict] = {}
    for b in range(recal.n_buckets):
        reg = recal.regs.get(b, _IdentityReg())
        iso = _extract_bucket_map(reg)
        if iso is None:
            # Identity passthrough: two-knot linear map [0,1]->[0,1]
            iso = {"x": [0.0, 1.0], "y": [0.0, 1.0]}
        buckets[str(b)] = iso
    return buckets


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _surfaces_dir(surfaces_dir: Optional[str] = None) -> Path:
    if surfaces_dir is not None:
        return Path(surfaces_dir)
    return _SURFACES_DIR


def _write_artifact(
    result: ServedReliabilityResult,
    recal: SegmentRecalibrator,
    sport: str,
    surfaces_dir: Optional[str],
) -> str:
    """Atomically write the recal artifact JSON; return path written."""
    buckets = _build_apply_buckets(recal)

    artifact: Dict = {
        "sport": sport,
        "verdict": result.verdict,
        "n_buckets": recal.n_buckets,
        "n_fit": result.n_fit,
        "n_eval": result.n_eval,
        "honesty": "CALIBRATION only; no dollar edge implied",
        "EDGE_CLAIMED": False,
        "per_bucket": result.per_bucket,
        "buckets": buckets,
    }

    sdir = _surfaces_dir(surfaces_dir)
    sdir.mkdir(parents=True, exist_ok=True)
    out = str(sdir / _ARTIFACT_NAME)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    os.replace(tmp, out)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(
    states: List[dict],
    sport: str = "nba",
    surfaces_dir: Optional[str] = None,
    min_cell: int = _MIN_CELL,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[ServedReliabilityResult, Optional[str]]:
    """Fit isotonic recal on A, gate via served-reliability on B, persist if warranted.

    Parameters
    ----------
    states       : in-game state dicts (keys: game_id, seconds_remaining,
                   p0, p_live, score_diff, outcome).
    sport        : sport tag written into the artifact.
    surfaces_dir : override for surfaces/ directory (tests inject a tmp dir).
    min_cell     : min samples per cell for blend surface fit.
    rng          : optional RNG (unused here; accepted for API consistency).

    Returns
    -------
    (result, path_or_none)
      result       : ServedReliabilityResult (verdict, per_bucket, metrics).
      path_or_none : path of written artifact, or None if verdict did not warrant write.

    Never raises -- all exceptions produce (INSUFFICIENT_DATA result, None).
    """
    try:
        a, b = split_ab(states)
        if not a or not b:
            return ServedReliabilityResult(verdict="INSUFFICIENT_DATA"), None

        # Fit blend weight surface on A
        surf = fit_weight_surface(a, min_cell=min_cell)

        # Fit per-bucket isotonic regressors on A
        recal = fit_recal(a, surf, rng=rng, shuffle_labels=False)

        # Gate: score served reliability on B (never touched during fit)
        result = run_scoreboard(a, b, recal=recal, min_cell=min_cell)

        # Persist only on PASS or PARTIAL
        if result.verdict not in _PERSIST_VERDICTS:
            return result, None

        path = _write_artifact(result, recal, sport=sport,
                               surfaces_dir=surfaces_dir)
        return result, path

    except Exception:  # noqa: BLE001 -- never raise
        return ServedReliabilityResult(verdict="INSUFFICIENT_DATA"), None


__all__ = [
    "run",
    "_extract_bucket_map",
    "_build_apply_buckets",
    "_ARTIFACT_NAME",
    "_PERSIST_VERDICTS",
]
