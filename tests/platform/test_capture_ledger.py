"""test_capture_ledger.py — Acceptance tests for the forward-capture ledger schema + writer.

All disk writes go to pytest's ``tmp_path`` fixture — the real
``data/lines/forward/`` directory is NEVER touched.

Python 3.9 compatible. No network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path wiring — import from scripts/platformkit/capture without installing.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "platformkit" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))

import ledger_schema as schema  # noqa: E402
import ledger_writer as writer  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(
    sport: str = "nba",
    event_id: str = "0042500404",
    market: str = "player_pts",
    book: str = "draftkings",
    price: float = -115.0,
    side: str = "over",
    kind: str = "open",
    ts_utc_observed: str = "2026-06-11T18:00:00Z",
    source: str = "test",
) -> dict:
    return {
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


# ---------------------------------------------------------------------------
# 1. Append two rows then read_all returns both in order (append-only proven).
# ---------------------------------------------------------------------------

def test_append_and_read_all_preserves_order(tmp_path: Path) -> None:
    rec1 = _make_record(price=-115.0, kind="open")
    rec2 = _make_record(price=-110.0, kind="move")

    writer.append(rec1, root=tmp_path)
    writer.append(rec2, root=tmp_path)

    records = writer.read_all("nba", "2026-06-11", root=tmp_path)

    assert len(records) == 2, f"Expected 2 records, got {len(records)}"
    assert records[0]["price"] == -115.0
    assert records[1]["price"] == -110.0
    assert records[0]["kind"] == "open"
    assert records[1]["kind"] == "move"


# ---------------------------------------------------------------------------
# 2. Truncating / overwrite attempt raises RuntimeError.
# ---------------------------------------------------------------------------

def test_truncating_mode_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="append-only"):
        writer._safe_open_mode("w")


def test_exclusive_create_mode_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="append-only"):
        writer._safe_open_mode("x")


def test_append_mode_does_not_raise() -> None:
    # 'a' is the only permitted write mode — must not raise.
    writer._safe_open_mode("a")


def test_read_mode_does_not_raise() -> None:
    writer._safe_open_mode("r")


# ---------------------------------------------------------------------------
# 3. Daily rotation: two rows with different dates land in different files.
# ---------------------------------------------------------------------------

def test_daily_rotation_separate_files(tmp_path: Path) -> None:
    rec_day1 = _make_record(ts_utc_observed="2026-06-11T12:00:00Z", kind="open")
    rec_day2 = _make_record(ts_utc_observed="2026-06-12T12:00:00Z", kind="close")

    path1 = writer.append(rec_day1, root=tmp_path)
    path2 = writer.append(rec_day2, root=tmp_path)

    assert path1 != path2, "Different dates must land in different files"
    assert "2026-06-11" in path1.name
    assert "2026-06-12" in path2.name

    records_day1 = writer.read_all("nba", "2026-06-11", root=tmp_path)
    records_day2 = writer.read_all("nba", "2026-06-12", root=tmp_path)

    assert len(records_day1) == 1
    assert len(records_day2) == 1
    assert records_day1[0]["kind"] == "open"
    assert records_day2[0]["kind"] == "close"


# ---------------------------------------------------------------------------
# 4a. Schema validation: missing field raises ValueError.
# ---------------------------------------------------------------------------

def test_validate_missing_field_raises() -> None:
    rec = _make_record()
    del rec["market"]
    with pytest.raises(ValueError, match="market"):
        schema.validate(rec)


def test_validate_missing_sport_raises() -> None:
    rec = _make_record()
    del rec["sport"]
    with pytest.raises(ValueError, match="sport"):
        schema.validate(rec)


def test_validate_missing_price_raises() -> None:
    rec = _make_record()
    del rec["price"]
    with pytest.raises(ValueError, match="price"):
        schema.validate(rec)


# ---------------------------------------------------------------------------
# 4b. Schema validation: bad 'kind' raises ValueError.
# ---------------------------------------------------------------------------

def test_validate_bad_kind_raises() -> None:
    rec = _make_record(kind="live")
    with pytest.raises(ValueError, match="kind"):
        schema.validate(rec)


def test_validate_empty_kind_raises() -> None:
    rec = _make_record(kind="")
    with pytest.raises(ValueError, match="kind"):
        schema.validate(rec)


def test_validate_valid_kinds_pass() -> None:
    for kind in ("open", "move", "close"):
        rec = _make_record(kind=kind)
        result = schema.validate(rec)
        assert result is rec, "validate() must return the same dict on success"


# ---------------------------------------------------------------------------
# 5. Target path shape: .../data/lines/forward/<sport>/<date>.jsonl
# ---------------------------------------------------------------------------

def test_target_path_shape(tmp_path: Path) -> None:
    rec = _make_record(sport="nba", ts_utc_observed="2026-06-11T20:00:00Z")
    path = writer.append(rec, root=tmp_path)

    # Must be under tmp_path (not the real data dir).
    assert str(path).startswith(str(tmp_path))

    # Must match .../nba/2026-06-11.jsonl
    assert path.parent.name == "nba"
    assert path.name == "2026-06-11.jsonl"


def test_target_path_shape_different_sport(tmp_path: Path) -> None:
    rec = _make_record(sport="nfl", event_id="nfl_wk1_kc_buf", ts_utc_observed="2026-09-07T18:00:00Z")
    path = writer.append(rec, root=tmp_path)

    assert path.parent.name == "nfl"
    assert path.name == "2026-09-07.jsonl"


# ---------------------------------------------------------------------------
# 6. record_key returns the expected 6-tuple.
# ---------------------------------------------------------------------------

def test_record_key_shape() -> None:
    rec = _make_record()
    key = schema.record_key(rec)
    assert isinstance(key, tuple)
    assert len(key) == 6
    assert key == ("nba", "0042500404", "player_pts", "draftkings", "over", "open")


# ---------------------------------------------------------------------------
# 7. price field accepts both float and str (raw observed price, no normalisation).
# ---------------------------------------------------------------------------

def test_price_can_be_string(tmp_path: Path) -> None:
    rec = _make_record(price="-115")  # type: ignore[arg-type]
    path = writer.append(rec, root=tmp_path)
    records = writer.read_all("nba", "2026-06-11", root=tmp_path)
    assert records[0]["price"] == "-115"


def test_price_can_be_float(tmp_path: Path) -> None:
    rec = _make_record(price=1.95)
    writer.append(rec, root=tmp_path)
    records = writer.read_all("nba", "2026-06-11", root=tmp_path)
    assert records[0]["price"] == 1.95
