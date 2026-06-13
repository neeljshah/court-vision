"""tests.platform.test_fdr_correction — Verify BH FDR correction in catalog_common.

Assertions (all using SYNTHETIC p-values; real gate is never invoked):
  1. BH tightens: p=0.04 (passes α=0.05 single-test) FAILS BH when m=16.
  2. Smallest p-values pass; BH step-up property holds.
  3. All-large p-values → none pass; empty list is graceful.
  4. None entries (BUNDLE_ERROR/GATE_ERROR) → None in output, not False.
  5. Existing actual_verdict/passed_expected fields are unchanged after BH annotation.
  6. Integration via run_catalog_common stub: fdr_bh_pass + fdr_bh_threshold appear
     in every verdict row; BUNDLE_ERROR rows get fdr_bh_pass=None.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from scripts.platformkit.catalog_common import _benjamini_hochberg, run_catalog_common
from src.loop.gate import FeatureBundle
from src.loop.signal import GateResult, Hypothesis, Signal, SignalValue, Verdict


# ---------------------------------------------------------------------------
# 1. BH tightens: p=0.04 fails BH when m=16 (rank-1 threshold = 0.00625)
# ---------------------------------------------------------------------------

class TestBHTightens:
    def test_single_moderate_p_fails_bh_m16(self) -> None:
        """p=0.04 at rank 1 of 16; threshold=0.00625; 0.04>0.00625 → FAIL."""
        passes, thr = _benjamini_hochberg([0.99] * 15 + [0.04], q=0.10)
        assert all(p is False for p in passes)
        assert thr is None

    def test_p_exactly_at_rank1_threshold_passes(self) -> None:
        """p=(1/16)*0.10 at rank 1 of 16 → PASS."""
        thr_val = (1 / 16) * 0.10
        passes, thr = _benjamini_hochberg([thr_val] + [0.99] * 15, q=0.10)
        assert passes[0] is True
        assert thr == pytest.approx(thr_val)

    def test_premise_p04_passes_single_alpha05(self) -> None:
        assert 0.04 < 0.05  # confirms the single-test premise


# ---------------------------------------------------------------------------
# 2. Smallest p-values pass; BH step-up
# ---------------------------------------------------------------------------

class TestSmallestPValuesPass:
    def test_two_small_pass_eight_large_fail(self) -> None:
        # m=10, q=0.10; rank1 thr=0.01, rank2 thr=0.02
        passes, thr = _benjamini_hochberg([0.005, 0.015] + [0.99] * 8, q=0.10)
        assert passes[0] is True and passes[1] is True
        assert all(passes[i] is False for i in range(2, 10))
        assert thr == pytest.approx(0.02)

    def test_all_very_small_all_pass(self) -> None:
        # m=5, each p just under its rank threshold
        passes, thr = _benjamini_hochberg([0.01, 0.03, 0.05, 0.07, 0.09], q=0.10)
        assert all(p is True for p in passes)
        assert thr == pytest.approx(0.10)

    def test_step_up_property(self) -> None:
        # m=4, q=0.10: sorted 0.01(r1 thr0.025 PASS), 0.06(r2 thr0.05 FAIL),
        # 0.07(r3 thr0.075 PASS) → max_k=3 → all ranks 1-3 pass via step-up
        passes, thr = _benjamini_hochberg([0.01, 0.06, 0.07, 0.99], q=0.10)
        assert passes[0] is True   # p=0.01
        assert passes[1] is True   # p=0.06 (step-up: rank<=3)
        assert passes[2] is True   # p=0.07
        assert passes[3] is False  # p=0.99


# ---------------------------------------------------------------------------
# 3. All-large → none pass; empty list graceful
# ---------------------------------------------------------------------------

class TestAllLargeOrEmpty:
    def test_all_large_reject(self) -> None:
        passes, thr = _benjamini_hochberg([0.5, 0.6, 0.7, 0.8, 0.9], q=0.10)
        assert all(p is False for p in passes)
        assert thr is None

    def test_empty_list(self) -> None:
        passes, thr = _benjamini_hochberg([], q=0.10)
        assert passes == [] and thr is None


# ---------------------------------------------------------------------------
# 4. Graceful on None entries
# ---------------------------------------------------------------------------

class TestMissingPValues:
    def test_all_none(self) -> None:
        passes, thr = _benjamini_hochberg([None, None], q=0.10)
        assert passes == [None, None] and thr is None

    def test_none_skipped_testable_passes(self) -> None:
        # m=1; p=0.001 <= (1/1)*0.10=0.10 → PASS
        passes, thr = _benjamini_hochberg([None, 0.001, None], q=0.10)
        assert passes[0] is None and passes[1] is True and passes[2] is None
        assert thr == pytest.approx(0.10)

    def test_none_interspersed(self) -> None:
        # m=2 (indices 1,3); rank1 thr=0.05, rank2 thr=0.10
        # 0.001<=0.05 PASS; 0.99>0.10 FAIL
        passes, thr = _benjamini_hochberg([None, 0.001, None, 0.99], q=0.10)
        assert passes == [None, True, None, False]
        assert thr == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 5. Existing row fields are unchanged after BH annotation
# ---------------------------------------------------------------------------

class TestExistingRowsUnchanged:
    def test_verdict_fields_preserved(self) -> None:
        import copy
        original = [
            {"name": "a", "actual_verdict": "REJECT", "p_value": 0.50,
             "passed_expected": True},
            {"name": "b", "actual_verdict": "SHIP", "p_value": 0.04,
             "passed_expected": False},
        ]
        rows = copy.deepcopy(original)
        p_vals = [r["p_value"] for r in rows]
        bh_passes, bh_thr = _benjamini_hochberg(p_vals, q=0.10)
        for row, bh_p in zip(rows, bh_passes):
            row["fdr_bh_pass"] = bh_p
            row["fdr_bh_threshold"] = bh_thr
        for orig, ann in zip(original, rows):
            for key in ("name", "actual_verdict", "p_value", "passed_expected"):
                assert ann[key] == orig[key], f"Field '{key}' was mutated"
        assert all("fdr_bh_pass" in r for r in rows)
        assert all("fdr_bh_threshold" in r for r in rows)


# ---------------------------------------------------------------------------
# 6. Integration: run_catalog_common stub confirms fields appear
# ---------------------------------------------------------------------------

_N = 20


def _make_bundle() -> FeatureBundle:
    base = np.arange(_N * 3, dtype=float).reshape(_N, 3)
    return FeatureBundle(base=base, signal_col=np.zeros(_N),
                         target=np.ones(_N),
                         dates=[f"2024-01-{i+1:02d}" for i in range(_N)])


class _FakeAdapter:
    def feature_bundle(self, hyp: Any, seasons: Sequence[int], **kw: Any) -> FeatureBundle:
        return _make_bundle()


def _make_sig_cls(sig_name: str, p_val: float) -> type:
    class _S(Signal):
        name: str = sig_name  # type: ignore[assignment]
        target: str = "winprob"
        scope: str = "pregame"
        reads_atlas: List[str] = []
        emits: List[str] = []
        _p: float = p_val

        def build(self, ctx: Any) -> SignalValue:  # pragma: no cover
            return None

        def hypothesis(self) -> Hypothesis:
            return Hypothesis(name=self.name, target="winprob", scope="pregame",
                              statement="stub", rationale="stub", source="seed",
                              expected_verdict="REJECT")
    _S.__name__ = sig_name
    return _S


def _stub_eval(sig: Any, **_kw: Any) -> GateResult:
    return GateResult(signal_name=sig.name, verdict=Verdict.REJECT, reason="stub",
                      wf_folds=[-0.01] * 3, wf_all_improve=True, null_delta=-0.01,
                      null_pass=True, ablation_delta=-0.01, ablation_pass=True,
                      calibration_ok=True, clv=0.0, clv_pass=False,
                      p_value=getattr(sig.__class__, "_p", 0.5), fdr_pass=False)


def _run_stub(sig_classes, adapter=None):
    ad = adapter or _FakeAdapter()
    with patch("scripts.platformkit.catalog_common.evaluate", side_effect=_stub_eval):
        return run_catalog_common(sig_classes, ad, [2023],
                                  compute_fn=lambda c, b: np.zeros(b.shape[0]))


class TestIntegrationFdrFields:
    def test_fdr_fields_present_in_all_rows(self) -> None:
        sigs = [_make_sig_cls("ia", 0.80), _make_sig_cls("ib", 0.90)]
        result = _run_stub(sigs)
        for row in result["verdicts"]:
            assert "fdr_bh_pass" in row and "fdr_bh_threshold" in row

    def test_large_p_all_fail_bh(self) -> None:
        sigs = [_make_sig_cls("la", 0.80), _make_sig_cls("lb", 0.90)]
        result = _run_stub(sigs)
        assert all(r["fdr_bh_pass"] is False for r in result["verdicts"])
        assert result["verdicts"][0]["fdr_bh_threshold"] is None

    def test_actual_verdict_unchanged(self) -> None:
        sigs = [_make_sig_cls("vc", 0.5)]
        result = _run_stub(sigs)
        row = result["verdicts"][0]
        assert row["actual_verdict"] == "REJECT" and row["passed_expected"] is True

    def test_bundle_error_row_fdr_none(self) -> None:
        bad = _FakeAdapter()
        bad.feature_bundle = MagicMock(side_effect=RuntimeError("no data"))  # type: ignore[method-assign]
        sigs = [_make_sig_cls("be", 0.5)]
        result = _run_stub(sigs, adapter=bad)
        row = result["verdicts"][0]
        assert row["actual_verdict"] == "BUNDLE_ERROR"
        assert row["fdr_bh_pass"] is None
