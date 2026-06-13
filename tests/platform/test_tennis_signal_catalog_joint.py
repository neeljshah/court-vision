"""tests/platform/test_tennis_signal_catalog_joint.py — Offline tests for joint signal catalog.

Synthetic in-memory data only (no network, no full XGBoost corpus). Verifies:
  1. CATALOG_JOINT_SIGNALS structure (name/target/hypothesis/docstring contracts).
  2. run_joint_catalog() return schema and valid verdicts.
  3. Report writing (out_path creates non-empty markdown with required headers).
  4. F5 compliance (no banned imports in signal_catalog_joint.py).
  5. _compute_joint_signal_col shape/value contracts + _derive_bundle isolation.

Run:
    python -m pytest tests/platform/test_tennis_signal_catalog_joint.py -q --timeout=120
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from typing import List, Set

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JOINT_CATALOG_FILE = REPO_ROOT / "domains" / "tennis" / "signal_catalog_joint.py"
VALID_VERDICTS: Set[str] = {"SHIP", "DEFER", "REJECT", "VARIANCE_ONLY", "BUNDLE_ERROR", "GATE_ERROR"}
_BANNED_PREFIXES = (
    "domains.nba", "src.data", "src.sim", "src.tracking", "src.pipeline",
    "basketball_nba", "domains.mlb", "domains.soccer",
)


# ---------------------------------------------------------------------------
# Synthetic data factories
# ---------------------------------------------------------------------------

def _make_matches(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(99)
    base_date = dt.date(2022, 1, 5)
    dates = [base_date + dt.timedelta(days=int(d)) for d in np.cumsum(rng.integers(1, 4, n))]
    player_ids = list(range(1, 26))
    rows = []
    for i, d in enumerate(dates):
        p1, p2 = rng.choice(player_ids, size=2, replace=False)
        rows.append({
            "date": str(d), "tourney_id": f"{d.year}-T{i % 10:03d}",
            "p1_id": int(p1), "p2_id": int(p2), "winner": int(rng.integers(1, 3)),
            "surface": ["Hard", "Clay", "Grass"][i % 3], "score": "6-4 6-3",
            "round": ["R64", "R32", "QF", "SF", "F"][i % 5], "match_num": i,
            "best_of": 5 if i % 8 == 0 else 3, "tour": "atp",
            "season": d.year, "event_id": f"{d}-T{i % 10:03d}-{p1}-{p2}", "retirement": False,
        })
    return pd.DataFrame(rows)


def _make_odds(matches_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for _, row in matches_df.iterrows():
        p1_true = rng.uniform(0.35, 0.65); vig = 1.04
        ps_p1, ps_p2 = round(vig / p1_true, 2), round(vig / (1.0 - p1_true), 2)
        w = int(row["winner"])
        rows.append({
            "event_id": row["event_id"], "ps_p1": ps_p1, "ps_p2": ps_p2,
            "b365_p1": round(ps_p1 * 0.97, 2), "b365_p2": round(ps_p2 * 0.97, 2),
            "psw": ps_p1 if w == 1 else ps_p2, "psl": ps_p2 if w == 1 else ps_p1,
            "b365w": round(ps_p1 * 0.97, 2) if w == 1 else round(ps_p2 * 0.97, 2),
            "b365l": round(ps_p2 * 0.97, 2) if w == 1 else round(ps_p1 * 0.97, 2),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def matches_df() -> pd.DataFrame: return _make_matches(300)

@pytest.fixture(scope="module")
def odds_df(matches_df: pd.DataFrame) -> pd.DataFrame: return _make_odds(matches_df)

@pytest.fixture(scope="module")
def adapter(matches_df: pd.DataFrame, odds_df: pd.DataFrame):
    from domains.tennis.adapter import TennisAdapter
    return TennisAdapter(matches_df=matches_df, odds_df=odds_df)

@pytest.fixture(scope="module")
def joint_result(adapter):
    from domains.tennis.signal_catalog_joint import run_joint_catalog
    return run_joint_catalog(adapter, seasons=[2022, 2023])

@pytest.fixture(scope="module")
def base_bundle(adapter):
    from src.loop.signal import Hypothesis
    hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
    return adapter.feature_bundle(hyp, seasons=[2022])


# ---------------------------------------------------------------------------
# 1. Catalog structure
# ---------------------------------------------------------------------------

class TestJointCatalogStructure:
    def test_is_tuple_non_empty(self) -> None:
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS
        assert isinstance(CATALOG_JOINT_SIGNALS, tuple) and len(CATALOG_JOINT_SIGNALS) >= 6

    def test_names_start_with_tennis_joint_and_unique(self) -> None:
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS
        names = [cls.name for cls in CATALOG_JOINT_SIGNALS]
        assert all(n.startswith("tennis_joint_") for n in names), "all names must start with 'tennis_joint_'"
        assert len(names) == len(set(names)), f"Duplicate signal names: {names}"

    def test_target_winprob_and_expected_reject(self) -> None:
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS
        for cls in CATALOG_JOINT_SIGNALS:
            inst = cls()
            assert inst.target == "winprob", f"{cls.name}.target must be 'winprob'"
            hyp = inst.hypothesis()
            assert hyp.expected_verdict and "REJECT" in hyp.expected_verdict.upper()

    def test_docstrings_have_expected_verdict_reject(self) -> None:
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS
        for cls in CATALOG_JOINT_SIGNALS:
            doc = cls.__doc__ or ""
            assert "Expected gate verdict:" in doc and "REJECT" in doc, (
                f"{cls.__name__} docstring missing 'Expected gate verdict: REJECT'")

    def test_names_differ_from_original_catalog(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS
        originals = {cls.name for cls in CATALOG_SIGNALS}
        for cls in CATALOG_JOINT_SIGNALS:
            assert cls.name not in originals, f"{cls.name} duplicates an original catalog signal"


# ---------------------------------------------------------------------------
# 2. run_joint_catalog return schema + valid verdicts
# ---------------------------------------------------------------------------

class TestRunJointCatalogSchema:
    def test_schema_ok(self, joint_result) -> None:
        assert isinstance(joint_result, dict)
        assert "ok" in joint_result and isinstance(joint_result["ok"], bool)
        assert "verdicts" in joint_result and isinstance(joint_result["verdicts"], list)

    def test_verdicts_length_matches_catalog(self, joint_result) -> None:
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS
        assert len(joint_result["verdicts"]) == len(CATALOG_JOINT_SIGNALS)

    def test_each_verdict_has_required_fields_and_valid_verdict(self, joint_result) -> None:
        required = {"name", "expected", "actual_verdict", "passed_expected", "n", "coverage"}
        for row in joint_result["verdicts"]:
            assert not (required - set(row.keys())), f"Missing fields in {row}"
            assert row["actual_verdict"] in VALID_VERDICTS

    def test_no_exception_single_season(self, adapter) -> None:
        from domains.tennis.signal_catalog_joint import run_joint_catalog
        r = run_joint_catalog(adapter, seasons=[2022])
        assert isinstance(r, dict) and "verdicts" in r


# ---------------------------------------------------------------------------
# 3. Report writing
# ---------------------------------------------------------------------------

class TestJointReportWriting:
    def test_report_written_with_honest_header_and_table(self, adapter, tmp_path) -> None:
        from domains.tennis.signal_catalog_joint import run_joint_catalog
        out = tmp_path / "joint_catalog_report.md"
        run_joint_catalog(adapter, seasons=[2022, 2023], out_path=out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert len(content) > 100
        assert "Honest JOINT signal catalog" in content
        assert "NO edge claimed" in content
        assert "| Signal |" in content

    def test_no_report_without_out_path(self, adapter) -> None:
        from domains.tennis.signal_catalog_joint import run_joint_catalog
        assert isinstance(run_joint_catalog(adapter, seasons=[2022], out_path=None), dict)


# ---------------------------------------------------------------------------
# 4. F5 compliance
# ---------------------------------------------------------------------------

def _collect_imports_ast(source: str) -> List[str]:
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names: names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names

class TestF5Compliance:
    def test_file_exists(self) -> None:
        assert JOINT_CATALOG_FILE.exists()

    def test_no_banned_imports_and_kernel_seam_present(self) -> None:
        imports = _collect_imports_ast(JOINT_CATALOG_FILE.read_text(encoding="utf-8"))
        violations = [i for i in imports if any(i == b or i.startswith(b + ".") for b in _BANNED_PREFIXES)]
        assert not violations, f"F5-banned imports: {violations}"
        assert any(i.startswith("src.loop") for i in imports), "must import from src.loop"


# ---------------------------------------------------------------------------
# 5. _compute_joint_signal_col shape/value contracts + _derive_bundle
# ---------------------------------------------------------------------------

class TestComputeJointSignalCol:
    def test_all_signals_correct_shape_and_finite(self, base_bundle) -> None:
        from domains.tennis.signal_catalog_joint import CATALOG_JOINT_SIGNALS, _compute_joint_signal_col
        n = base_bundle.base.shape[0]
        for cls in CATALOG_JOINT_SIGNALS:
            col = _compute_joint_signal_col(cls, base_bundle.base)
            assert col.shape == (n,), f"{cls.name}: shape {col.shape} != ({n},)"
            assert np.all(np.isfinite(col) | np.isnan(col)), f"{cls.name}: contains inf"

    def test_bo5_elo_gap_non_negative(self, base_bundle) -> None:
        from domains.tennis.signal_catalog_joint import Bo5EloDiffSignal, _compute_joint_signal_col
        col = _compute_joint_signal_col(Bo5EloDiffSignal, base_bundle.base)
        assert np.all(col >= 0.0), "bo5×|elo_diff| must be non-negative"

    def test_surf_elo_damped_bounded_by_surf_diff(self, base_bundle) -> None:
        from domains.tennis.signal_catalog_joint import SurfDiffEloDampedSignal, _compute_joint_signal_col
        col = _compute_joint_signal_col(SurfDiffEloDampedSignal, base_bundle.base)
        surf = base_bundle.base[:, 1]
        assert np.all(np.abs(col) <= np.abs(surf) + 1e-9)

    def test_rest_ratio_bo5_zero_outside_bo5(self, base_bundle) -> None:
        from domains.tennis.signal_catalog_joint import RestAsymmetryBo5Signal, _compute_joint_signal_col
        col = _compute_joint_signal_col(RestAsymmetryBo5Signal, base_bundle.base)
        bo = base_bundle.base[:, 2]
        assert np.all(col[bo != 5.0] == 0.0), "rest_ratio_bo5 must be zero outside Bo5"

    def test_derive_bundle_preserves_base_and_target(self, base_bundle) -> None:
        from domains.tennis.signal_catalog_joint import (
            CATALOG_JOINT_SIGNALS, _compute_joint_signal_col, _derive_bundle)
        n = base_bundle.base.shape[0]
        for cls in CATALOG_JOINT_SIGNALS:
            col = _compute_joint_signal_col(cls, base_bundle.base)
            derived = _derive_bundle(base_bundle, col)
            assert derived.base.shape == base_bundle.base.shape
            assert derived.signal_col.shape == (n,)
            np.testing.assert_array_equal(derived.base, base_bundle.base)
            np.testing.assert_array_equal(derived.target, base_bundle.target)
