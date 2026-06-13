"""tests/platform/test_run_proof.py — Offline tests for the tennis proof runner.

OFFLINE: no network, no torch, no real parquets.  Synthetic corpus ~80 matches.
Coverage: proof_metrics correctness; V3 gate path end-to-end (GateResult shape,
verdict not asserted); run_proof graceful exit on missing corpus; F5 compliance.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.proof_tennis.proof_metrics import (
    brier, clv_sign_invariants, ece, isotonic_calibrate, reliability_slope,
)
from domains.tennis.adapter import TennisAdapter
from domains.tennis.signals import FatigueRestSignal, H2HResidualSignal, SurfaceTransitionSignal
from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import GateResult, Hypothesis, Verdict

_SIGNAL_MAP = {
    "tennis_fatigue_rest": FatigueRestSignal,
    "tennis_surface_transition": SurfaceTransitionSignal,
    "tennis_h2h_residual": H2HResidualSignal,
}


# ---------------------------------------------------------------------------
# proof_metrics unit tests
# ---------------------------------------------------------------------------

class TestBrier:
    def test_perfect(self):
        y = np.array([1.0, 0.0, 1.0, 0.0])
        assert brier(y, y) == pytest.approx(0.0, abs=1e-10)

    def test_constant_half(self):
        y = np.array([1.0, 0.0, 1.0, 0.0])
        assert brier(np.full(4, 0.5), y) == pytest.approx(0.25, abs=1e-10)

    def test_worst(self):
        assert brier(np.array([0.0, 1.0]), np.array([1.0, 0.0])) == pytest.approx(1.0)


class TestECE:
    def test_empty(self):
        assert ece(np.array([]), np.array([])) == 0.0

    def test_range(self):
        rng = np.random.default_rng(42)
        p = rng.random(200)
        val = ece(p, rng.binomial(1, p).astype(float))
        assert 0.0 <= val <= 1.0


class TestReliabilitySlope:
    def test_no_exception(self):
        rng = np.random.default_rng(7)
        p = np.tile(np.linspace(0.05, 0.95, 20), 20)
        y = np.array([rng.binomial(1, pi) for pi in p], dtype=float)
        s = reliability_slope(p, y, bins=10)
        assert s is None or isinstance(s, float)


class TestIsotonicCalibrate:
    def test_monotone_output(self):
        rng = np.random.default_rng(13)
        tp = rng.random(200)
        ty = rng.binomial(1, tp).astype(float)
        ep = np.sort(rng.random(50))
        cal = isotonic_calibrate(tp, ty, ep)
        assert np.all(np.diff(cal) >= -1e-8)

    def test_in_range(self):
        rng = np.random.default_rng(99)
        tp = rng.random(100)
        ty = rng.binomial(1, tp).astype(float)
        cal = isotonic_calibrate(tp, ty, rng.random(30))
        assert np.all(cal >= 0.0) and np.all(cal <= 1.0)


class TestCLVSignInvariants:
    def test_close_vs_itself_zero(self):
        a = np.array([1.83, 2.10, 1.65])
        b = np.array([2.05, 1.73, 2.20])
        r = clv_sign_invariants(a, b, a, b)
        assert r["inv_a_ok"] is True
        assert r["max_close_vs_itself"] < 1e-9

    def test_anti_symmetry(self):
        rng = np.random.default_rng(5)
        a = rng.uniform(1.5, 3.5, 50)
        b = rng.uniform(1.5, 3.5, 50)
        ca, cb = a * rng.uniform(0.95, 1.05, 50), b * rng.uniform(0.95, 1.05, 50)
        r = clv_sign_invariants(a, b, ca, cb)
        assert r["inv_b_ok"] is True


# ---------------------------------------------------------------------------
# Synthetic corpus builder
# ---------------------------------------------------------------------------

def _make_synthetic_corpus(tmp_path: Path, n: int = 80) -> Path:
    """Build matches.parquet + odds.parquet in tmp_path/tennis_corpus."""
    rng = np.random.default_rng(42)
    players = list(range(1001, 1009))
    surfaces = ["Hard", "Clay", "Grass"]
    years = rng.choice([2022, 2023, 2024], size=n, replace=True)
    months = rng.integers(1, 12, size=n)
    days = rng.integers(1, 28, size=n)
    dates = sorted([dt.date(int(y), int(m), int(d)).isoformat()
                    for y, m, d in zip(years, months, days)])
    p1_ids = rng.choice(players, size=n, replace=True)
    p2_ids = np.array([rng.choice([p for p in players if p != p1]) for p1 in p1_ids])
    tourney_ids = [f"t{rng.integers(1, 10)}" for _ in range(n)]
    event_ids = [f"{dates[i]}-{tourney_ids[i]}-{p1_ids[i]}-{p2_ids[i]}" for i in range(n)]
    matches_df = pd.DataFrame({
        "event_id": event_ids, "date": dates, "tourney_id": tourney_ids,
        "p1_id": p1_ids.astype(int), "p2_id": p2_ids.astype(int),
        "winner": rng.choice([1, 2], size=n, replace=True).astype(int),
        "surface": rng.choice(surfaces, size=n, replace=True),
        "best_of": rng.choice([3, 5], size=n, replace=True, p=[0.8, 0.2]).astype(int),
        "tourney_level": rng.choice(["A", "G", "M"], size=n, replace=True),
        "round": rng.choice(["R32", "R16", "QF", "SF", "F"], size=n, replace=True),
        "match_num": list(range(1, n + 1)), "score": ["6-4 6-3"] * n, "tour": ["atp"] * n,
    })
    raw_a = rng.uniform(1.5, 3.5, n)
    raw_b = rng.uniform(1.5, 3.5, n)
    odds_df = pd.DataFrame({
        "event_id": event_ids,
        "ps_p1": np.round(raw_a, 2), "ps_p2": np.round(raw_b, 2),
        "b365_p1": np.round(raw_a * 0.98, 2), "b365_p2": np.round(raw_b * 0.98, 2),
    })
    corpus = tmp_path / "tennis_corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    matches_df.to_parquet(corpus / "matches.parquet", index=False)
    odds_df.to_parquet(corpus / "odds.parquet", index=False)
    return corpus


# ---------------------------------------------------------------------------
# V3: gate end-to-end on synthetic corpus
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_corpus(tmp_path_factory):
    return _make_synthetic_corpus(tmp_path_factory.mktemp("corpus"))


class TestV3GateSynthetic:
    """Real gate.evaluate on synthetic data. Verdict not asserted — only shape."""

    @pytest.mark.parametrize("signal_name", list(_SIGNAL_MAP.keys()))
    def test_gate_returns_valid_result(self, signal_name, synthetic_corpus):
        matches_df = pd.read_parquet(synthetic_corpus / "matches.parquet")
        odds_df = pd.read_parquet(synthetic_corpus / "odds.parquet")
        adapter = TennisAdapter(matches_df=matches_df, odds_df=odds_df)
        cls = _SIGNAL_MAP[signal_name]
        hyp = Hypothesis(name=signal_name, target="winprob", scope="pregame",
                         statement=signal_name, rationale="")
        bundle = adapter.feature_bundle(hyp, [2022, 2023, 2024])

        assert isinstance(bundle, FeatureBundle)
        assert bundle.base.ndim == 2
        assert bundle.signal_col.shape[0] == bundle.base.shape[0]

        sig = cls()
        sig._gate_matrix = bundle  # type: ignore[attr-defined]
        result = evaluate(sig, device="cpu", n_splits=3)

        assert isinstance(result, GateResult)
        assert result.signal_name == signal_name
        assert result.verdict in (Verdict.SHIP, Verdict.VARIANCE_ONLY, Verdict.REJECT, Verdict.DEFER)
        assert isinstance(result.wf_folds, list)
        assert isinstance(result.wf_all_improve, bool)


# ---------------------------------------------------------------------------
# Missing corpus graceful exit
# ---------------------------------------------------------------------------

class TestMissingCorpus:
    def test_load_adapter_none(self, tmp_path):
        from scripts.platformkit.proof_tennis.run_proof import _load_adapter
        assert _load_adapter(tmp_path / "nonexistent") is None

    def test_main_exits_code_2(self, tmp_path):
        from scripts.platformkit.proof_tennis.run_proof import main
        rc = main(["--corpus", str(tmp_path / "nonexistent"),
                   "--report", str(tmp_path / "report.md")])
        assert rc == 2


# ---------------------------------------------------------------------------
# F5 compliance: no forbidden imports in adapter/signals
# ---------------------------------------------------------------------------

class TestF5Compliance:
    _FORBIDDEN = ["domains.nba", "src.data", "src.sim", "src.tracking", "src.pipeline"]

    @staticmethod
    def _import_lines(src: str) -> str:
        return "\n".join(
            ln for ln in src.splitlines()
            if ln.lstrip().startswith(("import ", "from "))
        )

    def test_adapter_no_nba_import(self):
        import inspect, domains.tennis.adapter as m
        import_src = self._import_lines(inspect.getsource(m))
        for f in self._FORBIDDEN:
            assert f not in import_src, f"F5 violation: '{f}' in domains/tennis/adapter.py"

    def test_signals_no_nba_import(self):
        import inspect, domains.tennis.signals as m
        import_src = self._import_lines(inspect.getsource(m))
        for f in self._FORBIDDEN:
            assert f not in import_src, f"F5 violation: '{f}' in domains/tennis/signals.py"


# ---------------------------------------------------------------------------
# V4: paper portfolio walk-forward tests
# ---------------------------------------------------------------------------

class TestV4PaperPortfolio:
    """V4: paper book disclaimer, drawdown gate injection, kelly/clamp exercised."""

    # Edge-claim denylist: these strings must NOT appear in the paper_book output
    _EDGE_DENYLIST = ["proven edge", "ROI", "profitable", "+EV", "beat the market"]

    def test_run_v4_produces_paper_book_with_disclaimer(self, synthetic_corpus, tmp_path):
        from scripts.platformkit.proof_tennis.proof_runner import run_v4, _V4_DISCLAIMER
        matches_df = pd.read_parquet(synthetic_corpus / "matches.parquet")
        odds_df = pd.read_parquet(synthetic_corpus / "odds.parquet")
        adapter = TennisAdapter(matches_df=matches_df, odds_df=odds_df)
        paper_dir = tmp_path / "paper_book"
        result = run_v4(adapter, paper_book_dir=paper_dir)

        assert isinstance(result, dict)
        assert "ok" in result
        assert "detail" in result
        # disclaimer must appear in detail
        detail = result["detail"]
        assert "disclaimer" in detail
        assert _V4_DISCLAIMER in detail["disclaimer"]
        # paper book file must exist and contain disclaimer
        book_path = paper_dir / "paper_book.json"
        assert book_path.exists(), "paper_book.json not written"
        import json as _json
        book = _json.loads(book_path.read_text(encoding="utf-8"))
        assert "disclaimer" in book
        assert _V4_DISCLAIMER in book["disclaimer"]

    def test_drawdown_injection_fires(self, synthetic_corpus, tmp_path):
        """check_drawdown_ok must return False on a >15% losing streak."""
        from src.prediction.betting_portfolio import check_drawdown_ok
        # Direct unit test: 20% loss must exceed 15% threshold
        assert not check_drawdown_ok(1000.0, 800.0), (
            "check_drawdown_ok should return False when bankroll drops 20%"
        )
        # V4 must record drawdown_inject_fired=True
        from scripts.platformkit.proof_tennis.proof_runner import run_v4
        matches_df = pd.read_parquet(synthetic_corpus / "matches.parquet")
        odds_df = pd.read_parquet(synthetic_corpus / "odds.parquet")
        adapter = TennisAdapter(matches_df=matches_df, odds_df=odds_df)
        result = run_v4(adapter, paper_book_dir=tmp_path / "pb2")
        assert result["detail"].get("drawdown_inject_fired") is True

    def test_kelly_and_clamp_exercised(self):
        """kelly/clamp decision-kernel seam: smoke test."""
        from src.prediction.betting_portfolio import KELLY_FRACTION, clamp_kelly_pct
        # KELLY_FRACTION must be a positive float
        assert isinstance(KELLY_FRACTION, float) and KELLY_FRACTION > 0
        # clamp_kelly_pct: negative → 0, large → capped, None → None
        assert clamp_kelly_pct(-0.5) == 0.0
        assert clamp_kelly_pct(999.0) == pytest.approx(0.25, abs=1e-6)
        assert clamp_kelly_pct(None) is None

    def test_no_edge_claim_strings_in_output(self, synthetic_corpus, tmp_path):
        """Denylist: no edge/ROI claim strings in paper book JSON."""
        from scripts.platformkit.proof_tennis.proof_runner import run_v4
        matches_df = pd.read_parquet(synthetic_corpus / "matches.parquet")
        odds_df = pd.read_parquet(synthetic_corpus / "odds.parquet")
        adapter = TennisAdapter(matches_df=matches_df, odds_df=odds_df)
        paper_dir = tmp_path / "pb3"
        run_v4(adapter, paper_book_dir=paper_dir)
        book_path = paper_dir / "paper_book.json"
        if book_path.exists():
            text = book_path.read_text(encoding="utf-8").lower()
            for bad in self._EDGE_DENYLIST:
                assert bad.lower() not in text, f"Edge claim '{bad}' found in paper_book.json"

    def test_run_v4_nan_corpus_no_crash(self, tmp_path):
        """Regression: NaN raw_elo and NaN market line must not crash run_v4."""
        import datetime as dt
        from scripts.platformkit.proof_tennis.proof_runner import run_v4, _V4_DISCLAIMER

        rng = np.random.default_rng(77)
        n = 60
        players = list(range(2001, 2007))
        years = rng.choice([2020, 2021, 2022, 2023], size=n, replace=True)
        months = rng.integers(1, 12, size=n)
        days = rng.integers(1, 28, size=n)
        dates = [dt.date(int(y), int(m), int(d)).isoformat()
                 for y, m, d in zip(years, months, days)]
        p1_ids = rng.choice(players, size=n, replace=True)
        p2_ids = np.array([rng.choice([p for p in players if p != p1]) for p1 in p1_ids])
        event_ids = [f"nan-{i}" for i in range(n)]

        # Inject NaN into p1_elo_prob for ~20% of rows (debut players)
        elo_probs = rng.uniform(0.35, 0.65, n).astype(object)
        nan_elo_idx = rng.choice(n, size=n // 5, replace=False)
        for idx in nan_elo_idx:
            elo_probs[idx] = float("nan")

        matches_df = pd.DataFrame({
            "event_id": event_ids, "date": dates, "tourney_id": ["t1"] * n,
            "p1_id": p1_ids.astype(int), "p2_id": p2_ids.astype(int),
            "winner": rng.choice([1, 2], size=n).astype(int),
            "surface": rng.choice(["Hard", "Clay"], size=n),
            "best_of": [3] * n, "tourney_level": ["A"] * n, "round": ["R32"] * n,
            "match_num": list(range(1, n + 1)), "score": ["6-4 6-3"] * n, "tour": ["atp"] * n,
            "p1_elo_prob": elo_probs,
        })

        # Inject NaN into ps_p1 (no odds available) for ~15% of rows
        raw_a = rng.uniform(1.5, 3.5, n)
        raw_b = rng.uniform(1.5, 3.5, n)
        nan_odds_idx = rng.choice(n, size=n // 7, replace=False)
        raw_a[nan_odds_idx] = float("nan")

        odds_df = pd.DataFrame({
            "event_id": event_ids,
            "ps_p1": np.round(raw_a, 2), "ps_p2": np.round(raw_b, 2),
            "b365_p1": np.round(raw_a * 0.98, 2), "b365_p2": np.round(raw_b * 0.98, 2),
        })

        adapter = TennisAdapter(matches_df=matches_df, odds_df=odds_df)
        paper_dir = tmp_path / "nan_paper"
        result = run_v4(adapter, paper_book_dir=paper_dir)

        assert isinstance(result, dict), "run_v4 must return a dict"
        detail = result.get("detail", {})
        assert "disclaimer" in detail, "disclaimer must be present in detail"
        assert _V4_DISCLAIMER in detail["disclaimer"], "disclaimer text must match"
        n_skipped = detail.get("n_skipped_nan", -1)
        assert n_skipped >= 0, f"n_skipped_nan must be reported; got {n_skipped}"
        assert n_skipped > 0, (
            f"Expected >0 skipped NaN rows (injected NaN elo + NaN odds); got {n_skipped}"
        )
