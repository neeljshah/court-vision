"""S29: the FWER-ledger backup is restorable, tamper-evident and read-only.

Every case runs on a SYNTHETIC 13-row ledger under tmp_path. The real
data/cache/eval_gate/backtest_fwer.jsonl is never opened by this file.

Non-tautology: cases 2 and 3 are the ones a lenient rule would drop -- a backup that
cannot notice a tampered byte or a shrinking ledger proves nothing. The row-count and
k_cumulative checks run on the COPY, so a bad night can never be hidden by editing
the source.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.eval_gate.ledger_backup import backup, latest, verify

ROWS = 13


def _write_ledger(src_dir: Path, n: int = ROWS) -> Path:
    src_dir.mkdir(parents=True, exist_ok=True)
    p = src_dir / "backtest_fwer.jsonl"
    p.write_text("".join(
        json.dumps({"at": f"2026-09-0{1 + i % 9}T00:00:00+00:00", "predictor": f"p{i}",
                    "sport": "basketball_nba", "start": "2023-10-01",
                    "end": "2024-04-01", "k_cumulative": i + 1}) + "\n"
        for i in range(n)), "ascii")
    (src_dir / "gate_manifest.json").write_text('{"rows": 19}\n', "ascii")
    (src_dir / "hedge_trial_2026-09-01.json").write_text('{"trial": 1}\n', "ascii")
    return p


def _sha_mtime(p: Path):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


def test_backup_manifest_verifies_ok(tmp_path):
    src, out = tmp_path / "cache", tmp_path / "backups"
    _write_ledger(src)
    m = backup(src, out, now_iso="2026-09-01T03:00:00+00:00")

    assert m["ledger"] == {"rows": ROWS, "k_cumulative_max": ROWS, "k_monotone": True}
    assert set(m["files"]) == {"backtest_fwer.jsonl", "gate_manifest.json",
                               "hedge_trial_2026-09-01.json"}
    assert m["absent"] == ["hypotheses.sqlite"]   # S15 has not landed: recorded, not an error
    assert m["warn"] == [] and m["prior_night"] is None
    assert latest(out) == out / "2026-09-01"

    v = verify(out / "2026-09-01")
    assert v["ok"] and set(v["files"].values()) == {"OK"}


def test_tampered_backup_reports_mismatch(tmp_path):
    src, out = tmp_path / "cache", tmp_path / "backups"
    _write_ledger(src)
    backup(src, out, now_iso="2026-09-01T03:00:00+00:00")

    copy = out / "2026-09-01" / "backtest_fwer.jsonl"
    copy.write_bytes(copy.read_bytes().replace(b"basketball_nba", b"basketball_nbX", 1))

    v = verify(out / "2026-09-01")
    assert not v["ok"]
    assert v["files"]["backtest_fwer.jsonl"] == "MISMATCH"
    assert v["files"]["gate_manifest.json"] == "OK"


def test_shrunk_source_is_flagged_not_blocked(tmp_path):
    src, out = tmp_path / "cache", tmp_path / "backups"
    _write_ledger(src)
    backup(src, out, now_iso="2026-09-01T03:00:00+00:00")

    _write_ledger(src, n=9)                       # a bad write lost four rows
    m = backup(src, out, now_iso="2026-09-02T03:00:00+00:00")

    assert m["prior_night"] == "2026-09-01"
    assert m["ledger"]["rows"] == 9
    assert any(w.startswith("ROWS_SHRANK: 13 -> 9") for w in m["warn"])
    assert any(w.startswith("K_REGRESSED: 13 -> 9") for w in m["warn"])
    assert all("2026-09-01 -> 2026-09-02" in w for w in m["warn"])
    assert verify(out / "2026-09-02")["ok"]       # flagged, still a usable copy


def test_same_day_rerun_overwrites_cleanly(tmp_path):
    src, out = tmp_path / "cache", tmp_path / "backups"
    _write_ledger(src)
    backup(src, out, now_iso="2026-09-01T03:00:00+00:00")
    (out / "2026-09-01" / "stale.txt").write_text("leftover\n", "ascii")

    _write_ledger(src, n=14)
    m = backup(src, out, now_iso="2026-09-01T21:00:00+00:00")

    assert m["prior_night"] is None               # today's own dir is not its own prior
    assert m["warn"] == [] and m["ledger"]["rows"] == 14
    assert not (out / "2026-09-01" / "stale.txt").exists()
    assert not (out / "2026-09-01.tmp").exists()
    assert [p.name for p in out.iterdir()] == ["2026-09-01"]
    assert verify(out / "2026-09-01")["ok"]


def test_source_is_byte_identical_throughout(tmp_path):
    src, out = tmp_path / "cache", tmp_path / "backups"
    ledger = _write_ledger(src)
    before = _sha_mtime(ledger)

    backup(src, out, now_iso="2026-09-01T03:00:00+00:00")
    backup(src, out, now_iso="2026-09-01T21:00:00+00:00")     # same-day rerun
    backup(src, out, now_iso="2026-09-02T03:00:00+00:00")
    verify(out / "2026-09-02")

    assert _sha_mtime(ledger) == before
    assert not (src / "backtest_fwer.jsonl.lock").exists()    # the lock was never taken
    m = json.loads((out / "2026-09-02" / "manifest.json").read_text("ascii"))
    assert m["source_sha256_before"] == m["source_sha256_after"] == before[0]
    assert m["files"]["backtest_fwer.jsonl"]["sha256"] == before[0]
