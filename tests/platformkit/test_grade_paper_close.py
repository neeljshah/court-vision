"""tests.platformkit.test_grade_paper_close -- close-resolution wiring in grade_one.

Covers the two key scenarios demanded by M3:
  * TRUE close from line_store -> clv_is_proxy=False, CLV computed from it.
  * NO true close (no line_store history) -> clv_is_proxy=True and the prior
    proxy behavior (last_decimal_home/away on the bet) is unchanged.

Also covers:
  * Level-1 precedence: closing_decimal on bet dict wins over line_store.
  * Level-3: line_store proxy (last-observed, not at-lock) -> clv_is_proxy=True.
  * Level-5: no close at all -> clv_pct=None, win/loss only.
  * _game_key_for_bet: event_id path and sport|home|away|date fallback.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_grade_paper_close.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from scripts.platformkit.odds_provider.markets import MONEYLINE, MarketQuote
from scripts.platformkit.odds_provider.snapshot import write_quotes
from scripts.platformkit.grade_paper import (
    _close_from_store,
    _game_key_for_bet,
    grade_one,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
TIP = "2026-06-18T23:00:00+00:00"

_GAME = {"home_score": 5, "away_score": 3}   # home wins


def _bet_base(**extra):
    """Minimal open bet dict for testing grade_one."""
    b = {
        "sport": "nba",
        "matchup": "Spurs @ Knicks",
        "side": "home",
        "taken_decimal": 2.50,  # implied 0.40
        "stake": 10.0,
        "ts": "2026-06-18T20:00:00+00:00",
        "taken_book": "test",
    }
    b.update(extra)
    return b


def _write_ml(tmp_path, captured_at, home_odds, away_odds, *, commence=TIP):
    """Write one moneyline tick (home + away) to the tmp line_store."""
    game_id = "G_TEST"
    kwargs = {"out_dir": tmp_path,
              "commence_by_game": {game_id: commence} if commence else None}
    for side, odds in (("home", home_odds), ("away", away_odds)):
        q = MarketQuote(
            sport="nba", game_id=game_id, home="Knicks", away="Spurs",
            market_type=MONEYLINE, side=side, line=None, odds=odds,
            book="test_book", captured_at=captured_at, devigged_prob=None,
        )
        write_quotes([q], **kwargs)
    return game_id


# ---------------------------------------------------------------------------
# _game_key_for_bet
# ---------------------------------------------------------------------------
def test_game_key_event_id():
    bet = _bet_base(event_id="EVT_123")
    assert _game_key_for_bet(bet) == "EVT_123"


def test_game_key_composite_explicit_home_away_no_date():
    # Explicit home/away but no game_date -> dateless key (ts is NOT the game date,
    # so we deliberately omit it and let line_store scan the sport's files).
    bet = _bet_base(home="Knicks", away="Spurs")
    key = _game_key_for_bet(bet)
    assert key == "nba|Knicks|Spurs"


def test_game_key_composite_with_explicit_game_date():
    bet = _bet_base(home="Knicks", away="Spurs", game_date="2026-06-18")
    key = _game_key_for_bet(bet)
    assert key == "nba|Knicks|Spurs|2026-06-18"


def test_game_key_from_matchup_away_at_home():
    # The real paper rows carry ONLY a 'matchup' (Away@Home), no home/away fields.
    # The resolver must recover home/away from it: 'Spurs @ Knicks' => home=Knicks.
    bet = _bet_base()  # matchup="Spurs @ Knicks", no home/away
    key = _game_key_for_bet(bet)
    assert key == "nba|Knicks|Spurs"


def test_game_key_no_data():
    # No event_id, no home/away -> None
    bet = {"sport": "nba", "ts": "2026-06-18T20:00:00+00:00", "side": "home",
           "taken_decimal": 2.0, "stake": 10.0}
    assert _game_key_for_bet(bet) is None


# ---------------------------------------------------------------------------
# _close_from_store
# ---------------------------------------------------------------------------
def test_close_from_store_true_close(tmp_path):
    """At-lock tick -> is_true_close=True -> returns (ch, ca, True, book, book)."""
    # tick at 22:55 is 5 min before 23:00 tip -> within 30-min window
    gid = _write_ml(tmp_path, "2026-06-18T22:55:00+00:00", 1.80, 2.10)
    bet = _bet_base(event_id=gid)
    result = _close_from_store(bet, base=tmp_path)
    assert result is not None
    ch, ca, is_true, book_h, book_a = result
    assert is_true is True
    assert abs(ch - 1.80) < 1e-9
    assert abs(ca - 2.10) < 1e-9
    assert book_h == "test_book" and book_a == "test_book"  # see _write_ml


def test_close_from_store_proxy(tmp_path):
    """Only early ticks -> no at-lock -> is_true=False (proxy)."""
    gid = _write_ml(tmp_path, "2026-06-18T12:00:00+00:00", 1.70, 2.20)
    bet = _bet_base(event_id=gid)
    result = _close_from_store(bet, base=tmp_path)
    assert result is not None
    ch, ca, is_true, book_h, book_a = result
    assert is_true is False


def test_close_from_store_no_history(tmp_path):
    """No line history for this game -> None."""
    bet = _bet_base(event_id="UNKNOWN_GAME")
    assert _close_from_store(bet, base=tmp_path) is None


def test_close_from_store_no_game_key(tmp_path):
    """No event_id + no home/away -> None (cannot build game_key)."""
    bet = {"sport": "nba", "ts": "2026-06-18T20:00:00+00:00", "side": "home",
           "taken_decimal": 2.0, "stake": 10.0}
    assert _close_from_store(bet, base=tmp_path) is None


# ---------------------------------------------------------------------------
# grade_one: TRUE close from line_store -> clv_is_proxy=False
# ---------------------------------------------------------------------------
def test_grade_one_true_close_from_store(tmp_path):
    """M3 requirement: line_store true close -> clv_is_proxy=False, CLV computed."""
    # taken 2.50 (implied 0.40); close home 1.80/away 2.10
    # fair_home after Shin devig of 1.80/2.10 will be >> 0.40 -> positive CLV
    gid = _write_ml(tmp_path, "2026-06-18T22:55:00+00:00", 1.80, 2.10)
    bet = _bet_base(event_id=gid)
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    assert s["clv_is_proxy"] is False        # TRUE close -> not a proxy
    assert s["clv_pct"] is not None          # CLV was computed
    assert s["beat_close"] is True           # 2.50 > fair decimal at 1.80/2.10 close
    assert s["outcome"] == "win"             # home 5 > away 3
    assert s["executed"] is False


def test_grade_one_stamps_close_book_from_line_store(tmp_path):
    """Same-venue CLV restriction needs the close's book -- line_store resolution
    must stamp it onto the settled row (see PROPOSED_same_venue_close_restriction)."""
    gid = _write_ml(tmp_path, "2026-06-18T22:55:00+00:00", 1.80, 2.10)
    bet = _bet_base(event_id=gid)  # taken_book="test", close book="test_book"
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    assert s["close_book_home"] == "test_book"
    assert s["close_book_away"] == "test_book"


def test_grade_one_close_book_none_when_not_from_line_store(tmp_path):
    """Level-1 (bet already carries closing_decimal_*) has no per-book provenance
    -> close_book_{home,away} stay explicitly None, never guessed."""
    bet = _bet_base(closing_decimal_home=1.80, closing_decimal_away=2.10)
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    assert s["close_book_home"] is None
    assert s["close_book_away"] is None


# ---------------------------------------------------------------------------
# grade_one: NO true close -> clv_is_proxy=True (prior proxy behavior preserved)
# ---------------------------------------------------------------------------
def test_grade_one_no_store_history_uses_bet_proxy(tmp_path):
    """M3 requirement: no line_store history -> falls back to bet-dict proxy, clv_is_proxy=True."""
    # last_decimal_* on the bet, no line_store history for this event_id
    bet = _bet_base(
        event_id="NO_HISTORY_GAME",
        last_decimal_home=1.80,
        last_decimal_away=2.10,
    )
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    assert s["clv_is_proxy"] is True         # bet-dict proxy -> still flagged
    assert s["clv_pct"] is not None
    assert s["outcome"] == "win"
    assert s["executed"] is False


def test_grade_one_proxy_close_from_store_is_flagged(tmp_path):
    """line_store returns a proxy (not at-lock) -> clv_is_proxy=True."""
    gid = _write_ml(tmp_path, "2026-06-18T12:00:00+00:00", 1.80, 2.10)
    bet = _bet_base(event_id=gid)
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    assert s["clv_is_proxy"] is True
    assert s["clv_pct"] is not None          # CLV still computed, just labelled proxy


# ---------------------------------------------------------------------------
# Level-1 precedence: closing_decimal on bet wins over line_store
# ---------------------------------------------------------------------------
def test_grade_one_level1_bet_dict_wins(tmp_path):
    """closing_decimal already on the bet takes precedence over line_store."""
    # Store a different close in line_store (1.95 / 1.95)
    gid = _write_ml(tmp_path, "2026-06-18T22:55:00+00:00", 1.95, 1.95)
    # Bet carries its own pre-resolved close (1.80 / 2.10)
    bet = _bet_base(event_id=gid,
                    closing_decimal_home=1.80, closing_decimal_away=2.10)
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    # Level-1 price used; line_store 1.95/1.95 is ignored
    assert s["closing_decimal_home"] == 1.80
    assert s["closing_decimal_away"] == 2.10
    assert s["clv_is_proxy"] is False


# ---------------------------------------------------------------------------
# Level-5: no close at all -> win/loss only, no CLV
# ---------------------------------------------------------------------------
def test_grade_one_no_close_winloss_only(tmp_path):
    """No close at any level -> clv_pct=None, bet still graded with outcome."""
    bet = _bet_base(event_id="NO_HISTORY")  # no history, no proxy fields
    s = grade_one(bet, _GAME, _line_store_base=tmp_path)

    assert s["clv_pct"] is None
    assert s["beat_close"] is None
    assert s["outcome"] == "win"
    assert s["graded"] is True
    assert s["executed"] is False


# ---------------------------------------------------------------------------
# REGRESSION (the reported bug): a MATCHUP-ONLY paper bet (no event_id, no
# home/away fields -- exactly the shape of every row in clv_ledger.jsonl) must
# resolve the captured close from line_store and compute CLV. Before the fix,
# game_key_for_bet returned None for these rows -> clv_status="no_close" forever.
# ---------------------------------------------------------------------------
def _write_ml_named(tmp_path, captured_at, home_name, away_name,
                    home_odds, away_odds, *, commence=TIP):
    """Write a moneyline tick keyed by full team NAMES (home/away), as the live
    daemon does -- so a matchup-only bet can match by composite key."""
    game_id = "G_NAMED"
    kwargs = {"out_dir": tmp_path, "commence_by_game": {game_id: commence}}
    for side, odds in (("home", home_odds), ("away", away_odds)):
        q = MarketQuote(
            sport="mlb", game_id=game_id, home=home_name, away=away_name,
            market_type=MONEYLINE, side=side, line=None, odds=odds,
            book="consensus", captured_at=captured_at, devigged_prob=None,
        )
        write_quotes([q], **kwargs)


def test_grade_one_matchup_only_resolves_close_end_to_end(tmp_path):
    """Synthetic E2E mirroring the real ledger: a bet that carries ONLY a
    'Away@Home' matchup (no event_id, no home/away fields) resolves the captured
    at-lock close and computes CLV -- no Claude in the loop."""
    # At-lock tick (22:55 vs 23:00 tip) for Braves(home) vs Giants(away).
    _write_ml_named(tmp_path, "2026-06-18T22:55:00+00:00",
                    "Atlanta Braves", "San Francisco Giants", 1.80, 2.10)
    # The bet looks exactly like a real clv_ledger row: matchup-only, no IDs.
    bet = {
        "sport": "mlb",
        "matchup": "San Francisco Giants@Atlanta Braves",  # Away@Home
        "side": "away",                                     # backed the Giants
        "taken_decimal": 2.50,                              # implied 0.40
        "stake_units": 1.0,
        "ts": "2026-06-17T22:59:00+00:00",                 # recorded the DAY BEFORE
        "taken_book": "test",
    }
    game = {"home_score": 2, "away_score": 7}  # away (Giants) win
    s = grade_one(bet, game, _line_store_base=tmp_path)

    assert s["clv_status"] == "true_close"     # NOT 'no_close' anymore
    assert s["clv_is_proxy"] is False          # captured at lock
    assert s["clv_pct"] is not None            # CLV resolved
    assert s["outcome"] == "win"               # Giants won


def test_grade_one_matchup_only_clv_sign_is_correct(tmp_path):
    """Sign sanity (guards the documented 'record_clv backwards' gotcha):
    taking a BETTER number than the close -> CLV > 0; a WORSE number -> CLV < 0.
    Close (home 1.80 / away 2.10) devigs the AWAY fair prob to ~0.46."""
    _write_ml_named(tmp_path, "2026-06-18T22:55:00+00:00",
                    "Atlanta Braves", "San Francisco Giants", 1.80, 2.10)
    base = {
        "sport": "mlb", "matchup": "San Francisco Giants@Atlanta Braves",
        "side": "away", "stake_units": 1.0,
        "ts": "2026-06-17T22:59:00+00:00", "taken_book": "test",
    }
    game = {"home_score": 2, "away_score": 7}

    # BETTER than close: taken 2.50 (implied 0.40) < fair away (~0.46) -> CLV > 0.
    better = grade_one({**base, "taken_decimal": 2.50}, game,
                       _line_store_base=tmp_path)
    assert better["clv_pct"] > 0.0
    assert better["beat_close"] is True

    # WORSE than close: taken 1.60 (implied 0.625) > fair away (~0.46) -> CLV < 0.
    worse = grade_one({**base, "taken_decimal": 1.60}, game,
                      _line_store_base=tmp_path)
    assert worse["clv_pct"] < 0.0
    assert worse["beat_close"] is False
