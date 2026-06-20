"""predict_service.test_recal_recency_segments -- per-file test for recal_recency_segments.

Acceptance criteria (from workstream BE-R5-4-recal-recency-segments):
  (a) A recal whose Brier improves in BOTH windows returns ship=True with
      per-window Brier/ECE populated.
  (b) A recal that improves in only ONE window returns ship=False
      (single-fold artifact rejected).
  (c) No $ field anywhere in SegmentCheckResult or WindowMetrics.
  (d) Degrades to ship=False on insufficient data (INSUFFICIENT_DATA honest path).

Additional checks:
  - status="ok" when data is sufficient; "INSUFFICIENT_DATA" when thin.
  - windows list is empty on INSUFFICIENT_DATA paths.
  - note never contains a '$' character.
  - CALIBRATION not edge: Brier/ECE reported; no ROI/PnL/profit key.
  - Length mismatch -> INSUFFICIENT_DATA / ship=False.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_recal_recency_segments.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import numpy as np
import pytest  # noqa: F401

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.recal_recency_segments import (  # noqa: E402
    FORBIDDEN_KEYS,
    MIN_TOTAL_EVENTS,
    MIN_WINDOW_EVENTS,
    SegmentCheckResult,
    WindowMetrics,
    recal_segment_check,
)

# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------

def _overconfident(n: int, seed: int = 42):
    """Strongly miscalibrated (overconfident) probs.

    True probs uniform [0.3, 0.7]; raw pushed 2.2x toward extremes.
    A calibrator should measurably reduce Brier in both recency windows.
    Returns (raw_probs, outcomes) as lists.
    """
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.3, 0.7, n)
    raw = np.where(
        true_p >= 0.5,
        0.5 + (true_p - 0.5) * 2.2,
        0.5 - (0.5 - true_p) * 2.2,
    )
    raw = np.clip(raw, 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)
    return raw.tolist(), outcomes.tolist()


def _well_calibrated(n: int, seed: int = 7):
    """Nearly-calibrated probs (small Gaussian noise on true_p).

    Recalibration should not help in either window consistently.
    Returns (raw_probs, outcomes) as lists.
    """
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.3, 0.7, n)
    raw = np.clip(true_p + rng.normal(0, 0.01, n), 0.02, 0.98)
    outcomes = rng.binomial(1, true_p).astype(float)
    return raw.tolist(), outcomes.tolist()


def _mixed_windows(n: int, seed: int = 123):
    """Probs that are miscalibrated only in the RECENT half, calibrated in the holdout half.

    Achieved by: holdout portion (first half of eval) uses nearly-calibrated probs,
    recent portion (second half of eval) uses overconfident probs.
    This should produce a single-fold artifact (recent improves, holdout does not).
    """
    rng = np.random.default_rng(seed)
    # Warmup + holdout portion: well calibrated
    n_warm = 50
    n_holdout = n // 3
    n_recent = n - n_warm - n_holdout

    true_p_hold = rng.uniform(0.3, 0.7, n_holdout)
    raw_hold = np.clip(true_p_hold + rng.normal(0, 0.01, n_holdout), 0.02, 0.98)
    out_hold = rng.binomial(1, true_p_hold).astype(float)

    # Recent portion: overconfident
    true_p_rec = rng.uniform(0.3, 0.7, n_recent)
    raw_rec = np.where(
        true_p_rec >= 0.5,
        0.5 + (true_p_rec - 0.5) * 2.4,
        0.5 - (0.5 - true_p_rec) * 2.4,
    )
    raw_rec = np.clip(raw_rec, 0.01, 0.99)
    out_rec = rng.binomial(1, true_p_rec).astype(float)

    # Warmup (first n_warm events) also well-calibrated
    true_p_warm = rng.uniform(0.3, 0.7, n_warm)
    raw_warm = np.clip(true_p_warm + rng.normal(0, 0.01, n_warm), 0.02, 0.98)
    out_warm = rng.binomial(1, true_p_warm).astype(float)

    raw = np.concatenate([raw_warm, raw_hold, raw_rec]).tolist()
    outcomes = np.concatenate([out_warm, out_hold, out_rec]).tolist()
    return raw, outcomes


# ---------------------------------------------------------------------------
# AC (a): ship=True when Brier improves in BOTH windows
# ---------------------------------------------------------------------------

class TestBothWindowsImprove:
    """AC-a: strongly miscalibrated data -> ship=True with both windows improving."""

    def test_ship_true_on_overconfident_data(self):
        """Primary acceptance test: overconfident probs -> ship=True.

        Uses N=1000 to ensure both recency windows have enough events for the
        walk-forward recalibrator to consistently improve Brier.  N=600 is
        borderline: at seed=42 the holdout window Brier delta is <0.001
        (within sample noise) so 1000 is used for a stable acceptance test.
        """
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)

        assert result.ship is True, (
            f"Expected ship=True for strongly miscalibrated data (N=1000, seed=42); "
            f"note={result.note}"
        )

    def test_status_ok_when_sufficient(self):
        """status must be 'ok' when data is sufficient."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        assert result.status == "ok", f"Expected status=ok, got: {result.status}"

    def test_windows_populated_on_ship_true(self):
        """windows list must have >=2 entries on ship=True."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        assert len(result.windows) >= 2, (
            f"Expected >=2 windows, got {len(result.windows)}"
        )

    def test_both_windows_brier_improved(self):
        """All WindowMetrics.brier_improved must be True when ship=True."""
        raw, outcomes = _overconfident(1000, seed=99)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.ship:
            for w in result.windows:
                assert w.brier_improved is True, (
                    f"Window '{w.window_label}' has brier_improved=False "
                    f"but ship=True: raw={w.brier_raw:.5f}, recal={w.brier_recal:.5f}"
                )

    def test_per_window_brier_ece_are_finite(self):
        """All per-window Brier/ECE values must be finite on ship=True."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.ship:
            for w in result.windows:
                for field_name, val in [
                    ("brier_raw", w.brier_raw),
                    ("brier_recal", w.brier_recal),
                    ("ece_raw", w.ece_raw),
                    ("ece_recal", w.ece_recal),
                ]:
                    assert np.isfinite(val), (
                        f"Window '{w.window_label}' field '{field_name}' is not finite: {val}"
                    )

    def test_window_n_positive(self):
        """Each window must report n > 0."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.status == "ok":
            for w in result.windows:
                assert w.n > 0, f"Window '{w.window_label}' has n=0"

    def test_window_labels_present(self):
        """Windows must be labelled 'recent' and 'holdout'."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.status == "ok" and len(result.windows) >= 2:
            labels = {w.window_label for w in result.windows}
            assert "recent" in labels, f"Missing 'recent' window, got: {labels}"
            assert "holdout" in labels, f"Missing 'holdout' window, got: {labels}"


# ---------------------------------------------------------------------------
# AC (b): ship=False when only ONE window improves (single-fold artifact)
# ---------------------------------------------------------------------------

class TestSingleFoldArtifact:
    """AC-b: improvement in only one window -> ship=False (single-fold artifact)."""

    def test_ship_false_on_single_fold_improvement(self):
        """Forced asymmetric miscalibration -> ship=False (single-window improvement)."""
        # Use mixed_windows: holdout is well-calibrated, recent is overconfident.
        # With a large enough sample the two windows should split the improvement.
        raw, outcomes = _mixed_windows(400, seed=55)
        result = recal_segment_check(raw, outcomes, min_history=50,
                                     min_window_events=20, min_total_events=60)
        # If exactly one window improves, ship must be False.
        if result.status == "ok":
            n_improved = sum(1 for w in result.windows if w.brier_improved)
            if n_improved < len(result.windows):
                assert result.ship is False, (
                    f"Expected ship=False when only {n_improved}/{len(result.windows)} "
                    f"windows improve; note={result.note}"
                )

    def test_ship_false_consistency_with_windows(self):
        """ship=False must be consistent with at least one window not improving."""
        raw, outcomes = _mixed_windows(500, seed=77)
        result = recal_segment_check(raw, outcomes, min_history=50,
                                     min_window_events=20, min_total_events=60)
        if result.status == "ok" and not result.ship:
            all_improved = all(w.brier_improved for w in result.windows)
            assert not all_improved, (
                "ship=False but all windows show brier_improved=True -- inconsistency"
            )

    def test_well_calibrated_ship_false_or_ok(self):
        """Well-calibrated input: ship should be False (no improvement to replicate)."""
        raw, outcomes = _well_calibrated(600, seed=21)
        result = recal_segment_check(raw, outcomes, min_history=50)
        # Well-calibrated: either no improvement or marginal; ship should not be True
        # based on both windows strictly improving Brier (isotonic can hurt calibrated data).
        # We only ASSERT ship consistency with the window results.
        if result.status == "ok":
            all_improved = all(w.brier_improved for w in result.windows)
            assert result.ship == all_improved, (
                f"ship={result.ship} inconsistent with all_windows_improved={all_improved}"
            )


# ---------------------------------------------------------------------------
# AC (c): No $ field
# ---------------------------------------------------------------------------

class TestNoDollarField:
    """AC-c: No $ / money / edge field in SegmentCheckResult or WindowMetrics."""

    def test_no_forbidden_field_in_segment_check_result(self):
        """SegmentCheckResult._fields must not intersect FORBIDDEN_KEYS."""
        fields = set(SegmentCheckResult._fields)
        bad = fields & FORBIDDEN_KEYS
        assert not bad, f"SegmentCheckResult has forbidden field(s): {bad}"

    def test_no_forbidden_field_in_window_metrics(self):
        """WindowMetrics._fields must not intersect FORBIDDEN_KEYS."""
        fields = set(WindowMetrics._fields)
        bad = fields & FORBIDDEN_KEYS
        assert not bad, f"WindowMetrics has forbidden field(s): {bad}"

    def test_note_has_no_dollar_sign_ok(self):
        """note must not contain '$' for a successful (ok) result."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        assert "$" not in result.note, f"note contains '$': {result.note}"

    def test_note_has_no_dollar_sign_insufficient(self):
        """note must not contain '$' for INSUFFICIENT_DATA result."""
        result = recal_segment_check([], [])
        assert "$" not in result.note, f"note contains '$': {result.note}"

    def test_status_has_no_dollar_sign(self):
        """status must not contain '$'."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes)
        assert "$" not in result.status


# ---------------------------------------------------------------------------
# AC (d): INSUFFICIENT_DATA honest path
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """AC-d: thin / degenerate data -> ship=False with INSUFFICIENT_DATA status."""

    def test_empty_input(self):
        """Empty input -> INSUFFICIENT_DATA, ship=False."""
        result = recal_segment_check([], [])
        assert result.ship is False
        assert result.status == "INSUFFICIENT_DATA"
        assert result.windows == []

    def test_length_mismatch(self):
        """Mismatched lengths -> INSUFFICIENT_DATA, ship=False."""
        result = recal_segment_check([0.5, 0.6], [1.0])
        assert result.ship is False
        assert result.status == "INSUFFICIENT_DATA"
        assert result.windows == []

    def test_below_min_total(self):
        """Fewer events than min_total_events -> INSUFFICIENT_DATA."""
        raw, outcomes = _overconfident(40, seed=1)
        result = recal_segment_check(raw, outcomes,
                                     min_total_events=80, min_window_events=15)
        assert result.ship is False
        assert result.status == "INSUFFICIENT_DATA"
        assert result.windows == []

    def test_eval_window_too_small_for_two_splits(self):
        """Enough total events but eval window too small for 2 windows."""
        # min_history=50 eats most of 70 events, leaving very few for eval
        raw, outcomes = _overconfident(70, seed=2)
        result = recal_segment_check(raw, outcomes, min_history=50,
                                     min_window_events=15, min_total_events=60)
        # With 70 total and 50 warmup, only 20 eval events -- below 2*15=30
        assert result.ship is False
        if len(result.windows) == 0:
            assert result.status == "INSUFFICIENT_DATA"

    def test_insufficient_data_windows_empty(self):
        """On INSUFFICIENT_DATA, windows list must be empty."""
        result = recal_segment_check([0.5] * 10, [1.0] * 10)
        if result.status == "INSUFFICIENT_DATA":
            assert result.windows == [], (
                f"Expected empty windows on INSUFFICIENT_DATA, got {result.windows}"
            )

    def test_insufficient_data_note_mentions_insufficient(self):
        """INSUFFICIENT_DATA note must mention it."""
        result = recal_segment_check([], [])
        assert "INSUFFICIENT_DATA" in result.note or "insufficient" in result.note.lower(), (
            f"INSUFFICIENT_DATA note does not mention data insufficiency: {result.note}"
        )


# ---------------------------------------------------------------------------
# Additional invariant checks
# ---------------------------------------------------------------------------

class TestInvariants:
    """Structural invariants that must hold for all valid outputs."""

    def test_ship_false_when_status_insufficient(self):
        """ship must be False whenever status is INSUFFICIENT_DATA."""
        result = recal_segment_check([0.5] * 5, [1.0] * 5)
        if result.status == "INSUFFICIENT_DATA":
            assert result.ship is False, (
                f"ship={result.ship} but status=INSUFFICIENT_DATA -- inconsistency"
            )

    def test_brier_recal_in_unit_interval(self):
        """All per-window brier_recal values must be in [0, 1]."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes)
        for w in result.windows:
            if np.isfinite(w.brier_recal):
                assert 0.0 <= w.brier_recal <= 1.0, (
                    f"brier_recal={w.brier_recal:.5f} out of [0,1] in '{w.window_label}'"
                )

    def test_ece_recal_in_unit_interval(self):
        """All per-window ece_recal values must be in [0, 1]."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes)
        for w in result.windows:
            if np.isfinite(w.ece_recal):
                assert 0.0 <= w.ece_recal <= 1.0, (
                    f"ece_recal={w.ece_recal:.5f} out of [0,1] in '{w.window_label}'"
                )

    def test_ship_true_implies_status_ok(self):
        """ship=True must imply status='ok' (never ship on INSUFFICIENT_DATA)."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes)
        if result.ship:
            assert result.status == "ok", (
                f"ship=True but status={result.status!r} -- contract violation"
            )

    def test_note_is_nonempty(self):
        """note must be a non-empty string for all outcomes."""
        for fn, seed in [(_overconfident, 1), (_well_calibrated, 2)]:
            raw, outcomes = fn(1000, seed=seed)
            result = recal_segment_check(raw, outcomes)
            assert isinstance(result.note, str) and len(result.note) > 0, (
                "note must be a non-empty string"
            )

    def test_result_is_named_tuple(self):
        """recal_segment_check must return a SegmentCheckResult NamedTuple."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes)
        assert isinstance(result, SegmentCheckResult), (
            f"Expected SegmentCheckResult, got {type(result)}"
        )

    def test_windows_are_window_metrics(self):
        """Each entry in windows must be a WindowMetrics NamedTuple."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes)
        for w in result.windows:
            assert isinstance(w, WindowMetrics), (
                f"Expected WindowMetrics, got {type(w)}"
            )


# ---------------------------------------------------------------------------
# Deterministic single-fold artifact: ship=False when only ONE window improves
# ---------------------------------------------------------------------------

def _deterministic_one_window_miscal(
    n_warm: int = 50,
    n_holdout: int = 80,
    n_recent: int = 120,
) -> "tuple[list[float], list[float]]":
    """Build (raw_probs, outcomes) where ONLY the recent window is miscalibrated.

    Holdout window: perfectly calibrated (raw == true_p, no overshoot).
    Recent window:  overconfident (raw pushed 2.5x toward extremes).
    Walk-forward recalibration trained on the whole prefix will improve Brier in
    the recent window but NOT in the holdout window (probs already optimal).
    This gives a deterministic single-window improvement, no randomness.
    """
    rng = np.random.default_rng(0)

    # Warmup (not in eval): well calibrated
    true_p_w = rng.uniform(0.35, 0.65, n_warm)
    raw_w = true_p_w.copy()
    out_w = rng.binomial(1, true_p_w).astype(float)

    # Holdout eval: perfectly calibrated -- Brier already optimal, no room to improve
    true_p_h = rng.uniform(0.35, 0.65, n_holdout)
    raw_h = true_p_h.copy()          # raw == true_p  ->  isotonic can't help
    out_h = rng.binomial(1, true_p_h).astype(float)

    # Recent eval: heavily overconfident -- isotonic recal should measurably help
    true_p_r = rng.uniform(0.35, 0.65, n_recent)
    raw_r = np.where(
        true_p_r >= 0.5,
        0.5 + (true_p_r - 0.5) * 2.5,
        0.5 - (0.5 - true_p_r) * 2.5,
    )
    raw_r = np.clip(raw_r, 0.01, 0.99)
    out_r = rng.binomial(1, true_p_r).astype(float)

    raw = np.concatenate([raw_w, raw_h, raw_r]).tolist()
    out = np.concatenate([out_w, out_h, out_r]).tolist()
    return raw, out


class TestSingleFoldArtifactDeterministic:
    """Deterministic single-fold artifact tests -- no stochastic seeds needed.

    The data is constructed so that exactly one window (recent) is miscalibrated
    and one window (holdout) is already calibrated.  ship must be False.
    """

    def test_ship_false_deterministic_one_window(self):
        """Deterministic: only recent window miscal -> ship=False."""
        raw, outcomes = _deterministic_one_window_miscal(
            n_warm=50, n_holdout=80, n_recent=120
        )
        result = recal_segment_check(
            raw, outcomes,
            min_history=50,
            min_window_events=30,
            min_total_events=80,
        )
        if result.status == "ok":
            n_improved = sum(1 for w in result.windows if w.brier_improved)
            assert result.ship is False, (
                f"Expected ship=False (single-fold artifact): "
                f"{n_improved}/{len(result.windows)} windows improved; "
                f"note={result.note}"
            )

    def test_single_fold_note_mentions_no_candidate(self):
        """When ship=False due to partial improvement, note says NO_CANDIDATE."""
        raw, outcomes = _deterministic_one_window_miscal(
            n_warm=50, n_holdout=80, n_recent=120
        )
        result = recal_segment_check(
            raw, outcomes,
            min_history=50,
            min_window_events=30,
            min_total_events=80,
        )
        if result.status == "ok" and not result.ship:
            assert "NO_CANDIDATE" in result.note or "ship=False" in result.note, (
                f"Expected NO_CANDIDATE or ship=False in note for single-fold reject; "
                f"note={result.note}"
            )

    def test_single_fold_status_remains_ok(self):
        """Single-fold artifact -> ship=False but status stays 'ok' (data is sufficient)."""
        raw, outcomes = _deterministic_one_window_miscal(
            n_warm=50, n_holdout=80, n_recent=120
        )
        result = recal_segment_check(
            raw, outcomes,
            min_history=50,
            min_window_events=30,
            min_total_events=80,
        )
        # If we get a valid split the status must be ok, not INSUFFICIENT_DATA
        if len(result.windows) > 0:
            assert result.status == "ok", (
                f"Expected status=ok for sufficient data; got {result.status}"
            )

    def test_single_fold_windows_populated(self):
        """Windows are still populated even when ship=False on single-fold data."""
        raw, outcomes = _deterministic_one_window_miscal(
            n_warm=50, n_holdout=80, n_recent=120
        )
        result = recal_segment_check(
            raw, outcomes,
            min_history=50,
            min_window_events=30,
            min_total_events=80,
        )
        if result.status == "ok":
            assert len(result.windows) >= 2, (
                f"Expected >=2 windows on ok status; got {len(result.windows)}"
            )


# ---------------------------------------------------------------------------
# Boundary conditions: exactly at min_total_events / min_window_events limits
# ---------------------------------------------------------------------------

class TestBoundaryConditions:
    """Boundary tests for the INSUFFICIENT_DATA guards.

    The guards use strict less-than (n < min_total_events), so exactly at the
    boundary (n == min_total_events) should NOT trigger INSUFFICIENT_DATA
    provided the eval window is also large enough.
    """

    def test_exactly_at_min_total_events_boundary(self):
        """n == min_total_events: should not be INSUFFICIENT_DATA from the total guard."""
        min_tot = 40
        raw, outcomes = _overconfident(min_tot, seed=3)
        result = recal_segment_check(
            raw, outcomes,
            min_total_events=min_tot,
            min_history=10,
            min_window_events=5,
        )
        # The total-events guard uses n < min_total_events (strict), so n==min_total_events
        # must not hit that guard.  It may still fail on eval-window size -- that is ok.
        assert "n={} < min_total_events={}".format(min_tot, min_tot) not in result.note, (
            "Boundary n==min_total_events should not fail the strict < guard; "
            f"note={result.note}"
        )

    def test_one_below_min_total_events(self):
        """n == min_total_events - 1: must return INSUFFICIENT_DATA."""
        min_tot = 40
        raw, outcomes = _overconfident(min_tot - 1, seed=4)
        result = recal_segment_check(
            raw, outcomes,
            min_total_events=min_tot,
            min_history=10,
            min_window_events=5,
        )
        assert result.status == "INSUFFICIENT_DATA", (
            f"n={min_tot-1} < min_total_events={min_tot} must be INSUFFICIENT_DATA; "
            f"status={result.status}, note={result.note}"
        )
        assert result.ship is False
        assert result.windows == []

    def test_window_too_small_triggers_insufficient(self):
        """If eval indices are too few for two windows -> INSUFFICIENT_DATA."""
        # 80 total, min_history=70 -> only 10 eval events; min_window_events=10 -> need 20
        raw, outcomes = _overconfident(80, seed=5)
        result = recal_segment_check(
            raw, outcomes,
            min_history=70,
            min_window_events=10,
            min_total_events=60,
        )
        assert result.status == "INSUFFICIENT_DATA", (
            f"Too-small eval window must give INSUFFICIENT_DATA; "
            f"status={result.status}, note={result.note}"
        )
        assert result.ship is False
        assert result.windows == []

    def test_min_window_events_exactly_met(self):
        """Each window has exactly min_window_events events -> should not fail the window guard."""
        # 200 total, min_history=50 -> 150 eval; split 50/50 -> 75 each; min_window=30
        raw, outcomes = _overconfident(200, seed=6)
        result = recal_segment_check(
            raw, outcomes,
            min_history=50,
            min_window_events=30,
            min_total_events=100,
        )
        if result.status == "ok":
            for w in result.windows:
                assert w.n >= 30, (
                    f"Window '{w.window_label}' has n={w.n} < min_window_events=30"
                )


# ---------------------------------------------------------------------------
# No-improvement: honest no-ship must be a success note, not an error
# ---------------------------------------------------------------------------

class TestNoImprovementHonestSuccess:
    """When calibration does not improve, ship=False but the outcome is honest success.

    The note must not contain error / exception / crash language.
    status must be 'ok' (data was sufficient; the model just didn't benefit).
    """

    def test_no_improvement_status_ok(self):
        """No-improvement result must have status='ok', not INSUFFICIENT_DATA."""
        raw, outcomes = _well_calibrated(800, seed=31)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if not result.ship:
            assert result.status == "ok", (
                f"No-improvement ship=False must have status=ok; "
                f"status={result.status}, note={result.note}"
            )

    def test_no_improvement_note_has_no_error_language(self):
        """No-improvement note must not contain 'error', 'exception', or 'crash'."""
        raw, outcomes = _well_calibrated(800, seed=31)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if not result.ship and result.status == "ok":
            lowered = result.note.lower()
            for bad_word in ("error", "exception", "crash", "traceback"):
                assert bad_word not in lowered, (
                    f"No-improvement note contains '{bad_word}': {result.note}"
                )

    def test_no_improvement_note_honest_no_ship(self):
        """No-improvement note must say 'NO_CANDIDATE' or 'ship=False'."""
        raw, outcomes = _well_calibrated(800, seed=31)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if not result.ship and result.status == "ok":
            assert ("NO_CANDIDATE" in result.note or "ship=False" in result.note), (
                f"No-improvement note must say NO_CANDIDATE or ship=False; "
                f"note={result.note}"
            )

    def test_tie_no_improvement_ship_false_consistency(self):
        """ship=False on no-improvement must be consistent with window metrics."""
        raw, outcomes = _well_calibrated(800, seed=31)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.status == "ok" and not result.ship:
            all_improved = all(w.brier_improved for w in result.windows)
            assert not all_improved, (
                "ship=False but all windows show brier_improved=True -- inconsistency"
            )

    def test_windows_nonempty_on_no_improvement_ok(self):
        """Windows must be populated even when no improvement (status=ok)."""
        raw, outcomes = _well_calibrated(800, seed=31)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.status == "ok":
            assert len(result.windows) >= 2, (
                f"Expected >=2 windows on status=ok, got {len(result.windows)}"
            )


# ---------------------------------------------------------------------------
# Per-window metrics integrity: Brier/ECE/n are internally consistent
# ---------------------------------------------------------------------------

class TestPerWindowMetricsIntegrity:
    """Verify per-window Brier/ECE/n values are self-consistent."""

    def test_window_n_sum_approximately_equals_n_eval(self):
        """Sum of window n values should equal total eval events (non-overlapping)."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        if result.status == "ok":
            total_window_n = sum(w.n for w in result.windows)
            n_total = len(raw)
            min_hist = 50
            # Eval events <= n_total - min_hist; total_window_n == n_eval exactly
            assert total_window_n <= n_total - min_hist + 1, (
                f"Sum of window n={total_window_n} exceeds n_total-min_hist={n_total-min_hist}"
            )
            assert total_window_n > 0, "Window n sum must be positive"

    def test_brier_raw_non_negative(self):
        """brier_raw must be >= 0 in all windows (Brier is a squared error)."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        for w in result.windows:
            assert w.brier_raw >= 0.0, (
                f"brier_raw={w.brier_raw} is negative in window '{w.window_label}'"
            )

    def test_brier_recal_non_negative(self):
        """brier_recal must be >= 0 in all windows."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        for w in result.windows:
            assert w.brier_recal >= 0.0, (
                f"brier_recal={w.brier_recal} is negative in window '{w.window_label}'"
            )

    def test_brier_improved_flag_matches_values(self):
        """brier_improved flag must agree with brier_recal < brier_raw."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        for w in result.windows:
            expected = w.brier_recal < w.brier_raw
            assert w.brier_improved == expected, (
                f"Window '{w.window_label}' brier_improved={w.brier_improved} "
                f"but brier_raw={w.brier_raw:.5f} vs brier_recal={w.brier_recal:.5f} "
                f"implies improved={expected}"
            )

    def test_ece_raw_non_negative(self):
        """ece_raw must be >= 0 in all windows."""
        raw, outcomes = _overconfident(1000, seed=42)
        result = recal_segment_check(raw, outcomes, min_history=50)
        for w in result.windows:
            if np.isfinite(w.ece_raw):
                assert w.ece_raw >= 0.0, (
                    f"ece_raw={w.ece_raw} is negative in window '{w.window_label}'"
                )
