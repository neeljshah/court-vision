"""domains.tennis.signal_catalog — Honest signal-discovery catalog for tennis.

Runs 7 candidate signals through the REAL gate (src.loop.gate.evaluate) via the
proven-leak-free TennisAdapter.feature_bundle seam.

CONTRACT — base columns (frozen; indices match adapter_helpers._feature_bundle_impl):
    base[:,0] = elo_diff      base[:,1] = surf_diff     base[:,2] = best_of
    base[:,3] = rest_days_a   base[:,4] = rest_days_b
    signal_col = win_prob_p1 (blended Elo); target = winner {0,1}

Each candidate derives a NEW signal_col from these columns ONLY — no additional
corpus reads.  Leak-freeness is inherited from the adapter (SECOND_DOMAIN_PROOF §3.1).

HONEST DISCIPLINE: expected verdicts are REJECT/DEFER (efficient market). A SHIP
verdict is flagged as a probable artifact; no edge is claimed.

F5: ZERO imports from domains.nba/src.data/src.sim/src.tracking/src.pipeline.
PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from src.loop.gate import FeatureBundle, evaluate  # noqa: F401 — AST-scanned by tests
from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from scripts.platformkit.catalog_common import (
    derive_bundle as _derive_bundle_impl,
    run_catalog_common,
    write_catalog_report as _write_report_impl,
)

logger = logging.getLogger(__name__)

_IDX_ELO_DIFF, _IDX_SURF_DIFF, _IDX_BEST_OF, _IDX_REST_A, _IDX_REST_B = 0, 1, 2, 3, 4


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    """Re-export for backward compatibility (tests import this name)."""
    return _derive_bundle_impl(b, s)


# ---------------------------------------------------------------------------
# Candidate signals (7 total; each derived from base columns 0-4)
# ---------------------------------------------------------------------------

class AbsRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. |rest_a-rest_b| — magnitude discards directionality; fully public and priced by sharp books."""
    name: str = "tennis_abs_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        ra, rb = ctx.extra.get("rest_days_a"), ctx.extra.get("rest_days_b")
        return None if (ra is None or rb is None) else float(abs(float(ra) - float(rb)))
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|rest_a-rest_b| predicts outcome beyond Elo.",
            rationale="Magnitude-only; public; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class SurfVsOverallEloSignal(Signal):
    """Expected gate verdict: REJECT. surf_diff-elo_diff captures surface specialism residual; priced by sharp surface-Elo models."""
    name: str = "tennis_surf_vs_overall_elo"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        return None  # derived from base columns only
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="surf_diff - elo_diff captures surface specialist residual.",
            rationale="Public surface-Elo; already priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloGapMagnitudeSignal(Signal):
    """Expected gate verdict: REJECT. |elo_diff| — mismatch magnitude; non-directional transform of a base feature already in the matrix."""
    name: str = "tennis_elo_gap_magnitude"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|elo_diff| adds calibration beyond signed Elo.",
            rationale="Redundant with base matrix; markets aware. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class BestOf5Signal(Signal):
    """Expected gate verdict: REJECT or DEFER (power). Bo5 indicator (Grand Slams) — sparse; public; priced; gate may DEFER on thin sub-population."""
    name: str = "tennis_best_of_5"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        b = ctx.extra.get("best_of")
        return None if b is None else (1.0 if float(b) == 5.0 else 0.0)
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="Bo5 format produces outcomes not captured by Elo.",
            rationale="Sparse; public; priced. DEFER or REJECT is honest outcome.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestSurfaceInteractionSignal(Signal):
    """Expected gate verdict: REJECT. rest_diff × 1/(1+|elo_diff|) — rest advantage weighted by match closeness; higher-order public interaction."""
    name: str = "tennis_rest_surface_interaction"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="rest_diff × 1/(1+|elo_diff|): rest matters more in close matches.",
            rationale="Higher-order public interaction; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class SurfSpecialistFlagSignal(Signal):
    """Expected gate verdict: REJECT. Binary flag: surf_diff-elo_diff > 100 Elo pts; surface specialist label fully priced by sharp-book surface models."""
    name: str = "tennis_surf_specialist_flag"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="surf_diff-elo_diff > 100 flags a strong surface specialist.",
            rationale="Public narrative; embedded in sharp surface-Elo. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class SignedRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. Unclipped rest_a-rest_b — differs from FatigueRestSignal only at extremes (>15 days), which are rare and noisy."""
    name: str = "tennis_signed_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue:
        ra, rb = ctx.extra.get("rest_days_a"), ctx.extra.get("rest_days_b")
        return None if (ra is None or rb is None) else float(float(ra) - float(rb))
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="Unclipped rest_a-rest_b vs. clipped FatigueRestSignal.",
            rationale="Extreme rest gaps are rare/noisy/public. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


CATALOG_SIGNALS: Tuple[type, ...] = (
    AbsRestDiffSignal, SurfVsOverallEloSignal, EloGapMagnitudeSignal,
    BestOf5Signal, RestSurfaceInteractionSignal, SurfSpecialistFlagSignal,
    SignedRestDiffSignal,
)


# ---------------------------------------------------------------------------
# Base-column transforms (no raw corpus reads; leak-freeness inherited)
# ---------------------------------------------------------------------------

def _compute_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive signal_col from proven base matrix only (columns 0-4)."""
    elo = base[:, _IDX_ELO_DIFF]; surf = base[:, _IDX_SURF_DIFF]
    bo = base[:, _IDX_BEST_OF]
    ra = base[:, _IDX_REST_A]; rb = base[:, _IDX_REST_B]; rd = ra - rb
    name = signal_cls.name  # type: ignore[attr-defined]
    if name == AbsRestDiffSignal.name:           return np.abs(rd)
    if name == SurfVsOverallEloSignal.name:      return surf - elo
    if name == EloGapMagnitudeSignal.name:       return np.abs(elo)
    if name == BestOf5Signal.name:               return (bo == 5.0).astype(float)
    if name == RestSurfaceInteractionSignal.name:return rd / (1.0 + np.abs(elo))
    if name == SurfSpecialistFlagSignal.name:    return ((surf - elo) > 100.0).astype(float)
    if name == SignedRestDiffSignal.name:        return rd
    logger.warning("unknown signal '%s', returning zeros", name)
    return np.zeros(base.shape[0], dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner — delegates to catalog_common
# ---------------------------------------------------------------------------

_HEADER_LINES = [
    "\n## Contract\nSignal columns derived from the **proven leak-free adapter bundle** "
    "(base: elo_diff, surf_diff, best_of, rest_days_a, rest_days_b).  "
    "No raw corpus reads; leak-freeness inherited from `TennisAdapter.feature_bundle`.",
]


def run_catalog(
    adapter: Any,
    seasons: Sequence[int],
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run every CATALOG_SIGNALS candidate through the real gate.

    Mirrors run_v3: bundle = adapter.feature_bundle(hyp, seasons);
    sig._gate_matrix = derived_bundle; evaluate(sig, device="cpu", n_splits=3).
    Returns {"ok": bool, "verdicts": list[dict]}.  Writes markdown to out_path if given.
    SHIP verdicts are flagged loudly — probable artifact, no edge claimed.
    """
    return run_catalog_common(
        signal_classes=CATALOG_SIGNALS,
        adapter=adapter,
        seasons=seasons,
        compute_fn=_compute_signal_col,
        out_path=out_path,
        header_lines=_HEADER_LINES,
        ship_log_prefix="CATALOG",
    )


__all__ = [
    "AbsRestDiffSignal", "SurfVsOverallEloSignal", "EloGapMagnitudeSignal",
    "BestOf5Signal", "RestSurfaceInteractionSignal", "SurfSpecialistFlagSignal",
    "SignedRestDiffSignal", "CATALOG_SIGNALS", "run_catalog",
    "_compute_signal_col", "_derive_bundle",
]
