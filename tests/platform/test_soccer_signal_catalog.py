"""tests/platform/test_soccer_signal_catalog.py — Gate-catalog tests for soccer.

Verifies:
  1. run_catalog returns {"ok": bool, "verdicts": list} with one row per signal.
  2. Every verdict row has "actual_verdict" in {SHIP, DEFER, REJECT, VARIANCE_ONLY}.
  3. Report file is written when out_path is supplied.
  4. No exception for any candidate with synthetic data.
  5. CATALOG_SIGNALS has 7 entries, all distinct names.
  6. _compute_signal_col returns correct shapes and values for each candidate.
  7. AST import-contract: signal_catalog.py imports only allowed modules.

Fixtures use a tiny synthetic SoccerAdapter mirroring the real adapter's
feature_bundle() interface but backed by in-memory NumPy arrays.
"""
from __future__ import annotations

import ast
import datetime as _dt
import pathlib
import tempfile
from typing import Any, Dict, List, Sequence

import numpy as np
import pytest

from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis, Signal
from domains.soccer.signal_catalog import (
    CATALOG_SIGNALS,
    AttackingImbalanceSignal,
    LamTotalDeviationSignal,
    SignedRestDiffSignal,
    HomeAttackShareSignal,
    LamTotalRestInteractionSignal,
    AbsRestDiffSignal,
    LowScoringFlagSignal,
    _compute_signal_col,
    run_catalog,
)

# ---------------------------------------------------------------------------
# Synthetic SoccerAdapter (mirrors adapter.feature_bundle seam)
# ---------------------------------------------------------------------------
_N = 300  # rows — enough for 3-fold WF + ablation cuts

_RNG = np.random.default_rng(42)
_BASE = np.column_stack([
    _RNG.uniform(0.8, 2.2, _N),   # lam_home
    _RNG.uniform(0.6, 1.8, _N),   # lam_away
    _RNG.uniform(1.5, 3.5, _N),   # lam_total
    _RNG.uniform(3.0, 15.0, _N),  # rest_days_home
    _RNG.uniform(3.0, 15.0, _N),  # rest_days_away
])
_SIG = _RNG.uniform(0.3, 0.7, _N)   # p_over25
_TGT = (_RNG.uniform(0, 1, _N) < _SIG).astype(float)
_DATES = [str((_dt.date(2018, 1, 1) + _dt.timedelta(days=i)).isoformat())
          for i in range(_N)]
_LINES = _RNG.uniform(0.40, 0.60, _N)
_CLOSING = _RNG.uniform(0.40, 0.60, _N)


class _SyntheticSoccerAdapter:
    """Minimal adapter that returns a pre-built FeatureBundle for any call."""

    def feature_bundle(self, hypothesis: Hypothesis, seasons: Sequence[int]) -> FeatureBundle:
        return FeatureBundle(
            base=_BASE.copy(),
            signal_col=_SIG.copy(),
            target=_TGT.copy(),
            dates=_DATES.copy(),
            lines=_LINES.copy(),
            closing=_CLOSING.copy(),
        )


_adapter = _SyntheticSoccerAdapter()
_VALID_VERDICTS = {"SHIP", "DEFER", "REJECT", "VARIANCE_ONLY"}

# ---------------------------------------------------------------------------
# Catalog-level tests
# ---------------------------------------------------------------------------

class TestCatalogSignals:
    def test_exactly_seven_entries(self):
        assert len(CATALOG_SIGNALS) == 7

    def test_all_signal_subclasses(self):
        for cls in CATALOG_SIGNALS:
            assert issubclass(cls, Signal), f"{cls} is not a Signal subclass"

    def test_distinct_names(self):
        names = [cls.name for cls in CATALOG_SIGNALS]
        assert len(set(names)) == len(names), f"Duplicate names: {names}"

    def test_all_correct_classes_present(self):
        classes = set(CATALOG_SIGNALS)
        for cls in (AttackingImbalanceSignal, LamTotalDeviationSignal,
                    SignedRestDiffSignal, HomeAttackShareSignal,
                    LamTotalRestInteractionSignal, AbsRestDiffSignal,
                    LowScoringFlagSignal):
            assert cls in classes, f"{cls.__name__} missing from CATALOG_SIGNALS"

    def test_all_target_winprob(self):
        for cls in CATALOG_SIGNALS:
            assert cls.target == "winprob", f"{cls.name}.target != 'winprob'"

    def test_all_scope_pregame(self):
        for cls in CATALOG_SIGNALS:
            assert cls.scope == "pregame", f"{cls.name}.scope != 'pregame'"


# ---------------------------------------------------------------------------
# run_catalog structure
# ---------------------------------------------------------------------------

class TestRunCatalog:
    def _result(self):
        """Run catalog once; cache result for speed."""
        if not hasattr(self, "_cached"):
            self._cached = run_catalog(_adapter, seasons=[2019, 2020])
        return self._cached

    def test_returns_dict_with_ok_and_verdicts(self):
        r = self._result()
        assert isinstance(r, dict)
        assert "ok" in r and "verdicts" in r

    def test_verdicts_count_matches_catalog(self):
        r = self._result()
        assert len(r["verdicts"]) == len(CATALOG_SIGNALS)

    def test_all_verdicts_in_valid_set(self):
        r = self._result()
        for row in r["verdicts"]:
            assert row["actual_verdict"] in _VALID_VERDICTS, (
                f"{row['name']}: unexpected verdict '{row['actual_verdict']}'"
            )

    def test_no_bundle_error_or_gate_error(self):
        r = self._result()
        for row in r["verdicts"]:
            assert row["actual_verdict"] not in ("BUNDLE_ERROR", "GATE_ERROR"), (
                f"{row['name']} raised an error: {row.get('reason')}"
            )

    def test_each_row_has_name_and_reason(self):
        r = self._result()
        for row in r["verdicts"]:
            assert row.get("name"), "Missing 'name' in verdict row"
            assert "reason" in row, f"{row['name']} missing 'reason'"

    def test_ok_is_bool(self):
        r = self._result()
        assert isinstance(r["ok"], bool)


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

class TestReportWriting:
    def test_report_written_when_out_path_given(self, tmp_path):
        out = tmp_path / "Soccer" / "Signals" / "_Catalog.md"
        run_catalog(_adapter, seasons=[2019], out_path=out)
        assert out.exists(), "Report file not written"
        content = out.read_text(encoding="utf-8")
        assert "Honest signal catalog" in content
        assert "NO edge claimed" in content

    def test_report_contains_verdict_table(self, tmp_path):
        out = tmp_path / "_Catalog.md"
        run_catalog(_adapter, seasons=[2019], out_path=out)
        content = out.read_text(encoding="utf-8")
        assert "| Signal |" in content
        assert "soccer_attacking_imbalance" in content

    def test_report_has_gate_detail_section(self, tmp_path):
        out = tmp_path / "_Catalog.md"
        run_catalog(_adapter, seasons=[2019], out_path=out)
        content = out.read_text(encoding="utf-8")
        assert "## Gate detail" in content


# ---------------------------------------------------------------------------
# _compute_signal_col correctness
# ---------------------------------------------------------------------------

class TestComputeSignalCol:
    def test_attacking_imbalance_shape(self):
        sc = _compute_signal_col(AttackingImbalanceSignal, _BASE)
        assert sc.shape == (_N,)

    def test_attacking_imbalance_nonnegative(self):
        sc = _compute_signal_col(AttackingImbalanceSignal, _BASE)
        assert np.all(sc >= 0)

    def test_lam_total_deviation_mean_near_zero(self):
        sc = _compute_signal_col(LamTotalDeviationSignal, _BASE)
        assert abs(float(np.nanmean(sc))) < 1e-6

    def test_signed_rest_diff_correct(self):
        sc = _compute_signal_col(SignedRestDiffSignal, _BASE)
        expected = _BASE[:, 3] - _BASE[:, 4]
        np.testing.assert_allclose(sc, expected)

    def test_home_attack_share_nonnegative(self):
        sc = _compute_signal_col(HomeAttackShareSignal, _BASE)
        valid = sc[~np.isnan(sc)]
        assert np.all(valid >= 0)

    def test_lam_total_rest_interaction_clipped(self):
        sc = _compute_signal_col(LamTotalRestInteractionSignal, _BASE)
        assert np.all(sc >= -30.0) and np.all(sc <= 30.0)

    def test_abs_rest_diff_nonnegative(self):
        sc = _compute_signal_col(AbsRestDiffSignal, _BASE)
        assert np.all(sc >= 0)

    def test_low_scoring_flag_binary(self):
        sc = _compute_signal_col(LowScoringFlagSignal, _BASE)
        assert set(sc.tolist()).issubset({0.0, 1.0})

    def test_unknown_signal_returns_zeros(self):
        class _FakeSig(Signal):
            name: str = "soccer_unknown_xyz"
            target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
            def build(self, ctx): return None
            def hypothesis(self): return Hypothesis(name=self.name, target="winprob",
                scope="pregame", statement="x", rationale="x", source="seed")
        sc = _compute_signal_col(_FakeSig, _BASE)
        assert np.all(sc == 0.0)


# ---------------------------------------------------------------------------
# AST import-contract check for signal_catalog.py
# ---------------------------------------------------------------------------

class TestImportContract:
    CATALOG_FILE = (
        pathlib.Path(__file__).parent.parent.parent
        / "domains" / "soccer" / "signal_catalog.py"
    )

    def _imports(self):
        source = self.CATALOG_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
        return mods

    def test_no_domains_nba(self):
        for m in self._imports():
            assert not m.startswith("domains.nba"), f"Forbidden: {m}"
            assert not m.startswith("domains.basketball_nba"), f"Forbidden: {m}"

    def test_no_domains_tennis(self):
        for m in self._imports():
            assert not m.startswith("domains.tennis"), f"Forbidden: {m}"

    def test_no_src_data_sim_tracking_pipeline(self):
        forbidden = ("src.data", "src.sim", "src.tracking", "src.pipeline")
        for m in self._imports():
            for f in forbidden:
                assert not m.startswith(f), f"Forbidden: {m}"

    def test_no_domains_soccer_config(self):
        for m in self._imports():
            assert m != "domains.soccer.config", "Forbidden: domains.soccer.config"

    def test_allowed_src_imports_only(self):
        allowed_src = {"src.loop.gate", "src.loop.signal"}
        for m in self._imports():
            if m.startswith("src."):
                assert m in allowed_src, f"Non-whitelisted src import: {m}"
