"""scripts.platformkit.ingame.ingame_recal_persist -- persist the validated
in-game isotonic recalibration surface to a versioned JSON so the proven Q4
calibration win stops being orphaned (computed but never saved).

DESIGN
------
ingame_blend_recal.run() returns a RecalResult.  When the verdict is SHIP or
PARTIAL the fitted per-bucket isotonic maps are real and should be reusable by the
serve path (ig-recal-apply lane).  This module:

  1. Calls run() (or accepts a pre-computed RecalResult + fitted regressor dict).
  2. For SHIP / PARTIAL: serialises the per-bucket iso maps as lists of
     (threshold, prediction) pairs (sklearn Isotonic exposes X_thresholds_ and
     y_thresholds_), plus the RecalResult metadata, into
     scripts/platformkit/ingame/surfaces/nba_recal.json atomically (tmp + os.replace).
  3. For NOT_IMPROVED / INSUFFICIENT_DATA: writes NOTHING (no orphan file).
  4. load_recal_surface() deserialises the JSON so callers can round-trip.

ARTIFACT SCHEMA (surfaces/nba_recal.json)
  {
    "sport": "nba",
    "verdict": "SHIP" | "PARTIAL",
    "n_fit": <int>,
    "n_eval": <int>,
    "honesty": "CALIBRATION only; no dollar edge implied",
    "per_bucket": {          # mirrors RecalResult.per_bucket keys
      "bucket_0": {
        "n": <int>,
        "ece_raw": <float>, "ece_recal": <float>,
        "brier_raw": <float>, "brier_recal": <float>,
        "ece_improved": <bool>, "brier_not_worse": <bool>,
        "iso_map": {         # None if identity (thin / no sklearn)
          "x_thresholds": [...],
          "y_thresholds": [...]
        }
      }, ...
    }
  }

No $ / roi / pnl key anywhere.  ASCII only.  <=300 LOC.  stdlib + numpy + sklearn.
INVARIANTS: never edit src/ or kernel/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.ingame.ingame_blend_recal import (
    RecalResult,
    SegmentRecalibrator,
    _IdentityReg,
    _N_BUCKETS,
    eval_recal,
    fit_recal,
    run,
    split_ab,
)
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
    time_bucket,
)

# Verdicts that warrant persisting the surface.
_PERSIST_VERDICTS = {"SHIP", "PARTIAL"}

# Minimum samples per bucket cell for an iso map to be meaningful.
# Mirrors _MIN_SEGMENT in ingame_blend_recal.
_MIN_CELL = 20

# Default surfaces directory relative to this file.
_SURFACES_DIR = Path(__file__).parent / "surfaces"

# Name of the persisted recal artifact.
_ARTIFACT_NAME = "nba_recal.json"


# ---------------------------------------------------------------------------
# iso-map extraction
# ---------------------------------------------------------------------------

def _extract_iso_map(reg: object) -> Optional[Dict]:
    """Extract (x_thresholds, y_thresholds) from a fitted IsotonicRegression.

    Returns None for _IdentityReg or any object without the sklearn attributes
    (e.g., when sklearn is absent or the bucket was too thin to fit).
    """
    if isinstance(reg, _IdentityReg):
        return None
    x_attr = getattr(reg, "X_thresholds_", None)
    y_attr = getattr(reg, "y_thresholds_", None)
    if x_attr is None or y_attr is None:
        return None
    return {
        "x_thresholds": [round(float(v), 8) for v in x_attr],
        "y_thresholds": [round(float(v), 8) for v in y_attr],
    }


# ---------------------------------------------------------------------------
# persistence / loading
# ---------------------------------------------------------------------------

def _surfaces_dir(surfaces_dir: Optional[str] = None) -> Path:
    if surfaces_dir is not None:
        return Path(surfaces_dir)
    return _SURFACES_DIR


def persist_recal_surface(
    result: RecalResult,
    recal: SegmentRecalibrator,
    sport: str = "nba",
    surfaces_dir: Optional[str] = None,
) -> Optional[str]:
    """Atomically write the recal surface JSON if verdict warrants it.

    Parameters
    ----------
    result       : RecalResult from eval_recal / run
    recal        : the fitted SegmentRecalibrator (holds the iso regressors)
    sport        : sport tag used in the artifact key
    surfaces_dir : override for the surfaces/ directory (for tests)

    Returns
    -------
    Path of the written file as a str, or None if nothing was written.
    """
    if result.verdict not in _PERSIST_VERDICTS:
        return None  # NOT_IMPROVED / INSUFFICIENT_DATA -> write nothing

    # Build per_bucket enriched with iso_map
    enriched: Dict = {}
    for key, bucket_meta in result.per_bucket.items():
        # Parse bucket index from "bucket_0", "bucket_1", ...
        try:
            b_idx = int(key.split("_")[1])
        except (IndexError, ValueError):
            b_idx = -1

        reg = recal.regs.get(b_idx, _IdentityReg())
        iso_map = _extract_iso_map(reg)

        enriched[key] = dict(bucket_meta)  # shallow copy of RecalResult metadata
        enriched[key]["iso_map"] = iso_map  # None for identity / thin

    artifact: Dict = {
        "sport": sport,
        "verdict": result.verdict,
        "n_fit": result.n_fit,
        "n_eval": result.n_eval,
        "honesty": "CALIBRATION only; no dollar edge implied",
        "per_bucket": enriched,
    }

    sdir = _surfaces_dir(surfaces_dir)
    sdir.mkdir(parents=True, exist_ok=True)
    out = str(sdir / _ARTIFACT_NAME)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    os.replace(tmp, out)
    return out


def load_recal_surface(
    sport: str = "nba",
    surfaces_dir: Optional[str] = None,
) -> Optional[Dict]:
    """Load the persisted recal surface JSON, or None if absent / unreadable."""
    sdir = _surfaces_dir(surfaces_dir)
    path = sdir / _ARTIFACT_NAME
    if not path.exists():
        return None
    try:
        with open(str(path), encoding="ascii") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# High-level runner: run recal + persist in one call
# ---------------------------------------------------------------------------

def run_and_persist(
    states: List[dict],
    sport: str = "nba",
    surfaces_dir: Optional[str] = None,
    min_cell: int = _MIN_CELL,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[RecalResult, Optional[str]]:
    """Run the full blend+recal pipeline and persist the surface when warranted.

    Parameters
    ----------
    states       : in-game state dicts (keys: game_id, seconds_remaining,
                   p0, p_live, outcome, ...)
    sport        : sport tag
    surfaces_dir : override for surfaces/ directory (tests inject a tmp dir)
    min_cell     : min samples per bucket to fit a real iso map (else identity)
    rng          : optional RNG for reproducibility

    Returns
    -------
    (result, path_or_none)
      result       : RecalResult (verdict, per_bucket, metrics)
      path_or_none : path written, or None if verdict did not warrant a write
    """
    a, b = split_ab(states)
    if not a or not b:
        return RecalResult(verdict="INSUFFICIENT_DATA"), None

    # Fit blend surface on A
    surf = fit_weight_surface(a, min_cell=min_cell)

    # Fit per-bucket isotonic regressors on A
    recal = fit_recal(a, surf, rng=rng, shuffle_labels=False)

    # Evaluate on B
    from scripts.platformkit.ingame.ingame_blend_recal import eval_recal as _eval
    result = _eval(a, b, min_cell=min_cell, rng=rng)

    # Persist if warranted
    path = persist_recal_surface(result, recal, sport=sport,
                                  surfaces_dir=surfaces_dir)
    return result, path


__all__ = [
    "persist_recal_surface",
    "load_recal_surface",
    "run_and_persist",
    "_extract_iso_map",
    "_ARTIFACT_NAME",
    "_PERSIST_VERDICTS",
]
