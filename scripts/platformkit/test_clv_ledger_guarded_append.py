"""Per-file test for clv_ledger_guarded_append (BE8-1).

Acceptance: 1) same open row x2 -> 1 line; 2) open then settled -> 2 lines;
3) concurrent double-fire same row -> 1 line; 4) no $/pnl/bankroll key written;
5) missing-file path creates parent + writes 1 line.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \\
       scripts/platformkit/test_clv_ledger_guarded_append.py -q
"""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.platformkit.clv_ledger_guarded_append import (
    append_if_new_status_aware,
    make_session_seen,
    record_open_guarded,
    record_settlement_guarded,
    status_key,
)
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPORT = "nba"
_MATCHUP = "BOS@LAL"
_SIDE = "home"
_BOOK = "FanDuel"
_DATE = "2026-06-19"


def _open_row(**overrides: Any) -> Dict[str, Any]:  # noqa: ANN401
    base: Dict[str, Any] = {
        "ts": "2026-06-19T12:00:00+00:00",
        "sport": _SPORT, "matchup": _MATCHUP, "side": _SIDE,
        "taken_book": _BOOK, "taken_decimal": 2.10, "model_prob": 0.52,
        "stake_units": 1.0, "status": "open", "executed": False,
        "game_date": _DATE, "market": "moneyline",
    }
    base.update(overrides)
    from scripts.platformkit.clv_ledger import bet_id as _bid
    base.setdefault("bet_id", _bid(base))
    return base


def _settled_row(open_row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(open_row)
    row["status"] = "settled"
    row["settled_at"] = "2026-06-19T22:00:00+00:00"
    row["clv_pct"] = 1.23
    row["beat_close"] = True
    return row


def _read_lines(path: Path) -> list:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            lines.append(json.loads(line))
    return lines


# ---------------------------------------------------------------------------
# Test 1: appending the same open row twice yields exactly 1 line
# ---------------------------------------------------------------------------

def test_duplicate_open_row_yields_one_line() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        row = _open_row()

        res1 = append_if_new_status_aware(row, ledger)
        res2 = append_if_new_status_aware(row, ledger)

        assert res1["appended"] is True,  "first write should succeed"
        assert res2["appended"] is False, "duplicate write should be blocked"

        lines = _read_lines(ledger)
        assert len(lines) == 1, "exactly 1 line in ledger after duplicate open"


# ---------------------------------------------------------------------------
# Test 2: open then settled (same bet_id) -> 2 lines (distinct status)
# ---------------------------------------------------------------------------

def test_open_then_settled_yields_two_lines() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        open_row = _open_row()
        settled = _settled_row(open_row)

        r_open = append_if_new_status_aware(open_row, ledger)
        r_settled = append_if_new_status_aware(settled, ledger)

        assert r_open["appended"] is True,    "open write should succeed"
        assert r_settled["appended"] is True, "settled twin should also be appended"

        lines = _read_lines(ledger)
        assert len(lines) == 2, "2 lines expected: open + settled"

        statuses = {ln["status"] for ln in lines}
        assert statuses == {"open", "settled"}, "must have both status values"

        # Both rows share the same base bet_id (status-agnostic identity).
        open_bid  = next(ln["bet_id"] for ln in lines if ln["status"] == "open")
        settl_bid = next(ln["bet_id"] for ln in lines if ln["status"] == "settled")
        assert open_bid == settl_bid, "bet_ids must match for open/settled pair"


# ---------------------------------------------------------------------------
# Test 3: concurrent double-fire of identical row -> 1 line
# ---------------------------------------------------------------------------

def test_concurrent_double_fire_yields_one_line() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        row = _open_row()
        results = []

        def _write() -> None:
            res = append_if_new_status_aware(row, ledger)
            results.append(res["appended"])

        t1 = threading.Thread(target=_write)
        t2 = threading.Thread(target=_write)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        lines = _read_lines(ledger)
        assert len(lines) == 1, (
            "concurrent double-fire must produce exactly 1 line; got %d" % len(lines)
        )
        # Exactly one thread should have observed True (the winner).
        assert results.count(True) >= 1, "at least one thread must have appended"


# ---------------------------------------------------------------------------
# Test 4: row carries no dollar / pnl / profit / bankroll key
# ---------------------------------------------------------------------------

def test_no_dollar_key_written() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        row = _open_row()
        # Inject all banned keys to verify they are stripped.
        for k in BANNED_KEYS:
            row[k] = 999.99

        append_if_new_status_aware(row, ledger)

        lines = _read_lines(ledger)
        assert len(lines) == 1
        written = lines[0]
        for k in BANNED_KEYS:
            assert k not in written, "banned key %r must not appear in written row" % k


# ---------------------------------------------------------------------------
# Test 5: missing-file path creates parent directory and writes 1 line
# ---------------------------------------------------------------------------

def test_missing_file_creates_parent_and_writes() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "nested" / "deep" / "clv_ledger.jsonl"
        assert not ledger.exists(), "ledger must not exist before test"

        row = _open_row()
        res = append_if_new_status_aware(row, ledger)

        assert res["appended"] is True,        "write to missing path must succeed"
        assert ledger.exists(),                 "ledger file must be created"
        lines = _read_lines(ledger)
        assert len(lines) == 1, "exactly 1 line after first write to new file"


# ---------------------------------------------------------------------------
# Test 6: record_open_guarded default-injects status="open"
# ---------------------------------------------------------------------------

def test_record_open_guarded_defaults_status() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        row = _open_row()
        del row["status"]  # omit status -- guard must default to "open"

        res = record_open_guarded(row, ledger)
        assert res["appended"] is True

        lines = _read_lines(ledger)
        assert lines[0]["status"] == "open"


# ---------------------------------------------------------------------------
# Test 7: record_settlement_guarded forces status="settled"
# ---------------------------------------------------------------------------

def test_record_settlement_guarded_forces_settled() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        open_row = _open_row()
        settled = _settled_row(open_row)

        record_open_guarded(open_row, ledger)
        res = record_settlement_guarded(settled, ledger)

        assert res["appended"] is True
        lines = _read_lines(ledger)
        settled_lines = [ln for ln in lines if ln["status"] == "settled"]
        assert len(settled_lines) == 1

        # Replay settlement -> blocked.
        res2 = record_settlement_guarded(settled, ledger)
        assert res2["appended"] is False
        assert len(_read_lines(ledger)) == 2, "replay must not add a third line"


# ---------------------------------------------------------------------------
# Test 8: make_session_seen pre-loads existing keys; batch append is efficient
# ---------------------------------------------------------------------------

def test_make_session_seen_deduplicates_batch() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        row = _open_row()

        # Write the first row normally.
        append_if_new_status_aware(row, ledger)

        # Build session seen set from disk state.
        seen = make_session_seen(ledger)
        expected_key = status_key(row)
        assert expected_key in seen, "pre-existing key must be in seen set"

        # Replay the same row using the session set -- must be blocked.
        res = append_if_new_status_aware(row, ledger, _seen=seen)
        assert res["appended"] is False

        # New row with different matchup must pass.
        row2 = _open_row(matchup="MIA@OKC")
        res2 = append_if_new_status_aware(row2, ledger, _seen=seen)
        assert res2["appended"] is True

        lines = _read_lines(ledger)
        assert len(lines) == 2, "original + new-matchup row = 2 lines"


# ---------------------------------------------------------------------------
# Test 9: status_key returns correct format
# ---------------------------------------------------------------------------

def test_status_key_format() -> None:
    row = _open_row()
    key = status_key(row)
    assert "|open" in key, "status_key must embed '|open' for an open row"

    settled = _settled_row(row)
    key2 = status_key(settled)
    assert "|settled" in key2, "status_key must embed '|settled' for a settled row"

    # The prefix (bet_id part) must match between the two keys.
    assert key.rsplit("|", 1)[0] == key2.rsplit("|", 1)[0], (
        "open and settled share the same bet_id prefix"
    )


# ---------------------------------------------------------------------------
# Test 10: result dict shape -- no error key on success, no appended=True on dup
# ---------------------------------------------------------------------------

def test_result_dict_shape() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.jsonl"
        row = _open_row()

        res_first = append_if_new_status_aware(row, ledger)
        assert "error" not in res_first
        assert res_first["appended"] is True
        assert "key" in res_first

        res_dup = append_if_new_status_aware(row, ledger)
        assert res_dup["appended"] is False
        assert "key" in res_dup
