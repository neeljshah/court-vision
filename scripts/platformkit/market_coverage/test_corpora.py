"""Per-file tests for market_coverage.corpora (mlb_ml_states delegation).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/market_coverage/test_corpora.py -q
"""
from __future__ import annotations

from scripts.platformkit.market_coverage import corpora as C


def test_mlb_ml_states_delegates_to_build_states(monkeypatch, tmp_path):
    """mlb_ml_states must delegate to oddsapi_close_corpus.build_states('mlb') --
    it no longer requires a joinable local odds.parquet/event_id (that seam was the
    DATA_LIMITED bug this delegation fixes). *root* is ignored by the delegate."""
    calls = []
    fake_states = [{"game_id": "mlb-x", "home": "A", "away": "B",
                    "state_ts": "2026-01-01T00:00:00", "outcome": 1,
                    "devig_close_prob": 0.6}]

    def fake_build_states(sport):
        calls.append(sport)
        return fake_states

    monkeypatch.setattr(
        "scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
        fake_build_states)

    got = C.mlb_ml_states(tmp_path / "nonexistent_root")  # root need not even exist
    assert calls == ["mlb"]
    assert got == fake_states


def test_mlb_ml_states_state_shape_matches_corpora_contract(monkeypatch, tmp_path):
    """Whatever build_states returns, mlb_ml_states passes it through unchanged and
    each state carries the corpora.py-compatible shape edge_finder's gate depends
    on (game_id/home/away/state_ts/outcome/devig_close_prob)."""
    fake_states = [
        {"game_id": "mlb-2026-01-01-A-B", "home": "A", "away": "B",
         "state_ts": "2026-01-01T00:00:00", "outcome": 1, "devig_close_prob": 0.62},
        {"game_id": "mlb-2026-01-02-C-D", "home": "C", "away": "D",
         "state_ts": "2026-01-02T00:00:00", "outcome": 0, "devig_close_prob": 0.41},
    ]
    monkeypatch.setattr(
        "scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
        lambda sport: fake_states)
    got = C.mlb_ml_states(tmp_path)
    required = {"game_id", "home", "away", "state_ts", "outcome", "devig_close_prob"}
    for s in got:
        assert required <= set(s.keys())
        assert s["outcome"] in (0, 1)
        assert 0.0 <= s["devig_close_prob"] <= 1.0
