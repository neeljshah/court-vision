"""tests/platform/test_soccer_signal_catalog_joint.py — Gate-catalog tests for soccer JOINT signals.

Verifies:
  1. run_joint_catalog returns {"ok": bool, "verdicts": list} with one row per signal.
  2. Every verdict row has "actual_verdict" in {SHIP, DEFER, REJECT, VARIANCE_ONLY}.
  3. No exception (BUNDLE_ERROR/GATE_ERROR) for any candidate with synthetic data.
  4. CATALOG_JOINT_SIGNALS has exactly 8 entries, all distinct names.
  5. _compute_joint_signal_col returns correct shapes/values for each candidate.
  6. Report file is written with expected headers.
  7. AST import-contract: signal_catalog_joint.py imports only allowed modules.

Fixtures use a tiny synthetic SoccerAdapter (N=300) mirroring the real adapter seam.
"""
from __future__ import annotations
import ast
import datetime as _dt
import pathlib
from typing import Sequence
import numpy as np
import pytest
from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis, Signal
from domains.soccer.signal_catalog_joint import (
    CATALOG_JOINT_SIGNALS,
    LamDiffRestDiffProductSignal,
    LamTotalAbsRestDiffSignal,
    LamRatioSignal,
    HighVolumeAttackImbalanceSignal,
    HomeAttackShareRestDiffSignal,
    LamDiffSquaredSignal,
    SignedLamDiffRestDiffSignal,
    LamWeightedRestDiffSignal,
    _compute_joint_signal_col,
    run_joint_catalog,
)

# ---------------------------------------------------------------------------
# Synthetic SoccerAdapter (N=300)
# ---------------------------------------------------------------------------
_N = 300
_RNG = np.random.default_rng(99)
_BASE = np.column_stack([
    _RNG.uniform(0.8, 2.2, _N),   # lam_home
    _RNG.uniform(0.6, 1.8, _N),   # lam_away
    _RNG.uniform(1.5, 3.5, _N),   # lam_total
    _RNG.uniform(3.0, 15.0, _N),  # rest_days_home
    _RNG.uniform(3.0, 15.0, _N),  # rest_days_away
])
_SIG = _RNG.uniform(0.3, 0.7, _N)
_TGT = (_RNG.uniform(0, 1, _N) < _SIG).astype(float)
_DATES = [str((_dt.date(2018,1,1)+_dt.timedelta(days=i)).isoformat()) for i in range(_N)]
_LINES = _RNG.uniform(0.40, 0.60, _N)
_CLOSING = _RNG.uniform(0.40, 0.60, _N)


class _SyntheticSoccerAdapter:
    def feature_bundle(self, hypothesis: Hypothesis, seasons: Sequence[int]) -> FeatureBundle:
        return FeatureBundle(base=_BASE.copy(), signal_col=_SIG.copy(), target=_TGT.copy(),
                             dates=_DATES.copy(), lines=_LINES.copy(), closing=_CLOSING.copy())


_adapter = _SyntheticSoccerAdapter()
_VALID_VERDICTS = {"SHIP", "DEFER", "REJECT", "VARIANCE_ONLY"}

# ---------------------------------------------------------------------------
# CATALOG_JOINT_SIGNALS structure
# ---------------------------------------------------------------------------

class TestCatalogJointSignals:
    def test_exactly_eight_entries(self):
        assert len(CATALOG_JOINT_SIGNALS) == 8

    def test_all_signal_subclasses(self):
        for cls in CATALOG_JOINT_SIGNALS:
            assert issubclass(cls, Signal), f"{cls} is not a Signal subclass"

    def test_distinct_names(self):
        names = [cls.name for cls in CATALOG_JOINT_SIGNALS]
        assert len(set(names)) == len(names), f"Duplicate names: {names}"

    def test_all_correct_classes_present(self):
        classes = set(CATALOG_JOINT_SIGNALS)
        for cls in (LamDiffRestDiffProductSignal, LamTotalAbsRestDiffSignal, LamRatioSignal,
                    HighVolumeAttackImbalanceSignal, HomeAttackShareRestDiffSignal,
                    LamDiffSquaredSignal, SignedLamDiffRestDiffSignal, LamWeightedRestDiffSignal):
            assert cls in classes, f"{cls.__name__} missing from CATALOG_JOINT_SIGNALS"

    def test_all_target_winprob(self):
        for cls in CATALOG_JOINT_SIGNALS:
            assert cls.target == "winprob", f"{cls.name}.target != 'winprob'"

    def test_all_scope_pregame(self):
        for cls in CATALOG_JOINT_SIGNALS:
            assert cls.scope == "pregame", f"{cls.name}.scope != 'pregame'"

    def test_all_expect_reject(self):
        for cls in CATALOG_JOINT_SIGNALS:
            hyp = cls().hypothesis()
            assert hyp.expected_verdict == "REJECT", (
                f"{cls.name}.expected_verdict should be REJECT, got {hyp.expected_verdict}")


# ---------------------------------------------------------------------------
# run_joint_catalog structure
# ---------------------------------------------------------------------------

class TestRunJointCatalog:
    def _result(self):
        if not hasattr(self, "_cached"):
            self._cached = run_joint_catalog(_adapter, seasons=[2019, 2020])
        return self._cached

    def test_returns_dict_with_ok_and_verdicts(self):
        r = self._result()
        assert isinstance(r, dict) and "ok" in r and "verdicts" in r

    def test_verdicts_count_matches_catalog(self):
        assert len(self._result()["verdicts"]) == len(CATALOG_JOINT_SIGNALS)

    def test_all_verdicts_in_valid_set(self):
        for row in self._result()["verdicts"]:
            assert row["actual_verdict"] in _VALID_VERDICTS, (
                f"{row['name']}: unexpected verdict '{row['actual_verdict']}'")

    def test_no_bundle_error_or_gate_error(self):
        for row in self._result()["verdicts"]:
            assert row["actual_verdict"] not in ("BUNDLE_ERROR","GATE_ERROR"), (
                f"{row['name']} error: {row.get('reason')}")

    def test_each_row_has_name_and_reason(self):
        for row in self._result()["verdicts"]:
            assert row.get("name"), "Missing 'name' in verdict row"
            assert "reason" in row, f"{row['name']} missing 'reason'"

    def test_ok_is_bool(self):
        assert isinstance(self._result()["ok"], bool)

    def test_all_rows_have_coverage(self):
        for row in self._result()["verdicts"]:
            assert "coverage" in row and 0.0 <= float(row["coverage"]) <= 1.0


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

class TestJointReportWriting:
    def test_report_written_when_out_path_given(self, tmp_path):
        out = tmp_path / "Soccer" / "Signals" / "_Catalog_Joint.md"
        run_joint_catalog(_adapter, seasons=[2019], out_path=out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Honest JOINT signal catalog" in content
        assert "NO edge claimed" in content

    def test_report_contains_verdict_table(self, tmp_path):
        out = tmp_path / "_Catalog_Joint.md"
        run_joint_catalog(_adapter, seasons=[2019], out_path=out)
        content = out.read_text(encoding="utf-8")
        assert "| Signal |" in content and "soccer_lam_diff_x_rest_diff" in content

    def test_report_has_gate_detail_section(self, tmp_path):
        out = tmp_path / "_Catalog_Joint.md"
        run_joint_catalog(_adapter, seasons=[2019], out_path=out)
        assert "## Gate detail" in out.read_text(encoding="utf-8")

    def test_report_has_contract_section(self, tmp_path):
        out = tmp_path / "_Catalog_Joint.md"
        run_joint_catalog(_adapter, seasons=[2019], out_path=out)
        assert "JOINT transforms" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _compute_joint_signal_col correctness
# ---------------------------------------------------------------------------

class TestComputeJointSignalCol:
    def test_all_correct_shapes(self):
        for cls in CATALOG_JOINT_SIGNALS:
            sc = _compute_joint_signal_col(cls, _BASE)
            assert sc.shape == (_N,), f"{cls.name}: wrong shape {sc.shape}"
            assert sc[~np.isnan(sc)].shape[0] > 0, f"{cls.name}: all NaN"

    def test_lam_diff_rest_diff_clipped(self):
        sc = _compute_joint_signal_col(LamDiffRestDiffProductSignal, _BASE)
        assert np.all(sc >= -50.) and np.all(sc <= 50.)

    def test_lam_total_abs_rest_diff_nonnegative(self):
        sc = _compute_joint_signal_col(LamTotalAbsRestDiffSignal, _BASE)
        assert np.all(sc >= 0.) and np.all(sc <= 60.)

    def test_lam_ratio_positive(self):
        sc = _compute_joint_signal_col(LamRatioSignal, _BASE)
        valid = sc[~np.isnan(sc)]
        assert np.all(valid > 0.) and np.all(valid <= 10.)

    def test_high_vol_attack_imbalance_nonnegative(self):
        sc = _compute_joint_signal_col(HighVolumeAttackImbalanceSignal, _BASE)
        assert np.all(sc >= 0.)

    def test_home_share_rest_diff_clipped(self):
        sc = _compute_joint_signal_col(HomeAttackShareRestDiffSignal, _BASE)
        valid = sc[~np.isnan(sc)]
        assert np.all(valid >= -15.) and np.all(valid <= 15.)

    def test_lam_diff_squared_nonnegative(self):
        sc = _compute_joint_signal_col(LamDiffSquaredSignal, _BASE)
        assert np.all(sc >= 0.) and np.all(sc <= 25.)

    def test_signed_lam_diff_x_rest_diff_clipped(self):
        sc = _compute_joint_signal_col(SignedLamDiffRestDiffSignal, _BASE)
        assert np.all(sc >= -15.) and np.all(sc <= 15.)

    def test_lam_weighted_rest_diff_clipped(self):
        sc = _compute_joint_signal_col(LamWeightedRestDiffSignal, _BASE)
        valid = sc[~np.isnan(sc)]
        assert np.all(valid >= -20.) and np.all(valid <= 20.)

    def test_unknown_signal_returns_zeros(self):
        class _FakeJoint(Signal):
            name: str = "soccer_unknown_joint_xyz"
            target: str = "winprob"; scope: str = "pregame"; reads_atlas = []; emits = []
            def build(self, ctx): return None
            def hypothesis(self): return Hypothesis(name=self.name,target="winprob",
                scope="pregame",statement="x",rationale="x",source="seed")
        assert np.all(_compute_joint_signal_col(_FakeJoint, _BASE) == 0.)

    def test_lam_ratio_correct_formula(self):
        sc = _compute_joint_signal_col(LamRatioSignal, _BASE)
        expected = np.clip(_BASE[:,0]/_BASE[:,1], 0.1, 10.)
        np.testing.assert_allclose(sc[~np.isnan(sc)], expected[~np.isnan(sc)], rtol=1e-5)

    def test_lam_diff_squared_correct_formula(self):
        sc = _compute_joint_signal_col(LamDiffSquaredSignal, _BASE)
        np.testing.assert_allclose(sc, np.minimum((_BASE[:,0]-_BASE[:,1])**2, 25.), rtol=1e-5)


# ---------------------------------------------------------------------------
# AST import-contract
# ---------------------------------------------------------------------------

class TestJointImportContract:
    CATALOG_FILE = (pathlib.Path(__file__).parent.parent.parent
                    / "domains" / "soccer" / "signal_catalog_joint.py")

    def _imports(self):
        tree = ast.parse(self.CATALOG_FILE.read_text(encoding="utf-8"))
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
        return mods

    def test_no_domains_nba(self):
        for m in self._imports():
            assert not m.startswith("domains.nba") and not m.startswith("domains.basketball_nba")

    def test_no_domains_tennis(self):
        for m in self._imports():
            assert not m.startswith("domains.tennis"), f"Forbidden: {m}"

    def test_no_src_data_sim_tracking_pipeline(self):
        for m in self._imports():
            for f in ("src.data","src.sim","src.tracking","src.pipeline"):
                assert not m.startswith(f), f"Forbidden: {m}"

    def test_no_domains_soccer_config(self):
        for m in self._imports():
            assert m != "domains.soccer.config"

    def test_no_domains_soccer_signal_catalog(self):
        for m in self._imports():
            assert "domains.soccer.signal_catalog" not in m

    def test_allowed_src_imports_only(self):
        allowed = {"src.loop.gate","src.loop.signal"}
        for m in self._imports():
            if m.startswith("src."):
                assert m in allowed, f"Non-whitelisted src import: {m}"
