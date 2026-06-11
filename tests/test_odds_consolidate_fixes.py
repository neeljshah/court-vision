"""test_odds_consolidate_fixes.py — regression tests for Bug 1, Bug 3, Bug 10 fixes.

Bug 1 (HIGH): In-play CSVs (<date>_fd_inplay.csv, <date>_dk_inplay.csv) must NOT
    contribute any book entry to consolidate_for_slate() or consolidate().

Bug 3 (MEDIUM): Freshest-wins merge must inherit HTTP row's non-empty selection IDs
    when the WS (fresher, winner) row has empty selection IDs, and must recompute
    deeplink URLs from the inherited IDs.

Bug 10 (LOW): Book quotes whose captured_at is older than _MAX_PREGAME_QUOTE_AGE_SEC
    (24 h) are dropped while ANY fresh quote survives. Round 1b graceful-stale
    fallback: if the age cap would empty a date that HAD raw rows, the freshest
    stale quote per (prop, book) is RE-INCLUDED instead — tagged lines_stale=True
    with captured_at preserved — so a stale slate beats an empty slate.
"""
from __future__ import annotations

import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

DATE = "2099-06-15"  # Far-future; won't collide with real scrape files.
_START_TIME = f"{DATE}T23:00:00Z"  # 7 PM ET on DATE (matches ET-date filter)

_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]
_EXTENDED_FIELDS = _CANONICAL_FIELDS + [
    "book_selection_id_over", "book_selection_id_under",
]


def _ts_utc(hours_ago: float = 0) -> str:
    """Return a UTC ISO timestamp `hours_ago` hours in the past."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_csv(path: Path, rows: list[dict], extended: bool = False) -> None:
    fields = _EXTENDED_FIELDS if extended else _CANONICAL_FIELDS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _base_row(
    *,
    book: str,
    over_price: int = -115,
    under_price: int = -110,
    captured_at: str | None = None,
    player_name: str = "LeBron James",
    stat: str = "pts",
    line: float = 24.5,
    sel_over: str = "",
    sel_under: str = "",
) -> dict:
    return {
        "captured_at": captured_at or _ts_utc(1),  # default: 1 h ago (fresh)
        "book": book,
        "game_id": "0042500099",
        "player_id": "2544",
        "player_name": player_name,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": under_price,
        "start_time": _START_TIME,
        "book_selection_id_over": sel_over,
        "book_selection_id_under": sel_under,
    }


@pytest.fixture()
def lines_dir(tmp_path, monkeypatch):
    """Redirect _courtvision_odds._LINES_DIR to a tmp dir and clear caches."""
    import api._courtvision_odds as _odds
    ld = tmp_path / "lines"
    ld.mkdir()
    monkeypatch.setattr(_odds, "_LINES_DIR", ld)
    _odds._CACHE.clear()
    # Disable NBA roster filter so synthetic player names pass through.
    monkeypatch.setattr(_odds, "_NBA_PLAYER_SET", set())
    return ld


# ══════════════════════════════════════════════════════════════════════════════
# Bug 1 — In-play CSVs must not leak into the pregame consolidated slate
# ══════════════════════════════════════════════════════════════════════════════

class TestBug1InplayExclusion:

    def test_inplay_csv_not_in_consolidate(self, lines_dir):
        """A <date>_fd_inplay.csv must NOT contribute any book to consolidate()."""
        import api._courtvision_odds as _odds

        # Write a normal pregame file and an in-play file for the same date.
        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110)],
        )
        _write_csv(
            lines_dir / f"{DATE}_fd_inplay.csv",
            [_base_row(book="fd_inplay", over_price=2000)],  # +2000 live odds
        )

        result = _odds.consolidate(DATE)
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        assert "fd_inplay" not in all_book_keys, (
            f"fd_inplay book must be excluded from pregame consolidate; "
            f"found books: {all_book_keys}"
        )
        assert "dk" in all_book_keys, "dk pregame book must still be present"

    def test_inplay_csv_not_in_consolidate_for_slate(self, lines_dir):
        """A <date>_dk_inplay.csv must NOT appear in consolidate_for_slate()."""
        import api._courtvision_odds as _odds

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-108)],
        )
        _write_csv(
            lines_dir / f"{DATE}_dk_inplay.csv",
            [_base_row(book="dk_inplay", over_price=1500)],
        )

        result = _odds.consolidate_for_slate(DATE)
        # consolidate_for_slate uses _BOOK_DISPLAY names for the book key.
        all_labels = {b["book"] for p in result for b in p["books"]}
        inplay_labels = {lbl for lbl in all_labels if "inplay" in lbl.lower()
                         or "live" in lbl.lower()}
        assert not inplay_labels, (
            f"In-play labels must not appear in slate; found: {inplay_labels}"
        )

    def test_both_inplay_books_excluded(self, lines_dir):
        """Both fd_inplay and dk_inplay are excluded; their prices must not set best_price."""
        import api._courtvision_odds as _odds

        # Only inplay files present for this date.
        _write_csv(
            lines_dir / f"{DATE}_fd_inplay.csv",
            [_base_row(book="fd_inplay", over_price=3000)],
        )
        _write_csv(
            lines_dir / f"{DATE}_dk_inplay.csv",
            [_base_row(book="dk_inplay", over_price=2500)],
        )

        result = _odds.consolidate(DATE)
        # No pregame books → prop list should be empty (or LeBron prop has 0 books).
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        assert not (all_book_keys & {"fd_inplay", "dk_inplay"}), (
            f"In-play keys must never appear in consolidate output: {all_book_keys}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Bug 3 — Freshest-wins merge must inherit HTTP selection IDs into WS winner
# ══════════════════════════════════════════════════════════════════════════════

class TestBug3SelectionIdInheritance:

    def test_ws_winner_inherits_http_selection_ids(self, lines_dir, monkeypatch):
        """HTTP row (older, has sel IDs) + WS row (newer, no sel IDs) for same
        (player,stat,line,book) → result has WS price AND HTTP selection IDs."""
        # Patch _book_deeplink to record calls and return predictable URLs.
        import api._courtvision_odds as _odds

        deeplink_calls: list[dict] = []

        def _fake_deeplink(book, prop, side="OVER", stake=10.0):
            deeplink_calls.append({"book": book, "prop": prop, "side": side})
            sel_id = (prop.get("selection_id_over") if side == "OVER"
                      else prop.get("selection_id_under")) or ""
            if sel_id:
                return {"web_url": f"https://fake.betslip/{sel_id}", "app_url": None}
            return {"web_url": "https://fake.generic/", "app_url": None}

        monkeypatch.setattr(_odds, "_book_deeplink", _fake_deeplink)

        # HTTP file — older timestamp, has selection IDs.
        http_captured = _ts_utc(2)  # 2 h ago
        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(
                book="dk", over_price=-115,
                captured_at=http_captured,
                sel_over="outcome_OVER_999",
                sel_under="outcome_UNDER_999",
            )],
            extended=True,
        )
        # WS file — newer timestamp, no selection IDs (WS schema omits them).
        ws_captured = _ts_utc(1)  # 1 h ago (fresher)
        _write_csv(
            lines_dir / f"{DATE}_dk_ws.csv",
            [_base_row(
                book="dk", over_price=-112,  # WS has a better price
                captured_at=ws_captured,
                sel_over="",
                sel_under="",
            )],
            extended=True,
        )

        result = _odds.consolidate(DATE)
        dk_entries = [
            b for p in result for b in p["books"]
            if b["book"] == "dk"
        ]
        assert len(dk_entries) == 1, f"Expected 1 DK entry; got {dk_entries}"
        entry = dk_entries[0]

        # WS price must win.
        assert entry["over_price"] == -112, (
            f"WS fresher price must win; got {entry['over_price']}"
        )
        # HTTP selection IDs must be inherited.
        assert entry["selection_id_over"] == "outcome_OVER_999", (
            f"selection_id_over not inherited; got '{entry['selection_id_over']}'"
        )
        assert entry["selection_id_under"] == "outcome_UNDER_999", (
            f"selection_id_under not inherited; got '{entry['selection_id_under']}'"
        )
        # Deeplink URL must be non-generic (built from the inherited ID).
        assert "outcome_OVER_999" in entry["deeplink_over_web"], (
            f"deeplink_over_web should include inherited sel ID; "
            f"got '{entry['deeplink_over_web']}'"
        )

    def test_ws_own_selection_ids_not_overwritten(self, lines_dir, monkeypatch):
        """WS row with its own non-empty selection IDs keeps them (not overwritten by HTTP)."""
        import api._courtvision_odds as _odds

        monkeypatch.setattr(_odds, "_book_deeplink",
                            lambda book, prop, side="OVER", stake=10.0: {
                                "web_url": f"https://x/{prop.get('selection_id_over','')}/{prop.get('selection_id_under','')}",
                                "app_url": None,
                            })

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-115, captured_at=_ts_utc(2),
                       sel_over="http_over_id", sel_under="http_under_id")],
            extended=True,
        )
        _write_csv(
            lines_dir / f"{DATE}_dk_ws.csv",
            [_base_row(book="dk", over_price=-110, captured_at=_ts_utc(1),
                       sel_over="ws_over_id", sel_under="ws_under_id")],
            extended=True,
        )

        result = _odds.consolidate(DATE)
        dk = next((b for p in result for b in p["books"] if b["book"] == "dk"), None)
        assert dk is not None
        # WS has its own IDs — must keep them, not inherit HTTP's.
        assert dk["selection_id_over"] == "ws_over_id", (
            f"WS own sel_over should be kept; got '{dk['selection_id_over']}'"
        )
        assert dk["selection_id_under"] == "ws_under_id"

    def test_http_only_no_change(self, lines_dir, monkeypatch):
        """HTTP-only (no WS file): selection IDs come through unchanged."""
        import api._courtvision_odds as _odds

        monkeypatch.setattr(_odds, "_book_deeplink",
                            lambda book, prop, side="OVER", stake=10.0: {
                                "web_url": "", "app_url": None,
                            })

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110, captured_at=_ts_utc(1),
                       sel_over="only_over", sel_under="only_under")],
            extended=True,
        )

        result = _odds.consolidate(DATE)
        dk = next((b for p in result for b in p["books"] if b["book"] == "dk"), None)
        assert dk is not None
        assert dk["selection_id_over"] == "only_over"
        assert dk["selection_id_under"] == "only_under"


# ══════════════════════════════════════════════════════════════════════════════
# Bug 10 — Quotes older than _MAX_PREGAME_QUOTE_AGE_SEC are dropped when fresh
# quotes exist; an ALL-stale date re-includes the freshest stale quotes, tagged
# lines_stale=True (Round 1b graceful-stale fallback — stale slate > empty slate)
# ══════════════════════════════════════════════════════════════════════════════

class TestBug10StaleQuoteDrop:

    def test_stale_quote_dropped(self, lines_dir):
        """Round 1b: an ALL-stale date is NOT emptied — the freshest stale quote
        is re-included via the graceful fallback, tagged lines_stale=True, with
        captured_at preserved untouched (drives the downstream stale pill)."""
        import api._courtvision_odds as _odds

        stale_ts = _ts_utc(30)
        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110, captured_at=stale_ts)],
        )

        result = _odds.consolidate(DATE)
        dk_books = [b for p in result for b in p["books"] if b["book"] == "dk"]
        assert dk_books, (
            "All-stale slate must re-include the stale quote (graceful "
            "fallback), not return an empty slate"
        )
        # captured_at must be preserved untouched so freshest_book_age_min
        # still reports the true ~30 h age downstream.
        assert dk_books[0]["captured_at"] == stale_ts
        # Every prop served by the fallback carries the lines_stale flag.
        assert all(p.get("lines_stale") is True for p in result), (
            "Props served by the stale fallback must be tagged lines_stale=True"
        )

    def test_fresh_quote_kept(self, lines_dir):
        """A book quote with captured_at 1 h ago is kept in consolidate()."""
        import api._courtvision_odds as _odds

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110, captured_at=_ts_utc(1))],
        )

        result = _odds.consolidate(DATE)
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        assert "dk" in all_book_keys, "Fresh quote (1h old) must be kept"

    def test_stale_dropped_fresh_kept_same_prop(self, lines_dir):
        """For the same prop: stale quote from one book is dropped, fresh from
        another is kept — both in the same date's CSV file."""
        import api._courtvision_odds as _odds

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110, captured_at=_ts_utc(30))],
        )
        _write_csv(
            lines_dir / f"{DATE}_fd.csv",
            [_base_row(book="fd", over_price=-112, captured_at=_ts_utc(1))],
        )

        result = _odds.consolidate(DATE)
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        assert "fd" in all_book_keys, "Fresh FD quote (1h) must survive"
        assert "dk" not in all_book_keys, "Stale DK quote (30h) must be dropped"
        # The graceful fallback never fires when a fresh quote survived, so
        # nothing on this slate may carry the lines_stale tag.
        assert not any(p.get("lines_stale") for p in result), (
            "lines_stale must not be set when fresh quotes survived the cap"
        )

    def test_unparseable_captured_at_not_dropped(self, lines_dir):
        """A quote with an unparseable captured_at is kept (safe fallback — do not drop)."""
        import api._courtvision_odds as _odds

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110, captured_at="not-a-timestamp")],
        )

        result = _odds.consolidate(DATE)
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        assert "dk" in all_book_keys, (
            "Quote with unparseable captured_at must NOT be dropped "
            "(safe fallback — only parseable old timestamps are dropped)"
        )

    def test_exactly_at_boundary_kept(self, lines_dir):
        """A quote at exactly 5.9 h old (just under 6 h limit) is kept."""
        import api._courtvision_odds as _odds

        _write_csv(
            lines_dir / f"{DATE}_dk.csv",
            [_base_row(book="dk", over_price=-110, captured_at=_ts_utc(5.9))],
        )

        result = _odds.consolidate(DATE)
        all_book_keys = {b["book"] for p in result for b in p["books"]}
        assert "dk" in all_book_keys, "Quote just under 6h must be kept"
