"""test_ws_lines_consolidation.py — tests for the WS-file additive odds merge.

Covers (via consolidate_for_slate — the function courtvision_router calls):
  - HTTP file + WS file for same book → one "DraftKings" entry, WS (fresher
    captured_at) wins over HTTP (staler captured_at).
  - No "_ws" book label leaks into the books list shown to the user.
  - Failover: WS file absent → HTTP file used, price preserved.
  - HTTP file absent → WS file used.
  - Cross-book isolation: dk dedup does not affect fd entry.

Also covers consolidate() directly to verify the raw-book dedup layer.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATE = "2099-01-15"   # Far-future date; won't collide with real scrape files.

_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

# start_time in ET hours so the ET-date filter matches DATE
_START_TIME = f"{DATE}T23:00:00Z"  # 7 PM ET on DATE


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CANONICAL_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _base_row(
    *,
    book: str,
    over_price: int,
    captured_at: str,
    player_name: str = "LeBron James",
    stat: str = "pts",
    line: float = 24.5,
) -> dict:
    return {
        "captured_at": captured_at,
        "book": book,
        "game_id": "0042500099",
        "player_id": "2544",
        "player_name": player_name,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": -115,
        "start_time": _START_TIME,
    }


@pytest.fixture()
def lines_dir(tmp_path, monkeypatch):
    """Redirect _courtvision_odds._LINES_DIR to a temp dir and clear caches."""
    import api._courtvision_odds as _odds
    ld = tmp_path / "lines"
    ld.mkdir()
    monkeypatch.setattr(_odds, "_LINES_DIR", ld)
    _odds._CACHE.clear()
    # Disable NBA roster filter (no players_nba_active.json in tmp)
    monkeypatch.setattr(_odds, "_NBA_PLAYER_SET", set())
    return ld


# ── helpers that inspect the two output shapes ─────────────────────────────

def _books_by_raw(result_consolidate: list[dict], player: str, stat: str) -> list[dict]:
    """From consolidate() output: return books list for (player, stat).

    consolidate() books entries have raw canonical book key e.g. "dk".
    """
    for p in result_consolidate:
        if p["player"].lower() == player.lower() and p["stat"] == stat:
            return p["books"]
    return []


def _slate_books_by_display(result_slate: list[dict], player: str, stat: str) -> list[dict]:
    """From consolidate_for_slate() output: return books list (display names e.g. 'DraftKings')."""
    for p in result_slate:
        if p["player"].lower() == player.lower() and p["stat"] == stat:
            return p["books"]
    return []


class TestWsHttpMerge:

    # ── consolidate() layer (raw canonical book keys) ──────────────────────

    def test_consolidate_ws_wins_over_http(self, lines_dir):
        """consolidate(): WS (fresher captured_at) beats HTTP for same (player,stat,line,book)."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-115,
                              captured_at=f"{DATE}T02:00:00Z")])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-112,
                              captured_at=f"{DATE}T02:00:15Z")])

        result = _odds.consolidate(DATE)
        books = _books_by_raw(result, "LeBron James", "pts")
        dk_entries = [b for b in books if b["book"] == "dk"]
        assert len(dk_entries) == 1, (
            f"Expected exactly ONE 'dk' raw entry; got {[b['book'] for b in books]}"
        )
        assert dk_entries[0]["over_price"] == -112, (
            f"WS (fresher) price -112 should win; got {dk_entries[0]['over_price']}"
        )

    def test_consolidate_http_wins_when_fresher(self, lines_dir):
        """consolidate(): HTTP file is fresher than WS (e.g. WS stale) → HTTP wins."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-109,
                              captured_at=f"{DATE}T03:00:30Z")])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-115,
                              captured_at=f"{DATE}T03:00:00Z")])

        result = _odds.consolidate(DATE)
        books = _books_by_raw(result, "LeBron James", "pts")
        dk_entries = [b for b in books if b["book"] == "dk"]
        assert len(dk_entries) == 1
        assert dk_entries[0]["over_price"] == -109, (
            f"HTTP (T+30s fresher) should win; got {dk_entries[0]['over_price']}"
        )

    def test_consolidate_http_only(self, lines_dir):
        """consolidate(): WS file absent → HTTP price is returned, no KeyError."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-110,
                              captured_at=f"{DATE}T01:30:00Z")])

        result = _odds.consolidate(DATE)
        books = _books_by_raw(result, "LeBron James", "pts")
        dk_entries = [b for b in books if b["book"] == "dk"]
        assert len(dk_entries) == 1
        assert dk_entries[0]["over_price"] == -110

    def test_consolidate_ws_only(self, lines_dir):
        """consolidate(): HTTP file absent → WS file is the sole source."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-113,
                              captured_at=f"{DATE}T02:05:00Z")])

        result = _odds.consolidate(DATE)
        books = _books_by_raw(result, "LeBron James", "pts")
        dk_entries = [b for b in books if b["book"] == "dk"]
        assert len(dk_entries) == 1
        assert dk_entries[0]["over_price"] == -113

    def test_no_ws_raw_book_key_leaks(self, lines_dir):
        """consolidate(): no raw book key should contain '_ws' suffix."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-110,
                              captured_at=f"{DATE}T01:00:00Z")])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-108,
                              captured_at=f"{DATE}T01:00:10Z")])

        result = _odds.consolidate(DATE)
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        ws_leaks = {k for k in all_book_keys if k.endswith("_ws")}
        assert not ws_leaks, f"_ws book key(s) leaked into consolidate books: {ws_leaks}"

    def test_consolidate_cross_book_isolation(self, lines_dir):
        """consolidate(): DK dedup is isolated from FD — both books appear."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-110,
                              captured_at=f"{DATE}T01:00:00Z")])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-108,
                              captured_at=f"{DATE}T01:00:20Z")])
        _write_csv(lines_dir / f"{DATE}_fd.csv",
                   [_base_row(book="fd", over_price=-114,
                              captured_at=f"{DATE}T01:00:05Z")])

        result = _odds.consolidate(DATE)
        books = _books_by_raw(result, "LeBron James", "pts")
        by_book = {b["book"]: b for b in books}
        assert "dk" in by_book, "dk entry must exist"
        assert "fd" in by_book, "fd entry must exist"
        assert by_book["dk"]["over_price"] == -108, "DK WS price wins"
        assert by_book["fd"]["over_price"] == -114, "FD price unchanged"

    # ── consolidate_for_slate() layer (display names) ──────────────────────

    def test_slate_ws_wins_price_shown(self, lines_dir):
        """consolidate_for_slate(): fresher WS price appears under 'DraftKings' display label."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-115,
                              captured_at=f"{DATE}T02:00:00Z")])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-112,
                              captured_at=f"{DATE}T02:00:15Z")])

        result = _odds.consolidate_for_slate(DATE)
        books = _slate_books_by_display(result, "LeBron James", "pts")
        # In consolidate_for_slate, book is the display name ("DraftKings")
        dk_entries = [b for b in books if b["book"] == "DraftKings"]
        assert len(dk_entries) == 1, (
            f"Expected ONE 'DraftKings' slate entry; got {[b['book'] for b in books]}"
        )
        assert dk_entries[0]["over_odds"] == -112, (
            f"WS (fresher) price -112 should appear; got {dk_entries[0]['over_odds']}"
        )

    def test_slate_no_ws_display_label_leaks(self, lines_dir):
        """consolidate_for_slate(): no book label should contain '_ws' suffix."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-110,
                              captured_at=f"{DATE}T01:00:00Z")])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-108,
                              captured_at=f"{DATE}T01:00:10Z")])
        _write_csv(lines_dir / f"{DATE}_fd_ws.csv",
                   [_base_row(book="fd", over_price=-106,
                              captured_at=f"{DATE}T01:00:05Z")])

        result = _odds.consolidate_for_slate(DATE)
        all_labels = {b["book"] for p in result for b in p["books"]}
        ws_leaks = {lbl for lbl in all_labels
                    if "_ws" in lbl.lower() or lbl.lower().endswith("ws")}
        assert not ws_leaks, (
            f"_ws label(s) leaked into slate books: {ws_leaks}"
        )

    def test_slate_http_failover(self, lines_dir):
        """consolidate_for_slate(): WS absent → HTTP price used correctly."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk.csv",
                   [_base_row(book="dk", over_price=-110,
                              captured_at=f"{DATE}T01:30:00Z")])

        result = _odds.consolidate_for_slate(DATE)
        books = _slate_books_by_display(result, "LeBron James", "pts")
        dk_entries = [b for b in books if b["book"] == "DraftKings"]
        assert len(dk_entries) == 1
        assert dk_entries[0]["over_odds"] == -110

    def test_slate_ws_only_source(self, lines_dir):
        """consolidate_for_slate(): HTTP file missing → WS file is sole source."""
        import api._courtvision_odds as _odds

        _write_csv(lines_dir / f"{DATE}_dk_ws.csv",
                   [_base_row(book="dk", over_price=-113,
                              captured_at=f"{DATE}T02:05:00Z")])

        result = _odds.consolidate_for_slate(DATE)
        books = _slate_books_by_display(result, "LeBron James", "pts")
        dk_entries = [b for b in books if b["book"] == "DraftKings"]
        assert len(dk_entries) == 1
        assert dk_entries[0]["over_odds"] == -113

    def test_slate_multi_player_independent_dedup(self, lines_dir):
        """Each player's prop is deduped independently — WS wins for one, HTTP for another."""
        import api._courtvision_odds as _odds

        # LeBron pts: WS fresher
        _write_csv(lines_dir / f"{DATE}_dk.csv", [
            _base_row(book="dk", over_price=-110,
                      captured_at=f"{DATE}T01:00:00Z",
                      player_name="LeBron James", stat="pts", line=24.5),
            _base_row(book="dk", over_price=-115,
                      captured_at=f"{DATE}T01:00:50Z",
                      player_name="Anthony Davis", stat="reb", line=10.5),
        ])
        _write_csv(lines_dir / f"{DATE}_dk_ws.csv", [
            _base_row(book="dk", over_price=-108,
                      captured_at=f"{DATE}T01:00:20Z",
                      player_name="LeBron James", stat="pts", line=24.5),
            _base_row(book="dk", over_price=-120,
                      captured_at=f"{DATE}T01:00:10Z",
                      player_name="Anthony Davis", stat="reb", line=10.5),
        ])

        result = _odds.consolidate_for_slate(DATE)
        lebron_books = _slate_books_by_display(result, "LeBron James", "pts")
        ad_books = _slate_books_by_display(result, "Anthony Davis", "reb")

        assert lebron_books, "LeBron pts prop missing"
        assert ad_books, "AD reb prop missing"

        lebron_dk = [b for b in lebron_books if b["book"] == "DraftKings"]
        ad_dk = [b for b in ad_books if b["book"] == "DraftKings"]

        assert len(lebron_dk) == 1, f"Expected 1 DK entry for LeBron; got {lebron_dk}"
        assert len(ad_dk) == 1, f"Expected 1 DK entry for AD; got {ad_dk}"
        assert lebron_dk[0]["over_odds"] == -108, "LeBron: WS fresher wins"
        assert ad_dk[0]["over_odds"] == -115, "AD: HTTP fresher wins"
