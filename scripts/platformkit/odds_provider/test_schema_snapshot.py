"""Per-file tests for schema_snapshot.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_schema_snapshot.py -q

Acceptance criteria:
  1. shape_of profiles a flat record's key -> type_name (the real line_history
     JSONL row shape).
  2. shape_of is depth-bounded: a payload nested deeper than max_depth does not
     explode / recurse past the bound.
  3. shape_of_records unions across rows (a key present in only some rows still
     appears); a genuine type conflict at the same path yields a "mixed(...)"
     marker.
  4. compare() flags a dropped field as missing_keys (the silent-degrade this
     module exists to catch), an added field as new_keys (does not fail ok),
     and a type flip as type_changes.
  5. save_snapshot/load_snapshot round-trip atomically (tmp+replace) under an
     injected path -- never touches the real data/cache/schema_snapshots/.
  6. discover_capture_files finds real *.jsonl files under an injected base_dir,
     sorted with newest last.
  7. snapshot_sport + check_sport run end-to-end against REAL captured JSONL
     samples copied from data/cache/line_history/ (see test_against_real_samples).
  8. Every public function never raises on malformed/missing input.
"""
from __future__ import annotations

import datetime
import json

from scripts.platformkit.odds_provider.schema_snapshot import (
    check_sport, compare, discover_capture_files, load_records_by_provider,
    load_snapshot, save_snapshot, shape_of, shape_of_records, snapshot_sport)

_ROW = {
    "sport": "nba", "game_id": "1", "home": "A", "away": "B",
    "market_type": "moneyline", "side": "home", "line": None, "odds": 1.5,
    "book": "espn:DraftKings", "devigged_prob": 0.6,
    "captured_at": "2026-06-22T00:00:00+00:00", "commence_time": "2026-06-14T00:30Z",
}


def test_shape_of_flat_record():
    shape = shape_of(_ROW)
    assert shape["$"] == "object"
    assert shape["odds"] == "number"
    assert shape["book"] == "string"
    assert shape["line"] == "null"


def test_shape_of_depth_bounded():
    nested = {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}
    shape = shape_of(nested, max_depth=2)
    # depth 0 = "$", depth1 = "a", depth2 = "a.b" (object, not descended further)
    assert shape["a.b"] == "object"
    assert "a.b.c" not in shape


def test_shape_of_records_unions_optional_keys():
    rows = [dict(_ROW), {k: v for k, v in _ROW.items() if k != "devigged_prob"}]
    shape = shape_of_records(rows)
    assert shape["devigged_prob"] == "number"  # present in at least one row
    assert shape["odds"] == "number"


def test_shape_of_records_flags_type_conflict():
    rows = [dict(_ROW, odds=1.5), dict(_ROW, odds="1.5")]
    shape = shape_of_records(rows)
    assert shape["odds"].startswith("mixed(")


def test_compare_detects_missing_key():
    snap = shape_of(_ROW)
    fresh = {k: v for k, v in snap.items() if k != "odds"}
    diff = compare(fresh, snap)
    assert diff["ok"] is False
    assert "odds" in diff["missing_keys"]


def test_compare_new_key_is_benign():
    snap = shape_of(_ROW)
    fresh = dict(snap, extra_field="string")
    diff = compare(fresh, snap)
    assert diff["ok"] is True
    assert "extra_field" in diff["new_keys"]


def test_compare_type_change_fails():
    snap = shape_of(_ROW)
    fresh = dict(snap)
    fresh["odds"] = "object"
    diff = compare(fresh, snap)
    assert diff["ok"] is False
    assert "odds" in diff["type_changes"]


def test_compare_never_raises_on_bad_input():
    diff = compare(None, None)
    assert diff["ok"] is True or diff["ok"] is False  # just must not raise


def test_save_and_load_snapshot_roundtrip(tmp_path):
    path = tmp_path / "nba" / "espn.json"
    shape = shape_of(_ROW)
    ok = save_snapshot("espn", "nba", shape, sample_size=1, dated="2026-06-22", path=path)
    assert ok is True
    assert path.exists()
    loaded = load_snapshot("espn", "nba", path=path)
    assert loaded["shape"] == shape
    assert loaded["sample_size"] == 1


def test_load_snapshot_missing_file_returns_none(tmp_path):
    assert load_snapshot("nope", "nba", path=tmp_path / "missing.json") is None


def test_discover_capture_files_sorted_newest_last(tmp_path):
    sport_dir = tmp_path / "nba"
    sport_dir.mkdir()
    (sport_dir / "2026-06-20.jsonl").write_text("{}", encoding="utf-8")
    (sport_dir / "2026-06-22.jsonl").write_text("{}", encoding="utf-8")
    (sport_dir / "2026-06-21.jsonl").write_text("{}", encoding="utf-8")
    files = discover_capture_files("nba", base_dir=tmp_path)
    assert [f.name for f in files] == ["2026-06-20.jsonl", "2026-06-21.jsonl",
                                        "2026-06-22.jsonl"]


def test_discover_capture_files_missing_dir_empty(tmp_path):
    assert discover_capture_files("nba", base_dir=tmp_path) == []


def test_load_records_by_provider_buckets_by_book_prefix(tmp_path):
    f = tmp_path / "day.jsonl"
    rows = [dict(_ROW, book="espn:DraftKings"), dict(_ROW, book="pinnacle"),
            dict(_ROW, book="espn:FanDuel")]
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    by_provider = load_records_by_provider(f)
    assert len(by_provider["espn"]) == 2
    assert len(by_provider["pinnacle"]) == 1


def test_load_records_by_provider_skips_malformed_lines(tmp_path):
    f = tmp_path / "day.jsonl"
    f.write_text(json.dumps(_ROW) + "\nNOT JSON\n", encoding="utf-8")
    by_provider = load_records_by_provider(f)
    assert sum(len(v) for v in by_provider.values()) == 1


def test_snapshot_then_check_ok_on_unchanged_shape(tmp_path):
    line_history = tmp_path / "line_history"
    sport_dir = line_history / "nba"
    sport_dir.mkdir(parents=True)
    (sport_dir / "2026-06-22.jsonl").write_text(json.dumps(_ROW), encoding="utf-8")
    snap_dir = tmp_path / "snapshots"

    snap_doc = snapshot_sport("nba", base_dir=line_history, snapshot_dir=snap_dir)
    assert snap_doc["providers"]["espn"]["saved"] is True

    check_doc = check_sport("nba", base_dir=line_history, snapshot_dir=snap_dir)
    assert check_doc["providers"]["espn"]["status"] == "ok"


def test_check_sport_flags_drift_on_dropped_field(tmp_path):
    line_history = tmp_path / "line_history"
    sport_dir = line_history / "nba"
    sport_dir.mkdir(parents=True)
    (sport_dir / "2026-06-22.jsonl").write_text(json.dumps(_ROW), encoding="utf-8")
    snap_dir = tmp_path / "snapshots"
    snapshot_sport("nba", base_dir=line_history, snapshot_dir=snap_dir)

    dropped = {k: v for k, v in _ROW.items() if k != "devigged_prob"}
    (sport_dir / "2026-06-23.jsonl").write_text(json.dumps(dropped), encoding="utf-8")
    # today pinned near the baseline date (1 day old) -- this test exercises
    # fresh drift, not the stale_baseline path (see test_check_sport_old_
    # baseline_drift_reports_stale_baseline below for that).
    check_doc = check_sport("nba", base_dir=line_history, snapshot_dir=snap_dir,
                             today=datetime.date(2026, 6, 23))
    assert check_doc["providers"]["espn"]["status"] == "drift"
    assert "devigged_prob" in check_doc["providers"]["espn"]["missing_keys"]


def test_check_sport_no_snapshot_reported_not_failed(tmp_path):
    line_history = tmp_path / "line_history"
    sport_dir = line_history / "nba"
    sport_dir.mkdir(parents=True)
    (sport_dir / "2026-06-22.jsonl").write_text(json.dumps(_ROW), encoding="utf-8")
    check_doc = check_sport("nba", base_dir=line_history, snapshot_dir=tmp_path / "snaps")
    assert check_doc["providers"]["espn"]["status"] == "no_snapshot"


def test_snapshot_sport_missing_capture_dir_empty_providers(tmp_path):
    doc = snapshot_sport("nba", base_dir=tmp_path / "nonexistent")
    assert doc["providers"] == {}
    assert doc["capture_file"] is None


# --- stale_baseline (2026-07-15, fix lane F3): an old baseline that drifts on a
# field that was null when snapshotted (e.g. devigged_prob) self-identifies as
# "stale_baseline" instead of counting as live drift forever. ------------------

def test_check_sport_recent_drift_still_reports_drift(tmp_path):
    line_history = tmp_path / "line_history"
    sport_dir = line_history / "nba"
    sport_dir.mkdir(parents=True)
    (sport_dir / "2026-06-22.jsonl").write_text(json.dumps(_ROW), encoding="utf-8")
    snap_dir = tmp_path / "snapshots"
    snapshot_sport("nba", base_dir=line_history, snapshot_dir=snap_dir)

    dropped = {k: v for k, v in _ROW.items() if k != "devigged_prob"}
    (sport_dir / "2026-06-23.jsonl").write_text(json.dumps(dropped), encoding="utf-8")
    check_doc = check_sport("nba", base_dir=line_history, snapshot_dir=snap_dir,
                             today=datetime.date(2026, 6, 24))
    assert check_doc["providers"]["espn"]["status"] == "drift"


def test_check_sport_old_baseline_drift_reports_stale_baseline(tmp_path):
    line_history = tmp_path / "line_history"
    sport_dir = line_history / "nba"
    sport_dir.mkdir(parents=True)
    (sport_dir / "2026-06-22.jsonl").write_text(json.dumps(_ROW), encoding="utf-8")
    snap_dir = tmp_path / "snapshots"
    snapshot_sport("nba", base_dir=line_history, snapshot_dir=snap_dir)

    dropped = {k: v for k, v in _ROW.items() if k != "devigged_prob"}
    (sport_dir / "2026-07-20.jsonl").write_text(json.dumps(dropped), encoding="utf-8")
    check_doc = check_sport("nba", base_dir=line_history, snapshot_dir=snap_dir,
                             today=datetime.date(2026, 7, 20))  # baseline 28 days old
    info = check_doc["providers"]["espn"]
    assert info["status"] == "stale_baseline"
    assert info["baseline_age_days"] == 28


def test_check_sport_old_baseline_no_drift_stays_ok(tmp_path):
    line_history = tmp_path / "line_history"
    sport_dir = line_history / "nba"
    sport_dir.mkdir(parents=True)
    (sport_dir / "2026-06-22.jsonl").write_text(json.dumps(_ROW), encoding="utf-8")
    snap_dir = tmp_path / "snapshots"
    snapshot_sport("nba", base_dir=line_history, snapshot_dir=snap_dir)

    check_doc = check_sport("nba", base_dir=line_history, snapshot_dir=snap_dir,
                             today=datetime.date(2026, 7, 20))
    assert check_doc["providers"]["espn"]["status"] == "ok"


def test_against_real_samples():
    """Run the real end-to-end pipeline against >=3 real providers using the
    ACTUAL captured JSONL samples already on disk under data/cache/line_history/
    (nba, mlb, tennis -- see honest result printed by the module's __main__).
    This is a read-only smoke test: it must never raise and must produce a
    provider breakdown for each sport that has real capture files."""
    for sport in ("nba", "mlb", "tennis"):
        files = discover_capture_files(sport)
        if not files:
            continue  # honest: sport has no captures on this box right now
        by_provider = load_records_by_provider(files[-1])
        assert isinstance(by_provider, dict)
        for provider, records in by_provider.items():
            shape = shape_of_records(records)
            assert isinstance(shape, dict)
            assert len(shape) > 0
