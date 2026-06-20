"""Per-file tests for live_feed.active_pairs.

Verifies the core contract from the workstream spec:
  - active_pairs returns rows (model_prob, pm_prob, no dollar_pnl/pnl_usd)
    when given mock PM markets.
  - active_pairs returns [] when the injected providers yield 0 events.
  - Rows are never polluted with $ / P&L keys.

Run:
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/pm_trading/test_live_feed_active_pairs.py -q
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
# helpers
# ---------------------------------------------------------------------------

def _fake_predict(sport, home, away):
    """Deterministic calibrated prob; NOPROB home -> no prediction."""
    if home == "NOPROB":
        return {}
    return {"p_home_win": 0.62}


def _mlb_games():
    return [
        LF.Game("mlb", "NYY", "BOS", game_id="g1", game_date="2026-06-20"),
        LF.Game("mlb", "LAD", "SFG", game_id="g2", game_date="2026-06-20"),
    ]


class MockPMProvider(LF.PMProvider):
    """Injects a fixed list of PM markets for tests."""

    def __init__(self, markets):
        self._markets = list(markets)

    def fetch_markets(self):
        return list(self._markets)


def _pm_markets_for_g1():
    """Return one PM market matching game g1 (NYY vs BOS)."""
    return [{
        "market_id": "KALSHI-MLB-NYY-BOS-20260620",
        "game_id": "g1",
        "sport": "mlb",
        "home": "NYY",
        "away": "BOS",
        "pm_prob": 0.55,
    }]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_active_pairs_returns_rows_when_pm_market_exists():
    """When a PM market matches a game with a model prob, a pair row is returned."""
    rows = LF.active_pairs(
        now=1_700_000_000.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(_pm_markets_for_g1())],
    )
    assert len(rows) == 1, "expected 1 pair row (only g1 has a PM market)"
    row = rows[0]
    assert "model_prob" in row, "row must carry model_prob"
    assert "pm_prob" in row, "row must carry pm_prob"
    assert abs(row["model_prob"] - 0.62) < 1e-6
    assert abs(row["pm_prob"] - 0.55) < 1e-6
    assert row["sport"] == "mlb"
    assert row["home"] == "NYY"
    assert row["away"] == "BOS"
    assert row["market_id"] == "KALSHI-MLB-NYY-BOS-20260620"
    assert row["tier"] == "model_vs_pm"
    assert row["clv_status"] == "INSUFFICIENT_DATA"
    assert abs(row["captured_at"] - 1_700_000_000.0) < 1.0


def test_active_pairs_no_dollar_fields():
    """Rows must never contain dollar_pnl, pnl_usd, or any $ key."""
    _DOLLAR_KEYS = {"dollar_pnl", "pnl_usd", "dollar", "pnl", "roi",
                    "profit", "dollar_stake"}
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(_pm_markets_for_g1())],
    )
    assert rows, "need at least one row to check keys"
    for row in rows:
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ field(s) leaked into active_pairs row: %s" % sorted(bad)


def test_active_pairs_empty_when_no_pm_markets():
    """When providers yield 0 markets, active_pairs returns []."""
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider([])],  # zero PM markets
    )
    assert rows == [], "expected [] when providers return no markets"


def test_active_pairs_empty_when_no_games():
    """When the game source is empty, active_pairs returns []."""
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([])],  # zero games
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(_pm_markets_for_g1())],
    )
    assert rows == [], "expected [] when no games"


def test_active_pairs_skips_game_with_no_model_prob():
    """A game whose predict_fn returns {} is skipped (not errored)."""
    games = [LF.Game("mlb", "NOPROB", "BOS", game_id="g3")]
    pm = [{"market_id": "M3", "game_id": "g3", "sport": "mlb",
           "home": "NOPROB", "away": "BOS", "pm_prob": 0.5}]
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(games)],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm)],
    )
    assert rows == [], "game with no model prob must be silently skipped"


def test_active_pairs_skips_game_with_no_matching_pm_market():
    """A game with a model prob but no PM market is silently skipped."""
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource([LF.Game("mlb", "LAD", "SFG", game_id="g2")])],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(_pm_markets_for_g1())],  # g1 only
    )
    assert rows == [], "unmatched game must not produce a row"


def test_active_pairs_matchup_fallback_match():
    """When game_id is absent, active_pairs matches on (sport, home, away)."""
    # Game has no game_id; PM market has no game_id but matching sport/home/away.
    games = [LF.Game("mlb", "NYY", "BOS", game_id="")]
    pm = [{"market_id": "M-MATCHUP", "sport": "mlb",
           "home": "NYY", "away": "BOS", "pm_prob": 0.48}]
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(games)],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm)],
    )
    assert len(rows) == 1
    assert rows[0]["pm_prob"] == 0.48


def test_active_pairs_strips_injected_dollar_keys():
    """Even if a provider accidentally injects $ keys they are stripped."""
    pm = [{
        "market_id": "M-BAD",
        "game_id": "g1",
        "sport": "mlb",
        "home": "NYY",
        "away": "BOS",
        "pm_prob": 0.50,
        "dollar_pnl": 999.0,    # should be stripped
        "pnl_usd": 42.0,        # should be stripped
    }]
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm)],
    )
    assert rows, "expected a row"
    assert "dollar_pnl" not in rows[0]
    assert "pnl_usd" not in rows[0]


def test_active_pairs_multiple_providers_deduplicated():
    """Two providers each returning the same game -> only one row per game."""
    pm_a = [{"market_id": "MA", "game_id": "g1",
              "sport": "mlb", "home": "NYY", "away": "BOS", "pm_prob": 0.55}]
    pm_b = [{"market_id": "MB", "game_id": "g1",
              "sport": "mlb", "home": "NYY", "away": "BOS", "pm_prob": 0.53}]
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm_a), MockPMProvider(pm_b)],
    )
    # Both providers match the same game_id; the FIRST match wins (one row out).
    assert len(rows) == 1


def test_active_pairs_provider_that_raises_is_tolerated():
    """A PM provider that raises must not crash active_pairs."""

    class BoomProvider(LF.PMProvider):
        def fetch_markets(self):
            raise RuntimeError("network down")

    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[BoomProvider(), MockPMProvider(_pm_markets_for_g1())],
    )
    # BoomProvider raised, but the second provider still delivers.
    assert len(rows) == 1


def test_active_pairs_rejects_pm_prob_out_of_range():
    """A PM market with pm_prob outside [0, 1] is silently skipped."""
    pm = [{"market_id": "M-BAD", "game_id": "g1",
           "sport": "mlb", "home": "NYY", "away": "BOS",
           "pm_prob": 1.5}]  # invalid
    rows = LF.active_pairs(
        now=0.0,
        sources=[LF.MockGamesSource(_mlb_games())],
        predict_fn=_fake_predict,
        pm_providers=[MockPMProvider(pm)],
    )
    assert rows == [], "out-of-range pm_prob must be skipped"


# ---------------------------------------------------------------------------
# standalone runner
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
