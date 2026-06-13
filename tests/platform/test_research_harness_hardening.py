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

class TestVarianceOnlyVerdict:
    def test_variance_only_in_valid_verdicts(self) -> None:
        assert "VARIANCE_ONLY" in VALID_VERDICTS

    def test_variance_only_finding_accepted(self, tmp_path: Path) -> None:
        ledger = Ledger(path=tmp_path / "f.jsonl")
        f = ResearchFinding(
            sport="tennis", family="rest_diff",
            hypothesis="Rest-diff explains variance only, no directional edge",
            verdict="VARIANCE_ONLY",
            evidence={"n": 5000, "r2": 0.02},
            what_would_change_my_mind="Directional CLV on 2+ independent corpora",
        )
        assert ledger.append(f) is True
        assert len(ledger.all_findings()) == 1

    def test_variance_only_roundtrips_jsonl(self, tmp_path: Path) -> None:
        p = tmp_path / "f.jsonl"
        ledger = Ledger(path=p)
        ledger.append(ResearchFinding(
            sport="soccer", family="xg_var",
            hypothesis="xG variance signal",
            verdict="VARIANCE_ONLY",
            evidence={},
            what_would_change_my_mind="Positive CLV",
        ))
        ledger2 = Ledger(path=p)
        findings = ledger2.all_findings()
        assert len(findings) == 1
        assert findings[0].verdict == "VARIANCE_ONLY"

    def test_variance_only_in_summarize(self, tmp_path: Path) -> None:
        ledger = Ledger(path=tmp_path / "f.jsonl")
        ledger.append(ResearchFinding(
            sport="mlb", family="home_var",
            hypothesis="Home variance",
            verdict="VARIANCE_ONLY",
            evidence={},
            what_would_change_my_mind="Two corpora",
        ))
        s = ledger.summarize()
        assert s["by_verdict"].get("VARIANCE_ONLY", 0) == 1


# ---------------------------------------------------------------------------
# Fix 1b: BeliefStore maps VARIANCE_ONLY as partial-SHIP (alpha += 0.5*w)
# ---------------------------------------------------------------------------

class TestVarianceOnlyBeliefUpdate:
    def test_variance_only_increments_alpha_not_beta(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("tennis", "rest_diff", "VARIANCE_ONLY",
                                  dated="2025-06-01")
        b = store.get_belief("tennis", "rest_diff")
        assert b.alpha > _PRIOR_ALPHA, "alpha must increase for VARIANCE_ONLY"
        assert b.beta == pytest.approx(_PRIOR_BETA, abs=1e-9), "beta must not change"

    def test_variance_only_alpha_increment_is_half_ship(self) -> None:
        """VARIANCE_ONLY weight=0.5; SHIP weight=1.0 → half the alpha increment."""
        s_vo = BeliefStore(half_life_days=math.inf)
        s_ship = BeliefStore(half_life_days=math.inf)
        s_vo.update_from_finding("nba", "f", "VARIANCE_ONLY", dated="2025-06-01")
        s_ship.update_from_finding("nba", "f", "SHIP", dated="2025-06-01")
        da_vo = s_vo.get_belief("nba", "f").alpha - _PRIOR_ALPHA
        da_ship = s_ship.get_belief("nba", "f").alpha - _PRIOR_ALPHA
        assert da_vo == pytest.approx(da_ship / 2.0, abs=1e-9)

    def test_variance_only_raises_posterior_mean(self) -> None:
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        prior_mean = _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA)
        store.update_from_finding("soccer", "xg", "VARIANCE_ONLY", dated="2025-06-01")
        assert store.get_belief("soccer", "xg").posterior_mean > prior_mean

    def test_reject_defer_ship_unaffected(self) -> None:
        """REJECT/DEFER/SHIP weights are unchanged from before."""
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("nba", "rej", "REJECT", dated="2025-01-01")
        store.update_from_finding("nba", "def", "DEFER", dated="2025-01-01")
        store.update_from_finding("nba", "ship", "SHIP", dated="2025-01-01")
        brej = store.get_belief("nba", "rej")
        bdef = store.get_belief("nba", "def")
        bship = store.get_belief("nba", "ship")
        assert brej.alpha == pytest.approx(_PRIOR_ALPHA, abs=1e-9)
        assert brej.beta == pytest.approx(_PRIOR_BETA + 1.0, abs=1e-9)
        assert bdef.alpha == pytest.approx(_PRIOR_ALPHA + 0.1, abs=1e-9)
        assert bdef.beta == pytest.approx(_PRIOR_BETA + 0.1, abs=1e-9)
        assert bship.alpha == pytest.approx(_PRIOR_ALPHA + 1.0, abs=1e-9)
        assert bship.beta == pytest.approx(_PRIOR_BETA, abs=1e-9)

    def test_update_from_ledger_variance_only(self, tmp_path: Path) -> None:
        ledger = Ledger(path=tmp_path / "f.jsonl")
        ledger.append(ResearchFinding(
            sport="mlb", family="park_factor",
            hypothesis="Park factor explains variance",
            verdict="VARIANCE_ONLY",
            evidence={"n": 3000},
            what_would_change_my_mind="CLV on 2+ corpora",
            dated="2025-06-01",
        ))
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_ledger(ledger)
        b = store.get_belief("mlb", "park_factor")
        assert b.alpha > _PRIOR_ALPHA
        assert b.beta == pytest.approx(_PRIOR_BETA, abs=1e-9)


# ---------------------------------------------------------------------------
# Fix 2: gap_observer min_score filters zero-score entries
# ---------------------------------------------------------------------------

