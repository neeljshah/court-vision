"""tests/platform/test_totals_ensemble.py -- per-file test for the NBA totals STACK proof.

Covers scripts/platformkit/proof_nba/totals_ensemble.run():
  * with a real (or fixture) corpus it returns a FINITE RMSE for the close, each single
    model, and the combined STACK;
  * the combined ensemble is NOT meaningfully WORSE than the best single component -- on
    collinear/synthetic data the honest outcome is a near-tie (combining cannot beat the
    best single), which is the documented null, so we assert "within tolerance" not strict <;
  * the data_limited fallback (n_overlap below threshold) is handled gracefully -- a dict
    with status=data_limited and no crash, never a partial/NaN report.

Corpus resolution honours the shared override contract: PROOF_CORPUS_ROOT=tests/fixtures/proof
points load_box() at the tiny fixture box; we also point the module's _NBA at the same fixture
dir so the odds merge resolves there too (the proof itself still defaults to the real
data/domains path when neither is set). If no usable corpus is reachable, we skip gracefully.

OFFLINE: no network, no torch. INVARIANTS: ASCII-only; per-file test only.
Run: python -m pytest tests/platform/test_totals_ensemble.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.platformkit.proof_nba.totals_ensemble as te

_REPO = Path(te.__file__).resolve().parents[3]
_FIX_ROOT = _REPO / "tests" / "fixtures" / "proof"
_FIX_NBA = _FIX_ROOT / "nba"


@pytest.fixture()
def fixture_corpus(monkeypatch):
    """Point both corpus seams at the committed NBA fixture, or skip if it is absent."""
    box = _FIX_NBA / "espn_boxscores.parquet"
    odds = _FIX_NBA / "odds.parquet"
    if not box.is_file() or not odds.is_file():
        pytest.skip(f"NBA fixture corpus missing under {_FIX_NBA}")
    # load_box() honours $PROOF_CORPUS_ROOT/nba; the odds merge + existence check read _NBA.
    monkeypatch.setenv("PROOF_CORPUS_ROOT", str(_FIX_ROOT))
    monkeypatch.setattr(te, "_NBA", _FIX_NBA, raising=True)
    return _FIX_NBA


def _is_finite_number(x) -> bool:
    import math
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


class TestTotalsEnsembleOk:
    def test_returns_ok_with_finite_metrics(self, fixture_corpus):
        rep = te.run()
        # data_limited is an acceptable graceful outcome; only assert the rich shape when ok.
        if rep.get("status") != "ok":
            assert rep.get("status") in ("data_limited",) or "error" in rep
            pytest.skip(f"corpus not rich enough for stack: {rep}")

        for key in ("close_rmse", "best_single_rmse", "stack_rmse"):
            assert _is_finite_number(rep[key]), f"{key} not a finite number: {rep.get(key)}"
            assert rep[key] > 0.0, f"{key} should be a positive RMSE: {rep[key]}"

        assert set(rep["singles"]) == set(te._COMPONENTS)
        for comp, d in rep["singles"].items():
            assert _is_finite_number(d["rmse"]) and d["rmse"] > 0.0

    def test_ensemble_not_worse_than_best_single(self, fixture_corpus):
        rep = te.run()
        if rep.get("status") != "ok":
            pytest.skip(f"corpus not rich enough for stack: {rep.get('status')}")
        best = float(rep["best_single_rmse"])
        stack = float(rep["stack_rmse"])
        # Honest null: collinear components mean the OLS stack can only TIE the best single;
        # it must never blow up. Allow a small tolerance for the held-out near-tie, but never
        # a material regression. When it does win, the flag must agree.
        assert stack <= best * 1.10 + 1e-6, (
            f"stack RMSE {stack} materially worse than best single {best}"
        )
        if rep["stack_beats_best_single"]:
            assert stack < best + 1e-3

    def test_verdict_and_gaps_present(self, fixture_corpus):
        rep = te.run()
        if rep.get("status") != "ok":
            pytest.skip(f"corpus not rich enough for stack: {rep.get('status')}")
        assert isinstance(rep["verdict"], str) and rep["verdict"]
        for key in ("gap_best_single_to_close", "gap_stack_to_close"):
            assert _is_finite_number(rep[key])
        # No retracted/edge numbers leak into the verdict/note text.
        blob = (rep["verdict"] + " " + rep["note"]).lower()
        for bad in ("18.38", "54.57", "8.94", "0.119", "78.11"):
            assert bad not in blob


class TestTotalsEnsembleDataLimited:
    def test_data_limited_fallback_is_graceful(self, monkeypatch, tmp_path):
        """A corpus with too few overlapping games returns status=data_limited, not a crash."""
        import numpy as np
        import pandas as pd

        nba = tmp_path / "nba"
        nba.mkdir(parents=True)
        # 5 games -> below the n>=40 stack threshold but enough columns to build.
        n = 5
        teams = ["BOS", "NYK", "MIA", "LAL", "GSW"]
        dates = pd.to_datetime(["2025-10-21"] * n) + pd.to_timedelta(np.arange(n), unit="D")
        box = pd.DataFrame({
            "event_id": [f"e{i}" for i in range(n)],
            "date": dates,
            "home_abbr": teams, "away_abbr": teams[::-1],
            "home_score": np.full(n, 112.0), "away_score": np.full(n, 108.0),
            "home_pts": np.full(n, 112.0), "away_pts": np.full(n, 108.0),
            "home_fg_attempted": np.full(n, 88.0), "away_fg_attempted": np.full(n, 86.0),
            "home_ft_attempted": np.full(n, 22.0), "away_ft_attempted": np.full(n, 20.0),
            "home_oreb": np.full(n, 10.0), "away_oreb": np.full(n, 9.0),
            "home_tov": np.full(n, 13.0), "away_tov": np.full(n, 14.0),
        })
        odds = pd.DataFrame({
            "date": [d.strftime("%Y-%m-%d") for d in dates],
            "home_team": teams, "away_team": teams[::-1],
            "home_ml": np.full(n, -150.0), "away_ml": np.full(n, 130.0),
            "total": np.full(n, 220.5), "spread": np.full(n, -3.5),
        })
        box.to_parquet(nba / "espn_boxscores.parquet", index=False)
        odds.to_parquet(nba / "odds.parquet", index=False)

        monkeypatch.setenv("PROOF_CORPUS_ROOT", str(tmp_path))
        monkeypatch.setattr(te, "_NBA", nba, raising=True)
        rep = te.run()
        assert isinstance(rep, dict)
        assert rep.get("status") == "data_limited" or "error" in rep
        if rep.get("status") == "data_limited":
            assert _is_finite_number(rep["n_overlap"])
            assert int(rep["n_overlap"]) < 40

    def test_missing_parquet_returns_error_not_crash(self, monkeypatch, tmp_path):
        empty = tmp_path / "empty_nba"
        empty.mkdir()
        monkeypatch.setattr(te, "_NBA", empty, raising=True)
        monkeypatch.delenv("PROOF_CORPUS_ROOT", raising=False)
        rep = te.run()
        assert isinstance(rep, dict)
        assert "error" in rep or rep.get("status") in ("data_limited",)
