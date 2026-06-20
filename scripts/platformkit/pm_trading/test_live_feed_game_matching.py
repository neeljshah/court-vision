"""test_live_feed_game_matching.py -- per-file tests for WS2 PM game matching.

Acceptance contract (workstream WS2-pm-game-market-matching):
  1. A single-sided "Will <SlateTeam> win" YES contract with a Yes price maps to
     the corresponding moneyline side (pm_prob = Yes price) and links via
     normalized team name (canonical key).
  2. A non-sports binary contract (e.g. "Will it rain?") is suppressed and does
     NOT produce a pair row.
  3. active_pairs() returns the matched pair row with pm_prob = Yes price and
     no dollar fields.
  4. Full-name vs short-code cross-matching works: Kalshi "Boston Celtics"
     matches slate "BOS" via canonical key; raw-upper fallback would miss this.
  5. Away-side binary contract resolves correctly (pm_prob = away YES price).
  6. Binary for a team not on the slate is suppressed.

Run:
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/pm_trading/test_live_feed_game_matching.py -q
"""
from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_HERE), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_feed as LF  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({"dollar_pnl", "pnl_usd", "dollar", "pnl",
                           "roi", "profit", "dollar_stake"})


def _fake_predict(sport, home, away):
    """Deterministic 0.62 home-win prob for every game (no real model needed)."""
    return {"p_home_win": 0.62}


def _nba_game_bos_mia():
    """NBA game with SHORT CODE team identifiers (as the slate carries them)."""
    return LF.Game("nba", "BOS", "MIA", game_id="g-nba-1", game_date="2026-06-20")


def _mlb_game_nyy_bos():
    return LF.Game("mlb", "NYY", "BOS", game_id="g-mlb-1", game_date="2026-06-20")


# ---------------------------------------------------------------------------
# _canonical_key unit tests
# ---------------------------------------------------------------------------

def test_canonical_key_nba_short_code():
    """canonical_key("nba", "BOS") should yield nba:celtics."""
    key = LF._canonical_key("nba", "BOS")
    assert key == "nba:celtics", "short code BOS -> nba:celtics; got %s" % key


def test_canonical_key_nba_full_name():
    """canonical_key("nba", "Boston Celtics") should yield nba:celtics."""
    key = LF._canonical_key("nba", "Boston Celtics")
    assert key == "nba:celtics", "full name -> nba:celtics; got %s" % key


def test_canonical_key_nba_full_equals_short():
    """Full name and short code must map to the SAME canonical key."""
    assert LF._canonical_key("nba", "BOS") == LF._canonical_key("nba", "Boston Celtics")
    assert LF._canonical_key("nba", "MIA") == LF._canonical_key("nba", "Miami Heat")
    assert LF._canonical_key("mlb", "NYY") == LF._canonical_key("mlb", "New York Yankees")


def test_canonical_key_mlb_short_code():
    key = LF._canonical_key("mlb", "NYY")
    assert key == "mlb:yankees", "NYY -> mlb:yankees; got %s" % key


# ---------------------------------------------------------------------------
# _parse_binary_contract unit tests
# ---------------------------------------------------------------------------

def test_parse_binary_will_team_win_home():
    """'Will Boston Celtics win' YES=0.65 vs BOS/MIA slate -> home side, 0.65."""
    result = LF._parse_binary_contract(
        "Will Boston Celtics win?", 0.65, "nba", "BOS", "MIA")
    assert result is not None, "_parse_binary_contract should not return None"
    pm_prob, side = result
    assert abs(pm_prob - 0.65) < 1e-9
    assert side == "home"


def test_parse_binary_will_team_win_away():
    """'Will Miami Heat win' YES=0.38 vs BOS/MIA slate -> away side, 0.38."""
    result = LF._parse_binary_contract(
        "Will Miami Heat win?", 0.38, "nba", "BOS", "MIA")
    assert result is not None
    pm_prob, side = result
    assert abs(pm_prob - 0.38) < 1e-9
    assert side == "away"


def test_parse_binary_team_to_win_pattern():
    """'Celtics to win' YES=0.62 -> home side for BOS/MIA slate."""
    result = LF._parse_binary_contract(
        "Celtics to win", 0.62, "nba", "BOS", "MIA")
    assert result is not None
    _pm_prob, side = result
    assert side == "home"


def test_parse_binary_team_wins_pattern():
    """'Yankees wins' YES=0.55 -> home for NYY/BOS MLB slate."""
    result = LF._parse_binary_contract(
        "Yankees wins", 0.55, "mlb", "NYY", "BOS")
    assert result is not None
    _pm_prob, side = result
    assert side == "home"


def test_parse_binary_non_sports_suppressed():
    """'Will it rain tomorrow?' does not match any slate team -> None."""
    result = LF._parse_binary_contract(
        "Will it rain tomorrow?", 0.70, "nba", "BOS", "MIA")
    assert result is None, "non-sports title must be suppressed (return None)"


def test_parse_binary_unknown_team_suppressed():
    """'Will the Lakers win?' does not match BOS/MIA slate -> None."""
    result = LF._parse_binary_contract(
        "Will the Lakers win?", 0.50, "nba", "BOS", "MIA")
    assert result is None, "unmatched team must be suppressed (return None)"


def test_parse_binary_yes_prob_out_of_range():
    """yes_prob=0.0 and yes_prob=1.0 both return None (degenerate)."""
    assert LF._parse_binary_contract("Will BOS win?", 0.0, "nba", "BOS", "MIA") is None
    assert LF._parse_binary_contract("Will BOS win?", 1.0, "nba", "BOS", "MIA") is None
    assert LF._parse_binary_contract("Will BOS win?", 1.5, "nba", "BOS", "MIA") is None


# ---------------------------------------------------------------------------
# active_pairs with binary contracts
# ---------------------------------------------------------------------------

class _MockBinaryProvider(LF.PMProvider):
    """Injects a list of single-sided binary PM market dicts."""

    def __init__(self, markets):
        self._markets = list(markets)

    def fetch_markets(self):
        return list(self._markets)


def _binary_market(title: str, yes_prob: float, sport: str = "nba",
                   market_id: str = "BM-1") -> dict:
    """Build a single-sided binary PM market row (as _single_binary_to_pm_market returns)."""
    return LF._single_binary_to_pm_market(market_id, sport, title, yes_prob)


def test_active_pairs_binary_home_side_matched():
    """'Will Boston Celtics win' binary YES=0.65 -> pair row pm_prob=0.65."""
    m = _binary_market("Will Boston Celtics win?", 0.65, sport="nba")
    assert m is not None, "_single_binary_to_pm_market returned None"
    rows = LF.active_pairs(
        now=1_700_000_000.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert len(rows) == 1, "expected 1 pair row; got %d" % len(rows)
    row = rows[0]
    assert abs(row["pm_prob"] - 0.65) < 1e-9, (
        "pm_prob must equal the YES price 0.65; got %s" % row["pm_prob"])
    assert abs(row["model_prob"] - 0.62) < 1e-6
    assert row["sport"] == "nba"
    assert row["home"] == "BOS"
    assert row["away"] == "MIA"
    assert row["clv_status"] == "INSUFFICIENT_DATA"
    bad = _DOLLAR_KEYS & set(row.keys())
    assert not bad, "$ field(s) leaked into binary pair row: %s" % sorted(bad)


def test_active_pairs_binary_away_side_matched():
    """'Will Miami Heat win' YES=0.38 -> pair row pm_prob=0.38."""
    m = _binary_market("Will Miami Heat win?", 0.38, sport="nba", market_id="BM-MIA")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert len(rows) == 1, "away-side binary must produce a pair row"
    assert abs(rows[0]["pm_prob"] - 0.38) < 1e-9


def test_active_pairs_non_sports_binary_suppressed():
    """'Will it rain?' binary must NOT produce any pair row."""
    m = _binary_market("Will it rain tomorrow?", 0.80, sport="nba", market_id="BM-RAIN")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert rows == [], "non-sports binary must be suppressed; got %s" % rows


def test_active_pairs_canonical_fullname_matches_shortcode_slate():
    """Two-leg market with full team names links to a short-code slate game."""
    # Kalshi emits full names; our slate has short codes -- canonical key bridges.
    pm_two_leg = {
        "market_id": "KALSHI-NBA-BOS-MIA",
        "sport": "nba",
        "home": "Boston Celtics",   # full name from Kalshi
        "away": "Miami Heat",
        "pm_prob": 0.60,
        "binary_title": None,
    }
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([pm_two_leg])],
    )
    assert len(rows) == 1, (
        "full-name PM market must match short-code slate via canonical key")
    assert rows[0]["market_id"] == "KALSHI-NBA-BOS-MIA"
    assert abs(rows[0]["pm_prob"] - 0.60) < 1e-9


def test_active_pairs_binary_unknown_team_no_row():
    """Binary for 'Lakers' does not match BOS/MIA slate -> no row."""
    m = _binary_market("Will the Lakers win?", 0.50, sport="nba", market_id="BM-LAL")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert rows == [], "unmatched binary team must produce no row"


def test_active_pairs_binary_no_dollar_fields():
    """Binary-matched pair rows must never contain $ / P&L fields."""
    m = _binary_market("Will Boston Celtics win?", 0.65, sport="nba")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert rows, "need at least one row to check keys"
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ field(s) in row: %s" % sorted(bad)


def test_active_pairs_binary_market_id_preserved():
    """market_id from the binary contract is carried through to the pair row."""
    m = _binary_market("Will Boston Celtics win?", 0.65, sport="nba",
                       market_id="POLY-BOS-WIN-20260620")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert rows
    assert rows[0]["market_id"] == "POLY-BOS-WIN-20260620"


def test_active_pairs_clv_status_insufficient():
    """active_pairs always sets clv_status=INSUFFICIENT_DATA for PM pairs."""
    m = _binary_market("Will Boston Celtics win?", 0.65, sport="nba")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    for row in rows:
        assert row.get("clv_status") == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_single_binary_to_pm_market_invalid_prob():
    """_single_binary_to_pm_market returns None for yes_prob <= 0 or >= 1."""
    assert LF._single_binary_to_pm_market("ID1", "nba", "Will BOS win?", 0.0) is None
    assert LF._single_binary_to_pm_market("ID2", "nba", "Will BOS win?", 1.0) is None
    assert LF._single_binary_to_pm_market("ID3", "nba", "Will BOS win?", -0.1) is None
    assert LF._single_binary_to_pm_market("ID4", "nba", "Will BOS win?", 1.1) is None


def test_single_binary_to_pm_market_valid():
    """_single_binary_to_pm_market returns a partial row for a valid yes_prob."""
    row = LF._single_binary_to_pm_market("BM-99", "nba", "Will BOS win?", 0.65)
    assert row is not None
    assert row["market_id"] == "BM-99"
    assert row["sport"] == "nba"
    assert row["binary_title"] == "Will BOS win?"
    assert abs(row["binary_yes_prob"] - 0.65) < 1e-9
    # home/away/pm_prob are None until active_pairs resolves them
    assert row["home"] is None
    assert row["away"] is None
    assert row["pm_prob"] is None


def test_active_pairs_empty_when_no_games():
    """Honest empty: active_pairs returns [] when there are no games."""
    m = _binary_market("Will Boston Celtics win?", 0.65, sport="nba")
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([m])],
    )
    assert rows == []


def test_active_pairs_empty_when_no_pm_markets():
    """Honest empty: active_pairs returns [] when providers yield no markets."""
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([_nba_game_bos_mia()])],
        predict_fn=_fake_predict,
        pm_providers=[_MockBinaryProvider([])],
    )
    assert rows == []


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import inspect
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and inspect.isfunction(v)]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
            passed += 1
        except Exception as exc:
            print("FAIL", name, "->", exc)
    print("%d/%d green" % (passed, len(tests)))
