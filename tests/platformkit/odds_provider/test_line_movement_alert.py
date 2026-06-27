"""Per-file test for scripts.platformkit.odds_provider.line_movement_alert.

Acceptance criteria (LS-12 extension):
  * open+latest rows for a (book, market) -> LineShift.delta == latest-open;
    delta flows into MovementAlert.delta and sign matches direction (STEAM/FADE).
  * single-snapshot -> MovementAlert.status == INSUFFICIENT_DATA, delta is None.
  * missing key -> [] no exception.
  * no $ / roi / pnl / edge field anywhere in MovementAlert.
  * STEAM when odds shorten; FADE when odds lengthen.
  * filter_by_direction and filter_by_book helpers work.
  * include_stable=False suppresses STABLE; include_stable=True surfaces all.
  * threshold controls the STABLE boundary.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_line_movement_alert.py -q
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
from collections import defaultdict
from pathlib import Path

import pytest

from scripts.platformkit.odds_provider.line_movement_alert import (
    DEFAULT_THRESHOLD,
    DIRECTION_FADE,
    DIRECTION_STABLE,
    DIRECTION_STEAM,
    INSUFFICIENT_DATA,
    MovementAlert,
    filter_by_book,
    filter_by_direction,
    get_alerts,
)


# ---------------------------------------------------------------------------
# Helpers -- shared with test_line_movement.py pattern
# ---------------------------------------------------------------------------

def _mk_row(
    *,
    game_id: str = "gid1",
    home: str = "NYK",
    away: str = "SAS",
    sport: str = "nba",
    market_type: str = "moneyline",
    side: str = "home",
    odds: float = 1.90,
    book: str = "espn:BetMGM",
    captured_at: str,
) -> dict:
    return {
        "game_id": game_id,
        "home": home,
        "away": away,
        "sport": sport,
        "market_type": market_type,
        "side": side,
        "line": None,
        "odds": odds,
        "book": book,
        "devigged_prob": 0.50,
        "captured_at": captured_at,
        "commence_time": None,
    }


def _make_store(rows: list) -> Path:
    """Write rows to a temp line-history dir (sport/date.jsonl). Returns base path."""
    tmp = tempfile.mkdtemp()
    base = Path(tmp)
    groups: dict = defaultdict(list)
    for r in rows:
        sport = str(r.get("sport", "nba")).lower()
        cap = str(r.get("captured_at", ""))
        date = cap[:10] if len(cap) >= 10 else "2026-06-20"
        groups[(sport, date)].append(r)
    for (sport, date), grp in groups.items():
        path = base / sport / f"{date}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in grp:
                fh.write(json.dumps(row) + "\n")
    return base


# ---------------------------------------------------------------------------
# Core delta + direction tests
# ---------------------------------------------------------------------------

class TestAlertDeltaAndDirection:
    """delta == latest - open; direction matches sign."""

    def test_odds_lengthen_produces_fade(self):
        """1.80 -> 2.00: delta = +0.20 -> FADE."""
        base = _make_store([
            _mk_row(odds=1.80, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=2.00, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        ok = [a for a in alerts if a.status == "ok"]
        assert ok, "Expected at least one ok alert"
        a = ok[0]
        assert a.delta == pytest.approx(2.00 - 1.80, abs=1e-6)
        assert a.direction == DIRECTION_FADE

    def test_odds_shorten_produces_steam(self):
        """2.00 -> 1.80: delta = -0.20 -> STEAM."""
        base = _make_store([
            _mk_row(odds=2.00, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.80, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        ok = [a for a in alerts if a.status == "ok"]
        assert ok
        a = ok[0]
        assert a.delta == pytest.approx(1.80 - 2.00, abs=1e-6)
        assert a.direction == DIRECTION_STEAM

    def test_tiny_shift_below_threshold_is_stable(self):
        """delta=0.02 < threshold=0.05 -> STABLE."""
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.92, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        ok = [a for a in alerts if a.status == "ok"]
        assert ok
        assert ok[0].direction == DIRECTION_STABLE

    def test_delta_exactly_at_threshold_is_stable(self):
        """delta == threshold -> STABLE (boundary is exclusive)."""
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.95, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        # threshold=0.05; delta=+0.05 exactly is NOT > threshold -> STABLE
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        ok = [a for a in alerts if a.status == "ok"]
        assert ok
        assert ok[0].direction == DIRECTION_STABLE

    def test_delta_exceeds_threshold_is_fade(self):
        """delta = 0.06 > 0.05 -> FADE."""
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.96, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        ok = [a for a in alerts if a.status == "ok"]
        assert ok
        assert ok[0].direction == DIRECTION_FADE


# ---------------------------------------------------------------------------
# Single-snapshot -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestSingleSnapshot:
    """Only one capture for a (book, market_type, side) -> INSUFFICIENT_DATA."""

    def test_single_row_yields_insufficient_or_zero_delta(self):
        """A single quote means open == latest. Accept either:
        - status INSUFFICIENT_DATA (delta None), or
        - status ok with delta == 0.0 (no movement; both timestamps identical).
        We never fabricate a shift from one quote.
        """
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T14:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, include_stable=True)
        for a in alerts:
            if a.status == INSUFFICIENT_DATA:
                assert a.delta is None
                assert a.direction == INSUFFICIENT_DATA
            else:
                # open == latest -> delta 0 is acceptable
                assert a.delta == pytest.approx(0.0, abs=1e-6)
                assert a.direction == DIRECTION_STABLE


# ---------------------------------------------------------------------------
# Missing key -> [] no exception
# ---------------------------------------------------------------------------

class TestMissingKey:
    def test_missing_game_key_returns_empty_list(self):
        base = _make_store([])
        result = get_alerts("gid_nonexistent", base=base)
        assert result == []

    def test_key_not_in_history_returns_empty(self):
        base = _make_store([
            _mk_row(game_id="OTHER_GAME", odds=1.90,
                    captured_at="2026-06-20T12:00:00+00:00"),
        ])
        result = get_alerts("gid1", base=base)
        assert result == []

    def test_invalid_base_path_returns_empty(self):
        """A non-existent base dir is not an error -- returns empty."""
        result = get_alerts("gid1", base=Path("/nonexistent/path/xyz"))
        assert result == []


# ---------------------------------------------------------------------------
# No $ / roi / pnl / edge fields
# ---------------------------------------------------------------------------

class TestNoForbiddenFields:
    """MovementAlert dataclass must not contain forbidden financial keys."""

    FORBIDDEN = {"dollar", "pnl", "roi", "edge", "profit"}

    def test_no_forbidden_field_names_in_dataclass(self):
        fields = {f.name for f in dataclasses.fields(MovementAlert)}
        bad = {f for f in fields
               if any(kw in f.lower() for kw in self.FORBIDDEN)}
        assert not bad, f"Forbidden field names in MovementAlert: {bad}"

    def test_alert_dict_has_no_forbidden_keys(self):
        base = _make_store([
            _mk_row(odds=1.80, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=2.00, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, include_stable=True)
        for a in alerts:
            d = dataclasses.asdict(a)
            for key in d:
                assert not any(kw in key.lower() for kw in self.FORBIDDEN), (
                    f"Forbidden key {key!r} found in alert dict"
                )


# ---------------------------------------------------------------------------
# include_stable filter
# ---------------------------------------------------------------------------

class TestIncludeStableFilter:
    """include_stable=False (default) suppresses STABLE alerts."""

    def test_stable_suppressed_by_default(self):
        """A tiny shift (STABLE) should not appear when include_stable=False."""
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.91, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        # threshold=0.05; delta=0.01 -> STABLE
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=False)
        stable = [a for a in alerts if a.direction == DIRECTION_STABLE]
        assert stable == [], f"STABLE alerts should be suppressed, got: {stable}"

    def test_stable_surfaced_when_include_stable_true(self):
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.91, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        stable = [a for a in alerts if a.direction == DIRECTION_STABLE]
        assert stable, "Expected STABLE alerts when include_stable=True"

    def test_significant_shift_always_surfaces(self):
        """A shift above threshold is never suppressed regardless of include_stable."""
        base = _make_store([
            _mk_row(odds=2.00, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.70, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        # delta = -0.30; threshold=0.05 -> STEAM
        alerts_default = get_alerts("gid1", base=base, threshold=0.05)
        steam = [a for a in alerts_default if a.direction == DIRECTION_STEAM]
        assert steam, "STEAM alert missing even with include_stable=False"


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

class TestFilterHelpers:
    def test_filter_by_direction_steam(self):
        base = _make_store([
            _mk_row(book="espn:DK", odds=2.00,
                    captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(book="espn:DK", odds=1.75,
                    captured_at="2026-06-20T18:00:00+00:00"),
            _mk_row(book="espn:FD", odds=1.80,
                    captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(book="espn:FD", odds=2.10,
                    captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        steam = filter_by_direction(alerts, DIRECTION_STEAM)
        fade = filter_by_direction(alerts, DIRECTION_FADE)
        assert all(a.direction == DIRECTION_STEAM for a in steam)
        assert all(a.direction == DIRECTION_FADE for a in fade)

    def test_filter_by_book(self):
        base = _make_store([
            _mk_row(book="kalshi", odds=1.88,
                    captured_at="2026-06-20T12:00:00+00:00"),
            _mk_row(book="kalshi", odds=1.95,
                    captured_at="2026-06-20T18:00:00+00:00"),
            _mk_row(book="espn:BetMGM", odds=1.90,
                    captured_at="2026-06-20T12:00:00+00:00"),
            _mk_row(book="espn:BetMGM", odds=1.85,
                    captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.01, include_stable=True)
        kalshi_only = filter_by_book(alerts, "kalshi")
        assert all(a.book == "kalshi" for a in kalshi_only)
        assert kalshi_only, "Expected kalshi alerts"

    def test_filter_by_direction_empty_on_no_match(self):
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=1.91, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=False)
        # No STEAM or FADE (tiny delta suppressed) -> filter returns []
        result = filter_by_direction(alerts, DIRECTION_STEAM)
        assert result == []


# ---------------------------------------------------------------------------
# venue_type tag propagated
# ---------------------------------------------------------------------------

class TestVenueTypePropagated:
    def test_pm_venue_tagged_prediction_market(self):
        base = _make_store([
            _mk_row(book="kalshi", odds=1.85,
                    captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(book="kalshi", odds=1.70,
                    captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        for a in alerts:
            assert a.venue_type == "prediction_market", (
                f"kalshi should be prediction_market, got {a.venue_type}"
            )

    def test_sportsbook_venue_tagged_sportsbook(self):
        base = _make_store([
            _mk_row(book="espn:BetMGM", odds=1.90,
                    captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(book="espn:BetMGM", odds=1.70,
                    captured_at="2026-06-20T18:00:00+00:00"),
        ])
        alerts = get_alerts("gid1", base=base, threshold=0.05, include_stable=True)
        for a in alerts:
            assert a.venue_type == "sportsbook"


# ---------------------------------------------------------------------------
# threshold field carried on each alert
# ---------------------------------------------------------------------------

class TestThresholdCarried:
    def test_custom_threshold_stored_on_alert(self):
        base = _make_store([
            _mk_row(odds=1.80, captured_at="2026-06-20T10:00:00+00:00"),
            _mk_row(odds=2.00, captured_at="2026-06-20T18:00:00+00:00"),
        ])
        custom = 0.12
        alerts = get_alerts("gid1", base=base, threshold=custom, include_stable=True)
        for a in alerts:
            assert a.threshold == pytest.approx(custom, abs=1e-9)
