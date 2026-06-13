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


class TestJsonRoundTrip:
    def test_save_and_load_preserves_beliefs(self) -> None:
        store = BeliefStore(half_life_days=90.0)
        store.update_from_finding("nba", "ast_edge", "SHIP", dated="2025-06-01")
        store.update_from_finding("nba", "reb_edge", "REJECT", dated="2025-05-01")
        store.update_from_finding("soccer", "xg_ratio", "DEFER", dated="2025-04-01")

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "beliefs.json"
            store.save(p)
            loaded = BeliefStore.load(p)

        for sport, family in [("nba", "ast_edge"), ("nba", "reb_edge"),
                               ("soccer", "xg_ratio")]:
            orig = store.get_belief(sport, family)
            rest = loaded.get_belief(sport, family)
            assert rest.alpha == pytest.approx(orig.alpha, abs=1e-9)
            assert rest.beta == pytest.approx(orig.beta, abs=1e-9)
            assert rest.effective_obs == pytest.approx(orig.effective_obs, abs=1e-9)

    def test_round_trip_preserves_hyperparams(self) -> None:
        store = BeliefStore(half_life_days=365.0, prior_alpha=2.0, prior_beta=18.0,
                            min_obs_threshold=7.0)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.json"
            store.save(p)
            loaded = BeliefStore.load(p)
        assert loaded._half_life == pytest.approx(365.0, abs=1e-9)
        assert loaded._a0 == pytest.approx(2.0, abs=1e-9)
        assert loaded._b0 == pytest.approx(18.0, abs=1e-9)
        assert loaded._min_obs == pytest.approx(7.0, abs=1e-9)

    def test_load_absent_file_returns_fresh_store(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nonexistent.json"
            store = BeliefStore.load(p)
        assert len(store.all_beliefs()) == 0

    def test_to_dict_is_json_serialisable(self) -> None:
        store = BeliefStore()
        store.update_from_finding("mlb", "home_field", "REJECT", dated="2025-01-01")
        d = store.to_dict()
        # Must serialise without error
        s = json.dumps(d)
        assert "home_field" in s

    def test_atomic_write_does_not_leave_tmp(self) -> None:
        store = BeliefStore()
        store.update_from_finding("nba", "f", "SHIP", dated="2025-01-01")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "beliefs.json"
            store.save(p)
            tmp = p.with_suffix(".json.tmp")
            assert p.exists()
            assert not tmp.exists()


# ---------------------------------------------------------------------------
# 6. All-REJECT history → near-zero mean, sane upper CI
# ---------------------------------------------------------------------------

class TestAllRejectHistory:
    def test_posterior_mean_near_zero_after_many_rejects(self) -> None:
        """After 44 REJECTs (platform reality), posterior mean << 0.10."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        for i in range(44):
            store.update_from_finding("nba", f"fam_{i}", "REJECT",
                                      dated="2025-06-01")
        # Aggregate via sport pooling
        sa, sb = store._sport_agg("nba")
        pm = _beta_mean(sa, sb)
        assert pm < 0.10, f"Expected pm < 0.10 with 44 rejects, got {pm:.4f}"

    def test_single_family_all_reject_mean_near_zero(self) -> None:
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        for _ in range(20):
            store.update_from_finding("tennis", "null_family", "REJECT",
                                      dated="2025-06-01")
        b = store.get_belief("tennis", "null_family")
        assert b.posterior_mean < 0.10

    def test_upper_ci_bound_sane_after_rejects(self) -> None:
        """95% CI upper bound should be < 0.30 after 20 clean REJECTs."""
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        for _ in range(20):
            store.update_from_finding("soccer", "null_sig", "REJECT",
                                      dated="2025-06-01")
        _, hi = store.credible_interval("soccer", "null_sig", pool=False)
        assert hi < 0.30, f"Upper CI bound too wide after 20 REJECTs: {hi:.3f}"

    def test_math_consistency_alpha_beta(self) -> None:
        """Direct alpha/beta check: Beta(1, 1+20) mean = 1/22 ≈ 0.045."""
        store = BeliefStore(
            half_life_days=math.inf,
            prior_alpha=1.0, prior_beta=1.0,
            min_obs_threshold=0.0,
        )
        for _ in range(20):
            store.update_from_finding("mlb", "null", "REJECT", dated="2025-01-01")
        b = store.get_belief("mlb", "null")
        # alpha=1 (no SHIPs), beta=1+20=21
        assert b.alpha == pytest.approx(1.0, abs=1e-9)
        assert b.beta == pytest.approx(21.0, abs=1e-9)
        assert b.posterior_mean == pytest.approx(1.0 / 22.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 7. No edge-claim language in rendered output
# ---------------------------------------------------------------------------

class TestNoEdgeClaimLanguage:
    FORBIDDEN = [
        "betting edge",
        "edge detected",
        "positive ROI",
        "+EV",
        "profitable",
        "beat the market",
        "beat the line",
        "beat the close",
        "exploit",
    ]

    def test_render_table_no_edge_language(self) -> None:
        store = BeliefStore(half_life_days=math.inf, min_obs_threshold=0.0)
        store.update_from_finding("nba", "ast_edge", "SHIP", dated="2025-06-01")
        store.update_from_finding("nba", "reb_rej", "REJECT", dated="2025-06-01")
        table = store.render_table().lower()
        for phrase in self.FORBIDDEN:
            assert phrase.lower() not in table, (
                f"Edge-claim phrase found in render_table output: {phrase!r}"
            )

    def test_render_table_empty_store_no_edge_language(self) -> None:
        store = BeliefStore()
        out = store.render_table().lower()
        for phrase in self.FORBIDDEN:
            assert phrase.lower() not in out

    def test_json_output_no_edge_language(self) -> None:
        store = BeliefStore()
        store.update_from_finding("soccer", "xg", "SHIP", dated="2025-06-01")
        serialised = json.dumps(store.to_dict()).lower()
        for phrase in self.FORBIDDEN:
            assert phrase.lower() not in serialised


# ---------------------------------------------------------------------------
# 8. Bulk update via list of dicts
# ---------------------------------------------------------------------------

class TestBulkUpdate:
    def test_update_from_findings_list(self) -> None:
        findings = [
            _finding("nba", "pace", "REJECT", "2025-01-01"),
            _finding("nba", "pace", "REJECT", "2025-02-01"),
            _finding("nba", "pace", "SHIP",   "2025-03-01"),
        ]
        store = BeliefStore(half_life_days=math.inf)
        store.update_from_findings(findings)
        b = store.get_belief("nba", "pace")
        assert b.alpha == pytest.approx(_PRIOR_ALPHA + 1.0, abs=1e-9)
        assert b.beta == pytest.approx(_PRIOR_BETA + 2.0, abs=1e-9)

    def test_update_from_ledger(self) -> None:
        """BeliefStore.update_from_ledger() should read a real Ledger object."""
        from scripts.research_harness.research_ledger import Ledger, ResearchFinding

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "findings.jsonl"
            ledger = Ledger(path=p)
            ledger.append(ResearchFinding(
                sport="tennis", family="elo_diff",
                hypothesis="Elo gap predicts outcome",
                verdict="REJECT",
                evidence={"n": 1000},
                what_would_change_my_mind="Two independent corpora with +CLV",
                dated="2025-06-01",
            ))
            store = BeliefStore(half_life_days=math.inf)
            store.update_from_ledger(ledger)

        b = store.get_belief("tennis", "elo_diff")
        assert b.beta > _PRIOR_BETA


# ---------------------------------------------------------------------------
# 9. FamilyBelief helper
# ---------------------------------------------------------------------------

class TestFamilyBelief:
    def test_credible_interval_width_shrinks_with_more_data(self) -> None:
        few = FamilyBelief("nba", "f", alpha=1.5, beta=9.5, effective_obs=1.0)
        many = FamilyBelief("nba", "f", alpha=11.0, beta=99.0, effective_obs=100.0)
        lo_few, hi_few = few.credible_interval()
        lo_many, hi_many = many.credible_interval()
        width_few = hi_few - lo_few
        width_many = hi_many - lo_many
        assert width_many < width_few

    def test_posterior_mean_property(self) -> None:
        b = FamilyBelief("nba", "f", alpha=3.0, beta=7.0)
        assert b.posterior_mean == pytest.approx(0.30, abs=1e-9)

    def test_from_dict_round_trip(self) -> None:
        b = FamilyBelief("soccer", "xg", alpha=2.5, beta=12.5,
                         effective_obs=4.0, last_updated="2025-06-01")
        b2 = FamilyBelief.from_dict(b.to_dict())
        assert b2.alpha == pytest.approx(b.alpha, abs=1e-9)
        assert b2.beta == pytest.approx(b.beta, abs=1e-9)
        assert b2.effective_obs == pytest.approx(b.effective_obs, abs=1e-9)
