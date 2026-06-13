"""tests/platform/test_belief_decay.py — Unit tests for BeliefStore time-decay logic.

Tests:
  1. Old finding contributes exponentially less than a recent one (weight ratio).
  2. Half-life parameterisation: shorter half-life => faster decay.
  3. Infinite half-life => unit weight (no decay).
  4. Decay reduces effective_obs vs no-decay baseline.
  5. All-REJECT decayed history still yields posterior mean >= 0 and near the prior floor.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research_harness.belief_store import (
    BeliefStore,
    _PRIOR_ALPHA,
    _PRIOR_BETA,
)

_SPORT = "test_sport"
_FAM = "test_family"

# Reference date used as "today" in all tests so results are deterministic.
_TODAY = "2026-01-01"


# ---------------------------------------------------------------------------
# 1. Weight ratio matches exp(-ln2 * age / half_life)
# ---------------------------------------------------------------------------

class TestWeightRatioMatchesFormula:
    """An old finding contributes exp(-ln2*age/hl) relative to a brand-new one."""

    def _expected_weight(self, age_days: float, half_life: float) -> float:
        return math.exp(-math.log(2.0) * age_days / half_life)

    def test_weight_ratio_90_day_half_life(self):
        """REJECT dated 90 days ago should carry half the weight of a REJECT today."""
        hl = 90.0
        recent_date = "2026-01-01"   # same as reference
        old_date = "2025-10-03"      # 90 days before reference

        store_recent = BeliefStore(half_life_days=hl, reference_date=_TODAY)
        store_recent.update_from_finding(_SPORT, _FAM, "REJECT", dated=recent_date)

        store_old = BeliefStore(half_life_days=hl, reference_date=_TODAY)
        store_old.update_from_finding(_SPORT, _FAM, "REJECT", dated=old_date)

        obs_recent = store_recent.get_belief(_SPORT, _FAM).effective_obs
        obs_old = store_old.get_belief(_SPORT, _FAM).effective_obs

        expected_old_weight = self._expected_weight(90.0, hl)
        # Recent weight should be ~1.0; old weight should be ~0.5
        assert abs(obs_recent - 1.0) < 1e-9, f"Recent weight: {obs_recent}"
        assert abs(obs_old - expected_old_weight) < 1e-6, (
            f"Old weight {obs_old} != expected {expected_old_weight}"
        )

    def test_weight_ratio_180_day_half_life(self):
        """180-day-old finding with 180-day half-life => weight ratio 0.5."""
        hl = 180.0
        old_date = "2025-07-05"   # 180 days before 2026-01-01

        store_recent = BeliefStore(half_life_days=hl, reference_date=_TODAY)
        store_recent.update_from_finding(_SPORT, _FAM, "REJECT", dated="2026-01-01")

        store_old = BeliefStore(half_life_days=hl, reference_date=_TODAY)
        store_old.update_from_finding(_SPORT, _FAM, "REJECT", dated=old_date)

        obs_recent = store_recent.get_belief(_SPORT, _FAM).effective_obs
        obs_old = store_old.get_belief(_SPORT, _FAM).effective_obs

        expected = self._expected_weight(180.0, hl)
        assert abs(obs_recent - 1.0) < 1e-9
        assert abs(obs_old - expected) < 1e-6

    def test_weight_ratio_arbitrary_age(self):
        """Weight ratio for arbitrary age matches the formula exactly."""
        hl = 60.0
        age = 45.0
        import datetime
        ref = datetime.date(2026, 1, 1)
        old_d = ref - datetime.timedelta(days=age)
        old_date = old_d.isoformat()

        store = BeliefStore(half_life_days=hl, reference_date=_TODAY)
        store.update_from_finding(_SPORT, _FAM, "REJECT", dated=old_date)

        obs = store.get_belief(_SPORT, _FAM).effective_obs
        expected = self._expected_weight(age, hl)
        assert abs(obs - expected) < 1e-6, f"obs={obs}, expected={expected}"


# ---------------------------------------------------------------------------
# 2. Shorter half-life => faster decay
# ---------------------------------------------------------------------------

class TestShorterHalfLifeFasterDecay:
    """A shorter half-life must produce a lower effective weight for a fixed old date."""

    def _obs_for_hl(self, half_life: float, age_days: float) -> float:
        import datetime
        ref = datetime.date(2026, 1, 1)
        old_d = ref - datetime.timedelta(days=age_days)
        store = BeliefStore(half_life_days=half_life, reference_date=_TODAY)
        store.update_from_finding(_SPORT, _FAM, "REJECT", dated=old_d.isoformat())
        return store.get_belief(_SPORT, _FAM).effective_obs

    def test_30_hl_decays_faster_than_180_hl(self):
        age = 60
        obs_short = self._obs_for_hl(30.0, age)
        obs_long = self._obs_for_hl(180.0, age)
        assert obs_short < obs_long, (
            f"short-hl obs {obs_short} should be < long-hl obs {obs_long}"
        )

    def test_monotone_decay_across_three_half_lives(self):
        age = 90
        obs_values = [self._obs_for_hl(hl, age) for hl in (30.0, 90.0, 360.0)]
        assert obs_values[0] < obs_values[1] < obs_values[2], (
            f"Expected monotone increase in obs with longer half-life: {obs_values}"
        )

    def test_very_short_hl_approaches_zero(self):
        """With half-life of 1 day and a 365-day-old finding, weight is near zero."""
        obs = self._obs_for_hl(1.0, 365.0)
        assert obs < 1e-100, f"Expected near-zero obs, got {obs}"


# ---------------------------------------------------------------------------
# 3. Infinite / very-large half-life => unit weight
# ---------------------------------------------------------------------------

class TestInfiniteHalfLifeNoDecay:
    """With infinite half-life every finding gets weight 1.0 regardless of age."""

    def test_infinite_hl_unit_weight(self):
        store = BeliefStore(half_life_days=math.inf, reference_date=_TODAY)
        store.update_from_finding(_SPORT, _FAM, "REJECT", dated="2000-01-01")
        obs = store.get_belief(_SPORT, _FAM).effective_obs
        assert abs(obs - 1.0) < 1e-9, f"Infinite hl obs={obs}"

    def test_very_large_hl_approaches_unit_weight(self):
        """A very large (but finite) half-life gives weight extremely close to 1."""
        store = BeliefStore(half_life_days=1e12, reference_date=_TODAY)
        store.update_from_finding(_SPORT, _FAM, "REJECT", dated="2025-01-01")
        obs = store.get_belief(_SPORT, _FAM).effective_obs
        assert obs > 0.999, f"Very large hl obs={obs} should be ~1.0"

    def test_no_dated_string_gives_unit_weight(self):
        """Empty dated string => weight 1.0 (per _age_weight guard)."""
        store = BeliefStore(half_life_days=30.0, reference_date=_TODAY)
        store.update_from_finding(_SPORT, _FAM, "REJECT", dated="")
        obs = store.get_belief(_SPORT, _FAM).effective_obs
        assert abs(obs - 1.0) < 1e-9, f"Empty dated obs={obs}"

    def test_multiple_old_findings_inf_hl_full_weight(self):
        """Three old findings with inf hl => effective_obs == 3."""
        store = BeliefStore(half_life_days=math.inf, reference_date=_TODAY)
        for d in ("2000-01-01", "2010-06-15", "2019-12-31"):
            store.update_from_finding(_SPORT, _FAM, "REJECT", dated=d)
        obs = store.get_belief(_SPORT, _FAM).effective_obs
        assert abs(obs - 3.0) < 1e-9, f"expected 3, got {obs}"


# ---------------------------------------------------------------------------
# 4. Decay reduces effective_obs vs no-decay baseline
# ---------------------------------------------------------------------------

class TestDecayReducesEffectiveObs:
    """effective_obs with time-decay must be < effective_obs with no decay."""

    def test_single_old_finding_obs_comparison(self):
        old_date = "2025-07-05"  # 180 days before reference
        store_decay = BeliefStore(half_life_days=180.0, reference_date=_TODAY)
        store_decay.update_from_finding(_SPORT, _FAM, "REJECT", dated=old_date)

        store_nodecay = BeliefStore(half_life_days=math.inf, reference_date=_TODAY)
        store_nodecay.update_from_finding(_SPORT, _FAM, "REJECT", dated=old_date)

        obs_decay = store_decay.get_belief(_SPORT, _FAM).effective_obs
        obs_nodecay = store_nodecay.get_belief(_SPORT, _FAM).effective_obs

        assert obs_decay < obs_nodecay, (
            f"Decay obs={obs_decay} should be < nodecay obs={obs_nodecay}"
        )

    def test_multiple_findings_mixed_ages_obs_comparison(self):
        dates = ["2024-01-01", "2025-01-01", "2025-10-01"]
        store_decay = BeliefStore(half_life_days=90.0, reference_date=_TODAY)
        store_nodecay = BeliefStore(half_life_days=math.inf, reference_date=_TODAY)
        for d in dates:
            store_decay.update_from_finding(_SPORT, _FAM, "REJECT", dated=d)
            store_nodecay.update_from_finding(_SPORT, _FAM, "REJECT", dated=d)

        obs_decay = store_decay.get_belief(_SPORT, _FAM).effective_obs
        obs_nodecay = store_nodecay.get_belief(_SPORT, _FAM).effective_obs

        assert obs_decay < obs_nodecay, (
            f"Decay obs={obs_decay} should be < nodecay obs={obs_nodecay}"
        )

    def test_recent_finding_decay_minimal(self):
        """A same-day finding: decay obs should be essentially 1.0."""
        store = BeliefStore(half_life_days=30.0, reference_date=_TODAY)
        store.update_from_finding(_SPORT, _FAM, "REJECT", dated=_TODAY)
        obs = store.get_belief(_SPORT, _FAM).effective_obs
        assert abs(obs - 1.0) < 1e-9, f"Same-day obs={obs}"


# ---------------------------------------------------------------------------
# 5. All-REJECT decayed history => posterior mean near prior floor, not below 0
# ---------------------------------------------------------------------------

class TestDecayedAllRejectHistory:
    """A history of decayed REJECTs must stay non-negative and close to the prior floor."""

    _PRIOR_MEAN = _PRIOR_ALPHA / (_PRIOR_ALPHA + _PRIOR_BETA)  # ~0.10

    def test_posterior_mean_non_negative_after_decayed_rejects(self):
        store = BeliefStore(half_life_days=30.0, reference_date=_TODAY)
        for d in ("2023-01-01", "2024-01-01", "2024-06-01", "2025-01-01"):
            store.update_from_finding(_SPORT, _FAM, "REJECT", dated=d)
        pm = store.get_belief(_SPORT, _FAM).posterior_mean
        assert pm >= 0.0, f"posterior_mean={pm} must not be negative"

    def test_posterior_mean_not_far_below_prior_floor_after_decay(self):
        """Decayed-REJECT history should not pull posterior below ~half the prior mean."""
        store = BeliefStore(half_life_days=7.0, reference_date=_TODAY)
        # 10 very old REJECTs that are nearly zero-weight
        for yr in range(2010, 2020):
            store.update_from_finding(_SPORT, _FAM, "REJECT", dated=f"{yr}-01-01")
        pm = store.get_belief(_SPORT, _FAM).posterior_mean
        # Should still be reasonably close to the prior mean (not crushed to 0)
        assert pm >= self._PRIOR_MEAN * 0.5, (
            f"posterior_mean={pm:.4f} is unexpectedly far below prior mean {self._PRIOR_MEAN}"
        )

    def test_posterior_mean_bounded_above_zero_many_rejects(self):
        """Even 100 heavy REJECTs with finite half-life can't make P(ship) < 0."""
        store = BeliefStore(half_life_days=180.0, reference_date=_TODAY)
        for i in range(100):
            store.update_from_finding(_SPORT, _FAM, "REJECT", dated="2025-01-01")
        pm = store.get_belief(_SPORT, _FAM).posterior_mean
        assert pm >= 0.0, f"posterior_mean={pm} must not be negative"
        assert pm < 1.0, f"posterior_mean={pm} must not exceed 1.0"

    def test_prior_floor_without_any_findings(self):
        """No findings => posterior == prior mean exactly."""
        store = BeliefStore(reference_date=_TODAY)
        pm = store.get_belief(_SPORT, _FAM).posterior_mean
        assert abs(pm - self._PRIOR_MEAN) < 1e-9, (
            f"prior-only pm={pm}, expected {self._PRIOR_MEAN}"
        )
