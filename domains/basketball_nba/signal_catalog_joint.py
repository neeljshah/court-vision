"""domains.basketball_nba.signal_catalog_joint — JOINT/interaction catalog for NBA.

Runs 8 joint/interaction candidate signals through the REAL gate (src.loop.gate.evaluate)
via the proven-leak-free NBAAdapter.feature_bundle seam.

CONTRACT — base columns (frozen; indices match adapter.feature_bundle output):
    base[:,0] = elo_home          base[:,1] = elo_away
    base[:,2] = elo_diff_hfa      base[:,3] = rest_days_home
    base[:,4] = rest_days_away    base[:,5] = home_b2b
    base[:,6] = away_b2b          base[:,7] = rolling_win10_home
    signal_col = p_home_elo; target = home win {0,1}

Each candidate derives a NEW signal_col from >= 2 base columns ONLY. Leak-freeness
inherited from the adapter. Expected verdicts are REJECT/DEFER. SHIP is a probable
artifact; no edge claimed.

CORPUS SCOPE NOTE (honesty):
    This catalog operates on a schedule-level corpus. Joint signals involving
    box-score stats (e.g. AST × rest) are NOT testable here — the corpus
    contains no box-score columns.  Such signals are a future data extension.

F5: ZERO imports from domains.tennis / domains.soccer / domains.mlb /
    src.data / src.sim / src.tracking / src.pipeline.
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

# Base column indices (frozen contract — never change without updating adapter)
_IDX_ELO_HOME, _IDX_ELO_AWAY, _IDX_ELO_DIFF_HFA = 0, 1, 2
_IDX_REST_HOME, _IDX_REST_AWAY = 3, 4
_IDX_HOME_B2B, _IDX_AWAY_B2B = 5, 6
_IDX_WIN10_HOME = 7


def _derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    """Re-export for backward compatibility (tests import this name)."""
    return _derive_bundle_impl(b, s)


# ---------------------------------------------------------------------------
# Joint/interaction candidate signals (8 total; each uses >= 2 base columns)
# ---------------------------------------------------------------------------

class EloXRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff_hfa * (rest_home - rest_away) — Elo
    quality gap amplified by the signed rest advantage; both inputs are public;
    NBA books account for rest-weighted Elo at opening. Redundant with base."""
    name: str = "nba_joint_elo_diff_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff_hfa × (rest_home - rest_away): quality gap weighted by rest.",
            rationale="Public Elo × public rest; higher-order but priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloXHomeB2BSignal(Signal):
    """Expected gate verdict: REJECT. elo_diff_hfa * (1 - home_b2b) — quality edge
    suppressed when home team is on a back-to-back; public interaction; NBA books
    open with sharp b2b adjustments already baked in. Priced at open."""
    name: str = "nba_joint_elo_diff_x_home_b2b"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="elo_diff_hfa × (1 - home_b2b): quality edge discounted on home b2b.",
            rationale="Public Elo × public schedule; NBA b2b priced at open. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class B2BDifferentialSignal(Signal):
    """Expected gate verdict: REJECT. away_b2b - home_b2b — signed b2b disadvantage
    differential; +1 when away is on b2b and home is not, -1 vice versa, 0 if same;
    public schedule information; NBA books known to adjust for b2b parity. Priced."""
    name: str = "nba_joint_b2b_differential"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="away_b2b - home_b2b: signed b2b disadvantage differential.",
            rationale="Public schedule; b2b differential priced by NBA books. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class Win10XEloSignal(Signal):
    """Expected gate verdict: REJECT. rolling_win10_home * elo_diff_hfa — recent
    home momentum amplified by structural Elo quality; higher-order public product;
    both components fully priced by closing lines. No new information."""
    name: str = "nba_joint_win10_x_elo_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="rolling_win10_home × elo_diff_hfa: momentum amplified by quality gap.",
            rationale="Public momentum × public Elo; priced by closing line. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloClosenessXRestSignal(Signal):
    """Expected gate verdict: REJECT. (1 / (1 + elo_diff_hfa**2)) * (rest_home -
    rest_away) — rest differential matters more in evenly-matched games; non-linear
    but fully public combination; NBA closing lines capture this interaction."""
    name: str = "nba_joint_elo_closeness_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(1/(1+elo_diff²)) × (rest_diff): rest matters more in close matchups.",
            rationale="Non-linear but public; both components priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class AbsRestDiffXEloMismatchSignal(Signal):
    """Expected gate verdict: REJECT. |rest_diff| * |elo_diff_hfa| — fatigue magnitude
    × quality mismatch magnitude; two-way absolute interaction; non-directional so
    carries even less information than the signed version; public; priced."""
    name: str = "nba_joint_abs_rest_x_abs_elo"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="|rest_diff| × |elo_diff_hfa|: fatigue magnitude × quality magnitude.",
            rationale="Both magnitudes public; non-directional; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class Win10XRestDiffSignal(Signal):
    """Expected gate verdict: REJECT. rolling_win10_home * (rest_home - rest_away) —
    recent home form scaled by rest advantage; both components are public; NBA
    bettors and books adjust for form + rest simultaneously; priced at open."""
    name: str = "nba_joint_win10_x_rest_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="rolling_win10_home × (rest_home - rest_away): form scaled by rest.",
            rationale="Public form × public rest; higher-order; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


class EloRatioXB2BDiffSignal(Signal):
    """Expected gate verdict: REJECT. (elo_home / elo_away) * (away_b2b - home_b2b) —
    Elo ratio (monotone transform of elo_diff) weighted by b2b differential; non-linear
    but fully public; both numerator/denominator always positive (>0) in practice."""
    name: str = "nba_joint_elo_ratio_x_b2b_diff"
    target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target="winprob", scope="pregame",
            statement="(elo_home / elo_away) × (away_b2b - home_b2b): quality ratio × b2b.",
            rationale="Monotone Elo reparametrisation × public schedule; priced. REJECT expected.",
            source="seed", expected_verdict="REJECT", priority="P2")


CATALOG_SIGNALS: Tuple[type, ...] = (
    EloXRestDiffSignal, EloXHomeB2BSignal, B2BDifferentialSignal,
    Win10XEloSignal, EloClosenessXRestSignal, AbsRestDiffXEloMismatchSignal,
    Win10XRestDiffSignal, EloRatioXB2BDiffSignal,
)


# ---------------------------------------------------------------------------
# Base-column transforms (no raw corpus reads; leak-freeness inherited)
# ---------------------------------------------------------------------------

def _compute_signal_col(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Derive signal_col from proven base matrix only (columns 0-7)."""
    elo_h = base[:, _IDX_ELO_HOME]; elo_a = base[:, _IDX_ELO_AWAY]
    elo_d = base[:, _IDX_ELO_DIFF_HFA]
    rh = base[:, _IDX_REST_HOME]; ra = base[:, _IDX_REST_AWAY]
    hb2b = base[:, _IDX_HOME_B2B]; ab2b = base[:, _IDX_AWAY_B2B]
    w10 = base[:, _IDX_WIN10_HOME]
    name = signal_cls.name  # type: ignore[attr-defined]
    if name == EloXRestDiffSignal.name:
        return elo_d * (rh - ra)
    if name == EloXHomeB2BSignal.name:
        return elo_d * (1.0 - hb2b)
    if name == B2BDifferentialSignal.name:
        return ab2b - hb2b
    if name == Win10XEloSignal.name:
        return w10 * elo_d
    if name == EloClosenessXRestSignal.name:
        return (1.0 / (1.0 + elo_d ** 2)) * (rh - ra)
    if name == AbsRestDiffXEloMismatchSignal.name:
        return np.abs(rh - ra) * np.abs(elo_d)
    if name == Win10XRestDiffSignal.name:
        return w10 * (rh - ra)
    if name == EloRatioXB2BDiffSignal.name:
        # Guard against division by zero — Elo values always positive in practice.
        safe_a = np.where(elo_a == 0, 1.0, elo_a)
        return (elo_h / safe_a) * (ab2b - hb2b)
    logger.warning("unknown signal '%s', returning zeros", name)
    return np.zeros(base.shape[0], dtype=float)


# ---------------------------------------------------------------------------
# Catalog runner — delegates to catalog_common
# ---------------------------------------------------------------------------

_JOINT_HEADER_LINES = [
    "\n## Contract\nSignal columns are pure algebraic interactions of >= 2 base columns "
    "(elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, "
    "home_b2b, away_b2b, rolling_win10_home). "
    "No raw corpus reads; leak-freeness inherited from `NBAAdapter.feature_bundle`.\n\n"
    "**Corpus scope:** schedule-level only.  Box-score joint signals (e.g. AST × rest) "
    "require a box-score corpus extension — NOT testable at this layer.",
]

_JOINT_TITLE = (
    "# Honest joint/interaction signal catalog — markets are efficient; expected "
    "and observed verdicts are REJECT/DEFER. NO edge claimed."
)


def run_catalog(
    adapter: Any,
    seasons: Sequence[int],
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run every CATALOG_SIGNALS candidate through the real gate.

    bundle = adapter.feature_bundle(hyp, seasons);
    sig._gate_matrix = derived_bundle; evaluate(sig, device='cpu', n_splits=3).
    Returns {"ok": bool, "verdicts": list[dict]}. Writes markdown to out_path if given.
    SHIP verdicts flagged loudly — probable artifact, no edge claimed.
    """
    return run_catalog_common(
        signal_classes=CATALOG_SIGNALS,
        adapter=adapter,
        seasons=seasons,
        compute_fn=_compute_signal_col,
        out_path=out_path,
        header_lines=_JOINT_HEADER_LINES,
        extra_bundle_kwargs={},
        ship_log_prefix="NBA JOINT CATALOG",
        title=_JOINT_TITLE,
    )


__all__ = [
    "EloXRestDiffSignal", "EloXHomeB2BSignal", "B2BDifferentialSignal",
    "Win10XEloSignal", "EloClosenessXRestSignal", "AbsRestDiffXEloMismatchSignal",
    "Win10XRestDiffSignal", "EloRatioXB2BDiffSignal",
    "CATALOG_SIGNALS", "run_catalog", "_compute_signal_col", "_derive_bundle",
]
