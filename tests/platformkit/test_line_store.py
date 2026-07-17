"""Per-file test for scripts.platformkit.odds_provider.line_store (offline, tmp dir).

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_line_store.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.odds_provider.markets import MONEYLINE, MarketQuote
from scripts.platformkit.odds_provider.snapshot import write_quotes
from scripts.platformkit.odds_provider.line_store import (
    get_close, get_latest, get_latest_batch, get_open, parse_game_key,
)

TIP = "2026-06-18T23:00:00+00:00"  # tipoff / lock time


def _q(captured_at, side="home", odds=1.91, suspect=False):
    return MarketQuote(
        sport="nba", game_id="G1", home="Knicks", away="Spurs",
        market_type=MONEYLINE, side=side, line=None, odds=odds,
        book="espn:DraftKings", captured_at=captured_at, devigged_prob=None,
        captured_at_suspect=suspect)


def _seed(tmp_path, captures, *, commence=TIP):
    for cap, odds in captures:
        write_quotes([_q(cap, odds=odds)], out_dir=tmp_path,
                     commence_by_game={"G1": commence} if commence else None)


def test_parse_game_key_both_forms():
    assert parse_game_key("G1").game_id == "G1"
    k = parse_game_key("nba|Knicks|Spurs|2026-06-18")
    assert k.game_id is None
    assert (k.sport, k.home, k.away, k.date) == ("nba", "Knicks", "Spurs", "2026-06-18")


def test_open_is_earliest(tmp_path):
    _seed(tmp_path, [
        ("2026-06-18T18:00:00+00:00", 1.80),
        ("2026-06-18T20:00:00+00:00", 1.91),
        ("2026-06-18T22:55:00+00:00", 2.00),
    ])
    opn = get_open("G1", base=tmp_path)
    assert opn is not None
    row = opn[(MONEYLINE, "home")]
    assert row["captured_at"] == "2026-06-18T18:00:00+00:00"
    assert row["odds"] == 1.80


def test_latest_is_most_recent(tmp_path):
    _seed(tmp_path, [
        ("2026-06-18T18:00:00+00:00", 1.80),
        ("2026-06-18T22:55:00+00:00", 2.00),
    ])
    lat = get_latest("G1", base=tmp_path)
    assert lat[(MONEYLINE, "home")]["odds"] == 2.00


def test_latest_batch_one_pass_matches_per_game(tmp_path):
    # Two games in one sport; batch must return the latest quote per game in one
    # pass and agree with the per-game get_latest() for each.
    def _q2(gid, captured_at, odds):
        return MarketQuote(
            sport="nba", game_id=gid, home="A", away="B", market_type=MONEYLINE,
            side="home", line=None, odds=odds, book="espn:DraftKings",
            captured_at=captured_at, devigged_prob=None)
    write_quotes([_q2("G1", "2026-06-18T18:00:00+00:00", 1.80)], out_dir=tmp_path)
    write_quotes([_q2("G1", "2026-06-18T22:00:00+00:00", 2.00)], out_dir=tmp_path)
    write_quotes([_q2("G2", "2026-06-18T19:00:00+00:00", 1.50)], out_dir=tmp_path)

    batch = get_latest_batch("nba", ["G1", "G2", "G3"], base=tmp_path)
    assert batch["G1"][(MONEYLINE, "home")]["odds"] == 2.00  # latest of the two
    assert batch["G2"][(MONEYLINE, "home")]["odds"] == 1.50
    assert "G3" not in batch  # no history -> absent, never fabricated
    # parity with the per-game reader
    assert batch["G1"] == get_latest("G1", base=tmp_path)


def test_latest_batch_empty_inputs(tmp_path):
    assert get_latest_batch("nba", [], base=tmp_path) == {}
    assert get_latest_batch("nba", ["G1"], base=tmp_path) == {}  # no files yet


def test_close_within_window_is_true_close(tmp_path):
    # Last tick at 22:55 is 5 min before the 23:00 tip -> within 30-min lock window.
    _seed(tmp_path, [
        ("2026-06-18T18:00:00+00:00", 1.80),
        ("2026-06-18T22:55:00+00:00", 2.00),
    ])
    res = get_close("G1", base=tmp_path)
    assert res is not None
    closes, is_true = res
    assert is_true is True
    assert closes[(MONEYLINE, "home")]["odds"] == 2.00


def test_close_without_window_is_proxy(tmp_path):
    # All ticks are hours before tip -> none at lock -> last-observed is a PROXY.
    _seed(tmp_path, [
        ("2026-06-18T12:00:00+00:00", 1.80),
        ("2026-06-18T15:00:00+00:00", 1.95),
    ])
    res = get_close("G1", base=tmp_path)
    closes, is_true = res
    assert is_true is False
    assert closes[(MONEYLINE, "home")]["odds"] == 1.95  # last observed


def test_close_proxy_when_no_commence_time(tmp_path):
    # No commence_time logged -> cannot prove at-lock -> proxy even if near tip.
    write_quotes([_q("2026-06-18T22:55:00+00:00", odds=2.0)],
                 out_dir=tmp_path, commence_by_game=None)
    closes, is_true = get_close("G1", base=tmp_path)
    assert is_true is False
    assert closes[(MONEYLINE, "home")]["odds"] == 2.0


def test_composite_game_key_matches(tmp_path):
    _seed(tmp_path, [("2026-06-18T18:00:00+00:00", 1.80)])
    opn = get_open("nba|Knicks|Spurs|2026-06-18", base=tmp_path)
    assert opn is not None
    assert opn[(MONEYLINE, "home")]["odds"] == 1.80


def test_missing_history_returns_none(tmp_path):
    assert get_open("G1", base=tmp_path) is None
    assert get_close("G1", base=tmp_path) is None
    assert get_latest("ZZZ", base=tmp_path) is None


def test_true_close_requires_all_market_sides_at_lock(tmp_path):
    # home gets an at-lock tick; away only has an early tick -> overall proxy.
    write_quotes([_q("2026-06-18T22:55:00+00:00", side="home", odds=2.0)],
                 out_dir=tmp_path, commence_by_game={"G1": TIP})
    write_quotes([_q("2026-06-18T12:00:00+00:00", side="away", odds=1.9)],
                 out_dir=tmp_path, commence_by_game={"G1": TIP})
    closes, is_true = get_close("G1", base=tmp_path)
    assert is_true is False
    assert (MONEYLINE, "home") in closes and (MONEYLINE, "away") in closes


# ---------------------------------------------------------------------------
# CLOCK-TRUST GUARD (captured_at_suspect) -- go-live defect A
# ---------------------------------------------------------------------------

def test_suspect_row_at_lock_time_is_never_a_true_close(tmp_path):
    # Timing alone would qualify (5 min before the 23:00 tip, inside the 30-min
    # lock window), but the row is stamped captured_at_suspect=True (markets.py's
    # clock-trust guard tripped) -- it must NEVER be promoted to a TRUE close.
    write_quotes([_q("2026-06-18T22:55:00+00:00", odds=2.0, suspect=True)],
                 out_dir=tmp_path, commence_by_game={"G1": TIP})
    closes, is_true = get_close("G1", base=tmp_path)
    assert is_true is False  # PROXY-only, even though it is the only/last tick
    assert closes[(MONEYLINE, "home")]["odds"] == 2.0
    assert closes[(MONEYLINE, "home")]["captured_at_suspect"] is True


def test_suspect_row_falls_back_to_non_suspect_at_lock_tick(tmp_path):
    # An earlier suspect tick sits inside the lock window, but a LATER
    # non-suspect tick is also at-lock -> the honest (non-suspect) tick wins
    # as the true close, not the suspect one.
    write_quotes([_q("2026-06-18T22:50:00+00:00", odds=1.80, suspect=True)],
                 out_dir=tmp_path, commence_by_game={"G1": TIP})
    write_quotes([_q("2026-06-18T22:58:00+00:00", odds=2.00, suspect=False)],
                 out_dir=tmp_path, commence_by_game={"G1": TIP})
    closes, is_true = get_close("G1", base=tmp_path)
    assert is_true is True
    assert closes[(MONEYLINE, "home")]["odds"] == 2.00
    assert closes[(MONEYLINE, "home")]["captured_at_suspect"] is False


def test_non_suspect_close_within_window_is_still_a_true_close(tmp_path):
    # Happy path (not-suspect): unaffected by the clock-trust guard -- same
    # at-lock tick classification as before the fix.
    _seed(tmp_path, [
        ("2026-06-18T18:00:00+00:00", 1.80),
        ("2026-06-18T22:55:00+00:00", 2.00),
    ])
    res = get_close("G1", base=tmp_path)
    closes, is_true = res
    assert is_true is True
    assert closes[(MONEYLINE, "home")]["odds"] == 2.00
    assert closes[(MONEYLINE, "home")].get("captured_at_suspect") is False
