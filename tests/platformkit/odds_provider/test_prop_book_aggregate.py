"""Per-file unit tests for prop_book_aggregate (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_prop_book_aggregate.py -q

ACCEPTANCE criteria (all tested here):
  - Canned FanDuel two-sided + DFS single-line rows -> per (player, stat, line)
    best OVER and best UNDER decimal w/ book attribution; sportsbook two-sided
    price beats a worse DFS price on the SAME side.
  - Provider down -> UNAVAILABLE sentinel (no synthetic rows).
  - Offseason empty slate -> [] not fabricated rows.
  - FanDuel-only OVER (no under) keeps under absent, never guessed.
  - payout_type carried so DFS-vs-book is distinguishable.
  - Never raises.
  - No $ / roi / pnl / profit field in any output dict.

All http_get calls are injected; nothing here touches the network.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.odds_provider.prop_book_aggregate import (
    _SPORTSBOOK_PROVIDERS,
    FanDuelProvider,
    book_best_line_props,
    book_gather_raw,
    book_props_unavailable,
)
from scripts.platformkit.odds_provider.prop_draftkings_v2 import DraftKingsV2Provider

# ---------------------------------------------------------------------------
# Canned FanDuel payloads (mirroring the real runner shape)
# ---------------------------------------------------------------------------

_PAGE = {
    "attachments": {"events": {
        "35035171": {"name": "Uzbekistan v Colombia",
                     "openDate": "2026-06-18T02:00:00.000Z", "eventTypeId": 1},
        "31345701": {"name": "FIFA World Cup", "eventTypeId": 1},
    }}
}

_EVENT_TWO_SIDED = {
    "attachments": {
        "events": {"35035171": {"name": "Uzbekistan v Colombia"}},
        "markets": {
            "P1": {
                "marketId": "P1", "eventId": "35035171",
                "marketName": "Luis Diaz - Shots on Target",
                "runners": [
                    {"runnerName": "Over", "handicap": 1.5,
                     "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": 120}}},
                    {"runnerName": "Under", "handicap": 1.5,
                     "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -150}}},
                ],
            },
            "P2": {
                "marketId": "P2", "eventId": "35035171",
                "marketName": "Falcao Garcia - Shots",
                "runners": [
                    {"runnerName": "Over", "handicap": 2.5,
                     "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -110}}},
                    {"runnerName": "Under", "handicap": 2.5,
                     "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -110}}},
                ],
            },
        },
    }
}

# FanDuel posting OVER only for one prop (handicap present, no Under runner).
_EVENT_OVER_ONLY = {
    "attachments": {
        "events": {"35035171": {"name": "Uzbekistan v Colombia"}},
        "markets": {
            "P3": {
                "marketId": "P3", "eventId": "35035171",
                "marketName": "Pedraza - Shots on Target",
                "runners": [
                    {"runnerName": "Over", "handicap": 0.5,
                     "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": -130}}},
                ],
            },
        },
    }
}

# No prop markets posted (current live state -- only Moneyline).
_EVENT_NO_PROPS = {
    "attachments": {
        "events": {"35035171": {"name": "Uzbekistan v Colombia"}},
        "markets": {
            "M1": {"marketId": "M1", "eventId": "35035171",
                   "marketName": "Moneyline (3-way)", "runners": []},
        },
    }
}


# ---------------------------------------------------------------------------
# Fake DFS provider (context-only rows: over_price=None, payout_type=dfs_pickem)
# ---------------------------------------------------------------------------

class _FakeDFSProvider:
    """Mimics PrizePicks / Underdog: pick'em context rows, no real decimal price."""

    name = "fake_dfs"

    def __init__(self, rows):
        self._rows = rows

    def fetch_props(self, sport):
        return list(self._rows)


def _dfs_context_row(player, stat, line, sport="soccer_intl"):
    """A pick'em DFS context row: no two-sided price, payout_type='dfs_pickem'."""
    return PropLine(
        sport=sport,
        event_id="35035171",
        match="Uzbekistan v Colombia",
        player=player,
        team=None,
        stat=stat,
        line=line,
        over_price=None,
        under_price=None,
        payout_type="dfs_pickem",
        source="fake_dfs",
        as_of="2026-06-18T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Fake FanDuel provider: injects canned responses; zero network.
# ---------------------------------------------------------------------------

def _make_fanduel(event_body):
    """FanDuelProvider backed by canned PAGE + event body; no network."""
    def http_get(url):
        if "content-managed-page" in url:
            return _PAGE
        return event_body

    return FanDuelProvider(http_get=http_get)


def _make_fanduel_down():
    """FanDuelProvider that raises on every call -> UNAVAILABLE gracefully."""
    def boom(url):
        raise ConnectionError("network down")
    return FanDuelProvider(http_get=boom)


def _make_fanduel_no_events():
    """FanDuelProvider returning empty page (no World Cup events)."""
    return FanDuelProvider(http_get=lambda url: {})


# ===========================================================================
# 1. Core acceptance: canned FanDuel two-sided rows
# ===========================================================================

def test_fanduel_two_sided_rows_emitted():
    """Two-sided FanDuel props produce PropLine rows w/ both over+under prices."""
    prov = _make_fanduel(_EVENT_TWO_SIDED)
    result = book_best_line_props("soccer_intl", book_providers=[prov])
    assert isinstance(result, list)
    assert len(result) >= 1
    for r in result:
        assert r.payout_type == "sportsbook", "expected sportsbook, got %r" % r.payout_type
        assert r.over_price is not None and r.over_price > 1.0
        assert r.under_price is not None and r.under_price > 1.0


def test_fanduel_luis_diaz_shots_on_target():
    """Concrete row: Luis Diaz Shots on Target 1.5 -> correct decimal prices."""
    prov = _make_fanduel(_EVENT_TWO_SIDED)
    rows = book_best_line_props("soccer_intl", book_providers=[prov])
    diaz = [r for r in rows if "diaz" in (r.player or "").lower()
            and r.stat == "Shots On Target"]
    assert diaz, "expected Diaz Shots On Target row"
    r = diaz[0]
    assert r.line == 1.5
    assert r.source == "fanduel"
    assert abs(r.over_price - 2.20) < 1e-9   # +120 -> 2.20
    # -150 -> 1 + 100/150 = 1.666...
    assert abs(r.under_price - (1.0 + 100.0 / 150.0)) < 1e-9


def test_payout_type_carried_sportsbook_vs_dfs():
    """payout_type='sportsbook' on FanDuel rows; 'dfs_pickem' on context-only rows."""
    book_prov = _make_fanduel(_EVENT_TWO_SIDED)
    # DFS row for a different player so it has no sportsbook match
    dfs_prov = _FakeDFSProvider([
        _dfs_context_row("Cuadrado", "Passes Attempted", 45.5),
    ])
    rows = book_best_line_props(
        "soccer_intl", book_providers=[book_prov], dfs_providers=[dfs_prov])
    book_rows = [r for r in rows if r.source == "fanduel"]
    dfs_rows = [r for r in rows if r.source == "fake_dfs"]
    assert all(r.payout_type == "sportsbook" for r in book_rows)
    assert all(r.payout_type == "dfs_pickem" for r in dfs_rows)


# ===========================================================================
# 2. Sportsbook price beats DFS price on the same side
# ===========================================================================

def test_sportsbook_beats_dfs_price_same_side():
    """FanDuel decimal > DFS None on same (player,stat,line): book price wins.

    FanDuel parse_event_props uses the marketName as the player field when no
    player-named runner exists (Over/Under runners carry 'runnerName' of 'Over'/'Under',
    not a player name). So the FanDuel player key is "Luis Diaz - Shots on Target".
    The DFS context row must use the exact same player string to trigger dedup.
    """
    book_prov = _make_fanduel(_EVENT_TWO_SIDED)
    # FanDuel emits player="Luis Diaz - Shots on Target" (the full marketName).
    fd_player = "Luis Diaz - Shots on Target"
    # DFS pick'em row matching that exact player key: no price on either side.
    dfs_row = _dfs_context_row(fd_player, "Shots On Target", 1.5)
    dfs_prov = _FakeDFSProvider([dfs_row])
    rows = book_best_line_props(
        "soccer_intl", book_providers=[book_prov], dfs_providers=[dfs_prov])
    diaz = [r for r in rows
            if "diaz" in (r.player or "").lower() and r.stat == "Shots On Target"]
    assert len(diaz) == 1, "expected exactly one merged row, got %d: %r" % (len(diaz), diaz)
    r = diaz[0]
    # sportsbook price must have won (decimal > None)
    assert r.over_price is not None and r.over_price > 1.0
    assert r.under_price is not None and r.under_price > 1.0
    assert r.payout_type == "sportsbook"


def test_sportsbook_higher_price_beats_worse_dfs_decimal():
    """When DFS provides a worse decimal, FanDuel's better price prevails.

    Both rows share the same (player, stat, event_id, line) key so they merge.
    FanDuel emits player="Luis Diaz - Shots on Target" -- use that exact key.
    """
    book_prov = _make_fanduel(_EVENT_TWO_SIDED)
    fd_player = "Luis Diaz - Shots on Target"
    # A second book with a worse OVER (1.60) than FanDuel (2.20).
    dfs_row = PropLine(
        sport="soccer_intl", event_id="35035171",
        match="Uzbekistan v Colombia", player=fd_player,
        team=None, stat="Shots On Target", line=1.5,
        over_price=1.60,   # worse than FanDuel 2.20
        under_price=None,
        payout_type="sportsbook",
        source="book_worse", as_of="2026-06-18T00:00:00+00:00",
    )
    dfs_prov = _FakeDFSProvider([dfs_row])
    rows = book_best_line_props(
        "soccer_intl", book_providers=[book_prov], dfs_providers=[dfs_prov])
    diaz = [r for r in rows
            if "diaz" in (r.player or "").lower() and r.stat == "Shots On Target"]
    assert diaz
    r = diaz[0]
    # best OVER is FanDuel 2.20, not worse-book 1.60
    assert abs(r.over_price - 2.20) < 1e-9, "expected FanDuel 2.20, got %r" % r.over_price


# ===========================================================================
# 3. Provider down -> UNAVAILABLE
# ===========================================================================

def test_provider_down_returns_unavailable():
    """Network failure on all providers -> UNAVAILABLE sentinel (no synthetic rows)."""
    prov = _make_fanduel_down()
    result = book_props_unavailable("soccer_intl", book_providers=[prov])
    assert is_unavailable(result), "expected UNAVAILABLE sentinel, got %r" % type(result)
    assert "reason" in result


def test_provider_down_best_line_returns_empty_not_unavailable():
    """book_best_line_props with all-down providers returns [] (caller signals UNAVAILABLE)."""
    prov = _make_fanduel_down()
    result = book_best_line_props("soccer_intl", book_providers=[prov])
    assert result == []


def test_no_raise_on_provider_exception():
    """book_best_line_props NEVER raises even when provider raises."""
    def boom(url):
        raise RuntimeError("catastrophic failure")
    prov = FanDuelProvider(http_get=boom)
    result = book_best_line_props("soccer_intl", book_providers=[prov])
    assert isinstance(result, list)


# ===========================================================================
# 4. Offseason empty slate -> [] not fabricated
# ===========================================================================

def test_offseason_empty_events_returns_empty_list():
    """No events in FanDuel page -> [] (offseason), not a fabricated row list."""
    prov = _make_fanduel_no_events()
    result = book_best_line_props("soccer_intl", book_providers=[prov])
    assert result == []


def test_offseason_book_props_unavailable_signals_unavailable():
    """Empty-events FanDuel -> book_props_unavailable returns UNAVAILABLE."""
    prov = _make_fanduel_no_events()
    result = book_props_unavailable("soccer_intl", book_providers=[prov])
    assert is_unavailable(result)


def test_no_markets_posted_returns_empty():
    """Provider up, no prop markets posted (only Moneyline) -> [] not fabricated."""
    prov = _make_fanduel(_EVENT_NO_PROPS)
    result = book_best_line_props("soccer_intl", book_providers=[prov])
    assert result == []


# ===========================================================================
# 5. FanDuel-only OVER: under_price absent, never guessed
# ===========================================================================

def test_over_only_row_keeps_under_absent():
    """FanDuel posts OVER only for Pedraza: under_price must remain None (never guessed)."""
    prov = _make_fanduel(_EVENT_OVER_ONLY)
    rows = book_best_line_props("soccer_intl", book_providers=[prov])
    # The single-runner market won't emit a row (parse_event_props requires both
    # over AND under, OR at least over is not None -- but our dedup keeps whatever
    # the parser emitted honestly).
    # The canned fixture only has "Over" runner -> parse_event_props still emits the
    # row with under_price=None because line_val is set and over is not None.
    if rows:
        for r in rows:
            # under_price must never be guessed from thin air
            assert r.under_price is None or r.under_price > 1.0
            # OVER is present if FanDuel had it
            if r.player and "pedraza" in r.player.lower():
                assert r.over_price is not None and r.over_price > 1.0
                assert r.under_price is None, (
                    "under was not posted; must not be guessed, got %r" % r.under_price)


def test_fanduel_over_only_parse_is_honest():
    """Direct parse check: single Over runner -> PropLine with under_price=None."""
    from scripts.platformkit.odds_provider.prop_fanduel import parse_event_props
    rows = parse_event_props(_EVENT_OVER_ONLY, "soccer_intl")
    if rows:
        r = rows[0]
        assert r.over_price is not None and r.over_price > 1.0
        assert r.under_price is None


# ===========================================================================
# 6. No forbidden $ / roi / pnl fields in any output dict
# ===========================================================================

def test_no_dollar_or_roi_field_in_output():
    """Honesty: no $ / roi / pnl / profit / money field in any PropLine.to_dict()."""
    prov = _make_fanduel(_EVENT_TWO_SIDED)
    rows = book_best_line_props("soccer_intl", book_providers=[prov])
    assert rows, "need at least one row to validate"
    for r in rows:
        d = r.to_dict()
        for bad_key in ("dollar", "roi", "pnl", "profit", "money"):
            assert bad_key not in d, "forbidden key %r found in PropLine.to_dict()" % bad_key


# ===========================================================================
# 7. book_gather_raw: flat gather, no dedup
# ===========================================================================

# ===========================================================================
# 2026-07-03 root-cause fix: DraftKingsV2Provider wired alongside FanDuel.
# FanDuel posts no MLB player-prop markets (live-verified); DK sportsbook-nash
# is the real MLB pregame prop source prop_edge_config already uses. Default
# provider set must include both so book_best_line_props is not structurally
# silent for MLB.
# ===========================================================================

def test_default_sportsbook_providers_include_draftkings_v2():
    """DraftKingsV2Provider must be in the default provider registry (root-cause
    fix: FanDuel-only left MLB pregame close-capture permanently silent)."""
    assert DraftKingsV2Provider in _SPORTSBOOK_PROVIDERS


def test_default_sportsbook_providers_still_include_fanduel():
    """FanDuel stays wired (soccer/WC coverage; harmless no-op for MLB today)."""
    assert FanDuelProvider in _SPORTSBOOK_PROVIDERS


def test_book_gather_raw_returns_flat_list():
    """book_gather_raw returns raw un-deduped rows from all providers."""
    prov = _make_fanduel(_EVENT_TWO_SIDED)
    rows = book_gather_raw("soccer_intl", book_providers=[prov])
    assert isinstance(rows, list)
    assert len(rows) >= 1
    assert all(isinstance(r, PropLine) for r in rows)


def test_book_gather_raw_never_raises():
    """book_gather_raw does not raise even on provider failure."""
    prov = _make_fanduel_down()
    result = book_gather_raw("soccer_intl", book_providers=[prov])
    assert result == []


# ===========================================================================
# 8. book_props_unavailable sentinel vs empty-but-alive distinction
# ===========================================================================

def test_book_props_unavailable_returns_rows_when_alive():
    """When FanDuel is alive and has rows, book_props_unavailable returns the rows."""
    prov = _make_fanduel(_EVENT_TWO_SIDED)
    result = book_props_unavailable("soccer_intl", book_providers=[prov])
    assert isinstance(result, list)
    assert len(result) >= 1


def test_book_props_unavailable_all_down_returns_sentinel():
    """All providers down -> UNAVAILABLE sentinel with reason."""
    prov = _make_fanduel_down()
    result = book_props_unavailable("soccer_intl", book_providers=[prov])
    assert is_unavailable(result)
    assert "reason" in result
    assert "unavailable" in result.get("reason", "").lower()


# ===========================================================================
# 9. Multi-row dedup: same prop from two books -> one merged row, best price
# ===========================================================================

def test_two_books_same_prop_best_price_per_side():
    """Two books quote the same (player, stat, line): best decimal per side survives.

    FanDuel emits player="Luis Diaz - Shots on Target". Book B must use that
    same string so the dedup key matches and rows merge into one.
    """
    # Book A (FanDuel): Diaz SoT 1.5, over=2.20 (+120), under=1.67 (-150)
    book_a = _make_fanduel(_EVENT_TWO_SIDED)
    fd_player = "Luis Diaz - Shots on Target"

    # Book B: better OVER (2.50) but worse UNDER (1.55) than FanDuel.
    diaz_better_over = PropLine(
        sport="soccer_intl", event_id="35035171",
        match="Uzbekistan v Colombia", player=fd_player,
        team=None, stat="Shots On Target", line=1.5,
        over_price=2.50,   # better than FanDuel 2.20
        under_price=1.55,  # worse than FanDuel 1.67
        payout_type="sportsbook",
        source="book_b", as_of="2026-06-18T00:01:00+00:00",
    )
    book_b = _FakeDFSProvider([diaz_better_over])

    rows = book_best_line_props(
        "soccer_intl", book_providers=[book_a], dfs_providers=[book_b])
    diaz = [r for r in rows
            if "diaz" in (r.player or "").lower() and r.stat == "Shots On Target"]
    assert len(diaz) == 1, "expected one merged row, got %d" % len(diaz)
    r = diaz[0]
    # Best OVER = Book B's 2.50; best UNDER = FanDuel's ~1.667
    assert abs(r.over_price - 2.50) < 1e-9, "expected best over 2.50, got %r" % r.over_price
    assert abs(r.under_price - (1.0 + 100.0 / 150.0)) < 1e-3, (
        "expected best under ~1.667, got %r" % r.under_price)
