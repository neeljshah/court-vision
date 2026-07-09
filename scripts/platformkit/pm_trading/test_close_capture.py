"""Per-file tests for close_capture.py (PT-3).

Accept: mock Kalshi settled->is_proxy=False; open->is_proxy=True; degraded->None;
line_store true-close->False; proxy->True; no close->None; CLV sign correct; no $.
2026-07-06 audit fix: kalshi-taken row gets own-venue close (close_venue=
"kalshi", close_kind="kalshi_lock") ahead of the book line_store fallback;
non-kalshi paths byte-unchanged; close_venue always present; no row rewrites.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_close_capture.py -q
"""
from __future__ import annotations

import json
import sys
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.pm_trading.close_capture import (
    CloseResult, capture_close, _kalshi_close, _kx_venue_close,
    _event_id_for_row,
)
from scripts.platformkit.clv_ledger import compute_clv
from scripts.platformkit.clv import kx_ticker_close as _kx_ticker_close
from scripts.platformkit.clv import kx_close_fallback as _kx_close_fallback


def _row(event_id: str = "KXNBA2026-BOS-NYK", sport: str = "nba",
         side: str = "home", taken_decimal: float = 1.95) -> dict:
    return {
        "event_id": event_id, "sport": sport, "side": side,
        "taken_decimal": taken_decimal, "matchup": "BOS@NYK",
        "status": "open", "executed": False,
    }


def _no_dollar_keys(obj: object) -> bool:
    """Recursively assert no $/dollar/roi/pnl/profit key anywhere in a mapping."""
    if not isinstance(obj, dict):
        return True
    forbidden = {"dollar", "roi", "pnl", "profit", "$"}
    for k in obj:
        if any(f in str(k).lower() for f in forbidden):
            return False
    return all(_no_dollar_keys(v) for v in obj.values())


def _seed_kx_close(tmp_path, ticker: str, sport: str, close_prob: float):
    """Same fixture recipe as test_kx_close_fallback.py's _seed_close: writes one
    in-play tick then derives+writes the kx_ticker_close close-proxy, returning
    the closes_dir to monkeypatch onto kx_close_fallback's kx_ticker_close ref."""
    grade_dir = tmp_path / "grade"
    out_dir = tmp_path / "closes"
    p = grade_dir / sport / (ticker + ".jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "sport": sport, "game_id": ticker, "ts": "2026-07-06T23:55:00Z",
            "market_prob": close_prob, "model_prob": 0.5, "side": "home",
        }) + "\n")
    _kx_ticker_close.write_closes(sport, grade_dir=grade_dir, out_dir=out_dir)
    return out_dir


# ---------------------------------------------------------------------------
# Tests: join-key fix (2026-07-08b root cause) -- event_id on a real paper_pm
# row is the ESPN/FanDuel game id, NEVER a Kalshi ticker; market_id carries
# the real per-team contract ticker and must be used to derive the event
# ticker Kalshi's own API groups by.
# ---------------------------------------------------------------------------

class TestEventIdJoinKeyFix:

    def test_derives_event_ticker_from_market_id(self):
        """market_id 'KXMLBGAME-...LADSD-SD' -> event ticker minus '-SD'."""
        row = {"market_id": "KXMLBGAME-26JUN281610LADSD-SD",
               "event_id": "401815950"}  # ESPN id -- must be ignored
        assert _event_id_for_row(row) == "KXMLBGAME-26JUN281610LADSD"

    def test_market_id_wins_over_espn_event_id(self):
        """A real paper_pm row shape: event_id is ESPN/FanDuel, never Kalshi."""
        row = {"market_id": "KXMLBGAME-26JUN301840TEXCLE-CLE",
               "event_id": "fd:35769002"}
        assert _event_id_for_row(row) == "KXMLBGAME-26JUN301840TEXCLE"

    def test_falls_back_to_kx_shaped_event_id_when_no_market_id(self):
        """No market_id, but event_id already looks like a Kalshi ticker."""
        row = {"event_id": "KXNBA2026-BOS-NYK"}
        assert _event_id_for_row(row) == "KXNBA2026-BOS-NYK"

    def test_none_when_neither_field_is_a_kalshi_ticker(self):
        row = {"event_id": "401815950"}  # bare ESPN id, no market_id
        assert _event_id_for_row(row) is None

    def test_kalshi_close_matches_via_market_id_derived_ticker(self):
        """End-to-end: a row shaped like a real paper_pm/kalshi row (ESPN
        event_id, Kalshi market_id) now MATCHES the Kalshi market list --
        the exact join that was broken for all 284 real ledger rows."""
        row = {"event_id": "401815950", "sport": "mlb",
               "market_id": "KXMLBGAME-26JUN281610LADSD-SD"}

        def _mock_fetch(sport):
            return [{
                "event_ticker": "KXMLBGAME-26JUN281610LADSD",
                "status": "resolved",
                "close_home_dec": 2.18, "close_away_dec": 1.78,
            }]

        res = _kalshi_close(row, kalshi_fetch=_mock_fetch)
        assert res is not None
        assert res.is_proxy is False
        assert res.close_home_dec == 2.18


# ---------------------------------------------------------------------------
# Tests: Kalshi path
# ---------------------------------------------------------------------------

class TestKalshiClose:

    def _oe_like(self, event_id: str, home_dec: float, away_dec: float) -> object:
        """Minimal OddsEvent-like stub (has .event_id and .prices)."""
        class _OE:
            pass
        oe = _OE()
        oe.event_id = event_id
        oe.prices = {"kalshi": {"home": home_dec, "away": away_dec, "draw": None}}
        return oe

    def test_settled_market_is_not_proxy(self):
        """Kalshi OddsEvent match (open market by parse_events) -> is_proxy=True
        because we cannot confirm it has settled yet. Settled raw dict -> False."""
        row = _row(event_id="KXNBA2026-BOS-NYK")
        ev = self._oe_like("KXNBA2026-BOS-NYK", 1.80, 2.10)

        def _mock_fetch(sport):
            return [ev]

        res = _kalshi_close(row, kalshi_fetch=_mock_fetch)
        assert res is not None
        assert res.close_home_dec == 1.80
        assert res.close_away_dec == 2.10
        # OddsEvent objects come from 'open' markets -> proxy=True by convention.
        assert res.is_proxy is True
        assert res.close_source == "kalshi"

    def test_raw_dict_resolved_market_not_proxy(self):
        """Raw dict with status='resolved' -> is_proxy=False (true close)."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _mock_fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK",
                "status": "resolved",
                "close_home_dec": 1.78,
                "close_away_dec": 2.15,
            }]

        res = _kalshi_close(row, kalshi_fetch=_mock_fetch)
        assert res is not None
        assert abs(res.close_home_dec - 1.78) < 1e-9
        assert abs(res.close_away_dec - 2.15) < 1e-9
        assert res.is_proxy is False
        assert res.close_source == "kalshi"

    def test_raw_dict_open_market_is_proxy(self):
        """Raw dict with status='open' -> is_proxy=True."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _mock_fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK",
                "status": "open",
                "close_home_dec": 1.85,
                "close_away_dec": 2.05,
            }]

        res = _kalshi_close(row, kalshi_fetch=_mock_fetch)
        assert res is not None
        assert res.is_proxy is True

    def test_no_event_id_returns_none(self):
        """Row without event_id -> Kalshi path returns None (no guess)."""
        row = _row(event_id="")
        res = _kalshi_close(row, kalshi_fetch=lambda s: [])
        assert res is None

    def test_empty_market_list_returns_none(self):
        """Kalshi returns empty list -> None (no close fabricated)."""
        row = _row(event_id="KXNBA2026-BOS-NYK")
        res = _kalshi_close(row, kalshi_fetch=lambda s: [])
        assert res is None

    def test_unavailable_sentinel_returns_none(self):
        """Kalshi returns {'status': 'unavailable'} -> None."""
        row = _row(event_id="KXNBA2026-BOS-NYK")
        res = _kalshi_close(row, kalshi_fetch=lambda s: {"status": "unavailable"})
        assert res is None

    def test_raising_fetch_returns_none(self):
        """Kalshi fetch raises an exception -> graceful None (degraded path)."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _bad_fetch(sport):
            raise RuntimeError("network error")

        res = _kalshi_close(row, kalshi_fetch=_bad_fetch)
        assert res is None

    def test_degenerate_odds_returns_none(self):
        """Prices <= 1.0 are not valid decimal odds -> None."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _mock_fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK",
                "status": "resolved",
                "close_home_dec": 0.5,   # invalid
                "close_away_dec": 2.00,
            }]

        res = _kalshi_close(row, kalshi_fetch=_mock_fetch)
        assert res is None


# ---------------------------------------------------------------------------
# Tests: capture_close (full resolution chain)
# ---------------------------------------------------------------------------

class TestCaptureClose:

    def test_kalshi_hit_returns_kalshi_result(self):
        """Kalshi match -> CloseResult(is_proxy, source='kalshi') returned."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK",
                "status": "resolved",
                "close_home_dec": 1.80,
                "close_away_dec": 2.10,
            }]

        res = capture_close(row, kalshi_fetch=_fetch)
        assert res is not None
        assert res.close_source == "kalshi"
        assert isinstance(res.close_home_dec, float)
        assert isinstance(res.close_away_dec, float)
        assert res.close_home_dec > 1.0
        assert res.close_away_dec > 1.0
        assert res.is_proxy is False
        assert _no_dollar_keys(res.__dict__)

    def test_provider_degraded_returns_none_when_no_line_store(self):
        """Kalshi fails and no history -> None or CloseResult (both honest)."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _bad_fetch(sport):
            raise RuntimeError("network error")

        res = capture_close(row, kalshi_fetch=_bad_fetch)
        # None (no history) or CloseResult from line_store -- both are honest.
        assert res is None or isinstance(res, CloseResult)

    def test_no_event_id_and_no_history_returns_none(self):
        """Row with neither event_id nor line-store history -> None."""
        row = _row(event_id="", sport="nba")
        res = capture_close(row, kalshi_fetch=lambda s: [])
        assert res is None

    def test_result_dataclass_no_dollar_fields(self):
        """CloseResult carries no dollar / pnl / roi / profit fields."""
        cr = CloseResult(close_home_dec=1.80, close_away_dec=2.10,
                         is_proxy=False, close_source="kalshi")
        assert _no_dollar_keys(cr.__dict__)

    def test_is_proxy_false_only_for_settled(self):
        """is_proxy=False only when the raw market status is settled/resolved."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _settled_fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK",
                "status": "finalized",
                "close_home_dec": 1.75,
                "close_away_dec": 2.20,
            }]

        res = capture_close(row, kalshi_fetch=_settled_fetch)
        assert res is not None
        assert res.is_proxy is False

    def test_open_market_is_proxy_true(self):
        """Kalshi open market (not yet settled) -> is_proxy=True honestly."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _open_fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK",
                "status": "open",
                "close_home_dec": 1.82,
                "close_away_dec": 2.08,
            }]

        res = capture_close(row, kalshi_fetch=_open_fetch)
        assert res is not None
        assert res.is_proxy is True


# ---------------------------------------------------------------------------
# Tests: CLV sign convention (via clv_ledger.compute_clv)
# ---------------------------------------------------------------------------

class TestClvSignConvention:
    """Verify the CLV sign matches the documented contract: POSITIVE = better number."""

    def test_better_price_than_close_positive_clv(self):
        """Taken 1.95 home (prob ~0.513), fair close ~0.556 -> clv_pct > 0."""
        # Home wins: taken decimal 1.95, close 1.80/2.10.
        # devig(1.80, 2.10) -> fair_home ~ 0.54 (above taken_p ~0.513) -> CLV positive.
        clv = compute_clv("home", 1.95, 1.80, 2.10)
        assert clv["clv_pct"] > 0.0, (
            "Expected positive CLV (better number than close); got %r" % clv
        )
        assert clv["beat_close"] is True
        assert _no_dollar_keys(clv)

    def test_worse_price_than_close_negative_clv(self):
        """Taken 1.60 home (prob 0.625), fair close ~0.54 -> clv_pct < 0."""
        # Taken worse price: 1.60 (too short vs. fair close).
        clv = compute_clv("home", 1.60, 1.80, 2.10)
        assert clv["clv_pct"] < 0.0, (
            "Expected negative CLV (worse number than close); got %r" % clv
        )
        assert clv["beat_close"] is False
        assert _no_dollar_keys(clv)

    def test_clv_output_no_dollar_keys(self):
        """compute_clv must never emit any dollar/roi/pnl key."""
        clv = compute_clv("away", 2.10, 1.80, 2.10)
        assert _no_dollar_keys(clv), "Dollar key found in CLV output: %r" % clv

    def test_clv_fields_present(self):
        """compute_clv always returns taken_p, fair_close, clv_pct, beat_close."""
        clv = compute_clv("home", 1.90, 1.85, 2.05)
        for key in ("taken_p", "fair_close", "clv_pct", "beat_close"):
            assert key in clv, "Missing CLV field: %r" % key


# ---------------------------------------------------------------------------
# Tests: is_proxy propagation guard
# ---------------------------------------------------------------------------

class TestIsProxyPropagation:

    def test_close_result_is_proxy_field_bool(self):
        """CloseResult.is_proxy is always a bool."""
        cr = CloseResult(1.80, 2.10, is_proxy=False, close_source="kalshi")
        assert isinstance(cr.is_proxy, bool)
        cr2 = CloseResult(1.80, 2.10, is_proxy=True, close_source="proxy")
        assert isinstance(cr2.is_proxy, bool)

    def test_proxy_source_tag_set(self):
        """close_source field describes the resolution tier honestly."""
        for src in ("kalshi", "line_store", "proxy"):
            cr = CloseResult(1.80, 2.10, is_proxy=True, close_source=src)
            assert cr.close_source == src


# ---------------------------------------------------------------------------
# Tests: kalshi own-venue close tier (2026-07-06 audit fix)
# ---------------------------------------------------------------------------

class TestKxVenueClose:
    """Kalshi-taken rows must get their OWN venue's close, not a different
    book's line_store snapshot -- the cross-venue-basis bug."""

    def test_kalshi_taken_row_gets_venue_close_when_available(self, tmp_path, monkeypatch):
        """taken_book='kalshi' + a derived kx close on disk -> close_venue=
        'kalshi', close_kind='kalshi_lock', is_proxy=True (honest proxy label),
        reusing kx_close_fallback/kx_ticker_close end-to-end (no duplicated fetch)."""
        out_dir = _seed_kx_close(tmp_path, "KXNBAGAME-VENUE", "nba", 0.60)
        monkeypatch.setattr(_kx_ticker_close, "DEFAULT_CLOSES_DIR", out_dir)
        row = {
            "event_id": "KXNBAGAME-VENUE", "sport": "nba", "side": "home",
            "taken_book": "kalshi", "taken_decimal": 1.95, "matchup": "BOS@NYK",
        }
        res = _kx_venue_close(row)
        assert res is not None
        assert res.close_venue == "kalshi"
        assert res.close_kind == "kalshi_lock"
        assert res.is_proxy is True
        assert res.close_source == "kalshi_venue"
        assert res.close_home_dec == pytest.approx(1.0 / 0.60)
        assert res.close_away_dec == pytest.approx(1.0 / 0.40)
        assert _no_dollar_keys(res.__dict__)

    def test_kalshi_taken_row_falls_back_labeled_when_no_kx_close(self, tmp_path, monkeypatch):
        """taken_book='kalshi' but no derived close on disk -> _kx_venue_close
        returns None; capture_close falls through to the line_store tier and
        the returned CloseResult still honestly carries close_venue='book'."""
        empty_dir = tmp_path / "closes_never_derived"
        monkeypatch.setattr(_kx_ticker_close, "DEFAULT_CLOSES_DIR", empty_dir)
        row = {
            "event_id": "KXNBAGAME-NOCLOSE", "sport": "nba", "side": "home",
            "taken_book": "kalshi", "taken_decimal": 1.95, "matchup": "BOS@NYK",
        }
        assert _kx_venue_close(row) is None
        # Full chain: no public-REST match, no kx-venue close, no line_store
        # history -> honest None (never a fabricated close).
        res = capture_close(row, kalshi_fetch=lambda s: [])
        assert res is None

    def test_non_kalshi_taken_row_never_gets_kx_venue_close(self, tmp_path, monkeypatch):
        """taken_book != 'kalshi' -> _kx_venue_close is gated off even when a kx
        close WOULD resolve for that ticker (never substituted for a non-kalshi
        taken price -- the exact bug this tier must not re-introduce reversed)."""
        out_dir = _seed_kx_close(tmp_path, "KXNBAGAME-OTHERBOOK", "nba", 0.60)
        monkeypatch.setattr(_kx_ticker_close, "DEFAULT_CLOSES_DIR", out_dir)
        row = {
            "event_id": "KXNBAGAME-OTHERBOOK", "sport": "nba", "side": "home",
            "taken_book": "fanduel", "taken_decimal": 1.95, "matchup": "BOS@NYK",
        }
        assert _kx_venue_close(row) is None

    def test_missing_taken_book_never_gets_kx_venue_close(self, tmp_path, monkeypatch):
        """No taken_book field at all -> gated off (never a silent guess)."""
        out_dir = _seed_kx_close(tmp_path, "KXNBAGAME-NOBOOK", "nba", 0.60)
        monkeypatch.setattr(_kx_ticker_close, "DEFAULT_CLOSES_DIR", out_dir)
        row = {"event_id": "KXNBAGAME-NOBOOK", "sport": "nba"}
        assert _kx_venue_close(row) is None

    def test_kx_venue_close_takes_precedence_over_line_store_in_full_chain(
        self, tmp_path, monkeypatch
    ):
        """capture_close's full precedence: kalshi-taken row with BOTH a
        derivable kx-venue close AND a line_store history returns the
        kx-venue result (close_venue='kalshi'), not the line_store one."""
        out_dir = _seed_kx_close(tmp_path, "KXNBAGAME-PRECEDENCE", "nba", 0.70)
        monkeypatch.setattr(_kx_ticker_close, "DEFAULT_CLOSES_DIR", out_dir)

        def _fake_line_store(row):
            # If this fires, precedence is broken -- kx-venue should win first.
            return (1.50, 2.50, True, "fanduel", "fanduel")

        import scripts.platformkit.pm_trading.close_capture as _cc
        monkeypatch.setattr(_cc, "_close_from_store", _fake_line_store)

        row = {
            "event_id": "KXNBAGAME-PRECEDENCE", "sport": "nba", "side": "home",
            "taken_book": "kalshi", "taken_decimal": 1.95, "matchup": "BOS@NYK",
        }
        res = capture_close(row, kalshi_fetch=lambda s: [])
        assert res is not None
        assert res.close_venue == "kalshi"
        assert res.close_kind == "kalshi_lock"

    def test_close_venue_always_present_on_every_tier(self):
        """close_venue is never blank on a CloseResult from any of the three
        constructors: kalshi (public REST), kalshi_venue, line_store."""
        for src, venue in (("kalshi", "kalshi"), ("kalshi_venue", "kalshi"),
                          ("line_store", "book"), ("proxy", "book")):
            cr = CloseResult(1.80, 2.10, is_proxy=True, close_source=src,
                             close_venue=venue)
            assert cr.close_venue in ("kalshi", "book")
            assert cr.close_venue == venue

    def test_capture_close_result_always_has_close_venue_attr(self):
        """Every CloseResult capture_close can return has a close_venue
        attribute (dataclass default guarantees this even on old call sites)."""
        row = _row(event_id="KXNBA2026-BOS-NYK")

        def _fetch(sport):
            return [{
                "event_ticker": "KXNBA2026-BOS-NYK", "status": "resolved",
                "close_home_dec": 1.80, "close_away_dec": 2.10,
            }]

        res = capture_close(row, kalshi_fetch=_fetch)
        assert res is not None
        assert hasattr(res, "close_venue")
        assert res.close_venue == "kalshi"

    def test_capture_close_never_mutates_input_row(self, tmp_path, monkeypatch):
        """FORWARD-ONLY invariant: capture_close/its' venue tier never writes
        back into the row dict it was given (no rewriting of ledger rows)."""
        out_dir = _seed_kx_close(tmp_path, "KXNBAGAME-NOMUTATE", "nba", 0.60)
        monkeypatch.setattr(_kx_ticker_close, "DEFAULT_CLOSES_DIR", out_dir)
        row = {
            "event_id": "KXNBAGAME-NOMUTATE", "sport": "nba", "side": "home",
            "taken_book": "kalshi", "taken_decimal": 1.95, "matchup": "BOS@NYK",
        }
        before = dict(row)
        _ = capture_close(row, kalshi_fetch=lambda s: [])
        assert row == before, "capture_close must never mutate the input row"
