"""test_clv_ledger_dedup.py -- per-file tests for clv_ledger_dedup.

Acceptance criteria (be-clv-dedup-validator):
  1. open + settled twin (same bet_id, different status) -> BOTH kept (distinct keys).
  2. byte-identical replay (same bet_id AND same status) -> second dropped (1 dup).
  3. Running dedup_ledger twice on a clean ledger -> no_change on second run (idempotent).
  4. dedup_ledger dry_run=True -> file unchanged, status="dry_run".
  5. dedup_ledger on missing file -> status="no_file".
  6. _row_key: open vs settled -> distinct strings.
  7. No $ / pnl / roi / dollar field in any output row.
  8. append_if_new: status-key semantics (open not blocked by settled of same bet).
  9. append_if_new: exact replay (same bet_id + same status) -> blocked (False).
  10. Dollar keys stripped from rows during dedup rewrite.

Run with:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_dedup.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Hermetic import: ensure repo root on sys.path
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
from scripts.platformkit.clv_ledger_dedup import (
    _first_occurrence_rows,
    _row_key,
    _strip_dollar_keys,
    append_if_new,
    dedup_ledger,
    sanitize_rows,
)
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_BET_ID = "nba|NYK@SAS|moneyline|home|dk|2026-06-20"


def _open_row(bid: str = _BET_ID) -> dict:
    return {
        "bet_id": bid,
        "status": "open",
        "sport": "nba",
        "matchup": "NYK@SAS",
        "side": "home",
        "taken_book": "dk",
        "taken_decimal": 1.91,
        "stake_units": 1.0,
        "executed": False,
    }


def _settled_row(bid: str = _BET_ID) -> dict:
    row = dict(_open_row(bid))
    row["status"] = "settled"
    row["clv_pct"] = 1.23
    row["beat_close"] = True
    return row


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _read_jsonl(path: Path) -> list:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


# ---------------------------------------------------------------------------
# Test 1: open + settled twin -> BOTH kept
# ---------------------------------------------------------------------------
def test_open_and_settled_twin_both_kept(tmp_path):
    """open row + settled row with same bet_id must NOT be collapsed."""
    ledger = tmp_path / "led.jsonl"
    _write_jsonl(ledger, [_open_row(), _settled_row()])

    result = dedup_ledger(ledger, dry_run=False)

    assert result["status"] in ("no_change", "ok"), result
    rows_out = _read_jsonl(ledger)
    statuses = {r["status"] for r in rows_out}
    assert "open" in statuses, "open row must be kept"
    assert "settled" in statuses, "settled row must be kept"
    assert result["dups_removed"] == 0
    assert result["rows_out"] == 2


# ---------------------------------------------------------------------------
# Test 2: byte-identical replay -> dropped (exactly 1 dup)
# ---------------------------------------------------------------------------
def test_byte_identical_replay_dropped(tmp_path):
    """Two identical open rows (same bet_id AND same status) -> second is a dup."""
    ledger = tmp_path / "led.jsonl"
    _write_jsonl(ledger, [_open_row(), _open_row()])  # exact copy twice

    result = dedup_ledger(ledger, dry_run=False)

    assert result["status"] == "ok", result
    assert result["dups_removed"] == 1
    assert result["rows_out"] == 1
    rows_out = _read_jsonl(ledger)
    assert len(rows_out) == 1


# ---------------------------------------------------------------------------
# Test 3: idempotent -- two runs on a clean ledger
# ---------------------------------------------------------------------------
def test_dedup_idempotent(tmp_path):
    """Running dedup_ledger twice on a clean ledger is a no-op on the second run."""
    # First run: has a replay dup
    ledger = tmp_path / "led.jsonl"
    _write_jsonl(ledger, [_open_row(), _open_row()])

    r1 = dedup_ledger(ledger, dry_run=False)
    assert r1["status"] == "ok"
    assert r1["dups_removed"] == 1

    # Second run: ledger is already clean
    r2 = dedup_ledger(ledger, dry_run=False)
    assert r2["status"] == "no_change"
    assert r2["dups_removed"] == 0


# ---------------------------------------------------------------------------
# Test 4: dry_run=True leaves the file unchanged
# ---------------------------------------------------------------------------
def test_dry_run_leaves_file_unchanged(tmp_path):
    """dry_run=True must not touch the file even when dups exist."""
    ledger = tmp_path / "led.jsonl"
    original_content = json.dumps(_open_row()) + "\n" + json.dumps(_open_row()) + "\n"
    ledger.write_text(original_content, encoding="utf-8")

    result = dedup_ledger(ledger, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["dups_removed"] == 1
    # File must be byte-identical to before
    assert ledger.read_text(encoding="utf-8") == original_content
    # No .bak created during dry_run
    assert not ledger.with_suffix(".jsonl.bak").exists()


# ---------------------------------------------------------------------------
# Test 5: missing file -> no_file
# ---------------------------------------------------------------------------
def test_missing_file_returns_no_file(tmp_path):
    """Ledger that does not exist -> status=no_file, no crash."""
    ledger = tmp_path / "nonexistent.jsonl"
    result = dedup_ledger(ledger, dry_run=False)
    assert result["status"] == "no_file"
    assert result["dups_removed"] == 0


# ---------------------------------------------------------------------------
# Test 6: _row_key -- open vs settled produce distinct strings
# ---------------------------------------------------------------------------
def test_row_key_open_vs_settled_distinct():
    """_row_key must return different strings for open vs settled of same bet."""
    open_k = _row_key(_open_row())
    settled_k = _row_key(_settled_row())
    assert open_k != settled_k
    assert open_k.endswith("|open")
    assert settled_k.endswith("|settled")


# ---------------------------------------------------------------------------
# Test 7: no dollar / pnl / roi key in any output row
# ---------------------------------------------------------------------------
def test_no_dollar_keys_in_output(tmp_path):
    """dedup_ledger must strip banned dollar/pnl/roi keys from every row."""
    dirty_row = dict(_open_row())
    dirty_row["pnl"] = 99.99      # banned
    dirty_row["roi"] = 0.12       # banned
    dirty_row["bankroll"] = 1000  # banned

    ledger = tmp_path / "led.jsonl"
    _write_jsonl(ledger, [dirty_row])

    # Even no-dup ledger gets dollar keys stripped on rewrite attempt.
    # Add a dup so the rewrite is triggered.
    _write_jsonl(ledger, [dirty_row, dirty_row])
    result = dedup_ledger(ledger, dry_run=False)
    assert result["status"] == "ok"

    rows_out = _read_jsonl(ledger)
    for r in rows_out:
        for banned in BANNED_KEYS:
            assert banned not in r, "Banned key %r found in output row" % banned


# ---------------------------------------------------------------------------
# Test 8: append_if_new -- open row does NOT block settled row of same bet
# ---------------------------------------------------------------------------
def test_append_if_new_open_does_not_block_settled(tmp_path):
    """append_if_new uses (bet_id|status) key: settled twin must not be skipped."""
    ledger = tmp_path / "led.jsonl"
    seen: set = set()

    # Write open row
    r1 = append_if_new(_open_row(), ledger, _seen=seen)
    assert r1 is True

    # Write settled twin (different status) -- must NOT be blocked
    r2 = append_if_new(_settled_row(), ledger, _seen=seen)
    assert r2 is True, "settled twin must be appended even when open row is present"

    rows = _read_jsonl(ledger)
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Test 9: append_if_new -- exact replay (same bet_id + same status) -> blocked
# ---------------------------------------------------------------------------
def test_append_if_new_replay_blocked(tmp_path):
    """append_if_new must return False on a byte-identical replay."""
    ledger = tmp_path / "led.jsonl"
    seen: set = set()

    r1 = append_if_new(_open_row(), ledger, _seen=seen)
    assert r1 is True

    # Same row again
    r2 = append_if_new(_open_row(), ledger, _seen=seen)
    assert r2 is False

    rows = _read_jsonl(ledger)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Test 10: _first_occurrence_rows internal helper
# ---------------------------------------------------------------------------
def test_first_occurrence_rows_twin_and_replay():
    """Unit-test _first_occurrence_rows directly: twin kept, replay dropped."""
    rows = [_open_row(), _settled_row(), _open_row()]  # open, settled, open-replay

    deduped, n_dups = _first_occurrence_rows(rows)

    assert n_dups == 1, "exactly one replay should be dropped"
    assert len(deduped) == 2, "open + settled must both survive"
    statuses = {r["status"] for r in deduped}
    assert statuses == {"open", "settled"}


# ---------------------------------------------------------------------------
# Test 11: _strip_dollar_keys helper
# ---------------------------------------------------------------------------
def test_strip_dollar_keys_removes_banned():
    """_strip_dollar_keys must remove all banned keys without touching others."""
    row = {"bet_id": "X", "stake_units": 1.0, "pnl": 5.0, "roi": 0.1, "sport": "nba"}
    clean = _strip_dollar_keys(row)
    assert "pnl" not in clean
    assert "roi" not in clean
    assert clean["stake_units"] == 1.0
    assert clean["sport"] == "nba"
    # Original must not be mutated
    assert "pnl" in row


# ===========================================================================
# Workstream BE-R5-3 acceptance tests (a)-(d) for sanitize_rows pure function
# ===========================================================================

# ---------------------------------------------------------------------------
# Acceptance (a): two open rows with identical status-folded key collapse to one
# ---------------------------------------------------------------------------
def test_sanitize_rows_a_two_open_rows_collapse(tmp_path):
    """(a) sanitize_rows: two OPEN rows sharing the same status-folded key collapse to one."""
    rows = [_open_row(), _open_row()]  # exact replay: same bet_id + status=open

    kept, dropped = sanitize_rows(rows)

    assert dropped == 1, "exactly one dup should be reported"
    assert len(kept) == 1, "only one open row should survive"
    assert kept[0]["status"] == "open"
    # Return type contract: 2-tuple
    assert isinstance(kept, list)
    assert isinstance(dropped, int)


# ---------------------------------------------------------------------------
# Acceptance (b): open row + settled twin (same bet_id, different status) both kept
# ---------------------------------------------------------------------------
def test_sanitize_rows_b_open_and_settled_twin_both_kept(tmp_path):
    """(b) sanitize_rows: open + settled twin of the SAME bet_id -> BOTH kept (distinct keys)."""
    rows = [_open_row(), _settled_row()]  # same bet_id, different status

    kept, dropped = sanitize_rows(rows)

    assert dropped == 0, "no dups: open and settled are distinct keys"
    assert len(kept) == 2, "both rows must survive"
    statuses = {r["status"] for r in kept}
    assert "open" in statuses
    assert "settled" in statuses


# ---------------------------------------------------------------------------
# Acceptance (c): byte-for-byte replay of a settled row collapses to one
# ---------------------------------------------------------------------------
def test_sanitize_rows_c_settled_replay_collapses(tmp_path):
    """(c) sanitize_rows: settled row written twice collapses to one (last wins)."""
    settled_v1 = dict(_settled_row())
    settled_v1["clv_pct"] = 1.11

    settled_v2 = dict(_settled_row())
    settled_v2["clv_pct"] = 2.22  # later update with fresh clv_pct

    rows = [settled_v1, settled_v2]  # both have same bet_id + status=settled

    kept, dropped = sanitize_rows(rows)

    assert dropped == 1, "one settled replay must be dropped"
    assert len(kept) == 1, "only one settled row survives (last)"
    # For settled rows, sanitize_rows keeps the LAST occurrence.
    assert kept[0]["clv_pct"] == 2.22, "last settled row (v2) must win"


# ---------------------------------------------------------------------------
# Acceptance (d): returns (kept_rows, dropped_count) and never writes to DEFAULT_LEDGER
# ---------------------------------------------------------------------------
def test_sanitize_rows_d_pure_function_never_touches_default_ledger(tmp_path, monkeypatch):
    """(d) sanitize_rows is a pure function: returns (list, int), never writes DEFAULT_LEDGER."""
    # Redirect DEFAULT_LEDGER to a tmp file that does NOT exist.
    # If sanitize_rows ever writes to it the file will appear and the assert fails.
    sentinel = tmp_path / "should_never_be_written.jsonl"
    monkeypatch.setattr(
        "scripts.platformkit.clv_ledger.DEFAULT_LEDGER",
        sentinel,
    )

    rows = [_open_row(), _open_row(), _settled_row()]
    result = sanitize_rows(rows)

    # Return value shape
    assert isinstance(result, tuple), "must return a 2-tuple"
    assert len(result) == 2, "tuple must have exactly 2 elements"
    kept, dropped = result
    assert isinstance(kept, list)
    assert isinstance(dropped, int)

    # Correctness: one open replay dropped; settled twin kept
    assert dropped == 1
    assert len(kept) == 2  # one open + one settled

    # The sentinel file must not have been touched.
    assert not sentinel.exists(), "sanitize_rows must never write to DEFAULT_LEDGER"
