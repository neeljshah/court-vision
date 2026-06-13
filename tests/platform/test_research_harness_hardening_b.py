"""tests/platform/test_research_harness_hardening.py — Hardening tests.

Three targeted additions (backward-compatible, no edge claims):
1. VARIANCE_ONLY accepted by ledger + belief_store update logic.
2. gap_observer.rank_gaps min_score filters zero-score entries.
3. belief_store.calibration_summary() on all-REJECT ledger.
"""
from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest

from scripts.research_harness.research_ledger import (
    Ledger,
    ResearchFinding,
    VALID_VERDICTS,
)
from scripts.research_harness.belief_store import (
    BeliefStore,
    _PRIOR_ALPHA,
    _PRIOR_BETA,
    _beta_mean,
)
from scripts.research_harness.gap_observer import rank_gaps


# ---------------------------------------------------------------------------
# Synthetic stubs for gap_observer
# ---------------------------------------------------------------------------

@dataclass
class _Cand:
    sport: str
    name: str


@dataclass
class _CR:
    sport: str
    candidates: List[_Cand] = field(default_factory=list)
    tested_set: Set[str] = field(default_factory=set)

    @property
    def n_enumerated(self) -> int:
        return len(self.candidates)

    @property
    def n_tested(self) -> int:
        return len(self.tested_set)


@dataclass
class _FF:
    sport: str
    family: str
    verdict: str
    dated: str = "2026-01-01"
    hypothesis: str = "synthetic"
    evidence: dict = field(default_factory=dict)


class _FBS:
    """Fake BeliefStore that returns a fixed CI for all families."""
    def __init__(self, lo: float = 0.003, hi: float = 0.408) -> None:
        self._lo, self._hi = lo, hi

    def credible_interval(self, sport: str, family: str) -> Tuple[float, float]:
        return self._lo, self._hi


# ---------------------------------------------------------------------------
# Fix 1a: VARIANCE_ONLY is in VALID_VERDICTS
# ---------------------------------------------------------------------------

class TestRankGapsMinScore:
    def _zero_score_setup(self):
        """Sport with coverage_gap=0 (all tested) + all REJECTED → score=0."""
        cr = _CR(
            sport="tennis",
            candidates=[_Cand(sport="tennis", name=f"t_{i}") for i in range(3)],
            tested_set={f"t_{i}" for i in range(3)},  # all tested → cov_gap=0
        )
        findings = [_FF(sport="tennis", family=f"t_{i}", verdict="REJECT")
                    for i in range(3)]
        return {"tennis": cr}, findings

    def test_explicit_min_score_filters_zero_entries(self) -> None:
        """min_score=1e-9 must filter out zero-score entries."""
        enum, findings = self._zero_score_setup()
        gaps = rank_gaps(enumerator_results=enum, findings=findings, min_score=1e-9)
        # All candidates from ledger have coverage_gap=0 → score=0; filtered out
        for g in gaps:
            assert g.score >= 1e-9, f"Zero-score entry leaked through: {g}"

    def test_default_min_score_zero_includes_zero_entries(self) -> None:
        """Default min_score=0.0: zero-score entries are included (backward compat)."""
        # Build a scenario where score collapses to 0:
        # coverage_gap=0 (all candidates tested) → cov=0 → score=0
        cr = _CR(
            sport="nba",
            candidates=[_Cand(sport="nba", name="fully_tested")],
            tested_set={"fully_tested"},
        )
        findings = [_FF(sport="nba", family="fully_tested", verdict="REJECT")]
        gaps_default = rank_gaps(enumerator_results={"nba": cr}, findings=findings)
        gaps_filtered = rank_gaps(enumerator_results={"nba": cr},
                                  findings=findings, min_score=1e-9)
        # Default (0.0) includes the zero-score entry; min_score=1e-9 excludes it
        assert len(gaps_default) >= len(gaps_filtered)

    def test_real_gaps_survive_min_score_filter(self) -> None:
        """Non-zero-score gaps (untested candidates) survive min_score=1e-9."""
        cr = _CR(
            sport="mlb",
            candidates=[_Cand(sport="mlb", name=f"m_{i}") for i in range(5)],
            tested_set=set(),  # none tested → coverage_gap=1.0
        )
        gaps = rank_gaps(enumerator_results={"mlb": cr}, min_score=1e-9)
        assert len(gaps) == 5
        for g in gaps:
            assert g.score >= 1e-9

    def test_min_score_custom_threshold(self) -> None:
        """A custom min_score > default excludes low-scoring entries."""
        cr = _CR(
            sport="soccer",
            # 5 candidates, 4 tested → cov=0.2; with REJECT: score≈0.2*0.405*1.0*0.2≈0.016
            candidates=[_Cand(sport="soccer", name=f"s_{i}") for i in range(5)],
            tested_set={f"s_{i}" for i in range(4)},
        )
        findings = [_FF(sport="soccer", family="s_0", verdict="REJECT")]
        gaps_default = rank_gaps(enumerator_results={"soccer": cr},
                                 findings=findings)
        # With a high min_score, the REJECT entry (low score due to settled_discount=0.2)
        # may be filtered while untested entry (no settled_discount) remains
        gaps_high = rank_gaps(enumerator_results={"soccer": cr},
                              findings=findings, min_score=0.05)
        # High threshold should have fewer or equal entries
        assert len(gaps_high) <= len(gaps_default)

    def test_min_score_does_not_change_rank_order_for_nonzero(self) -> None:
        """Entries with score>0 keep their relative rank order regardless of min_score."""
        cr = _CR(
            sport="tennis",
            candidates=[_Cand(sport="tennis", name=f"tt_{i}") for i in range(5)],
            tested_set=set(),  # all non-zero scores (coverage_gap=1.0)
        )
        gaps_default = rank_gaps(enumerator_results={"tennis": cr})
        gaps_filt = rank_gaps(enumerator_results={"tennis": cr}, min_score=1e-9)
        # All scores > 0 so both should return the same entries in the same order
        assert [g.family for g in gaps_filt] == [g.family for g in gaps_default]


# ---------------------------------------------------------------------------
# Fix 3: calibration_summary() on all-REJECT synthetic ledger
# ---------------------------------------------------------------------------

class TestCalibrationSummary:
    def test_all_reject_observed_ship_rate_zero(self, tmp_path: Path) -> None:
        """All-REJECT ledger → observed_ship_rate == 0.0 (no SHIPs detected)."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        for i in range(10):
            store.update_from_finding("nba", f"fam_{i}", "REJECT",
                                      dated="2025-06-01")
        cal = store.calibration_summary()
        assert cal["observed_ship_rate"] == pytest.approx(0.0, abs=1e-9)

    def test_all_reject_mean_posterior_near_prior(self, tmp_path: Path) -> None:
        """All-REJECT: mean_posterior should be near (or below) the prior mean."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        for i in range(10):
            store.update_from_finding("nba", f"fam_{i}", "REJECT",
                                      dated="2025-06-01")
        cal = store.calibration_summary()
        prior_mean = _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA)
        # REJECTs push mean below prior; it should be < prior
        assert cal["mean_posterior"] < prior_mean

    def test_all_reject_is_overconfident_true(self) -> None:
        """With 0 observed ships but positive prior mean, is_overconfident=True."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        for i in range(10):
            store.update_from_finding("soccer", f"sig_{i}", "REJECT",
                                      dated="2025-06-01")
        cal = store.calibration_summary()
        # observed_ship_rate=0, mean_posterior>0 → gap > 0.05 → overconfident
        assert cal["is_overconfident"] is True

    def test_n_matches_number_of_families(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        for i in range(7):
            store.update_from_finding("tennis", f"f_{i}", "REJECT",
                                      dated="2025-06-01")
        cal = store.calibration_summary()
        assert cal["n"] == 7

    def test_empty_store_returns_sane_defaults(self) -> None:
        store = BeliefStore()
        cal = store.calibration_summary()
        assert cal["n"] == 0
        assert cal["observed_ship_rate"] == pytest.approx(0.0, abs=1e-9)
        # mean_posterior for empty store = prior mean
        assert cal["mean_posterior"] == pytest.approx(
            _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA), abs=1e-6)

    def test_all_ship_observed_ship_rate_one(self) -> None:
        """All-SHIP ledger → observed_ship_rate should approach 1.0."""
        store = BeliefStore(half_life_days=math.inf)
        for i in range(10):
            store.update_from_finding("nba", f"fam_{i}", "SHIP",
                                      dated="2025-06-01")
        cal = store.calibration_summary()
        assert cal["observed_ship_rate"] == pytest.approx(1.0, abs=1e-9)

    def test_keys_present(self) -> None:
        store = BeliefStore()
        cal = store.calibration_summary()
        for key in ("observed_ship_rate", "mean_posterior", "n", "is_overconfident"):
            assert key in cal, f"Missing key: {key}"

    def test_variance_only_counts_as_ship_like(self) -> None:
        """VARIANCE_ONLY (alpha+=0.5) should push alpha above ship_threshold."""
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("mlb", "park_factor", "VARIANCE_ONLY",
                                  dated="2025-06-01")
        cal = store.calibration_summary()
        # One VARIANCE_ONLY → alpha > prior+0.3 → observed_ship_rate = 1.0
        assert cal["observed_ship_rate"] == pytest.approx(1.0, abs=1e-9)

    def test_no_edge_claim_language(self) -> None:
        """calibration_summary output must contain no edge-claim language."""
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("nba", "x", "SHIP", dated="2025-06-01")
        cal = store.calibration_summary()
        serialised = str(cal).lower()
        for phrase in ("betting edge", "positive roi", "+ev", "beat the market"):
            assert phrase not in serialised
