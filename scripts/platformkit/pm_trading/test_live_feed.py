"""test_live_feed.py -- per-file tests for live_feed.active_pairs.

Acceptance contract (workstream W4-pm-paper-real-trades):
  1. With a mock provider supplying one liquid per-game binary market matched to
     a game, active_pairs() returns >= 1 pair row with model_prob, pm_prob,
     clv_status=INSUFFICIENT_DATA, and no dollar/pnl/roi key.
  2. With no matching market, active_pairs() returns [].
  3. A futures/series/championship contract is rejected by Path-4.
  4. venue is propagated from the PM market row onto every pair row.
  5. freshness_captured_epoch is stamped on every pair row.
  6. is_pm / executed are NOT present on active_pairs rows (those are stamped
     by pm_paper_tick_runner._coerce_row, not by active_pairs).

Run:
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest scripts/platformkit/pm_trading/test_live_feed.py -q
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
# Shared constants
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({
    "dollar_pnl", "pnl_usd", "dollar", "dollars", "pnl", "roi",
    "profit", "dollar_stake", "dollar_value", "net_pnl",
    "realized_pnl", "unrealized_pnl",
})

_NOW = 1_750_000_000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_predict(sport, home, away):
    """Deterministic calibrated prob. NOPROB -> no prediction."""
    if home == "NOPROB":
        return {}
    return {"p_home_win": 0.62}


class MockPMProvider(LF.PMProvider):
    def __init__(self, markets):
        self._markets = list(markets)

    def fetch_markets(self):
        return list(self._markets)


def _mlb_games():
    return [
        LF.Game("mlb", "NYY", "BOS", game_id="g1", game_date="2026-06-20"),
        LF.Game("mlb", "LAD", "SFG", game_id="g2", game_date="2026-06-20"),
    ]


def _pm_market_g1(venue="kalshi"):
    """One PM market matching game g1 (NYY vs BOS mlb) with venue stamped."""
    return {
        "market_id": "KXMLB-NYY-BOS-20260620",
        "game_id": "g1",
        "sport": "mlb",
        "home": "NYY",
        "away": "BOS",
        "pm_prob": 0.55,
        "venue": venue,
    }


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

def test_active_pairs_returns_rows_when_pm_market_exists():
    """Liquid per-game market matched to a game -> >= 1 pair row returned."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([_pm_market_g1()])],
    )
    assert len(rows) >= 1, "expected >= 1 pair row"
    row = rows[0]
    assert abs(row["model_prob"] - 0.62) < 1e-6, "model_prob mismatch"
    assert abs(row["pm_prob"] - 0.55) < 1e-6, "pm_prob mismatch"
    assert row["sport"] == "mlb"
    assert row["home"] == "NYY"
    assert row["away"] == "BOS"
    assert row["tier"] == "model_vs_pm"
    assert row["clv_status"] == "INSUFFICIENT_DATA"
    assert abs(row["captured_at"] - _NOW) < 1.0, "captured_at mismatch"


def test_active_pairs_empty_when_no_matching_market():
    """No PM market matching any slate game -> [] (honest empty)."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([])],
    )
    assert rows == [], "expected [] when no matching PM market"


def test_active_pairs_empty_when_no_games():
    """Empty game slate -> []."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource([])],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([_pm_market_g1()])],
    )
    assert rows == [], "expected [] when no games"


def test_active_pairs_no_dollar_keys():
    """No dollar/pnl/roi key must appear in any row."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([_pm_market_g1()])],
    )
    assert rows, "need at least one row"
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ key(s) leaked into active_pairs row: %s" % sorted(bad)


def test_active_pairs_clv_status_always_insufficient_data():
    """clv_status must be INSUFFICIENT_DATA on every row."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([_pm_market_g1()])],
    )
    for row in rows:
        assert row.get("clv_status") == "INSUFFICIENT_DATA", (
            "clv_status must be INSUFFICIENT_DATA; got %r" % row.get("clv_status")
        )


def test_active_pairs_propagates_venue_from_market_row():
    """venue stamped on the PM market row is propagated onto the pair row."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([_pm_market_g1(venue="kalshi")])],
    )
    assert rows, "need at least one row"
    assert rows[0].get("venue") == "kalshi", (
        "venue must be propagated from PM market; got %r" % rows[0].get("venue")
    )


def test_active_pairs_stamps_freshness_epoch():
    """freshness_captured_epoch must be present and match the now argument."""
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([_pm_market_g1()])],
    )
    assert rows, "need at least one row"
    assert "freshness_captured_epoch" in rows[0], "freshness_captured_epoch missing"
    assert abs(rows[0]["freshness_captured_epoch"] - _NOW) < 1.0


# ---------------------------------------------------------------------------
# Futures / championship rejection
# ---------------------------------------------------------------------------

def test_active_pairs_rejects_championship_binary_via_path4():
    """Path-4 futures gate must suppress championship/season-long contracts.

    A 'Will team win the championship?' YES price is a season-long prob, NOT
    a per-game win probability.  Pairing it against a per-game model prob is
    misleading and must be blocked by _FUTURES_EXCLUDE_RE.
    """
    championship_binary = {
        "market_id": "poly-nba-win-championship",
        "sport": "nba",
        "home": None,
        "away": None,
        "pm_prob": None,
        "binary_title": "Will the Boston Celtics win the NBA championship?",
        "binary_yes_prob": 0.65,
        "venue": "polymarket",
    }
    game = LF.Game("nba", "Boston Celtics", "Miami Heat",
                   game_id="bos-mia-001", game_date="2026-06-20")
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource([game])],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([championship_binary])],
    )
    assert rows == [], (
        "championship/futures contract must be rejected by Path-4 futures gate"
    )


def test_active_pairs_rejects_series_binary_via_path4():
    """'Will team win the series?' is also a multi-game contract -- reject it."""
    series_binary = {
        "market_id": "poly-nba-series-win",
        "sport": "nba",
        "home": None,
        "away": None,
        "pm_prob": None,
        "binary_title": "Will the Celtics win the series?",
        "binary_yes_prob": 0.58,
        "venue": "polymarket",
    }
    game = LF.Game("nba", "Boston Celtics", "Miami Heat",
                   game_id="bos-mia-002", game_date="2026-06-20")
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource([game])],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([series_binary])],
    )
    assert rows == [], "series contract must be rejected by futures gate"


def test_active_pairs_accepts_per_game_binary_via_path4():
    """'Will team win tonight?' is a per-game binary -- it must be accepted."""
    game_binary = {
        "market_id": "poly-nba-win-tonight",
        "sport": "nba",
        "home": None,
        "away": None,
        "pm_prob": None,
        "binary_title": "Will the Boston Celtics win tonight?",
        "binary_yes_prob": 0.65,
        "venue": "polymarket",
    }
    game = LF.Game("nba", "Boston Celtics", "Miami Heat",
                   game_id="bos-mia-003", game_date="2026-06-20")
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource([game])],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([game_binary])],
    )
    assert len(rows) >= 1, (
        "per-game binary 'win tonight' must route through Path-4 and produce a row"
    )
    assert rows[0]["clv_status"] == "INSUFFICIENT_DATA"
    bad = _DOLLAR_KEYS & set(rows[0].keys())
    assert not bad, "$ key(s) in Path-4 row: %s" % sorted(bad)


def test_active_pairs_rejects_pm_prob_out_of_range():
    """pm_prob outside (0, 1) is silently skipped (no crash, no row)."""
    bad_mkt = dict(_pm_market_g1())
    bad_mkt["pm_prob"] = 1.5  # invalid
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([bad_mkt])],
    )
    assert rows == [], "out-of-range pm_prob must be silently skipped"


def test_active_pairs_skips_game_with_no_model_prob():
    """A game whose predict_fn returns {} is silently skipped."""
    games = [LF.Game("mlb", "NOPROB", "BOS", game_id="g3")]
    pm = [{"market_id": "M3", "game_id": "g3", "sport": "mlb",
           "home": "NOPROB", "away": "BOS", "pm_prob": 0.5, "venue": "kalshi"}]
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(games)],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm)],
    )
    assert rows == [], "game with no model prob must be silently skipped"


def test_active_pairs_tolerates_provider_that_raises():
    """A PM provider that raises must not crash active_pairs."""
    class BoomProvider(LF.PMProvider):
        def fetch_markets(self):
            raise RuntimeError("network down")

    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[BoomProvider(), MockPMProvider([_pm_market_g1()])],
    )
    assert len(rows) == 1, "BoomProvider raised but second provider must still deliver"


def test_active_pairs_deduplicates_multiple_providers():
    """Two providers matching the same game -> only one row (first match wins)."""
    pm_a = [dict(_pm_market_g1(venue="kalshi"))]
    pm_b = [dict(_pm_market_g1(venue="kalshi"))]
    pm_b[0]["market_id"] = "DUPLICATE-MKT"
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm_a), MockPMProvider(pm_b)],
    )
    assert len(rows) == 1, "duplicate game match must be deduplicated"


# ---------------------------------------------------------------------------
# W4-pm-paper-live-wiring: is_pm-eligible venue + ledger-write guard
# ---------------------------------------------------------------------------

def test_active_pairs_per_game_binary_has_pm_eligible_venue():
    """W4: per-game binary match -> row.venue in {kalshi, polymarket}.

    is_pm-eligible venues are the only ones pm_paper_tick_runner._coerce_row
    accepts.  Verifying venue here ensures the live-feed pair can reach the
    ledger without being silently dropped by the coercer.
    Uses a structured PM market with home/away set so matching uses Path-1/2.
    """
    _PM_VENUES = frozenset({"kalshi", "polymarket"})
    # Use a structured market (game_id match = Path-1) with polymarket venue
    structured_pm = {
        "market_id": "poly-mlb-nyy-bos-20260620",
        "game_id": "g-venue-test",
        "sport": "mlb",
        "home": "NYY",
        "away": "BOS",
        "pm_prob": 0.60,
        "venue": "polymarket",
    }
    game = LF.Game("mlb", "NYY", "BOS", game_id="g-venue-test",
                   game_date="2026-06-20")
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource([game])],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([structured_pm])],
    )
    assert len(rows) >= 1, "per-game market must produce at least one pair row"
    for row in rows:
        v = row.get("venue", "")
        assert v in _PM_VENUES, (
            "W4: pair row venue must be PM-eligible (kalshi|polymarket); got %r" % v
        )


def test_active_pairs_empty_provider_zero_rows_no_dollar_keys():
    """W4: empty provider -> active_pairs returns [] (honest-empty, zero writes).

    Confirmed that active_pairs returns the empty list when no PM market matches --
    no row is produced, so the ledger tick loop cannot write anything.
    """
    rows = LF.active_pairs(
        now=_NOW,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([])],
    )
    assert rows == [], "W4: empty provider must return [] (honest-empty)"
    # trivially no $ keys when list is empty, but verify the contract explicitly
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ key(s) in row from empty provider: %s" % sorted(bad)


def test_active_pairs_real_pm_provider_wired_via_default_providers():
    """W4: _default_pm_providers() returns at least Kalshi+Polymarket provider instances.

    Verifies that the live-feed wiring calls the real keyless REST providers
    (KalshiPMProvider, PolymarketPMProvider) when no pm_providers are injected.
    This is the 'real-provider wiring' assertion without making a network call.
    """
    providers = LF._default_pm_providers()
    names = [type(p).__name__ for p in providers]
    assert "KalshiPMProvider" in names, (
        "W4: KalshiPMProvider must be in _default_pm_providers()"
    )
    assert "PolymarketPMProvider" in names, (
        "W4: PolymarketPMProvider must be in _default_pm_providers()"
    )


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
