"""tests/test_line_validator.py - probe R17_J2 acceptance tests.

Covers the line-freshness validator that gates `scripts/place_bet.py`:

  1. Snapshot <= 2 min old AND exact (book, player, stat, line, odds) match -> VALID.
  2. Snapshot > 2 min old (no fresher row exists) -> INVALID, reason "stale".
  3. Line moved 3.5 -> 4.5 within fresh window -> INVALID, reason contains
     "line moved", snapshot surfaces the new line.
  4. Odds moved -110 -> -130 within fresh window (line unchanged) -> INVALID,
     reason contains "odds moved".
  5. Player absent from book entirely -> INVALID, reason contains "not found".
  6. --force-stale flag in place_bet.py bypasses validation and proceeds to
     ledger write.

All tests use a tmp_path lines_dir + an injected `now` clock, so no network
or wall-clock dependency.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta
from typing import List

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.line_validator import validate_bet_line   # noqa: E402


HEADER = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]


def _write_lines_csv(path, rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _row(captured_at, player, stat, line, over, under, book="pin",
         game_id="111", player_id="999") -> dict:
    return {
        "captured_at": captured_at,
        "book":        book,
        "game_id":     game_id,
        "player_id":   player_id,
        "player_name": player,
        "stat":        stat,
        "line":        line,
        "over_price":  over,
        "under_price": under,
        "start_time":  "2026-05-27T00:35:00Z",
    }


@pytest.fixture
def lines_dir(tmp_path):
    return tmp_path


# --------------------------------------------------------------------------- #
# 1. Fresh + exact match -> VALID                                              #
# --------------------------------------------------------------------------- #
def test_fresh_exact_match_is_valid(lines_dir):
    now = datetime(2026, 5, 26, 14, 0, 0)
    captured_at = (now - timedelta(seconds=30)).isoformat(timespec="seconds")
    _write_lines_csv(lines_dir / "2026-05-26_pin.csv", [
        _row(captured_at, "Keldon Johnson", "reb", 3.5, 157, -213),
    ])
    ok, reason, snap = validate_bet_line(
        book="pin", player_name="Keldon Johnson", stat="reb",
        line=3.5, side="OVER", odds=157,
        max_staleness_sec=120, lines_dir=str(lines_dir), now=now,
    )
    assert ok is True, f"expected VALID, got reason={reason!r}"
    assert "valid" in reason.lower()
    assert snap["age_sec"] is not None and snap["age_sec"] <= 120
    assert snap["line"] == 3.5
    assert snap["odds_current"] == 157


# --------------------------------------------------------------------------- #
# 2. Stale snapshot -> INVALID                                                 #
# --------------------------------------------------------------------------- #
def test_stale_snapshot_is_invalid(lines_dir):
    now = datetime(2026, 5, 26, 14, 0, 0)
    # Only row is 5 minutes old (>2 min staleness window).
    captured_at = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
    _write_lines_csv(lines_dir / "2026-05-26_pin.csv", [
        _row(captured_at, "Keldon Johnson", "reb", 3.5, 157, -213),
    ])
    ok, reason, snap = validate_bet_line(
        book="pin", player_name="Keldon Johnson", stat="reb",
        line=3.5, side="OVER", odds=157,
        max_staleness_sec=120, lines_dir=str(lines_dir), now=now,
    )
    assert ok is False
    assert "stale" in reason.lower()
    # The stale snapshot is still surfaced so the operator can see it.
    assert snap.get("age_sec", 0) > 120


# --------------------------------------------------------------------------- #
# 3. Line moved within fresh window -> INVALID, "line moved"                   #
# --------------------------------------------------------------------------- #
def test_line_moved_is_invalid(lines_dir):
    now = datetime(2026, 5, 26, 14, 0, 0)
    fresh_ts = (now - timedelta(seconds=20)).isoformat(timespec="seconds")
    # Live line is 4.5, but caller wants to place at 3.5.
    _write_lines_csv(lines_dir / "2026-05-26_pin.csv", [
        _row(fresh_ts, "Keldon Johnson", "reb", 4.5, 130, -180),
    ])
    ok, reason, snap = validate_bet_line(
        book="pin", player_name="Keldon Johnson", stat="reb",
        line=3.5, side="OVER", odds=157,
        max_staleness_sec=120, lines_dir=str(lines_dir), now=now,
    )
    assert ok is False
    assert "line moved" in reason.lower()
    # Surface the new line in the snapshot.
    assert snap["line"] == 4.5
    # And the captured_at reflects the live row.
    assert snap["captured_at"] == fresh_ts


# --------------------------------------------------------------------------- #
# 4. Odds moved within fresh window (line same) -> INVALID, "odds moved"       #
# --------------------------------------------------------------------------- #
def test_odds_moved_is_invalid(lines_dir):
    now = datetime(2026, 5, 26, 14, 0, 0)
    fresh_ts = (now - timedelta(seconds=10)).isoformat(timespec="seconds")
    # Same line, but over_price moved from -110 (placement) to -130 (live).
    _write_lines_csv(lines_dir / "2026-05-26_pin.csv", [
        _row(fresh_ts, "Stephon Castle", "ast", 6.5, -130, -110),
    ])
    ok, reason, snap = validate_bet_line(
        book="pin", player_name="Stephon Castle", stat="ast",
        line=6.5, side="OVER", odds=-110,
        max_staleness_sec=120, lines_dir=str(lines_dir), now=now,
    )
    assert ok is False
    assert "odds moved" in reason.lower()
    assert snap["odds_current"] == -130


# --------------------------------------------------------------------------- #
# 5. Player not in book -> INVALID, "not found"                                #
# --------------------------------------------------------------------------- #
def test_player_not_in_book_is_invalid(lines_dir):
    now = datetime(2026, 5, 26, 14, 0, 0)
    fresh_ts = (now - timedelta(seconds=15)).isoformat(timespec="seconds")
    # Book has Keldon but caller asks about Wemby.
    _write_lines_csv(lines_dir / "2026-05-26_pin.csv", [
        _row(fresh_ts, "Keldon Johnson", "reb", 3.5, 157, -213),
    ])
    ok, reason, snap = validate_bet_line(
        book="pin", player_name="Victor Wembanyama", stat="reb",
        line=13.5, side="OVER", odds=104,
        max_staleness_sec=120, lines_dir=str(lines_dir), now=now,
    )
    assert ok is False
    assert "not found" in reason.lower()
    # Nothing matched, so the snapshot is empty.
    assert snap == {}


# --------------------------------------------------------------------------- #
# 6. --force-stale bypass in place_bet.py                                      #
# --------------------------------------------------------------------------- #
def test_force_stale_flag_bypasses_validation(tmp_path, monkeypatch):
    """End-to-end: --force-stale lets a placement land even though the
    validator would otherwise reject (stale snapshot)."""
    # Redirect ledger storage into tmp_path.
    ledger = tmp_path / "pnl_ledger.csv"
    bankroll = tmp_path / "pnl_bankroll.csv"
    from src.betting import pnl_ledger as _pl
    monkeypatch.setattr(_pl, "LEDGER_CSV",   str(ledger))
    monkeypatch.setattr(_pl, "BANKROLL_CSV", str(bankroll))
    monkeypatch.setattr(_pl, "LOCK_PATH",    str(ledger) + ".lock")
    import scripts.place_bet as pb
    monkeypatch.setattr(pb, "LEDGER_CSV", str(ledger))

    # Lines dir is empty -> the validator would normally fail with
    # "no snapshots". --force-stale should bypass that.
    empty_lines = tmp_path / "empty_lines"
    empty_lines.mkdir()

    rc = pb.main([
        "--player", "Keldon Johnson",
        "--stat",   "reb",
        "--side",   "OVER",
        "--line",   "3.5",
        "--book",   "pin",
        "--odds",   "157",
        "--stake",  "10",
        "--bankroll", "1000",
        "--no-slate-validate",
        "--force-stale",
        "--lines-dir", str(empty_lines),
    ])
    assert rc == 0, "expected --force-stale to skip validator and place bet"
    # Ledger row written.
    assert ledger.exists()
    with open(ledger, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["player"] == "Keldon Johnson"
    assert float(rows[0]["stake"]) == 10.0


# --------------------------------------------------------------------------- #
# 7. End-to-end: without --force-stale, place_bet aborts on missing snapshot.  #
# --------------------------------------------------------------------------- #
def test_place_bet_aborts_when_validator_rejects(tmp_path, monkeypatch, capsys):
    """Without --force-stale, an absent/stale line causes a non-zero exit
    and NOTHING is written to the ledger."""
    ledger = tmp_path / "pnl_ledger.csv"
    bankroll = tmp_path / "pnl_bankroll.csv"
    from src.betting import pnl_ledger as _pl
    monkeypatch.setattr(_pl, "LEDGER_CSV",   str(ledger))
    monkeypatch.setattr(_pl, "BANKROLL_CSV", str(bankroll))
    monkeypatch.setattr(_pl, "LOCK_PATH",    str(ledger) + ".lock")
    import scripts.place_bet as pb
    monkeypatch.setattr(pb, "LEDGER_CSV", str(ledger))

    empty_lines = tmp_path / "empty_lines"
    empty_lines.mkdir()

    rc = pb.main([
        "--player", "Keldon Johnson",
        "--stat",   "reb",
        "--side",   "OVER",
        "--line",   "3.5",
        "--book",   "pin",
        "--odds",   "157",
        "--stake",  "10",
        "--bankroll", "1000",
        "--no-slate-validate",
        "--lines-dir", str(empty_lines),
    ])
    assert rc != 0, "expected non-zero exit when validator rejects"
    out = capsys.readouterr().out
    assert "line-validator" in out
    # Ledger NOT written.
    assert not ledger.exists() or len(list(csv.DictReader(open(ledger)))) == 0
