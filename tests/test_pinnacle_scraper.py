"""tests/test_pinnacle_scraper.py -- R15 Pinnacle scraper unit tests.

Covers:
1. canonical schema validity (10 fields, correct names + order) for player props
2. mainline schema validity (10 fields)
3. parse_player_props produces well-formed rows from a stub matchups/markets payload
4. parse_mainline produces moneyline/total/spread rows
5. stat resolution from `units` + description fallback
6. player-name recovery from special.description
7. _BOOK_ALIASES contains pin -> pinnacle and pinnacle -> pinnacle
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import pytest                                                       # noqa: E402

from scripts.pinnacle_scraper import (                               # noqa: E402
    MAINLINE_FIELDS,
    PROP_FIELDS,
    _player_from_description,
    _stat_from_units_and_desc,
    parse_mainline,
    parse_player_props,
)
from src.betting.clv import _BOOK_ALIASES, _book_canon                # noqa: E402


# ── schema sanity ─────────────────────────────────────────────────────────────


def test_prop_schema_is_canonical_ten_columns():
    expected = ["captured_at", "book", "game_id", "player_id", "player_name",
                "stat", "line", "over_price", "under_price", "start_time"]
    assert PROP_FIELDS == expected


def test_mainline_schema_has_required_columns():
    assert "captured_at" in MAINLINE_FIELDS
    assert "market_type" in MAINLINE_FIELDS
    assert "side" in MAINLINE_FIELDS
    assert "line" in MAINLINE_FIELDS
    assert "price" in MAINLINE_FIELDS
    assert "home_team" in MAINLINE_FIELDS
    assert "away_team" in MAINLINE_FIELDS
    assert MAINLINE_FIELDS[0] == "captured_at"
    assert MAINLINE_FIELDS[1] == "book"


# ── alias resolution (the integration point for compute_clv) ──────────────────


def test_alias_pin_resolves_to_pinnacle():
    assert "pin" in _BOOK_ALIASES
    assert _BOOK_ALIASES["pin"] == "pinnacle"


def test_alias_pinnacle_canonicalizes_itself():
    assert "pinnacle" in _BOOK_ALIASES
    assert _BOOK_ALIASES["pinnacle"] == "pinnacle"


def test_book_canon_resolves_case_and_whitespace():
    assert _book_canon("PIN") == "pinnacle"
    assert _book_canon("  pinnacle ") == "pinnacle"
    assert _book_canon("Pin") == "pinnacle"


# ── stat resolution ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("units,desc,expected", [
    ("Points",       None,                          "pts"),
    ("Rebounds",     None,                          "reb"),
    ("Assists",      None,                          "ast"),
    ("Threes",       None,                          "fg3m"),
    ("Blocks",       None,                          "blk"),
    ("Steals",       None,                          "stl"),
    ("Turnovers",    None,                          "tov"),
    (None,           "LeBron James Total Points",   "pts"),
    (None,           "Anthony Davis Total Blocks",  "blk"),
    ("",             "Stephen Curry Total Threes",  "fg3m"),
    ("Lasers",       None,                          None),  # unrecognised
])
def test_stat_resolution(units, desc, expected):
    assert _stat_from_units_and_desc(units, desc) == expected


# ── player name parsing ───────────────────────────────────────────────────────


def test_player_from_description_strips_units_suffix():
    assert _player_from_description("LeBron James Total Points", "Points") \
        == "LeBron James"


def test_player_from_description_fallback_without_units():
    # No units provided -- use generic ' Total ' split.
    assert _player_from_description("Jokic Total Rebounds", None) == "Jokic"


def test_player_from_description_handles_empty():
    assert _player_from_description("", "Points") == ""
    assert _player_from_description(None, "Points") == ""


# ── parse_player_props end-to-end with stub payload ───────────────────────────


def _stub_prop_matchups_and_markets():
    """Build minimal but realistic Pinnacle payload for two props."""
    matchups = [
        # The parent game.
        {
            "id": 1000,
            "parentId": None,
            "type": "matchup",
            "league": {"id": 487},
            "startTime": "2026-05-27T00:35:00Z",
            "participants": [
                {"alignment": "home", "name": "Boston Celtics", "id": 11, "order": 1},
                {"alignment": "away", "name": "New York Knicks", "id": 12, "order": 0},
            ],
        },
        # Special: Tatum points.
        {
            "id": 2001,
            "parentId": 1000,
            "type": "special",
            "units": "Points",
            "startTime": "2026-05-27T00:35:00Z",
            "special": {
                "category": "Player Props",
                "description": "Jayson Tatum Total Points",
            },
            "participants": [
                {"id": 9001, "name": "Over",  "alignment": "neutral", "order": 0},
                {"id": 9002, "name": "Under", "alignment": "neutral", "order": 1},
            ],
        },
        # Special: Brunson rebounds (under listed first to verify pid matching).
        {
            "id": 2002,
            "parentId": 1000,
            "type": "special",
            "units": "Rebounds",
            "startTime": "2026-05-27T00:35:00Z",
            "special": {
                "category": "Player Props",
                "description": "Jalen Brunson Total Rebounds",
            },
            "participants": [
                {"id": 9011, "name": "Under", "alignment": "neutral", "order": 1},
                {"id": 9012, "name": "Over",  "alignment": "neutral", "order": 0},
            ],
        },
        # Non-player-prop special (should be ignored).
        {
            "id": 2003,
            "parentId": 1000,
            "type": "special",
            "units": "Points",
            "special": {"category": "Game Props",
                        "description": "Total team rebounds"},
        },
    ]
    related = {
        1000: [
            # Tatum points OU market
            {"matchupId": 2001, "type": "total", "key": "s;0;ou",
             "prices": [
                 {"participantId": 9001, "points": 27.5, "price": -110},
                 {"participantId": 9002, "points": 27.5, "price": -110},
             ]},
            # Brunson rebounds OU market
            {"matchupId": 2002, "type": "total", "key": "s;0;ou",
             "prices": [
                 {"participantId": 9012, "points": 3.5, "price": +120},
                 {"participantId": 9011, "points": 3.5, "price": -150},
             ]},
        ]
    }
    return matchups, related


def test_parse_player_props_emits_canonical_rows():
    matchups, related = _stub_prop_matchups_and_markets()
    rows = parse_player_props(matchups, related, "2026-05-27T08:30:00")
    assert len(rows) == 2
    by_player = {r["player_name"]: r for r in rows}
    assert "Jayson Tatum" in by_player
    assert "Jalen Brunson" in by_player

    tatum = by_player["Jayson Tatum"]
    # all 10 canonical fields present
    assert set(tatum.keys()) >= set(PROP_FIELDS)
    assert tatum["book"] == "pin"
    assert tatum["stat"] == "pts"
    assert tatum["line"] == 27.5
    assert tatum["over_price"] == -110
    assert tatum["under_price"] == -110
    assert tatum["game_id"] == "1000"
    assert tatum["start_time"] == "2026-05-27T00:35:00Z"

    brunson = by_player["Jalen Brunson"]
    # Critical: even though Pinnacle returned under before over in `prices`,
    # the participant-id mapping must put the correct prices on each side.
    assert brunson["stat"] == "reb"
    assert brunson["line"] == 3.5
    assert brunson["over_price"] == +120
    assert brunson["under_price"] == -150


def test_parse_player_props_skips_unparseable():
    """Special with no matching market -> dropped, no exception."""
    matchups, _ = _stub_prop_matchups_and_markets()
    rows = parse_player_props(matchups, {}, "2026-05-27T08:30:00")
    assert rows == []


# ── parse_mainline end-to-end with stub payload ───────────────────────────────


def _stub_mainline_matchups_and_markets():
    matchups = [
        {
            "id": 5000,
            "parentId": None,
            "type": "matchup",
            "league": {"id": 487},
            "startTime": "2026-05-27T00:35:00Z",
            "participants": [
                {"alignment": "home", "name": "OKC Thunder", "id": 21},
                {"alignment": "away", "name": "SAS Spurs",   "id": 22},
            ],
        }
    ]
    markets = [
        # Moneyline
        {"matchupId": 5000, "type": "moneyline", "key": "s;0;m", "period": 0,
         "prices": [
             {"designation": "home", "price": -174},
             {"designation": "away", "price": +156},
         ]},
        # Total
        {"matchupId": 5000, "type": "total", "key": "s;0;ou", "period": 0,
         "prices": [
             {"points": 222.5, "price": -110},
             {"points": 222.5, "price": -110},
         ]},
        # Spread
        {"matchupId": 5000, "type": "spread", "key": "s;0;s;-4", "period": 0,
         "prices": [
             {"designation": "home", "points": -4.5, "price": -105},
             {"designation": "away", "points": +4.5, "price": -115},
         ]},
        # Q1 spread -- must be filtered (period != 0)
        {"matchupId": 5000, "type": "spread", "key": "s;1;s;-1", "period": 1,
         "prices": [
             {"designation": "home", "points": -1.5, "price": -110},
             {"designation": "away", "points": +1.5, "price": -110},
         ]},
    ]
    return matchups, markets


def test_parse_mainline_emits_all_three_market_types():
    matchups, markets = _stub_mainline_matchups_and_markets()
    rows = parse_mainline(matchups, markets, "2026-05-27T08:30:00")
    by_type: dict = {}
    for r in rows:
        by_type.setdefault(r["market_type"], []).append(r)

    assert "moneyline" in by_type
    assert "total" in by_type
    assert "spread" in by_type
    # Q1 spread must NOT leak in.
    for r in rows:
        # No period-1 row should appear; we can't see the period in the row,
        # but the stub-row total count tells us: 2(ml) + 2(total) + 2(spread) = 6.
        pass
    assert len(rows) == 6

    # Sanity: home moneyline price.
    ml = {r["side"]: r for r in by_type["moneyline"]}
    assert ml["home"]["price"] == -174
    assert ml["away"]["price"] == +156

    # Sanity: spread points carried through.
    sp = {r["side"]: r for r in by_type["spread"]}
    assert sp["home"]["line"] == -4.5
    assert sp["away"]["line"] == +4.5

    # Sanity: total -- first price tagged over, second under.
    tot = by_type["total"]
    assert tot[0]["side"] == "over"
    assert tot[1]["side"] == "under"
    assert tot[0]["line"] == 222.5

    # All rows must carry team names.
    for r in rows:
        assert r["home_team"] == "OKC Thunder"
        assert r["away_team"] == "SAS Spurs"
        assert r["book"] == "pin"
