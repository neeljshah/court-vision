"""Per-file test for odds_provider.kalshi_series_spec (pure, offline).

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_series_spec.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.odds_provider import kalshi_series_spec as spec


def test_series_for_mlb_has_all_four_market_types():
    pairs = spec.series_for("mlb")
    types = {mt for _s, mt in pairs}
    assert types == {"moneyline", "total", "spread", "team_total"}
    assert ("KXMLBGAME", "moneyline") in pairs
    assert ("KXMLBTOTAL", "total") in pairs
    assert ("KXMLBSPREAD", "spread") in pairs
    assert ("KXMLBTEAMTOTAL", "team_total") in pairs


def test_series_for_tennis_is_moneyline_only_atp_and_wta():
    pairs = spec.series_for("tennis")
    assert pairs == [("KXATPMATCH", "moneyline"), ("KXWTAMATCH", "moneyline")]


def test_series_for_soccer_intl_and_soccer_and_nba():
    assert spec.series_for("soccer_intl") == [
        ("KXWCGAME", "moneyline"), ("KXWCSPREAD", "spread"),
        ("KXWCTEAMTOTAL", "team_total")]
    assert spec.series_for("soccer") == [
        ("KXEPLGAME", "moneyline"), ("KXSOCCERTOTAL", "total")]
    assert spec.series_for("nba") == [
        ("KXNBAGAME", "moneyline"), ("KXNBASPREAD", "spread")]


def test_series_for_unsupported_sport_is_empty():
    assert spec.series_for("cricket") == []


def test_series_for_returns_a_copy_not_the_module_list():
    pairs = spec.series_for("mlb")
    pairs.append(("BOGUS", "bogus"))
    assert ("BOGUS", "bogus") not in spec.series_for("mlb")


def test_game_series_back_compat_is_moneyline_only():
    assert spec._GAME_SERIES == {
        "mlb": "KXMLBGAME", "soccer": "KXEPLGAME",
        "soccer_intl": "KXWCGAME", "nba": "KXNBAGAME"}
    # tennis has no single "GAME" series (it is MATCH-per-tour) -- not in back-compat map.
    assert "tennis" not in spec._GAME_SERIES


def test_ticker_game_date_parses_game_and_match_tickers():
    assert spec.ticker_game_date("KXWCGAME-26JUL04CANMAR") == __import__(
        "datetime").date(2026, 7, 4)
    assert spec.ticker_game_date("KXATPMATCH-26JUL05SAFDJO-SAF") == __import__(
        "datetime").date(2026, 7, 5)


def test_ticker_game_date_unparseable_is_none():
    assert spec.ticker_game_date("KXWCGAME-WEIRDFORMAT") is None
    assert spec.ticker_game_date(None) is None


def test_is_future_game_grace_and_drop():
    now = datetime(2026, 6, 30, 19, 0, tzinfo=timezone.utc)
    assert spec.is_future_game("KXWCGAME-26JUL04CANMAR", now) is True   # 4 days out
    assert spec.is_future_game("KXWCGAME-26JUL01XYZABC", now) is False  # tomorrow, grace
    assert spec.is_future_game("KXWCGAME-26JUN30XYZABC", now) is False  # today
    assert spec.is_future_game("KXWCGAME-WEIRDFORMAT", now) is False    # unparseable -> kept
