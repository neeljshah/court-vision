"""test_inplay_ws_consumption.py — Consumer-side tests for the DK in-play WS feed.

Tests the critical property: when both an HTTP in-play file
(<date>_dk_inplay.csv, older captured_at) and a WS in-play file
(<date>_dk_inplay_ws.csv, newer captured_at) exist for the same player/stat,
_load_inplay_line_history correctly tracks both captures as separate
time-series entries AND _line_movement_for returns the WS (fresher) price
as line_current.

Also tests:
  - WS file absent → HTTP-only line is intact (no regression)
  - HTTP file absent → WS-only line works
  - _normalize_push from dk_inplay_ws.py produces correct "dk_inplay" rows
  - _write_csv from dk_inplay_ws.py deduplicates on (cap[:16], player, stat, line)

These tests run entirely offline — no network, no NBA API, no real DK WS.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# ── Helpers ───────────────────────────────────────────────────────────────────

DATE = "2099-06-15"  # Far-future date: never collides with real scraped files

_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

_GAME_ID = "0042500399"
_START_TIME = f"{DATE}T23:00:00Z"  # 7 PM ET — ensures ET-date filter matches DATE


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CANONICAL_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _row(
    *,
    book: str,
    captured_at: str,
    over_price: int,
    under_price: int = -115,
    player_name: str = "LeBron James",
    stat: str = "pts",
    line: float = 24.5,
    game_id: str = _GAME_ID,
) -> Dict[str, Any]:
    return {
        "captured_at": captured_at,
        "book": book,
        "game_id": game_id,
        "player_id": "2544",
        "player_name": player_name,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": under_price,
        "start_time": _START_TIME,
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def lines_dir(tmp_path, monkeypatch):
    """Redirect _load_inplay_line_history to use a temp lines directory.

    The function uses _ROOT (module-level Path in courtvision_router) to
    glob data/lines/<date>_*inplay*.csv.  We monkeypatch _ROOT so the
    glob points to our temp directory layout.
    Also clear the cache to prevent cross-test pollution.
    """
    import api.courtvision_router as _router

    # Create the directory tree tmp/data/lines/
    ld = tmp_path / "data" / "lines"
    ld.mkdir(parents=True)

    # Monkeypatch _ROOT so _ROOT / "data" / "lines" resolves to our temp dir
    monkeypatch.setattr(_router, "_ROOT", tmp_path)

    # Clear the in-process cache
    _router._INPLAY_LINE_CACHE.clear()

    yield ld


# ── Tests: _load_inplay_line_history freshest-wins behavior ──────────────────

class TestInplayLineHistoryFreshestWins:
    """Validate that _load_inplay_line_history + _line_movement_for pick
    the freshest captured_at as line_current when both HTTP and WS files exist."""

    def test_ws_newer_gives_fresher_line_current(self, lines_dir):
        """WS file (newer captured_at) → _line_movement_for returns WS price as line_current."""
        import api.courtvision_router as _router

        # HTTP in-play file: T+00, over=-110 (older)
        _write_csv(lines_dir / f"{DATE}_dk_inplay.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T01:00:00",
                 over_price=-110, line=24.5),
        ])
        # WS in-play file: T+30s, over=-108 (newer, WS pushed an update)
        _write_csv(lines_dir / f"{DATE}_dk_inplay_ws.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T01:00:30",
                 over_price=-108, line=24.5),
        ])

        hist = _router._load_inplay_line_history(DATE, frozenset())
        # Should have at least 2 entries for LeBron pts (one per capture)
        lebron_pts = [r for r in hist
                      if r.get("name") == "lebron james" and r.get("stat") == "pts"]
        assert len(lebron_pts) >= 2, (
            f"Expected >=2 captured_at entries (HTTP + WS); got {len(lebron_pts)}"
        )

        move = _router._line_movement_for(hist, "lebron james", "pts")
        assert move["line_current"] is not None, "line_current should not be None"
        assert abs(move["line_current"] - 24.5) < 0.01, (
            f"line_current should be 24.5; got {move['line_current']}"
        )
        # The over_price in the WS row (-108) should be the most recent entry
        # (line_current price isn't directly exposed by _line_movement_for, but
        # we verify via the raw history that the WS entry is the last when sorted
        # by cap)
        sorted_entries = sorted(lebron_pts, key=lambda r: r["cap"])
        last_entry = sorted_entries[-1]
        assert last_entry["over"] == -108, (
            f"WS (newer, cap={last_entry['cap']}) should have over=-108; "
            f"got {last_entry['over']}"
        )

    def test_http_only_line_intact_when_ws_absent(self, lines_dir):
        """When WS file is absent, HTTP-only line is returned unmodified."""
        import api.courtvision_router as _router

        _write_csv(lines_dir / f"{DATE}_dk_inplay.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T02:00:00",
                 over_price=-115, line=24.5),
        ])
        # No WS file written

        hist = _router._load_inplay_line_history(DATE, frozenset())
        lebron_pts = [r for r in hist
                      if r.get("name") == "lebron james" and r.get("stat") == "pts"]
        assert len(lebron_pts) == 1, (
            f"Expected exactly 1 entry (HTTP only); got {len(lebron_pts)}"
        )
        assert lebron_pts[0]["over"] == -115, (
            f"HTTP price -115 should be intact; got {lebron_pts[0]['over']}"
        )

    def test_ws_only_when_http_absent(self, lines_dir):
        """When HTTP file is absent, WS file alone is used correctly."""
        import api.courtvision_router as _router

        # No HTTP file
        _write_csv(lines_dir / f"{DATE}_dk_inplay_ws.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T03:00:00",
                 over_price=-112, line=23.5),
        ])

        hist = _router._load_inplay_line_history(DATE, frozenset())
        lebron_pts = [r for r in hist
                      if r.get("name") == "lebron james" and r.get("stat") == "pts"]
        assert len(lebron_pts) == 1, (
            f"Expected 1 entry (WS only); got {len(lebron_pts)}"
        )
        assert lebron_pts[0]["over"] == -112
        assert abs(lebron_pts[0]["line"] - 23.5) < 0.01

    def test_line_current_is_freshest_across_multiple_captures(self, lines_dir):
        """Three captures (HTTP T1, WS T2, WS T3) → line_current is from T3."""
        import api.courtvision_router as _router

        # HTTP at T+00 (line=24.5, over=-115)
        _write_csv(lines_dir / f"{DATE}_dk_inplay.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T00:00:00",
                 over_price=-115, line=24.5),
        ])
        # WS at T+30 and T+60 (line moved to 25.5, then 25.5 again with tighter juice)
        _write_csv(lines_dir / f"{DATE}_dk_inplay_ws.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T00:00:30",
                 over_price=-112, line=25.5),
            _row(book="dk_inplay", captured_at=f"{DATE}T00:01:00",
                 over_price=-109, line=25.5),
        ])

        hist = _router._load_inplay_line_history(DATE, frozenset())
        lebron_pts = [r for r in hist
                      if r.get("name") == "lebron james" and r.get("stat") == "pts"]

        move = _router._line_movement_for(hist, "lebron james", "pts")
        assert abs(move["line_open"] - 24.5) < 0.01, (
            f"line_open should be 24.5 (HTTP at T0); got {move['line_open']}"
        )
        assert abs(move["line_current"] - 25.5) < 0.01, (
            f"line_current should be 25.5 (WS at T1:00); got {move['line_current']}"
        )
        assert move["line_delta"] is not None
        assert abs(move["line_delta"] - 1.0) < 0.01, (
            f"line_delta should be +1.0; got {move['line_delta']}"
        )

    def test_book_label_is_dk_inplay_not_ws_suffixed(self, lines_dir):
        """Both HTTP and WS files must produce book='dk_inplay' — no '_ws' leak."""
        import api.courtvision_router as _router

        _write_csv(lines_dir / f"{DATE}_dk_inplay.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T01:00:00",
                 over_price=-110, line=24.5),
        ])
        _write_csv(lines_dir / f"{DATE}_dk_inplay_ws.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T01:00:30",
                 over_price=-108, line=24.5),
        ])

        hist = _router._load_inplay_line_history(DATE, frozenset())
        books_seen = {r.get("book", "") for r in hist}
        ws_leaks = {b for b in books_seen if b.endswith("_ws")}
        assert not ws_leaks, (
            f"No '_ws'-suffixed book labels should appear in history; got: {ws_leaks}"
        )
        assert "dk_inplay" in books_seen, "dk_inplay book label must be present"

    def test_no_cross_game_contamination(self, lines_dir):
        """game_id filter (canon_ids) restricts to correct game only."""
        import api.courtvision_router as _router

        other_game = "0042500001"
        _write_csv(lines_dir / f"{DATE}_dk_inplay.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T01:00:00",
                 over_price=-110, line=24.5, game_id=_GAME_ID),
        ])
        _write_csv(lines_dir / f"{DATE}_dk_inplay_ws.csv", [
            _row(book="dk_inplay", captured_at=f"{DATE}T01:00:30",
                 over_price=-108, line=24.5, game_id=other_game),
        ])

        # Filter to only _GAME_ID
        hist_filtered = _router._load_inplay_line_history(
            DATE, frozenset({_GAME_ID})
        )
        # Only HTTP row (game_id=_GAME_ID) should appear in matched result
        assert all(r["over"] in (-110, None) for r in hist_filtered), (
            "WS row from a different game should not appear in matched history"
        )


# ── Tests: dk_inplay_ws._normalize_push ──────────────────────────────────────

class TestNormalizePush:
    """Unit tests for dk_inplay_ws._normalize_push — verifies correct row shape."""

    def _make_payload(
        self,
        player_name: str = "LeBron James",
        player_id: str = "2544",
        line: float = 24.5,
        over_american: str = "-112",
        under_american: str = "-108",
        event_id: str = "EVT-001",
    ) -> Dict[str, Any]:
        """Synthesize a minimal DK WS push payload with a single O/U market."""
        sel_over = {
            "marketId": "MKT-001",
            "participants": [{"type": "Player", "name": player_name, "id": player_id}],
            "points": line,
            "outcomeType": "over",
            "displayOdds": {"american": over_american},
        }
        sel_under = {
            "marketId": "MKT-001",
            "participants": [{"type": "Player", "name": player_name, "id": player_id}],
            "points": line,
            "outcomeType": "under",
            "displayOdds": {"american": under_american},
        }
        return {
            "events": [{"id": event_id, "startEventDate": _START_TIME}],
            "markets": [{"id": "MKT-001", "eventId": event_id}],
            "selections": [sel_over, sel_under],
        }

    def test_ou_market_produces_correct_row(self):
        """Standard O/U market → one row with over_price, under_price, book='dk_inplay'."""
        from scripts.dk_inplay_ws import _normalize_push

        payload = self._make_payload(line=24.5, over_american="-112", under_american="-108")
        rows = _normalize_push(payload, "pts", "2099-06-15T01:00:00")

        assert len(rows) == 1, f"Expected 1 row; got {len(rows)}"
        r = rows[0]
        assert r["book"] == "dk_inplay", f"book must be 'dk_inplay'; got {r['book']}"
        assert abs(r["line"] - 24.5) < 0.01
        assert r["over_price"] == -112
        assert r["under_price"] == -108
        assert r["player_name"] == "LeBron James"
        assert r["stat"] == "pts"

    def test_unicode_minus_odds_parsed(self):
        """DK uses U+2212 (−) for negative odds — must parse correctly."""
        from scripts.dk_inplay_ws import _normalize_push

        payload = self._make_payload(over_american="−110", under_american="−110")
        rows = _normalize_push(payload, "reb", "2099-06-15T01:00:00")

        assert len(rows) == 1
        assert rows[0]["over_price"] == -110
        assert rows[0]["under_price"] == -110

    def test_missing_points_row_skipped(self):
        """Selections without 'points' field → no row emitted."""
        from scripts.dk_inplay_ws import _normalize_push

        payload = self._make_payload()
        # Remove points from all selections
        for s in payload["selections"]:
            s.pop("points", None)
        rows = _normalize_push(payload, "pts", "2099-06-15T01:00:00")
        assert rows == [], f"Expected no rows for missing points; got {rows}"

    def test_empty_payload_no_crash(self):
        """Empty or None payload → returns []."""
        from scripts.dk_inplay_ws import _normalize_push

        assert _normalize_push({}, "pts", "2099-06-15T01:00:00") == []
        assert _normalize_push(None, "pts", "2099-06-15T01:00:00") == []  # type: ignore[arg-type]

    def test_book_label_always_dk_inplay(self):
        """book column in every emitted row must be exactly 'dk_inplay'."""
        from scripts.dk_inplay_ws import _normalize_push, _INPLAY_BOOK_LABEL

        assert _INPLAY_BOOK_LABEL == "dk_inplay", (
            f"_INPLAY_BOOK_LABEL must be 'dk_inplay'; got '{_INPLAY_BOOK_LABEL}'"
        )
        payload = self._make_payload()
        rows = _normalize_push(payload, "pts", "2099-06-15T01:00:00")
        for r in rows:
            assert r["book"] == "dk_inplay", (
                f"All rows must have book='dk_inplay'; got '{r['book']}'"
            )


# ── Tests: dk_inplay_ws._write_csv ───────────────────────────────────────────

class TestWriteCsv:
    """Unit tests for dk_inplay_ws._write_csv deduplication logic."""

    def _sample_rows(self, captured_at: str, over_price: int) -> List[Dict[str, Any]]:
        return [{
            "captured_at": captured_at,
            "book": "dk_inplay",
            "game_id": _GAME_ID,
            "player_id": "2544",
            "player_name": "LeBron James",
            "stat": "pts",
            "line": 24.5,
            "over_price": over_price,
            "under_price": -115,
            "start_time": _START_TIME,
        }]

    def test_first_write_creates_header_and_row(self, tmp_path):
        from scripts.dk_inplay_ws import _write_csv

        path = str(tmp_path / f"{DATE}_dk_inplay_ws.csv")
        rows = self._sample_rows("2099-06-15T01:00:00", -112)
        written = _write_csv(rows, path)

        assert written == 1
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        assert lines[0].startswith("captured_at"), "First line must be CSV header"
        assert len(lines) == 2  # header + 1 row

    def test_same_minute_deduplication(self, tmp_path):
        """Two calls with same captured_at[:16] + player + stat + line → only 1 row."""
        from scripts.dk_inplay_ws import _write_csv

        path = str(tmp_path / f"{DATE}_dk_inplay_ws.csv")
        # First write at T01:00:00
        _write_csv(self._sample_rows("2099-06-15T01:00:00", -112), path)
        # Second write at same minute, different seconds — must be deduped
        n2 = _write_csv(self._sample_rows("2099-06-15T01:00:45", -110), path)

        assert n2 == 0, f"Duplicate within same minute should write 0 rows; got {n2}"
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # header + 1 row total

    def test_different_minute_both_written(self, tmp_path):
        """Two captures at different minutes → both written (time-series accumulation)."""
        from scripts.dk_inplay_ws import _write_csv

        path = str(tmp_path / f"{DATE}_dk_inplay_ws.csv")
        _write_csv(self._sample_rows("2099-06-15T01:00:00", -112), path)
        n2 = _write_csv(self._sample_rows("2099-06-15T01:01:00", -108), path)

        assert n2 == 1, f"Second capture at new minute should write 1 row; got {n2}"
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3  # header + 2 rows

    def test_canonical_fields_in_header(self, tmp_path):
        """Output CSV must have exactly the canonical field names in order."""
        from scripts.dk_inplay_ws import _write_csv, _CANONICAL_FIELDS

        path = str(tmp_path / f"{DATE}_dk_inplay_ws.csv")
        _write_csv(self._sample_rows("2099-06-15T01:00:00", -112), path)

        with open(path, encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        assert header == _CANONICAL_FIELDS, (
            f"CSV header mismatch.\n  Expected: {_CANONICAL_FIELDS}\n  Got:      {header}"
        )


# ── Tests: start_dk_inplay_ws idling behavior when not configured ─────────────

class TestIdleBehaviorWhenNotConfigured:
    """start_dk_inplay_ws must idle gracefully when subcategory IDs are empty."""

    def test_disabled_env_returns_immediately(self, monkeypatch):
        """DK_INPLAY_WS_ENABLED not set → coroutine completes immediately."""
        import asyncio
        import scripts.dk_inplay_ws as ws_mod

        monkeypatch.delenv("DK_INPLAY_WS_ENABLED", raising=False)

        # asyncio.run() wraps the coroutine — should return in < 1s
        asyncio.run(
            asyncio.wait_for(ws_mod.start_dk_inplay_ws(), timeout=2.0)
        )

    def test_empty_subcategory_ids_idles_without_crash(self, monkeypatch):
        """When _INPLAY_SUBCATEGORY_IDS is empty, subscriber idles without crashing.

        We run the coroutine in a new event loop and cancel it after a short
        iteration, confirming it handles CancelledError cleanly.
        """
        import asyncio
        import scripts.dk_inplay_ws as ws_mod

        monkeypatch.setenv("DK_INPLAY_WS_ENABLED", "1")
        monkeypatch.setattr(ws_mod, "_INPLAY_SUBCATEGORY_IDS", {})
        # Patch heartbeat to be a no-op (avoids disk I/O in tests)
        monkeypatch.setattr(ws_mod, "_hb", lambda _name: None)

        async def _run():
            """Run start_dk_inplay_ws and cancel it after one sleep iteration."""
            task = asyncio.create_task(ws_mod.start_dk_inplay_ws())
            # Yield so the coroutine reaches the asyncio.sleep inside the idle loop
            for _ in range(10):
                await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # Expected — idle loop was cancelled cleanly

        # Must complete without raising (CancelledError is caught inside _run)
        asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
