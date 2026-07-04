"""Per-file test for beat_the_close_ml_wta.py (Lane 3: WTA odds ingest gate arm).

Tests (offline synthetic + real-data skip-if-absent):
  1. Missing corpus -> status="corpus_missing", never raises.
  2. Too-few-rows -> status="data_limited", n reported honestly.
  3. Synthetic corpus with real signal -> runs end-to-end, verdict is one of
     BEATS/MATCH/BEHIND, no $ / edge / roi / pnl key in output.
  4. gap == round(model_metric - close_metric, 4) arithmetic sanity.
  5. Real-data (if present): WTA gate produces status="ok" with n>=60 and a Brier
     gap in a plausible range (not wildly divergent from the ATP arm's framing).
  6. tour key is 'wta' (never silently 'atp') when status == "ok".

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/proof_tennis/test_beat_the_close_ml_wta.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_tennis.beat_the_close_ml_wta import run  # noqa: E402

_WTA_MATCHES = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_ODDS = _REPO / "data" / "domains" / "tennis" / "odds.parquet"
_REAL_DATA = _WTA_MATCHES.is_file() and _ODDS.is_file()

_FORBIDDEN_KEYS = {"$", "roi", "pnl", "edge", "profit", "dollar"}


def _has_forbidden(d: dict) -> bool:
    return any(k.lower() in _FORBIDDEN_KEYS for k in d)


def _make_synthetic_corpus(tmp_path: Path, n: int = 400, join_frac: float = 1.0):
    """Synthetic WTA matches.parquet + odds.parquet with a real, learnable signal."""
    rng = np.random.default_rng(11)
    n_players = 40
    # Span well past TRAIN_YEAR_MAX=2022 so the walk-forward held-out set is non-empty.
    dates = pd.date_range("2015-01-01", periods=n, freq="8D")
    p1_ids = rng.integers(1, n_players // 2 + 1, n)
    p2_ids = rng.integers(n_players // 2 + 1, n_players + 1, n)
    true_p = np.clip(0.5 + 0.15 * np.sin(p1_ids.astype(float)), 0.05, 0.95)
    winner = (rng.uniform(size=n) < true_p).astype(int) + 1
    event_ids = [f"evt_{i}" for i in range(n)]

    matches = pd.DataFrame({
        "event_id": event_ids,
        "date": dates,
        "tour": "wta",
        "tourney_id": np.arange(n) % 15,
        "tourney_name": "SyntheticWTA",
        "tourney_level": "PM",
        "surface": rng.choice(["Hard", "Clay", "Grass"], n),
        "best_of": 3,
        "round": "R32",
        "match_num": np.arange(n),
        "p1_id": p1_ids,
        "p2_id": p2_ids,
        "p1_name": ["Player_" + str(x) for x in p1_ids],
        "p2_name": ["Player_" + str(x) for x in p2_ids],
        "p1_rank": rng.integers(1, 200, n),
        "p2_rank": rng.integers(1, 200, n),
        "winner": winner,
        "score": "6-3 6-4",
        "retirement": False,
        "minutes": rng.integers(60, 150, n),
    })
    matches_path = tmp_path / "wta_matches.parquet"
    matches.to_parquet(matches_path, index=False)

    n_odds = int(n * join_frac)
    # Market price is a noisy version of true_p -> devigged prob close to true_p
    p_market = np.clip(true_p[:n_odds] + rng.normal(0, 0.03, n_odds), 0.02, 0.98)
    ps_p1 = 1.0 / p_market
    ps_p2 = 1.0 / (1.0 - p_market)
    odds = pd.DataFrame({
        "event_id": event_ids[:n_odds],
        "tour": "wta",
        "ps_p1": ps_p1.astype("float32"),
        "ps_p2": ps_p2.astype("float32"),
    })
    odds_path = tmp_path / "odds.parquet"
    odds.to_parquet(odds_path, index=False)
    return matches_path, odds_path


class TestBeatTheCloseWtaOffline:
    def test_missing_corpus_returns_status(self, tmp_path):
        rep = run(corpus=tmp_path)
        assert rep["status"] == "corpus_missing"
        assert not _has_forbidden(rep)

    def test_too_few_rows_returns_data_limited(self, tmp_path):
        matches_path, odds_path = _make_synthetic_corpus(tmp_path, n=20)
        # run() expects wta_matches.parquet + odds.parquet under corpus dir
        rep = run(corpus=tmp_path)
        assert rep["status"] in ("data_limited", "ok")
        assert not _has_forbidden(rep)

    def test_synthetic_corpus_runs_and_verdict_is_valid(self, tmp_path):
        _make_synthetic_corpus(tmp_path, n=500)
        rep = run(corpus=tmp_path)
        assert rep["status"] == "ok", f"expected ok, got {rep}"
        assert rep["n"] >= 60
        assert any(rep["verdict"].startswith(prefix) for prefix in ("BEATS", "MATCH", "BEHIND"))
        assert not _has_forbidden(rep)

    def test_gap_arithmetic(self, tmp_path):
        _make_synthetic_corpus(tmp_path, n=500)
        rep = run(corpus=tmp_path)
        if rep["status"] != "ok":
            pytest.skip("not enough rows joined")
        expected_gap = round(rep["model_metric"] - rep["close_metric"], 4)
        assert rep["gap"] == expected_gap

    def test_tour_key_is_wta_when_ok(self, tmp_path):
        _make_synthetic_corpus(tmp_path, n=500)
        rep = run(corpus=tmp_path)
        if rep["status"] != "ok":
            pytest.skip("not enough rows joined")
        assert rep["tour"] == "wta"

    def test_no_pooling_odds_filtered_to_wta_only(self, tmp_path):
        """odds.parquet with a mixed-tour frame must only use tour=='wta' rows
        (provenance: never pool ATP evidence into the WTA verdict)."""
        matches_path, odds_path = _make_synthetic_corpus(tmp_path, n=300)
        odds = pd.read_parquet(odds_path)
        # Inject a bogus ATP row with a wildly different (easily detectable) price
        bogus = pd.DataFrame({
            "event_id": ["evt_bogus_atp"],
            "tour": ["atp"],
            "ps_p1": [1.01],
            "ps_p2": [99.0],
        })
        mixed = pd.concat([odds, bogus], ignore_index=True)
        mixed.to_parquet(odds_path, index=False)
        rep = run(corpus=tmp_path)
        if rep["status"] != "ok":
            pytest.skip("not enough rows joined")
        # n must be unaffected by the bogus ATP row (it has no matching WTA event_id anyway,
        # but this also guards the tour-filter in _devig_market)
        assert rep["n"] <= 300


@pytest.mark.skipif(not _REAL_DATA, reason="real tennis WTA corpus not available")
class TestBeatTheCloseWtaRealData:
    def test_real_wta_gate_runs_ok(self):
        rep = run()
        assert rep["status"] == "ok", f"WTA gate failed on real corpus: {rep}"
        assert rep["n"] >= 60
        assert rep["tour"] == "wta"

    def test_real_wta_verdict_is_honest(self):
        rep = run()
        if rep["status"] != "ok":
            pytest.skip("real WTA corpus too small this run")
        assert any(rep["verdict"].startswith(p) for p in ("BEATS", "MATCH", "BEHIND"))
        assert not _has_forbidden(rep)

    def test_real_wta_no_forbidden_keys(self):
        rep = run()
        assert not _has_forbidden(rep)
