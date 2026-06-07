"""tests/test_live_snapshot_picker.py

Lock-in tests for api.courtvision_router._epoch_snaps / _is_epoch_snap and
the _box_score_from_snapshot function, covering:
  1. _is_epoch_snap excludes _pregame / _final / _endq3 sentinels and accepts
     epoch-digit suffixes.
  2. _epoch_snaps returns a sorted list of epoch files; [-1] is the latest.
  3. On real game 0042500316 the correct three sentinel files are excluded.
  4. _box_score_from_snapshot reads is_starter from both 'is_starter' and
     'starter' fields, falls back to False when neither is present.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("NBA_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.courtvision_router import (
    _is_epoch_snap,
    _epoch_snaps,
    _box_score_from_snapshot,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1 & 2. _is_epoch_snap and _epoch_snaps unit tests (synthetic tmp directory)
# ─────────────────────────────────────────────────────────────────────────────

GID = "0042500316"


def _make_snap_file(directory: Path, gid: str, suffix: str, content: dict) -> Path:
    """Write {gid}_{suffix}.json to directory and return the Path."""
    p = directory / f"{gid}_{suffix}.json"
    p.write_text(json.dumps(content), encoding="utf-8")
    return p


class TestIsEpochSnap:
    """_is_epoch_snap must return True only for digit-suffixed stems."""

    @pytest.mark.parametrize("suffix,expected", [
        ("1780024638000", True),   # valid epoch
        ("1234567890",   True),   # valid epoch (shorter)
        ("0",            True),   # single digit
        ("pregame",      False),  # named sentinel
        ("final",        False),  # named sentinel
        ("endq3",        False),  # named sentinel
        ("FINAL",        False),  # case variant
        ("endQ3",        False),  # mixed-case sentinel
        ("abc123",       False),  # alphanumeric non-digit suffix
        ("",             False),  # empty (edge case)
    ])
    def test_suffix_classification(self, tmp_path, suffix, expected):
        p = tmp_path / f"{GID}_{suffix}.json"
        p.write_text("{}", encoding="utf-8")
        assert _is_epoch_snap(p) == expected, (
            f"Expected _is_epoch_snap({p.name}) == {expected}"
        )


class TestEpochSnaps:
    """_epoch_snaps should return only epoch-digit files, sorted ascending."""

    def test_excludes_sentinel_files(self, tmp_path):
        """Sentinel files must not appear in the result list."""
        sentinels = ["pregame", "final", "endq3"]
        epochs    = ["1000", "2000", "3000"]

        content = {"captured_at": "2026-05-29T00:00:00+00:00", "game_status": "FINAL"}
        for s in sentinels:
            _make_snap_file(tmp_path, GID, s, content)
        for e in epochs:
            _make_snap_file(tmp_path, GID, e, content)

        result = _epoch_snaps(tmp_path, GID)
        names  = [p.name for p in result]

        for s in sentinels:
            assert f"{GID}_{s}.json" not in names, (
                f"Sentinel {GID}_{s}.json should be excluded"
            )

    def test_returns_only_epoch_files(self, tmp_path):
        """All returned files must have digit-only suffixes."""
        for s in ["pregame", "final", "endq3"]:
            _make_snap_file(tmp_path, GID, s, {})
        for e in ["1000", "2000", "3000"]:
            _make_snap_file(tmp_path, GID, e, {})

        result = _epoch_snaps(tmp_path, GID)
        assert len(result) == 3

    def test_sorted_ascending(self, tmp_path):
        """Files must be sorted ascending by name (epoch numbers)."""
        epochs = ["3000", "1000", "2000"]
        for e in epochs:
            _make_snap_file(tmp_path, GID, e, {})

        result = _epoch_snaps(tmp_path, GID)
        names  = [p.name for p in result]
        assert names == sorted(names), f"Expected sorted; got {names}"

    def test_last_element_is_latest(self, tmp_path):
        """[-1] element must be the file with the largest epoch suffix."""
        epochs = ["1000000", "2000000", "9000000", "5000000"]
        for e in epochs:
            _make_snap_file(tmp_path, GID, e, {})

        result = _epoch_snaps(tmp_path, GID)
        assert result[-1].name == f"{GID}_9000000.json"

    def test_empty_dir_returns_empty_list(self, tmp_path):
        result = _epoch_snaps(tmp_path, GID)
        assert result == []

    def test_only_sentinels_returns_empty_list(self, tmp_path):
        for s in ["pregame", "final", "endq3"]:
            _make_snap_file(tmp_path, GID, s, {})

        result = _epoch_snaps(tmp_path, GID)
        assert result == [], (
            "_epoch_snaps must return [] when only sentinel files are present"
        )

    def test_other_gid_files_not_included(self, tmp_path):
        """Files for a different gid must not appear."""
        other_gid = "0041234567"
        _make_snap_file(tmp_path, GID,      "1000", {})
        _make_snap_file(tmp_path, other_gid, "2000", {})

        result = _epoch_snaps(tmp_path, GID)
        assert len(result) == 1
        assert GID in result[0].name


# ─────────────────────────────────────────────────────────────────────────────
# 3. Real-data test on game 0042500316
# ─────────────────────────────────────────────────────────────────────────────

LIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
REAL_GAME_SENTINELS = ["pregame", "final", "endq3"]


@pytest.mark.skipif(
    not LIVE_DIR.exists() or not any(LIVE_DIR.glob(f"{GID}_*.json")),
    reason=f"data/live/{GID}_*.json not present — offline data missing",
)
class TestRealGameSentinelExclusion:
    """On real game 0042500316 the three named sentinels must be excluded."""

    def test_sentinel_files_exist_on_disk(self):
        """Pre-condition: confirm the sentinel files we're testing actually exist."""
        for s in REAL_GAME_SENTINELS:
            p = LIVE_DIR / f"{GID}_{s}.json"
            assert p.exists(), f"Expected sentinel {p.name} to exist for this test"

    def test_sentinels_excluded_from_epoch_snaps(self):
        result = _epoch_snaps(LIVE_DIR, GID)
        names  = [p.name for p in result]
        for s in REAL_GAME_SENTINELS:
            sentinel_name = f"{GID}_{s}.json"
            assert sentinel_name not in names, (
                f"Sentinel {sentinel_name} must be excluded from _epoch_snaps"
            )

    def test_latest_is_epoch_file(self):
        """[-1] must be a digit-epoch file, not a sentinel."""
        result = _epoch_snaps(LIVE_DIR, GID)
        assert result, "No epoch snaps found for 0042500316"
        latest = result[-1]
        suffix = latest.stem.rpartition("_")[2]
        assert suffix.isdigit(), (
            f"Latest snapshot {latest.name} has non-digit suffix '{suffix}' — "
            f"sentinel leaked past _epoch_snaps filter"
        )

    def test_epoch_count_matches_expectation(self):
        """All 316 files except the 3 sentinels should be returned."""
        all_316 = list(LIVE_DIR.glob(f"{GID}_*.json"))
        sentinels = [p for p in all_316 if not _is_epoch_snap(p)]
        epoch_result = _epoch_snaps(LIVE_DIR, GID)
        assert len(epoch_result) == len(all_316) - len(sentinels), (
            f"Expected {len(all_316) - len(sentinels)} epoch snaps, "
            f"got {len(epoch_result)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. _box_score_from_snapshot reads is_starter
# ─────────────────────────────────────────────────────────────────────────────

_PLAYER_BASE = {
    "name": "Test Player",
    "team": "AAA",
    "min": 35,
    "pts": 20,
    "reb": 5,
    "ast": 3,
    "fg3m": 2,
    "stl": 1,
    "blk": 0,
    "tov": 2,
}


class TestBoxScoreFromSnapshot:
    """_box_score_from_snapshot must correctly set the 'starter' field."""

    def test_is_starter_true(self):
        """is_starter=True in snapshot player dict should set starter=True."""
        snap = {"players": [{**_PLAYER_BASE, "is_starter": True}]}
        box  = _box_score_from_snapshot(snap)
        assert box[0]["starter"] is True

    def test_is_starter_false(self):
        """is_starter=False should set starter=False."""
        snap = {"players": [{**_PLAYER_BASE, "is_starter": False}]}
        box  = _box_score_from_snapshot(snap)
        assert box[0]["starter"] is False

    def test_starter_key_true(self):
        """Legacy 'starter' key (True) should propagate."""
        snap = {"players": [{**_PLAYER_BASE, "starter": True}]}
        box  = _box_score_from_snapshot(snap)
        assert box[0]["starter"] is True

    def test_starter_key_false(self):
        """Legacy 'starter' key (False) should propagate."""
        snap = {"players": [{**_PLAYER_BASE, "starter": False}]}
        box  = _box_score_from_snapshot(snap)
        assert box[0]["starter"] is False

    def test_no_starter_field_defaults_false(self):
        """Player with neither is_starter nor starter should default to False."""
        snap = {"players": [dict(_PLAYER_BASE)]}
        box  = _box_score_from_snapshot(snap)
        assert box[0]["starter"] is False

    def test_is_starter_takes_priority_over_starter(self):
        """When both keys are present, is_starter takes logical-OR priority
        (bool(is_starter or starter)).  Specifically: if is_starter=True, result=True."""
        snap = {"players": [{**_PLAYER_BASE, "is_starter": True, "starter": False}]}
        box  = _box_score_from_snapshot(snap)
        # bool(True or False) = True
        assert box[0]["starter"] is True

    def test_empty_snapshot_returns_empty(self):
        box = _box_score_from_snapshot({})
        assert box == []

    def test_none_snapshot_returns_empty(self):
        box = _box_score_from_snapshot(None)
        assert box == []

    def test_snapshot_without_players_returns_empty(self):
        box = _box_score_from_snapshot({"game_status": "FINAL"})
        assert box == []

    def test_player_without_name_is_skipped(self):
        snap = {"players": [{"team": "AAA", "min": 30}]}
        box  = _box_score_from_snapshot(snap)
        assert box == []

    def test_multi_player_starter_mix(self):
        """Multiple players with mixed is_starter values are all read correctly."""
        snap = {"players": [
            {**_PLAYER_BASE, "name": "Alice", "min": 35, "is_starter": True},
            {**_PLAYER_BASE, "name": "Bob",   "min": 10, "is_starter": False},
            {**_PLAYER_BASE, "name": "Carol",  "min": 30, "is_starter": True},
        ]}
        box = _box_score_from_snapshot(snap)
        by_name = {r["player_name"]: r["starter"] for r in box}
        assert by_name["Alice"] is True
        assert by_name["Bob"]   is False
        assert by_name["Carol"] is True

    def test_minutes_string_parsed(self):
        """Minutes in MM:SS string format should be parsed correctly."""
        snap = {"players": [{**_PLAYER_BASE, "min": "35:30"}]}
        box  = _box_score_from_snapshot(snap)
        assert abs(box[0]["min"] - 35.5) < 0.01

    def test_sorted_by_minutes_descending(self):
        """Box score rows must be sorted by minutes descending."""
        snap = {"players": [
            {**_PLAYER_BASE, "name": "Low",  "min": 10},
            {**_PLAYER_BASE, "name": "High", "min": 35},
            {**_PLAYER_BASE, "name": "Mid",  "min": 20},
        ]}
        box   = _box_score_from_snapshot(snap)
        names = [r["player_name"] for r in box]
        assert names == ["High", "Mid", "Low"], (
            f"Expected sorted by min desc, got {names}"
        )

    @pytest.mark.skipif(
        not LIVE_DIR.exists() or not any(LIVE_DIR.glob(f"{GID}_*.json")),
        reason="data/live data missing",
    )
    def test_real_final_snapshot_has_starters(self):
        """On the real FINAL snapshot for 0042500316, is_starter should be read."""
        snaps = _epoch_snaps(LIVE_DIR, GID)
        assert snaps, "No epoch snaps found"
        final_snap = json.loads(snaps[-1].read_text(encoding="utf-8"))
        box = _box_score_from_snapshot(final_snap)
        assert len(box) > 0, "No box score rows from final snapshot"
        # At least one starter should be True (real snapshot has is_starter=True)
        starters = [r for r in box if r["starter"]]
        assert len(starters) > 0, (
            "Expected at least one starter=True from real final snapshot; "
            f"got all False. Sample row: {box[0]}"
        )
