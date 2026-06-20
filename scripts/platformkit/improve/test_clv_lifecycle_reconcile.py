"""Per-file test: scripts.platformkit.improve.clv_lifecycle_reconcile.

Acceptance matrix (per workstream spec BE-R4-8):
  A. All opens settled cleanly -> drift=0, clean=True
  B. One open never settled   -> unsettled_open=1, clean still True
  C. One settled with no open -> settled_orphans=1, clean=False
  D. Empty ledger             -> clean=True (no rows, no drift)
  E. Missing ledger file      -> INSUFFICIENT_DATA, clean=False
  F. No $ / roi / pnl field anywhere in output
  G. Read-only: function never writes to the ledger file

Run with:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_clv_lifecycle_reconcile.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.platformkit.improve.clv_lifecycle_reconcile import (
    reconcile_clv_lifecycle,
    CALIBRATION_NOTE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


def _write_ledger(tmp_path: Path, rows: list) -> Path:
    ledger = tmp_path / "clv_ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return ledger


def _assert_no_banned(obj):
    """Recursively assert no banned key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert not _BANNED_KEY_RE.search(str(k)), "Banned key: %r" % k
            _assert_no_banned(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_no_banned(item)


# ---------------------------------------------------------------------------
# Fixtures -- minimal ledger rows
# ---------------------------------------------------------------------------

def _open_row_gen1(matchup="NYK@SAS", sport="nba", side="home",
                   taken_decimal=2.0, ts="2026-06-20T10:00:00+00:00"):
    """Generation-1 open row (no bet_id, no market field)."""
    return {
        "ts": ts,
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_book": "espn:DraftKings",
        "taken_decimal": taken_decimal,
        "model_prob": 0.55,
        "stake_units": 1.0,
        "status": "open",
        "executed": False,
    }


def _settled_row_gen1(open_row, clv_pct=1.5):
    """Generation-1 settled twin -- settle_key mirrors the open row's fields."""
    sk = "|".join([
        str(open_row["sport"]),
        str(open_row["matchup"]),
        str(open_row["side"]),
        str(open_row["taken_book"]),
        str(open_row["taken_decimal"]),
        str(open_row["ts"]),
    ])
    settled = dict(open_row)
    settled["status"] = "settled"
    settled["settled_at"] = "2026-06-20T22:00:00+00:00"
    settled["clv_pct"] = clv_pct
    settled["beat_close"] = clv_pct > 0
    settled["settle_key"] = sk
    return settled


def _open_row_gen2(matchup="CHW@DET", sport="mlb", side="away",
                   game_date="2026-06-20", ts="2026-06-20T12:00:00+00:00"):
    """Generation-2 open row (has bet_id and market field)."""
    row = {
        "ts": ts,
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_book": "espn:DraftKings",
        "taken_decimal": 2.1,
        "model_prob": 0.48,
        "stake_units": 1.0,
        "status": "open",
        "executed": False,
        "market": "moneyline",
        "game_date": game_date,
    }
    # Derive bet_id the same way clv_ledger.bet_id() does
    anchor = matchup
    market = "moneyline"
    book = "espn:DraftKings"
    row["bet_id"] = "|".join([sport, anchor, market, side, book, game_date])
    return row


def _settled_row_gen2(open_row, clv_pct=2.0):
    """Generation-2 settled twin -- settle_key == bet_id of open row."""
    settled = dict(open_row)
    settled["status"] = "settled"
    settled["settled_at"] = "2026-06-20T23:00:00+00:00"
    settled["clv_pct"] = clv_pct
    settled["beat_close"] = clv_pct > 0
    settled["settle_key"] = open_row["bet_id"]  # gen2: settle_key = bet_id
    return settled


# ---------------------------------------------------------------------------
# Test A: all opens settled cleanly -> clean=True, drift=0
# ---------------------------------------------------------------------------

class TestAllSettledClean:
    """Acceptance A: clean ledger with matched open/settled pairs."""

    def test_gen1_clean(self, tmp_path):
        o = _open_row_gen1()
        s = _settled_row_gen1(o)
        path = _write_ledger(tmp_path, [o, s])
        result = reconcile_clv_lifecycle(path=path)
        assert result["clean"] is True, result
        assert result["status"] == "clean"
        assert result["settled_orphans"] == 0
        assert result["n_open"] == 1
        assert result["n_settled"] == 1
        _assert_no_banned(result)

    def test_gen2_clean(self, tmp_path):
        o = _open_row_gen2()
        s = _settled_row_gen2(o)
        path = _write_ledger(tmp_path, [o, s])
        result = reconcile_clv_lifecycle(path=path)
        assert result["clean"] is True, result
        assert result["status"] == "clean"
        assert result["settled_orphans"] == 0
        _assert_no_banned(result)

    def test_mixed_generations_clean(self, tmp_path):
        o1 = _open_row_gen1(matchup="NYK@SAS", sport="nba")
        s1 = _settled_row_gen1(o1)
        o2 = _open_row_gen2(matchup="CHW@DET", sport="mlb")
        s2 = _settled_row_gen2(o2)
        path = _write_ledger(tmp_path, [o1, s1, o2, s2])
        result = reconcile_clv_lifecycle(path=path)
        assert result["clean"] is True, result
        assert result["settled_orphans"] == 0
        assert result["n_open"] == 2
        assert result["n_settled"] == 2
        _assert_no_banned(result)

    def test_clean_note_present(self, tmp_path):
        o = _open_row_gen1()
        s = _settled_row_gen1(o)
        path = _write_ledger(tmp_path, [o, s])
        result = reconcile_clv_lifecycle(path=path)
        assert result["note"] == CALIBRATION_NOTE


# ---------------------------------------------------------------------------
# Test B: one open never settled -> unsettled_open=1, clean still True
# ---------------------------------------------------------------------------

class TestUnsettledOpen:
    """Acceptance B: open row with no settled twin is informational only."""

    def test_one_unsettled_open_still_clean(self, tmp_path):
        o = _open_row_gen1(matchup="LAL@GSW", ts="2026-06-20T08:00:00+00:00")
        # No settled twin written
        path = _write_ledger(tmp_path, [o])
        result = reconcile_clv_lifecycle(path=path)
        # unsettled open is NOT an error -- bet may not be graded yet
        assert result["unsettled_open"] == 1
        assert result["clean"] is True, (
            "unsettled open alone must not make clean=False; result=%r" % result
        )
        assert result["status"] == "clean"
        assert result["settled_orphans"] == 0
        _assert_no_banned(result)

    def test_unsettled_detail_present(self, tmp_path):
        o = _open_row_gen1(matchup="BOS@MIA", sport="nba")
        path = _write_ledger(tmp_path, [o])
        result = reconcile_clv_lifecycle(path=path)
        assert result["unsettled_open"] == 1
        assert len(result["unsettled_details"]) == 1
        detail = result["unsettled_details"][0]
        assert detail["matchup"] == "BOS@MIA"
        assert detail["sport"] == "nba"
        _assert_no_banned(result)

    def test_two_opens_one_settled_one_not(self, tmp_path):
        o1 = _open_row_gen1(matchup="NYK@SAS", ts="2026-06-20T10:00:00+00:00")
        s1 = _settled_row_gen1(o1)
        o2 = _open_row_gen1(matchup="BOS@MIA", ts="2026-06-20T11:00:00+00:00")
        # o2 has no settled twin
        path = _write_ledger(tmp_path, [o1, s1, o2])
        result = reconcile_clv_lifecycle(path=path)
        assert result["unsettled_open"] == 1
        assert result["settled_orphans"] == 0
        assert result["clean"] is True
        _assert_no_banned(result)


# ---------------------------------------------------------------------------
# Test C: one settled with no open -> settled_orphans=1, clean=False
# ---------------------------------------------------------------------------

class TestSettledOrphan:
    """Acceptance C: settled row with no matching open row is a drift signal."""

    def test_orphan_settled_sets_clean_false(self, tmp_path):
        # Write a settled row that has NO corresponding open row in the ledger
        orphan_settled = {
            "ts": "2026-06-19T18:00:00+00:00",
            "sport": "nba",
            "matchup": "DEN@OKC",
            "side": "home",
            "taken_book": "espn:FanDuel",
            "taken_decimal": 1.95,
            "model_prob": 0.53,
            "stake_units": 1.0,
            "status": "settled",
            "executed": False,
            "settled_at": "2026-06-19T23:00:00+00:00",
            "clv_pct": -0.5,
            "beat_close": False,
            "settle_key": "nba|DEN@OKC|home|espn:FanDuel|1.95|2026-06-19T18:00:00+00:00",
        }
        path = _write_ledger(tmp_path, [orphan_settled])
        result = reconcile_clv_lifecycle(path=path)
        assert result["settled_orphans"] == 1, result
        assert result["clean"] is False
        assert result["status"] == "drift"
        _assert_no_banned(result)

    def test_orphan_detail_present(self, tmp_path):
        orphan_settled = {
            "ts": "2026-06-19T18:00:00+00:00",
            "sport": "nba",
            "matchup": "DEN@OKC",
            "side": "home",
            "taken_book": "espn:FanDuel",
            "taken_decimal": 1.95,
            "model_prob": 0.53,
            "stake_units": 1.0,
            "status": "settled",
            "executed": False,
            "settled_at": "2026-06-19T23:00:00+00:00",
            "clv_pct": -0.5,
            "beat_close": False,
            "settle_key": "nba|DEN@OKC|home|espn:FanDuel|1.95|2026-06-19T18:00:00+00:00",
        }
        path = _write_ledger(tmp_path, [orphan_settled])
        result = reconcile_clv_lifecycle(path=path)
        assert len(result["orphan_details"]) == 1
        detail = result["orphan_details"][0]
        assert detail["matchup"] == "DEN@OKC"
        assert detail["sport"] == "nba"
        _assert_no_banned(result)

    def test_one_clean_pair_plus_one_orphan(self, tmp_path):
        o = _open_row_gen1(matchup="NYK@SAS")
        s = _settled_row_gen1(o)
        # Inject an orphan settled (no matching open)
        orphan = {
            "ts": "2026-06-18T10:00:00+00:00",
            "sport": "mlb",
            "matchup": "ATL@NYM",
            "side": "away",
            "taken_book": "espn:DraftKings",
            "taken_decimal": 2.3,
            "model_prob": 0.44,
            "stake_units": 1.0,
            "status": "settled",
            "executed": False,
            "settled_at": "2026-06-18T22:00:00+00:00",
            "clv_pct": 3.1,
            "beat_close": True,
            "settle_key": "mlb|ATL@NYM|away|espn:DraftKings|2.3|2026-06-18T10:00:00+00:00",
        }
        path = _write_ledger(tmp_path, [o, s, orphan])
        result = reconcile_clv_lifecycle(path=path)
        assert result["settled_orphans"] == 1
        assert result["clean"] is False
        _assert_no_banned(result)

    def test_gen2_orphan(self, tmp_path):
        """A gen2 settled row whose bet_id matches no open row is an orphan."""
        orphan_settled = {
            "ts": "2026-06-20T12:00:00+00:00",
            "sport": "mlb",
            "matchup": "CIN@NYY",
            "side": "away",
            "taken_book": "espn:DraftKings",
            "taken_decimal": 2.5,
            "model_prob": 0.40,
            "stake_units": 1.0,
            "status": "settled",
            "executed": False,
            "market": "moneyline",
            "game_date": "2026-06-20",
            "bet_id": "mlb|CIN@NYY|moneyline|away|espn:DraftKings|2026-06-20",
            "settled_at": "2026-06-20T23:00:00+00:00",
            "clv_pct": 0.8,
            "beat_close": True,
            # settle_key = bet_id (gen2 format)
            "settle_key": "mlb|CIN@NYY|moneyline|away|espn:DraftKings|2026-06-20",
        }
        path = _write_ledger(tmp_path, [orphan_settled])
        result = reconcile_clv_lifecycle(path=path)
        assert result["settled_orphans"] == 1
        assert result["clean"] is False
        _assert_no_banned(result)


# ---------------------------------------------------------------------------
# Test D: empty ledger -> clean=True
# ---------------------------------------------------------------------------

class TestEmptyLedger:
    """Acceptance D: empty ledger is clean by definition."""

    def test_empty_file(self, tmp_path):
        path = tmp_path / "clv_ledger.jsonl"
        path.write_text("", encoding="utf-8")
        result = reconcile_clv_lifecycle(path=path)
        assert result["clean"] is True
        assert result["status"] == "clean"
        assert result["n_open"] == 0
        assert result["n_settled"] == 0
        assert result["unsettled_open"] == 0
        assert result["settled_orphans"] == 0
        _assert_no_banned(result)

    def test_blank_lines_only(self, tmp_path):
        path = tmp_path / "clv_ledger.jsonl"
        path.write_text("\n\n\n", encoding="utf-8")
        result = reconcile_clv_lifecycle(path=path)
        assert result["clean"] is True
        assert result["status"] == "clean"
        _assert_no_banned(result)


# ---------------------------------------------------------------------------
# Test E: missing ledger file -> INSUFFICIENT_DATA, clean=False
# ---------------------------------------------------------------------------

class TestMissingFile:
    """Acceptance E: missing ledger -> honest INSUFFICIENT_DATA."""

    def test_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent_clv.jsonl"
        result = reconcile_clv_lifecycle(path=path)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clean"] is False
        _assert_no_banned(result)

    def test_missing_file_has_reason(self, tmp_path):
        path = tmp_path / "nonexistent_clv.jsonl"
        result = reconcile_clv_lifecycle(path=path)
        assert "reason" in result
        assert str(result["reason"])  # non-empty


# ---------------------------------------------------------------------------
# Test F: no $ / roi / pnl / profit key in any output
# ---------------------------------------------------------------------------

class TestNoBannedKeys:
    """Acceptance F: no banned key in any output shape."""

    def test_clean_output_no_banned(self, tmp_path):
        o = _open_row_gen1()
        s = _settled_row_gen1(o)
        path = _write_ledger(tmp_path, [o, s])
        result = reconcile_clv_lifecycle(path=path)
        _assert_no_banned(result)

    def test_drift_output_no_banned(self, tmp_path):
        orphan = {
            "ts": "2026-06-19T18:00:00+00:00",
            "sport": "tennis",
            "matchup": "Djokovic vs Alcaraz",
            "side": "home",
            "taken_book": "espn:BetMGM",
            "taken_decimal": 1.8,
            "model_prob": 0.60,
            "stake_units": 1.0,
            "status": "settled",
            "executed": False,
            "settled_at": "2026-06-19T21:00:00+00:00",
            "clv_pct": 1.2,
            "beat_close": True,
            "settle_key": "tennis|Djokovic vs Alcaraz|home|espn:BetMGM|1.8|2026-06-19T18:00:00+00:00",
        }
        path = _write_ledger(tmp_path, [orphan])
        result = reconcile_clv_lifecycle(path=path)
        _assert_no_banned(result)

    def test_insufficient_data_no_banned(self, tmp_path):
        path = tmp_path / "no_file.jsonl"
        result = reconcile_clv_lifecycle(path=path)
        _assert_no_banned(result)


# ---------------------------------------------------------------------------
# Test G: read-only (function does not write to the ledger)
# ---------------------------------------------------------------------------

class TestReadOnly:
    """Acceptance G: reconcile_clv_lifecycle never mutates the ledger file."""

    def test_file_size_unchanged(self, tmp_path):
        o = _open_row_gen1()
        path = _write_ledger(tmp_path, [o])
        size_before = path.stat().st_size
        mtime_before = path.stat().st_mtime
        reconcile_clv_lifecycle(path=path)
        assert path.stat().st_size == size_before, "File size changed -- wrote to ledger"
        assert path.stat().st_mtime == mtime_before, "mtime changed -- wrote to ledger"

    def test_no_new_files_created(self, tmp_path):
        o = _open_row_gen1()
        path = _write_ledger(tmp_path, [o])
        files_before = set(tmp_path.iterdir())
        reconcile_clv_lifecycle(path=path)
        files_after = set(tmp_path.iterdir())
        # Allow a .lock sidecar from IO layer; no new .jsonl files
        new_jsonl = [f for f in (files_after - files_before) if f.suffix == ".jsonl"]
        assert not new_jsonl, "New JSONL file(s) created: %r" % new_jsonl


# ---------------------------------------------------------------------------
# Integration smoke: run against the real local ledger (skip if absent)
# ---------------------------------------------------------------------------

class TestRealLedgerSmoke:
    """Non-blocking smoke test against the real local ledger if it exists."""

    def test_real_ledger_runs_without_crash(self):
        """Runs reconcile on the real ledger; only validates output shape."""
        from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
        if not DEFAULT_LEDGER.exists():
            pytest.skip("Real ledger not present; skipping smoke test")
        result = reconcile_clv_lifecycle()
        # Shape checks
        assert "status" in result
        assert result["status"] in ("clean", "drift", "INSUFFICIENT_DATA")
        assert isinstance(result["clean"], bool)
        assert isinstance(result["n_open"], int)
        assert isinstance(result["n_settled"], int)
        assert isinstance(result["unsettled_open"], int)
        assert isinstance(result["settled_orphans"], int)
        assert isinstance(result["orphan_details"], list)
        assert isinstance(result["unsettled_details"], list)
        _assert_no_banned(result)
