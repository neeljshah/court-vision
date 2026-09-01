"""Tests for gate_manifest: tmp-dir fixtures covering readable, corrupt, empty,
and missing artifacts, plus the dedicated lock/null-ship and evidence globs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate import gate_manifest as gm
from scripts.platformkit.eval_gate.gate_manifest import build_manifest, main, render_table

_AS_OF = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _mk(repo_root: Path) -> None:
    (repo_root / "data" / "cache" / "eval_gate").mkdir(parents=True)
    (repo_root / "docs" / "evidence").mkdir(parents=True)


def test_missing_dirs_tolerated(tmp_path):
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert m["rows"] == []
    assert m["summary"] == {"total": 0, "ok": 0, "empty": 0, "unreadable": 0}


def test_readable_ledger_row_and_staleness(tmp_path):
    _mk(tmp_path)
    p = tmp_path / "data" / "cache" / "eval_gate" / "combo_fwer.json"
    p.write_text(json.dumps({"verdict": "MATCHES_CLOSE", "as_of": "2026-08-01"}),
                 encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert len(m["rows"]) == 1
    row = m["rows"][0]
    assert row["status"] == "OK"
    assert row["verdict"] == "MATCHES_CLOSE"
    assert row["category"] == "ledger"
    assert row["staleness_days"] == 31.0
    assert m["summary"]["ok"] == 1


def test_corrupt_artifact_is_unreadable_and_fails_closed(tmp_path):
    _mk(tmp_path)
    p = tmp_path / "data" / "cache" / "eval_gate" / "bad.json"
    p.write_text("{not json", encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert len(m["rows"]) == 1  # never dropped
    assert m["rows"][0]["status"] == "UNREADABLE"
    assert m["rows"][0]["error"]
    assert m["summary"]["unreadable"] == 1


def test_empty_file_is_empty_status(tmp_path):
    _mk(tmp_path)
    p = tmp_path / "data" / "cache" / "eval_gate" / "empty.json"
    p.write_text("", encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert m["rows"][0]["status"] == "EMPTY"
    assert m["summary"]["empty"] == 1


def test_evidence_glob_recurses_and_tolerates_absence(tmp_path):
    _mk(tmp_path)
    nested = tmp_path / "docs" / "evidence" / "calibration"
    nested.mkdir()
    (nested / "sweep.json").write_text(json.dumps({"status": "done"}), encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert any(r["category"] == "evidence" for r in m["rows"])


def test_null_ship_and_lock_glob_anywhere_under_data_cache(tmp_path):
    _mk(tmp_path)
    deep = tmp_path / "data" / "cache" / "autoloop"
    deep.mkdir(parents=True)
    (deep / "null_ship_run.json").write_text(json.dumps({"verdict": "REJECT"}), encoding="ascii")
    (deep / "combo_lock_state.json").write_text(json.dumps({"verdict": "SHIP"}), encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    cats = {r["name"]: r["category"] for r in m["rows"]}
    assert cats == {"null_ship_run.json": "lock_or_null_ship",
                    "combo_lock_state.json": "lock_or_null_ship"}


def test_jsonl_ledger_uses_last_row_and_renders(tmp_path):
    _mk(tmp_path)
    p = tmp_path / "data" / "cache" / "eval_gate" / "backtest_charges.jsonl"
    p.write_text(json.dumps({"at": "2026-07-01", "verdict": "SHIP"}) + "\n"
                 + json.dumps({"at": "2026-08-15", "verdict": "REJECT"}) + "\n",
                 encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    row = m["rows"][0]
    assert row["verdict"] == "REJECT"  # last row wins
    table = render_table(m)
    assert "REJECT" in table and "TOTAL=1" in table


def test_no_double_count_when_ledger_file_also_matches_lock_glob(tmp_path):
    _mk(tmp_path)
    p = tmp_path / "data" / "cache" / "eval_gate" / "combo_lock.json"
    p.write_text(json.dumps({"verdict": "SHIP"}), encoding="ascii")
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert len(m["rows"]) == 1  # deduped, not counted under both globs
    assert m["rows"][0]["category"] == "ledger"  # first-seen category wins


# --- adversarial review 2026-09-01: swallowed artifacts + staleness/tz ---


def test_naive_as_of_is_read_as_utc_not_a_typeerror(tmp_path):
    # Was: a caller passing a plain datetime(...) with no tzinfo blew up the whole
    # build with "can't subtract offset-naive and offset-aware datetimes".
    _mk(tmp_path)
    p = tmp_path / "data" / "cache" / "eval_gate" / "l.json"
    p.write_text(json.dumps({"as_of": "2026-08-01T00:00:00+00:00"}), encoding="ascii")
    naive = build_manifest(tmp_path, as_of=datetime(2026, 9, 1))
    assert naive["rows"][0]["staleness_days"] == 31.0
    assert naive["rows"][0]["staleness_days"] == build_manifest(
        tmp_path, as_of=_AS_OF
    )["rows"][0]["staleness_days"]


def test_offset_aware_as_of_field_is_not_double_counted(tmp_path):
    # Same instant written in three zones must yield the same staleness; a naive
    # string is the only one read as UTC.
    _mk(tmp_path)
    d = tmp_path / "data" / "cache" / "eval_gate"
    for i, stamp in enumerate(
        ["2026-08-31T00:00:00+00:00", "2026-08-30T20:00:00-04:00", "2026-08-31T00:00:00Z"]
    ):
        (d / f"z{i}.json").write_text(json.dumps({"as_of": stamp}), encoding="ascii")
    stale = {r["staleness_days"] for r in build_manifest(tmp_path, as_of=_AS_OF)["rows"]}
    assert stale == {1.0}


def test_vanished_file_becomes_a_row_not_a_crash(tmp_path, monkeypatch):
    # Was: stat() sat OUTSIDE the try, so one file disappearing between the scan
    # and its row killed every other row with FileNotFoundError.
    _mk(tmp_path)
    ghost = tmp_path / "data" / "cache" / "eval_gate" / "ghost.json"
    ghost.write_text(json.dumps({"verdict": "SHIP"}), encoding="ascii")
    keep = tmp_path / "data" / "cache" / "eval_gate" / "keep.json"
    keep.write_text(json.dumps({"verdict": "REJECT"}), encoding="ascii")

    real_scan = gm._scan

    def scan_then_delete(root, bad_dirs, exclude=None):
        found = real_scan(root, bad_dirs, exclude=exclude)
        ghost.unlink()
        return found

    monkeypatch.setattr(gm, "_scan", scan_then_delete)
    m = build_manifest(tmp_path, as_of=_AS_OF)
    by_name = {r["name"]: r for r in m["rows"]}
    assert by_name["ghost.json"]["status"] == "UNREADABLE"
    assert by_name["ghost.json"]["staleness_days"] is None
    assert by_name["keep.json"]["verdict"] == "REJECT"  # survivor still reported
    assert m["summary"]["unreadable"] == 1
    assert "-" in render_table(m)  # None staleness renders, does not raise


def test_untraversable_dir_is_recorded_not_silently_dropped(tmp_path, monkeypatch):
    # pathlib.rglob returns silently on PermissionError, dropping a whole evidence
    # subtree with no trace. os.walk + onerror must surface it as UNREADABLE.
    _mk(tmp_path)
    real_walk = gm.os.walk

    def walk_with_denial(root, onerror=None, **kw):
        if str(root).replace("\\", "/").endswith("docs/evidence"):
            onerror(PermissionError(13, "Permission denied", str(root)))
            return iter(())
        return real_walk(root, onerror=onerror, **kw)

    monkeypatch.setattr(gm.os, "walk", walk_with_denial)
    m = build_manifest(tmp_path, as_of=_AS_OF)
    assert m["summary"]["unreadable"] == 1
    assert m["rows"][0]["category"] == "scan_error"
    assert "Permission denied" in m["rows"][0]["error"]


def test_cli_rejects_unparseable_as_of_instead_of_defaulting_to_now(tmp_path):
    # Was: _parse_dt returned None and build_manifest silently used now(), so a
    # typo'd --as-of produced a manifest whose every staleness was wrong, exit 0.
    _mk(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["--repo-root", str(tmp_path), "--out", str(tmp_path / "m.json"),
              "--as-of", "not-a-real-date"])
    assert exc.value.code == 2  # argparse usage error, not a silent success


def test_manifest_does_not_audit_its_own_output(tmp_path):
    # Run twice into the default ledger dir: the manifest must not ingest the
    # previous run's manifest as a "ledger" artifact.
    _mk(tmp_path)
    out = tmp_path / "data" / "cache" / "eval_gate" / "gate_manifest.json"
    assert main(["--repo-root", str(tmp_path), "--out", str(out)]) == 0
    assert main(["--repo-root", str(tmp_path), "--out", str(out)]) == 0
    second = json.loads(out.read_text(encoding="ascii"))
    assert second["rows"] == []
    assert second["summary"]["total"] == 0
