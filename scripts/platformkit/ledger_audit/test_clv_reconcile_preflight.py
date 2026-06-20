"""tests for clv_reconcile_preflight -- read-only CLV ledger dup reconciliation.

Acceptance criteria (from workstream be-r2-w2-clv-preflight-reconcile):
  (1) open + settled twin of the same bet_id -> CLEAN (status-aware key, no false dup)
  (2) two identical (bet_id|open) rows -> DUPS_FOUND; keep_first_plan names line 1
      as kept and line 2+ as quarantine_candidates
  (3) reconcile_preflight NEVER writes or deletes the ledger
  (4) missing ledger -> status=UNAVAILABLE, not an exception
  (5) no $ / roi / pnl / profit / dollar field anywhere in output

All tests are self-contained: they write to tmp_path (pytest fixture) only.
NEVER imports from human-gated paths; stdlib + pytest + the module under test.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.ledger_audit.clv_reconcile_preflight import (
    reconcile_preflight,
    _row_key_status_aware,
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


def _no_dollar_fields(obj: Any, path: str = "") -> None:
    """Recursively assert no dollar / roi / pnl / profit key in output."""
    banned = {"dollar", "roi", "pnl", "profit", "usd", "bankroll", "stake_usd"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = k.lower()
            for b in banned:
                assert b not in low, (
                    "banned field %r found at %s.%s" % (b, path, k)
                )
            _no_dollar_fields(v, path="%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _no_dollar_fields(item, path="%s[%d]" % (path, i))


# ---------------------------------------------------------------------------
# 1. open + settled twin of the SAME bet -> CLEAN (status-aware, no false dup)
# ---------------------------------------------------------------------------

def test_open_settled_twin_is_not_a_dup(tmp_path: Path) -> None:
    """An open row and its settled twin share the same bet_id but must NOT be dups."""
    ledger = tmp_path / "clv_ledger.jsonl"
    open_row = {
        "bet_id": "nba|game1|moneyline|home|book_a|2026-06-20",
        "sport": "nba",
        "matchup": "team_a vs team_b",
        "side": "home",
        "taken_book": "book_a",
        "taken_decimal": 2.1,
        "stake_units": 1.0,
        "status": "open",
    }
    settled_row = dict(open_row)
    settled_row["status"] = "settled"
    settled_row["clv_pct"] = 1.23
    settled_row["beat_close"] = True

    _write_ledger(ledger, [open_row, settled_row])

    result = reconcile_preflight(path=ledger)

    assert result["status"] == "CLEAN", (
        "open+settled twin must not be a dup; got: %s" % result
    )
    assert result["n_dups"] == 0
    assert result["keep_first_plan"] == []
    assert result["n_rows_scanned"] == 2
    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# 2. two identical (bet_id|open) rows -> DUPS_FOUND with correct plan
# ---------------------------------------------------------------------------

def test_true_dup_open_rows_found(tmp_path: Path) -> None:
    """Two rows with the same bet_id AND same status -> DUPS_FOUND."""
    ledger = tmp_path / "clv_ledger.jsonl"
    row_a = {
        "bet_id": "nba|game2|moneyline|away|book_b|2026-06-20",
        "sport": "nba",
        "matchup": "team_c vs team_d",
        "side": "away",
        "taken_book": "book_b",
        "taken_decimal": 1.85,
        "stake_units": 2.0,
        "status": "open",
    }
    row_b = dict(row_a)  # identical -> true dup

    _write_ledger(ledger, [row_a, row_b])

    result = reconcile_preflight(path=ledger)

    assert result["status"] == "DUPS_FOUND", (
        "two identical open rows must be flagged; got: %s" % result
    )
    assert result["n_dups"] == 1
    assert len(result["dup_keys"]) == 1

    plan = result["keep_first_plan"]
    assert len(plan) == 1

    entry = plan[0]
    assert entry["kept_line"] == 1, "first occurrence (line 1) must be kept"
    assert entry["quarantine_candidates"] == [2], "line 2 must be the quarantine candidate"

    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# 3. NEVER writes or deletes the ledger
# ---------------------------------------------------------------------------

def test_never_mutates_ledger(tmp_path: Path) -> None:
    """reconcile_preflight must not write or delete the ledger file."""
    ledger = tmp_path / "clv_ledger.jsonl"
    row = {
        "bet_id": "nba|game3|spread|home|book_c|2026-06-20",
        "status": "open",
        "taken_decimal": 1.95,
    }
    _write_ledger(ledger, [row])

    before_mtime = os.path.getmtime(str(ledger))
    before_size = os.path.getsize(str(ledger))

    reconcile_preflight(path=ledger)

    after_mtime = os.path.getmtime(str(ledger))
    after_size = os.path.getsize(str(ledger))

    assert before_mtime == after_mtime, "mtime changed -> ledger was written"
    assert before_size == after_size, "size changed -> ledger was mutated"


# ---------------------------------------------------------------------------
# 4. missing ledger -> status=UNAVAILABLE, not an exception
# ---------------------------------------------------------------------------

def test_missing_ledger_returns_unavailable(tmp_path: Path) -> None:
    """If the ledger file does not exist, return UNAVAILABLE without raising."""
    missing = tmp_path / "does_not_exist.jsonl"
    assert not missing.exists()

    result = reconcile_preflight(path=missing)

    assert result["status"] == "UNAVAILABLE", (
        "missing ledger must yield UNAVAILABLE; got: %s" % result
    )
    assert result["error"] is not None
    assert result["n_dups"] == 0
    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# 5. multiple dup keys -> plan has one entry per key, each with keep+quarantine
# ---------------------------------------------------------------------------

def test_multiple_dup_keys_plan(tmp_path: Path) -> None:
    """A ledger with 2 distinct dup keys (each appearing 3x) surfaces all candidates."""
    ledger = tmp_path / "clv_ledger.jsonl"

    rows: List[Dict[str, Any]] = []
    for key_suffix in ("A", "B"):
        base = {
            "bet_id": "nba|game_%s|ml|home|bk|2026-06-20" % key_suffix,
            "status": "open",
            "taken_decimal": 2.0,
        }
        rows.append(dict(base))
        rows.append(dict(base))
        rows.append(dict(base))

    _write_ledger(ledger, rows)

    result = reconcile_preflight(path=ledger)

    assert result["status"] == "DUPS_FOUND"
    assert result["n_dups"] == 2
    assert result["n_rows_scanned"] == 6

    for entry in result["keep_first_plan"]:
        assert len(entry["quarantine_candidates"]) == 2, (
            "each key has 3 occurrences -> 1 kept + 2 quarantine"
        )

    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# 6. status-aware key unit test: open vs settled -> distinct; same -> same
# ---------------------------------------------------------------------------

def test_row_key_status_aware_open_settled_distinct() -> None:
    """Same bet_id + different status -> distinct keys."""
    base = {"bet_id": "nba|g1|ml|home|bk|2026-06-20"}
    open_row = dict(base, status="open")
    settled_row = dict(base, status="settled")
    assert _row_key_status_aware(open_row) != _row_key_status_aware(settled_row)


def test_row_key_status_aware_same_status_same_key() -> None:
    """Same bet_id + same status -> same key (still detected as dup)."""
    base = {"bet_id": "nba|g1|ml|home|bk|2026-06-20", "status": "open"}
    assert _row_key_status_aware(base) == _row_key_status_aware(dict(base))


def test_row_key_missing_status_does_not_raise() -> None:
    """Missing status field must not raise."""
    row = {"bet_id": "nba|g1|ml|home|bk|2026-06-20"}
    key = _row_key_status_aware(row)
    assert isinstance(key, str)
    assert len(key) > 0


# ---------------------------------------------------------------------------
# 7. clean ledger -> CLEAN with empty plan
# ---------------------------------------------------------------------------

def test_clean_ledger_returns_clean(tmp_path: Path) -> None:
    """A ledger with all-unique (bet_id|status) keys returns CLEAN."""
    ledger = tmp_path / "clv_ledger.jsonl"
    rows = [
        {"bet_id": "nba|g1|ml|home|bk|2026-06-20", "status": "open",
         "taken_decimal": 2.1},
        {"bet_id": "nba|g1|ml|home|bk|2026-06-20", "status": "settled",
         "taken_decimal": 2.1, "clv_pct": 0.5},
        {"bet_id": "nba|g2|ml|away|bk|2026-06-20", "status": "open",
         "taken_decimal": 1.9},
    ]
    _write_ledger(ledger, rows)

    result = reconcile_preflight(path=ledger)

    assert result["status"] == "CLEAN"
    assert result["n_dups"] == 0
    assert result["keep_first_plan"] == []
    assert result["n_rows_scanned"] == 3
    _no_dollar_fields(result)


# ---------------------------------------------------------------------------
# 8. empty ledger -> CLEAN, not an error
# ---------------------------------------------------------------------------

def test_empty_ledger_is_clean(tmp_path: Path) -> None:
    """An empty (but existing) ledger is CLEAN."""
    ledger = tmp_path / "clv_ledger.jsonl"
    ledger.write_text("", encoding="utf-8")

    result = reconcile_preflight(path=ledger)

    assert result["status"] == "CLEAN"
    assert result["n_rows_scanned"] == 0
    _no_dollar_fields(result)
