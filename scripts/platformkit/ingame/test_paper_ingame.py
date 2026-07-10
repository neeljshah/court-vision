"""Per-file tests for scripts.platformkit.ingame.paper_ingame.

Tests the write-guard that rejects malformed rows BEFORE they touch the ledger,
so the game_id='gg' (len=2) leak cannot recur.

Run with:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_paper_ingame.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.ingame.paper_ingame import (
    CHANNEL_PAPER_INGAME,
    _MIN_GAME_ID_LEN,
    _is_malformed_input,
    record_ingame_bet,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _count_rows(ledger: Path) -> int:
    """Count JSONL rows written to the ledger file. Does NOT use load_ledger
    (which filters synthetic rows) so we can verify the raw on-disk state."""
    if not ledger.exists():
        return 0
    lines = [ln.strip() for ln in ledger.read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    return len(lines)


def _read_rows(ledger: Path):
    """Return all raw JSONL rows as dicts."""
    if not ledger.exists():
        return []
    out = []
    for ln in ledger.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
    return out


# ---------------------------------------------------------------------------
# _is_malformed_input unit tests
# ---------------------------------------------------------------------------

class TestIsMalformedInput:
    """Unit tests for the guard predicate itself."""

    def test_short_game_id_gg(self):
        """'gg' (len=2) is below _MIN_GAME_ID_LEN and must be flagged."""
        assert _is_malformed_input("nba", "gg") is True

    def test_short_game_id_single_char(self):
        assert _is_malformed_input("nba", "x") is True

    def test_short_game_id_empty(self):
        assert _is_malformed_input("nba", "") is True

    def test_boundary_exactly_min_len(self):
        """A game_id of exactly _MIN_GAME_ID_LEN chars is accepted."""
        gid = "a" * _MIN_GAME_ID_LEN
        assert _is_malformed_input("nba", gid) is False

    def test_real_nba_game_id(self):
        """Typical NBA game ID (9 chars) must pass."""
        assert _is_malformed_input("nba", "401859967") is False

    def test_synthetic_sport_test_prefix(self):
        """sport starting with 'test_' is flagged as synthetic."""
        assert _is_malformed_input("test_nba", "401859967") is True

    def test_synthetic_sport_exact_test_(self):
        assert _is_malformed_input("test_", "401859967") is True

    def test_valid_sport_with_underscore(self):
        """Sports like 'soccer_intl' or 'mlb' must NOT be rejected."""
        assert _is_malformed_input("soccer_intl", "401859967") is False
        assert _is_malformed_input("mlb", "401859967") is False


# ---------------------------------------------------------------------------
# record_ingame_bet write-guard integration tests
# ---------------------------------------------------------------------------

class TestRecordIngameBetWriteGuard:
    """Integration tests: verify raw on-disk row count after record_ingame_bet."""

    def test_malformed_game_id_gg_writes_zero_rows(self, tmp_path):
        """game_id='gg' (len=2) must be rejected; 0 rows written to ledger."""
        ledger = tmp_path / "test_ledger.jsonl"

        result = record_ingame_bet(
            sport="nba",
            game_id="gg",       # the exact malformed value from the bug
            market="win_home",
            side="home",
            taken_decimal=1.9,
            path=ledger,
        )

        # The function must not raise and must return a structured no-op.
        assert result["added_new"] is False, "malformed row must not be added"
        assert result["executed"] is False, "executed must always be False"
        assert result["channel"] == CHANNEL_PAPER_INGAME
        assert result.get("status") in ("rejected",), (
            "status should be 'rejected', got %r" % result.get("status")
        )
        # Most importantly: zero rows on disk.
        assert _count_rows(ledger) == 0, (
            "expected 0 rows for malformed game_id='gg', found %d" % _count_rows(ledger)
        )

    def test_malformed_empty_game_id_writes_zero_rows(self, tmp_path):
        """Empty game_id must also be rejected."""
        ledger = tmp_path / "test_ledger.jsonl"
        result = record_ingame_bet(
            sport="nba", game_id="", market="win_home",
            side="home", taken_decimal=1.9, path=ledger,
        )
        assert result["added_new"] is False
        assert _count_rows(ledger) == 0

    def test_synthetic_sport_writes_zero_rows(self, tmp_path):
        """sport='test_nba' must be rejected even with a valid game_id."""
        ledger = tmp_path / "test_ledger.jsonl"
        result = record_ingame_bet(
            sport="test_nba", game_id="401859967",
            market="win_home", side="home", taken_decimal=1.9, path=ledger,
        )
        assert result["added_new"] is False
        assert _count_rows(ledger) == 0

    def test_valid_9char_game_id_writes_exactly_one_row(self, tmp_path):
        """A proper 9-char game_id with valid inputs must produce exactly 1 row."""
        ledger = tmp_path / "test_ledger.jsonl"

        result = record_ingame_bet(
            sport="nba",
            game_id="401859967",    # real-format game ID
            market="win_home",
            side="home",
            taken_decimal=1.95,
            model_prob=0.54,
            stake=0.0,              # paper-only, never real money
            path=ledger,
        )

        assert result["added_new"] is True, "valid row must be written"
        assert result["executed"] is False, "executed must always be False"
        assert result["channel"] == CHANNEL_PAPER_INGAME
        # No dollar P&L field allowed.
        for banned in ("pnl", "profit", "dollar"):
            assert banned not in result, "dollar P&L field must not exist: %r" % banned

        rows = _read_rows(ledger)
        assert len(rows) == 1, "expected exactly 1 row, found %d" % len(rows)
        row = rows[0]
        assert row["game_id"] == "401859967"
        assert row["executed"] is False
        assert row["channel"] == CHANNEL_PAPER_INGAME
        assert "pnl" not in row

    def test_idempotency_second_call_same_key_writes_zero_extra_rows(self, tmp_path):
        """Second call with the same key must not add a duplicate row."""
        ledger = tmp_path / "test_ledger.jsonl"
        kwargs = dict(sport="nba", game_id="401859967", market="win_home",
                      side="home", taken_decimal=1.9, path=ledger)

        r1 = record_ingame_bet(**kwargs)
        r2 = record_ingame_bet(**kwargs)

        assert r1["added_new"] is True
        # r2 either finds the existing row (idempotency) or gets rejected because
        # the scan reads through load_ledger (which filters the row as having a
        # valid game_id; real row passes the guard, is already open -> False).
        assert r2["added_new"] is False
        assert _count_rows(ledger) == 1, (
            "expected exactly 1 row after duplicate call, found %d" % _count_rows(ledger)
        )

    def test_idempotency_holds_after_first_row_already_settled(self, tmp_path):
        """B2 sweep regression (2026-07-11): a same-day re-trigger of an edge
        whose FIRST row already settled must NOT append a duplicate open row.

        Root cause: _scan_existing (formerly _scan_open) only matched
        status=="open" rows, so once the original settled it was invisible to
        the idempotency scan and a second record_ingame_bet call appended a
        brand-new OPEN row under the identical edge_key -- a duplicate that
        the settle daemon's own dedup guard then ignores forever (it treats
        any edge_key with an existing settled twin as already done). Measured
        on the real ledger: 427/440 open paper_ingame rows were exactly this.
        """
        ledger = tmp_path / "test_ledger.jsonl"
        kwargs = dict(sport="mlb", game_id="KXMLBGAME-26JUL011310TEXCLE",
                      market="win_home", side="home", taken_decimal=1.9, path=ledger)

        r1 = record_ingame_bet(**kwargs)
        assert r1["added_new"] is True

        # Simulate the settle daemon: flip the row to settled in place (same
        # edge_key, same ts_date -- exactly what grade_live's append does).
        rows = _read_rows(ledger)
        rows[0]["status"] = "settled"
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        r2 = record_ingame_bet(**kwargs)
        assert r2["added_new"] is False, (
            "a same-day re-trigger after settlement must be a no-op, not a new open row")
        assert _count_rows(ledger) == 1, (
            "expected exactly 1 row (the settled twin), found %d" % _count_rows(ledger)
        )

    def test_valid_row_never_has_dollar_field(self, tmp_path):
        """Honesty: no dollar P&L field in any written row."""
        ledger = tmp_path / "test_ledger.jsonl"
        record_ingame_bet(
            sport="nba", game_id="401859967", market="win_home",
            side="home", taken_decimal=1.9, path=ledger,
        )
        for row in _read_rows(ledger):
            for banned in ("pnl", "profit", "dollar_edge"):
                assert banned not in row, "banned field %r found in row" % banned
            assert row.get("executed") is False

    def test_rejected_result_never_raises(self, tmp_path):
        """record_ingame_bet must never raise, even for the worst inputs."""
        ledger = tmp_path / "test_ledger.jsonl"
        # These would crash unguarded code; the function must absorb them silently.
        for bad_gid in ("gg", "", "x", "ab"):
            result = record_ingame_bet(
                sport="nba", game_id=bad_gid, market="m", side="home",
                taken_decimal=1.9, path=ledger,
            )
            assert isinstance(result, dict), "must return dict, not raise"
            assert result.get("executed") is False
