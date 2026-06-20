"""Per-file tests for scripts.platformkit.clv_settle_write.

Acceptance criteria (be-r2-w1-clv-writer-dedup):

  1. Writing an open row twice yields ONE (bet_id|open) line in the ledger.
  2. Writing its settled twin yields a SECOND DISTINCT (bet_id|settled) line.
  3. Replaying the settled twin is a no-op (no third line appended).
  4. No $/pnl/roi/profit key on any written row.
  5. status-key formula matches governance _row_key so a freshly written
     ledger scans CLEAN under ledger_audit.dup_key_detector.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_settle_write.py -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.platformkit.clv_settle_write import write_open_bet, write_settlement
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS
from scripts.platformkit.ledger_audit.dup_key_detector import scan_ledger


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_BET_ID = "nba|NYK@SAS|moneyline|home|dk|2026-06-20"


def _open_row(bet_id: str = _BET_ID) -> Dict[str, Any]:
    return {
        "bet_id": bet_id,
        "sport": "nba",
        "matchup": "NYK@SAS",
        "side": "home",
        "taken_book": "dk",
        "taken_decimal": 2.05,
        "stake_units": 1.0,
        "status": "open",
        "executed": False,
    }


def _settled_row(bet_id: str = _BET_ID) -> Dict[str, Any]:
    row = _open_row(bet_id)
    row["status"] = "settled"
    row["clv_pct"] = 1.23
    row["beat_close"] = True
    row["outcome"] = "win"
    row["unit_result"] = 1.05
    row["settle_key"] = bet_id
    return row


def _load_lines(path: Path):
    """Return a list of dicts from a JSONL file."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Test 1: double open-write -> ONE line
# ---------------------------------------------------------------------------

def test_write_open_bet_deduplicates():
    """Writing the same open row twice appends exactly ONE line."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        row = _open_row()

        r1 = write_open_bet(row, path=ledger)
        r2 = write_open_bet(row, path=ledger)

        assert r1["appended"] is True, "first write should be appended"
        assert r2["appended"] is False, "second write (same bet_id|open) should be blocked"

        lines = _load_lines(ledger)
        assert len(lines) == 1, "expected exactly 1 row after two identical open writes"
        assert lines[0]["status"] == "open"
        assert lines[0]["bet_id"] == _BET_ID


# ---------------------------------------------------------------------------
# Test 2: open + settled -> TWO distinct lines
# ---------------------------------------------------------------------------

def test_open_then_settled_produces_two_distinct_rows():
    """Open row then its settled twin = two rows, different status."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        open_row = _open_row()
        settled_row = _settled_row()

        r_open = write_open_bet(open_row, path=ledger)
        r_settled = write_settlement(settled_row, path=ledger)

        assert r_open["appended"] is True
        assert r_settled["appended"] is True, "settled twin must be a NEW distinct row"

        lines = _load_lines(ledger)
        assert len(lines) == 2, "expected exactly 2 rows (open + settled)"
        statuses = {line["status"] for line in lines}
        assert statuses == {"open", "settled"}, "must have one open and one settled"


# ---------------------------------------------------------------------------
# Test 3: settled replay is a no-op
# ---------------------------------------------------------------------------

def test_write_settlement_replay_is_noop():
    """Replaying the settled twin a second time appends nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        open_row = _open_row()
        settled_row = _settled_row()

        write_open_bet(open_row, path=ledger)
        r1 = write_settlement(settled_row, path=ledger)
        r2 = write_settlement(settled_row, path=ledger)  # replay

        assert r1["appended"] is True
        assert r2["appended"] is False, "settled replay must be blocked"

        lines = _load_lines(ledger)
        assert len(lines) == 2, "expected 2 rows total (open + settled), not 3"


# ---------------------------------------------------------------------------
# Test 4: no banned $/pnl/roi keys on written rows
# ---------------------------------------------------------------------------

def test_no_banned_dollar_keys_written():
    """No dollar / pnl / roi key survives into the ledger."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        # Inject banned keys into both row variants.
        dirty_open = {**_open_row(), "pnl": 99.0, "roi": 0.5, "profit": 10.0}
        dirty_settled = {**_settled_row(), "bankroll": 1000.0, "dollars": 55.0}

        write_open_bet(dirty_open, path=ledger)
        write_settlement(dirty_settled, path=ledger)

        for row in _load_lines(ledger):
            for banned in BANNED_KEYS:
                assert banned not in row, (
                    "banned key %r found on %s row" % (banned, row.get("status"))
                )


# ---------------------------------------------------------------------------
# Test 5: dup_key_detector scans CLEAN after write_open_bet + write_settlement
# ---------------------------------------------------------------------------

def test_dup_key_detector_clean_after_open_and_settled():
    """A ledger with one open + one settled row for the same bet_id is CLEAN.

    Verifies the status_key formula aligns with ledger_audit.dup_key_detector
    so the governance dup scanner sees no false collisions.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        write_open_bet(_open_row(), path=ledger)
        write_settlement(_settled_row(), path=ledger)

        result = scan_ledger(path=ledger)
        assert result["status"] == "CLEAN", (
            "dup_key_detector reported %s; dup_keys=%r"
            % (result["status"], result.get("dup_keys"))
        )
        assert result["n_dups"] == 0
        assert result["n_rows_scanned"] == 2


# ---------------------------------------------------------------------------
# Test 6: true byte-for-byte settled replay is still flagged by dup_key_detector
# ---------------------------------------------------------------------------

def test_dup_key_detector_catches_true_settled_dup():
    """If two identical settled rows are somehow written, detector catches it."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        settled = _settled_row()
        # Force-write the same settled row twice via raw file to simulate corruption.
        with ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(settled) + "\n")
            fh.write(json.dumps(settled) + "\n")

        result = scan_ledger(path=ledger)
        assert result["status"] == "DUPS_FOUND", (
            "detector missed a true byte-for-byte settled duplicate"
        )
        assert result["n_dups"] >= 1


# ---------------------------------------------------------------------------
# Test 7: write_settlement returns the key in the response
# ---------------------------------------------------------------------------

def test_write_settlement_returns_key():
    """write_settlement must return the status_key in the result dict."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        result = write_settlement(_settled_row(), path=ledger)
        assert result.get("key") == "%s|settled" % _BET_ID


# ---------------------------------------------------------------------------
# Test 8: write_open_bet returns the key in the response
# ---------------------------------------------------------------------------

def test_write_open_bet_returns_key():
    """write_open_bet must return the status_key in the result dict."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        result = write_open_bet(_open_row(), path=ledger)
        assert result.get("key") == "%s|open" % _BET_ID
