"""domains.tennis.signal_catalog_joint — JOINT/interaction candidate signals.

Extends the Renaissance search.  Each candidate is a PURE TRANSFORM of base
cols 0-4 only, combining ≥2 cols via product/ratio/threshold/conditional.
Zero new data; zero raw corpus reads; leak-freeness inherited from adapter.

CONTRACT — base columns (indices match adapter_helpers._feature_bundle_impl):
    base[:,0]=elo_diff  base[:,1]=surf_diff  base[:,2]=best_of
    base[:,3]=rest_days_a  base[:,4]=rest_days_b
    signal_col=win_prob_p1 (blended Elo); target=winner {0,1}

HONEST DISCIPLINE: expected verdicts pre-written as REJECT. A SHIP verdict
is flagged as a probable artifact — single-fold lifts are artifacts. NO edge
claimed.  F5: ZERO imports from domains.nba/src.data/src.sim/src.tracking/
src.pipeline/domains.mlb/domains.soccer/basketball_nba. PRIVATE.
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
_IDX_ELO, _IDX_SURF, _IDX_BO, _IDX_RA, _IDX_RB = 0, 1, 2, 3, 4


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    """Re-export for backward compatibility (tests import this name)."""
    return _derive_bundle_impl(b, s)


# ---------------------------------------------------------------------------
# 8 JOINT/interaction candidate signals — each combines ≥2 base cols
# ---------------------------------------------------------------------------

class EloRestInteractionSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff×rest_diff — rest advantage scaled by quality gap; fully priced by sharp fatigue models."""
    name: str = "tennis_joint_elo_rest"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff × (rest_a-rest_b): rest advantage scaled by quality gap.",
            rationale="Product of two public priced features. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class SurfDiffEloDampedSignal(Signal):
    """Expected gate verdict: REJECT. surf_diff/(1+|elo_diff|) — surface specialist residual attenuated by overall quality gap; priced by sharp surface-Elo models."""
    name: str = "tennis_joint_surf_elo_damped"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="surf_diff/(1+|elo_diff|): surface edge after discounting overall Elo.",
            rationale="Higher-order public transform; sharp books price this. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class Bo5EloDiffSignal(Signal):
    """Expected gate verdict: REJECT. (best_of==5)×|elo_diff| — GS format amplifies better player; sparse and fully priced in tournament-Elo models."""
    name: str = "tennis_joint_bo5_elo_gap"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(best_of==5)×|elo_diff|: Elo gap matters more in Bo5 formats.",
            rationale="Sparse GS sub-population; priced in GS-specific models. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class SignedRestEloDiffSignal(Signal):
    """Expected gate verdict: REJECT. sign(elo_diff)×rest_diff — directional rest advantage aligned with favourite; sharper interaction but still public/priced."""
    name: str = "tennis_joint_signed_rest_elo"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="sign(elo_diff)×rest_diff: rest edge when favouring the stronger player.",
            rationale="Directional public transform; in sharp fatigue models. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class SurfEloAbsDiffSignal(Signal):
    """Expected gate verdict: REJECT. |surf_diff-elo_diff|×best_of — surface/overall disagreement magnitude scaled by format; three-way higher-order public interaction."""
    name: str = "tennis_joint_surf_elo_absdiff_bo"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|surf_diff-elo_diff|×best_of: surface/overall disagreement × format length.",
            rationale="Three-way higher-order public signal. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestCloseMatchSignal(Signal):
    """Expected gate verdict: REJECT. rest_diff/(1+|elo_diff|)×(best_of/3) — rest matters most in close, long matches; all factors public/priced."""
    name: str = "tennis_joint_rest_close_match_bo"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="rest_diff/(1+|elo_diff|)×(best_of/3): rest most predictive in close long matches.",
            rationale="Complex three-factor; all public/priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloSurfProductSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff×surf_diff — bilinear interaction; large when overall and surface gaps agree, near-zero when they disagree; priced by composite-Elo models."""
    name: str = "tennis_joint_elo_surf_product"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff×surf_diff: bilinear interaction of overall and surface quality gaps.",
            rationale="Alignment of two public ratings; priced by composite-Elo. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class RestAsymmetryBo5Signal(Signal):
    """Expected gate verdict: REJECT. (rest_a/(rest_b+1))×(best_of==5) — rest ratio restricted to Bo5; sparse and public; priced in GS fatigue models."""
    name: str = "tennis_joint_rest_ratio_bo5"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
    def build(self, ctx: AsOfContext) -> SignalValue: return None
    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(rest_a/(rest_b+1))×(best_of==5): rest ratio in Grand Slam formats only.",
            rationale="Ratio + sparse Bo5 interaction; fully public/priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


CATALOG_JOINT_SIGNALS: Tuple[type, ...] = (
    EloRestInteractionSignal, SurfDiffEloDampedSignal, Bo5EloDiffSignal,
    SignedRestEloDiffSignal, SurfEloAbsDiffSignal, RestCloseMatchSignal,
    EloSurfProductSignal, RestAsymmetryBo5Signal,
)


# ---------------------------------------------------------------------------
# Base-column transforms (no raw corpus reads; leak-freeness inherited)
# ---------------------------------------------------------------------------

def _compute_joint_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive joint signal_col from proven base matrix only (columns 0-4)."""
    elo = base[:, _IDX_ELO]; surf = base[:, _IDX_SURF]; bo = base[:, _IDX_BO]
    ra = base[:, _IDX_RA]; rb = base[:, _IDX_RB]; rd = ra - rb
    name = signal_cls.name  # type: ignore[attr-defined]
    if name == EloRestInteractionSignal.name:      return elo * rd
    if name == SurfDiffEloDampedSignal.name:       return surf / (1.0 + np.abs(elo))
    if name == Bo5EloDiffSignal.name:              return (bo == 5.0).astype(float) * np.abs(elo)
    if name == SignedRestEloDiffSignal.name:       return np.sign(elo) * rd
    if name == SurfEloAbsDiffSignal.name:          return np.abs(surf - elo) * bo
    if name == RestCloseMatchSignal.name:          return (rd / (1.0 + np.abs(elo))) * (bo / 3.0)
    if name == EloSurfProductSignal.name:          return elo * surf
    if name == RestAsymmetryBo5Signal.name:        return (ra / (rb + 1.0)) * (bo == 5.0).astype(float)
    logger.warning("unknown joint signal '%s', returning zeros", name)
    return np.zeros(base.shape[0], dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner — delegates to catalog_common
# ---------------------------------------------------------------------------

_JOINT_HEADER_LINES = [
    "\n## Contract\nSignal columns are PURE TRANSFORMS of the proven leak-free adapter "
    "bundle (base: elo_diff, surf_diff, best_of, rest_days_a, rest_days_b) — each combines "
    "≥2 base cols via product/ratio/threshold/conditional. No raw corpus reads; leak-freeness "
    "inherited from `TennisAdapter.feature_bundle`.",
]

_JOINT_TITLE = (
    "# Honest JOINT signal catalog — markets are efficient; expected and observed "
    "verdicts are REJECT/DEFER. NO edge claimed."
)


def run_joint_catalog(
    adapter: Any,
    seasons: Sequence[int],
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run every CATALOG_JOINT_SIGNALS candidate through the real gate.

    Returns {"ok": bool, "verdicts": list[dict]}.  Writes markdown to out_path.
    SHIP verdicts are flagged loudly — probable artifact, no edge claimed.
    """
    return run_catalog_common(
        signal_classes=CATALOG_JOINT_SIGNALS,
        adapter=adapter,
        seasons=seasons,
        compute_fn=_compute_joint_signal_col,
        out_path=out_path,
        header_lines=_JOINT_HEADER_LINES,
        title=_JOINT_TITLE,
        ship_log_prefix="JOINT CATALOG",
    )


__all__ = [
    "EloRestInteractionSignal", "SurfDiffEloDampedSignal", "Bo5EloDiffSignal",
    "SignedRestEloDiffSignal", "SurfEloAbsDiffSignal", "RestCloseMatchSignal",
    "EloSurfProductSignal", "RestAsymmetryBo5Signal",
    "CATALOG_JOINT_SIGNALS", "_compute_joint_signal_col", "_derive_bundle",
    "run_joint_catalog",
]
