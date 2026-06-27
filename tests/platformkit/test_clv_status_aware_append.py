"""tests.platformkit.test_clv_status_aware_append -- acceptance tests.

WORKSTREAM: BE-H-clv-status-rowkey-writer

Acceptance criteria (from the workstream spec):
  (A) Appending an open row then a settled row for the same bet_id yields two
      DISTINCT status-aware keys (no dup-trip).
  (B) Appending the same open row twice IS caught as a dup (second append
      returns {"appended": False}).
  (C) Key format is bet_id + "|" + status.
  (D) No ledger-file mutation performed by the test (uses a temp ledger).
  (E) No $/pnl/roi/profit key in any row or result dict (honesty guard).
  (F) status_aware_key never raises on None/missing status (falls back to "open").
  (G) settle_append and open_append both return the correct key format on success.
  (H) make_session_seen builds a _seen set that prevents redundant disk scans.

Per-file run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      tests/platformkit/test_clv_status_aware_append.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Set

import pytest

from scripts.platformkit.clv_status_aware_append import (
    make_session_seen,
    open_append,
    settle_append,
    status_aware_key,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_BID = "nba|BOS@NYK|moneyline|home|DraftKings|2026-06-20"

_BANNED_KEYS: frozenset = frozenset({
    "roi", "pnl", "profit", "loss", "bankroll", "dollar",
    "$", "usd", "net_profit", "return",
})


def _make_open(bet_id: str = _BID) -> Dict[str, Any]:
    return {
        "bet_id": bet_id,
        "sport": "nba",
        "matchup": "BOS@NYK",
        "side": "home",
        "taken_book": "DraftKings",
        "taken_decimal": 2.10,
        "model_prob": 0.52,
        "stake_units": 1.0,
        "status": "open",
        "game_date": "2026-06-20",
    }


def _make_settled(bet_id: str = _BID) -> Dict[str, Any]:
    return {
        "bet_id": bet_id,
        "status": "settled",
        "outcome": "win",
        "close_decimal": 2.05,
        "clv_pct": 2.44,
        "stake_units": 1.0,
        "game_date": "2026-06-20",
    }


def _assert_no_banned(obj: Any, label: str = "") -> None:
    """Recursively assert no banned dollar/pnl key appears in obj."""
    if isinstance(obj, dict):
        for k in obj:
            assert k.lower() not in _BANNED_KEYS, (
                "Banned key %r in %s" % (k, label or "result")
            )
            _assert_no_banned(obj[k], label + "." + k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_banned(v, label + "[%d]" % i)


def _read_ledger(path: Path):
    """Read all JSONL rows from a temp ledger file."""
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# CRITERION C: key format is bet_id + "|" + status
# ---------------------------------------------------------------------------

def test_key_format_open():
    """(C) status_aware_key returns bet_id+'|open' for an open row."""
    row = _make_open()
    key = status_aware_key(row)
    assert key == _BID + "|open", "Expected %r|open; got %r" % (_BID, key)


def test_key_format_settled():
    """(C) status_aware_key returns bet_id+'|settled' for a settled row."""
    row = _make_settled()
    key = status_aware_key(row)
    assert key == _BID + "|settled", "Expected %r|settled; got %r" % (_BID, key)


# ---------------------------------------------------------------------------
# CRITERION F: key never raises on None/missing status
# ---------------------------------------------------------------------------

def test_key_no_raise_on_missing_status():
    """(F) status_aware_key never raises on None/missing status (falls back to "open").

    Contract (from clv_ledger_status_dedup.status_key):
      - None and empty-string ("") status -> fall back to |open
      - Whitespace-only status ("   ") is truthy -> strips to "" -> appended as "|"
        (edge case; callers should always set "open" or "settled" explicitly)
      - Function never raises regardless of input.
    """
    # These all fall back to |open (falsy status)
    fallback_cases = [
        {"bet_id": "x|y|z"},
        {"bet_id": "x|y|z", "status": None},
        {"bet_id": "x|y|z", "status": ""},
    ]
    for row in fallback_cases:
        key = status_aware_key(row)
        assert isinstance(key, str) and "|" in key, (
            "Expected non-empty key with | for row=%r; got %r" % (row, key)
        )
        assert key.endswith("|open"), (
            "None/empty status must fall back to |open; got %r for row=%r"
            % (key, row)
        )

    # Whitespace-only: truthy str, strips to ""; function must not raise
    ws_row = {"bet_id": "x|y|z", "status": "   "}
    try:
        ws_key = status_aware_key(ws_row)
    except Exception as exc:
        pytest.fail(
            "status_aware_key raised on whitespace-only status: %s" % exc
        )
    assert isinstance(ws_key, str), (
        "status_aware_key must return str for whitespace status; got %r" % ws_key
    )
    # After strip, status is ""; key ends with "|" (not |open -- that's the
    # actual contract of the underlying primitive for this edge case).
    assert ws_key.startswith("x|y|z|"), (
        "key must start with bet_id| for whitespace-only status; got %r" % ws_key
    )


# ---------------------------------------------------------------------------
# CRITERION A: open then settled -> two distinct keys (no dup-trip)
# ---------------------------------------------------------------------------

def test_open_then_settled_distinct_keys_no_dup_trip(tmp_path):
    """(A)(D) Appending open then settled for same bet_id -> 2 rows, no dup trip."""
    ledger = tmp_path / "test_ledger.jsonl"

    res_open = open_append(_make_open(), path=ledger)
    res_settled = settle_append(_make_settled(), path=ledger)

    # Both must have been appended
    assert res_open.get("appended") is True, (
        "Open row must be appended; got %r" % res_open
    )
    assert res_settled.get("appended") is True, (
        "Settled row must be appended; got %r" % res_settled
    )

    # Keys must be distinct
    key_open = res_open.get("key", "")
    key_settled = res_settled.get("key", "")
    assert key_open != key_settled, (
        "Open and settled keys must differ; both got %r" % key_open
    )

    # Key format check
    assert key_open.endswith("|open"), (
        "Open key must end with |open; got %r" % key_open
    )
    assert key_settled.endswith("|settled"), (
        "Settled key must end with |settled; got %r" % key_settled
    )

    # Ledger must have exactly 2 rows
    rows = _read_ledger(ledger)
    assert len(rows) == 2, (
        "Ledger must have 2 rows (open + settled); got %d" % len(rows)
    )

    # Honesty guard
    _assert_no_banned(res_open, "res_open")
    _assert_no_banned(res_settled, "res_settled")


# ---------------------------------------------------------------------------
# CRITERION B: same open row twice IS caught as a dup
# ---------------------------------------------------------------------------

def test_duplicate_open_row_is_caught(tmp_path):
    """(B)(D) Appending the same open row twice -> second append is blocked."""
    ledger = tmp_path / "test_ledger.jsonl"

    res_first = open_append(_make_open(), path=ledger)
    res_second = open_append(_make_open(), path=ledger)

    assert res_first.get("appended") is True, (
        "First open row must be appended; got %r" % res_first
    )
    assert res_second.get("appended") is False, (
        "Second identical open row must be blocked (dup); got %r" % res_second
    )

    # Ledger must have exactly 1 row (no dup written)
    rows = _read_ledger(ledger)
    assert len(rows) == 1, (
        "Ledger must have exactly 1 row after dup-blocked second write; got %d" % len(rows)
    )

    # Honesty guard
    _assert_no_banned(res_first, "res_first")
    _assert_no_banned(res_second, "res_second")


# ---------------------------------------------------------------------------
# CRITERION D: no mutation of real ledger (temp only in all tests)
# Verified by design: all test functions above use tmp_path fixtures.
# Additional explicit test confirming DEFAULT_LEDGER is never touched.
# ---------------------------------------------------------------------------

def test_no_real_ledger_mutation(tmp_path):
    """(D) Tests use a temp ledger; the real DEFAULT_LEDGER is not touched."""
    from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
    real = Path(DEFAULT_LEDGER)
    mtime_before = real.stat().st_mtime if real.exists() else None

    ledger = tmp_path / "isolated.jsonl"
    open_append(_make_open(), path=ledger)
    settle_append(_make_settled(), path=ledger)

    if mtime_before is not None:
        mtime_after = real.stat().st_mtime if real.exists() else None
        assert mtime_after == mtime_before, (
            "Real ledger mtime changed -- test must never write to DEFAULT_LEDGER"
        )
    # If ledger didn't exist before, ensure it still doesn't after the test
    if mtime_before is None:
        assert not real.exists(), (
            "Real ledger was created by test -- must use tmp_path only"
        )


# ---------------------------------------------------------------------------
# CRITERION E: no $/pnl/roi key in row or results (honesty)
# ---------------------------------------------------------------------------

def test_no_banned_keys_in_rows_and_results(tmp_path):
    """(E) No banned dollar/pnl/roi key in any row, result, or ledger line."""
    ledger = tmp_path / "test_honesty.jsonl"

    open_row = _make_open()
    settled_row = _make_settled()

    # Rows themselves must not carry banned keys
    _assert_no_banned(open_row, "open_row_input")
    _assert_no_banned(settled_row, "settled_row_input")

    res_open = open_append(open_row, path=ledger)
    res_settled = settle_append(settled_row, path=ledger)

    _assert_no_banned(res_open, "res_open")
    _assert_no_banned(res_settled, "res_settled")

    # Written rows on disk must not carry banned keys either
    for written_row in _read_ledger(ledger):
        _assert_no_banned(written_row, "written_row")


# ---------------------------------------------------------------------------
# CRITERION G: settle_append and open_append return correct key format
# ---------------------------------------------------------------------------

def test_return_key_format_matches_status_aware_key(tmp_path):
    """(G) Returned key in result matches status_aware_key(row) formula."""
    ledger = tmp_path / "test_key_format.jsonl"

    open_row = _make_open()
    settled_row = _make_settled()

    # Pre-compute expected keys
    expected_open_key = status_aware_key(open_row)
    expected_settled_key = status_aware_key(settled_row)

    res_open = open_append(open_row, path=ledger)
    res_settled = settle_append(settled_row, path=ledger)

    assert res_open.get("key") == expected_open_key, (
        "open_append key mismatch: expected %r; got %r"
        % (expected_open_key, res_open.get("key"))
    )
    assert res_settled.get("key") == expected_settled_key, (
        "settle_append key mismatch: expected %r; got %r"
        % (expected_settled_key, res_settled.get("key"))
    )


# ---------------------------------------------------------------------------
# CRITERION H: make_session_seen builds correct initial seen-set
# ---------------------------------------------------------------------------

def test_make_session_seen_batch_efficiency(tmp_path):
    """(H) make_session_seen returns set of existing status_keys; enables batch use."""
    ledger = tmp_path / "batch_test.jsonl"

    # Prime the ledger with one open row
    open_append(_make_open(), path=ledger)

    seen: Set[str] = make_session_seen(path=ledger)
    assert isinstance(seen, set), "make_session_seen must return a set"

    open_key = status_aware_key(_make_open())
    assert open_key in seen, (
        "seen set must contain the already-written open key; "
        "open_key=%r seen=%r" % (open_key, seen)
    )

    settled_key = status_aware_key(_make_settled())
    assert settled_key not in seen, (
        "seen set must NOT contain settled key before it is written; "
        "settled_key=%r seen=%r" % (settled_key, seen)
    )

    # Now append the settled row passing the seen set -- it must succeed
    res = settle_append(_make_settled(), path=ledger, _seen=seen)
    assert res.get("appended") is True, (
        "settle_append with _seen must append settled row; got %r" % res
    )

    # seen set must have been updated in-place
    assert settled_key in seen, (
        "seen set must be updated in-place after settle_append; "
        "settled_key=%r seen=%r" % (settled_key, seen)
    )

    # A second open_append with the same seen set must be blocked
    res2 = open_append(_make_open(), path=ledger, _seen=seen)
    assert res2.get("appended") is False, (
        "Duplicate open via seen-set must be blocked; got %r" % res2
    )

    # Ledger must have exactly 2 rows total
    rows = _read_ledger(ledger)
    assert len(rows) == 2, (
        "Ledger must have 2 rows (open + settled) after batch session; got %d" % len(rows)
    )
