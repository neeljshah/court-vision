"""Per-file test for knowledge.validate_q3_state. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_q3_state.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge import validate_q3_state as vq3


def _synthetic_linescores(n_games=400, seed=5, reversion=0.0, vol_bump=0.0) -> pd.DataFrame:
    """reversion>0 injects a real Q3-recovers-vs-halftime-deficit signal
    (home_q3 pulls back toward even by `reversion` fraction of the halftime
    gap). vol_bump>0 inflates Q3's own-quarter stdev specifically for games
    close at half, so the volatility hypothesis has a real signal to find."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01")
    rows = []
    for g in range(n_games):
        h_q1, a_q1 = 25 + rng.normal(0, 4), 25 + rng.normal(0, 4)
        h_q2, a_q2 = 25 + rng.normal(0, 4), 25 + rng.normal(0, 4)
        half_gap = (h_q1 + h_q2) - (a_q1 + a_q2)
        close = abs(half_gap) < vq3.CLOSE_HALF_EDGE
        q3_sd = 4 + (vol_bump if close else 0.0)
        h_q3 = 25 - reversion * half_gap / 2 + rng.normal(0, q3_sd)
        a_q3 = 25 + reversion * half_gap / 2 + rng.normal(0, 4)
        h_q4, a_q4 = 25 + rng.normal(0, 4), 25 + rng.normal(0, 4)
        rows.append({
            "event_id": str(g), "home_abbr": "H%d" % (g % 6), "away_abbr": "A%d" % (g % 6),
            "home_q1": h_q1, "home_q2": h_q2, "home_q3": h_q3, "home_q4": h_q4,
            "away_q1": a_q1, "away_q2": a_q2, "away_q3": a_q3, "away_q4": a_q4,
            "date": start + pd.Timedelta(days=g),
        })
    return pd.DataFrame(rows)


def test_team_game_quarters_shape():
    ls = _synthetic_linescores(n_games=30)
    tg = vq3.team_game_quarters(ls, "test")
    assert len(tg) == 60  # 2 team-rows per game
    assert set(tg.columns) >= {"q1_margin", "q2_margin", "q3_margin", "q4_margin",
                               "first_half_margin", "corpus", "side"}
    assert set(tg["corpus"].unique()) == {"test"}


def test_q3_margin_vs_halftime_deficit_detects_injected_reversion():
    ls = _synthetic_linescores(n_games=500, reversion=0.6)
    tg = pd.concat([vq3.team_game_quarters(ls, "c1"), vq3.team_game_quarters(ls, "c2")],
                   ignore_index=True)
    r = vq3.q3_margin_vs_halftime_deficit(tg)
    assert set(r) >= {"hypothesis", "verdict", "per_corpus", "note"}
    assert r["verdict"] == "REPLICATED"
    for corpus_stats in r["per_corpus"].values():
        assert corpus_stats["r"] < 0  # reversion -> negative correlation by construction


def test_q3_margin_vs_halftime_deficit_null_on_symmetric_synthetic_data():
    ls = _synthetic_linescores(n_games=500, reversion=0.0)
    tg = vq3.team_game_quarters(ls, "solo")
    r = vq3.q3_margin_vs_halftime_deficit(tg)
    assert r["verdict"] in {"NULL", "NOT_TESTABLE"}


def test_q3_volatility_close_halftime_detects_injected_bump():
    ls = _synthetic_linescores(n_games=600, vol_bump=6.0)
    tg = pd.concat([vq3.team_game_quarters(ls, "c1"), vq3.team_game_quarters(ls, "c2")],
                   ignore_index=True)
    r = vq3.q3_volatility_close_halftime(tg)
    assert set(r) >= {"hypothesis", "verdict", "per_corpus", "note"}
    assert r["verdict"] == "REPLICATED"


def test_q3_volatility_close_halftime_null_on_flat_synthetic_data():
    ls = _synthetic_linescores(n_games=600, vol_bump=0.0)
    tg = vq3.team_game_quarters(ls, "solo")
    r = vq3.q3_volatility_close_halftime(tg)
    assert r["verdict"] in {"NULL", "NOT_TESTABLE"}


def test_verdict_replicated_helper():
    assert vq3._verdict_replicated({"a": True, "b": True}) == "REPLICATED"
    assert vq3._verdict_replicated({"a": True, "b": False}) == "PARTIAL"
    assert vq3._verdict_replicated({"a": False, "b": False}) == "NULL"
    assert vq3._verdict_replicated({"a": None, "b": None}) == "NOT_TESTABLE"


def test_run_writes_two_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    ls = _synthetic_linescores(n_games=200, reversion=0.4, vol_bump=3.0)
    monkeypatch.setattr(vq3, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vq3, "load_all_corpora", lambda: pd.concat(
        [vq3.team_game_quarters(ls, "c1"), vq3.team_game_quarters(ls, "c2")], ignore_index=True))
    rows = vq3.run()
    assert len(rows) == 2
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2
