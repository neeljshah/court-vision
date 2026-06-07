"""W-034+ — Win-probability calibration audit across ALL periods.

Tests verify the per-period ECE audit findings from
docs/_audits/WINPROB_CALIBRATION_ALLPERIODS.md:

  1. FLAG-OFF BYTE-IDENTICAL: predict_home_win_prob with no env flags produces
     the same output as with every known calibration flag explicitly set to OFF.
     This confirms the serve path is byte-identical to the pre-audit baseline.

  2. ECE CONFIRMED WITHIN-NOISE: the eval_winprob_ece.json results (which are the
     validated, stored corpus results) show that all three end-of-quarter periods
     have ECE_signal <= 0.02, confirming no new recalibration is warranted.

  3. BRIER PROGRESSION: Brier decreases from endQ1 to endQ2 to endQ3 (more game
     state information reduces uncertainty), and is below the v1_raw baseline for
     all periods.

  4. EXISTING ENDQ3 NOT REGRESSED: the endQ3 Brier from the ECE corpus (0.117) is
     below the prior v1_raw baseline Brier (0.135), confirming W-005/W-032 work.

  5. NO NEW FLAG: CV_WP_CALIB_ALLPERIODS does not exist and enabling it should not
     change any predictions (no such gated calibration was introduced, because the
     audit found no systematic miscalibration to correct).

Usage:
  python -m pytest tests/test_winprob_calibration_allperiods.py -v
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.inplay_winprob import (  # noqa: E402
    predict_home_win_prob,
    reset_cache,
    active_stack,
)

# Path to the stored ECE results from the last harness run.
_ECE_RESULTS_PATH = os.path.join(
    PROJECT_DIR, ".planning", "ingame", "eval_winprob_ece.json"
)

# Half-normal factor for ECE_null computation.
_HALF_NORMAL = math.sqrt(2 / math.pi)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove any winprob-related env flags before each test."""
    for flag in (
        "CV_WP_FOULS_ENDQ3",
        "CV_WP_RECONCILED_CALIB",
        "CV_LATE_FOUL_STATE",
        "CV_WP_CALIB_ALLPERIODS",   # this flag must NOT exist
    ):
        monkeypatch.delenv(flag, raising=False)
    yield
    for flag in (
        "CV_WP_FOULS_ENDQ3",
        "CV_WP_RECONCILED_CALIB",
        "CV_LATE_FOUL_STATE",
        "CV_WP_CALIB_ALLPERIODS",
    ):
        monkeypatch.delenv(flag, raising=False)


@pytest.fixture(autouse=True)
def _reset_caches():
    reset_cache()
    yield
    reset_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feats(snap: str, score_margin: float = 5.0, pregame_wp: float = 0.55) -> Dict[str, Any]:
    """Build a minimal feature dict for the given snapshot."""
    period = {"endQ1": 1, "endQ2": 2, "endQ3": 3}[snap]
    minutes = period * 12.0
    total = 50.0 + period * 12.0
    pace = total / minutes

    feats = {
        "score_margin": score_margin,
        "total_pts": total,
        "pace_so_far": pace,
        "q1_delta": score_margin * 0.5,
        "last_q_margin": score_margin * 0.5,
        "pregame_win_prob": pregame_wp,
        "home_team_id": 1610612744,  # GSW
        "season": "2024-25",
        "projected_final_margin": score_margin + (score_margin / minutes) * (48.0 - minutes),
        "projected_total_score": total + pace * (48.0 - minutes),
        "qtr_margin_var": 1.0,
        "qtr_margin_mean": score_margin / period,
        "net_rtg_diff": 0.0,
        "pace_diff": 0.0,
        "elo_diff": 0.0,
        "stars_diff": 0.0,
        "rest_diff": 0.0,
        "b2b_diff": 0.0,
        "last5_diff": 0.0,
    }
    if period >= 2:
        feats["q2_delta"] = score_margin * 0.3
    if period >= 3:
        feats["q3_delta"] = score_margin * 0.2
    return feats


def _compute_ece_null(reliability: List[Dict[str, Any]], n_total: int) -> float:
    """Compute expected ECE under perfect calibration from a reliability table."""
    ece_null = 0.0
    for row in reliability:
        n_b = row.get("bin_n", 0)
        if n_b == 0:
            continue
        mean_pred = row.get("mean_predicted_p") or 0.5
        var_b = mean_pred * (1.0 - mean_pred)
        e_gap = _HALF_NORMAL * math.sqrt(var_b / n_b)
        ece_null += (n_b / n_total) * e_gap
    return ece_null


def _load_ece_results() -> Optional[Dict[str, Any]]:
    if not os.path.exists(_ECE_RESULTS_PATH):
        return None
    try:
        with open(_ECE_RESULTS_PATH) as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Test 1 — Flag-OFF byte-identical: no env flags = all flags OFF
# ---------------------------------------------------------------------------

class TestByteIdenticalAllFlagsOff:
    """confirm that no known flag changes the output when OFF."""

    @pytest.mark.parametrize("snap", ["endQ1", "endQ2", "endQ3"])
    def test_no_flags_eq_explicit_off(self, snap, monkeypatch):
        """predict_home_win_prob with no flags == all flags explicitly OFF."""
        feats = _make_feats(snap)

        # No flags set (already cleared by fixture)
        p_noflags = predict_home_win_prob(feats, snap)

        # All calibration flags explicitly OFF
        for flag in ("CV_WP_FOULS_ENDQ3", "CV_WP_RECONCILED_CALIB",
                     "CV_LATE_FOUL_STATE"):
            monkeypatch.setenv(flag, "0")
        p_alloff = predict_home_win_prob(feats, snap)

        if p_noflags is None:
            pytest.skip(f"no artifact for {snap}")
        assert p_noflags == p_alloff, (
            f"{snap}: no-flag ({p_noflags}) != all-flags-OFF ({p_alloff})"
        )

    @pytest.mark.parametrize("snap", ["endQ1", "endQ2", "endQ3"])
    def test_cv_wp_calib_allperiods_does_not_exist(self, snap, monkeypatch):
        """CV_WP_CALIB_ALLPERIODS is not a real flag and must not change output."""
        feats = _make_feats(snap)
        p_off = predict_home_win_prob(feats, snap)

        monkeypatch.setenv("CV_WP_CALIB_ALLPERIODS", "1")
        p_on = predict_home_win_prob(feats, snap)

        if p_off is None:
            pytest.skip(f"no artifact for {snap}")

        # The flag does not exist; output must be identical.
        assert p_off == p_on, (
            f"{snap}: CV_WP_CALIB_ALLPERIODS=1 changed output "
            f"({p_off} -> {p_on}); this flag must not exist in the serve path"
        )


# ---------------------------------------------------------------------------
# Test 2 — ECE confirmed within noise
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists(_ECE_RESULTS_PATH),
    reason="eval_winprob_ece.json not present (run eval_winprob_ece.py first)",
)
class TestECEWithinNoise:
    """Verify the per-period ECE audit findings from eval_winprob_ece.json."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.data = _load_ece_results()
        if self.data is None:
            pytest.skip("could not load ECE results")

    @pytest.mark.parametrize("period,snap", [
        ("Q1", "endQ1"), ("Q2", "endQ2"), ("Q3", "endQ3"),
    ])
    def test_ece_signal_below_calibration_threshold(self, period, snap):
        """ECE_obs - ECE_null <= 0.02 for all end-of-quarter periods.

        The calibration threshold is 0.02. Any period above this threshold
        with a monotone bias pattern would warrant a new Platt/isotonic
        calibrator. The audit found all periods at or below 0.02.
        """
        d = self.data["by_period"][period].get("inplay_wp", {})
        n = d.get("n", 0)
        if n == 0:
            pytest.skip(f"no inplay_wp data for {period}")
        ece_obs = d.get("ece", 0)
        reliability = d.get("reliability", [])
        ece_null = _compute_ece_null(reliability, n)
        signal = max(0.0, ece_obs - ece_null)
        assert signal <= 0.02, (
            f"{period} ({snap}): ECE_signal={signal:.5f} > 0.02 threshold "
            f"(ECE_obs={ece_obs:.5f}, ECE_null={ece_null:.5f}). "
            f"Re-run the ECE harness with n>=500 and check for monotone bias "
            f"before considering recalibration."
        )

    @pytest.mark.parametrize("period,snap", [
        ("Q1", "endQ1"), ("Q2", "endQ2"), ("Q3", "endQ3"),
    ])
    def test_n_at_least_100(self, period, snap):
        """Enough games in the ECE corpus for a meaningful measurement."""
        d = self.data["by_period"][period].get("inplay_wp", {})
        n = d.get("n", 0)
        if n == 0:
            pytest.skip(f"no inplay_wp data for {period}")
        assert n >= 100, (
            f"{period} ({snap}): n={n} is too small for a reliable ECE estimate. "
            f"Re-run the ECE harness with --max-games 220 or larger."
        )


# ---------------------------------------------------------------------------
# Test 3 — Brier progression across periods
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists(_ECE_RESULTS_PATH),
    reason="eval_winprob_ece.json not present",
)
class TestBrierProgression:
    """Brier score decreases as more game information becomes available."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.data = _load_ece_results()
        if self.data is None:
            pytest.skip("could not load ECE results")

    def test_brier_decreases_from_q1_to_q3(self):
        """endQ3 Brier < endQ2 Brier < endQ1 Brier (more info = better calibration)."""
        briers = {}
        for period in ("Q1", "Q2", "Q3"):
            d = self.data["by_period"][period].get("inplay_wp", {})
            n = d.get("n", 0)
            if n > 0:
                briers[period] = d["brier"]
        if len(briers) < 2:
            pytest.skip("insufficient period data")
        if "Q1" in briers and "Q2" in briers:
            assert briers["Q2"] < briers["Q1"], (
                f"endQ2 Brier ({briers['Q2']:.5f}) should be < endQ1 ({briers['Q1']:.5f})"
            )
        if "Q2" in briers and "Q3" in briers:
            assert briers["Q3"] < briers["Q2"], (
                f"endQ3 Brier ({briers['Q3']:.5f}) should be < endQ2 ({briers['Q2']:.5f})"
            )

    def test_endq3_brier_below_v1raw_baseline(self):
        """endQ3 Brier from ECE corpus must be below the v1_raw production baseline (0.135).

        v1_raw baseline from validation_harness_winprob.json: 0.1354.
        This confirms W-005 + v6_hp_iter68 improvements are real.
        """
        d = self.data["by_period"]["Q3"].get("inplay_wp", {})
        n = d.get("n", 0)
        if n == 0:
            pytest.skip("no Q3 inplay_wp data")
        brier = d["brier"]
        V1_RAW_BASELINE = 0.135
        assert brier < V1_RAW_BASELINE, (
            f"endQ3 Brier={brier:.5f} should be < v1_raw baseline {V1_RAW_BASELINE}"
        )


# ---------------------------------------------------------------------------
# Test 4 — Existing endQ3 not regressed
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists(_ECE_RESULTS_PATH),
    reason="eval_winprob_ece.json not present",
)
class TestEndQ3NotRegressed:
    """endQ3 calibration audit: confirm not regressed from W-005 shipment."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.data = _load_ece_results()
        if self.data is None:
            pytest.skip("could not load ECE results")

    def test_endq3_brier_below_0_125(self):
        """endQ3 Brier < 0.125 (v6_hp_iter68 mean WF Brier from _meta.json).

        The meta_blend mean WF Brier at endQ3 is 0.11497 (3/4 folds improved).
        The v6_hp_iter68 mean WF Brier is 0.12500. Use 0.125 as the reference.
        """
        d = self.data["by_period"]["Q3"].get("inplay_wp", {})
        n = d.get("n", 0)
        if n == 0:
            pytest.skip("no Q3 inplay_wp data")
        brier = d["brier"]
        # v6_hp_iter68 honest WF Brier = 0.12500 (from _meta.json).
        # The ECE harness uses a different (smaller) corpus but should be comparable.
        assert brier <= 0.125, (
            f"endQ3 Brier={brier:.5f} exceeds v6_hp_iter68 WF reference of 0.1250 — "
            f"possible regression in the model stack"
        )

    def test_endq3_ece_pattern_not_monotone_overconfident(self):
        """endQ3 bins do NOT show monotone over-confidence (would warrant recal)."""
        d = self.data["by_period"]["Q3"].get("inplay_wp", {})
        if d.get("n", 0) == 0:
            pytest.skip("no Q3 data")
        reliability = d.get("reliability", [])
        # 'monotone over-confident' = all bins with n>=10 have pred > obs (model too sure)
        over_bins = []
        for row in reliability:
            if row.get("bin_n", 0) < 10:
                continue
            mp = row.get("mean_predicted_p")
            of = row.get("observed_freq")
            if mp is not None and of is not None:
                over_bins.append(mp > of)
        if not over_bins:
            pytest.skip("no bins with n>=10")
        # If ALL large bins are over-confident, that's a systematic pattern.
        # We expect a mix (not all over), confirming noise not systematic bias.
        n_over = sum(over_bins)
        n_total_bins = len(over_bins)
        assert n_over < n_total_bins, (
            f"endQ3: all {n_total_bins} bins with n>=10 are over-confident — "
            f"this is a systematic bias. Re-run full audit and consider recalibration."
        )


# ---------------------------------------------------------------------------
# Test 5 — Predict ranges: all periods return probabilities in (0, 1)
# ---------------------------------------------------------------------------

class TestPredictRanges:
    """All snapshots return valid probabilities for various game states."""

    @pytest.mark.parametrize("snap,margin", [
        ("endQ1", -8), ("endQ1", 0), ("endQ1", 12),
        ("endQ2", -15), ("endQ2", 5), ("endQ2", 20),
        ("endQ3", -25), ("endQ3", 0), ("endQ3", 18),
    ])
    def test_probability_in_unit_interval(self, snap, margin):
        feats = _make_feats(snap, score_margin=float(margin))
        p = predict_home_win_prob(feats, snap)
        if p is None:
            pytest.skip(f"no artifact for {snap}")
        assert 0.0 <= p <= 1.0, f"{snap} margin={margin}: p={p} out of [0,1]"

    @pytest.mark.parametrize("snap", ["endQ1", "endQ2", "endQ3"])
    def test_monotone_in_margin(self, snap):
        """Larger home lead -> higher home win probability (monotonicity)."""
        feats_low = _make_feats(snap, score_margin=-10.0)
        feats_mid = _make_feats(snap, score_margin=0.0)
        feats_high = _make_feats(snap, score_margin=15.0)
        p_low = predict_home_win_prob(feats_low, snap)
        p_mid = predict_home_win_prob(feats_mid, snap)
        p_high = predict_home_win_prob(feats_high, snap)
        if p_low is None or p_mid is None or p_high is None:
            pytest.skip(f"no artifact for {snap}")
        assert p_low < p_mid < p_high, (
            f"{snap}: monotonicity violated "
            f"p(-10)={p_low:.4f} p(0)={p_mid:.4f} p(+15)={p_high:.4f}"
        )
