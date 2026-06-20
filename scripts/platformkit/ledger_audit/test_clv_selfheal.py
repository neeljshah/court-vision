"""tests for clv_selfheal -- atomic keep-first dedup self-heal driver.

Acceptance criteria (W-CLV-SELFHEAL workstream):
  (1) A ledger with open+settle dup keys (status-change appends) is healed:
      - rows preserved (open twin + settled twin both kept)
      - only genuine same-status dups dropped
      - dropped_keys list returned
  (2) After heal the concurrency gate (_run_concurrency) exits 0 (clean).
  (3) A ledger with genuine non-status dups still fails HEALED_BLOCKED after heal
      (i.e., rows that are truly identical including status AND cannot be
      distinguished by keep-first still block the gate -- though in practice
      keep-first resolves all same-key dups, so this test verifies the
      post-heal re-scan is actually run and returns HEALED_OK, not BLOCKED,
      because keep-first IS sufficient to resolve same-status dups).
      The HEALED_BLOCKED path fires only when the post-heal scan STILL finds dups,
      which can occur if the ledger has mixed-encoding corruption that the
      json parser cannot distinguish -- we test the branch via monkeypatching.
  (4) No $ / pnl / roi / profit / dollar field in any output.
  (5) Mutation is atomic: original backed up to .selfheal.bak; tmp cleaned.
  (6) Missing ledger -> UNAVAILABLE, no exception.
  (7) dry_run=True returns HEALED_OK status without touching the file.

All tests are self-contained; they use tmp_path and never touch the canonical
data/frontend/clv_ledger.jsonl.  NEVER imports from human-gated paths.
NEVER runs the full test suite (per-file only).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from scripts.platformkit.ledger_audit.clv_selfheal import (
    selfheal,
    SELFHEAL_CLEAN,
    SELFHEAL_OK,
    SELFHEAL_BLOCKED,
    SELFHEAL_UNAVAIL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ledger(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write rows as JSONL to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _load_ledger(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL rows from path."""
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _no_dollar_fields(obj: Any, path: str = "") -> None:
    """Recursively assert no banned dollar/roi/pnl/profit key in output."""
    banned = {"dollar", "roi", "pnl", "profit", "usd", "bankroll", "stake_usd"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = k.lower()
            for b in banned:
                assert b not in low, (
                    "banned field %r at %s.%s" % (b, path, k)
                )
            _no_dollar_fields(v, path="%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _no_dollar_fields(item, path="%s[%d]" % (path, i))


# ---------------------------------------------------------------------------
# Test 1: open+settle STATUS-CHANGE dups are healed; keep-first applied
# ---------------------------------------------------------------------------

def test_status_change_dups_are_healed(tmp_path: Path) -> None:
    """Ledger with genuine same-status dups (from replay) is healed; open+settled twins kept."""
    ledger = tmp_path / "clv_ledger.jsonl"

    open_row = {
        "bet_id": "nba|g1|ml|home|bk|2026-06-20",
        "status": "open",
        "sport": "nba",
        "stake_units": 1.0,
        "taken_decimal": 2.1,
    }
    settled_row = dict(open_row, status="settled", clv_pct=0.5, beat_close=True)
    # Replay dup: same bet_id AND same status -> genuine dup that must be dropped
    open_dup = dict(open_row)

    _write_ledger(ledger, [open_row, settled_row, open_dup])

    result = selfheal(path=ledger)

    # Status must be HEALED_OK
    assert result["status"] == SELFHEAL_OK, "expected HEALED_OK; got: %s" % result

    # dups_before must be 1 (only the open replay is a true dup)
    assert result["dups_before"] == 1, "dups_before=%d" % result["dups_before"]
    assert result["dups_after"] == 0, "dups_after=%d" % result["dups_after"]

    # Exactly one key dropped
    assert len(result["dropped_keys"]) == 1

    # rows_in=3, rows_out=2 (dup dropped; open twin + settled twin kept)
    assert result["rows_in"] == 3
    assert result["rows_out"] == 2

    # Verify on-disk content: 2 rows remain, both correct
    remaining = _load_ledger(ledger)
    assert len(remaining) == 2, "expected 2 rows after heal; got %d" % len(remaining)
    statuses = {r["status"] for r in remaining}
    assert statuses == {"open", "settled"}, "expected open+settled twins; got %s" % statuses

    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# Test 2: after heal, _run_concurrency from run_governance exits clean
# ---------------------------------------------------------------------------

def test_concurrency_gate_clean_after_heal(tmp_path: Path) -> None:
    """After selfheal, _run_concurrency must return ok=True (gate exits 0)."""
    ledger = tmp_path / "clv_ledger.jsonl"

    row = {
        "bet_id": "nba|g2|spread|away|bk|2026-06-20",
        "status": "open",
        "taken_decimal": 1.9,
        "stake_units": 0.5,
    }
    # Write two identical rows -> genuine dup
    _write_ledger(ledger, [row, dict(row)])

    # Heal first
    heal_result = selfheal(path=ledger)
    assert heal_result["status"] == SELFHEAL_OK, "heal failed: %s" % heal_result

    # Now run the actual governance concurrency gate
    from governance.run_governance import _run_concurrency
    gate = _run_concurrency(ledger_path=ledger)
    assert gate["ok"] is True, (
        "concurrency gate must be ok after heal; got: %s" % gate
    )
    assert gate["duplicate_keys"] == [], (
        "duplicate_keys must be empty after heal; got: %s" % gate["duplicate_keys"]
    )

    _no_dollar_fields(heal_result)
    _no_dollar_fields(gate)


# ---------------------------------------------------------------------------
# Test 3: HEALED_BLOCKED path fires when post-heal re-scan still finds dups
# ---------------------------------------------------------------------------

def test_healed_blocked_when_post_scan_still_has_dups(tmp_path: Path) -> None:
    """If dups remain after heal (mocked post-scan returns DUPS_FOUND), status=HEALED_BLOCKED."""
    ledger = tmp_path / "clv_ledger.jsonl"

    row = {
        "bet_id": "nba|g3|total|over|bk|2026-06-20",
        "status": "open",
        "taken_decimal": 1.88,
        "stake_units": 1.0,
    }
    _write_ledger(ledger, [row, dict(row)])  # genuine dup

    # Monkeypatch reconcile_preflight so the POST-HEAL re-scan returns DUPS_FOUND
    # (simulating a corruption scenario where keep-first is insufficient).
    original_reconcile = None
    call_count = [0]

    import scripts.platformkit.ledger_audit.clv_selfheal as _mod

    real_reconcile = _mod.reconcile_preflight

    def _patched_reconcile(path=None):
        call_count[0] += 1
        r = real_reconcile(path=path)
        # First call: PRE-heal scan -> let it return the real result (DUPS_FOUND).
        # Second call: POST-heal scan -> force DUPS_FOUND to simulate genuine corruption.
        if call_count[0] >= 2:
            r = dict(r)
            r["status"] = "DUPS_FOUND"
            r["n_dups"] = 1
            r["dup_keys"] = ["synthetic|blocked"]
        return r

    with patch.object(_mod, "reconcile_preflight", side_effect=_patched_reconcile):
        result = selfheal(path=ledger)

    assert result["status"] == SELFHEAL_BLOCKED, (
        "expected HEALED_BLOCKED when post-heal scan still has dups; got: %s" % result
    )
    assert result["dups_after"] == 1
    assert result["error"] is not None

    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# Test 4: no $ / pnl / roi / dollar field in any output
# ---------------------------------------------------------------------------

def test_no_dollar_fields_in_output(tmp_path: Path) -> None:
    """selfheal output must never contain banned dollar/roi/pnl/profit fields."""
    ledger = tmp_path / "clv_ledger.jsonl"
    row = {
        "bet_id": "nba|g4|ml|home|bk|2026-06-20",
        "status": "open",
        "taken_decimal": 2.05,
        "stake_units": 1.5,
        # Introduce a dollar field in the row -- must be stripped on rewrite
        "pnl": 999.99,
        "roi": 55.5,
    }
    _write_ledger(ledger, [row, dict(row)])

    result = selfheal(path=ledger)
    _no_dollar_fields(result)

    # Also verify the healed ledger rows themselves have no dollar fields
    if result["status"] == SELFHEAL_OK:
        remaining = _load_ledger(ledger)
        for r in remaining:
            _no_dollar_fields(r, path="healed_row")


# ---------------------------------------------------------------------------
# Test 5: atomic backup is created; tmp file is cleaned up
# ---------------------------------------------------------------------------

def test_atomic_backup_and_tmp_cleanup(tmp_path: Path) -> None:
    """selfheal creates a .selfheal.bak and leaves no .selfheal.tmp behind."""
    ledger = tmp_path / "clv_ledger.jsonl"
    row = {
        "bet_id": "nba|g5|total|under|bk|2026-06-20",
        "status": "open",
        "taken_decimal": 1.95,
        "stake_units": 1.0,
    }
    _write_ledger(ledger, [row, dict(row)])  # genuine dup

    result = selfheal(path=ledger)
    assert result["status"] == SELFHEAL_OK

    # Backup must exist
    backup = ledger.with_suffix(ledger.suffix + ".selfheal.bak")
    assert backup.exists(), ".selfheal.bak must exist after heal"

    # No stale .selfheal.tmp files
    tmp_files = list(tmp_path.glob("*.selfheal.tmp"))
    assert tmp_files == [], "stale .tmp files after heal: %s" % tmp_files


# ---------------------------------------------------------------------------
# Test 6: missing ledger -> UNAVAILABLE, no exception
# ---------------------------------------------------------------------------

def test_missing_ledger_returns_unavailable(tmp_path: Path) -> None:
    """Missing ledger must yield UNAVAILABLE without raising."""
    missing = tmp_path / "does_not_exist.jsonl"
    assert not missing.exists()

    result = selfheal(path=missing)

    assert result["status"] == SELFHEAL_UNAVAIL
    assert result["error"] is not None
    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# Test 7: dry_run=True does NOT mutate the ledger
# ---------------------------------------------------------------------------

def test_dry_run_does_not_mutate(tmp_path: Path) -> None:
    """dry_run=True must NOT write, replace, or backup the ledger."""
    ledger = tmp_path / "clv_ledger.jsonl"
    row = {
        "bet_id": "nba|g6|ml|away|bk|2026-06-20",
        "status": "open",
        "taken_decimal": 1.85,
        "stake_units": 2.0,
    }
    _write_ledger(ledger, [row, dict(row)])  # genuine dup

    before_size = os.path.getsize(str(ledger))
    before_mtime = os.path.getmtime(str(ledger))

    result = selfheal(path=ledger, dry_run=True)

    after_size = os.path.getsize(str(ledger))
    after_mtime = os.path.getmtime(str(ledger))

    # Status must indicate what WOULD happen
    assert result["status"] == SELFHEAL_OK, (
        "dry_run should still report HEALED_OK; got: %s" % result
    )
    assert result["dry_run"] is True

    # File must be untouched
    assert before_size == after_size, "ledger size changed in dry_run"
    assert before_mtime == after_mtime, "ledger mtime changed in dry_run"

    # No backup created
    backup = ledger.with_suffix(ledger.suffix + ".selfheal.bak")
    assert not backup.exists(), "backup must not be created in dry_run"

    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# Test 8: clean ledger -> CLEAN, file untouched
# ---------------------------------------------------------------------------

def test_clean_ledger_untouched(tmp_path: Path) -> None:
    """A ledger with no dups returns CLEAN immediately without writing."""
    ledger = tmp_path / "clv_ledger.jsonl"
    rows = [
        {"bet_id": "nba|g7|ml|home|bk|2026-06-20", "status": "open",
         "taken_decimal": 2.0, "stake_units": 1.0},
        {"bet_id": "nba|g7|ml|home|bk|2026-06-20", "status": "settled",
         "taken_decimal": 2.0, "stake_units": 1.0, "clv_pct": 0.3},
        {"bet_id": "nba|g8|spread|home|bk|2026-06-20", "status": "open",
         "taken_decimal": 1.91, "stake_units": 1.0},
    ]
    _write_ledger(ledger, rows)
    before_mtime = os.path.getmtime(str(ledger))

    result = selfheal(path=ledger)

    assert result["status"] == SELFHEAL_CLEAN
    assert result["dups_before"] == 0
    assert result["dropped_keys"] == []
    assert os.path.getmtime(str(ledger)) == before_mtime, "clean ledger was written"
    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# Test 9: multiple dup keys all healed in one pass
# ---------------------------------------------------------------------------

def test_multiple_dup_keys_all_healed(tmp_path: Path) -> None:
    """A ledger with N distinct dup keys is fully healed in one pass."""
    ledger = tmp_path / "clv_ledger.jsonl"
    rows = []
    n_keys = 3
    for i in range(n_keys):
        base = {
            "bet_id": "nba|g%d|ml|home|bk|2026-06-20" % i,
            "status": "open",
            "taken_decimal": 1.9 + i * 0.05,
            "stake_units": 1.0,
        }
        # 3 copies each -> 2 dups per key
        rows += [dict(base), dict(base), dict(base)]

    _write_ledger(ledger, rows)

    result = selfheal(path=ledger)

    assert result["status"] == SELFHEAL_OK, "expected HEALED_OK; got: %s" % result
    assert result["dups_before"] == n_keys
    assert result["dups_after"] == 0
    assert len(result["dropped_keys"]) == n_keys

    # rows_out = n_keys * 1 (one kept per key)
    remaining = _load_ledger(ledger)
    assert len(remaining) == n_keys, (
        "expected %d rows; got %d" % (n_keys, len(remaining))
    )
    _no_dollar_fields(result)
