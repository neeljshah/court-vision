"""Per-file tests for prop_close_capture_pregame (offline; injected ledger+feed)."""

from __future__ import annotations

import scripts.platformkit.clv.prop_close_capture_pregame as pg
from scripts.platformkit.clv import prop_close_store as _store


def _ledger():
    return [
        # open pregame prop -> should be captured
        {"sport": "mlb", "market_type": "prop", "channel": "paper", "status": "open",
         "prop_player": "Aaron Judge", "prop_stat": "Total Bases", "line": 1.5,
         "prop_side": "over", "side": "over"},
        # in-game prop -> NOT this capturer's job (skipped)
        {"sport": "mlb", "market_type": "prop", "channel": "paper_ingame_prop",
         "status": "open", "prop_player": "X", "prop_stat": "Hits", "line": 0.5},
        # settled pregame prop -> skipped
        {"sport": "mlb", "market_type": "prop", "channel": "paper", "status": "settled",
         "prop_player": "Y", "prop_stat": "Hits", "line": 0.5},
        # moneyline -> skipped
        {"sport": "mlb", "market_type": "moneyline", "channel": "paper", "status": "open"},
    ]


def test_open_pregame_filter():
    opens = pg._open_pregame_props(_ledger(), "mlb")
    assert len(opens) == 1 and opens[0]["prop_player"] == "Aaron Judge"


def test_capture_records_two_way_close(tmp_path):
    store = str(tmp_path / "prop_close_lines.jsonl")
    # injected pregame feed: a two-way DK line matching the open prop
    quotes = [(pg._base._match_key("Aaron Judge", "Total Bases", 1.5), 1.91, 1.95)]
    res = pg.capture_once("mlb", ledger=_ledger(), quote_fn=lambda s: quotes,
                          store_path=store, now="2026-06-28T22:00:00+00:00")
    assert res["open_props"] == 1 and res["captured"] == 1
    # the settler's lookup key now resolves to the captured close
    row = _ledger()[0]
    key = _store.key_for_row(row)
    loaded = _store._load(store)
    assert key in loaded
    assert loaded[key]["over_dec"] == 1.91 and loaded[key]["source"] == "sportsbook_pregame"


def test_no_matching_quote_is_not_fabricated(tmp_path):
    store = str(tmp_path / "prop_close_lines.jsonl")
    res = pg.capture_once("mlb", ledger=_ledger(), quote_fn=lambda s: [],
                          store_path=store, now="2026-06-28T22:00:00+00:00")
    assert res["captured"] == 0 and res["no_live_price"] == 1


def test_one_sided_quote_skipped(monkeypatch):
    class R:
        def __init__(self, player, stat, line, o, u):
            self.player, self.stat, self.line = player, stat, line
            self.over_price, self.under_price = o, u
    rows = [R("Two Way", "Hits", 0.5, 1.85, 1.95),   # kept
            R("One Sided", "Hits", 0.5, 1.85, None)]  # skipped
    import scripts.platformkit.odds_provider.prop_book_aggregate as agg
    monkeypatch.setattr(agg, "book_best_line_props", lambda sport: rows, raising=True)
    out = pg._pregame_quote_fn("mlb")
    assert len(out) == 1
    assert out[0][1] == 1.85 and out[0][2] == 1.95
