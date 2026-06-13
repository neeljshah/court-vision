"""tests.platform.test_catalog_common_reuse — Verify feature_bundle is called ONCE.

Asserts:
  1. adapter.feature_bundle is called exactly ONCE (not once-per-signal).
  2. Each signal gets its own distinct derived signal_col via derive_bundle.
  3. Per-signal gate results match the expected deterministic outcome.

Uses fake adapter + fake signal classes + stubbed gate.evaluate; no real data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.loop.gate import FeatureBundle
from src.loop.signal import GateResult, Hypothesis, Signal, SignalValue, Verdict
from scripts.platformkit.catalog_common import derive_bundle, run_catalog_common


# ---------------------------------------------------------------------------
# Deterministic test fixtures
# ---------------------------------------------------------------------------

_N = 20  # number of rows in the fake bundle
_N_FEATURES = 3

_BASE = np.arange(_N * _N_FEATURES, dtype=float).reshape(_N, _N_FEATURES)
_TARGET = np.ones(_N, dtype=float)
_DATES = [f"2024-01-{i+1:02d}" for i in range(_N)]


def _make_bundle() -> FeatureBundle:
    """Return a deterministic FeatureBundle (signal_col is a placeholder)."""
    return FeatureBundle(
        base=_BASE.copy(),
        signal_col=np.zeros(_N, dtype=float),
        target=_TARGET.copy(),
        dates=list(_DATES),
    )


# ---------------------------------------------------------------------------
# Fake adapter — records how many times feature_bundle is called
# ---------------------------------------------------------------------------

class FakeAdapter:
    def __init__(self) -> None:
        self.call_count: int = 0

    def feature_bundle(
        self, hypothesis: Any, seasons: Sequence[int], **kw: Any
    ) -> FeatureBundle:
        self.call_count += 1
        return _make_bundle()


# ---------------------------------------------------------------------------
# Fake signal classes — three signals, each with a distinct name
# ---------------------------------------------------------------------------

def _make_signal_cls(signal_name: str, col_offset: float) -> type:
    """Factory that returns a Signal subclass with a fixed name + hypothesis."""

    class _FakeSignal(Signal):
        name: str = signal_name
        target: str = "winprob"
        scope: str = "pregame"
        reads_atlas: List[str] = []
        emits: List[str] = []

        def build(self, ctx: Any) -> SignalValue:  # pragma: no cover
            return None

        def hypothesis(self) -> Hypothesis:
            return Hypothesis(
                name=self.name,
                target="winprob",
                scope="pregame",
                statement=f"Fake signal {signal_name}.",
                rationale="Test stub.",
                source="seed",
                expected_verdict="REJECT",
            )

    _FakeSignal.__name__ = signal_name
    _FakeSignal._col_offset = col_offset  # type: ignore[attr-defined]
    return _FakeSignal


_SIG_A = _make_signal_cls("fake_signal_a", 1.0)
_SIG_B = _make_signal_cls("fake_signal_b", 2.0)
_SIG_C = _make_signal_cls("fake_signal_c", 3.0)

FAKE_CATALOG = (_SIG_A, _SIG_B, _SIG_C)


def _compute_fn(signal_cls: type, base: np.ndarray) -> np.ndarray:
    """Return a distinct signal_col per class (offset × ones)."""
    offset: float = getattr(signal_cls, "_col_offset", 0.0)
    return np.full(base.shape[0], offset, dtype=float)


# ---------------------------------------------------------------------------
# Stub GateResult — deterministic REJECT
# ---------------------------------------------------------------------------

def _stub_gate_result(sig: Any, **_kw: Any) -> GateResult:
    """Return a deterministic REJECT result so the test is fast + offline."""
    return GateResult(
        signal_name=sig.name,
        verdict=Verdict.REJECT,
        reason="stubbed-reject",
        wf_folds=[-0.01, -0.01, -0.01],
        wf_all_improve=True,
        null_delta=-0.01,
        null_pass=True,
        ablation_delta=-0.01,
        ablation_pass=True,
        calibration_ok=True,
        clv=0.0,
        clv_pass=False,
        p_value=0.5,
        fdr_pass=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def adapter() -> FakeAdapter:
    return FakeAdapter()


def _run(adapter: FakeAdapter) -> Dict[str, Any]:
    with patch("scripts.platformkit.catalog_common.evaluate", side_effect=_stub_gate_result):
        return run_catalog_common(
            signal_classes=FAKE_CATALOG,
            adapter=adapter,
            seasons=[2023, 2024],
            compute_fn=_compute_fn,
        )


class TestFeatureBundleCalledOnce:
    """feature_bundle is hoisted and called exactly once regardless of catalog size."""

    def test_call_count_is_one(self, adapter: FakeAdapter) -> None:
        _run(adapter)
        assert adapter.call_count == 1, (
            f"Expected feature_bundle to be called 1 time, got {adapter.call_count}. "
            "The hoist optimization may be missing or broken."
        )

    def test_returns_all_signals(self, adapter: FakeAdapter) -> None:
        result = _run(adapter)
        assert len(result["verdicts"]) == len(FAKE_CATALOG)


class TestPerSignalDerivedBundle:
    """derive_bundle is called per signal so each gets a distinct signal_col."""

    def test_each_signal_has_distinct_col(self, adapter: FakeAdapter) -> None:
        """Verify compute_fn is invoked per-signal (offsets 1,2,3 are distinct)."""
        captured_gate_matrices: List[np.ndarray] = []

        def _capturing_evaluate(sig: Any, **kw: Any) -> GateResult:
            mat = sig._gate_matrix  # type: ignore[attr-defined]
            captured_gate_matrices.append(mat.signal_col.copy())
            return _stub_gate_result(sig, **kw)

        with patch(
            "scripts.platformkit.catalog_common.evaluate",
            side_effect=_capturing_evaluate,
        ):
            run_catalog_common(
                signal_classes=FAKE_CATALOG,
                adapter=adapter,
                seasons=[2023],
                compute_fn=_compute_fn,
            )

        assert len(captured_gate_matrices) == 3
        # Each signal's col should equal its offset (1.0, 2.0, 3.0)
        expected_offsets = [1.0, 2.0, 3.0]
        for i, (mat, expected) in enumerate(
            zip(captured_gate_matrices, expected_offsets)
        ):
            assert np.all(mat == expected), (
                f"Signal {i}: expected all-{expected} signal_col, got {mat}"
            )

    def test_base_unchanged_across_signals(self, adapter: FakeAdapter) -> None:
        """The shared base matrix must be identical for every signal."""
        captured_bases: List[np.ndarray] = []

        def _capturing_evaluate(sig: Any, **kw: Any) -> GateResult:
            mat = sig._gate_matrix  # type: ignore[attr-defined]
            captured_bases.append(mat.base.copy())
            return _stub_gate_result(sig, **kw)

        with patch(
            "scripts.platformkit.catalog_common.evaluate",
            side_effect=_capturing_evaluate,
        ):
            run_catalog_common(
                signal_classes=FAKE_CATALOG,
                adapter=adapter,
                seasons=[2023],
                compute_fn=_compute_fn,
            )

        assert len(captured_bases) == 3
        for i in range(1, len(captured_bases)):
            np.testing.assert_array_equal(
                captured_bases[0], captured_bases[i],
                err_msg=f"Base matrix differs between signal 0 and signal {i}.",
            )


class TestResultsMatchPerSignalPath:
    """Verdicts are identical to what the old per-signal-bundle path would produce."""

    def test_verdicts_are_reject(self, adapter: FakeAdapter) -> None:
        result = _run(adapter)
        for row in result["verdicts"]:
            assert row["actual_verdict"] == "REJECT", (
                f"Signal {row['name']}: expected REJECT, got {row['actual_verdict']}"
            )

    def test_signal_names_correct(self, adapter: FakeAdapter) -> None:
        result = _run(adapter)
        names = [r["name"] for r in result["verdicts"]]
        assert names == ["fake_signal_a", "fake_signal_b", "fake_signal_c"]

    def test_n_matches_bundle_rows(self, adapter: FakeAdapter) -> None:
        result = _run(adapter)
        for row in result["verdicts"]:
            assert row["n"] == _N, (
                f"Signal {row['name']}: expected n={_N}, got {row['n']}"
            )

    def test_ok_flag_when_all_pass_expected(self, adapter: FakeAdapter) -> None:
        result = _run(adapter)
        # All expected_verdicts are REJECT; actual = REJECT → passed_expected = True
        assert result["ok"] is True

    def test_coverage_is_full(self, adapter: FakeAdapter) -> None:
        result = _run(adapter)
        for row in result["verdicts"]:
            assert row["coverage"] == 1.0, (
                f"Signal {row['name']}: expected coverage=1.0, got {row['coverage']}"
            )


class TestEmptyCatalog:
    """Empty catalog returns ok=True, verdicts=[], and never calls feature_bundle."""

    def test_empty_catalog(self, adapter: FakeAdapter) -> None:
        with patch("scripts.platformkit.catalog_common.evaluate", side_effect=_stub_gate_result):
            result = run_catalog_common(
                signal_classes=[],
                adapter=adapter,
                seasons=[2023],
                compute_fn=_compute_fn,
            )
        assert result == {"ok": True, "verdicts": []}
        assert adapter.call_count == 0


class TestBundleErrorPropagatesAllSignals:
    """When feature_bundle raises, all signals get BUNDLE_ERROR (not just the first)."""

    def test_bundle_error_all_signals(self) -> None:
        bad_adapter = FakeAdapter()
        bad_adapter.feature_bundle = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("corpus missing")
        )
        with patch("scripts.platformkit.catalog_common.evaluate", side_effect=_stub_gate_result):
            result = run_catalog_common(
                signal_classes=FAKE_CATALOG,
                adapter=bad_adapter,
                seasons=[2023],
                compute_fn=_compute_fn,
            )
        assert len(result["verdicts"]) == len(FAKE_CATALOG)
        for row in result["verdicts"]:
            assert row["actual_verdict"] == "BUNDLE_ERROR"
            assert "corpus missing" in row["reason"]
        # feature_bundle called exactly once even on error
        assert bad_adapter.feature_bundle.call_count == 1
