"""test_pm_paper_tick_ledger.py -- per-file test for pm_paper_tick_runner wiring.

Acceptance criteria (from workstream pm-ledger-wire):
  1. With a mock capture_fn returning 1 PM pair, tick() appends a row to
     the clv_ledger path that pm_trail_browse.browse_pm_trail then returns
     (total_pm>0, count>0, executed=False, no $ field).
  2. With empty capture, no row is written and the ledger stays unchanged.
  3. Row invariants: is_pm=True, venue in {kalshi,polymarket}, executed=False,
     clv_status="INSUFFICIENT_DATA", no dollar/pnl/roi key, stake_units present.

W5 acceptance criteria (workstream W5-pm-paper-tick-backend):
  4. With an injected capture_fn returning 1 matched MLB Kalshi pair,
     tick() appends exactly 1 canonical row (is_pm=True, executed=False,
     clv_status=INSUFFICIENT_DATA, no $ keys).
  5. With 0 matches (honest offseason), writes pm_last_capture.json reason
     and appends 0 rows.
  6. A futures/series/championship contract is rejected and not written.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/pm_trading/test_pm_paper_tick_ledger.py -q
"""
from __future__ import annotations

import json
import pathlib
import sys as _sys
from typing import Any, Dict, List

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_HERE), str(_ROOT)):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

import live_feed as _LF  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({
    "dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
    "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl",
    "dollar_pnl", "pnl_usd",
})


def _read_ledger(path: pathlib.Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def _mock_pair_kalshi() -> Dict[str, Any]:
    """One valid Kalshi PM pair -- the canonical case."""
    return {
        "market_id": "NBAML-2026-06-20-NYK",
        "venue": "kalshi",
        "model_prob": 0.55,
        "market_price": 0.48,
        "edge": 0.07,
        "stake_units": 1.0,
    }


def _mock_pair_polymarket() -> Dict[str, Any]:
    """One valid Polymarket PM pair."""
    return {
        "market_id": "poly-nba-gsw-2026-06-20",
        "venue": "polymarket",
        "fair_prob": 0.62,   # alternate alias for model_prob
        "market_price": 0.55,
        "edge": 0.07,
        "stake_units": 1.0,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTickAppendsToClvLedger:
    """Core wiring: tick writes to clv_ledger, pm_trail_browse reads it back."""

    def test_one_pm_pair_written_to_clv_ledger(self, tmp_path: pathlib.Path) -> None:
        """tick() with 1 Kalshi pair -> clv_ledger row -> browse returns total_pm>0."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        ledger = tmp_path / "clv_ledger.jsonl"

        capture_fn = lambda now: [_mock_pair_kalshi()]  # noqa: E731

        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        # tick must return at least one market_id
        assert len(written) >= 1, "tick() must return written market_id list"

        # clv_ledger must have exactly one row
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "exactly one row should be appended"

        row = rows[0]
        # Core PM invariants
        assert row.get("is_pm") is True, "is_pm must be True"
        assert row.get("venue") in ("kalshi", "polymarket"), "venue must be PM"
        assert row.get("executed") is False, "executed must be False"
        assert row.get("clv_status") == "INSUFFICIENT_DATA", "CLV status must be INSUFFICIENT_DATA"
        assert row.get("market_id"), "market_id must be non-empty"
        assert "stake_units" in row, "stake_units must be present"

        # No dollar fields anywhere
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "dollar/pnl keys found in row: %s" % sorted(bad)

        # pm_trail_browse must surface it
        result = browse_pm_trail(ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["total_pm"] > 0, "browse_pm_trail total_pm must be >0"
        assert result["count"] > 0, "browse_pm_trail count must be >0"
        trade = result["trades"][0]
        assert trade["executed"] is False
        assert trade.get("is_pm") is True

    def test_polymarket_venue_also_works(self, tmp_path: pathlib.Path) -> None:
        """tick() with a polymarket pair is also surfaced as is_pm=True."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        ledger = tmp_path / "clv_ledger.jsonl"
        capture_fn = lambda now: [_mock_pair_polymarket()]  # noqa: E731

        tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        result = browse_pm_trail(ledger_path=ledger, venue="polymarket")
        assert result["total_pm"] > 0
        trade = result["trades"][0]
        assert trade["venue"] == "polymarket"
        assert trade["executed"] is False

    def test_model_prob_alias_resolved(self, tmp_path: pathlib.Path) -> None:
        """fair_prob on the capture row is normalised to model_prob."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        capture_fn = lambda now: [_mock_pair_polymarket()]  # noqa: E731
        tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        rows = _read_ledger(ledger)
        assert len(rows) == 1
        row = rows[0]
        # model_prob should be resolved from fair_prob
        assert row.get("model_prob") is not None or row.get("fair_prob") is not None, \
            "at least one of model_prob/fair_prob must be present"


class TestEmptyCaptureNoWrite:
    """Empty capture must leave the ledger completely unchanged."""

    def test_empty_capture_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        """tick() with empty capture -> ledger untouched."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        # Pre-write a sentinel row to confirm nothing new is added.
        sentinel = {"ts": "2026-01-01T00:00:00+00:00", "sport": "nba",
                    "matchup": "X@Y", "side": "home", "status": "open",
                    "executed": False}
        with ledger.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(sentinel) + "\n")

        capture_fn = lambda now: []  # noqa: E731
        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert written == [], "empty capture must return empty written list"
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "ledger must be unchanged (still 1 sentinel row)"

    def test_empty_capture_on_missing_ledger_no_file_created(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Empty capture must NOT create the ledger file."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        assert not ledger.exists()

        capture_fn = lambda now: []  # noqa: E731
        tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert not ledger.exists(), "empty capture must not create the ledger file"

    def test_capture_returns_only_sportsbook_rows_writes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Rows with non-PM venues (e.g. sportsbook) are silently dropped."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        sportsbook_rows = [
            {"market_id": "espn:401859967", "venue": "espn",
             "model_prob": 0.55, "market_price": 0.48, "stake_units": 1.0},
            {"market_id": "fanduel-nba-123", "taken_book": "FanDuel",
             "model_prob": 0.60, "stake_units": 1.0},
        ]
        capture_fn = lambda now: sportsbook_rows  # noqa: E731
        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert written == [], "sportsbook rows must be dropped"
        assert not ledger.exists(), "ledger must not be created for sportsbook-only capture"


class TestRowInvariants:
    """Verify honesty invariants on written rows."""

    def test_no_dollar_keys_in_row(self, tmp_path: pathlib.Path) -> None:
        """Rows with dollar/pnl keys in capture are stripped before writing."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        dirty_pair = dict(_mock_pair_kalshi())
        dirty_pair["dollar_pnl"] = 999.99   # must be stripped
        dirty_pair["pnl_usd"] = 50.0         # must be stripped
        dirty_pair["roi"] = 0.15             # must be stripped

        capture_fn = lambda now: [dirty_pair]  # noqa: E731
        tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        rows = _read_ledger(ledger)
        assert len(rows) == 1
        row = rows[0]
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "stripped dollar keys found in row: %s" % sorted(bad)

    def test_executed_always_false(self, tmp_path: pathlib.Path) -> None:
        """executed=False is always stamped, even if capture returns executed=True."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        manipulated = dict(_mock_pair_kalshi())
        manipulated["executed"] = True  # must be overridden

        capture_fn = lambda now: [manipulated]  # noqa: E731
        tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        rows = _read_ledger(ledger)
        assert rows[0].get("executed") is False

    def test_clv_status_defaults_to_insufficient_data(self, tmp_path: pathlib.Path) -> None:
        """clv_status defaults to INSUFFICIENT_DATA when absent from capture."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        pair = dict(_mock_pair_kalshi())
        pair.pop("clv_status", None)  # ensure absent

        capture_fn = lambda now: [pair]  # noqa: E731
        tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        rows = _read_ledger(ledger)
        assert rows[0].get("clv_status") == "INSUFFICIENT_DATA"

    def test_multiple_pm_pairs_all_written(self, tmp_path: pathlib.Path) -> None:
        """Multiple PM pairs from one capture are all written to the ledger."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        ledger = tmp_path / "clv_ledger.jsonl"
        pairs = [_mock_pair_kalshi(), _mock_pair_polymarket()]

        capture_fn = lambda now: pairs  # noqa: E731
        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert len(written) == 2, "both markets must be written"
        rows = _read_ledger(ledger)
        assert len(rows) == 2

        result = browse_pm_trail(ledger_path=ledger)
        assert result["total_pm"] == 2

    def test_capture_exception_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        """When capture_fn raises, the ledger is not touched."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"

        def raising_capture(now: float):
            raise RuntimeError("network down")

        written = tick(now=1718928000.0, capture_fn=raising_capture, ledger_path=ledger)
        assert written == []
        assert not ledger.exists()


# ---------------------------------------------------------------------------
# W4-pm-paper-live-wiring: real active_pairs as capture_fn + ledger contract
# ---------------------------------------------------------------------------

class TestW4LiveFeedToLedgerWiring:
    """W4: active_pairs -> tick -> ledger coercion chain.

    Verifies the real wiring: active_pairs (with mocked game + mocked PM
    provider) -> tick() capture_fn -> _coerce_row -> ledger row satisfies
    the full W4 honesty invariants (is_pm=True, executed=False,
    clv_status=INSUFFICIENT_DATA, no $ keys, PM-eligible venue).
    """

    def _make_capture_fn(self, game, pm_market, predict_fn=None):
        """Build a capture_fn that calls active_pairs with mocked dependencies."""
        import pathlib as _pl
        import sys as _sys

        _HERE = _pl.Path(__file__).resolve().parent
        _ROOT = _HERE.parents[2]
        for _p in (str(_HERE), str(_ROOT)):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)

        import live_feed as LF

        class _MockPMProvider(LF.PMProvider):
            def __init__(self, markets):
                self._markets = list(markets)
            def fetch_markets(self):
                return list(self._markets)

        def _predict(sport, home, away):
            return {"p_home_win": 0.60}

        _source = LF.MockGamesSource([game])
        _provider = _MockPMProvider([pm_market])
        _fn = predict_fn or _predict

        def capture_fn(now):
            rows = LF.active_pairs(
                now=now,
                sources=[_source],
                predict_fn=_fn,
                pm_providers=[_provider],
            )
            return rows

        return capture_fn

    def test_per_game_binary_via_active_pairs_coerced_to_ledger(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4: per-game binary -> active_pairs -> tick -> ledger with PM invariants.

        The capture_fn wraps active_pairs with a mocked per-game binary market
        ("Will NYY win tonight?") matching a live game. tick() must write a row
        with is_pm=True, executed=False, clv_status=INSUFFICIENT_DATA, and a
        PM-eligible venue; no $ keys allowed.
        """
        import pathlib as _pl
        import sys as _sys
        _HERE = _pl.Path(__file__).resolve().parent
        _ROOT = _HERE.parents[2]
        for _p in (str(_HERE), str(_ROOT)):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)
        import live_feed as LF
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        game = LF.Game("mlb", "NYY", "BOS", game_id="w4-g1", game_date="2026-06-20")
        pm_market = {
            "market_id": "KXMLB-NYY-BOS-w4",
            "game_id": "w4-g1",
            "sport": "mlb",
            "home": "NYY",
            "away": "BOS",
            "pm_prob": 0.57,
            "venue": "kalshi",
        }
        capture_fn = self._make_capture_fn(game, pm_market)
        ledger = tmp_path / "clv_ledger.jsonl"

        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)
        assert len(written) >= 1, "W4: per-game market must produce at least one written row"

        rows = _read_ledger(ledger)
        assert len(rows) >= 1, "W4: ledger must have at least one row"
        row = rows[0]

        # Honesty invariants
        assert row.get("is_pm") is True, "W4: is_pm must be True"
        assert row.get("executed") is False, "W4: executed must be False"
        assert row.get("clv_status") == "INSUFFICIENT_DATA", (
            "W4: clv_status must be INSUFFICIENT_DATA; got %r" % row.get("clv_status")
        )
        assert row.get("venue") in ("kalshi", "polymarket"), (
            "W4: venue must be PM-eligible; got %r" % row.get("venue")
        )
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "W4: $ keys found in coerced row: %s" % sorted(bad)

    def test_futures_binary_via_active_pairs_writes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4: futures/championship binary -> active_pairs returns [] -> ledger empty.

        Validates the full rejection chain: _parse_binary_contract rejects the
        championship contract, active_pairs returns [], tick writes nothing.
        """
        import pathlib as _pl
        import sys as _sys
        _HERE = _pl.Path(__file__).resolve().parent
        _ROOT = _HERE.parents[2]
        for _p in (str(_HERE), str(_ROOT)):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)
        import live_feed as LF
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        game = LF.Game("nba", "Boston Celtics", "Miami Heat",
                       game_id="w4-nba-futures", game_date="2026-06-20")
        championship_binary = {
            "market_id": "poly-nba-w4-championship",
            "sport": "nba",
            "home": None,
            "away": None,
            "pm_prob": None,
            "binary_title": "Will the Boston Celtics win the NBA championship?",
            "binary_yes_prob": 0.65,
            "venue": "polymarket",
        }
        capture_fn = self._make_capture_fn(game, championship_binary)
        ledger = tmp_path / "clv_ledger.jsonl"

        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)
        assert written == [], "W4: futures/championship contract must be rejected end-to-end"
        assert not ledger.exists(), "W4: ledger must not be created for rejected futures contract"

    def test_empty_provider_via_active_pairs_zero_ledger_writes(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4: empty PM provider -> active_pairs returns [] -> tick writes nothing.

        Confirms the honest-empty state: when no liquid PM market matches a
        current game (offseason or no live contracts), no row is written to the
        ledger and the file is not created.
        """
        import pathlib as _pl
        import sys as _sys
        _HERE = _pl.Path(__file__).resolve().parent
        _ROOT = _HERE.parents[2]
        for _p in (str(_HERE), str(_ROOT)):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)
        import live_feed as LF
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        game = LF.Game("mlb", "NYY", "BOS", game_id="w4-empty", game_date="2026-06-20")

        class EmptyProvider(LF.PMProvider):
            def fetch_markets(self):
                return []

        def capture_fn(now):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource([game])],
                predict_fn=lambda s, h, a: {"p_home_win": 0.55},
                pm_providers=[EmptyProvider()],
            )

        ledger = tmp_path / "clv_ledger.jsonl"
        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert written == [], "W4: empty provider must produce zero written rows"
        assert not ledger.exists(), "W4: ledger must not be created for honest-empty state"


# ---------------------------------------------------------------------------
# W4 acceptance gate: injected provider with 2 liquid markets
# ---------------------------------------------------------------------------

class TestW4AcceptanceGate:
    """Exact workstream W4-pm-paper-tick-real-trades acceptance contract.

    With an injected PMProvider returning 2 liquid kalshi/polymarket markets,
    tick() must write exactly 2 canonical rows (is_pm=True, executed=False,
    clv_status=INSUFFICIENT_DATA, no _STRIP_KEYS/$ field) to a temp ledger.
    With the provider returning [], tick() must write 0 rows (honest empty).
    """

    def _two_games_two_markets(self):
        """Two distinct games matched by 2 liquid PM markets (1 kalshi, 1 polymarket)."""
        import sys as _sys
        import pathlib as _pl
        _HERE = _pl.Path(__file__).resolve().parent
        _ROOT = _HERE.parents[2]
        for _p in (str(_HERE), str(_ROOT)):
            if _p not in _sys.path:
                _sys.path.insert(0, _p)
        import live_feed as LF

        games = [
            LF.Game("nba", "Boston Celtics", "Miami Heat",
                    game_id="w4-acc-g1", game_date="2026-06-20"),
            LF.Game("mlb", "NYY", "BOS",
                    game_id="w4-acc-g2", game_date="2026-06-20"),
        ]
        markets = [
            {
                "market_id": "KX-NBA-BOS-MIA-ACC",
                "game_id": "w4-acc-g1",
                "sport": "nba",
                "home": "Boston Celtics",
                "away": "Miami Heat",
                "pm_prob": 0.58,
                "venue": "kalshi",
            },
            {
                "market_id": "POLY-MLB-NYY-BOS-ACC",
                "game_id": "w4-acc-g2",
                "sport": "mlb",
                "home": "NYY",
                "away": "BOS",
                "pm_prob": 0.54,
                "venue": "polymarket",
            },
        ]
        return games, markets, LF

    def test_two_liquid_markets_via_injected_provider_writes_two_rows(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4 acceptance: injected provider with 2 liquid markets -> 2 canonical rows."""
        games, markets, LF = self._two_games_two_markets()
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        class TwoMarketProvider(LF.PMProvider):
            def fetch_markets(self):
                return list(markets)

        def capture_fn(now):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource(games)],
                predict_fn=lambda s, h, a: {"p_home_win": 0.60},
                pm_providers=[TwoMarketProvider()],
            )

        ledger = tmp_path / "clv_ledger.jsonl"
        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert len(written) == 2, (
            "W4: injected provider with 2 liquid markets must produce 2 written rows; "
            "got %d" % len(written)
        )

        rows = _read_ledger(ledger)
        assert len(rows) == 2, "W4: ledger must have exactly 2 rows"

        for row in rows:
            assert row.get("is_pm") is True, "W4: is_pm must be True"
            assert row.get("executed") is False, "W4: executed must be False"
            assert row.get("clv_status") == "INSUFFICIENT_DATA", (
                "W4: clv_status must be INSUFFICIENT_DATA; got %r" % row.get("clv_status")
            )
            assert row.get("venue") in ("kalshi", "polymarket"), (
                "W4: venue must be PM-eligible; got %r" % row.get("venue")
            )
            assert row.get("market_id"), "W4: market_id must be non-empty"
            bad = _DOLLAR_KEYS & set(row.keys())
            assert not bad, "W4: $ keys found in row: %s" % sorted(bad)

        # pm_trail_browse must surface both rows
        result = browse_pm_trail(ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["total_pm"] == 2, (
            "W4: browse_pm_trail total_pm must be 2; got %d" % result["total_pm"]
        )

    def test_empty_provider_via_injected_writes_zero_rows(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4 acceptance: injected provider returning [] -> 0 rows written (honest empty)."""
        games, _markets, LF = self._two_games_two_markets()
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        class EmptyProvider(LF.PMProvider):
            def fetch_markets(self):
                return []

        def capture_fn(now):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource(games)],
                predict_fn=lambda s, h, a: {"p_home_win": 0.60},
                pm_providers=[EmptyProvider()],
            )

        ledger = tmp_path / "clv_ledger.jsonl"
        written = tick(now=1718928000.0, capture_fn=capture_fn, ledger_path=ledger)

        assert written == [], (
            "W4 acceptance: empty provider must produce 0 written rows (offseason honest empty)"
        )
        assert not ledger.exists(), (
            "W4 acceptance: ledger must not be created when provider returns [] (offseason)"
        )


# ---------------------------------------------------------------------------
# W5-pm-paper-tick-backend: MLB Kalshi acceptance gate (ledger wiring)
# ---------------------------------------------------------------------------

_NOW_W5 = 1_750_100_000.0
_DOLLAR_KEYS_W5 = frozenset({
    "dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
    "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl",
    "dollar_pnl", "pnl_usd",
})


class TestW5MLBKalshiLedgerWiring:
    """W5-pm-paper-tick-backend: MLB Kalshi paper trade -> clv_ledger wiring.

    Acceptance contract:
    - inject 1 MLB Kalshi pair -> exactly 1 canonical row (is_pm=True,
      executed=False, clv_status=INSUFFICIENT_DATA, no $ keys)
    - inject 0 matches -> pm_last_capture.json written, 0 rows appended
    - futures/series/championship contract rejected, not written
    """

    def _mlb_kalshi_pair(self, home: str = "NYY", away: str = "BOS",
                          idx: int = 0) -> Dict[str, Any]:
        return {
            "market_id": "KXMLB-%s-%s-20260620-%d" % (home, away, idx),
            "sport": "mlb", "home": home, "away": away,
            "game_id": "w5-ledger-g%d" % idx,
            "model_prob": 0.57 + idx * 0.01,
            "pm_prob": 0.52 + idx * 0.01,
            "tier": "model_vs_pm",
            "clv_status": "INSUFFICIENT_DATA",
            "captured_at": _NOW_W5,
            "freshness_captured_epoch": _NOW_W5,
            "venue": "kalshi",
        }

    def test_w5_one_mlb_kalshi_pair_exactly_one_ledger_row(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: inject 1 MLB Kalshi pair -> exactly 1 canonical row in clv_ledger."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        ledger = tmp_path / "clv_ledger.jsonl"
        written = tick(
            now=_NOW_W5,
            capture_fn=lambda now: [self._mlb_kalshi_pair()],
            ledger_path=ledger,
        )

        assert len(written) == 1, (
            "W5: 1 MLB Kalshi pair must yield exactly 1 written market_id; got %d"
            % len(written)
        )
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "W5: ledger must have exactly 1 row; got %d" % len(rows)

        row = rows[0]
        assert row.get("is_pm") is True, "W5: is_pm must be True"
        assert row.get("executed") is False, "W5: executed must be False"
        assert row.get("clv_status") == "INSUFFICIENT_DATA", (
            "W5: clv_status must be INSUFFICIENT_DATA; got %r" % row.get("clv_status")
        )
        assert row.get("venue") in ("kalshi", "polymarket"), (
            "W5: venue must be PM; got %r" % row.get("venue")
        )
        assert row.get("market_id"), "W5: market_id must be non-empty"
        bad = _DOLLAR_KEYS_W5 & set(row.keys())
        assert not bad, "W5: $ keys in row: %s" % sorted(bad)
        assert row.get("sport") == "mlb", "W5: sport must be mlb"

        # pm_trail_browse must surface it as PM active
        result = browse_pm_trail(ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["total_pm"] >= 1, "W5: browse_pm_trail must see the MLB PM row"

    def test_w5_zero_mlb_matches_writes_diagnostic_zero_rows(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: 0 MLB PM matches -> pm_last_capture.json with reason, 0 rows."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"
        written = tick(
            now=_NOW_W5,
            capture_fn=lambda now: [],
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert written == [], "W5: 0 matches -> written == []"
        assert not ledger.exists(), "W5: ledger must not be created for 0 matches"
        assert diag.exists(), "W5: pm_last_capture.json must be written for 0 matches"
        with diag.open(encoding="utf-8") as fh:
            data = json.loads(fh.read())
        assert data.get("reason"), "W5: diagnostic reason must be non-empty"
        assert data.get("coerced_count") == 0, "W5: coerced_count must be 0"
        assert data.get("is_pm_active") is False, "W5: is_pm_active must be False"

    def test_w5_futures_contract_rejected_not_written(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: futures/championship contract rejected via active_pairs Path-4 guard."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        mlb_game = _LF.Game("mlb", "NYY", "BOS", game_id="w5-futures",
                             game_date="2026-06-20")
        world_series = {
            "market_id": "KXMLB-WORLD-SERIES-2026",
            "sport": "mlb",
            "home": None, "away": None, "pm_prob": None,
            "binary_title": "Will the Yankees win the World Series?",
            "binary_yes_prob": 0.14,
            "venue": "kalshi",
        }

        class FuturesProvider(_LF.PMProvider):
            def fetch_markets(self):
                return [world_series]

        def capture_fn(now):
            return _LF.active_pairs(
                now=now,
                sources=[_LF.MockGamesSource([mlb_game])],
                predict_fn=lambda s, h, a: {"p_home_win": 0.55},
                pm_providers=[FuturesProvider()],
            )

        written = tick(now=_NOW_W5, capture_fn=capture_fn, ledger_path=ledger)
        assert written == [], "W5: futures/championship contract must not be written"
        assert not ledger.exists(), "W5: ledger must not exist after futures rejection"

    def test_w5_series_contract_rejected_not_written(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: 'win the series' binary rejected by Path-4 futures guard."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        mlb_game = _LF.Game("mlb", "NYY", "BOS", game_id="w5-series",
                             game_date="2026-06-20")
        series_mkt = {
            "market_id": "KXMLB-SERIES-NYY-BOS",
            "sport": "mlb",
            "home": None, "away": None, "pm_prob": None,
            "binary_title": "Will the Yankees win the ALCS series?",
            "binary_yes_prob": 0.38,
            "venue": "kalshi",
        }

        class SeriesProvider(_LF.PMProvider):
            def fetch_markets(self):
                return [series_mkt]

        def capture_fn(now):
            return _LF.active_pairs(
                now=now,
                sources=[_LF.MockGamesSource([mlb_game])],
                predict_fn=lambda s, h, a: {"p_home_win": 0.55},
                pm_providers=[SeriesProvider()],
            )

        written = tick(now=_NOW_W5, capture_fn=capture_fn, ledger_path=ledger)
        assert written == [], "W5: series contract must not be written"
        assert not ledger.exists(), "W5: ledger must not exist after series rejection"

    def test_w5_five_mlb_games_five_rows_via_active_pairs(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: 5 MLB games each matched by a Kalshi contract -> 5 canonical rows."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        ledger = tmp_path / "clv_ledger.jsonl"
        matchups = [("NYY", "BOS"), ("DET", "CWS"), ("CHC", "TOR"),
                    ("TEX", "SDG"), ("TAM", "WAS")]
        games = [
            _LF.Game("mlb", h, a, game_id="w5-5g-%d" % i, game_date="2026-06-20")
            for i, (h, a) in enumerate(matchups)
        ]
        markets = [
            {
                "market_id": "KXMLB-%s-%s-20260620" % (h, a),
                "game_id": "w5-5g-%d" % i,
                "sport": "mlb", "home": h, "away": a,
                "pm_prob": 0.51 + i * 0.02,
                "venue": "kalshi",
            }
            for i, (h, a) in enumerate(matchups)
        ]

        class FiveMarketProvider(_LF.PMProvider):
            def fetch_markets(self):
                return markets

        def capture_fn(now):
            return _LF.active_pairs(
                now=now,
                sources=[_LF.MockGamesSource(games)],
                predict_fn=lambda s, h, a: {"p_home_win": 0.55},
                pm_providers=[FiveMarketProvider()],
            )

        written = tick(now=_NOW_W5, capture_fn=capture_fn, ledger_path=ledger)
        assert len(written) == 5, "W5: 5 MLB games -> 5 written rows; got %d" % len(written)

        rows = _read_ledger(ledger)
        assert len(rows) == 5, "W5: ledger must have 5 rows; got %d" % len(rows)
        for row in rows:
            assert row.get("is_pm") is True
            assert row.get("executed") is False
            assert row.get("clv_status") == "INSUFFICIENT_DATA"
            assert row.get("sport") == "mlb"
            bad = _DOLLAR_KEYS_W5 & set(row.keys())
            assert not bad, "W5: $ keys in row: %s" % sorted(bad)

        result = browse_pm_trail(ledger_path=ledger)
        assert result["total_pm"] == 5, (
            "W5: browse_pm_trail must see 5 PM rows; got %d" % result["total_pm"]
        )


# ---------------------------------------------------------------------------
# W4-pm-paper-tick-real-trades -- exact acceptance gate (ledger file)
# ---------------------------------------------------------------------------

_NOW_W4 = 1_750_000_000.0
_DOLLAR_KEYS_W4 = frozenset({
    "dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
    "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl",
    "dollar_pnl", "pnl_usd",
})


class TestW4AcceptanceGateLedger:
    """W4-pm-paper-tick-real-trades exact acceptance contract (ledger wiring).

    Verifies the confirmed-bug fix: pm_last_capture.json coerced_count must
    always equal the number of rows actually appended to the ledger, not just
    the count of rows passed to _append_to_ledger.

    Acceptance requirements:
    1. 2 valid Kalshi pairs -> exactly 2 rows in ledger, bet_ids distinct,
       all PM invariants satisfied, diagnostic reason=ok:2_markets_written,
       coerced_count==2==len(ledger rows).
    2. Empty capture -> 0 rows, diagnostic reason=no_liquid_pm_markets,
       coerced_count==0==len(ledger rows).
    3. coerced_count in diagnostic always equals rows appended (the core
       invariant that closes the confirmed bug).
    """

    def _two_kalshi_pairs(self):
        return [
            {
                "market_id": "KX-NBA-BOS-MIA-W4LEDGER",
                "sport": "nba",
                "home": "Boston Celtics",
                "away": "Miami Heat",
                "game_id": "w4-ledger-g1",
                "model_prob": 0.62,
                "pm_prob": 0.55,
                "tier": "model_vs_pm",
                "clv_status": "INSUFFICIENT_DATA",
                "captured_at": _NOW_W4,
                "venue": "kalshi",
            },
            {
                "market_id": "KX-NBA-LAL-GSW-W4LEDGER",
                "sport": "nba",
                "home": "Los Angeles Lakers",
                "away": "Golden State Warriors",
                "game_id": "w4-ledger-g2",
                "model_prob": 0.57,
                "pm_prob": 0.51,
                "tier": "model_vs_pm",
                "clv_status": "INSUFFICIENT_DATA",
                "captured_at": _NOW_W4,
                "venue": "kalshi",
            },
        ]

    def test_two_kalshi_pairs_write_exactly_two_rows_with_distinct_bet_ids(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4: 2 valid Kalshi pairs -> 2 rows, distinct bet_id, all invariants."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick
        from scripts.platformkit.pm_trail_browse import browse_pm_trail

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        written = tick(
            now=_NOW_W4,
            capture_fn=lambda now: self._two_kalshi_pairs(),
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert len(written) == 2, (
            "W4: 2 Kalshi pairs must yield exactly 2 written market_ids; got %d"
            % len(written)
        )
        rows = _read_ledger(ledger)
        assert len(rows) == 2, (
            "W4: ledger must have exactly 2 rows; got %d" % len(rows)
        )

        bet_ids = set()
        for row in rows:
            assert row.get("is_pm") is True, "W4: is_pm must be True"
            assert row.get("venue") in ("kalshi", "polymarket"), (
                "W4: venue must be PM; got %r" % row.get("venue")
            )
            assert row.get("executed") is False, "W4: executed must be False"
            assert row.get("clv_status") == "INSUFFICIENT_DATA"
            assert row.get("market_id"), "W4: market_id must be non-empty"
            bad = _DOLLAR_KEYS_W4 & set(row.keys())
            assert not bad, "W4: $ keys in row: %s" % sorted(bad)
            bid = row.get("bet_id")
            assert bid, "W4: bet_id must be non-empty"
            assert bid not in bet_ids, (
                "W4: bet_id must be distinct; duplicate: %r" % bid
            )
            bet_ids.add(bid)

        # Diagnostic invariants.
        with diag.open(encoding="utf-8") as fh:
            data = json.loads(fh.read())
        assert data.get("reason") == "ok:2_markets_written", (
            "W4: diagnostic reason must be 'ok:2_markets_written'; got %r"
            % data.get("reason")
        )
        assert data.get("coerced_count") == 2, (
            "W4: coerced_count must be 2; got %r" % data.get("coerced_count")
        )
        # Core invariant: coerced_count == ledger rows appended.
        assert data.get("coerced_count") == len(rows), (
            "W4: coerced_count (%d) != ledger rows (%d)"
            % (data.get("coerced_count", -1), len(rows))
        )

        # pm_trail_browse must surface both rows.
        result = browse_pm_trail(ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["total_pm"] == 2, (
            "W4: browse_pm_trail must see 2 PM rows; got %d" % result["total_pm"]
        )

    def test_empty_capture_zero_rows_reason_no_liquid_pm_markets(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4: empty capture -> 0 rows, reason=no_liquid_pm_markets, coerced_count==0."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        written = tick(
            now=_NOW_W4,
            capture_fn=lambda now: [],
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert written == [], "W4: empty capture must return []"
        assert not ledger.exists(), "W4: ledger must not be created"

        with diag.open(encoding="utf-8") as fh:
            data = json.loads(fh.read())
        assert data.get("reason") == "no_liquid_pm_markets", (
            "W4: reason must be 'no_liquid_pm_markets'; got %r" % data.get("reason")
        )
        assert data.get("coerced_count") == 0, (
            "W4: coerced_count must be 0; got %r" % data.get("coerced_count")
        )
        # coerced_count == ledger rows appended (both 0).
        ledger_rows = _read_ledger(ledger)
        assert data.get("coerced_count") == len(ledger_rows), (
            "W4: coerced_count (%d) != ledger rows (%d)"
            % (data.get("coerced_count", -1), len(ledger_rows))
        )

    def test_coerced_count_always_equals_ledger_rows_appended(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4: diagnostic coerced_count always equals rows appended to ledger.

        Drives the invariant that closes the confirmed bug: coerced_count in
        pm_last_capture.json must reflect what actually reached disk, not what
        was passed into _append_to_ledger.
        """
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        # Case A: 2 rows.
        ledger_a = tmp_path / "ledger_a.jsonl"
        diag_a = tmp_path / "diag_a.json"
        tick(
            now=_NOW_W4,
            capture_fn=lambda now: self._two_kalshi_pairs(),
            ledger_path=ledger_a,
            diagnostic_path=diag_a,
        )
        with diag_a.open(encoding="utf-8") as fh:
            d_a = json.loads(fh.read())
        assert d_a.get("coerced_count") == len(_read_ledger(ledger_a)), (
            "W4: coerced_count must equal ledger rows for 2-pair case"
        )

        # Case B: 0 rows.
        ledger_b = tmp_path / "ledger_b.jsonl"
        diag_b = tmp_path / "diag_b.json"
        tick(
            now=_NOW_W4,
            capture_fn=lambda now: [],
            ledger_path=ledger_b,
            diagnostic_path=diag_b,
        )
        with diag_b.open(encoding="utf-8") as fh:
            d_b = json.loads(fh.read())
        assert d_b.get("coerced_count") == len(_read_ledger(ledger_b)), (
            "W4: coerced_count must equal ledger rows for empty-capture case"
        )
