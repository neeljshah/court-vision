"""Per-file tests for scraped_line_gaps -- fully offline (synthetic line_history)."""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv import scraped_line_gaps as G


def _row(book, side, odds, *, market="moneyline", line=None, gid="G1",
         ts="2026-06-29T00:00:00+00:00", home="HOME", away="AWAY"):
    return {"sport": "mlb", "game_id": gid, "home": home, "away": away,
            "market_type": market, "side": side, "line": line, "odds": odds,
            "book": book, "captured_at": ts}


def _write(tmp_path, sport, date, rows):
    d = tmp_path / sport
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.jsonl" % date)).write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_load_and_group_moneyline(tmp_path):
    rows = [_row("pinnacle", "home", 2.00), _row("pinnacle", "away", 2.00),
            _row("fanduel", "home", 1.95), _row("fanduel", "away", 1.95)]
    _write(tmp_path, "mlb", "2026-06-29", rows)
    games = G.build_games(G.load_rows("mlb", "2026-06-29", base=tmp_path))
    assert len(games) == 1
    g = games[0]
    assert g["side_a"] == "home" and g["side_b"] == "away"
    assert set(g["book_prices"]) == {"pinnacle", "fanduel"}
    assert g["book_prices"]["fanduel"]["home"] == 1.95


def test_latest_quote_wins(tmp_path):
    rows = [_row("fanduel", "home", 1.80, ts="2026-06-29T00:00:00+00:00"),
            _row("fanduel", "home", 2.40, ts="2026-06-29T03:00:00+00:00"),
            _row("fanduel", "away", 1.80)]
    _write(tmp_path, "mlb", "2026-06-29", rows)
    games = G.build_games(G.load_rows("mlb", "2026-06-29", base=tmp_path))
    # the later 2.40 quote replaces the stale 1.80
    assert games[0]["book_prices"]["fanduel"]["home"] == 2.40


def test_spread_total_grouped_by_line(tmp_path):
    rows = [
        _row("pinnacle", "over", 1.90, market="total", line=9.0),
        _row("pinnacle", "under", 1.90, market="total", line=9.0),
        _row("fanduel", "over", 1.90, market="total", line=8.5),  # different line
        _row("fanduel", "under", 1.90, market="total", line=8.5),
    ]
    _write(tmp_path, "mlb", "2026-06-29", rows)
    games = G.build_games(G.load_rows("mlb", "2026-06-29", base=tmp_path))
    # two distinct (game, market, line) groups: 9.0 and 8.5 do NOT compete
    lines = sorted(g["line"] for g in games)
    assert lines == [8.5, 9.0]
    for g in games:
        assert g["side_a"] == "over" and g["side_b"] == "under"


def test_find_gap_when_soft_book_beats_sharp(tmp_path):
    # Pinnacle sharp fair ~0.50/0.50; FanDuel offers 2.20 on home = better than fair.
    rows = [_row("pinnacle", "home", 2.00), _row("pinnacle", "away", 2.00),
            _row("fanduel", "home", 2.20), _row("fanduel", "away", 1.80)]
    _write(tmp_path, "mlb", "2026-06-29", rows)
    res = G.find_gaps("mlb", "2026-06-29", min_clv_pct=0.0, base=tmp_path)
    assert res["shoppable"] == 1
    assert len(res["gaps"]) >= 1
    g = res["gaps"][0]
    assert g["side"] == "home"
    assert g["best_book"] == "fanduel"
    assert g["sport"] == "mlb" and g["market"] == "moneyline"
    assert g["expected_clv_pct"] > 0


def test_stale_quote_cannot_make_a_gap(tmp_path):
    # FanDuel 30min STALE vs a fresh DraftKings coin-flip -> the stale 74/26 quote
    # must be dropped, leaving 1 fresh book -> not shoppable -> NO fake gap.
    rows = [
        _row("espn:DraftKings", "home", 1.98, ts="2026-06-29T02:53:00+00:00"),
        _row("espn:DraftKings", "away", 1.98, ts="2026-06-29T02:53:00+00:00"),
        _row("fanduel", "home", 1.29, ts="2026-06-29T02:23:00+00:00"),  # 30m old
        _row("fanduel", "away", 3.50, ts="2026-06-29T02:23:00+00:00"),
    ]
    _write(tmp_path, "mlb", "2026-06-29", rows)
    res = G.find_gaps("mlb", "2026-06-29", min_clv_pct=0.0,
                      max_stale_sec=600.0, base=tmp_path)
    assert res["shoppable"] == 0
    assert res["gaps"] == []
    # but with a LOOSE staleness window the mirage reappears (proves the gate is why)
    loose = G.find_gaps("mlb", "2026-06-29", min_clv_pct=0.0,
                        max_stale_sec=99999.0, base=tmp_path)
    assert len(loose["gaps"]) >= 1


def test_efficient_slate_is_empty(tmp_path):
    # all books identical -> best price == fair -> no +CLV gap.
    rows = [_row("pinnacle", "home", 2.00), _row("pinnacle", "away", 2.00),
            _row("fanduel", "home", 2.00), _row("fanduel", "away", 2.00)]
    _write(tmp_path, "mlb", "2026-06-29", rows)
    res = G.find_gaps("mlb", "2026-06-29", min_clv_pct=0.5, base=tmp_path)
    assert res["gaps"] == []


def test_missing_file_is_empty_not_error(tmp_path):
    res = G.find_gaps("nba", "2026-06-29", base=tmp_path)
    assert res["rows"] == 0 and res["gaps"] == []
    full = G.scan(("nba", "mlb"), "2026-06-29", base=tmp_path)
    assert full["total_gaps"] == 0


def test_render_runs_on_empty():
    res = G.scan(("mlb",), "2099-01-01", base=None)
    out = G.render(res)
    assert "SCRAPED-LINE" in out and "efficient" in out.lower()
