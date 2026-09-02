"""Construct tests for measurement-time provenance and the opt-in claim gate."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate.gate_manifest import (
    StaleEvidence,
    assert_fresh,
    build_manifest,
    main,
    render_table,
)


def _ledger(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "cache" / "eval_gate"
    path.mkdir(parents=True)
    return path


def test_fresh_field_timestamp_passes_claim_gate(tmp_path):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    path = _ledger(tmp_path) / "fresh.json"
    path.write_text(json.dumps({"generated_at": (as_of - timedelta(days=1)).isoformat()}),
                    encoding="ascii")

    row = build_manifest(tmp_path, as_of=as_of)["rows"][0]
    assert row["measured_at_source"] == "field:generated_at"
    assert_fresh({"rows": [row]}, 30)


def test_stale_field_timestamp_beats_current_mtime_and_blocks(tmp_path):
    as_of = datetime.now(timezone.utc)
    path = _ledger(tmp_path) / "old.json"
    old = as_of - timedelta(days=400)
    path.write_text(json.dumps({"generated_at": old.isoformat()}), encoding="ascii")

    manifest = build_manifest(tmp_path, as_of=as_of)
    row = manifest["rows"][0]
    assert row["mtime"] and row["measured_at"] == old.isoformat()
    assert row["measured_at_source"] == "field:generated_at"
    with pytest.raises(StaleEvidence, match="old.json"):
        assert_fresh(manifest, 30)

    default_out = tmp_path / "default-manifest.json"
    assert main(["--repo-root", str(tmp_path), "--out", str(default_out),
                 "--as-of", as_of.isoformat()]) == 0
    assert json.loads(default_out.read_text(encoding="ascii"))["rows"][0]["status"] == "OK"

    out = tmp_path / "manifest.json"
    assert main(["--repo-root", str(tmp_path), "--out", str(out), "--as-of", as_of.isoformat(),
                 "--max-age-days", "30"]) == 1
    # S45(a): staleness is its own flag; status keeps saying what the file IS.
    written = json.loads(out.read_text(encoding="ascii"))["rows"][0]
    assert written["status"] == "OK" and written["stale"] is True


def test_mtime_only_and_unreadable_artifacts_are_stale(tmp_path):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    root = _ledger(tmp_path)
    (root / "unstamped.json").write_text(json.dumps({"verdict": "ACCEPT"}), encoding="ascii")
    (root / "corrupt.json").write_text("{not json", encoding="ascii")

    manifest = build_manifest(tmp_path, as_of=as_of)
    rows = {row["name"]: row for row in manifest["rows"]}
    assert rows["unstamped.json"]["measured_at_source"] == "mtime"
    assert rows["corrupt.json"]["status"] == "UNREADABLE"
    with pytest.raises(StaleEvidence) as exc:
        assert_fresh(manifest, 30)
    assert "unstamped.json" in str(exc.value) and "corrupt.json" in str(exc.value)


def test_no_max_age_keeps_master_status_and_staleness_behavior(tmp_path):
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    root = _ledger(tmp_path)
    stamped = root / "stamped.json"
    stamped.write_text(json.dumps({"as_of": "2026-08-01T00:00:00+00:00"}), encoding="ascii")
    plain = root / "plain.json"
    plain.write_text(json.dumps({"verdict": "ACCEPT"}), encoding="ascii")
    (root / "empty.json").write_text("", encoding="ascii")
    (root / "bad.json").write_text("{not json", encoding="ascii")

    manifest = build_manifest(tmp_path, as_of=as_of)
    rows = {row["name"]: row for row in manifest["rows"]}
    assert {name: row["status"] for name, row in rows.items()} == {
        "stamped.json": "OK", "plain.json": "OK", "empty.json": "EMPTY", "bad.json": "UNREADABLE"}
    assert rows["stamped.json"]["staleness_days"] == 31.0
    assert rows["plain.json"]["staleness_days"] == round(
        (as_of - datetime.fromtimestamp(plain.stat().st_mtime, tz=timezone.utc)).total_seconds() / 86400.0, 2)

    out = tmp_path / "manifest.json"
    assert main(["--repo-root", str(tmp_path), "--out", str(out), "--as-of", as_of.isoformat()]) == 1
    written = json.loads(out.read_text(encoding="ascii"))
    assert {row["name"]: row["status"] for row in written["rows"]} == {
        name: row["status"] for name, row in rows.items()}


# --- S45 + RT-7 follow-ups (2026-09-03) -------------------------------------

def test_stale_flag_does_not_erase_unreadable_or_empty_status(tmp_path):
    """S45(a): --max-age-days used to overwrite status with STALE, hiding an
    unparseable artifact from every reader that counts UNREADABLE."""
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    root = _ledger(tmp_path)
    (root / "corrupt.json").write_text("{not json", encoding="ascii")
    (root / "empty.json").write_text("", encoding="ascii")
    (root / "old.json").write_text(
        json.dumps({"generated_at": (as_of - timedelta(days=400)).isoformat()}), encoding="ascii")

    out = tmp_path / "manifest.json"
    assert main(["--repo-root", str(tmp_path), "--out", str(out),
                 "--as-of", as_of.isoformat(), "--max-age-days", "30"]) == 1
    written = json.loads(out.read_text(encoding="ascii"))
    rows = {row["name"]: row for row in written["rows"]}
    assert {name: row["status"] for name, row in rows.items()} == {
        "corrupt.json": "UNREADABLE", "empty.json": "EMPTY", "old.json": "OK"}
    assert all(row["stale"] is True for row in rows.values())
    assert written["summary"]["unreadable"] == 1 and written["summary"]["empty"] == 1
    assert written["summary"]["stale"] == 3
    # S45(b): the count a human reads, and the status counts still sum to TOTAL.
    footer = render_table(written).splitlines()[-1]
    assert "STALE=3" in footer and "UNREADABLE=1" in footer and "EMPTY=1" in footer


def test_future_self_declared_timestamp_is_invalid_not_fresh(tmp_path):
    """RT-7: as_of=2031-01-01 gave staleness -1581.0 days and status OK forever."""
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    root = _ledger(tmp_path)
    (root / "future.json").write_text(
        json.dumps({"generated_at": "2031-01-01T00:00:00+00:00"}), encoding="ascii")
    (root / "skew.json").write_text(  # inside the clock-skew tolerance -> still fresh
        json.dumps({"generated_at": (as_of + timedelta(hours=6)).isoformat()}), encoding="ascii")

    manifest = build_manifest(tmp_path, as_of=as_of)
    rows = {row["name"]: row for row in manifest["rows"]}
    assert rows["future.json"]["measured_at_invalid"] == "future"
    assert rows["future.json"]["staleness_days"] < 0
    assert rows["skew.json"]["measured_at_invalid"] is None
    with pytest.raises(StaleEvidence, match="future.json"):
        assert_fresh(manifest, 30)
    assert_fresh({"rows": [rows["skew.json"]]}, 30)

    out = tmp_path / "manifest.json"
    assert main(["--repo-root", str(tmp_path), "--out", str(out),
                 "--as-of", as_of.isoformat(), "--max-age-days", "3650"]) == 1
    written = {r["name"]: r for r in json.loads(out.read_text(encoding="ascii"))["rows"]}
    assert written["future.json"]["stale"] is True
    assert written["skew.json"]["stale"] is False
    assert "FUTUR" in render_table({"rows": list(written.values()), "summary":
                                    {"total": 2, "ok": 2, "empty": 0, "unreadable": 0,
                                     "stale": 1}, "as_of": as_of.isoformat()})
