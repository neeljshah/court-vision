"""Per-file tests for scripts.platformkit.clv_ledger_status_dedup.

Acceptance criteria (CLV-STATUS-KEY):
  1. open row + settled row with same bet_id -> two DISTINCT status-aware keys
     (no false dup, both retained in the ledger).
  2. identical open-row replayed twice -> second is a no-op (appended False).
  3. missing ledger -> created and row appended (appended True).
  4. no $/pnl/roi/bankroll key introduced on any written row.
  5. never raises (returns {"appended": False, "error": ...} on failure).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_status_dedup.py -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.platformkit.clv_ledger_status_dedup import (
    append_if_new_status_aware,
    dedup_status_ledger,
    status_key,
)
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_open_row(bet_id: str = "sport|event|ml|home|dk|2026-06-20") -> Dict[str, Any]:
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


def _make_settled_row(bet_id: str = "sport|event|ml|home|dk|2026-06-20") -> Dict[str, Any]:
    row = _make_open_row(bet_id)
    row["status"] = "settled"
    row["clv_pct"] = 1.23
    row["beat_close"] = True
    return row


def _load_lines(path: Path) -> list:
    lines = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines


# ---------------------------------------------------------------------------
# 1. status_key produces distinct keys for open vs settled
# ---------------------------------------------------------------------------

class TestStatusKey:
    def test_open_and_settled_are_distinct(self):
        open_row = _make_open_row()
        settled_row = _make_settled_row()
        assert status_key(open_row) != status_key(settled_row)

    def test_open_key_suffix(self):
        row = _make_open_row("a|b|ml|home|dk|2026-01-01")
        assert status_key(row) == "a|b|ml|home|dk|2026-01-01|open"

    def test_settled_key_suffix(self):
        row = _make_settled_row("a|b|ml|home|dk|2026-01-01")
        assert status_key(row) == "a|b|ml|home|dk|2026-01-01|settled"

    def test_missing_status_defaults_to_open(self):
        row = {"bet_id": "x|open_test", "sport": "nba"}
        k = status_key(row)
        assert k.endswith("|open")

    def test_byte_for_byte_replay_produces_same_key(self):
        """Two identical open rows -> same key (true replay detected)."""
        row = _make_open_row()
        assert status_key(row) == status_key(dict(row))


# ---------------------------------------------------------------------------
# 2. append_if_new_status_aware -- open + settled both retained
# ---------------------------------------------------------------------------

class TestAppendStatusAware:
    def test_open_and_settled_both_appended(self, tmp_path):
        """Core acceptance: open + settled of same bet_id -> two rows retained."""
        ledger = tmp_path / "clv.jsonl"
        open_row = _make_open_row()
        settled_row = _make_settled_row()

        r1 = append_if_new_status_aware(open_row, ledger)
        r2 = append_if_new_status_aware(settled_row, ledger)

        assert r1["appended"] is True, "open row should be appended"
        assert r2["appended"] is True, "settled row should be appended (not a dup)"

        rows = _load_lines(ledger)
        assert len(rows) == 2, "both open and settled rows must be in ledger"
        statuses = {r["status"] for r in rows}
        assert statuses == {"open", "settled"}

    def test_open_row_replay_is_noop(self, tmp_path):
        """Identical open-row replayed twice -> second write is blocked."""
        ledger = tmp_path / "clv.jsonl"
        open_row = _make_open_row()

        r1 = append_if_new_status_aware(open_row, ledger)
        r2 = append_if_new_status_aware(dict(open_row), ledger)

        assert r1["appended"] is True
        assert r2["appended"] is False, "replay of open row must be a no-op"

        rows = _load_lines(ledger)
        assert len(rows) == 1, "only one row must exist (replay blocked)"

    def test_settled_row_replay_is_noop(self, tmp_path):
        """Identical settled-row replayed twice -> second write is blocked."""
        ledger = tmp_path / "clv.jsonl"
        settled_row = _make_settled_row()

        r1 = append_if_new_status_aware(settled_row, ledger)
        r2 = append_if_new_status_aware(dict(settled_row), ledger)

        assert r1["appended"] is True
        assert r2["appended"] is False

        rows = _load_lines(ledger)
        assert len(rows) == 1

    def test_missing_ledger_creates_and_appends(self, tmp_path):
        """Missing ledger file -> directory created, row appended, True returned."""
        ledger = tmp_path / "subdir" / "clv.jsonl"
        assert not ledger.exists(), "precondition: file must not exist"

        row = _make_open_row()
        result = append_if_new_status_aware(row, ledger)

        assert result["appended"] is True
        assert ledger.exists(), "ledger should be created"
        rows = _load_lines(ledger)
        assert len(rows) == 1

    def test_no_banned_dollar_keys_written(self, tmp_path):
        """No $/pnl/roi/bankroll key must appear on any written row."""
        ledger = tmp_path / "clv.jsonl"
        # Inject a banned key to verify stripping.
        row = _make_open_row()
        row["pnl"] = 999.99          # banned
        row["bankroll"] = 5000.0     # banned
        row["roi"] = 0.18            # banned

        append_if_new_status_aware(row, ledger)

        rows = _load_lines(ledger)
        assert len(rows) == 1
        written = rows[0]
        for banned in BANNED_KEYS:
            assert banned not in written, "banned key %r must not appear in ledger" % banned

    def test_key_returned_on_append(self, tmp_path):
        """Return dict must contain 'key' with the correct status_key string."""
        ledger = tmp_path / "clv.jsonl"
        row = _make_open_row("k|v|ml|home|dk|2026-06-20")
        result = append_if_new_status_aware(row, ledger)
        assert result["key"] == "k|v|ml|home|dk|2026-06-20|open"

    def test_key_returned_on_skip(self, tmp_path):
        """Skipped (dup) write must still return 'key' field, not 'error'."""
        ledger = tmp_path / "clv.jsonl"
        row = _make_open_row()
        append_if_new_status_aware(row, ledger)
        result2 = append_if_new_status_aware(dict(row), ledger)
        assert "error" not in result2
        assert "key" in result2
        assert result2["appended"] is False

    def test_never_raises_on_bad_input(self, tmp_path):
        """Garbage input must not raise -- returns error dict instead."""
        ledger = tmp_path / "clv.jsonl"
        # Pass an object that will fail json.dumps
        row = {"bet_id": object()}  # type: ignore[dict-item]
        # Should not raise
        result = append_if_new_status_aware(row, ledger)  # type: ignore[arg-type]
        # May succeed (default=str) or return error, but must never raise.
        assert isinstance(result, dict)
        assert "appended" in result

    def test_seen_set_updated_on_append(self, tmp_path):
        """_seen set is mutated in-place when a row is appended."""
        ledger = tmp_path / "clv.jsonl"
        row = _make_open_row()
        seen: set = set()
        result = append_if_new_status_aware(row, ledger, _seen=seen)
        assert result["appended"] is True
        assert status_key(row) in seen, "_seen must contain the new key after append"

    def test_seen_set_prevents_rescan(self, tmp_path):
        """When _seen is passed, a dup is detected without re-reading the file."""
        ledger = tmp_path / "clv.jsonl"
        row = _make_open_row()
        seen: set = set()
        append_if_new_status_aware(row, ledger, _seen=seen)
        # Second call with same _seen -- dedup detected in-memory, no file read.
        result2 = append_if_new_status_aware(dict(row), ledger, _seen=seen)
        assert result2["appended"] is False

    def test_three_distinct_bets_all_appended(self, tmp_path):
        """Three distinct bet_ids -> three rows in ledger, all appended=True."""
        ledger = tmp_path / "clv.jsonl"
        for i in range(3):
            row = _make_open_row("id%d|ml|home|dk|2026-06-20" % i)
            result = append_if_new_status_aware(row, ledger)
            assert result["appended"] is True
        rows = _load_lines(ledger)
        assert len(rows) == 3

    def test_full_settlement_cycle(self, tmp_path):
        """Simulate a full open->settled cycle for multiple bets.

        open rows for bet A and bet B -> both appended.
        settled rows for bet A and bet B -> both appended.
        replay open row for bet A -> blocked.
        Total: 4 rows in ledger.
        """
        ledger = tmp_path / "clv.jsonl"
        bid_a = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        bid_b = "mlb|CHW@DET|ml|away|dk|2026-06-20"

        results = [
            append_if_new_status_aware(_make_open_row(bid_a), ledger),
            append_if_new_status_aware(_make_open_row(bid_b), ledger),
            append_if_new_status_aware(_make_settled_row(bid_a), ledger),
            append_if_new_status_aware(_make_settled_row(bid_b), ledger),
        ]
        for i, r in enumerate(results):
            assert r["appended"] is True, "step %d should have appended" % i

        # Replay open row A -> blocked
        replay = append_if_new_status_aware(_make_open_row(bid_a), ledger)
        assert replay["appended"] is False, "replay of open A must be blocked"

        rows = _load_lines(ledger)
        assert len(rows) == 4, "ledger must have exactly 4 rows (2 open + 2 settled)"


# ---------------------------------------------------------------------------
# 3. dedup_status_ledger -- status-aware full-ledger dedup rewrite
# ---------------------------------------------------------------------------

def _write_ledger(path: Path, rows: list) -> None:
    """Write a list of row dicts as JSONL to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


class TestDedupStatusLedger:
    def test_no_file_returns_no_file(self, tmp_path):
        """Missing ledger -> status 'no_file', no crash."""
        ledger = tmp_path / "nonexistent.jsonl"
        result = dedup_status_ledger(ledger)
        assert result["status"] == "no_file"
        assert result["dups_removed"] == 0

    def test_clean_ledger_returns_no_change(self, tmp_path):
        """Ledger with no status-aware dups -> status 'no_change', file untouched."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        _write_ledger(ledger, [_make_open_row(bid), _make_settled_row(bid)])
        result = dedup_status_ledger(ledger)
        assert result["status"] == "no_change"
        assert result["dups_removed"] == 0
        rows = _load_lines(ledger)
        assert len(rows) == 2  # both twins still present

    def test_dry_run_does_not_write(self, tmp_path):
        """dry_run=True (default) never modifies the file even when dups exist."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        open_row = _make_open_row(bid)
        # Two identical open rows (true dup)
        _write_ledger(ledger, [open_row, open_row])
        mtime_before = ledger.stat().st_mtime

        result = dedup_status_ledger(ledger, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["dups_removed"] == 1
        # File must not be touched
        assert ledger.stat().st_mtime == mtime_before

    def test_open_settled_twins_both_kept(self, tmp_path):
        """Core: open + settled of same bet_id -> BOTH kept (not collapsed)."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        _write_ledger(ledger, [_make_open_row(bid), _make_settled_row(bid)])
        result = dedup_status_ledger(ledger, dry_run=False)
        # No dups -> no_change (both twins have distinct status keys)
        assert result["status"] == "no_change"
        rows = _load_lines(ledger)
        assert len(rows) == 2
        statuses = {r["status"] for r in rows}
        assert statuses == {"open", "settled"}

    def test_identical_open_rows_collapsed_to_one(self, tmp_path):
        """Two byte-for-byte identical open rows -> 1 kept (latest), 1 removed."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        row_a = _make_open_row(bid)
        row_b = dict(row_a)
        row_b["marker"] = "latest"  # differentiates the two for 'latest wins' check
        _write_ledger(ledger, [row_a, row_b])
        result = dedup_status_ledger(ledger, dry_run=False)
        assert result["status"] == "ok"
        assert result["dups_removed"] == 1
        rows = _load_lines(ledger)
        assert len(rows) == 1
        # LATEST occurrence wins
        assert rows[0].get("marker") == "latest"

    def test_bak_file_written_on_apply(self, tmp_path):
        """Applying the dedup writes a .bak backup of the original."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        row = _make_open_row(bid)
        _write_ledger(ledger, [row, row])
        dedup_status_ledger(ledger, dry_run=False)
        bak = ledger.with_suffix(ledger.suffix + ".bak")
        assert bak.exists(), ".bak file must be written alongside the rewrite"

    def test_no_dollar_keys_in_output(self, tmp_path):
        """No banned $/pnl/roi keys must appear in the deduped ledger."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        dirty = _make_open_row(bid)
        dirty["pnl"] = 42.0
        dirty["bankroll"] = 1000.0
        _write_ledger(ledger, [dirty, dirty])  # two dirty identical rows
        result = dedup_status_ledger(ledger, dry_run=False)
        assert result["status"] == "ok"
        rows = _load_lines(ledger)
        assert len(rows) == 1
        for banned in BANNED_KEYS:
            assert banned not in rows[0], "banned key %r must be stripped" % banned

    def test_error_on_corrupt_ledger_never_raises(self, tmp_path):
        """Completely corrupt ledger must not raise -- returns error or no_change."""
        ledger = tmp_path / "clv.jsonl"
        ledger.write_text("not json at all\n", encoding="utf-8")
        # Must not raise regardless of dry_run
        result = dedup_status_ledger(ledger, dry_run=False)
        assert isinstance(result, dict)
        assert "status" in result
        # status is one of the known sentinels or an error string
        assert str(result["status"]).startswith("error") or result["status"] in (
            "ok", "no_change", "no_file", "dry_run"
        )

    def test_rows_in_rows_out_counts_accurate(self, tmp_path):
        """rows_in and rows_out in the result dict match actual ledger counts."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        open_row = _make_open_row(bid)
        settled_row = _make_settled_row(bid)
        dup_open = dict(open_row)
        # 3 rows: open, settled, duplicate open -> 2 unique status keys
        _write_ledger(ledger, [open_row, settled_row, dup_open])
        result = dedup_status_ledger(ledger, dry_run=True)
        assert result["rows_in"] == 3
        assert result["rows_out"] == 2
        assert result["dups_removed"] == 1
        assert result["status"] == "dry_run"

    def test_idempotent_double_apply(self, tmp_path):
        """Running dedup twice produces same result; second run reports no_change."""
        ledger = tmp_path / "clv.jsonl"
        bid = "nba|NYK@SAS|ml|home|dk|2026-06-20"
        row = _make_open_row(bid)
        _write_ledger(ledger, [row, row])
        r1 = dedup_status_ledger(ledger, dry_run=False)
        assert r1["status"] == "ok"
        r2 = dedup_status_ledger(ledger, dry_run=False)
        assert r2["status"] == "no_change"
