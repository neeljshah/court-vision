"""scripts.platformkit.ingame.ingame_blend_recal_multisport -- 4-sport per-sport
post-blend isotonic recalibration harness.

WHAT
----
Applies the validated ig-blend-isocal core (ingame_blend_recal) independently to
each of NBA, MLB, soccer, and tennis.  For each sport the harness:

  1. Loads the sport's on-disk generic-schema states (state_diff, frac_elapsed,
     p0, outcome, game_id -- the frozen contract used by ingame_gate_generic).
  2. Converts frac_elapsed -> seconds_remaining so the ingame_blend_recal
     time_bucket function (which expects seconds_remaining) works unchanged.
  3. Adds p_live = sigmoid(slope * state_diff * frac_elapsed) as the live-model
     signal (identical to ingame_gate_generic_models.fit_base applied per A-split).
  4. Splits A/B by game_id parity (leak-free, disjoint games).
  5. Fits the blend weight surface + per-bucket isotonic regressors on A.
  6. Evaluates on B: reports ECE and Brier (recal vs raw) per time-bucket.

VERDICTS
--------
  SUFFICIENT  -> ECE(recal) <= ECE(raw) AND Brier(recal) <= Brier(raw) + TOL
                 on the POOLED B eval (calibration win, no $ implied).
  REJECT      -> recal is worse -- honest null result.
  INSUFFICIENT_DATA -> sport has < MIN_STATES_SPORT states after load/filter.

PLANTED-NULL GUARD
------------------
  When shuffle_labels=True, outcomes on A are shuffled before fitting regressors.
  A legitimate isotonic fitter on noise produces near-identity output; any
  calibration improvement claim after shuffled-label fitting is an artifact.
  The per-sport verdict MUST NOT be "SUFFICIENT" in this mode.

HONESTY
-------
  No $ / roi / pnl / profit / edge field anywhere.
  verdict == CALIBRATION only.
  INSUFFICIENT_DATA for thin sports is honest -- never forced green.

<=300 LOC; ASCII-only; numpy + sklearn + stdlib only at runtime; no network.
INVARIANTS: never edit src/ or kernel/; build only under scripts/platformkit/.

Per-file test (run this, not the full suite):
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_blend_recal_multisport.py -q
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.ingame.ingame_blend_recal import (
    RecalResult,
    eval_recal,
    split_ab,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Total "seconds" we map the [0,1] frac_elapsed onto.
# 2880 = 48 min NBA; using the same total for all sports keeps time_bucket
# consistent (the function only needs a comparable scale, not real time).
_TOTAL_SECONDS = 2880.0

# Minimum states a sport corpus must have after load + filter to qualify.
_MIN_STATES_SPORT = 50

# Brier tolerance: recal Brier may exceed raw Brier by at most this.
_BRIER_TOL = 1e-4

# Logistic slope for the live-model p_live: sigmoid(slope * state_diff * frac).
# Sport-agnostic default; calibrated so the logit stays in a reasonable range.
_LIVE_SLOPE = 0.15

# Required columns in the generic corpus schema.
_REQUIRED_COLS = ("game_id", "state_diff", "frac_elapsed", "p0", "outcome")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def _frac_to_seconds(frac_elapsed: float) -> float:
    """Convert frac_elapsed in [0,1] to seconds_remaining."""
    return _TOTAL_SECONDS * max(0.0, 1.0 - float(frac_elapsed))


def _to_blend_state(row: dict) -> dict:
    """Convert a generic-schema row to the ingame_blend_recal state dict format.

    Adds seconds_remaining (from frac_elapsed) and p_live (logistic live model).
    score_diff is an alias for state_diff (blend surface uses score_diff).
    """
    fe = float(row["frac_elapsed"])
    sd = float(row["state_diff"])
    p_live = float(np.clip(_sigmoid(_LIVE_SLOPE * sd * (fe + 0.05)), 0.01, 0.99))
    return {
        "game_id": int(row["game_id"]) if str(row["game_id"]).lstrip("-").isdigit()
                   else abs(hash(str(row["game_id"]))) % (2 ** 31),
        "seconds_remaining": _frac_to_seconds(fe),
        "score_diff": sd,
        "p0": float(np.clip(float(row["p0"]), 0.01, 0.99)),
        "p_live": p_live,
        "outcome": int(row["outcome"]),
    }


def load_sport_states(paths: Sequence[str]) -> List[dict]:
    """Load + validate generic-schema parquets and convert to blend-state dicts.

    Silently drops rows missing required columns or with out-of-range values.
    Never raises -- a broken file yields zero rows from that file.
    """
    import pandas as pd

    states: List[dict] = []
    for path in paths:
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        missing = [c for c in _REQUIRED_COLS if c not in df.columns]
        if missing:
            continue
        for r in df.itertuples(index=False):
            try:
                fe = float(r.frac_elapsed)
                p0 = float(r.p0)
                y = int(r.outcome)
            except (TypeError, ValueError):
                continue
            if not (0.0 <= fe <= 1.0) or not (0.0 <= p0 <= 1.0) or y not in (0, 1):
                continue
            states.append(_to_blend_state({
                "game_id": r.game_id,
                "state_diff": r.state_diff,
                "frac_elapsed": fe,
                "p0": p0,
                "outcome": y,
            }))
    return states


# ---------------------------------------------------------------------------
# Per-sport recalibration
# ---------------------------------------------------------------------------

def recal_sport(states: List[dict], *,
                shuffle_labels: bool = False,
                rng: Optional[np.random.Generator] = None,
                min_cell: int = 10) -> RecalResult:
    """Run blend-recal for ONE sport's states.

    Returns RecalResult with verdict:
      SUFFICIENT        -- ECE non-worse AND Brier non-worse on pooled B.
      REJECT            -- recal did not improve (honest null).
      INSUFFICIENT_DATA -- fewer than _MIN_STATES_SPORT states.
    """
    if len(states) < _MIN_STATES_SPORT:
        return RecalResult(verdict="INSUFFICIENT_DATA")

    a, b = split_ab(states)
    if not a or not b:
        return RecalResult(verdict="INSUFFICIENT_DATA")

    result = eval_recal(a, b, shuffle_labels=shuffle_labels,
                         rng=rng, min_cell=min_cell)

    # Remap SHIP/PARTIAL/NOT_IMPROVED -> SUFFICIENT/REJECT for multisport API
    if result.verdict in ("SHIP", "PARTIAL"):
        pooled_ece_ok = result.ece_recal_pooled <= result.ece_raw_pooled
        pooled_brier_ok = result.brier_recal_pooled <= result.brier_raw_pooled + _BRIER_TOL
        verdict = "SUFFICIENT" if (pooled_ece_ok and pooled_brier_ok) else "REJECT"
    elif result.verdict == "NOT_IMPROVED":
        verdict = "REJECT"
    else:
        verdict = result.verdict  # INSUFFICIENT_DATA pass-through

    result.verdict = verdict
    return result


# ---------------------------------------------------------------------------
# Multi-sport result
# ---------------------------------------------------------------------------

@dataclass
class MultisportRecalResult:
    """Per-sport RecalResult container with aggregate summary."""
    per_sport: Dict[str, RecalResult] = field(default_factory=dict)
    planted_null: bool = False

    def to_dict(self) -> Dict:
        return {
            "planted_null": self.planted_null,
            "honesty": "CALIBRATION only; no dollar edge implied",
            "per_sport": {
                sport: res.to_dict()
                for sport, res in self.per_sport.items()
            },
        }

    def verdict_summary(self) -> Dict[str, str]:
        return {sport: res.verdict for sport, res in self.per_sport.items()}


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def run_multisport(sport_paths: Dict[str, Sequence[str]], *,
                   shuffle_labels: bool = False,
                   rng: Optional[np.random.Generator] = None,
                   min_cell: int = 10,
                   min_states: int = _MIN_STATES_SPORT) -> MultisportRecalResult:
    """Run blend-recal for each sport in `sport_paths`.

    Parameters
    ----------
    sport_paths : mapping sport_name -> list of parquet paths for that sport.
    shuffle_labels : planted-null mode (shuffle outcomes on A before fitting).
    rng : optional RNG for reproducibility.
    min_cell : passed to eval_recal (sparse blend surface cells).
    min_states : override the per-sport minimum states threshold.

    Returns MultisportRecalResult with per-sport RecalResult entries.
    """
    out = MultisportRecalResult(planted_null=shuffle_labels)
    for sport, paths in sport_paths.items():
        states = load_sport_states(list(paths))
        if len(states) < min_states:
            out.per_sport[sport] = RecalResult(verdict="INSUFFICIENT_DATA")
            continue
        out.per_sport[sport] = recal_sport(
            states,
            shuffle_labels=shuffle_labels,
            rng=rng,
            min_cell=min_cell,
        )
    return out
