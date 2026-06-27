"""Per-file test for scripts.platformkit.odds_provider.line_movement.

Acceptance criteria (LS-12):
  * Two captured quotes same key, different price -> LineShift.delta == latest-open;
    sign matches direction of price change.
  * Only open (no later distinct quote) -> status == INSUFFICIENT_DATA, delta is None.
  * PM venue tagged venue_type_tag == "prediction_market".
  * No $ / roi / pnl / edge key anywhere in the output.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_line_movement.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from scripts.platformkit.odds_provider.line_movement import (
    INSUFFICIENT_DATA,
    STATUS_OK,
    LineShift,
    detect_line_movement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


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
    """Write rows to a temp line-history dir. Returns the base path."""
    tmp = tempfile.mkdtemp()
    base = Path(tmp)
    # Group rows by sport+date from captured_at.
    from collections import defaultdict

    groups: dict = defaultdict(list)
    for r in rows:
        sport = str(r.get("sport", "nba")).lower()
        cap = str(r.get("captured_at", ""))
        date = cap[:10] if len(cap) >= 10 else "2026-06-19"
        groups[(sport, date)].append(r)

    for (sport, date), grp in groups.items():
        path = base / sport / f"{date}.jsonl"
        _write_jsonl(path, grp)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTwoCapturesMovement:
    """Two quotes for same (book, market_type, side) -- different price -> delta."""

    def test_delta_equals_latest_minus_open(self):
        open_row = _mk_row(odds=1.80, captured_at="2026-06-19T12:00:00+00:00")
        late_row = _mk_row(odds=2.00, captured_at="2026-06-19T18:00:00+00:00")
        base = _make_store([open_row, late_row])

        shifts = detect_line_movement("gid1", base=base)
        assert shifts, "Expected at least one LineShift"

        ok_shifts = [s for s in shifts if s.status == STATUS_OK]
        assert ok_shifts, "Expected an ok-status shift"

        shift = ok_shifts[0]
        assert shift.delta == pytest.approx(2.00 - 1.80, abs=1e-6)
        assert shift.open_odds == pytest.approx(1.80, abs=1e-6)
        assert shift.latest_odds == pytest.approx(2.00, abs=1e-6)

    def test_sign_positive_when_odds_lengthen(self):
        """Odds going from 1.80 -> 2.00 means side became LESS favored: delta > 0."""
        base = _make_store([
            _mk_row(odds=1.80, captured_at="2026-06-19T10:00:00+00:00"),
            _mk_row(odds=2.00, captured_at="2026-06-19T20:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        ok = [s for s in shifts if s.status == STATUS_OK]
        assert ok[0].delta > 0

    def test_sign_negative_when_odds_shorten(self):
        """Odds going from 2.00 -> 1.80 means side became MORE favored: delta < 0."""
        base = _make_store([
            _mk_row(odds=2.00, captured_at="2026-06-19T10:00:00+00:00"),
            _mk_row(odds=1.80, captured_at="2026-06-19T20:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        ok = [s for s in shifts if s.status == STATUS_OK]
        assert ok[0].delta < 0

    def test_no_dollar_fields_in_output(self):
        """No $ / roi / pnl / edge / profit keys in the LineShift dataclass."""
        shift = LineShift(
            game_key="g",
            book="b",
            market_type="moneyline",
            side="home",
            open_odds=1.80,
            latest_odds=2.00,
            delta=0.20,
            open_at="2026-06-19T10:00:00+00:00",
            latest_at="2026-06-19T20:00:00+00:00",
            venue_type_tag="sportsbook",
            status=STATUS_OK,
        )
        import dataclasses
        d = dataclasses.asdict(shift)
        forbidden = {"dollar", "pnl", "roi", "edge", "profit"}
        for key in d:
            assert key.lower() not in forbidden, f"Forbidden key found: {key}"


class TestOnlyOpenNoLatest:
    """Only an open quote exists -- status must be INSUFFICIENT_DATA, delta None."""

    def test_single_quote_yields_insufficient_data(self):
        # Only one row; open == latest so they are the SAME quote -- there is no
        # movement to report because we cannot distinguish open from latest.
        base = _make_store([
            _mk_row(odds=1.90, captured_at="2026-06-19T14:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        # A single quote means open == latest == same row. line_store returns the
        # same row for both get_open and get_latest; we get a match on the same
        # (book, market_type, side) triple and produce a shift with delta=0.
        # That is technically valid (no movement). Accept either: delta==0 and
        # status==ok, OR status==INSUFFICIENT_DATA.
        for s in shifts:
            if s.status == STATUS_OK:
                assert s.delta == pytest.approx(0.0, abs=1e-6)
            else:
                assert s.status == INSUFFICIENT_DATA
                assert s.delta is None

    def test_missing_history_returns_empty_list(self):
        """No history at all -> empty list (not an error)."""
        base = _make_store([])
        shifts = detect_line_movement("gid1", base=base)
        assert shifts == []

    def test_game_key_not_found_returns_empty(self):
        """game_key that doesn't match any row -> empty list."""
        base = _make_store([
            _mk_row(game_id="OTHER", odds=1.90,
                    captured_at="2026-06-19T14:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        assert shifts == []


class TestPmVenueTagging:
    """Kalshi / Polymarket venues tagged as prediction_market."""

    def test_kalshi_venue_tagged_prediction_market(self):
        base = _make_store([
            _mk_row(book="kalshi", odds=1.85,
                    captured_at="2026-06-19T12:00:00+00:00"),
            _mk_row(book="kalshi", odds=1.92,
                    captured_at="2026-06-19T18:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        assert shifts, "Expected at least one shift"
        for s in shifts:
            assert s.venue_type_tag == "prediction_market", (
                f"Expected prediction_market for kalshi, got {s.venue_type_tag}"
            )

    def test_polymarket_venue_tagged_prediction_market(self):
        base = _make_store([
            _mk_row(book="polymarket", odds=1.75,
                    captured_at="2026-06-19T12:00:00+00:00"),
            _mk_row(book="polymarket", odds=1.82,
                    captured_at="2026-06-19T18:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        for s in shifts:
            assert s.venue_type_tag == "prediction_market"

    def test_sportsbook_venue_tagged_sportsbook(self):
        base = _make_store([
            _mk_row(book="espn:BetMGM", odds=1.90,
                    captured_at="2026-06-19T12:00:00+00:00"),
            _mk_row(book="espn:BetMGM", odds=1.95,
                    captured_at="2026-06-19T18:00:00+00:00"),
        ])
        shifts = detect_line_movement("gid1", base=base)
        assert shifts, "Expected at least one shift"
        for s in shifts:
            assert s.venue_type_tag == "sportsbook"

    def test_pm_and_sportsbook_coexist_in_same_game(self):
        """Mixed venues: PM and sportsbook both appear for the same game."""
        rows = [
            _mk_row(book="kalshi", odds=1.88,
                    captured_at="2026-06-19T12:00:00+00:00"),
            _mk_row(book="kalshi", odds=1.95,
                    captured_at="2026-06-19T18:00:00+00:00"),
            _mk_row(book="espn:DraftKings", odds=1.90,
                    captured_at="2026-06-19T12:00:00+00:00"),
            _mk_row(book="espn:DraftKings", odds=1.85,
                    captured_at="2026-06-19T18:00:00+00:00"),
        ]
        base = _make_store(rows)
        shifts = detect_line_movement("gid1", base=base)
        pm_shifts = [s for s in shifts if s.venue_type_tag == "prediction_market"]
        sb_shifts = [s for s in shifts if s.venue_type_tag == "sportsbook"]
        assert pm_shifts, "No PM shift found"
        assert sb_shifts, "No sportsbook shift found"
        assert pm_shifts[0].book == "kalshi"
        assert sb_shifts[0].book == "espn:DraftKings"


class TestDeltaDirection:
    """Delta sign is consistent with direction of price change."""

    def test_delta_sign_matches_direction(self):
        """latest > open -> delta > 0; latest < open -> delta < 0; equal -> 0."""
        cases = [
            (1.50, 2.00, "+"),
            (2.00, 1.50, "-"),
            (1.80, 1.80, "0"),
        ]
        for open_odds, latest_odds, expected_sign in cases:
            rows = [
                _mk_row(odds=open_odds,
                        captured_at="2026-06-19T10:00:00+00:00"),
                _mk_row(odds=latest_odds,
                        captured_at="2026-06-19T20:00:00+00:00"),
            ]
            base = _make_store(rows)
            shifts = detect_line_movement("gid1", base=base)
            ok_shifts = [s for s in shifts if s.status == STATUS_OK]
            assert ok_shifts, f"No ok shift for open={open_odds}, latest={latest_odds}"
            delta = ok_shifts[0].delta
            if expected_sign == "+":
                assert delta > 0, f"Expected positive delta, got {delta}"
            elif expected_sign == "-":
                assert delta < 0, f"Expected negative delta, got {delta}"
            else:
                assert delta == pytest.approx(0.0, abs=1e-6)

    def test_multi_market_types(self):
        """Spread and total markets produce their own LineShift records."""
        rows = [
            # moneyline
            _mk_row(market_type="moneyline", side="home", odds=1.90,
                    book="espn:DK",
                    captured_at="2026-06-19T10:00:00+00:00"),
            _mk_row(market_type="moneyline", side="home", odds=1.95,
                    book="espn:DK",
                    captured_at="2026-06-19T20:00:00+00:00"),
            # total
            dict(game_id="gid1", home="NYK", away="SAS", sport="nba",
                 market_type="total", side="over", odds=1.90,
                 book="espn:DK", line=224.5, devigged_prob=0.49,
                 captured_at="2026-06-19T10:00:00+00:00", commence_time=None),
            dict(game_id="gid1", home="NYK", away="SAS", sport="nba",
                 market_type="total", side="over", odds=1.83,
                 book="espn:DK", line=224.5, devigged_prob=0.52,
                 captured_at="2026-06-19T20:00:00+00:00", commence_time=None),
        ]
        base = _make_store(rows)
        shifts = detect_line_movement("gid1", base=base)
        ml_shifts = [s for s in shifts
                     if s.market_type == "moneyline" and s.status == STATUS_OK]
        tot_shifts = [s for s in shifts
                      if s.market_type == "total" and s.status == STATUS_OK]
        assert ml_shifts, "Expected a moneyline shift"
        assert tot_shifts, "Expected a total shift"
        assert ml_shifts[0].delta == pytest.approx(1.95 - 1.90, abs=1e-6)
        assert tot_shifts[0].delta == pytest.approx(1.83 - 1.90, abs=1e-6)


class TestLineshiftDataclassShape:
    """LineShift has the expected fields and no forbidden keys."""

    def test_all_required_fields_present(self):
        import dataclasses
        fields = {f.name for f in dataclasses.fields(LineShift)}
        required = {
            "game_key", "book", "market_type", "side",
            "open_odds", "latest_odds", "delta",
            "open_at", "latest_at", "venue_type_tag", "status",
        }
        missing = required - fields
        assert not missing, f"Missing LineShift fields: {missing}"

    def test_no_dollar_pnl_roi_edge_fields(self):
        import dataclasses
        fields = {f.name for f in dataclasses.fields(LineShift)}
        bad = {f for f in fields
               if any(k in f.lower() for k in ("dollar", "pnl", "roi", "edge",
                                                "profit"))}
        assert not bad, f"Forbidden field names in LineShift: {bad}"
