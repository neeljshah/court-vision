"""tests/platform/test_mlb_signal_catalog_joint.py — Offline tests for the MLB joint catalog.

Synthetic in-memory data only. Verifies: catalog structure, run_catalog schema,
report writing, F5 compliance, _compute_signal_col/_derive_bundle, league_filter.
Run: python -m pytest tests/platform/test_mlb_signal_catalog_joint.py -q --timeout=120
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPO_ROOT / "domains" / "mlb" / "signal_catalog_joint.py"
VALID_VERDICTS: Set[str] = {"SHIP", "DEFER", "REJECT", "VARIANCE_ONLY", "BUNDLE_ERROR", "GATE_ERROR"}
_BANNED_PREFIXES = (
    "domains.nba", "domains.basketball_nba", "domains.tennis", "domains.soccer",
    "src.data", "src.sim", "src.tracking", "src.pipeline",
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_games_df(n_seasons: int = 3) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(42)
    teams_nl = ["NYM", "ATL", "CHC", "LAD", "STL"]
    teams_al = ["NYY", "BOS", "SEA", "HOU", "DET"]
    for s in range(n_seasons):
        year = 2015 + s
        for mi, month in enumerate(["04", "05", "06", "07", "08"]):
            for i, (h, a) in enumerate(zip(teams_nl, teams_nl[1:] + [teams_nl[0]])):
                hr, ar = int(rng.integers(1, 8)), int(rng.integers(1, 8))
                rows.append({"event_id": f"{year}-{month}-{(i*5+1):02d}-{h}-{a}",
                    "date": f"{year}-{month}-{(i*5+1):02d}", "season": year,
                    "home_team": h, "away_team": a, "home_runs": hr, "away_runs": ar,
                    "target_home_win": 1 if hr > ar else 0, "game_seq": 1, "home_league": "NL"})
            for i, (h, a) in enumerate(zip(teams_al, teams_al[1:] + [teams_al[0]])):
                hr, ar = int(rng.integers(1, 8)), int(rng.integers(1, 8))
                rows.append({"event_id": f"{year}-{month}-{(i*5+2):02d}-{h}-{a}",
                    "date": f"{year}-{month}-{(i*5+2):02d}", "season": year,
                    "home_team": h, "away_team": a, "home_runs": hr, "away_runs": ar,
                    "target_home_win": 1 if hr > ar else 0, "game_seq": 1, "home_league": "AL"})
    return pd.DataFrame(rows)


def _make_odds_df(games_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for _, g in games_df.iterrows():
        ho = round(float(rng.uniform(1.7, 2.4)), 2)
        ao = round(float(rng.uniform(1.7, 2.4)), 2)
        rows.append({"event_id": g["event_id"], "date": g["date"], "season": g["season"],
            "dec_open_home": ho, "dec_open_away": ao,
            "dec_close_home": max(1.01, round(ho + float(rng.uniform(-0.1, 0.1)), 2)),
            "dec_close_away": max(1.01, round(ao + float(rng.uniform(-0.1, 0.1)), 2)),
            "book": "sbro_archive"})
    return pd.DataFrame(rows)


def _collect_imports(source: str) -> List[str]:
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def games_df() -> pd.DataFrame:
    return _make_games_df(n_seasons=3)

@pytest.fixture(scope="module")
def odds_df(games_df: pd.DataFrame) -> pd.DataFrame:
    return _make_odds_df(games_df)

@pytest.fixture(scope="module")
def adapter(games_df, odds_df):
    from domains.mlb.adapter import MLBAdapter
    return MLBAdapter(games_df=games_df, odds_df=odds_df)

@pytest.fixture(scope="module")
def catalog_result(adapter):
    from domains.mlb.signal_catalog_joint import run_catalog
    return run_catalog(adapter, seasons=[2015, 2016])

@pytest.fixture(scope="module")
def report_content(adapter, tmp_path_factory):
    """Single report written once; all TestReportWriting tests share it."""
    from domains.mlb.signal_catalog_joint import run_catalog
    out = tmp_path_factory.mktemp("rpt") / "mlb_joint_catalog.md"
    run_catalog(adapter, seasons=[2015, 2016], out_path=out)
    return out.read_text(encoding="utf-8")

# -- 1. Catalog structure ----------------------------------------------------
class TestCatalogStructure:
    def test_catalog_signals_is_tuple(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        assert isinstance(CATALOG_SIGNALS, tuple)

    def test_at_least_5_signals(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        assert len(CATALOG_SIGNALS) >= 5

    def test_names_start_with_mlb_joint(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            assert cls.name.startswith("mlb_joint_"), f"{cls.name} must start with 'mlb_joint_'"

    def test_target_winprob(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            assert cls().target == "winprob"

    def test_expected_verdict_contains_reject(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            ev = cls().hypothesis().expected_verdict or ""
            assert "REJECT" in ev.upper(), f"{cls.name} expected_verdict missing REJECT"

    def test_docstring_has_expected_verdict(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            doc = cls.__doc__ or ""
            assert "Expected gate verdict:" in doc and "REJECT" in doc

    def test_names_unique(self) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        names = [cls.name for cls in CATALOG_SIGNALS]
        assert len(names) == len(set(names))

    def test_each_signal_uses_at_least_two_base_cols(self) -> None:
        """Verify each signal's _compute_signal_col actually uses >=2 columns."""
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS, _compute_signal_col
        rng = np.random.default_rng(0)
        base = rng.uniform(1400, 1600, size=(50, 6)).astype(float)
        base[:, 5] = rng.uniform(0.3, 0.7, size=50)
        for cls in CATALOG_SIGNALS:
            ref = _compute_signal_col(cls, base)
            changed = 0
            for col in range(6):
                b2 = base.copy(); b2[:, col] = 0.0
                if not np.allclose(ref, _compute_signal_col(cls, b2), equal_nan=True):
                    changed += 1
            assert changed >= 2, f"{cls.name}: only {changed} cols affect output — need >=2"


# -- 2. run_catalog return schema --------------------------------------------
class TestRunCatalogSchema:
    def test_returns_dict_with_ok_and_verdicts(self, catalog_result) -> None:
        assert isinstance(catalog_result, dict)
        assert "ok" in catalog_result and isinstance(catalog_result["ok"], bool)
        assert "verdicts" in catalog_result and isinstance(catalog_result["verdicts"], list)

    def test_verdicts_length_matches_catalog(self, catalog_result) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS
        assert len(catalog_result["verdicts"]) == len(CATALOG_SIGNALS)

    def test_each_verdict_has_required_fields(self, catalog_result) -> None:
        required = {"name", "expected", "actual_verdict", "passed_expected", "n", "coverage"}
        for row in catalog_result["verdicts"]:
            assert not (required - set(row.keys()))

    def test_actual_verdict_is_valid(self, catalog_result) -> None:
        for row in catalog_result["verdicts"]:
            assert row["actual_verdict"] in VALID_VERDICTS

    def test_league_filter_forwarded(self, adapter) -> None:
        from domains.mlb.signal_catalog_joint import run_catalog
        r = run_catalog(adapter, seasons=[2015, 2016], league_filter="NL")
        assert isinstance(r, dict) and "verdicts" in r

    def test_all_names_in_verdicts_start_with_mlb_joint(self, catalog_result) -> None:
        for row in catalog_result["verdicts"]:
            assert row["name"].startswith("mlb_joint_"), (
                f"verdict name '{row['name']}' must start with 'mlb_joint_'"
            )


# -- 3. Report writing -------------------------------------------------------

class TestReportWriting:
    def test_report_non_empty(self, report_content) -> None:
        assert len(report_content) > 100

    def test_report_header_present(self, report_content) -> None:
        assert "Honest joint" in report_content and "NO edge claimed" in report_content

    def test_report_verdict_table_present(self, report_content) -> None:
        assert "| Signal |" in report_content

    def test_report_joint_contract_note(self, report_content) -> None:
        assert "algebraic interactions" in report_content or "joint" in report_content.lower()


# -- 4. F5 compliance --------------------------------------------------------
class TestF5Compliance:
    def test_no_banned_imports(self) -> None:
        imports = _collect_imports(CATALOG_FILE.read_text(encoding="utf-8"))
        violations = [i for i in imports
                      if any(i == b or i.startswith(b + ".") for b in _BANNED_PREFIXES)]
        assert not violations, f"F5-banned imports: {violations}"

    def test_src_loop_import_present(self) -> None:
        imports = _collect_imports(CATALOG_FILE.read_text(encoding="utf-8"))
        assert any(i.startswith("src.loop") for i in imports)

    def test_file_exists(self) -> None:
        assert CATALOG_FILE.exists()

# -- 5. _compute_signal_col / _derive_bundle isolation -----------------------
class TestDerivBundle:
    def _bundle(self, adapter):
        from src.loop.signal import Hypothesis
        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        return adapter.feature_bundle(hyp, seasons=[2015])

    def test_compute_signal_col_shape(self, adapter) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS, _compute_signal_col
        bb = self._bundle(adapter)
        n = bb.base.shape[0]
        for cls in CATALOG_SIGNALS:
            sc = _compute_signal_col(cls, bb.base)
            assert sc.shape == (n,), f"{cls.name}: shape {sc.shape} != ({n},)"

    def test_compute_signal_col_finite(self, adapter) -> None:
        """All joint signals must produce finite output on well-formed base data."""
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS, _compute_signal_col
        bb = self._bundle(adapter)
        for cls in CATALOG_SIGNALS:
            sc = _compute_signal_col(cls, bb.base)
            assert np.all(np.isfinite(sc)), f"{cls.name}: non-finite values in signal_col"

    def test_derive_bundle_preserves_base(self, adapter) -> None:
        from domains.mlb.signal_catalog_joint import CATALOG_SIGNALS, _compute_signal_col, _derive_bundle
        bb = self._bundle(adapter)
        sc = _compute_signal_col(CATALOG_SIGNALS[0], bb.base)
        derived = _derive_bundle(bb, sc)
        np.testing.assert_array_equal(derived.base, bb.base)
        np.testing.assert_array_equal(derived.target, bb.target)
        assert derived.dates == bb.dates

    def test_abs_rest_elo_non_negative(self, adapter) -> None:
        from domains.mlb.signal_catalog_joint import AbsRestDiffXEloDiffSignal, _compute_signal_col
        bb = self._bundle(adapter)
        assert np.all(_compute_signal_col(AbsRestDiffXEloDiffSignal, bb.base) >= 0)

    def test_elo_closeness_sq_h2h_range(self, adapter) -> None:
        """(1/(1+d²)) * h2h ∈ (0, 1] for positive elo values and h2h ∈ [0,1]."""
        from domains.mlb.signal_catalog_joint import EloClosenessSqH2HSignal, _compute_signal_col
        bb = self._bundle(adapter)
        sc = _compute_signal_col(EloClosenessSqH2HSignal, bb.base)
        assert np.all(sc >= 0) and np.all(sc <= 1.0 + 1e-9)

    def test_elo_h2h_product_varies_with_h2h(self, adapter) -> None:
        """EloH2HProduct must actually depend on the h2h column (col 5)."""
        from domains.mlb.signal_catalog_joint import EloH2HProductSignal, _compute_signal_col
        bb = self._bundle(adapter)
        base_alt = bb.base.copy()
        base_alt[:, 5] = 0.5
        sc_orig = _compute_signal_col(EloH2HProductSignal, bb.base)
        sc_alt = _compute_signal_col(EloH2HProductSignal, base_alt)
        assert not np.allclose(sc_orig, sc_alt)

    def test_unknown_signal_returns_zeros(self) -> None:
        from domains.mlb.signal_catalog_joint import _compute_signal_col
        import types
        fake_cls = types.SimpleNamespace(name="mlb_joint_nonexistent_xyz")
        rng = np.random.default_rng(1)
        base = rng.uniform(1400, 1600, size=(20, 6))
        sc = _compute_signal_col(fake_cls, base)  # type: ignore[arg-type]
        assert np.all(sc == 0.0)
