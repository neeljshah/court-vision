"""Tests for prop_close_capture. Per-file:
python -m pytest scripts/platformkit/clv/test_prop_close_capture.py -q
"""
from __future__ import annotations

from scripts.platformkit.clv import prop_close_capture as C
from scripts.platformkit.clv import prop_close_store as PS


def _bet(player, stat, line, status="open", channel="paper_ingame_prop", sport="mlb"):
    return {"channel": channel, "status": status, "sport": sport,
            "game_date": "2026-06-25", "prop_player": player, "prop_stat": stat,
            "line": line, "prop_side": "over"}


def test_captures_matching_open_ingame_prop(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    led = [_bet("Player A", "Hits+Runs+RBIs", 2.5)]
    # live feed quote keyed date-independently (normalized stat matches)
    qf = lambda sport: [(C._match_key("Player A", "Hits Runs RBIs", 2.5), 1.87, 2.05)]
    res = C.capture_once("mlb", ledger=led, quote_fn=qf, store_path=sp,
                         now="2026-06-25T05:00:00Z")
    assert res["open_props"] == 1 and res["captured"] == 1
    c = PS.close_for_row(led[0], store_path=sp)
    assert c is not None and c["over_dec"] == 1.87 and c["under_dec"] == 2.05


def test_no_open_props_skips_fetch(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    called = {"n": 0}

    def qf(sport):
        called["n"] += 1
        return []

    res = C.capture_once("mlb", ledger=[], quote_fn=qf, store_path=sp)
    assert res["captured"] == 0
    assert called["n"] == 0  # never hits the network when nothing is open


def test_unmatched_prop_not_fabricated(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    led = [_bet("Player A", "Hits", 0.5)]
    qf = lambda sport: [(C._match_key("Someone Else", "Hits", 0.5), 1.9, 1.9)]
    res = C.capture_once("mlb", ledger=led, quote_fn=qf, store_path=sp)
    assert res["captured"] == 0 and res["no_live_price"] == 1
    assert PS.close_for_row(led[0], store_path=sp) is None


def test_settled_and_pregame_props_ignored(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    led = [
        _bet("A", "Hits", 0.5, status="settled"),          # already settled
        _bet("B", "Hits", 0.5, channel="paper"),           # pregame DFS, not in-game
    ]
    qf = lambda sport: [(C._match_key("A", "Hits", 0.5), 1.9, 1.9),
                        (C._match_key("B", "Hits", 0.5), 1.9, 1.9)]
    res = C.capture_once("mlb", ledger=led, quote_fn=qf, store_path=sp)
    assert res["open_props"] == 0 and res["captured"] == 0
