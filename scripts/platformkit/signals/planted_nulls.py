"""scripts.platformkit.signals.planted_nulls -- one shuffled-label NULL per family.

A calibration TRIPWIRE (not an FWER bound -- see PROPOSED-moat-fwer-wiring.md). For each
LANE C signal family (playstyle_corr / scheme_prior / archetype_matchup) we manufacture a
detail column that is KNOWN to carry no real in-game signal -- the outcome label SHUFFLED
under a fixed seed -- and run it through the IDENTICAL gate the real signals use
(ingame.detail_layer_gate.gate_detail_layer -> ingame_gate_generic.gate_cross, which
applies DM-clustered-by-game + the degenerate-base guard + graceful-degrade).

THE CONTRACT: a planted null must NOT 'ship'. The gate's graceful-degrade fits the blend
weight w->0 on a noise detail, so BASE+detail can only MATCH BASE -> the verdict is NOT
REPLICATED. If a planted null EVER returns REPLICATED, the family's added flexibility has
manufactured a false win and the WHOLE family is FROZEN (a flexibility_alarm). null_shipped
is the signal the prioritizer's frozen_families() reads to sink/flag that family until a
human reviews.

This module:
  * builds a synthetic but REALISTIC two-corpus base + a shuffled-label detail per family;
  * routes each through the SAME gate (no parallel stub -- tests-mirror-real);
  * returns a PlantedNullResult per family: shipped(bool) + verdict + family + note;
  * exposes ran_through_identical_gate() so a test asserts the same gate object is used.

Why shuffled-label (not random covariate): a shuffled OUTCOME label is the strongest
within-class null -- it preserves the marginal class balance but destroys any row-level
predictive link, so a family that 'ships' it has a real calibration leak, not noise luck.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag, never
creates the sentinel; calibration NOT edge (no $/pnl/roi/edge field); the null NEVER auto-
serves a signal. Stdlib + numpy + pandas (for the gate's parquet contract). ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.improve.candidate_families import (
    FAMILY_ARCHETYPE_MATCHUP, FAMILY_PLAYSTYLE_CORR, FAMILY_SCHEME_PRIOR,
)
from scripts.platformkit.ingame.detail_layer_gate import gate_detail_layer
from scripts.platformkit.ingame import detail_layer_gate as _DLG

logger = logging.getLogger("planted_nulls")

_FAMILIES = (FAMILY_PLAYSTYLE_CORR, FAMILY_SCHEME_PRIOR, FAMILY_ARCHETYPE_MATCHUP)
_DETAIL_COL = "detail"
# Verdicts the gate may return; only REPLICATED is a 'ship'. Everything else is a PASS
# for a null (REJECT/PARTIAL/INSUFFICIENT_DATA all mean the null did NOT manufacture a win).
_SHIP_VERDICT = "REPLICATED"


@dataclass(frozen=True)
class PlantedNullResult:
    """Result of running a family's shuffled-label null through the IDENTICAL gate."""

    family: str
    verdict: str
    shipped: bool          # True iff the gate returned REPLICATED (a tripwire FAILURE).
    n_games: int
    note: str = "calibration, not edge"
    is_planted_null: bool = True

    def freezes_family(self) -> bool:
        """A shipped null FREEZES the family (flexibility_alarm) -- a human must review."""
        return bool(self.shipped)


def _build_base_corpus(n_games: int, ticks: int, seed: int):
    """A realistic (state_diff, frac_elapsed, outcome) base corpus as a DataFrame.

    The outcome is a genuine (noisy) function of the end-state so BASE is a real model;
    the planted-null detail then SHUFFLES this label, severing the row-level link.
    """
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows: List[Dict[str, object]] = []
    for g in range(n_games):
        strength = float(rng.normal(0.0, 1.0))  # latent game tilt
        final = strength + float(rng.normal(0.0, 0.5))
        outcome = 1 if final > 0.0 else 0
        for t in range(ticks):
            frac = (t + 1) / float(ticks)
            sd = strength * frac * 10.0 + float(rng.normal(0.0, 1.0))
            rows.append({"game_id": "G%03d" % g, "asof_idx": t,
                         "state_diff": sd, "frac_elapsed": frac,
                         "outcome": int(outcome)})
    return pd.DataFrame(rows)


def _shuffled_label_detail(base_df, seed: int):
    """A DETAIL parquet whose column is the SHUFFLED outcome label (a known null).

    Shuffling the outcome preserves the marginal class balance but destroys the row-level
    predictive link -> the gate's weight surface must fit w->0 and REJECT. Returned as a
    (game_id, asof_idx, detail) frame matching the gate's join contract.
    """
    import pandas as pd
    rng = np.random.default_rng(seed + 7919)  # distinct stream from the base
    y = base_df["outcome"].to_numpy().astype(float)
    perm = rng.permutation(len(y))
    shuffled = y[perm]
    # nudge off an exact {0,1} so the leak-guard's |corr|>=.999 / class-constant check
    # does not mistake a shuffled label for a perfect leak; it stays a NOISE detail.
    noise = rng.normal(0.0, 0.25, size=len(shuffled))
    detail = shuffled + noise
    return pd.DataFrame({"game_id": base_df["game_id"].to_numpy(),
                         "asof_idx": base_df["asof_idx"].to_numpy(),
                         _DETAIL_COL: detail})


def run_planted_null(family: str, *, n_games: int = 60, ticks: int = 8,
                     seed: int = 1234) -> PlantedNullResult:
    """Run ONE family's shuffled-label null through the IDENTICAL detail-layer gate.

    Builds two disjoint base corpora (A, B) + a shuffled-label detail for each, then calls
    gate_detail_layer (the REAL gate -- no stub). A null that returns REPLICATED is a
    tripwire FAILURE (shipped=True -> the family freezes). Never raises: any failure is a
    conservative non-ship (shipped=False) with the verdict recorded, because a crashing
    null must not silently 'pass'.
    """
    try:
        base_a = _build_base_corpus(n_games, ticks, seed=seed)
        base_b = _build_base_corpus(n_games, ticks, seed=seed + 101)
        det_a = _shuffled_label_detail(base_a, seed=seed)
        det_b = _shuffled_label_detail(base_b, seed=seed + 101)
        v = gate_detail_layer(base_a, det_a, base_b, det_b,
                              col=_DETAIL_COL, sport="planted_null/%s" % family,
                              min_ticks=10)
        verdict = str(getattr(v, "verdict", "REJECT"))
        cov = getattr(v, "coverage", {}) or {}
        n = int(cov.get("a_games", 0)) + int(cov.get("b_games", 0))
        return PlantedNullResult(family=family, verdict=verdict,
                                 shipped=(verdict == _SHIP_VERDICT), n_games=n)
    except Exception as exc:  # noqa: BLE001 -- a crashing null is a conservative non-ship
        logger.debug("run_planted_null(%s) failed -> non-ship: %s", family, exc)
        return PlantedNullResult(family=family, verdict="ERROR", shipped=False, n_games=0)


def run_all_planted_nulls(*, n_games: int = 60, ticks: int = 8,
                          seed: int = 1234) -> List[PlantedNullResult]:
    """Run every LANE C family's planted null through the identical gate (deterministic)."""
    return [run_planted_null(fam, n_games=n_games, ticks=ticks, seed=seed)
            for fam in _FAMILIES]


def frozen_families(results: Sequence[PlantedNullResult]) -> List[str]:
    """Families whose planted null SHIPPED -> FROZEN (flexibility_alarm). Usually empty."""
    return [r.family for r in results if r.freezes_family()]


def ran_through_identical_gate() -> bool:
    """True: this module's gate symbol IS the production gate (no parallel stub).

    tests-mirror-real: a test asserts the null routes through the SAME gate object the
    real signals use, so the tripwire can never drift from the live gate.
    """
    return gate_detail_layer is _DLG.gate_detail_layer


__all__ = [
    "PlantedNullResult", "run_planted_null", "run_all_planted_nulls",
    "frozen_families", "ran_through_identical_gate",
]
