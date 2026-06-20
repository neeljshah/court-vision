"""test_pm_paper_tick_runner.py -- per-file tests for pm_paper_tick_runner.

Acceptance contract (workstream W4-pm-paper-real-trades):
  1. With a mock capture_fn supplying one liquid per-game binary market matched
     to a game, tick() appends a coerced PM row to the ledger:
       is_pm=True, executed=False, clv_status=INSUFFICIENT_DATA,
       no dollar/pnl/roi key, stake_units present.
  2. With no matching market (empty capture), tick() writes nothing and the
     ledger stays unchanged.
  3. active_pairs() end-to-end: with a mock PM provider supplying one liquid
     per-game binary market matched to a game, active_pairs() returns >= 1
     pair row; with no matching market, returns [].
  4. A futures/series/championship contract from the capture_fn is coerced and
     written IF it carries a valid venue -- the futures gate only fires in
     active_pairs Path-4.  But tick() with a capture_fn that already ran
     through active_pairs (which rejects futures) will write nothing.
  5. No $ / P&L key ever in any written row.

Run:
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest scripts/platformkit/pm_trading/test_pm_paper_tick_runner.py -q
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, List

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_HERE), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_feed as LF  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({
    "dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
    "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl",
    "dollar_pnl", "pnl_usd",
})

_NOW = 1_750_000_000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _one_pm_pair(venue: str = "kalshi") -> Dict[str, Any]:
    """Canonical PM pair row as returned by active_pairs() (venue-stamped)."""
    return {
        "market_id": "KXNBA-2026-BOS-MIA-20260620",
        "sport": "nba",
        "home": "Boston Celtics",
        "away": "Miami Heat",
        "game_id": "bos-mia-001",
        "model_prob": 0.62,
        "pm_prob": 0.55,
        "tier": "model_vs_pm",
        "clv_status": "INSUFFICIENT_DATA",
        "captured_at": _NOW,
        "freshness_captured_epoch": _NOW,
        "venue": venue,
    }


class MockPMProvider(LF.PMProvider):
    def __init__(self, markets):
        self._markets = list(markets)

    def fetch_markets(self):
        return list(self._markets)


def _fake_predict(sport, home, away):
    return {"p_home_win": 0.62}


# ---------------------------------------------------------------------------
# tick() with mock capture_fn
# ---------------------------------------------------------------------------

class TestTickWithMockCapture:
    """Core tick() contract using injectable capture_fn."""

    def test_one_pm_pair_appended_to_ledger(self, tmp_path: pathlib.Path) -> None:
        """tick() with 1 valid Kalshi pair -> 1 coerced row in ledger."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        written = tick(now=_NOW,
                       capture_fn=lambda now: [_one_pm_pair("kalshi")],
                       ledger_path=ledger)

        assert len(written) >= 1, "tick() must return written market_id list"
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "exactly one row must be appended"
        row = rows[0]

        # Core PM invariants
        assert row.get("is_pm") is True, "is_pm must be True"
        assert row.get("venue") in ("kalshi", "polymarket"), "venue must be PM"
        assert row.get("executed") is False, "executed must be False"
        assert row.get("clv_status") == "INSUFFICIENT_DATA"
        assert row.get("market_id"), "market_id must be non-empty"
        assert "stake_units" in row, "stake_units must be present"
        # No dollar keys
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ key(s) in ledger row: %s" % sorted(bad)

    def test_polymarket_pair_also_written(self, tmp_path: pathlib.Path) -> None:
        """tick() with a polymarket pair stamps is_pm=True and venue=polymarket."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        tick(now=_NOW,
             capture_fn=lambda now: [_one_pm_pair("polymarket")],
             ledger_path=ledger)

        rows = _read_ledger(ledger)
        assert len(rows) == 1
        assert rows[0].get("venue") == "polymarket"
        assert rows[0].get("is_pm") is True

    def test_empty_capture_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        """Empty capture -> ledger untouched, tick() returns []."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        sentinel = {"ts": "2026-01-01T00:00:00+00:00", "status": "open"}
        with ledger.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(sentinel) + "\n")

        written = tick(now=_NOW, capture_fn=lambda now: [], ledger_path=ledger)
        assert written == [], "empty capture must return []"
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "ledger must be unchanged (still 1 sentinel row)"

    def test_empty_capture_does_not_create_ledger(self, tmp_path: pathlib.Path) -> None:
        """Empty capture on a missing ledger must not create the file."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        assert not ledger.exists()
        tick(now=_NOW, capture_fn=lambda now: [], ledger_path=ledger)
        assert not ledger.exists(), "empty capture must not create the ledger file"

    def test_executed_always_false_even_if_capture_says_true(
        self, tmp_path: pathlib.Path
    ) -> None:
        """executed=False is always stamped; capture's executed=True is overridden."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        pair = dict(_one_pm_pair())
        pair["executed"] = True  # must be overridden to False
        tick(now=_NOW, capture_fn=lambda now: [pair], ledger_path=ledger)
        rows = _read_ledger(ledger)
        assert rows[0].get("executed") is False, "executed must be False always"

    def test_clv_status_defaults_to_insufficient_data(
        self, tmp_path: pathlib.Path
    ) -> None:
        """clv_status defaults to INSUFFICIENT_DATA even if absent from capture."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        pair = dict(_one_pm_pair())
        pair.pop("clv_status", None)
        tick(now=_NOW, capture_fn=lambda now: [pair], ledger_path=ledger)
        rows = _read_ledger(ledger)
        assert rows[0].get("clv_status") == "INSUFFICIENT_DATA"

    def test_no_dollar_keys_stripped_from_dirty_capture(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Dollar/pnl keys injected by capture_fn are stripped before writing."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        dirty = dict(_one_pm_pair())
        dirty["dollar_pnl"] = 999.99
        dirty["pnl_usd"] = 50.0
        dirty["roi"] = 0.15
        tick(now=_NOW, capture_fn=lambda now: [dirty], ledger_path=ledger)
        rows = _read_ledger(ledger)
        assert len(rows) == 1
        bad = _DOLLAR_KEYS & set(rows[0].keys())
        assert not bad, "$ key(s) not stripped: %s" % sorted(bad)

    def test_non_pm_venue_rows_dropped(self, tmp_path: pathlib.Path) -> None:
        """Rows with non-PM venues (sportsbook) must be silently dropped."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        sportsbook_rows = [
            {"market_id": "espn:401859967", "venue": "espn",
             "model_prob": 0.55, "market_price": 0.48, "stake_units": 1.0},
            {"market_id": "fanduel-nba-123", "taken_book": "FanDuel",
             "model_prob": 0.60, "stake_units": 1.0},
        ]
        written = tick(now=_NOW,
                       capture_fn=lambda now: sportsbook_rows,
                       ledger_path=ledger)
        assert written == [], "sportsbook rows must be dropped"
        assert not ledger.exists(), "ledger must not be created for sportsbook capture"

    def test_multiple_pm_pairs_all_written(self, tmp_path: pathlib.Path) -> None:
        """Multiple PM pairs from one capture are all appended."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        pairs = [
            _one_pm_pair("kalshi"),
            {**_one_pm_pair("polymarket"),
             "market_id": "poly-nba-bos-mia-20260620",
             "venue": "polymarket"},
        ]
        written = tick(now=_NOW, capture_fn=lambda now: pairs, ledger_path=ledger)
        assert len(written) == 2, "both market_ids must be returned"
        rows = _read_ledger(ledger)
        assert len(rows) == 2

    def test_capture_exception_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        """When capture_fn raises, the ledger is not touched."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"

        def _raise(now):
            raise RuntimeError("network down")

        written = tick(now=_NOW, capture_fn=_raise, ledger_path=ledger)
        assert written == []
        assert not ledger.exists()


# ---------------------------------------------------------------------------
# active_pairs() end-to-end with mock PM provider
# ---------------------------------------------------------------------------

class TestActivePairsEndToEnd:
    """active_pairs() with MockPMProvider -- the primary W4 acceptance gate.

    Tests that a mock provider supplying one liquid per-game binary market
    matched to a slate game produces >= 1 pair row, and that no matching
    market produces [].
    """

    def _game(self):
        return LF.Game("nba", "Boston Celtics", "Miami Heat",
                       game_id="bos-mia-001", game_date="2026-06-20")

    def _pm_market(self):
        """Liquid per-game binary market (per-game "win tonight", not futures)."""
        return {
            "market_id": "KXNBA-BOS-MIA-20260620",
            "game_id": "bos-mia-001",
            "sport": "nba",
            "home": "Boston Celtics",
            "away": "Miami Heat",
            "pm_prob": 0.55,
            "venue": "kalshi",
        }

    def test_liquid_per_game_market_produces_pair_row(self) -> None:
        """Mock provider with one liquid per-game market -> >= 1 pair row."""
        rows = LF.active_pairs(
            now=_NOW,
            sources=[LF.MockGamesSource([self._game()])],
            predict_fn=_fake_predict,
            pm_providers=[MockPMProvider([self._pm_market()])],
        )
        assert len(rows) >= 1, (
            "active_pairs must return >= 1 row when a liquid per-game market "
            "matches a slate game"
        )
        row = rows[0]
        assert row["clv_status"] == "INSUFFICIENT_DATA"
        assert 0.0 < row["model_prob"] < 1.0
        assert 0.0 < row["pm_prob"] < 1.0
        assert row.get("is_pm") is None or row.get("is_pm") is True, (
            "active_pairs rows do not stamp is_pm (that is done by _coerce_row)"
        )
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ key(s) in active_pairs row: %s" % sorted(bad)

    def test_no_matching_market_returns_empty(self) -> None:
        """No matching PM market -> active_pairs returns [] (honest empty)."""
        rows = LF.active_pairs(
            now=_NOW,
            sources=[LF.MockGamesSource([self._game()])],
            predict_fn=_fake_predict,
            pm_providers=[MockPMProvider([])],
        )
        assert rows == [], "active_pairs must return [] when no market matches"

    def test_futures_contract_rejected(self) -> None:
        """A futures/championship binary is rejected; active_pairs returns []."""
        championship = {
            "market_id": "poly-nba-championship-celtics",
            "sport": "nba",
            "home": None,
            "away": None,
            "pm_prob": None,
            "binary_title": "Will the Boston Celtics win the NBA championship?",
            "binary_yes_prob": 0.65,
            "venue": "polymarket",
        }
        rows = LF.active_pairs(
            now=_NOW,
            sources=[LF.MockGamesSource([self._game()])],
            predict_fn=_fake_predict,
            pm_providers=[MockPMProvider([championship])],
        )
        assert rows == [], (
            "futures/championship contract must be rejected by active_pairs Path-4"
        )

    def test_series_contract_rejected(self) -> None:
        """A 'win the series' binary is rejected; active_pairs returns []."""
        series = {
            "market_id": "poly-nba-series-celtics",
            "sport": "nba",
            "home": None,
            "away": None,
            "pm_prob": None,
            "binary_title": "Will the Celtics win the series?",
            "binary_yes_prob": 0.58,
            "venue": "polymarket",
        }
        rows = LF.active_pairs(
            now=_NOW,
            sources=[LF.MockGamesSource([self._game()])],
            predict_fn=_fake_predict,
            pm_providers=[MockPMProvider([series])],
        )
        assert rows == [], "series contract must be rejected"

    def test_tick_integration_with_active_pairs_via_mock_provider(
        self, tmp_path: pathlib.Path
    ) -> None:
        """End-to-end: tick() with capture_fn that calls active_pairs via mock
        provider writes a coerced PM row when a liquid market matches a game.
        """
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"

        # Build a capture_fn that calls active_pairs with a mock provider.
        def _capture(now: float):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource([self._game()])],
                predict_fn=_fake_predict,
                pm_providers=[MockPMProvider([self._pm_market()])],
            )

        written = tick(now=_NOW, capture_fn=_capture, ledger_path=ledger)
        assert len(written) >= 1, "tick() must write market_id(s) for matched game"

        rows = _read_ledger(ledger)
        assert len(rows) >= 1, "at least one row must be in the ledger"
        row = rows[0]
        assert row.get("is_pm") is True
        assert row.get("executed") is False
        assert row.get("clv_status") == "INSUFFICIENT_DATA"
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "$ key(s) in coerced ledger row: %s" % sorted(bad)

    def test_tick_integration_empty_market_writes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """End-to-end: tick() with capture_fn that calls active_pairs with no
        matching market -> no row written, honest empty.
        """
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"

        def _capture(now: float):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource([self._game()])],
                predict_fn=_fake_predict,
                pm_providers=[MockPMProvider([])],
            )

        written = tick(now=_NOW, capture_fn=_capture, ledger_path=ledger)
        assert written == [], "empty market -> tick() returns []"
        assert not ledger.exists(), "empty market -> ledger not created"


# ---------------------------------------------------------------------------
# Diagnostic reason (last_capture) tests -- W4 honest-empty contract
# ---------------------------------------------------------------------------

class TestDiagnosticReason:
    """Verify that tick() writes a structured last_capture diagnostic reason.

    When 0 markets are coerced, a pm_last_capture.json diagnostic file must be
    written with a non-empty reason string (e.g. 'no_liquid_pm_markets' for
    offseason, 'capture_error:...' for fetch failures, 'coerce_gap:...' when
    raw rows existed but none passed venue validation).  No trade row is ever
    fabricated.  When >= 1 market is coerced, reason starts with 'ok:'.
    """

    def test_empty_capture_writes_diagnostic_with_reason(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Empty capture -> pm_last_capture.json written, reason='no_liquid_pm_markets'."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        tick(now=_NOW, capture_fn=lambda now: [],
             ledger_path=ledger, diagnostic_path=diag)

        assert diag.exists(), "pm_last_capture.json must be created"
        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert "reason" in data, "diagnostic must carry a 'reason' field"
        assert data["reason"], "reason must be non-empty"
        assert "no_liquid" in data["reason"] or "offseason" in data["reason"] \
            or data["reason"].startswith("no_liquid"), (
            "empty capture reason must indicate no liquid PM markets; got: %r"
            % data["reason"]
        )
        assert data.get("coerced_count") == 0
        assert data.get("is_pm_active") is False

    def test_liquid_market_writes_diagnostic_ok_reason(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Successful capture -> diagnostic reason starts with 'ok:'."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        tick(now=_NOW, capture_fn=lambda now: [_one_pm_pair("kalshi")],
             ledger_path=ledger, diagnostic_path=diag)

        assert diag.exists(), "pm_last_capture.json must be created"
        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert data.get("reason", "").startswith("ok:"), (
            "diagnostic reason must start with 'ok:' when markets written; got: %r"
            % data.get("reason")
        )
        assert data.get("coerced_count") == 1
        assert data.get("is_pm_active") is True

    def test_capture_error_writes_capture_error_reason(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Capture exception -> diagnostic reason contains 'capture_error'."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        def _raise(now):
            raise RuntimeError("network down")

        tick(now=_NOW, capture_fn=_raise, ledger_path=ledger, diagnostic_path=diag)

        assert diag.exists(), "pm_last_capture.json must be created even on error"
        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert "capture_error" in data.get("reason", ""), (
            "reason must contain 'capture_error' on exception; got: %r"
            % data.get("reason")
        )
        assert data.get("is_pm_active") is False
        # Ledger must not be created (no fabricated rows)
        assert not ledger.exists(), "ledger must not be created on capture error"

    def test_sportsbook_rows_only_writes_coerce_gap_reason(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Non-PM venue rows dropped -> reason contains 'coerce_gap'."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"
        sportsbook = [{"market_id": "fanduel-123", "venue": "fanduel",
                       "model_prob": 0.55, "stake_units": 1.0}]

        tick(now=_NOW, capture_fn=lambda now: sportsbook,
             ledger_path=ledger, diagnostic_path=diag)

        assert diag.exists()
        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert "coerce_gap" in data.get("reason", ""), (
            "non-PM rows reason must be 'coerce_gap:...'; got: %r" % data.get("reason")
        )
        assert data.get("raw_count") == 1
        assert data.get("coerced_count") == 0

    def test_diagnostic_has_no_dollar_keys(self, tmp_path: pathlib.Path) -> None:
        """pm_last_capture.json must never contain dollar/pnl fields."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        tick(now=_NOW, capture_fn=lambda now: [],
             ledger_path=ledger, diagnostic_path=diag)

        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        bad = _DOLLAR_KEYS & set(data.keys())
        assert not bad, "$ keys in diagnostic: %s" % sorted(bad)


# ---------------------------------------------------------------------------
# W5-pm-paper-tick-backend: MLB Kalshi/Polymarket acceptance gate
# ---------------------------------------------------------------------------

class TestW5MLBKalshiAcceptance:
    """W5 acceptance: MLB Kalshi paper trade coercion.

    Acceptance contract (workstream W5-pm-paper-tick-backend):
    1. With injected capture_fn returning 1 matched MLB Kalshi pair,
       tick() appends exactly 1 canonical row (is_pm=True, executed=False,
       clv_status=INSUFFICIENT_DATA, no $ keys, taken_book=venue).
    2. With 0 matches (offseason/no-contract), writes pm_last_capture.json
       reason and appends 0 rows.
    3. A futures/series/championship contract is rejected (via active_pairs
       Path-4 guard) and not written to the ledger.
    """

    def _mlb_kalshi_pair(self) -> Dict[str, Any]:
        """One valid MLB Kalshi per-game binary pair as active_pairs would emit."""
        return {
            "market_id": "KXMLB-NYY-BOS-20260620",
            "sport": "mlb",
            "home": "NYY",
            "away": "BOS",
            "game_id": "823532",
            "model_prob": 0.58,
            "pm_prob": 0.53,
            "tier": "model_vs_pm",
            "clv_status": "INSUFFICIENT_DATA",
            "captured_at": _NOW,
            "freshness_captured_epoch": _NOW,
            "venue": "kalshi",
        }

    def test_one_mlb_kalshi_pair_appends_exactly_one_canonical_row(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: inject 1 MLB Kalshi pair -> exactly 1 canonical row in ledger."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        written = tick(
            now=_NOW,
            capture_fn=lambda now: [self._mlb_kalshi_pair()],
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert len(written) == 1, (
            "W5: 1 MLB Kalshi pair must yield exactly 1 written row; got %d" % len(written)
        )
        rows = _read_ledger(ledger)
        assert len(rows) == 1, (
            "W5: ledger must have exactly 1 row; got %d" % len(rows)
        )
        row = rows[0]
        assert row.get("is_pm") is True, "W5: is_pm must be True"
        assert row.get("executed") is False, "W5: executed must be False"
        assert row.get("clv_status") == "INSUFFICIENT_DATA", (
            "W5: clv_status must be INSUFFICIENT_DATA; got %r" % row.get("clv_status")
        )
        # taken_book must equal venue so enrich._infer_venue survives collapse
        assert row.get("taken_book") in ("kalshi", "polymarket"), (
            "W5: taken_book must be PM venue; got %r" % row.get("taken_book")
        )
        assert row.get("market_id"), "W5: market_id must be non-empty"
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "W5: $ keys in row: %s" % sorted(bad)
        assert row.get("sport") == "mlb", "W5: sport must be mlb"

    def test_zero_mlb_matches_writes_diagnostic_reason_and_zero_rows(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: 0 PM matches -> pm_last_capture.json written with reason, 0 rows appended."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        written = tick(
            now=_NOW,
            capture_fn=lambda now: [],
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert written == [], "W5: 0 matches must return []"
        assert not ledger.exists(), "W5: ledger must not be created when 0 rows written"
        assert diag.exists(), "W5: pm_last_capture.json must be written even with 0 matches"

        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())

        assert data.get("reason"), "W5: diagnostic must have non-empty reason"
        assert data.get("coerced_count") == 0, (
            "W5: coerced_count must be 0; got %r" % data.get("coerced_count")
        )
        assert data.get("is_pm_active") is False, "W5: is_pm_active must be False"

    def test_futures_series_contract_rejected_via_active_pairs(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: futures/series contract is rejected by active_pairs Path-4 and not written."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        # Build capture_fn that calls active_pairs with a futures contract
        mlb_game = LF.Game("mlb", "NYY", "BOS", game_id="w5-futures-g1",
                           game_date="2026-06-20")
        futures_contract = {
            "market_id": "KXMLB-CHAMPIONSHIP-2026",
            "sport": "mlb",
            "home": None,
            "away": None,
            "pm_prob": None,
            "binary_title": "Will the Yankees win the World Series?",
            "binary_yes_prob": 0.12,
            "venue": "kalshi",
        }

        class FuturesPMProvider(LF.PMProvider):
            def fetch_markets(self):
                return [futures_contract]

        def capture_fn(now):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource([mlb_game])],
                predict_fn=lambda s, h, a: {"p_home_win": 0.58},
                pm_providers=[FuturesPMProvider()],
            )

        written = tick(
            now=_NOW,
            capture_fn=capture_fn,
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert written == [], "W5: futures/series contract must be rejected; got %r" % written
        assert not ledger.exists(), "W5: ledger must not exist after futures rejection"

    def test_series_contract_also_rejected(self, tmp_path: pathlib.Path) -> None:
        """W5: 'win the series' contract rejected and not written (path-4 guard)."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        mlb_game = LF.Game("mlb", "NYY", "BOS", game_id="w5-series-g1",
                           game_date="2026-06-20")
        series_contract = {
            "market_id": "KXMLB-SERIES-2026-NYY",
            "sport": "mlb",
            "home": None,
            "away": None,
            "pm_prob": None,
            "binary_title": "Will the Yankees win the series?",
            "binary_yes_prob": 0.45,
            "venue": "kalshi",
        }

        class SeriesPMProvider(LF.PMProvider):
            def fetch_markets(self):
                return [series_contract]

        def capture_fn(now):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource([mlb_game])],
                predict_fn=lambda s, h, a: {"p_home_win": 0.58},
                pm_providers=[SeriesPMProvider()],
            )

        written = tick(now=_NOW, capture_fn=capture_fn, ledger_path=ledger)
        assert written == [], "W5: series contract must be rejected"
        assert not ledger.exists(), "W5: ledger must not be created after series rejection"

    def test_five_mlb_games_five_kalshi_pairs_written(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: 5 MLB games each matched by a Kalshi pair -> 5 rows in ledger."""
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"

        teams = [("NYY", "BOS"), ("DET", "CWS"), ("CHC", "TOR"),
                 ("TEX", "SDG"), ("TAM", "WAS")]
        pairs = [
            {
                "market_id": "KXMLB-%s-%s-20260620" % (h, a),
                "sport": "mlb", "home": h, "away": a,
                "game_id": "w5-g%d" % i, "model_prob": 0.55 + i * 0.01,
                "pm_prob": 0.50 + i * 0.01, "tier": "model_vs_pm",
                "clv_status": "INSUFFICIENT_DATA", "captured_at": _NOW,
                "freshness_captured_epoch": _NOW, "venue": "kalshi",
            }
            for i, (h, a) in enumerate(teams)
        ]

        written = tick(now=_NOW, capture_fn=lambda now: pairs, ledger_path=ledger)

        assert len(written) == 5, "W5: 5 MLB pairs must write 5 rows; got %d" % len(written)
        rows = _read_ledger(ledger)
        assert len(rows) == 5, "W5: ledger must have 5 rows; got %d" % len(rows)
        for row in rows:
            assert row.get("is_pm") is True, "W5: all rows must have is_pm=True"
            assert row.get("executed") is False, "W5: all rows must have executed=False"
            assert row.get("clv_status") == "INSUFFICIENT_DATA"
            assert row.get("sport") == "mlb"
            bad = _DOLLAR_KEYS & set(row.keys())
            assert not bad, "W5: $ keys in row: %s" % sorted(bad)

    def test_active_pairs_mlb_binary_win_match_via_mock_provider(self) -> None:
        """W5: active_pairs with 'Will NYY win tonight?' binary matches MLB game."""
        nyyv_bos = LF.Game("mlb", "NYY", "BOS", game_id="w5-bin-g1",
                           game_date="2026-06-20")
        nyy_binary = {
            "market_id": "KXMLB-NYY-BOS-W5-BIN",
            "sport": "mlb",
            "home": None, "away": None, "pm_prob": None,
            "binary_title": "Will NYY win tonight?",
            "binary_yes_prob": 0.54,
            "venue": "kalshi",
        }

        class BinaryMLBProvider(LF.PMProvider):
            def fetch_markets(self):
                return [nyy_binary]

        rows = LF.active_pairs(
            now=_NOW,
            sources=[LF.MockGamesSource([nyyv_bos])],
            predict_fn=_fake_predict,
            pm_providers=[BinaryMLBProvider()],
        )
        assert len(rows) >= 1, (
            "W5: 'Will NYY win tonight?' binary must match NYY@BOS MLB game"
        )
        row = rows[0]
        assert row["sport"] == "mlb"
        assert 0.0 < row["pm_prob"] < 1.0
        assert row["clv_status"] == "INSUFFICIENT_DATA"
        bad = _DOLLAR_KEYS & set(row.keys())
        assert not bad, "W5: $ keys in active_pairs row: %s" % sorted(bad)

    def test_offseason_no_pm_markets_writes_honest_empty_diagnostic(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W5: true offseason (provider returns []) -> pm_last_capture.json has reason,
        ledger not created -- honest 'none right now, here is why' state."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        # Simulate real offseason: active_pairs with empty provider and live MLB games
        mlb_games = [
            LF.Game("mlb", h, a, game_id="w5-off-%d" % i, game_date="2026-06-20")
            for i, (h, a) in enumerate([("NYY", "BOS"), ("CHC", "TOR"), ("TEX", "SDG")])
        ]

        class OffseasonProvider(LF.PMProvider):
            def fetch_markets(self):
                return []  # No PM markets -- the honest empty state

        def capture_fn(now):
            return LF.active_pairs(
                now=now,
                sources=[LF.MockGamesSource(mlb_games)],
                predict_fn=lambda s, h, a: {"p_home_win": 0.55},
                pm_providers=[OffseasonProvider()],
            )

        written = tick(now=_NOW, capture_fn=capture_fn,
                       ledger_path=ledger, diagnostic_path=diag)

        assert written == [], "W5: offseason -> 0 written rows"
        assert not ledger.exists(), "W5: ledger must not be created in offseason"
        assert diag.exists(), "W5: pm_last_capture.json must be written in offseason"

        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert data.get("reason"), "W5: offseason diagnostic must have reason text"
        assert data.get("is_pm_active") is False, "W5: is_pm_active must be False in offseason"
        assert data.get("coerced_count") == 0


# ---------------------------------------------------------------------------
# W4-pm-paper-tick-real-trades -- exact acceptance gate
# ---------------------------------------------------------------------------

class TestW4AcceptanceGate:
    """W4-pm-paper-tick-real-trades exact acceptance contract.

    Spec (from workstream description):
    1. tick() with capture_fn returning 2 valid kalshi pairs writes exactly
       2 rows (is_pm=True, venue set, distinct bet_id, no $ keys) to an
       injected ledger AND diagnostic reason=ok:2_markets_written with
       coerced_count == written count (not just rows passed to append).
    2. tick() with capture_fn returning [] writes 0 rows and diagnostic
       reason=no_liquid_pm_markets (coerced_count==0).
    3. diagnostic coerced_count always equals ledger rows appended.
    """

    def _two_kalshi_pairs(self):
        """Two distinct Kalshi per-game binary pairs."""
        return [
            {
                "market_id": "KX-NBA-BOS-MIA-W4ACC",
                "sport": "nba",
                "home": "Boston Celtics",
                "away": "Miami Heat",
                "game_id": "w4-acc-g1",
                "model_prob": 0.62,
                "pm_prob": 0.55,
                "tier": "model_vs_pm",
                "clv_status": "INSUFFICIENT_DATA",
                "captured_at": _NOW,
                "freshness_captured_epoch": _NOW,
                "venue": "kalshi",
            },
            {
                "market_id": "KX-NBA-LAL-GSW-W4ACC",
                "sport": "nba",
                "home": "Los Angeles Lakers",
                "away": "Golden State Warriors",
                "game_id": "w4-acc-g2",
                "model_prob": 0.57,
                "pm_prob": 0.52,
                "tier": "model_vs_pm",
                "clv_status": "INSUFFICIENT_DATA",
                "captured_at": _NOW,
                "freshness_captured_epoch": _NOW,
                "venue": "kalshi",
            },
        ]

    def test_two_valid_kalshi_pairs_write_exactly_two_rows(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4 acceptance: 2 valid Kalshi pairs -> exactly 2 rows, distinct bet_ids."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"
        pairs = self._two_kalshi_pairs()

        written = tick(
            now=_NOW,
            capture_fn=lambda now: pairs,
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        # Written market_id list must contain exactly 2 entries.
        assert len(written) == 2, (
            "W4: 2 Kalshi pairs must yield exactly 2 written market_ids; got %d"
            % len(written)
        )

        rows = _read_ledger(ledger)
        assert len(rows) == 2, (
            "W4: ledger must have exactly 2 rows; got %d" % len(rows)
        )

        # Row invariants.
        bet_ids = set()
        for row in rows:
            assert row.get("is_pm") is True, "W4: is_pm must be True"
            assert row.get("venue") in ("kalshi", "polymarket"), (
                "W4: venue must be PM-eligible; got %r" % row.get("venue")
            )
            assert row.get("executed") is False, "W4: executed must be False"
            assert row.get("clv_status") == "INSUFFICIENT_DATA", (
                "W4: clv_status must be INSUFFICIENT_DATA"
            )
            assert row.get("market_id"), "W4: market_id must be non-empty"
            bad = _DOLLAR_KEYS & set(row.keys())
            assert not bad, "W4: $ keys in ledger row: %s" % sorted(bad)
            # bet_id must be set and unique (prevents _collapse from folding rows).
            bid = row.get("bet_id")
            assert bid, "W4: bet_id must be non-empty"
            assert bid not in bet_ids, (
                "W4: bet_id must be distinct per row; duplicate: %r" % bid
            )
            bet_ids.add(bid)

        # Diagnostic: reason=ok:2_markets_written, coerced_count==written count.
        assert diag.exists(), "W4: diagnostic file must be written"
        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert data.get("reason") == "ok:2_markets_written", (
            "W4: diagnostic reason must be 'ok:2_markets_written'; got %r"
            % data.get("reason")
        )
        assert data.get("coerced_count") == 2, (
            "W4: diagnostic coerced_count must equal written count (2); got %r"
            % data.get("coerced_count")
        )
        # coerced_count must equal actual ledger rows (not just rows passed in).
        ledger_rows = _read_ledger(ledger)
        assert data.get("coerced_count") == len(ledger_rows), (
            "W4: diagnostic coerced_count (%d) must equal ledger rows appended (%d)"
            % (data.get("coerced_count", -1), len(ledger_rows))
        )

    def test_empty_capture_zero_rows_reason_no_liquid(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4 acceptance: empty capture -> 0 rows, reason=no_liquid_pm_markets."""
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        ledger = tmp_path / "clv_ledger.jsonl"
        diag = tmp_path / "pm_last_capture.json"

        written = tick(
            now=_NOW,
            capture_fn=lambda now: [],
            ledger_path=ledger,
            diagnostic_path=diag,
        )

        assert written == [], "W4: empty capture must return []"
        assert not ledger.exists(), "W4: ledger must not be created for empty capture"

        assert diag.exists(), "W4: diagnostic must be written for empty capture"
        with diag.open(encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        assert data.get("reason") == "no_liquid_pm_markets", (
            "W4: empty capture reason must be 'no_liquid_pm_markets'; got %r"
            % data.get("reason")
        )
        assert data.get("coerced_count") == 0, (
            "W4: coerced_count must be 0 for empty capture; got %r"
            % data.get("coerced_count")
        )

    def test_diagnostic_coerced_count_always_equals_ledger_rows_appended(
        self, tmp_path: pathlib.Path
    ) -> None:
        """W4 acceptance: coerced_count in diagnostic always == rows on disk.

        Drives the core invariant: diagnostic.coerced_count == len(ledger rows).
        Tested for both populated (2 rows) and empty (0 rows) captures.
        """
        import json as _json
        from scripts.platformkit.pm_trading.pm_paper_tick_runner import tick

        # Case A: 2 rows written.
        ledger_a = tmp_path / "clv_ledger_a.jsonl"
        diag_a = tmp_path / "diag_a.json"
        tick(
            now=_NOW,
            capture_fn=lambda now: self._two_kalshi_pairs(),
            ledger_path=ledger_a,
            diagnostic_path=diag_a,
        )
        with diag_a.open(encoding="utf-8") as fh:
            d_a = _json.loads(fh.read())
        rows_a = _read_ledger(ledger_a)
        assert d_a.get("coerced_count") == len(rows_a), (
            "W4: coerced_count (%d) != ledger rows (%d) for 2-row case"
            % (d_a.get("coerced_count", -1), len(rows_a))
        )

        # Case B: 0 rows written.
        ledger_b = tmp_path / "clv_ledger_b.jsonl"
        diag_b = tmp_path / "diag_b.json"
        tick(
            now=_NOW,
            capture_fn=lambda now: [],
            ledger_path=ledger_b,
            diagnostic_path=diag_b,
        )
        with diag_b.open(encoding="utf-8") as fh:
            d_b = _json.loads(fh.read())
        rows_b = _read_ledger(ledger_b)
        assert d_b.get("coerced_count") == len(rows_b), (
            "W4: coerced_count (%d) != ledger rows (%d) for 0-row case"
            % (d_b.get("coerced_count", -1), len(rows_b))
        )


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import inspect
    tests_cls = [
        TestTickWithMockCapture,
        TestActivePairsEndToEnd,
        TestDiagnosticReason,
        TestW5MLBKalshiAcceptance,
        TestW4AcceptanceGate,
    ]
    import pathlib as _p
    passed = 0
    total = 0
    for cls in tests_cls:
        obj = cls()
        for name in dir(obj):
            if not name.startswith("test_"):
                continue
            fn = getattr(obj, name)
            if not callable(fn):
                continue
            total += 1
            try:
                sig = inspect.signature(fn)
                params = [p for p in sig.parameters.values()
                          if p.name != "self"]
                if params:
                    # needs tmp_path
                    import tempfile
                    with tempfile.TemporaryDirectory() as td:
                        fn(tmp_path=_p.Path(td))
                else:
                    fn()
                print("PASS %s.%s" % (cls.__name__, name))
                passed += 1
            except Exception as exc:
                print("FAIL %s.%s -> %s" % (cls.__name__, name, exc))
    print("%d/%d green" % (passed, total))
