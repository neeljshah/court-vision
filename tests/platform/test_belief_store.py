"""test_belief_store.py — Synthetic tests for BeliefStore.

All tests use synthetic findings; no real corpora are required.
Tests cover:
  - Beta update math (alpha/beta increments)
  - Posterior mean monotonicity (more SHIPs → higher mean)
  - Time-decay reduces weight of old evidence
  - Pooling / backoff for sparse families
  - JSON round-trips
  - All-REJECT history → posterior mean near 0, sane upper CI bound
  - No edge-claim language in rendered output
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from scripts.research_harness.belief_store import (
    BeliefStore,
    FamilyBelief,
    _PRIOR_ALPHA,
    _PRIOR_BETA,
    _beta_mean,
    _beta_ci as _beta_credible_interval,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _finding(sport: str, family: str, verdict: str, dated: str = "2025-01-01") -> dict:
    return {"sport": sport, "family": family, "verdict": verdict, "dated": dated}


class TestBetaUpdateMath:
    def test_ship_increments_alpha(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("nba", "elo_diff", "SHIP", dated="2025-06-01")
        b = store.get_belief("nba", "elo_diff")
        # alpha should be prior + 1 weight unit
        assert b.alpha == pytest.approx(_PRIOR_ALPHA + 1.0, abs=1e-9)
        assert b.beta == pytest.approx(_PRIOR_BETA, abs=1e-9)

    def test_reject_increments_beta(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("nba", "momentum", "REJECT", dated="2025-06-01")
        b = store.get_belief("nba", "momentum")
        assert b.alpha == pytest.approx(_PRIOR_ALPHA, abs=1e-9)
        assert b.beta == pytest.approx(_PRIOR_BETA + 1.0, abs=1e-9)

    def test_defer_increments_both_small(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("tennis", "rest_diff", "DEFER", dated="2025-06-01")
        b = store.get_belief("tennis", "rest_diff")
        assert b.alpha == pytest.approx(_PRIOR_ALPHA + 0.1, abs=1e-9)
        assert b.beta == pytest.approx(_PRIOR_BETA + 0.1, abs=1e-9)

    def test_multiple_updates_accumulate(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        for _ in range(5):
            store.update_from_finding("nba", "streak", "SHIP", dated="2025-06-01")
        for _ in range(3):
            store.update_from_finding("nba", "streak", "REJECT", dated="2025-06-01")
        b = store.get_belief("nba", "streak")
        assert b.alpha == pytest.approx(_PRIOR_ALPHA + 5.0, abs=1e-9)
        assert b.beta == pytest.approx(_PRIOR_BETA + 3.0, abs=1e-9)

    def test_effective_obs_tracks_weight_count(self) -> None:
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_finding("mlb", "home_adv", "SHIP", dated="2025-01-01")
        store.update_from_finding("mlb", "home_adv", "REJECT", dated="2025-01-01")
        b = store.get_belief("mlb", "home_adv")
        assert b.effective_obs == pytest.approx(2.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 2. Posterior mean monotonicity
# ---------------------------------------------------------------------------

class TestPosteriorMeanMonotonicity:
    def test_more_ships_raises_mean(self) -> None:
        """Adding SHIPs one-by-one strictly raises the posterior mean."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        prev_mean = store.get_belief("nba", "corr_edge").posterior_mean
        for i in range(10):
            store.update_from_finding("nba", "corr_edge", "SHIP", dated="2025-06-01")
            curr_mean = store.get_belief("nba", "corr_edge").posterior_mean
            assert curr_mean > prev_mean, f"Mean did not rise after SHIP #{i+1}"
            prev_mean = curr_mean

    def test_more_rejects_lowers_mean(self) -> None:
        """Adding REJECTs one-by-one strictly lowers the posterior mean."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        # Start with a few SHIPs so we have room to fall
        for _ in range(5):
            store.update_from_finding("tennis", "elo", "SHIP", dated="2025-01-01")
        prev_mean = store.get_belief("tennis", "elo").posterior_mean
        for i in range(10):
            store.update_from_finding("tennis", "elo", "REJECT", dated="2025-06-01")
            curr_mean = store.get_belief("tennis", "elo").posterior_mean
            assert curr_mean < prev_mean, f"Mean did not fall after REJECT #{i+1}"
            prev_mean = curr_mean

    def test_all_ship_mean_above_prior(self) -> None:
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        prior_mean = _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA)
        for _ in range(20):
            store.update_from_finding("soccer", "possession_pct", "SHIP",
                                      dated="2025-06-01")
        b = store.get_belief("soccer", "possession_pct")
        assert b.posterior_mean > prior_mean

    def test_all_reject_mean_below_prior(self) -> None:
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        prior_mean = _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA)
        for _ in range(20):
            store.update_from_finding("mlb", "pitcher_rest", "REJECT",
                                      dated="2025-06-01")
        b = store.get_belief("mlb", "pitcher_rest")
        assert b.posterior_mean < prior_mean


# ---------------------------------------------------------------------------
# 3. Time-decay
# ---------------------------------------------------------------------------

class TestTimeDecay:
    def test_old_evidence_weighted_less_than_recent(self) -> None:
        """Updating with an old finding should change alpha/beta less than
        updating with an equally-verdicted recent finding."""
        store_old = BeliefStore(half_life_days=180.0,
                                reference_date="2026-06-01")
        store_new = BeliefStore(half_life_days=180.0,
                                reference_date="2026-06-01")

        store_old.update_from_finding("nba", "f", "SHIP", dated="2024-01-01")
        store_new.update_from_finding("nba", "f", "SHIP", dated="2026-05-01")

        old_inc = store_old.get_belief("nba", "f").alpha - _PRIOR_ALPHA
        new_inc = store_new.get_belief("nba", "f").alpha - _PRIOR_ALPHA
        assert new_inc > old_inc, (
            f"Recent finding should add more weight: new={new_inc:.4f}, old={old_inc:.4f}"
        )

    def test_very_old_evidence_near_zero_weight(self) -> None:
        """A finding 20 half-lives old should contribute almost nothing."""
        hl = 30.0  # 30-day half-life
        store = BeliefStore(half_life_days=hl, reference_date="2026-06-01")
        # 600 days ago ≈ 20 half-lives
        store.update_from_finding("nba", "g", "SHIP", dated="2024-10-08")
        b = store.get_belief("nba", "g")
        weight = b.alpha - _PRIOR_ALPHA
        assert weight < 1e-4, f"Expected near-zero weight, got {weight:.6f}"

    def test_infinite_half_life_equals_unit_weight(self) -> None:
        """With infinite half-life every finding gets weight exactly 1.0."""
        store = BeliefStore(half_life_days=math.inf,
                            reference_date="2026-06-01")
        store.update_from_finding("soccer", "h", "SHIP", dated="2000-01-01")
        b = store.get_belief("soccer", "h")
        assert b.alpha - _PRIOR_ALPHA == pytest.approx(1.0, abs=1e-9)

    def test_decay_reduces_effective_obs(self) -> None:
        """Effective obs with decay < effective obs without decay."""
        store_decay = BeliefStore(half_life_days=30.0,
                                  reference_date="2026-06-01")
        store_none = BeliefStore(half_life_days=math.inf,
                                 reference_date="2026-06-01")
        for store in (store_decay, store_none):
            store.update_from_finding("mlb", "temp", "REJECT", dated="2025-01-01")
        assert (store_decay.get_belief("mlb", "temp").effective_obs <
                store_none.get_belief("mlb", "temp").effective_obs)


# ---------------------------------------------------------------------------
# 4. Pooling / hierarchical fallback
# ---------------------------------------------------------------------------

class TestPoolingFallback:
    def test_sparse_family_falls_back_to_sport(self) -> None:
        """A family with zero observations should return the sport-level mean,
        which is informed by other families in the same sport."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=5.0)
        # Populate sport "tennis" with many REJECTs on OTHER families
        for i in range(20):
            store.update_from_finding("tennis", f"family_{i}", "REJECT",
                                      dated="2025-06-01")
        # A fresh family with no data should fall back to sport-level
        pm_pooled = store.posterior_mean("tennis", "brand_new_family", pool=True)
        pm_raw = store.get_belief("tennis", "brand_new_family").posterior_mean
        # Sport is all-REJECT so sport-level mean < prior mean; pooled ≤ raw
        assert pm_pooled <= pm_raw

    def test_dense_family_does_not_pool(self) -> None:
        """A family above min_obs should use its own posterior, not sport."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=3.0)
        # Lots of SHIPs for this family
        for _ in range(10):
            store.update_from_finding("nba", "rich_family", "SHIP",
                                      dated="2025-06-01")
        # Lots of REJECTs on other families in the same sport
        for i in range(30):
            store.update_from_finding("nba", f"null_{i}", "REJECT",
                                      dated="2025-06-01")
        pm_pooled = store.posterior_mean("nba", "rich_family", pool=True)
        pm_raw = store.get_belief("nba", "rich_family").posterior_mean
        # Above threshold: pooled == raw
        assert pm_pooled == pytest.approx(pm_raw, abs=1e-9)

    def test_global_fallback_when_sport_also_sparse(self) -> None:
        """When a sport has no data, fall all the way back to global."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=5.0)
        # Global data on another sport
        for _ in range(20):
            store.update_from_finding("mlb", "base_family", "REJECT",
                                      dated="2025-06-01")
        # "tennis" has zero data; should fall back to global
        pm_global = store.posterior_mean("tennis", "unseen_family", pool=True)
        # Global is all-REJECT, so mean should be below prior mean
        assert pm_global < _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA)

    def test_pooling_disabled_uses_own_prior(self) -> None:
        """With pool=False sparse families return their own (prior) mean."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=100.0)
        pm = store.posterior_mean("tennis", "unseen", pool=False)
        prior_mean = _beta_mean(_PRIOR_ALPHA, _PRIOR_BETA)
        assert pm == pytest.approx(prior_mean, abs=1e-9)


# ---------------------------------------------------------------------------
# 5. JSON round-trip
# ---------------------------------------------------------------------------

