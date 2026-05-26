"""tests/test_R27_T7_ledger_insurance.py — R27_T7 ledger insurance tests.

Covers ``scripts/ledger_insurance.py``:

* --backup creates compressed file + sidecar
* --backup --keep N rotates older backups
* --backup is idempotent within a day (overwrites; documented)
* --verify catches sha256 mismatch
* --restore --dry-run produces no side effects
* --restore requires explicit --commit
* --restore preserves pre-restore current state
* --restore is atomic (os.replace — never half-written)
* --list parses gzip correctly (row count + size)
* Concurrent backup attempts don't corrupt each other
* Sidecar tampering caught by --verify
* CLI happy-path end-to-end via main()

Ship gate: ≥10 tests, all must pass.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

# Importable without an editable install.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import ledger_insurance as li  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def ledger(tmp_path):
    """Synthetic ledger — 200 distinct rows so row-count + sha256 are tested."""
    p = tmp_path / "pnl_ledger.csv"
    rows = ["ts,bet_id,stake,result,pnl"]
    for i in range(200):
        rows.append(f"2026-05-26T12:00:00Z,bet{i:05d},10.0,W,9.09")
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return p


@pytest.fixture
def bdir(tmp_path):
    return tmp_path / "backups"


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. --backup creates compressed file + sidecar
# ---------------------------------------------------------------------------
def test_backup_creates_gz_and_sidecar(ledger, bdir):
    res = li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    assert res["ok"] is True
    gz = Path(res["gz_path"])
    assert gz.exists()
    assert gz.name == "pnl_ledger.csv.2026-05-26.gz"
    side = gz.with_suffix(gz.suffix + ".sha256")
    assert side.exists()
    # Sidecar pins source sha256.
    expected_sha = _sha256_of(ledger)
    assert side.read_text(encoding="utf-8").split()[0] == expected_sha
    assert res["sha256"] == expected_sha
    # Gzipped contents decode back to the source bytes.
    with gzip.open(gz, "rb") as fh:
        decompressed = fh.read()
    assert decompressed == ledger.read_bytes()


# ---------------------------------------------------------------------------
# 2. --backup --keep N rotates older backups
# ---------------------------------------------------------------------------
def test_backup_rotates_oldest(ledger, bdir):
    dates = [f"2026-05-{d:02d}" for d in range(1, 8)]   # 7 dates
    for d in dates:
        li.backup(ledger_path=ledger, backup_dir=bdir, today=d, keep=100)
    # All present.
    assert len(li.list_backups(bdir)) == 7
    # Now bump keep=3 — should drop the 4 oldest.
    res = li.backup(ledger_path=ledger, backup_dir=bdir,
                     today="2026-05-08", keep=3)
    assert res["ok"] is True
    remaining = sorted(e["date"] for e in li.list_backups(bdir))
    assert remaining == ["2026-05-06", "2026-05-07", "2026-05-08"]
    assert len(res["rotated"]) == 5  # 7 old + 1 new = 8 - keep 3 = 5 dropped
    # Sidecars also rotated.
    for date_str in ["2026-05-01", "2026-05-02", "2026-05-05"]:
        gz = bdir / f"pnl_ledger.csv.{date_str}.gz"
        assert not gz.exists()
        assert not gz.with_suffix(gz.suffix + ".sha256").exists()


# ---------------------------------------------------------------------------
# 3. --backup is idempotent within a day (overwrites cleanly)
# ---------------------------------------------------------------------------
def test_backup_idempotent_same_day(ledger, bdir):
    """Documented behaviour: a second --backup on the same date OVERWRITES.

    This is intentional — the morning cron may run twice (catch-up + real
    run) and we want a deterministic "snapshot of right now" each time
    rather than refusing or proliferating files.
    """
    res1 = li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    gz   = Path(res1["gz_path"])
    side = gz.with_suffix(gz.suffix + ".sha256")
    sha1 = side.read_text(encoding="utf-8")
    # Mutate the ledger between snapshots — second backup MUST reflect new hash.
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write("2026-05-26T13:00:00Z,bet99999,42.0,L,-42.0\n")
    res2 = li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    assert res2["ok"] is True
    assert Path(res2["gz_path"]) == gz   # same path
    sha2 = side.read_text(encoding="utf-8")
    assert sha1 != sha2                  # but new sidecar
    assert res2["sha256"] == _sha256_of(ledger)
    # Only one backup for that date — no .1, no .bak.
    files = [p for p in bdir.iterdir() if p.name.endswith(".gz")]
    assert len(files) == 1


# ---------------------------------------------------------------------------
# 4. --verify catches sha256 mismatch (rot)
# ---------------------------------------------------------------------------
def test_verify_catches_corruption(ledger, bdir):
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    # Pre-tamper: verify is clean.
    pre = li.verify(backup_dir=bdir)
    assert pre["ok"] is True and pre["n_fail"] == 0 and pre["n_ok"] == 1
    # Now flip a byte deep in the gz payload.
    gz = bdir / "pnl_ledger.csv.2026-05-26.gz"
    data = bytearray(gz.read_bytes())
    # Flip a byte well past the gzip header so decompression still works
    # but contents change.
    data[len(data) // 2] ^= 0x01
    gz.write_bytes(bytes(data))
    post = li.verify(backup_dir=bdir)
    assert post["ok"] is False
    assert post["n_fail"] == 1
    assert "mismatch" in (post["results"][0]["reason"] or "").lower() or \
           "decompress" in (post["results"][0]["reason"] or "").lower()


# ---------------------------------------------------------------------------
# 5. --restore --dry-run produces no side effects
# ---------------------------------------------------------------------------
def test_restore_dry_run_no_side_effects(ledger, bdir, tmp_path):
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    # Replace the live ledger with NEW content.
    new_ledger = tmp_path / "live_pnl_ledger.csv"
    new_ledger.write_text("ts,bet_id,stake,result,pnl\nLIVE_CONTENT\n",
                           encoding="utf-8")
    live_before = new_ledger.read_bytes()
    # Dry-run restore — must NOT mutate the live ledger.
    res = li.restore(date_str="2026-05-26", ledger_path=new_ledger,
                      backup_dir=bdir, commit=False)
    assert res["ok"] is True
    assert res["dry_run"] is True
    assert res["commit"] is False
    # No pre-restore copy made.
    pre_files = list(new_ledger.parent.glob(new_ledger.name + ".pre_restore_*"))
    assert pre_files == []
    # Live ledger untouched.
    assert new_ledger.read_bytes() == live_before


# ---------------------------------------------------------------------------
# 6. --restore requires --commit to actually write
# ---------------------------------------------------------------------------
def test_restore_requires_commit_to_write(ledger, bdir, tmp_path):
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    live = tmp_path / "live_pnl_ledger.csv"
    live.write_text("LIVE_CONTENT\n", encoding="utf-8")
    # commit=False → no write.
    li.restore(date_str="2026-05-26", ledger_path=live,
                backup_dir=bdir, commit=False)
    assert live.read_text(encoding="utf-8") == "LIVE_CONTENT\n"
    # commit=True → live now matches the backed-up source.
    res = li.restore(date_str="2026-05-26", ledger_path=live,
                      backup_dir=bdir, commit=True)
    assert res["ok"] is True
    assert res["dry_run"] is False
    assert live.read_bytes() == ledger.read_bytes()


# ---------------------------------------------------------------------------
# 7. --restore preserves pre-restore current state
# ---------------------------------------------------------------------------
def test_restore_preserves_pre_restore_copy(ledger, bdir, tmp_path):
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    live = tmp_path / "live_pnl_ledger.csv"
    live.write_text("PRE_RESTORE_CURRENT\n", encoding="utf-8")
    res = li.restore(date_str="2026-05-26", ledger_path=live,
                      backup_dir=bdir, commit=True)
    assert res["ok"] is True
    pre_path = Path(res["pre_restore_path"])
    assert pre_path.exists()
    assert pre_path.name.startswith(live.name + ".pre_restore_")
    assert pre_path.read_text(encoding="utf-8") == "PRE_RESTORE_CURRENT\n"
    # Live is the backed-up content.
    assert live.read_bytes() == ledger.read_bytes()


# ---------------------------------------------------------------------------
# 8. --restore is atomic (we get the FULL backup or the OLD file — never half)
# ---------------------------------------------------------------------------
def test_restore_is_atomic_via_os_replace(ledger, bdir, tmp_path, monkeypatch):
    """If os.replace fails, the live ledger stays at its pre-restore state.

    We simulate failure by making os.replace raise — the live ledger must
    NOT be left empty / half-written.
    """
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    live = tmp_path / "live_pnl_ledger.csv"
    live.write_text("ORIGINAL\n", encoding="utf-8")
    original_bytes = live.read_bytes()

    real_replace = os.replace
    calls = {"n": 0}

    def boom(src, dst):
        # Only blow up when restoring the actual live ledger — not when
        # the pre-restore copy is being created (we use shutil.copy2).
        if str(dst) == str(live):
            calls["n"] += 1
            raise OSError("simulated disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(li.os, "replace", boom)
    res = li.restore(date_str="2026-05-26", ledger_path=live,
                      backup_dir=bdir, commit=True)
    assert res["ok"] is False
    assert calls["n"] == 1
    # Live ledger NEVER half-overwritten.
    assert live.read_bytes() == original_bytes
    # No stray .tmp file left lying around.
    tmp_leftovers = [p for p in live.parent.iterdir()
                      if p.name.startswith(live.name + ".restore.")
                      and p.name.endswith(".tmp")]
    assert tmp_leftovers == []


# ---------------------------------------------------------------------------
# 9. --list parses gzip correctly (date + rows + size)
# ---------------------------------------------------------------------------
def test_list_parses_gzip(ledger, bdir):
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-24")
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-25")
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    out = li.list_backups(bdir)
    assert len(out) == 3
    # Sorted oldest-first.
    assert [e["date"] for e in out] == [
        "2026-05-24", "2026-05-25", "2026-05-26",
    ]
    for e in out:
        # Ledger fixture has 201 lines (header + 200 rows + trailing \n).
        assert e["row_count"] == 201
        assert e["size_bytes"] > 0
        assert e["has_sidecar"] is True
        assert len(e["sha256_short"]) == 16


# ---------------------------------------------------------------------------
# 10. Concurrent backups don't corrupt each other
# ---------------------------------------------------------------------------
def test_concurrent_backups_dont_corrupt(ledger, bdir):
    """Two threads writing to the SAME date must each produce a valid gz
    (the last one wins via os.replace; neither leaves a torn file)."""
    errors = []

    def runner():
        try:
            res = li.backup(
                ledger_path=ledger, backup_dir=bdir, today="2026-05-26",
            )
            if not res.get("ok"):
                errors.append(res.get("reason", "?"))
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=runner) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"backup errors: {errors}"
    # Exactly one final .gz for that date, and it round-trips.
    gz_files = list(bdir.glob("pnl_ledger.csv.2026-05-26.gz"))
    assert len(gz_files) == 1
    gz = gz_files[0]
    side = gz.with_suffix(gz.suffix + ".sha256")
    assert side.exists()
    # Decompressed contents EQUAL the source ledger.
    with gzip.open(gz, "rb") as fh:
        assert fh.read() == ledger.read_bytes()
    # Sidecar matches.
    expected = _sha256_of(ledger)
    assert side.read_text(encoding="utf-8").split()[0] == expected
    # No leftover .tmp files.
    leftovers = [p for p in bdir.iterdir() if ".tmp" in p.name]
    assert leftovers == []


# ---------------------------------------------------------------------------
# 11. Sidecar tampering caught
# ---------------------------------------------------------------------------
def test_verify_catches_sidecar_tampering(ledger, bdir):
    li.backup(ledger_path=ledger, backup_dir=bdir, today="2026-05-26")
    side = bdir / "pnl_ledger.csv.2026-05-26.gz.sha256"
    # Replace the recorded hash with a wrong one.
    side.write_text("0" * 64 + "  pnl_ledger.csv.2026-05-26\n",
                     encoding="utf-8")
    res = li.verify(backup_dir=bdir)
    assert res["ok"] is False
    assert res["n_fail"] == 1
    # Restore must also REFUSE on mismatch.
    rr = li.restore(date_str="2026-05-26",
                     ledger_path=bdir.parent / "fake.csv",
                     backup_dir=bdir, commit=True)
    assert rr["ok"] is False
    assert "mismatch" in (rr.get("reason") or "").lower()


# ---------------------------------------------------------------------------
# 12. CLI end-to-end: --backup, --list, --verify, --restore --dry-run
# ---------------------------------------------------------------------------
def test_cli_end_to_end(ledger, bdir, capsys):
    # --backup
    rc = li.main([
        "--backup",
        "--ledger-path", str(ledger),
        "--backup-dir",  str(bdir),
        "--today",       "2026-05-26",
        "--json",
    ])
    assert rc == 0
    cap = capsys.readouterr()
    payload = json.loads(cap.out)
    assert payload["ok"] is True
    # --list
    rc = li.main(["--list", "--backup-dir", str(bdir), "--json"])
    assert rc == 0
    cap = capsys.readouterr()
    listing = json.loads(cap.out)
    assert len(listing) == 1
    assert listing[0]["date"] == "2026-05-26"
    # --verify
    rc = li.main(["--verify", "--backup-dir", str(bdir), "--json"])
    assert rc == 0
    cap = capsys.readouterr()
    v = json.loads(cap.out)
    assert v["ok"] is True and v["n_ok"] == 1
    # --restore (dry-run is the default)
    rc = li.main([
        "--restore", "2026-05-26",
        "--ledger-path", str(ledger),
        "--backup-dir",  str(bdir),
        "--json",
    ])
    assert rc == 0
    cap = capsys.readouterr()
    rr = json.loads(cap.out)
    assert rr["ok"] is True and rr["dry_run"] is True
