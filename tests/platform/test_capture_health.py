"""test_capture_health.py — Offline unit tests for capture_health.py (N-CLV-005a).

All tests run without network access.  A stub webhook replaces the real alert
helper.  All disk writes go to pytest's ``tmp_path`` — real ``.bot_state/`` and
``data/lines/forward/`` are never touched.

Python 3.9 compatible.

Done-criteria mapped to tests:
  1. Offline gap report runs on a fixture schedule + fixture ledger (no network).
  2. A simulated missed game raises exactly ONE alert via the mocked webhook.
  3. The health JSON is written idempotently (rerun overwrites, no dupes).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Path wiring
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "platformkit" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))

import ledger_writer as _writer  # noqa: E402
import ledger_schema as _schema  # noqa: E402
import capture_health as ch  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DATE = "2030-01-15"
_EID_A = "test_nba_001"  # game that WILL have an opener row
_EID_B = "test_nba_002"  # game that will NOT have an opener row (the gap)

_SCHEDULE: List[Dict[str, Any]] = [
    {"event_id": _EID_A, "game_date": _DATE, "home": "New York Knicks",
     "away": "San Antonio Spurs"},
    {"event_id": _EID_B, "game_date": _DATE, "home": "Boston Celtics",
     "away": "Golden State Warriors"},
]


def _write_opener_row(ledger_root: Path, event_id: str, date: str) -> None:
    """Write a minimal valid opener row to the fixture ledger."""
    rec = {
        "sport": "nba",
        "event_id": event_id,
        "market": "spread",
        "book": "draftkings",
        "price": -110.0,
        "side": "new york knicks:-2.5",
        "kind": "open",
        "ts_utc_observed": f"{date}T20:00:00Z",
        "source": "odds_api_live",
    }
    _schema.validate(rec)
    _writer.append(rec, root=ledger_root)


# ---------------------------------------------------------------------------
# 1. Import — module importable with zero network
# ---------------------------------------------------------------------------

def test_import_clean() -> None:
    """capture_health must import without network or API key."""
    assert ch is not None
    assert hasattr(ch, "compute_gap_report")
    assert hasattr(ch, "write_health_json")
    assert hasattr(ch, "maybe_alert")


# ---------------------------------------------------------------------------
# 2. Gap report — all games captured → no gaps, status "ok"
# ---------------------------------------------------------------------------

def test_no_gaps_when_all_games_captured(tmp_path: Path) -> None:
    """When every scheduled game has an opener row, gap_count is 0."""
    _write_opener_row(tmp_path, _EID_A, _DATE)
    _write_opener_row(tmp_path, _EID_B, _DATE)

    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    assert report["gap_count"] == 0, f"Expected 0 gaps, got: {report['gaps']}"
    assert report["status"] == "ok"
    assert report["games_captured"] == 2
    assert report["games_checked"] == 2
    assert report["gaps"] == []


# ---------------------------------------------------------------------------
# 3. Gap report — one game missing → exactly one gap, status "gap_detected"
# ---------------------------------------------------------------------------

def test_one_gap_when_one_game_missing(tmp_path: Path) -> None:
    """When one game has no opener row, the report lists exactly one gap."""
    _write_opener_row(tmp_path, _EID_A, _DATE)
    # _EID_B intentionally NOT written

    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    assert report["gap_count"] == 1
    assert report["status"] == "gap_detected"
    assert report["games_captured"] == 1
    assert len(report["gaps"]) == 1
    assert report["gaps"][0]["event_id"] == _EID_B


# ---------------------------------------------------------------------------
# 4. Gap report — empty ledger → all games are gaps
# ---------------------------------------------------------------------------

def test_all_gaps_when_ledger_empty(tmp_path: Path) -> None:
    """When the ledger has zero rows, every scheduled game is a gap."""
    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    assert report["gap_count"] == len(_SCHEDULE)
    assert report["status"] == "gap_detected"
    assert report["games_captured"] == 0
    assert {g["event_id"] for g in report["gaps"]} == {_EID_A, _EID_B}


# ---------------------------------------------------------------------------
# 5. DONE CRITERIA 1: offline gap report — fixture schedule + fixture ledger,
#    no network calls required at any point.
# ---------------------------------------------------------------------------

def test_fixture_schedule_fixture_ledger_offline(tmp_path: Path) -> None:
    """Full offline round-trip: write fixture rows, compute report, verify shape."""
    _write_opener_row(tmp_path, _EID_A, _DATE)

    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    # Shape checks
    assert isinstance(report, dict)
    assert "generated_at" in report
    assert "sport" in report
    assert "games_checked" in report
    assert "games_captured" in report
    assert "gaps" in report
    assert "gap_count" in report
    assert "status" in report

    # The missing game is detected
    assert report["gap_count"] == 1
    assert report["gaps"][0]["event_id"] == _EID_B

    # Report is JSON-serialisable
    serialised = json.dumps(report)
    assert isinstance(serialised, str)


# ---------------------------------------------------------------------------
# 6. DONE CRITERIA 2: simulated missed game → exactly ONE alert via stub
# ---------------------------------------------------------------------------

def test_exactly_one_alert_for_one_missed_game(tmp_path: Path) -> None:
    """A single missing game must trigger the alert callback exactly once."""
    # Only _EID_A has an opener row → _EID_B is a gap
    _write_opener_row(tmp_path, _EID_A, _DATE)

    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)
    assert report["gap_count"] == 1, "precondition: exactly one gap in fixture"

    call_log: List[Dict[str, Any]] = []

    def stub_alert(message: str, gaps: List[Dict[str, Any]]) -> None:
        call_log.append({"message": message, "gaps": gaps})

    fired = ch.maybe_alert(report, alert_fn=stub_alert)

    assert fired is True, "maybe_alert must return True when gaps exist"
    assert len(call_log) == 1, (
        f"Expected exactly 1 alert call, got {len(call_log)}"
    )
    # The alert message must reference the missing event_id
    assert _EID_B in call_log[0]["message"], (
        "Alert message must mention the gap event_id"
    )
    # The gaps list passed to the stub matches the report
    assert len(call_log[0]["gaps"]) == 1
    assert call_log[0]["gaps"][0]["event_id"] == _EID_B


def test_no_alert_when_no_gaps(tmp_path: Path) -> None:
    """maybe_alert must NOT call the callback when there are no gaps."""
    _write_opener_row(tmp_path, _EID_A, _DATE)
    _write_opener_row(tmp_path, _EID_B, _DATE)

    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    call_log: List[str] = []

    def stub_alert(message: str, gaps: List[Dict[str, Any]]) -> None:
        call_log.append(message)

    fired = ch.maybe_alert(report, alert_fn=stub_alert)

    assert fired is False
    assert call_log == [], "No alerts must fire when there are no gaps"


def test_two_gaps_still_one_alert_call(tmp_path: Path) -> None:
    """Two gap games must produce exactly one consolidated alert, not two."""
    # Neither game has an opener → both are gaps
    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)
    assert report["gap_count"] == 2, "precondition: two gaps"

    call_log: List[Dict[str, Any]] = []

    def stub_alert(message: str, gaps: List[Dict[str, Any]]) -> None:
        call_log.append({"message": message, "gaps": gaps})

    ch.maybe_alert(report, alert_fn=stub_alert)

    assert len(call_log) == 1, "All gaps must be batched into a single alert call"
    assert len(call_log[0]["gaps"]) == 2


# ---------------------------------------------------------------------------
# 7. DONE CRITERIA 3: health JSON idempotency
# ---------------------------------------------------------------------------

def test_health_json_written_idempotently(tmp_path: Path) -> None:
    """Calling write_health_json twice overwrites the file — no duplication."""
    out = tmp_path / "capture_health.json"

    report1 = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)
    ch.write_health_json(report1, out_path=out)

    assert out.exists()
    with open(str(out), "r", encoding="utf-8") as fh:
        data1 = json.load(fh)

    # Write a second report (now with one game captured)
    _write_opener_row(tmp_path, _EID_A, _DATE)
    report2 = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)
    ch.write_health_json(report2, out_path=out)

    with open(str(out), "r", encoding="utf-8") as fh:
        data2 = json.load(fh)

    # File must reflect the SECOND report (overwritten, not appended)
    assert data2["games_captured"] == 1, "Second write must overwrite first"
    assert data2["gap_count"] == 1
    # Only one JSON object at the top level (not an array / not duped lines)
    assert isinstance(data2, dict)


def test_health_json_is_single_object(tmp_path: Path) -> None:
    """The health JSON file must contain exactly one top-level JSON object."""
    out = tmp_path / "capture_health.json"
    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    ch.write_health_json(report, out_path=out)
    ch.write_health_json(report, out_path=out)  # run twice

    raw = out.read_text(encoding="utf-8")
    # Must parse as a single dict, not a list or broken JSON
    parsed = json.loads(raw)
    assert isinstance(parsed, dict), "Health JSON must be a single object"


def test_health_json_default_path_not_written_in_tests(tmp_path: Path) -> None:
    """write_health_json with an explicit out_path must not touch .bot_state/."""
    real_default = ch._HEALTH_STATE_PATH
    before_exists = real_default.exists()

    out = tmp_path / "test_out.json"
    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)
    ch.write_health_json(report, out_path=out)

    # Real .bot_state must be untouched
    assert real_default.exists() == before_exists, (
        "write_health_json with out_path must not create .bot_state/capture_health.json"
    )
    assert out.exists(), "Explicit out_path must be written"


# ---------------------------------------------------------------------------
# 8. Gap report — only "open" rows count as captured; "move"/"close" do not
# ---------------------------------------------------------------------------

def test_only_open_kind_counts_as_captured(tmp_path: Path) -> None:
    """A game with only 'move' or 'close' rows (no 'open') must still be a gap."""
    # Write a "close" row for _EID_A — NOT an opener
    rec = {
        "sport": "nba",
        "event_id": _EID_A,
        "market": "spread",
        "book": "draftkings",
        "price": -110.0,
        "side": "new york knicks:-2.5",
        "kind": "close",
        "ts_utc_observed": f"{_DATE}T20:00:00Z",
        "source": "odds_api_live",
    }
    _schema.validate(rec)
    _writer.append(rec, root=tmp_path)

    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)

    # _EID_A has a row but not an opener — must still count as a gap
    assert report["gap_count"] == 2, (
        "A game with only 'close' rows must still appear as a gap"
    )
    gap_eids = {g["event_id"] for g in report["gaps"]}
    assert _EID_A in gap_eids


# ---------------------------------------------------------------------------
# 9. Malformed schedule entries are skipped without crashing
# ---------------------------------------------------------------------------

def test_malformed_schedule_entries_skipped(tmp_path: Path) -> None:
    """Entries missing event_id or game_date must be silently skipped."""
    schedule_with_bad: List[Dict[str, Any]] = [
        {"event_id": _EID_A, "game_date": _DATE},
        {"game_date": _DATE},                     # no event_id
        {"event_id": _EID_B},                     # no game_date
        {},                                        # completely empty
    ]
    _write_opener_row(tmp_path, _EID_A, _DATE)

    report = ch.compute_gap_report(schedule_with_bad, ledger_root=tmp_path)

    # Only the valid entry (_EID_A) is checked
    assert report["games_checked"] == 1
    assert report["gap_count"] == 0


# ---------------------------------------------------------------------------
# 10. Report shape — all required keys are present
# ---------------------------------------------------------------------------

def test_report_shape_has_required_keys(tmp_path: Path) -> None:
    """compute_gap_report must always return all required keys."""
    report = ch.compute_gap_report([], ledger_root=tmp_path)

    required = {"generated_at", "sport", "games_checked", "games_captured",
                "gaps", "gap_count", "status"}
    missing = required - set(report.keys())
    assert not missing, f"Report missing keys: {missing}"


def test_report_sport_is_nba(tmp_path: Path) -> None:
    report = ch.compute_gap_report(_SCHEDULE, ledger_root=tmp_path)
    assert report["sport"] == "nba"


def test_empty_schedule_zero_gaps(tmp_path: Path) -> None:
    """An empty schedule produces a clean 'ok' report with zero gaps."""
    report = ch.compute_gap_report([], ledger_root=tmp_path)

    assert report["games_checked"] == 0
    assert report["gap_count"] == 0
    assert report["status"] == "ok"
