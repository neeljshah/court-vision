"""Per-file tests for the code<->name team resolver + its aggregate wiring.

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_team_resolver.py -q

NETWORK-FREE. Asserts canonical() collapses code==fullname for NBA + MLB, that
teams_match links codes to full names once sport is threaded through, and that
genuinely DIFFERENT teams (same-city pairs) still do NOT match. Also confirms
soccer/tennis (no codes) pass through unchanged and unknown teams degrade.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider import aggregate
from scripts.platformkit.odds_provider.team_resolver import canonical


# --------------------------------------------------------------------------- #
# canonical(): code and full name collapse to the same key.
# --------------------------------------------------------------------------- #
def test_canonical_nba_code_equals_fullname():
    for code, full in [("BOS", "Boston Celtics"), ("LAL", "Los Angeles Lakers"),
                       ("NYK", "New York Knicks"), ("GSW", "Golden State Warriors"),
                       ("POR", "Portland Trail Blazers"), ("PHI", "Philadelphia 76ers")]:
        assert canonical("nba", code) == canonical("nba", full), (code, full)


def test_canonical_mlb_code_equals_fullname():
    for code, full in [("CIN", "Cincinnati Reds"), ("BOS", "Boston Red Sox"),
                       ("NYM", "New York Mets"), ("NYY", "New York Yankees"),
                       ("CWS", "Chicago White Sox"), ("CUB", "Chicago Cubs"),
                       ("SFO", "San Francisco Giants"), ("TOR", "Toronto Blue Jays")]:
        assert canonical("mlb", code) == canonical("mlb", full), (code, full)


def test_canonical_distinguishes_different_teams():
    # Same city, different team -> distinct keys.
    assert canonical("nba", "New York Knicks") != canonical("nba", "Brooklyn Nets")
    assert canonical("mlb", "Chicago White Sox") != canonical("mlb", "Chicago Cubs")
    # NBA BOS (Celtics) and MLB BOS (Red Sox) are namespaced by sport -> distinct.
    assert canonical("nba", "BOS") != canonical("mlb", "BOS")


def test_canonical_code_aliases():
    assert canonical("nba", "GS") == canonical("nba", "Golden State Warriors")
    assert canonical("nba", "NY") == canonical("nba", "New York Knicks")
    assert canonical("mlb", "CHC") == canonical("mlb", "Chicago Cubs")
    assert canonical("mlb", "SF") == canonical("mlb", "San Francisco Giants")


def test_canonical_soccer_tennis_passthrough_and_unknown_degrade():
    # No codes for soccer/tennis: pure normalized pass-through (no crash).
    assert canonical("soccer", "Manchester City") == "soccer:city"
    assert canonical("tennis", "Carlos Alcaraz") == "tennis:alcaraz"
    # Unknown NBA token degrades to its own nickname token, never crashes.
    assert canonical("nba", "Fake Town Aliens") == "nba:aliens"
    assert canonical("nba", "") == "nba:"


# --------------------------------------------------------------------------- #
# teams_match(): codes now link to full names, different teams still do not.
# --------------------------------------------------------------------------- #
def test_teams_match_links_code_to_fullname():
    assert aggregate.teams_match("BOS", "Boston Celtics", "nba")
    assert aggregate.teams_match("Boston Celtics", "BOS", "nba")
    assert aggregate.teams_match("CIN", "Cincinnati Reds", "mlb")
    assert aggregate.teams_match("LAL", "Los Angeles Lakers", "nba")


def test_teams_match_rejects_different_teams():
    # Different teams must NOT match even with sport threaded through.
    assert not aggregate.teams_match("New York Knicks", "New York Nets", "nba")
    assert not aggregate.teams_match("NYK", "Brooklyn Nets", "nba")
    assert not aggregate.teams_match("Chicago White Sox", "Chicago Cubs", "mlb")
    assert not aggregate.teams_match("CWS", "CHC", "mlb")
    # Cross-team code/name pair stays unmatched.
    assert not aggregate.teams_match("BOS", "Los Angeles Lakers", "nba")
    # NBA BOS code vs MLB Red Sox full name (wrong sport) does not match.
    assert not aggregate.teams_match("BOS", "Cincinnati Reds", "mlb")


def test_teams_match_soccer_strict_name_unchanged():
    # Soccer has no codes -> still the strict name rule (no false links).
    assert aggregate.teams_match("Manchester City", "Manchester City", "soccer")
    assert not aggregate.teams_match("Manchester City", "Manchester United", "soccer")
    assert aggregate.teams_match("San Antonio Spurs", "Spurs", "soccer")  # subset rule


# --------------------------------------------------------------------------- #
# to_odds_lookup-style probe: a coded slate now links to a full-name feed event.
# --------------------------------------------------------------------------- #
def test_lookup_links_code_slate_to_fullname_feed_nba():
    from scripts.platformkit.odds_provider.base import OddsEvent
    # Feed event uses FULL names; slate probes with CODES.
    feed = OddsEvent("e1", "nba", "Boston Celtics", "Los Angeles Lakers", None,
                     {"kalshi": {"home": 1.67, "away": 2.22}})
    probe = OddsEvent("", "nba", "BOS", "LAL", None, {})
    assert aggregate._event_match(feed, probe)
    # A different game does NOT link.
    other = OddsEvent("", "nba", "NYK", "BKN", None, {})
    assert not aggregate._event_match(feed, other)


def test_lookup_links_code_slate_to_fullname_feed_mlb():
    from scripts.platformkit.odds_provider.base import OddsEvent
    feed = OddsEvent("e2", "mlb", "Cincinnati Reds", "New York Mets", None,
                     {"espn:DraftKings": {"home": 1.8, "away": 2.0}})
    probe = OddsEvent("", "mlb", "CIN", "NYM", None, {})
    assert aggregate._event_match(feed, probe)
    # Same-city different team (Cubs vs White Sox) must NOT collide.
    cubs = OddsEvent("e3", "mlb", "Chicago Cubs", "Cincinnati Reds", None, {})
    sox = OddsEvent("", "mlb", "CWS", "CIN", None, {})
    assert not aggregate._event_match(cubs, sox)
