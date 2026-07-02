"""Per-file tests for historical_backtest_scoreboard (mocked -- no real network/data
scan; the live-data smoke check is done manually via `python -m ...main()`, not here).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/econ/test_historical_backtest_scoreboard.py -q
"""
from __future__ import annotations

from unittest.mock import patch
from dataclasses import dataclass, field
from typing import Dict

from scripts.platformkit.econ.historical_backtest_scoreboard import (
    build, render, write_status, HONEST_NOTE, MIN_N_FOR_VERDICT,
)


@dataclass
class _FakeResult:
    name: str
    bucket: str = "test"
    sport: str = "mlb"
    verdict: str = "MATCH"
    n: int = 2326
    n_corpora: int = 1
    bss: float = 0.0025
    brier_model: float = 0.2417
    brier_close: float = 0.2423
    ece: float = 0.0
    sharpness: float = 0.0
    dm_p: float = 0.0798
    dm_stat: float = 0.0
    reason: str = "MATCHES the close within noise"
    needs_forward_clv: bool = False
    meta: Dict = field(default_factory=dict)

    def as_dict(self):
        d = dict(self.__dict__)
        d.pop("meta", None)
        return d


def test_filters_out_needs_forward_clv_and_zero_n_rows():
    fake_hunt = [
        _FakeResult("mlb_moneyline"),
        _FakeResult("nba_prop_stl", verdict="NEEDS_FORWARD_CLV", n=0),
        _FakeResult("nba_prop_blk", verdict="NEEDS_FORWARD_CLV", n=0),
    ]
    with patch("scripts.platformkit.market_coverage.edge_finder.hunt", return_value=fake_hunt), \
         patch("scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
               return_value=[{"game_id": "x"}] * 11):
        doc = build()
    names = [r["name"] for r in doc["rows"]]
    assert "mlb_moneyline" in names
    assert "nba_prop_stl" not in names
    assert "nba_prop_blk" not in names


def test_every_row_marked_retrospective():
    with patch("scripts.platformkit.market_coverage.edge_finder.hunt", return_value=[_FakeResult("mlb_moneyline")]), \
         patch("scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
               return_value=[{"game_id": "x"}] * 11):
        doc = build()
    assert doc["counts_toward_live_criteria"] is False
    assert all(r.get("is_retrospective") is True for r in doc["rows"])


def test_soccer_intl_thin_corpus_reports_insufficient_not_a_verdict():
    with patch("scripts.platformkit.market_coverage.edge_finder.hunt", return_value=[]), \
         patch("scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
               return_value=[{"game_id": "x"}] * 11):
        doc = build()
    soccer_rows = [r for r in doc["rows"] if r["name"] == "soccer_intl_moneyline"]
    assert len(soccer_rows) == 1
    assert soccer_rows[0]["verdict"] == "INSUFFICIENT_DATA"
    assert soccer_rows[0]["n"] == 11
    assert soccer_rows[0]["n"] < MIN_N_FOR_VERDICT


def test_soccer_intl_enough_states_reports_ready_to_wire_not_fake_verdict():
    with patch("scripts.platformkit.market_coverage.edge_finder.hunt", return_value=[]), \
         patch("scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
               return_value=[{"game_id": "x"}] * 250):
        doc = build()
    soccer_rows = [r for r in doc["rows"] if r["name"] == "soccer_intl_moneyline"]
    assert soccer_rows[0]["verdict"] == "READY_TO_WIRE"
    assert soccer_rows[0]["n"] == 250


def test_edge_finder_import_failure_degrades_honestly():
    with patch("scripts.platformkit.market_coverage.edge_finder.hunt",
               side_effect=RuntimeError("boom")), \
         patch("scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
               return_value=[]):
        doc = build()
    assert any(r.get("status") == "error" for r in doc["rows"])


def test_render_never_raises_on_empty():
    assert "HISTORICAL BACKTEST" in render({"rows": [], "honest_note": HONEST_NOTE})


def test_write_status_atomic(tmp_path):
    out = tmp_path / "sub" / "historical_backtest_scoreboard.json"
    with patch("scripts.platformkit.market_coverage.edge_finder.hunt", return_value=[_FakeResult("mlb_moneyline")]), \
         patch("scripts.platformkit.odds_provider.oddsapi_close_corpus.build_states",
               return_value=[{"game_id": "x"}] * 11):
        ok = write_status(out_path=out)
    assert ok is True
    assert out.exists()
    assert not out.with_suffix(out.suffix + ".tmp").exists()
