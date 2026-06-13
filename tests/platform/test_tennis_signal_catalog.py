"""tests/platform/test_tennis_signal_catalog.py — Offline tests for the tennis signal catalog.

Synthetic in-memory data only (no network, no XGBoost on full corpus). Verifies:
  1. CATALOG_SIGNALS structure (name/target/hypothesis/docstring contracts).
  2. run_catalog() return schema and valid verdicts.
  3. Report writing (out_path creates a non-empty markdown file).
  4. F5 compliance (no banned imports in signal_catalog.py).
  5. _compute_signal_col / _derive_bundle isolation.

Run:
    python -m pytest tests/platform/test_tennis_signal_catalog.py -q --timeout=120
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
CATALOG_FILE = REPO_ROOT / "domains" / "tennis" / "signal_catalog.py"

VALID_VERDICTS: Set[str] = {"SHIP", "DEFER", "REJECT", "VARIANCE_ONLY", "BUNDLE_ERROR", "GATE_ERROR"}


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
            "p1_id": int(p1), "p2_id": int(p2),
            "winner": int(rng.integers(1, 3)),
            "surface": ["Hard", "Clay", "Grass"][i % 3],
            "score": "6-4 6-3", "round": ["R64", "R32", "QF", "SF", "F"][i % 5],
            "match_num": i, "best_of": 5 if i % 8 == 0 else 3, "tour": "atp",
            "season": d.year, "event_id": f"{d}-T{i % 10:03d}-{p1}-{p2}",
            "retirement": False,
        })
    return pd.DataFrame(rows)


def _make_odds(matches_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for _, row in matches_df.iterrows():
        p1_true = rng.uniform(0.35, 0.65)
        vig = 1.04
        ps_p1, ps_p2 = round(vig / p1_true, 2), round(vig / (1.0 - p1_true), 2)
        w = int(row["winner"])
        rows.append({
            "event_id": row["event_id"],
            "ps_p1": ps_p1, "ps_p2": ps_p2,
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
def matches_df() -> pd.DataFrame:
    return _make_matches(300)


@pytest.fixture(scope="module")
def odds_df(matches_df: pd.DataFrame) -> pd.DataFrame:
    return _make_odds(matches_df)


@pytest.fixture(scope="module")
def adapter(matches_df: pd.DataFrame, odds_df: pd.DataFrame):
    from domains.tennis.adapter import TennisAdapter
    return TennisAdapter(matches_df=matches_df, odds_df=odds_df)


@pytest.fixture(scope="module")
def catalog_result(adapter):
    """run_catalog on 2022-2023 only — module-scoped."""
    from domains.tennis.signal_catalog import run_catalog
    return run_catalog(adapter, seasons=[2022, 2023])


# ---------------------------------------------------------------------------
# 1. Catalog structure
# ---------------------------------------------------------------------------

class TestCatalogStructure:
    def test_catalog_signals_is_tuple(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        assert isinstance(CATALOG_SIGNALS, tuple), "CATALOG_SIGNALS must be a tuple"

    def test_catalog_signals_non_empty(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        assert len(CATALOG_SIGNALS) >= 5, f"Expected ≥5 entries; got {len(CATALOG_SIGNALS)}"

    def test_each_signal_has_name(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            assert hasattr(cls, "name") and isinstance(cls.name, str)
            assert cls.name.startswith("tennis_"), f"{cls.name} should start with 'tennis_'"

    def test_each_signal_target_winprob(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            assert cls().target == "winprob", f"{cls.name}.target must be 'winprob'"

    def test_each_signal_hypothesis_expected_reject(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            hyp = cls().hypothesis()
            assert hyp.expected_verdict is not None
            assert "REJECT" in hyp.expected_verdict.upper(), (
                f"{cls.name}.expected_verdict must contain 'REJECT'; got '{hyp.expected_verdict}'"
            )

    def test_each_signal_docstring_has_expected_verdict(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            doc = cls.__doc__ or ""
            assert "Expected gate verdict:" in doc, f"{cls.__name__} docstring missing 'Expected gate verdict:'"
            assert "REJECT" in doc, f"{cls.__name__} docstring missing 'REJECT'"

    def test_names_are_unique(self) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        names = [cls.name for cls in CATALOG_SIGNALS]
        assert len(names) == len(set(names)), f"Duplicate signal names: {names}"


# ---------------------------------------------------------------------------
# 2. run_catalog return schema
# ---------------------------------------------------------------------------

class TestRunCatalogSchema:
    def test_returns_dict(self, catalog_result) -> None:
        assert isinstance(catalog_result, dict)

    def test_has_ok_key(self, catalog_result) -> None:
        assert "ok" in catalog_result and isinstance(catalog_result["ok"], bool)

    def test_has_verdicts_key(self, catalog_result) -> None:
        assert "verdicts" in catalog_result and isinstance(catalog_result["verdicts"], list)

    def test_verdicts_length_matches_catalog(self, catalog_result) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS
        assert len(catalog_result["verdicts"]) == len(CATALOG_SIGNALS)

    def test_each_verdict_has_required_fields(self, catalog_result) -> None:
        required = {"name", "expected", "actual_verdict", "passed_expected", "n", "coverage"}
        for row in catalog_result["verdicts"]:
            missing = required - set(row.keys())
            assert not missing, f"Verdict row missing fields: {missing}"

    def test_actual_verdict_is_valid(self, catalog_result) -> None:
        for row in catalog_result["verdicts"]:
            assert row["actual_verdict"] in VALID_VERDICTS, (
                f"actual_verdict '{row['actual_verdict']}' not in {VALID_VERDICTS}"
            )

    def test_no_exception_raised(self, adapter) -> None:
        from domains.tennis.signal_catalog import run_catalog
        result = run_catalog(adapter, seasons=[2022])
        assert isinstance(result, dict) and "verdicts" in result


# ---------------------------------------------------------------------------
# 3. Report writing
# ---------------------------------------------------------------------------

class TestReportWriting:
    def test_report_is_written(self, adapter, tmp_path) -> None:
        from domains.tennis.signal_catalog import run_catalog
        out = tmp_path / "catalog_report.md"
        run_catalog(adapter, seasons=[2022, 2023], out_path=out)
        assert out.exists() and len(out.read_text(encoding="utf-8")) > 100

    def test_report_contains_required_header(self, adapter, tmp_path) -> None:
        from domains.tennis.signal_catalog import run_catalog
        out = tmp_path / "catalog_report2.md"
        run_catalog(adapter, seasons=[2022, 2023], out_path=out)
        content = out.read_text(encoding="utf-8")
        assert "Honest signal catalog" in content and "NO edge claimed" in content

    def test_report_contains_verdict_table(self, adapter, tmp_path) -> None:
        from domains.tennis.signal_catalog import run_catalog
        out = tmp_path / "catalog_report3.md"
        run_catalog(adapter, seasons=[2022, 2023], out_path=out)
        assert "| Signal |" in out.read_text(encoding="utf-8")

    def test_no_report_without_out_path(self, adapter) -> None:
        from domains.tennis.signal_catalog import run_catalog
        result = run_catalog(adapter, seasons=[2022], out_path=None)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 4. F5 compliance
# ---------------------------------------------------------------------------

_BANNED_PREFIXES = (
    "domains.nba", "src.data", "src.sim", "src.tracking", "src.pipeline",
    "basketball_nba", "domains.mlb", "domains.soccer",
)


def _collect_imports(source: str) -> List[str]:
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


class TestF5Compliance:
    def test_no_banned_imports_in_signal_catalog(self) -> None:
        imports = _collect_imports(CATALOG_FILE.read_text(encoding="utf-8"))
        violations = [i for i in imports if any(i == b or i.startswith(b + ".") for b in _BANNED_PREFIXES)]
        assert not violations, f"signal_catalog.py contains F5-banned imports: {violations}"

    def test_kernel_seam_imports_present(self) -> None:
        imports = _collect_imports(CATALOG_FILE.read_text(encoding="utf-8"))
        assert any(i.startswith("src.loop") for i in imports), "must import from src.loop"

    def test_file_exists(self) -> None:
        assert CATALOG_FILE.exists(), f"signal_catalog.py not found at {CATALOG_FILE}"


# ---------------------------------------------------------------------------
# 5. derive_bundle isolation
# ---------------------------------------------------------------------------

class TestDerivBundle:
    def test_derive_bundle_produces_correct_shape(self, adapter) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS, _compute_signal_col, _derive_bundle
        from src.loop.signal import Hypothesis
        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        base_bundle = adapter.feature_bundle(hyp, seasons=[2022])
        n = base_bundle.base.shape[0]
        for cls in CATALOG_SIGNALS:
            sig_col = _compute_signal_col(cls, base_bundle.base)
            assert sig_col.shape == (n,), f"{cls.name}: shape {sig_col.shape} != ({n},)"
            derived = _derive_bundle(base_bundle, sig_col)
            assert derived.base.shape == base_bundle.base.shape
            assert derived.signal_col.shape == (n,)
            assert derived.target.shape == (n,)

    def test_derive_bundle_preserves_base(self, adapter) -> None:
        from domains.tennis.signal_catalog import CATALOG_SIGNALS, _compute_signal_col, _derive_bundle
        from src.loop.signal import Hypothesis
        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        base_bundle = adapter.feature_bundle(hyp, seasons=[2022])
        sig_col = _compute_signal_col(CATALOG_SIGNALS[0], base_bundle.base)
        derived = _derive_bundle(base_bundle, sig_col)
        np.testing.assert_array_equal(derived.base, base_bundle.base)
        np.testing.assert_array_equal(derived.target, base_bundle.target)
        assert derived.dates == base_bundle.dates

    def test_abs_rest_diff_is_non_negative(self, adapter) -> None:
        from domains.tennis.signal_catalog import AbsRestDiffSignal, _compute_signal_col
        from src.loop.signal import Hypothesis
        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        base_bundle = adapter.feature_bundle(hyp, seasons=[2022])
        sig_col = _compute_signal_col(AbsRestDiffSignal, base_bundle.base)
        assert np.all(sig_col >= 0), "|rest_diff| must be non-negative"

    def test_best_of_5_is_binary(self, adapter) -> None:
        from domains.tennis.signal_catalog import BestOf5Signal, _compute_signal_col
        from src.loop.signal import Hypothesis
        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        base_bundle = adapter.feature_bundle(hyp, seasons=[2022])
        sig_col = _compute_signal_col(BestOf5Signal, base_bundle.base)
        unique = set(np.unique(sig_col))
        assert unique.issubset({0.0, 1.0}), f"BestOf5 must be binary; got {unique}"
