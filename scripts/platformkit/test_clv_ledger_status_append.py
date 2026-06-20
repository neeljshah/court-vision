"""Per-file tests for scripts.platformkit.clv_ledger_status_append.

BE-R4-2 acceptance criteria (all must pass):
  1. open row then settled row (same bet_id) -> both written (2 rows).
  2. Same open row twice                     -> 2nd skipped (returns False).
  3. Dollar-key record stripped before write (banned key absent from file).
  4. Never raises (missing file, bad record, None path).
  5. _seen set fast-path matches re-scan path (consistent key encoding).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_status_append.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.clv_ledger import bet_id as _bet_id
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS
from scripts.platformkit.clv_ledger_status_append import append_if_new_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(
    sport: str = "nba",
    matchup: str = "Lakers @ Celtics",
    side: str = "home",
    book: str = "FanDuel",
    game_date: str = "2026-06-19",
    idx: int = 0,
    status: str = "open",
    **extra: Any,
) -> Dict[str, Any]:
    """Build a minimal UNITS-only ledger row (no dollar keys)."""
    base: Dict[str, Any] = {
        "ts": "2026-06-19T10:00:%02d.000000+00:00" % idx,
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_book": book,
        "taken_decimal": 2.10,
        "model_prob": 0.52,
        "stake_units": 1.0,
        "status": status,
        "executed": False,
        "game_date": game_date,
    }
    base["bet_id"] = _bet_id({
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_book": book,
        "game_date": game_date,
    })
    base.update(extra)
    return base


def _read_ledger(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _write_ledger(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


# ---------------------------------------------------------------------------
# BE-R4-2 Criterion 1: open then settled -> both written (2 rows)
# ---------------------------------------------------------------------------

class TestOpenThenSettled:

    def test_open_row_is_written(self, tmp_path: Path):
        """First write of an open row returns True and creates the ledger."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")

        result = append_if_new_status(open_row, ledger)

        assert result is True
        rows = _read_ledger(ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "open"

    def test_settled_row_written_after_open_same_bet_id(self, tmp_path: Path):
        """Settled twin (same bet_id) is appended even though open row exists."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open", idx=0)
        # Settled twin shares the same bet_id but has status="settled".
        settled_row = dict(open_row)
        settled_row["status"] = "settled"
        settled_row["ts"] = "2026-06-19T22:00:00.000000+00:00"
        settled_row["clv_pct"] = 2.5
        settled_row["beat_close"] = True

        assert open_row["bet_id"] == settled_row["bet_id"], (
            "test setup: open and settled must share the same bet_id"
        )

        r1 = append_if_new_status(open_row, ledger)
        r2 = append_if_new_status(settled_row, ledger)

        assert r1 is True, "open row must be written (first append)"
        assert r2 is True, "settled twin must be written (different status)"
        rows = _read_ledger(ledger)
        assert len(rows) == 2, "expected 2 rows; got %d" % len(rows)
        statuses = [r["status"] for r in rows]
        assert "open" in statuses
        assert "settled" in statuses

    def test_both_rows_share_bet_id(self, tmp_path: Path):
        """Both written rows carry the same bet_id."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        settled_row = dict(open_row)
        settled_row["status"] = "settled"
        settled_row["clv_pct"] = 1.0

        append_if_new_status(open_row, ledger)
        append_if_new_status(settled_row, ledger)

        rows = _read_ledger(ledger)
        assert len(rows) == 2
        assert rows[0]["bet_id"] == rows[1]["bet_id"]

    def test_settled_before_open_also_works(self, tmp_path: Path):
        """Settlement write followed by open write (unusual order) -> both written."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        settled_row = dict(open_row)
        settled_row["status"] = "settled"

        r1 = append_if_new_status(settled_row, ledger)
        r2 = append_if_new_status(open_row, ledger)

        assert r1 is True
        assert r2 is True
        rows = _read_ledger(ledger)
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# BE-R4-2 Criterion 2: same open row twice -> 2nd skipped
# ---------------------------------------------------------------------------

class TestDuplicateOpenRowBlocked:

    def test_second_open_row_skipped(self, tmp_path: Path):
        """Replaying the same open row (tick overlap) returns False; 1 row written."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")

        r1 = append_if_new_status(open_row, ledger)
        r2 = append_if_new_status(open_row, ledger)

        assert r1 is True
        assert r2 is False
        rows = _read_ledger(ledger)
        assert len(rows) == 1

    def test_second_settled_row_skipped(self, tmp_path: Path):
        """Replaying the settled twin returns False; still 2 rows total."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        settled_row = dict(open_row)
        settled_row["status"] = "settled"

        append_if_new_status(open_row, ledger)
        append_if_new_status(settled_row, ledger)
        r3 = append_if_new_status(settled_row, ledger)  # replay of settled

        assert r3 is False
        rows = _read_ledger(ledger)
        assert len(rows) == 2

    def test_open_replay_after_both_rows_written(self, tmp_path: Path):
        """open replay after open+settled are written -> still False; 2 rows."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        settled_row = dict(open_row)
        settled_row["status"] = "settled"

        append_if_new_status(open_row, ledger)
        append_if_new_status(settled_row, ledger)
        r3 = append_if_new_status(open_row, ledger)  # replay of open

        assert r3 is False
        rows = _read_ledger(ledger)
        assert len(rows) == 2

    def test_different_bet_ids_both_written(self, tmp_path: Path):
        """Two distinct bets (different matchups) are both written."""
        ledger = tmp_path / "clv_ledger.jsonl"
        row_a = _make_row("nba", "Lakers @ Celtics", idx=0, status="open")
        row_b = _make_row("nba", "Warriors @ Nuggets", idx=1, status="open")

        assert row_a["bet_id"] != row_b["bet_id"], "test setup: distinct bets"

        r1 = append_if_new_status(row_a, ledger)
        r2 = append_if_new_status(row_b, ledger)

        assert r1 is True
        assert r2 is True
        rows = _read_ledger(ledger)
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# BE-R4-2 Criterion 3: dollar-key record stripped before write
# ---------------------------------------------------------------------------

class TestDollarKeyStripped:

    def test_banned_key_absent_from_written_row(self, tmp_path: Path):
        """Every BANNED_KEY is stripped before the row reaches the ledger."""
        ledger = tmp_path / "clv_ledger.jsonl"
        row = _make_row(status="open")
        # Plant all banned keys onto the row.
        for k in BANNED_KEYS:
            row[k] = 99.99

        append_if_new_status(row, ledger)

        rows = _read_ledger(ledger)
        assert len(rows) == 1
        for k in BANNED_KEYS:
            assert k not in rows[0], "banned key %r found in ledger row" % k

    def test_stake_units_preserved_when_present(self, tmp_path: Path):
        """stake_units (a UNITS field) survives the strip."""
        ledger = tmp_path / "clv_ledger.jsonl"
        row = _make_row(status="open")
        row["stake_units"] = 2.5

        append_if_new_status(row, ledger)

        rows = _read_ledger(ledger)
        assert rows[0]["stake_units"] == 2.5

    def test_pnl_stripped_on_settled_row(self, tmp_path: Path):
        """pnl on a settled row is stripped (it is a dollar/P&L key)."""
        ledger = tmp_path / "clv_ledger.jsonl"
        row = _make_row(status="settled")
        row["pnl"] = 50.0
        row["clv_pct"] = 3.1  # CLV is allowed

        append_if_new_status(row, ledger)

        rows = _read_ledger(ledger)
        assert len(rows) == 1
        assert "pnl" not in rows[0]
        assert "clv_pct" in rows[0]


# ---------------------------------------------------------------------------
# BE-R4-2 Criterion 4: never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:

    def test_missing_ledger_dir_is_created(self, tmp_path: Path):
        """Missing parent directory is created transparently."""
        ledger = tmp_path / "sub" / "deep" / "clv_ledger.jsonl"
        row = _make_row(status="open")

        result = append_if_new_status(row, ledger)

        assert result is True
        assert ledger.exists()

    def test_empty_record_does_not_raise(self, tmp_path: Path):
        """An empty dict does not raise (bet_id computed from empty fields)."""
        ledger = tmp_path / "clv_ledger.jsonl"
        result = append_if_new_status({}, ledger)
        # Should return True or False but never raise.
        assert isinstance(result, bool)

    def test_none_path_uses_default_ledger_without_raise(self, tmp_path: Path, monkeypatch):
        """Passing path=None is accepted (falls back to DEFAULT_LEDGER path logic).

        We monkeypatch DEFAULT_LEDGER to a tmp_path file so the test NEVER
        touches the real production ledger, while still exercising the
        path=None -> DEFAULT_LEDGER resolution code path.
        """
        import scripts.platformkit.clv_ledger as _clv_mod
        import scripts.platformkit.clv_ledger_status_append as _sa_mod

        # Capture the real production ledger path BEFORE monkeypatching replaces it.
        real_ledger_path = _clv_mod.DEFAULT_LEDGER
        real_row_count_before = (
            len(real_ledger_path.read_text(encoding="utf-8").splitlines())
            if real_ledger_path.exists() else 0
        )

        fake_ledger = tmp_path / "clv_ledger_test_none.jsonl"
        monkeypatch.setattr(_clv_mod, "DEFAULT_LEDGER", fake_ledger)
        monkeypatch.setattr(_sa_mod, "DEFAULT_LEDGER", fake_ledger)

        row = _make_row(sport="nba", status="open")
        try:
            result = append_if_new_status(row, path=None)
            assert isinstance(result, bool)
        except Exception as exc:  # noqa: BLE001
            pytest.fail("append_if_new_status raised unexpectedly: %s" % exc)

        # Confirm the real production ledger was NOT touched after the call.
        real_row_count_after = (
            len(real_ledger_path.read_text(encoding="utf-8").splitlines())
            if real_ledger_path.exists() else 0
        )
        assert real_row_count_after == real_row_count_before, (
            "real DEFAULT_LEDGER was modified by test: before=%d after=%d"
            % (real_row_count_before, real_row_count_after)
        )

    def test_bad_record_with_non_serialisable_value(self, tmp_path: Path):
        """Record with a non-JSON-serialisable value falls back via default=str."""
        ledger = tmp_path / "clv_ledger.jsonl"
        row = _make_row(status="open")
        row["extra"] = object()  # non-serialisable; json.dumps(default=str) handles it

        result = append_if_new_status(row, ledger)

        assert isinstance(result, bool)  # never raises


# ---------------------------------------------------------------------------
# BE-R4-2 Criterion 5: _seen fast-path matches re-scan path
# ---------------------------------------------------------------------------

class TestSeenSetFastPath:

    def test_seen_set_updated_on_open_write(self, tmp_path: Path):
        """After writing an open row, the status_key is in _seen."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        seen: set = set()

        append_if_new_status(open_row, ledger, _seen=seen)

        expected_key = "%s|open" % open_row["bet_id"]
        assert expected_key in seen, "_seen must contain the open status_key"

    def test_seen_set_updated_on_settled_write(self, tmp_path: Path):
        """After writing a settled row, the settled status_key is in _seen."""
        ledger = tmp_path / "clv_ledger.jsonl"
        settled_row = _make_row(status="settled")
        seen: set = set()

        append_if_new_status(settled_row, ledger, _seen=seen)

        expected_key = "%s|settled" % settled_row["bet_id"]
        assert expected_key in seen

    def test_seen_set_blocks_replay_without_disk_scan(self, tmp_path: Path):
        """Second call with a populated _seen set skips without re-reading the file."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        seen: set = set()

        r1 = append_if_new_status(open_row, ledger, _seen=seen)
        # Delete the file to prove the second call uses the in-memory set only.
        ledger.unlink()
        r2 = append_if_new_status(open_row, ledger, _seen=seen)

        assert r1 is True
        assert r2 is False  # blocked by _seen even though the file is gone

    def test_seen_key_format_matches_rescan(self, tmp_path: Path):
        """The key stored in _seen must equal what _seen_status_keys returns for the same row.

        This guards against the fast-path and the re-scan path diverging, which
        would let a replay through on one path but not the other.
        """
        from scripts.platformkit.clv_ledger_status_append import (
            _status_key,
            _seen_status_keys,
        )

        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        seen: set = set()

        append_if_new_status(open_row, ledger, _seen=seen)

        # Key computed by fast-path (_status_key on the in-flight record).
        fast_key = _status_key(open_row)
        # Key computed by re-scan (read from disk, compute on stored row).
        disk_keys = _seen_status_keys(ledger)

        assert fast_key in seen, "fast-path key not in _seen"
        assert fast_key in disk_keys, "fast-path key != re-scan key (divergence!)"

    def test_batch_open_plus_settled_via_shared_seen(self, tmp_path: Path):
        """Batching open then settled via shared _seen writes both and blocks replays."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        settled_row = dict(open_row)
        settled_row["status"] = "settled"
        settled_row["clv_pct"] = 5.0
        seen: set = set()

        r1 = append_if_new_status(open_row, ledger, _seen=seen)
        r2 = append_if_new_status(settled_row, ledger, _seen=seen)
        r3 = append_if_new_status(open_row, ledger, _seen=seen)    # replay
        r4 = append_if_new_status(settled_row, ledger, _seen=seen)  # replay

        assert r1 is True, "open must be written"
        assert r2 is True, "settled twin must be written"
        assert r3 is False, "open replay must be blocked"
        assert r4 is False, "settled replay must be blocked"
        rows = _read_ledger(ledger)
        assert len(rows) == 2, "exactly 2 rows expected; got %d" % len(rows)

    def test_full_session_no_seen_set_rescans_disk(self, tmp_path: Path):
        """Without _seen, each call re-scans the ledger and still blocks dups."""
        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        settled_row = dict(open_row)
        settled_row["status"] = "settled"

        # No _seen passed -- each call uses _seen_status_keys() disk scan.
        r1 = append_if_new_status(open_row, ledger)
        r2 = append_if_new_status(settled_row, ledger)
        r3 = append_if_new_status(open_row, ledger)
        r4 = append_if_new_status(settled_row, ledger)

        assert r1 is True
        assert r2 is True
        assert r3 is False
        assert r4 is False
        rows = _read_ledger(ledger)
        assert len(rows) == 2

    def test_preloaded_seen_from_existing_ledger(self, tmp_path: Path):
        """Caller can pre-populate _seen from disk; function agrees with it."""
        from scripts.platformkit.clv_ledger_status_append import _seen_status_keys

        ledger = tmp_path / "clv_ledger.jsonl"
        open_row = _make_row(status="open")
        _write_ledger([open_row], ledger)

        # Pre-populate _seen by scanning the disk (simulates session startup).
        seen = _seen_status_keys(ledger)

        r_open_replay = append_if_new_status(open_row, ledger, _seen=seen)

        # Settled twin not yet in the ledger -> should be written.
        settled_row = dict(open_row)
        settled_row["status"] = "settled"
        r_settled = append_if_new_status(settled_row, ledger, _seen=seen)

        assert r_open_replay is False, "open replay must be blocked by pre-loaded _seen"
        assert r_settled is True, "settled twin not in pre-loaded set; must be written"
        rows = _read_ledger(ledger)
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# BE-ledger-sanitize: load_ledger read-time filter (iter-3 P1)
# ---------------------------------------------------------------------------

class TestLoadLedgerSanitizer:
    """Verify that load_ledger silently drops synthetic/malformed rows.

    The sanitizer must:
      * Drop rows where sport starts with 'test_'
        (leaked from tests that omitted tmp_path, e.g. sport='test_none_path_no_raise').
      * Drop rows where game_id is present but shorter than the structured minimum
        (e.g. game_id='gg' is a malformed inplay row).
      * Pass well-formed real rows through unchanged.
    """

    def _build_jsonl(self, rows: list, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
        return path

    def test_test_sport_row_filtered_out(self, tmp_path: Path):
        """Row with sport='test_x' is dropped; well-formed row survives."""
        from scripts.platformkit.clv_ledger import load_ledger

        ledger = tmp_path / "clv_ledger.jsonl"
        bad_row = {"sport": "test_none_path_no_raise", "status": "open", "bet_id": "x|open"}
        good_row = _make_row(sport="nba", status="open")
        self._build_jsonl([bad_row, good_row], ledger)

        result = load_ledger(ledger)

        assert len(result) == 1, "expected 1 row; got %d" % len(result)
        assert result[0]["sport"] == "nba", "well-formed row must survive"

    def test_short_game_id_row_filtered_out(self, tmp_path: Path):
        """Row with game_id='gg' (len=2) is dropped; row without game_id survives."""
        from scripts.platformkit.clv_ledger import load_ledger

        ledger = tmp_path / "clv_ledger.jsonl"
        bad_row = {"sport": "mlb", "game_id": "gg", "status": "open", "bet_id": "y|open"}
        good_row = _make_row(sport="mlb", status="open")  # no game_id field
        self._build_jsonl([bad_row, good_row], ledger)

        result = load_ledger(ledger)

        assert len(result) == 1, "expected 1 row; got %d" % len(result)
        assert result[0].get("game_id") != "gg", "malformed game_id row must be dropped"

    def test_both_synthetic_rows_filtered_well_formed_survives(self, tmp_path: Path):
        """Both a test-sport row and a short-game_id row are dropped; real row passes."""
        from scripts.platformkit.clv_ledger import load_ledger

        ledger = tmp_path / "clv_ledger.jsonl"
        test_row = {"sport": "test_x", "status": "open", "bet_id": "t|open"}
        inplay_bad = {"sport": "mlb", "game_id": "gg", "status": "open", "bet_id": "i|open"}
        real_row = _make_row(sport="nba", status="open")
        self._build_jsonl([test_row, inplay_bad, real_row], ledger)

        result = load_ledger(ledger)

        assert len(result) == 1, "only well-formed row must survive; got %d" % len(result)
        assert result[0]["sport"] == "nba"

    def test_real_game_id_row_not_filtered(self, tmp_path: Path):
        """Row with a real structured game_id (e.g. '401859967') is NOT filtered."""
        from scripts.platformkit.clv_ledger import load_ledger

        ledger = tmp_path / "clv_ledger.jsonl"
        real_row = _make_row(sport="nba", status="open")
        real_row["game_id"] = "401859967"  # 9 chars -- well above the minimum
        self._build_jsonl([real_row], ledger)

        result = load_ledger(ledger)

        assert len(result) == 1, "row with valid game_id must survive"
        assert result[0]["game_id"] == "401859967"

    def test_none_game_id_not_filtered(self, tmp_path: Path):
        """Row with game_id=None (no field) is NOT filtered (absence != malformed)."""
        from scripts.platformkit.clv_ledger import load_ledger

        ledger = tmp_path / "clv_ledger.jsonl"
        row = _make_row(sport="mlb", status="open")
        # Explicitly ensure no game_id field.
        row.pop("game_id", None)
        self._build_jsonl([row], ledger)

        result = load_ledger(ledger)

        assert len(result) == 1, "row without game_id must survive"

    def test_production_ledger_synthetic_rows_absent(self):
        """Confirm the real production ledger no longer surfaces synthetic rows via load_ledger."""
        from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, load_ledger

        if not DEFAULT_LEDGER.exists():
            pytest.skip("production ledger not present in this environment")

        result = load_ledger(DEFAULT_LEDGER)
        for row in result:
            sport = str(row.get("sport") or "")
            assert not sport.startswith("test_"), (
                "synthetic test-sport row leaked to production ledger output: %r" % row
            )
            game_id = row.get("game_id")
            if game_id is not None:
                assert len(str(game_id)) >= 3, (
                    "malformed short game_id row in production ledger output: %r" % row
                )
