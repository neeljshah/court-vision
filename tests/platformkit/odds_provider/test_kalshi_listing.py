"""Per-file tests for scripts.platformkit.odds_provider.kalshi_listing (LANE 4).

NO NETWORK: rows_from_markets is pure (canned market dicts); todays_kalshi_games
is exercised with an injected http_get. Real-ticker-shaped fixtures per the
npb_outcome_resolver / kbo_outcome_resolver module docstrings (verified live
2026-07-06) -- each market dict carries the PER-LEG 'ticker' field (with a
'-<SIDE>' suffix) the resolvers actually parse, plus a shared 'event_ticker'
(without the suffix), mirroring the real Kalshi /markets payload shape
kalshi.py's group_markets/_team_label already consume.

Run ONLY this file (the full suite freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_listing.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.kalshi_listing import (
    rows_from_markets, todays_kalshi_games)

# ---- real-ticker-shaped fixtures (see resolver module docstrings) ----------- #
_KBO_MARKETS = [
    {"event_ticker": "KXKBOGAME-26JUL050500NCDKIA",
     "ticker": "KXKBOGAME-26JUL050500NCDKIA-NCD"},
    {"event_ticker": "KXKBOGAME-26JUL050500NCDKIA",
     "ticker": "KXKBOGAME-26JUL050500NCDKIA-KIA"},
    {"event_ticker": "KXKBOGAME-26JUL050500HANLG",
     "ticker": "KXKBOGAME-26JUL050500HANLG-HAN"},  # variable-width 3+2 split
]

_NPB_MARKETS = [
    {"event_ticker": "KXNPBGAME-26JUL050500YOKYAK",
     "ticker": "KXNPBGAME-26JUL050500YOKYAK-YOK"},
    {"event_ticker": "KXNPBGAME-26JUL050500HIRHAN",
     "ticker": "KXNPBGAME-26JUL050500HIRHAN-HIR"},
    # ambiguous/unresolvable tail -- must be dropped, never guessed
    {"event_ticker": "KXNPBGAME-26JUL050500XXXYYY",
     "ticker": "KXNPBGAME-26JUL050500XXXYYY-XXX"},
]


def test_kbo_listing_parses_real_shaped_tickers():
    rows = rows_from_markets("kbo", _KBO_MARKETS)
    # 3 markets (2 legs of NCDKIA + 1 leg of HANLG) but only 2 distinct GAMES
    # (deduped on the resolved date+home+away triple, not the raw ticker).
    assert len(rows) == 2
    for r in rows:
        assert r["sport"] == "kbo"
        assert r["state"] == "pre"
        assert r["home_score"] is None and r["away_score"] is None and r["clock"] is None
        assert r["home"] and r["away"] and r["home"] != r["away"]
        assert r["date"] == "2026-07-05"
    ncd_row = next(r for r in rows if r["event_id"].startswith("KXKBOGAME-26JUL050500NCDKIA"))
    # NCD/KIA alias to the parquet's own NC/KIA spelling.
    assert {ncd_row["home"], ncd_row["away"]} == {"NC", "KIA"}


def test_npb_listing_parses_real_shaped_tickers_and_drops_ambiguous():
    rows = rows_from_markets("npb", _NPB_MARKETS)
    # only the 2 resolvable tickers survive; the ambiguous XXXYYY is dropped
    assert len(rows) == 2
    for r in rows:
        assert r["sport"] == "npb"
        assert r["state"] == "pre"
        assert r["home_score"] is None and r["away_score"] is None and r["clock"] is None
        assert r["home"] and r["away"] and r["home"] != r["away"]


def test_no_odds_degrade_unknown_sport():
    """A sport with no Kalshi GAME series registered -> [] (never a guess)."""
    assert rows_from_markets("cricket", _KBO_MARKETS) == []


def test_dedup_by_resolved_game():
    """Both team-leg tickers of one game (different '-<SIDE>' suffix, same
    resolved date+home+away) collapse to ONE listing row."""
    rows = rows_from_markets("kbo", _KBO_MARKETS[:2])
    assert len(rows) == 1


def test_todays_kalshi_games_ok_shape():
    def _http(url: str):
        assert "series_ticker=KXKBOGAME" in url
        assert "status=open" in url
        return {"markets": _KBO_MARKETS}
    out = todays_kalshi_games("kbo", http_get=_http, use_cache=False)
    assert out["status"] == "ok"
    assert out["sport"] == "kbo"
    assert out["n_games"] == 2
    assert all(g["state"] == "pre" for g in out["games"])
    assert "no ESPN feed" in out["honest_note"] or "no ESPN" in out["honest_note"]


def test_todays_kalshi_games_unknown_sport_degrades():
    out = todays_kalshi_games("cricket", http_get=lambda u: {"markets": []},
                              use_cache=False)
    assert out["status"] == "unknown_sport"
    assert out["games"] == []


def test_todays_kalshi_games_http_failure_degrades_never_raises():
    def _raise(url: str):
        raise TimeoutError("boom")
    out = todays_kalshi_games("npb", http_get=_raise, use_cache=False)
    assert out["status"] == "unavailable"
    assert out["games"] == []


def test_todays_kalshi_games_bad_shape_degrades():
    out = todays_kalshi_games("kbo", http_get=lambda u: {"nope": []}, use_cache=False)
    assert out["status"] == "unavailable"
    assert out["games"] == []
