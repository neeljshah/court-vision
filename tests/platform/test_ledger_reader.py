"""test_ledger_reader.py — Acceptance tests for ledger_reader.py (N-CLV-007).

All disk I/O uses pytest's ``tmp_path`` fixture.  The real
``data/lines/forward/`` directory is NEVER touched.

Python 3.9 compatible.  No network.  No torch.  No pandas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import pytest

# ---------------------------------------------------------------------------
# Path wiring
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "platformkit" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))

import ledger_writer as writer  # noqa: E402
import ledger_reader as reader  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    sport: str = "nba",
    event_id: str = "0042500404",
    market: str = "player_points",
    book: str = "draftkings",
    price: float = -115.0,
    side: str = "over:Brunson:25.5",
    kind: str = "open",
    ts_utc_observed: str = "2026-06-11T18:00:00Z",
    source: str = "test",
    **extra,
) -> dict:
    rec = {
        "sport": sport,
        "event_id": event_id,
        "market": market,
        "book": book,
        "price": price,
        "side": side,
        "kind": kind,
        "ts_utc_observed": ts_utc_observed,
        "source": source,
    }
    rec.update(extra)
    return rec


def _write_records(records: List[dict], tmp_path: Path) -> None:
    """Write all records via the official writer."""
    for rec in records:
        writer.append(rec, root=tmp_path)


# ---------------------------------------------------------------------------
# 1. iter_rows — round-trips through writer
# ---------------------------------------------------------------------------

def test_iter_rows_round_trips_writer(tmp_path: Path) -> None:
    """Rows written by ledger_writer are readable by iter_rows in order."""
    recs = [
        _make_record(price=-115.0, kind="open"),
        _make_record(price=-112.0, kind="move"),
        _make_record(price=-110.0, kind="close"),
    ]
    _write_records(recs, tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))

    assert len(rows) == 3
    assert [r["kind"] for r in rows] == ["open", "move", "close"]
    assert [r["price"] for r in rows] == [-115.0, -112.0, -110.0]


# ---------------------------------------------------------------------------
# 2. iter_rows — forward_only excludes reconstructed by default
# ---------------------------------------------------------------------------

def test_iter_rows_excludes_reconstructed_by_default(tmp_path: Path) -> None:
    """forward_only=True (default) must drop ts_quality='reconstructed' rows."""
    live_rec = _make_record(kind="open", price=-115.0)
    archive_rec = _make_record(
        kind="close", price=-110.0,
        ts_quality="reconstructed",
    )
    _write_records([live_rec, archive_rec], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))

    assert len(rows) == 1, "reconstructed row must be excluded"
    assert rows[0]["price"] == -115.0


def test_iter_rows_includes_reconstructed_when_forward_only_false(tmp_path: Path) -> None:
    """forward_only=False must include all rows regardless of ts_quality."""
    live_rec = _make_record(kind="open", price=-115.0)
    archive_rec = _make_record(
        kind="close", price=-110.0,
        ts_quality="reconstructed",
    )
    _write_records([live_rec, archive_rec], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path, forward_only=False))

    assert len(rows) == 2


# ---------------------------------------------------------------------------
# 3. iter_rows — sport filter
# ---------------------------------------------------------------------------

def test_iter_rows_sport_filter(tmp_path: Path) -> None:
    """Sport filter returns only the requested sport."""
    nba = _make_record(sport="nba", event_id="nba_ev1")
    nfl = _make_record(
        sport="nfl", event_id="nfl_ev1",
        ts_utc_observed="2026-09-07T18:00:00Z",
    )
    _write_records([nba, nfl], tmp_path)

    nba_rows = list(reader.iter_rows(root=tmp_path, sport="nba"))
    nfl_rows = list(reader.iter_rows(root=tmp_path, sport="nfl"))

    assert len(nba_rows) == 1 and nba_rows[0]["event_id"] == "nba_ev1"
    assert len(nfl_rows) == 1 and nfl_rows[0]["event_id"] == "nfl_ev1"


# ---------------------------------------------------------------------------
# 4. iter_rows — market filter
# ---------------------------------------------------------------------------

def test_iter_rows_market_filter(tmp_path: Path) -> None:
    """Market filter returns only the matching market."""
    pts = _make_record(market="player_points", side="over:Brunson:25.5")
    ast = _make_record(market="player_assists", side="over:Brunson:6.5")
    _write_records([pts, ast], tmp_path)

    pts_rows = list(reader.iter_rows(root=tmp_path, market="player_points"))

    assert len(pts_rows) == 1
    assert pts_rows[0]["market"] == "player_points"


# ---------------------------------------------------------------------------
# 5. iter_rows — kind filter
# ---------------------------------------------------------------------------

def test_iter_rows_kind_filter(tmp_path: Path) -> None:
    """Kind filter returns only rows with the specified kind."""
    recs = [
        _make_record(kind="open", price=-115.0),
        _make_record(kind="move", price=-113.0),
        _make_record(kind="close", price=-110.0),
    ]
    _write_records(recs, tmp_path)

    close_rows = list(reader.iter_rows(root=tmp_path, kind="close"))

    assert len(close_rows) == 1
    assert close_rows[0]["kind"] == "close"
    assert close_rows[0]["price"] == -110.0


# ---------------------------------------------------------------------------
# 6. iter_rows — multi-sport, multi-day, combined filters
# ---------------------------------------------------------------------------

def test_iter_rows_combined_filters(tmp_path: Path) -> None:
    """Sport + kind combined filters work together."""
    recs = [
        _make_record(sport="nba", kind="open", event_id="nba_ev"),
        _make_record(sport="nba", kind="close", event_id="nba_ev"),
        _make_record(
            sport="nfl", kind="open", event_id="nfl_ev",
            ts_utc_observed="2026-09-07T18:00:00Z",
        ),
    ]
    _write_records(recs, tmp_path)

    rows = list(reader.iter_rows(root=tmp_path, sport="nba", kind="close"))

    assert len(rows) == 1
    assert rows[0]["sport"] == "nba"
    assert rows[0]["kind"] == "close"


# ---------------------------------------------------------------------------
# 7. iter_rows — empty root returns nothing gracefully
# ---------------------------------------------------------------------------

def test_iter_rows_empty_root(tmp_path: Path) -> None:
    """iter_rows on a directory with no ledger files yields nothing."""
    rows = list(reader.iter_rows(root=tmp_path))
    assert rows == []


def test_iter_rows_nonexistent_root(tmp_path: Path) -> None:
    """iter_rows on a non-existent root yields nothing (no crash)."""
    missing = tmp_path / "does_not_exist"
    rows = list(reader.iter_rows(root=missing))
    assert rows == []


# ---------------------------------------------------------------------------
# 8. pair_open_close — correct matching
# ---------------------------------------------------------------------------

def test_pair_open_close_matches_pair(tmp_path: Path) -> None:
    """pair_open_close returns a matched (open, close) pair."""
    open_rec = _make_record(kind="open", price=-115.0)
    close_rec = _make_record(kind="close", price=-110.0)
    _write_records([open_rec, close_rec], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))
    pairs = reader.pair_open_close(rows)

    assert len(pairs) == 1
    op, cl = pairs[0]
    assert op["kind"] == "open"
    assert cl["kind"] == "close"
    assert op["price"] == -115.0
    assert cl["price"] == -110.0


def test_pair_open_close_leaves_unmatched_out(tmp_path: Path) -> None:
    """An opener with no matching close is NOT included in the result."""
    open_rec = _make_record(kind="open", side="over:Brunson:25.5")
    # Different side → different key, no matching open.
    close_other = _make_record(kind="close", side="under:Brunson:25.5")
    _write_records([open_rec, close_other], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))
    pairs = reader.pair_open_close(rows)

    assert pairs == [], "unmatched open/close must not appear in pairs"


def test_pair_open_close_ignores_move_rows(tmp_path: Path) -> None:
    """Move rows are excluded from pairing logic."""
    recs = [
        _make_record(kind="open", price=-115.0),
        _make_record(kind="move", price=-113.0),
        _make_record(kind="close", price=-110.0),
    ]
    _write_records(recs, tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))
    pairs = reader.pair_open_close(rows)

    assert len(pairs) == 1
    op, cl = pairs[0]
    assert op["kind"] == "open" and cl["kind"] == "close"


def test_pair_open_close_multiple_markets(tmp_path: Path) -> None:
    """Each (sport, event_id, market, book, side) key is paired independently."""
    recs = [
        _make_record(market="player_points", side="over:A:25.5", kind="open", price=-115.0),
        _make_record(market="player_assists", side="over:A:6.5",  kind="open", price=-120.0),
        _make_record(market="player_points", side="over:A:25.5", kind="close", price=-108.0),
        _make_record(market="player_assists", side="over:A:6.5",  kind="close", price=-105.0),
    ]
    _write_records(recs, tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))
    pairs = reader.pair_open_close(rows)

    assert len(pairs) == 2
    markets_in_pairs = {op["market"] for op, _ in pairs}
    assert markets_in_pairs == {"player_points", "player_assists"}


def test_pair_open_close_close_without_open_excluded(tmp_path: Path) -> None:
    """A close with no matching open does not appear in pairs."""
    close_rec = _make_record(kind="close", price=-110.0)
    _write_records([close_rec], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path))
    pairs = reader.pair_open_close(rows)

    assert pairs == []


# ---------------------------------------------------------------------------
# 9. find_duplicate_keys — dedup/integrity helper
# ---------------------------------------------------------------------------

def test_find_duplicate_keys_clean_ledger_returns_empty(tmp_path: Path) -> None:
    """A ledger with unique record_keys returns an empty dict."""
    recs = [
        _make_record(kind="open"),
        _make_record(kind="close"),
    ]
    _write_records(recs, tmp_path)

    rows = list(reader.iter_rows(root=tmp_path, forward_only=False))
    dupes = reader.find_duplicate_keys(rows)

    assert dupes == {}


def test_find_duplicate_keys_flags_planted_duplicate(tmp_path: Path) -> None:
    """Manually planting a duplicate record_key is detected."""
    rec = _make_record(kind="open", price=-115.0)
    # Write the same logical record twice (writer does not dedupe).
    _write_records([rec, rec], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path, forward_only=False))
    dupes = reader.find_duplicate_keys(rows)

    assert len(dupes) == 1, "exactly one key should be flagged"
    # The duplicated key must point to both copies.
    flagged_rows = next(iter(dupes.values()))
    assert len(flagged_rows) == 2


def test_find_duplicate_keys_reports_all_copies(tmp_path: Path) -> None:
    """Three copies of the same record_key are all reported."""
    rec = _make_record(kind="move", price=-113.0)
    _write_records([rec, rec, rec], tmp_path)

    rows = list(reader.iter_rows(root=tmp_path, forward_only=False))
    dupes = reader.find_duplicate_keys(rows)

    assert len(dupes) == 1
    flagged_rows = next(iter(dupes.values()))
    assert len(flagged_rows) == 3


def test_find_duplicate_keys_distinct_records_not_flagged(tmp_path: Path) -> None:
    """Different record_keys are not flagged even when market/book overlap."""
    recs = [
        _make_record(kind="open",  market="player_points"),
        _make_record(kind="close", market="player_points"),
        _make_record(kind="open",  market="player_assists"),
    ]
    _write_records(recs, tmp_path)

    rows = list(reader.iter_rows(root=tmp_path, forward_only=False))
    dupes = reader.find_duplicate_keys(rows)

    assert dupes == {}


# ---------------------------------------------------------------------------
# 10. forward_only interplay with pair_open_close
# ---------------------------------------------------------------------------

def test_pair_open_close_respects_forward_only_filter(tmp_path: Path) -> None:
    """A reconstructed close is excluded before pairing when forward_only=True."""
    open_rec = _make_record(kind="open", price=-115.0)
    close_rec = _make_record(
        kind="close", price=-110.0,
        ts_quality="reconstructed",
    )
    _write_records([open_rec, close_rec], tmp_path)

    # Default forward_only=True → close is stripped before pairing.
    forward_rows = list(reader.iter_rows(root=tmp_path, forward_only=True))
    pairs = reader.pair_open_close(forward_rows)

    assert pairs == [], "reconstructed close must not pair with a forward open"


def test_pair_open_close_with_forward_only_false_can_pair(tmp_path: Path) -> None:
    """With forward_only=False, a reconstructed close CAN pair with its open."""
    open_rec = _make_record(kind="open", price=-115.0)
    close_rec = _make_record(
        kind="close", price=-110.0,
        ts_quality="reconstructed",
    )
    _write_records([open_rec, close_rec], tmp_path)

    all_rows = list(reader.iter_rows(root=tmp_path, forward_only=False))
    pairs = reader.pair_open_close(all_rows)

    assert len(pairs) == 1
