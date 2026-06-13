"""tests/platform/test_gate_determinism.py — Gate-verdict determinism property.

Renaissance-grade reproducibility requirement: evaluate(signal, device='cpu') must
produce IDENTICAL verdict AND numeric metrics across independent invocations on the
same fixed input — i.e. the gate is a pure function of its input bundle.

Why this matters: gate trains XGBoost per criterion; thread-level non-determinism
could silently produce different verdicts on different runs — invalidating catalog
reproducibility.  This test pins the guarantee.

Design: builds ONE minimal synthetic FeatureBundle from numpy (no corpus, no disk).
300 rows × 5 features (> _MIN_FOLD_ROWS=60); uses AbsRestDiffSignal (tennis) as
vehicle via _gate_matrix injection; calls evaluate() TWICE, device='cpu', n_splits=3.

Non-determinism finding
-----------------------
If any assertion fails this indicates a REAL reproducibility bug in the gate.
The test deliberately does NOT hide it — the assertion message reports the observed
variation in detail so Opus can investigate.

Run: python -m pytest tests/platform/test_gate_determinism.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Synthetic corpus size — must exceed gate's _MIN_FOLD_ROWS=60 for all folds
# AND leave enough for the ablation 25% holdout (>=20 rows), so 300 is safe.
_N_ROWS = 300
_N_FEATURES = 5   # matches tennis base (elo_diff, surf_diff, best_of, rest_a, rest_b)

# n_splits=3 mirrors catalog_common.run_catalog_common default; keeps runtime low.
_N_SPLITS = 3

# Reproducible numpy seed for synthetic data generation (NOT gate seed — fixed
# separately by XGB random_state=42 and numpy.default_rng(42) inside gate.py).
_DATA_SEED = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_synthetic_bundle() -> Any:
    """Build a minimal deterministic FeatureBundle without touching the corpus.

    Returns a FeatureBundle with:
        base       — 300×5 float64 (standardised random features)
        signal_col — 300-vector: abs(rest_a - rest_b) derived from base[:,3:5]
        target     — binary {0,1} win label (correlated weakly with elo_diff)
        dates      — ISO date strings 2015-01-01 … (one per row, ascending)
        lines, closing — None  (CLV check will be non-blocking)
    """
    from src.loop.gate import FeatureBundle

    rng = np.random.default_rng(_DATA_SEED)

    # Five base columns matching tennis adapter columns 0-4
    elo_diff  = rng.normal(0.0, 200.0, _N_ROWS)
    surf_diff = rng.normal(0.0, 150.0, _N_ROWS)
    best_of   = rng.choice([3.0, 5.0], _N_ROWS)
    rest_a    = rng.uniform(0.0, 20.0, _N_ROWS)
    rest_b    = rng.uniform(0.0, 20.0, _N_ROWS)

    base = np.column_stack([elo_diff, surf_diff, best_of, rest_a, rest_b]).astype(float)

    # Signal column: abs(rest_a - rest_b) — same as AbsRestDiffSignal
    signal_col = np.abs(rest_a - rest_b)

    # Binary target weakly correlated with elo_diff so gate sees a non-trivial problem
    logit = 0.003 * elo_diff + rng.normal(0, 1.0, _N_ROWS)
    target = (logit > 0.0).astype(float)

    # Ascending ISO dates: 2015-01-01 + i days
    base_date = dt.date(2015, 1, 1)
    dates = [(base_date + dt.timedelta(days=i)).isoformat() for i in range(_N_ROWS)]

    return FeatureBundle(
        base=base,
        signal_col=signal_col,
        target=target,
        dates=dates,
        lines=None,
        closing=None,
    )


def _build_signal_with_bundle(bundle: Any) -> Any:
    """Construct an AbsRestDiffSignal with the injected bundle attached."""
    from domains.tennis.signal_catalog import AbsRestDiffSignal
    sig = AbsRestDiffSignal()
    sig._gate_matrix = bundle  # type: ignore[attr-defined]
    return sig


def _call_gate(signal: Any) -> Any:
    """Call the real evaluate() with fixed cpu device and small n_splits."""
    from src.loop.gate import evaluate
    return evaluate(signal, device="cpu", n_splits=_N_SPLITS)


def _gate_result_key_fields(r: Any) -> dict:
    """Extract the fields we assert on for determinism."""
    return {
        "verdict": r.verdict,
        "wf_all_improve": r.wf_all_improve,
        "null_pass": r.null_pass,
        "ablation_pass": r.ablation_pass,
        "calibration_ok": r.calibration_ok,
        "clv_pass": r.clv_pass,
        "fdr_pass": r.fdr_pass,
    }


def _gate_result_numeric_fields(r: Any) -> dict:
    """Extract the numeric fields we assert are close (within float tolerance)."""
    fields: dict = {}
    # wf_folds is a list of floats
    if r.wf_folds:
        for i, v in enumerate(r.wf_folds):
            fields[f"wf_fold_{i}"] = v
    if r.ablation_delta is not None:
        fields["ablation_delta"] = r.ablation_delta
    if r.null_delta is not None:
        fields["null_delta"] = r.null_delta
    if r.p_value is not None:
        fields["p_value"] = r.p_value
    if r.clv is not None:
        fields["clv"] = r.clv
    return fields


# ---------------------------------------------------------------------------
# Skip guard — import check
# ---------------------------------------------------------------------------

def _imports_available() -> bool:
    try:
        from src.loop.gate import evaluate, FeatureBundle  # noqa: F401
        from domains.tennis.signal_catalog import AbsRestDiffSignal  # noqa: F401
        return True
    except Exception:
        return False


_SKIP_REASON = "src.loop.gate or domains.tennis not importable in this environment"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGateDeterminism:
    """Gate evaluate() must be deterministic: same inputs => same verdict+metrics."""

    @pytest.mark.skipif(not _imports_available(), reason=_SKIP_REASON)
    def test_verdict_identical_across_two_runs(self) -> None:
        """Verdict enum and all boolean criteria must be bit-identical across runs.

        The gate uses XGBoost with random_state=42 (baked into _fit_predict) and
        numpy.default_rng(42) in null_shuffle_control.  With device='cpu' and a
        fixed synthetic bundle, any non-determinism is a real finding.
        """
        bundle = _build_synthetic_bundle()

        # Run 1
        sig1 = _build_signal_with_bundle(bundle)
        r1 = _call_gate(sig1)

        # Run 2 — fresh signal object, same injected bundle
        sig2 = _build_signal_with_bundle(bundle)
        r2 = _call_gate(sig2)

        keys1 = _gate_result_key_fields(r1)
        keys2 = _gate_result_key_fields(r2)

        mismatches = {k: (keys1[k], keys2[k])
                      for k in keys1 if keys1[k] != keys2[k]}
        assert not mismatches, (
            "FINDING: gate verdict non-determinism detected.\n"
            f"Mismatched boolean/verdict fields:\n"
            + "\n".join(f"  {k}: run1={v[0]!r}  run2={v[1]!r}"
                        for k, v in mismatches.items())
            + f"\nRun1 reason: {r1.reason}"
            + f"\nRun2 reason: {r2.reason}"
        )

    @pytest.mark.skipif(not _imports_available(), reason=_SKIP_REASON)
    def test_numeric_metrics_identical_across_two_runs(self) -> None:
        """Numeric gate metrics must be identical (or within float64 epsilon).

        XGBoost trained with random_state=42, CPU-only, n_jobs=-1 may have tiny
        rounding differences across OS-thread schedules.  We allow atol=1e-9 for
        floating-point accumulation drift but assert the relative magnitude of any
        difference is negligible.  If the diff is larger than 1e-6 relative, that
        is a REAL finding.
        """
        bundle = _build_synthetic_bundle()

        sig1 = _build_signal_with_bundle(bundle)
        r1 = _call_gate(sig1)

        sig2 = _build_signal_with_bundle(bundle)
        r2 = _call_gate(sig2)

        nums1 = _gate_result_numeric_fields(r1)
        nums2 = _gate_result_numeric_fields(r2)

        # Keys must match (same folds evaluated)
        assert set(nums1.keys()) == set(nums2.keys()), (
            "FINDING: gate produced different numeric fields across runs.\n"
            f"  Run1 keys: {sorted(nums1)}\n"
            f"  Run2 keys: {sorted(nums2)}"
        )

        large_diffs = {}
        for k in nums1:
            v1, v2 = nums1[k], nums2[k]
            if v1 is None and v2 is None:
                continue
            diff = abs(float(v1) - float(v2))
            scale = max(abs(float(v1)), abs(float(v2)), 1e-12)
            rel = diff / scale
            if diff > 1e-9:  # anything above float64 epsilon is noteworthy
                large_diffs[k] = {"v1": v1, "v2": v2, "abs_diff": diff, "rel_diff": rel}

        # Fail on anything larger than 1e-6 relative — that's a true non-determinism
        serious = {k: v for k, v in large_diffs.items() if v["rel_diff"] > 1e-6}
        assert not serious, (
            "FINDING: gate numeric metrics differ by more than 1e-6 relative.\n"
            + "\n".join(
                f"  {k}: run1={v['v1']:.8g}  run2={v['v2']:.8g}"
                f"  abs_diff={v['abs_diff']:.3e}  rel_diff={v['rel_diff']:.3e}"
                for k, v in serious.items()
            )
        )

    @pytest.mark.skipif(not _imports_available(), reason=_SKIP_REASON)
    def test_reason_string_identical_across_two_runs(self) -> None:
        """The reason string must be identical — it encodes the same numeric values."""
        bundle = _build_synthetic_bundle()

        sig1 = _build_signal_with_bundle(bundle)
        r1 = _call_gate(sig1)

        sig2 = _build_signal_with_bundle(bundle)
        r2 = _call_gate(sig2)

        assert r1.reason == r2.reason, (
            "FINDING: gate reason string differs across runs.\n"
            f"  Run1: {r1.reason!r}\n"
            f"  Run2: {r2.reason!r}"
        )

    @pytest.mark.skipif(not _imports_available(), reason=_SKIP_REASON)
    def test_wf_folds_length_and_values_identical(self) -> None:
        """Walk-forward folds list must have the same length and values each run."""
        bundle = _build_synthetic_bundle()

        sig1 = _build_signal_with_bundle(bundle)
        r1 = _call_gate(sig1)

        sig2 = _build_signal_with_bundle(bundle)
        r2 = _call_gate(sig2)

        assert len(r1.wf_folds) == len(r2.wf_folds), (
            "FINDING: different number of walk-forward folds across runs.\n"
            f"  Run1: {len(r1.wf_folds)} folds  {r1.wf_folds}\n"
            f"  Run2: {len(r2.wf_folds)} folds  {r2.wf_folds}"
        )
        for i, (f1, f2) in enumerate(zip(r1.wf_folds, r2.wf_folds)):
            diff = abs(f1 - f2)
            scale = max(abs(f1), abs(f2), 1e-12)
            assert diff / scale <= 1e-6, (
                f"FINDING: walk-forward fold {i} differs by more than 1e-6 relative.\n"
                f"  Run1 fold {i}: {f1:.8g}\n"
                f"  Run2 fold {i}: {f2:.8g}\n"
                f"  abs_diff={diff:.3e}  rel_diff={diff/scale:.3e}"
            )
