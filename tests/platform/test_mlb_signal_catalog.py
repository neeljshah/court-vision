"""tests/platform/test_mlb_signal_catalog.py — Offline tests for the MLB signal catalog.

Synthetic in-memory data only. Verifies: catalog structure, run_catalog schema,
report writing, F5 compliance, _compute_signal_col/_derive_bundle, league_filter.

Run:
    python -m pytest tests/platform/test_mlb_signal_catalog.py -q --timeout=120
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
CATALOG_FILE = REPO_ROOT / "domains" / "mlb" / "signal_catalog.py"
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

    def add(date: str, home: str, away: str, season: int, hr: int, ar: int,
            league: str = "NL") -> None:
        rows.append({
            "event_id": f"{date}-{home}-{away}", "date": date, "season": season,
            "home_team": home, "away_team": away, "home_runs": hr, "away_runs": ar,
            "target_home_win": 1 if hr > ar else 0, "game_seq": 1, "home_league": league,
        })

    for s in range(n_seasons):
        year = 2015 + s
        for mi, month in enumerate(["04", "05", "06", "07", "08"]):
            for i, (h, a) in enumerate(zip(teams_nl, teams_nl[1:] + [teams_nl[0]])):
                add(f"{year}-{month}-{(i*5+1):02d}", h, a, year,
                    int(rng.integers(1, 8)), int(rng.integers(1, 8)), "NL")
            for i, (h, a) in enumerate(zip(teams_al, teams_al[1:] + [teams_al[0]])):
                add(f"{year}-{month}-{(i*5+2):02d}", h, a, year,
                    int(rng.integers(1, 8)), int(rng.integers(1, 8)), "AL")
    return pd.DataFrame(rows)


def _make_odds_df(games_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for _, g in games_df.iterrows():
        ho = round(float(rng.uniform(1.7, 2.4)), 2)
        ao = round(float(rng.uniform(1.7, 2.4)), 2)
        rows.append({
            "event_id": g["event_id"], "date": g["date"], "season": g["season"],
            "dec_open_home": ho, "dec_open_away": ao,
            "dec_close_home": max(1.01, round(ho + float(rng.uniform(-0.1, 0.1)), 2)),
            "dec_close_away": max(1.01, round(ao + float(rng.uniform(-0.1, 0.1)), 2)),
            "book": "sbro_archive",
        })
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
    from domains.mlb.signal_catalog import run_catalog
    return run_catalog(adapter, seasons=[2015, 2016])


# ---------------------------------------------------------------------------
# 1. Catalog structure
# ---------------------------------------------------------------------------

class TestCatalogStructure:
    def test_catalog_signals_is_tuple(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        assert isinstance(CATALOG_SIGNALS, tuple)

    def test_at_least_5_signals(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        assert len(CATALOG_SIGNALS) >= 5

    def test_names_start_with_mlb(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            assert cls.name.startswith("mlb_"), f"{cls.name} must start with 'mlb_'"

    def test_target_winprob(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            assert cls().target == "winprob"

    def test_expected_verdict_contains_reject(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            ev = cls().hypothesis().expected_verdict or ""
            assert "REJECT" in ev.upper(), f"{cls.name} expected_verdict missing REJECT"

    def test_docstring_has_expected_verdict(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        for cls in CATALOG_SIGNALS:
            doc = cls.__doc__ or ""
            assert "Expected gate verdict:" in doc and "REJECT" in doc

    def test_names_unique(self) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        names = [cls.name for cls in CATALOG_SIGNALS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# 2. run_catalog return schema
# ---------------------------------------------------------------------------

class TestRunCatalogSchema:
    def test_returns_dict_with_ok_and_verdicts(self, catalog_result) -> None:
        assert isinstance(catalog_result, dict)
        assert "ok" in catalog_result and isinstance(catalog_result["ok"], bool)
        assert "verdicts" in catalog_result and isinstance(catalog_result["verdicts"], list)

    def test_verdicts_length_matches_catalog(self, catalog_result) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS
        assert len(catalog_result["verdicts"]) == len(CATALOG_SIGNALS)

    def test_each_verdict_has_required_fields(self, catalog_result) -> None:
        required = {"name", "expected", "actual_verdict", "passed_expected", "n", "coverage"}
        for row in catalog_result["verdicts"]:
            assert not (required - set(row.keys()))

    def test_actual_verdict_is_valid(self, catalog_result) -> None:
        for row in catalog_result["verdicts"]:
            assert row["actual_verdict"] in VALID_VERDICTS

    def test_league_filter_forwarded(self, adapter) -> None:
        from domains.mlb.signal_catalog import run_catalog
        r = run_catalog(adapter, seasons=[2015, 2016], league_filter="NL")
        assert isinstance(r, dict) and "verdicts" in r


# ---------------------------------------------------------------------------
# 3. Report writing
# ---------------------------------------------------------------------------

class TestReportWriting:
    def test_report_written_and_non_empty(self, adapter, tmp_path) -> None:
        from domains.mlb.signal_catalog import run_catalog
        out = tmp_path / "mlb_catalog.md"
        run_catalog(adapter, seasons=[2015, 2016], out_path=out)
        assert out.exists() and len(out.read_text(encoding="utf-8")) > 100

    def test_report_header_present(self, adapter, tmp_path) -> None:
        from domains.mlb.signal_catalog import run_catalog
        out = tmp_path / "mlb_catalog2.md"
        run_catalog(adapter, seasons=[2015, 2016], out_path=out)
        content = out.read_text(encoding="utf-8")
        assert "Honest signal catalog" in content and "NO edge claimed" in content

    def test_report_verdict_table_present(self, adapter, tmp_path) -> None:
        from domains.mlb.signal_catalog import run_catalog
        out = tmp_path / "mlb_catalog3.md"
        run_catalog(adapter, seasons=[2015, 2016], out_path=out)
        assert "| Signal |" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 4. F5 compliance
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 5. _compute_signal_col / _derive_bundle isolation
# ---------------------------------------------------------------------------

class TestDerivBundle:
    def _bundle(self, adapter):
        from src.loop.signal import Hypothesis
        hyp = Hypothesis(name="x", target="winprob", scope="pregame", statement="x")
        return adapter.feature_bundle(hyp, seasons=[2015])

    def test_compute_signal_col_shape(self, adapter) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS, _compute_signal_col
        bb = self._bundle(adapter)
        n = bb.base.shape[0]
        for cls in CATALOG_SIGNALS:
            sc = _compute_signal_col(cls, bb.base)
            assert sc.shape == (n,), f"{cls.name}: shape {sc.shape} != ({n},)"

    def test_derive_bundle_preserves_base(self, adapter) -> None:
        from domains.mlb.signal_catalog import CATALOG_SIGNALS, _compute_signal_col, _derive_bundle
        bb = self._bundle(adapter)
        sc = _compute_signal_col(CATALOG_SIGNALS[0], bb.base)
        derived = _derive_bundle(bb, sc)
        np.testing.assert_array_equal(derived.base, bb.base)
        np.testing.assert_array_equal(derived.target, bb.target)
        assert derived.dates == bb.dates

    def test_abs_rest_diff_non_negative(self, adapter) -> None:
        from domains.mlb.signal_catalog import AbsRestDiffSignal, _compute_signal_col
        bb = self._bundle(adapter)
        assert np.all(_compute_signal_col(AbsRestDiffSignal, bb.base) >= 0)

    def test_elo_mismatch_magnitude_non_negative(self, adapter) -> None:
        from domains.mlb.signal_catalog import EloMismatchMagnitudeSignal, _compute_signal_col
        bb = self._bundle(adapter)
        assert np.all(_compute_signal_col(EloMismatchMagnitudeSignal, bb.base) >= 0)

    def test_h2h_residual_range(self, adapter) -> None:
        from domains.mlb.signal_catalog import H2HResidualSignal, _compute_signal_col
        bb = self._bundle(adapter)
        sc = _compute_signal_col(H2HResidualSignal, bb.base)
        assert np.all(sc >= -0.5) and np.all(sc <= 0.5)
