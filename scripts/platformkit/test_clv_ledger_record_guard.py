"""Per-file tests for scripts.platformkit.clv_ledger_record_guard.

Acceptance criteria (QA-CLV-RECORD-DEDUP workstream spec):
  * record twice same row -> exactly 1 ledger line; second returns appended=False.
  * distinct bet_id -> appended=True, row appears in ledger.
  * strips any $ / banned key before append; banned key never reaches the file.
  * missing file -> creates then appends (appended=True, file now exists).
  * never overwrites existing lines (append-only: prior rows still present).
  * record_settlement_guarded: dup settlement -> no-op; new settlement -> appended.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_clv_ledger_record_guard.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.clv_ledger import bet_id
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS
from scripts.platformkit.clv_ledger_record_guard import (
    record_bet_guarded,
    record_settlement_guarded,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _read_ledger(path: Path) -> List[Dict[str, Any]]:
    """Read all JSONL rows from a ledger file."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _make_kwargs(
    sport: str = "nba",
    matchup: str = "TeamA @ TeamB",
    side: str = "home",
    taken_book: str = "FanDuel",
    taken_decimal: float = 2.10,
    game_date: str = "2026-06-19",
    **extra,
) -> Dict[str, Any]:
    """Return a minimal valid kwarg dict for record_bet_guarded."""
    kw = dict(
        sport=sport,
        matchup=matchup,
        side=side,
        taken_book=taken_book,
        taken_decimal=taken_decimal,
        model_prob=0.52,
        stake_units=1.0,
        game_date=game_date,
    )
    kw.update(extra)
    return kw


# ---------------------------------------------------------------------------
# Primary acceptance tests
# ---------------------------------------------------------------------------

class TestRecordBetGuarded:

    def test_new_bet_appended_true(self, tmp_path: Path):
        """A new bet returns appended=True and appears in the ledger."""
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs()

        result = record_bet_guarded(**kw, path=ledger)

        assert result["appended"] is True
        assert result["record"] is not None
        rows = _read_ledger(ledger)
        assert len(rows) == 1

    def test_duplicate_bet_id_is_noop_appended_false(self, tmp_path: Path):
        """Recording same bet twice -> second call returns appended=False, 1 row only."""
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs()

        first = record_bet_guarded(**kw, path=ledger)
        second = record_bet_guarded(**kw, path=ledger)

        assert first["appended"] is True
        assert second["appended"] is False
        assert second["record"] is None
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "duplicate write produced extra ledger line"

    def test_distinct_bet_ids_both_written(self, tmp_path: Path):
        """Two bets with different matchups get distinct bet_ids and both are written."""
        ledger = tmp_path / "clv_ledger.jsonl"

        r1 = record_bet_guarded(**_make_kwargs(matchup="GSW @ BOS"), path=ledger)
        r2 = record_bet_guarded(**_make_kwargs(matchup="LAL @ MIA"), path=ledger)

        assert r1["appended"] is True
        assert r2["appended"] is True
        rows = _read_ledger(ledger)
        assert len(rows) == 2

    def test_strips_dollar_key_before_append(self, tmp_path: Path):
        """Banned $ key passed in a row must be stripped; never reaches the file."""
        ledger = tmp_path / "clv_ledger.jsonl"
        # We can't pass pnl via record_bet_guarded signature but the guard's
        # internal row construction + _strip_dollar_keys ensures belt-and-suspenders.
        # Verify by injecting via a minimally crafted call (covers the strip path).
        from scripts.platformkit.clv_ledger_record_guard import _strip_dollar_keys

        dirty_row: Dict[str, Any] = {
            "sport": "nba", "matchup": "A @ B", "side": "home",
            "taken_book": "FD", "taken_decimal": 2.0,
            "stake_units": 1.0, "status": "open", "executed": False,
            "pnl": 99.99, "bankroll": 500.0,
            "bet_id": bet_id({"sport": "nba", "matchup": "A @ B",
                              "side": "home", "taken_book": "FD"}),
        }
        clean = _strip_dollar_keys(dirty_row)
        for k in BANNED_KEYS:
            assert k not in clean, "BANNED key %r survived _strip_dollar_keys" % k
        assert "stake_units" in clean  # units field preserved
        assert "bet_id" in clean

    def test_dollar_key_not_in_written_row(self, tmp_path: Path):
        """After a guarded write, no banned key appears in the stored row."""
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs()

        result = record_bet_guarded(**kw, path=ledger)

        assert result["appended"] is True
        row = _read_ledger(ledger)[0]
        for k in BANNED_KEYS:
            assert k not in row, "banned key %r found in ledger row" % k

    def test_missing_file_creates_then_appends(self, tmp_path: Path):
        """When the ledger file does not exist, the guard creates it and appends."""
        ledger = tmp_path / "sub" / "nested" / "clv_ledger.jsonl"
        assert not ledger.exists()

        result = record_bet_guarded(**_make_kwargs(), path=ledger)

        assert result["appended"] is True
        assert ledger.exists(), "guard did not create the ledger file"
        rows = _read_ledger(ledger)
        assert len(rows) == 1

    def test_append_only_prior_rows_untouched(self, tmp_path: Path):
        """Adding a new bet must never disturb previously written rows."""
        ledger = tmp_path / "clv_ledger.jsonl"

        r1 = record_bet_guarded(**_make_kwargs(matchup="A @ B"), path=ledger)
        r2 = record_bet_guarded(**_make_kwargs(matchup="C @ D"), path=ledger)

        assert r1["appended"] is True
        assert r2["appended"] is True
        rows = _read_ledger(ledger)
        assert len(rows) == 2
        # First row still intact.
        assert rows[0]["matchup"] == "A @ B"
        assert rows[1]["matchup"] == "C @ D"

    def test_returns_bet_id_on_dup(self, tmp_path: Path):
        """On a duplicate the returned bet_id matches the original."""
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs()

        first = record_bet_guarded(**kw, path=ledger)
        second = record_bet_guarded(**kw, path=ledger)

        assert second["bet_id"] == first["bet_id"]

    def test_stake_units_preserved(self, tmp_path: Path):
        """stake_units survives the guard write unmodified."""
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs()
        kw["stake_units"] = 3.5

        record_bet_guarded(**kw, path=ledger)

        row = _read_ledger(ledger)[0]
        assert row["stake_units"] == 3.5

    def test_eight_concurrent_style_dup_writes_one_row(self, tmp_path: Path):
        """Simulates 8 duplicate writes (e.g. concurrent tick double-write).

        All 8 calls carry the same logical bet_id. Only 1 row must appear in
        the ledger; the remaining 7 must return appended=False.
        """
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs(matchup="NYK @ SAS", game_date="2026-06-19")

        results = [record_bet_guarded(**kw, path=ledger) for _ in range(8)]

        written = [r for r in results if r["appended"] is True]
        skipped = [r for r in results if r["appended"] is False]
        assert len(written) == 1, "expected exactly 1 write, got %d" % len(written)
        assert len(skipped) == 7
        rows = _read_ledger(ledger)
        assert len(rows) == 1, "expected 1 ledger line, got %d" % len(rows)

    def test_executed_field_is_false(self, tmp_path: Path):
        """Honesty invariant: executed must be False (guard never places real bet)."""
        ledger = tmp_path / "clv_ledger.jsonl"
        record_bet_guarded(**_make_kwargs(), path=ledger)
        row = _read_ledger(ledger)[0]
        assert row["executed"] is False

    def test_market_kwarg_included_in_bet_id(self, tmp_path: Path):
        """market kwarg is included in the bet_id so different markets are distinct."""
        ledger = tmp_path / "clv_ledger.jsonl"

        r1 = record_bet_guarded(
            **_make_kwargs(matchup="A @ B"), market="moneyline", path=ledger
        )
        r2 = record_bet_guarded(
            **_make_kwargs(matchup="A @ B"), market="spread", path=ledger
        )

        assert r1["appended"] is True
        assert r2["appended"] is True
        assert r1["bet_id"] != r2["bet_id"]
        assert len(_read_ledger(ledger)) == 2

    def test_dup_different_timestamp_still_noop(self, tmp_path: Path):
        """Same logical bet with a different write timestamp must still be a no-op."""
        ledger = tmp_path / "clv_ledger.jsonl"
        kw = _make_kwargs(matchup="A @ B", game_date="2026-06-19")

        # First write at T1.
        r1 = record_bet_guarded(**kw, path=ledger)
        # Second write at T2 (would happen if a concurrent tick re-fires).
        import time as _time
        _time.sleep(0.001)  # ensure ts differs
        r2 = record_bet_guarded(**kw, path=ledger)

        assert r1["appended"] is True
        assert r2["appended"] is False
        assert len(_read_ledger(ledger)) == 1


# ---------------------------------------------------------------------------
# Settlement guard tests
# ---------------------------------------------------------------------------

class TestRecordSettlementGuarded:

    def _make_settled(self, matchup: str = "GSW @ BOS") -> Dict[str, Any]:
        base = {
            "ts": "2026-06-19T22:00:00+00:00",
            "sport": "nba",
            "matchup": matchup,
            "side": "home",
            "taken_book": "DraftKings",
            "taken_decimal": 1.95,
            "stake_units": 1.0,
            "status": "settled",
            "executed": False,
            "game_date": "2026-06-19",
            "clv_pct": 1.23,
            "beat_close": True,
        }
        base["bet_id"] = bet_id(base)
        return base

    def test_new_settlement_appended(self, tmp_path: Path):
        ledger = tmp_path / "clv_ledger.jsonl"
        settled = self._make_settled()

        result = record_settlement_guarded(settled, path=ledger)

        assert result["appended"] is True
        rows = _read_ledger(ledger)
        assert len(rows) == 1

    def test_duplicate_settlement_is_noop(self, tmp_path: Path):
        """Recording the same settlement twice -> second is a no-op."""
        ledger = tmp_path / "clv_ledger.jsonl"
        settled = self._make_settled()

        first = record_settlement_guarded(settled, path=ledger)
        second = record_settlement_guarded(settled, path=ledger)

        assert first["appended"] is True
        assert second["appended"] is False
        rows = _read_ledger(ledger)
        assert len(rows) == 1

    def test_settlement_strips_dollar_keys(self, tmp_path: Path):
        """Banned $ keys in the settled row are stripped before writing."""
        ledger = tmp_path / "clv_ledger.jsonl"
        settled = self._make_settled()
        settled["pnl"] = 42.0
        settled["bankroll"] = 1000.0

        record_settlement_guarded(settled, path=ledger)

        row = _read_ledger(ledger)[0]
        for k in BANNED_KEYS:
            assert k not in row, "banned key %r in settlement row" % k

    def test_distinct_settlements_both_written(self, tmp_path: Path):
        """Two settlements for different matchups both reach the ledger."""
        ledger = tmp_path / "clv_ledger.jsonl"

        r1 = record_settlement_guarded(self._make_settled("GSW @ BOS"), path=ledger)
        r2 = record_settlement_guarded(self._make_settled("LAL @ MIA"), path=ledger)

        assert r1["appended"] is True
        assert r2["appended"] is True
        assert len(_read_ledger(ledger)) == 2
