"""tests/platform/test_nba_signal_catalog.py — Offline tests for the NBA signal catalogs.

Synthetic in-memory data only. Verifies: catalog structure, run_catalog schema,
report writing, F5 compliance, _compute_signal_col/_derive_bundle isolation.
One optional slow real-gate smoke (mark slow; skip by default).

Run fast tests:
    python -m pytest tests/platform/test_nba_signal_catalog.py -q --timeout=120
Run slow gate smoke (minutes):
    python -m pytest tests/platform/test_nba_signal_catalog.py -q --timeout=600 -m slow
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from typing import List, Set

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_FILE = REPO_ROOT / "domains" / "basketball_nba" / "signal_catalog.py"
CATALOG_JOINT_FILE = REPO_ROOT / "domains" / "basketball_nba" / "signal_catalog_joint.py"
VALID_VERDICTS: Set[str] = {"SHIP", "DEFER", "REJECT", "VARIANCE_ONLY", "BUNDLE_ERROR", "GATE_ERROR"}
_BANNED_PREFIXES = (
    "domains.tennis", "domains.soccer", "domains.mlb",
    "src.data", "src.sim", "src.tracking", "src.pipeline",
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_base(n: int = 200, seed: int = 42) -> np.ndarray:
    """(n,8) base matrix: elo_home, elo_away, elo_diff_hfa, rest_home, rest_away,
    home_b2b, away_b2b, rolling_win10_home (adapter contract, frozen)."""
    rng = np.random.default_rng(seed)
    elo_h = rng.uniform(1400, 1600, n)
    elo_a = rng.uniform(1400, 1600, n)
    rh = rng.choice([1, 2, 3, 4, 5, 7, 10], n).astype(float)
    ra = rng.choice([1, 2, 3, 4, 5, 7, 10], n).astype(float)
    w10 = rng.uniform(0.0, 1.0, n)
    w10[:15] = np.nan  # first 10 games no history
    return np.column_stack([
        elo_h, elo_a, (elo_h + 76.0) - elo_a,
        rh, ra, (rh == 1).astype(float), (ra == 1).astype(float), w10,
    ])

def _make_bundle(n: int = 200, seed: int = 42):
    from src.loop.gate import FeatureBundle
    rng = np.random.default_rng(seed + 1)
    base = _make_base(n, seed)
    sig = 1.0 / (1.0 + np.power(10.0, -base[:, 2] / 400.0))
    tgt = rng.integers(0, 2, n).astype(float)
    dates = [str(dt.date(2022, 1, 1) + dt.timedelta(days=i)) for i in range(n)]
    lines = rng.uniform(0.35, 0.65, n)
    return FeatureBundle(base=base, signal_col=sig, target=tgt,
                         dates=dates, lines=lines, closing=lines + rng.uniform(-0.03, 0.03, n))


class _SyntheticNBAAdapter:
    """Stub adapter returning a synthetic FeatureBundle. No corpus required."""
    def feature_bundle(self, hypothesis, seasons=None, **_kw):
        return _make_bundle(n=200, seed=42)


def _collect_imports(source: str) -> List[str]:
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adapter():
    return _SyntheticNBAAdapter()

@pytest.fixture(scope="module")
def catalog_result(adapter):
    from domains.basketball_nba.signal_catalog import run_catalog
    return run_catalog(adapter, seasons=[2022, 2023])

@pytest.fixture(scope="module")
def joint_result(adapter):
    from domains.basketball_nba.signal_catalog_joint import run_catalog as rj
    return rj(adapter, seasons=[2022, 2023])


# ---------------------------------------------------------------------------
# 1. Catalog structure
# ---------------------------------------------------------------------------

class TestCatalogStructure:
    def test_catalog_signals_tuple(self) -> None:
        from domains.basketball_nba.signal_catalog import CATALOG_SIGNALS
        assert isinstance(CATALOG_SIGNALS, tuple) and len(CATALOG_SIGNALS) >= 6

    def test_joint_catalog_signals_tuple(self) -> None:
        from domains.basketball_nba.signal_catalog_joint import CATALOG_SIGNALS
        assert isinstance(CATALOG_SIGNALS, tuple) and len(CATALOG_SIGNALS) >= 6

    def test_names_prefix(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        for cls in sc.CATALOG_SIGNALS:
            assert cls.name.startswith("nba_"), cls.name
        for cls in scj.CATALOG_SIGNALS:
            assert cls.name.startswith("nba_joint_"), cls.name

    def test_target_winprob(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        for cls in list(sc.CATALOG_SIGNALS) + list(scj.CATALOG_SIGNALS):
            assert cls().target == "winprob"

    def test_expected_verdict_reject(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        for cls in list(sc.CATALOG_SIGNALS) + list(scj.CATALOG_SIGNALS):
            ev = cls().hypothesis().expected_verdict or ""
            assert "REJECT" in ev.upper(), f"{cls.name}: missing REJECT in expected_verdict"

    def test_docstring_reject_label(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        for cls in list(sc.CATALOG_SIGNALS) + list(scj.CATALOG_SIGNALS):
            doc = cls.__doc__ or ""
            assert "Expected gate verdict:" in doc and "REJECT" in doc, cls.name

    def test_names_unique(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        for mod, cls_tuple in [("sc", sc.CATALOG_SIGNALS), ("scj", scj.CATALOG_SIGNALS)]:
            names = [c.name for c in cls_tuple]
            assert len(names) == len(set(names)), f"{mod}: duplicate names"

    def test_no_ast_signal_fabricated(self) -> None:
        """AST/box-score signals must not appear at schedule-level layer."""
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        for cls in list(sc.CATALOG_SIGNALS) + list(scj.CATALOG_SIGNALS):
            assert "ast" not in cls.name.lower(), f"{cls.name}: AST invalid at schedule level"


# ---------------------------------------------------------------------------
# 2. run_catalog return schema
# ---------------------------------------------------------------------------

class TestRunCatalogSchema:
    def test_returns_ok_and_verdicts(self, catalog_result, joint_result) -> None:
        for r in (catalog_result, joint_result):
            assert isinstance(r, dict) and "ok" in r and "verdicts" in r

    def test_verdicts_length(self, catalog_result, joint_result) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        assert len(catalog_result["verdicts"]) == len(sc.CATALOG_SIGNALS)
        assert len(joint_result["verdicts"]) == len(scj.CATALOG_SIGNALS)

    def test_verdict_fields(self, catalog_result) -> None:
        req = {"name", "expected", "actual_verdict", "passed_expected", "n", "coverage"}
        for row in catalog_result["verdicts"]:
            assert not (req - set(row.keys())), f"Missing fields: {row}"

    def test_actual_verdict_valid(self, catalog_result, joint_result) -> None:
        for r in list(catalog_result["verdicts"]) + list(joint_result["verdicts"]):
            assert r["actual_verdict"] in VALID_VERDICTS, r


# ---------------------------------------------------------------------------
# 3. Report writing
# ---------------------------------------------------------------------------

class TestReportWriting:
    def test_report_written(self, adapter, tmp_path) -> None:
        from domains.basketball_nba.signal_catalog import run_catalog
        out = tmp_path / "nba_cat.md"
        run_catalog(adapter, seasons=[2022], out_path=out)
        txt = out.read_text(encoding="utf-8")
        assert len(txt) > 100 and "NO edge claimed" in txt and "| Signal |" in txt

    def test_joint_report_written(self, adapter, tmp_path) -> None:
        from domains.basketball_nba.signal_catalog_joint import run_catalog as rj
        out = tmp_path / "nba_joint_cat.md"
        rj(adapter, seasons=[2022], out_path=out)
        assert out.exists() and len(out.read_text(encoding="utf-8")) > 100


# ---------------------------------------------------------------------------
# 4. F5 compliance
# ---------------------------------------------------------------------------

class TestF5Compliance:
    def test_no_banned_imports(self) -> None:
        for fpath in (CATALOG_FILE, CATALOG_JOINT_FILE):
            imports = _collect_imports(fpath.read_text(encoding="utf-8"))
            bad = [i for i in imports if any(i == b or i.startswith(b + ".") for b in _BANNED_PREFIXES)]
            assert not bad, f"{fpath.name}: F5-banned imports: {bad}"

    def test_src_loop_present(self) -> None:
        for fpath in (CATALOG_FILE, CATALOG_JOINT_FILE):
            imports = _collect_imports(fpath.read_text(encoding="utf-8"))
            assert any(i.startswith("src.loop") for i in imports), f"{fpath.name}: missing src.loop import"

    def test_files_exist(self) -> None:
        assert CATALOG_FILE.exists() and CATALOG_JOINT_FILE.exists()


# ---------------------------------------------------------------------------
# 5. _compute_signal_col / _derive_bundle isolation
# ---------------------------------------------------------------------------

class TestSignalColIsolation:
    def _bb(self):
        return _make_bundle(200, 42)

    def test_shape(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        bb = self._bb(); n = bb.base.shape[0]
        for mod, cls_tuple in [(sc, sc.CATALOG_SIGNALS), (scj, scj.CATALOG_SIGNALS)]:
            for cls in cls_tuple:
                out = mod._compute_signal_col(cls, bb.base)
                assert out.shape == (n,), f"{cls.name}: {out.shape}"

    def test_deterministic(self) -> None:
        from domains.basketball_nba import signal_catalog as sc
        bb = self._bb()
        for cls in sc.CATALOG_SIGNALS:
            s1 = sc._compute_signal_col(cls, bb.base)
            s2 = sc._compute_signal_col(cls, bb.base)
            np.testing.assert_array_equal(s1, s2, err_msg=f"{cls.name} not deterministic")

    def test_derive_bundle_preserves_base(self) -> None:
        from domains.basketball_nba.signal_catalog import CATALOG_SIGNALS, _compute_signal_col, _derive_bundle
        bb = self._bb()
        sc = _compute_signal_col(CATALOG_SIGNALS[0], bb.base)
        d = _derive_bundle(bb, sc)
        np.testing.assert_array_equal(d.base, bb.base)
        np.testing.assert_array_equal(d.signal_col, sc)
        assert d.dates == bb.dates

    def test_abs_signals_non_negative(self) -> None:
        from domains.basketball_nba import signal_catalog as sc, signal_catalog_joint as scj
        bb = self._bb()
        for cls in (sc.AbsRestDiffSignal, sc.EloMismatchMagnitudeSignal):
            assert np.all(sc._compute_signal_col(cls, bb.base) >= 0), cls.name
        assert np.all(scj._compute_signal_col(scj.AbsRestDiffXEloMismatchSignal, bb.base) >= 0)

    def test_home_b2b_binary(self) -> None:
        from domains.basketball_nba.signal_catalog import HomeB2BIndicatorSignal, _compute_signal_col
        sc = _compute_signal_col(HomeB2BIndicatorSignal, self._bb().base)
        assert set(np.unique(sc).tolist()) <= {0.0, 1.0}

    def test_rest_bucket_capped(self) -> None:
        from domains.basketball_nba.signal_catalog import RestBucketSignal, _compute_signal_col
        assert np.all(_compute_signal_col(RestBucketSignal, self._bb().base) <= 3.0)

    def test_elo_ratio_no_nan_on_zero_elo(self) -> None:
        from domains.basketball_nba.signal_catalog_joint import EloRatioXB2BDiffSignal, _compute_signal_col
        bb = self._bb()
        base_copy = bb.base.copy(); base_copy[0, 1] = 0.0
        sc = _compute_signal_col(EloRatioXB2BDiffSignal, base_copy)
        assert not np.any(np.isnan(sc)), "NaN on zero elo_away"

    def test_base_not_mutated(self) -> None:
        from domains.basketball_nba.signal_catalog import CATALOG_SIGNALS, _compute_signal_col
        bb = self._bb(); orig = bb.base.copy()
        for cls in CATALOG_SIGNALS:
            _compute_signal_col(cls, bb.base)
        np.testing.assert_array_equal(bb.base, orig)


# ---------------------------------------------------------------------------
# 6. Slow smoke test: real gate (verdicts must be REJECT or DEFER, NOT SHIP)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestRealGateSmoke:
    """Runs the real gate on synthetic data.  Expected: all REJECT/DEFER.
    A SHIP on synthetic noise would be a probable artifact — flagged as failure."""

    def _check(self, run_fn, label: str) -> None:
        result = run_fn(_SyntheticNBAAdapter(), seasons=[2022, 2023])
        ships = [r["name"] for r in result["verdicts"] if r["actual_verdict"] == "SHIP"]
        if ships:
            pytest.fail(
                f"{label}: SHIP on synthetic noise (probable artifact, NOT edge): {ships}")
        bad = [r for r in result["verdicts"] if r["actual_verdict"] not in {"REJECT", "DEFER"}]
        assert not bad, f"{label}: unexpected verdicts: {[(r['name'], r['actual_verdict']) for r in bad]}"

    def test_single_catalog(self) -> None:
        from domains.basketball_nba.signal_catalog import run_catalog
        self._check(run_catalog, "NBA SINGLE-SIGNAL CATALOG")

    def test_joint_catalog(self) -> None:
        from domains.basketball_nba.signal_catalog_joint import run_catalog as rj
        self._check(rj, "NBA JOINT CATALOG")
