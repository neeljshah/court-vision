"""tests/test_R31_X4_archive_probes.py — R31_X4 archiver tests.

Ship gate: >=8 tests, all pass.

Covers:
  1.  Archive --commit creates valid tar.gz that opens.
  2.  Sidecar sha256 matches the archive's actual digest.
  3.  --restore round-trips file contents exactly.
  4.  --keep N preserves last N (min_keep + young files).
  5.  --commit required for deletion (dry-run leaves originals).
  6.  Dry-run produces no side effects on disk.
  7.  list_archives parses tar metadata correctly.
  8.  Concurrent archive attempts: second call locks out.
  9.  verify catches corruption.
 10.  Restore refuses path-traversal members.
 11.  Archive integrates into nightly_cleanup as 'archive_probes' category.
"""
from __future__ import annotations

import json
import os
import sys
import tarfile
import time
from pathlib import Path

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import archive_probe_results as apr  # noqa: E402
from scripts import nightly_cleanup as nc  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _touch(path: Path, days_old: float = 0.0, content: bytes = b"{}") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if days_old > 0:
        mt = time.time() - days_old * 86400.0
        os.utime(path, (mt, mt))
    return path


def _mk_repo(tmp_path: Path, n_old: int = 6, n_fresh: int = 2) -> Path:
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for i in range(n_old):
        _touch(cache / f"probe_R{i:02d}_OLD_results.json",
               days_old=30.0 + i,
               content=json.dumps({"probe": f"R{i}", "ship_ok": True}).encode())
    for i in range(n_fresh):
        _touch(cache / f"probe_R99_FRESH{i}_results.json",
               days_old=float(i),
               content=json.dumps({"probe": f"FRESH{i}"}).encode())
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Archive --commit creates a valid tar.gz that opens
# ---------------------------------------------------------------------------
def test_archive_commit_creates_valid_tar(tmp_path):
    root = _mk_repo(tmp_path, n_old=6, n_fresh=0)
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=True)
    arc = Path(res["archive"])
    assert arc.exists(), "archive not written"
    # tarfile must open it cleanly.
    with tarfile.open(str(arc), "r:gz") as tf:
        names = tf.getnames()
    assert len(names) == 6
    assert res["n_archived"] == 6
    assert res["n_deleted"] == 6


# ---------------------------------------------------------------------------
# 2. Sidecar sha256 matches the on-disk archive digest
# ---------------------------------------------------------------------------
def test_sidecar_sha256_matches(tmp_path):
    root = _mk_repo(tmp_path, n_old=3, n_fresh=0)
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=True)
    arc = Path(res["archive"])
    sidecar = arc.with_suffix(arc.suffix + ".sha256")
    assert sidecar.exists()
    expected = apr.read_sidecar_digest(sidecar)
    actual = apr.sha256_file(arc)
    assert expected == actual
    # verify_archive agrees.
    ver = apr.verify_archive(arc)
    assert ver["ok"] is True
    assert ver["reason"] == "match"


# ---------------------------------------------------------------------------
# 3. --restore round-trips file contents exactly
# ---------------------------------------------------------------------------
def test_restore_round_trips(tmp_path):
    root = _mk_repo(tmp_path, n_old=4, n_fresh=0)
    cache = root / "data" / "cache"
    # Capture originals before archive.
    originals = {p.name: p.read_bytes()
                 for p in cache.glob("probe_R*_results.json")}
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=True)
    arc = Path(res["archive"])
    # All originals must be gone post-commit.
    for name in originals:
        assert not (cache / name).exists()
    # Restore back.
    rr = apr.restore_archive(arc, cache_dir=cache, overwrite=False)
    assert rr["ok"] is True
    assert rr["n_extracted"] == len(originals)
    for name, content in originals.items():
        restored = (cache / name).read_bytes()
        assert restored == content, f"content mismatch on {name}"


# ---------------------------------------------------------------------------
# 4. --keep N preserves last N regardless of age
# ---------------------------------------------------------------------------
def test_min_keep_preserves_youngest(tmp_path):
    root = _mk_repo(tmp_path, n_old=10, n_fresh=0)
    # min_keep=3 should leave the 3 youngest (still 30-32d old) intact.
    res = apr.archive_probes(root=root, keep_days=7, min_keep=3, commit=False)
    assert res["n_eligible"] == 7


def test_keep_days_threshold(tmp_path):
    root = _mk_repo(tmp_path, n_old=0, n_fresh=0)
    cache = root / "data" / "cache"
    # 5 files <7d, 5 files >7d.
    for i in range(5):
        _touch(cache / f"probe_RY{i}_results.json", days_old=float(i))
    for i in range(5):
        _touch(cache / f"probe_RO{i}_results.json", days_old=10.0 + i)
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=False)
    assert res["n_eligible"] == 5


# ---------------------------------------------------------------------------
# 5. --commit required for deletion / dry-run safety
# ---------------------------------------------------------------------------
def test_dry_run_no_deletion(tmp_path):
    root = _mk_repo(tmp_path, n_old=5, n_fresh=0)
    cache = root / "data" / "cache"
    before = sorted(p.name for p in cache.glob("probe_R*_results.json"))
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=False)
    after = sorted(p.name for p in cache.glob("probe_R*_results.json"))
    assert before == after, "dry-run mutated cache"
    assert res["n_eligible"] == 5
    # No archive on disk either.
    assert not (root / "data" / "archives").exists() or not any(
        (root / "data" / "archives").glob("probe_results_*.tar.gz")
    )


def test_dry_run_no_archive_file(tmp_path):
    root = _mk_repo(tmp_path, n_old=3, n_fresh=0)
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=False)
    # Archive path is reported but file should NOT exist.
    arc = Path(res["archive"])
    assert not arc.exists()


# ---------------------------------------------------------------------------
# 6. list_archives parses tar metadata correctly
# ---------------------------------------------------------------------------
def test_list_archives_parses_metadata(tmp_path):
    root = _mk_repo(tmp_path, n_old=4, n_fresh=0)
    apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=True)
    archives = apr.list_archives(root)
    assert len(archives) == 1
    meta = archives[0]
    assert meta["n_files"] == 4
    assert meta["sha256"] is not None
    assert len(meta["sha256"]) == 64
    assert meta["size_mb"] > 0.0


# ---------------------------------------------------------------------------
# 7. Concurrent archive attempts: lock blocks the second caller
# ---------------------------------------------------------------------------
def test_concurrent_archive_locked(tmp_path):
    root = _mk_repo(tmp_path, n_old=3, n_fresh=0)
    arch_dir = root / "data" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    # Pre-acquire the lock the next archive would attempt.
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lock = arch_dir / f"probe_results_{stamp}.tar.gz.lock"
    lock.write_text("99999")  # foreign PID
    try:
        res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=True)
        # Lock prevents archive creation; warns and skips deletion.
        assert any("locked" in w for w in res.get("warnings", []))
        assert res.get("n_archived", 0) == 0
        assert res.get("n_deleted", 0) == 0
        # Originals must still be on disk.
        assert len(list((root / "data" / "cache").glob("probe_R*_results.json"))) == 3
    finally:
        lock.unlink()


# ---------------------------------------------------------------------------
# 8. verify catches corruption
# ---------------------------------------------------------------------------
def test_verify_detects_corruption(tmp_path):
    root = _mk_repo(tmp_path, n_old=3, n_fresh=0)
    res = apr.archive_probes(root=root, keep_days=7, min_keep=0, commit=True)
    arc = Path(res["archive"])
    # Append one extra byte to corrupt the digest.
    with open(arc, "ab") as fh:
        fh.write(b"X")
    ver = apr.verify_archive(arc)
    assert ver["ok"] is False
    assert ver["reason"] == "mismatch"


# ---------------------------------------------------------------------------
# 9. Restore refuses path-traversal members
# ---------------------------------------------------------------------------
def test_restore_blocks_path_traversal(tmp_path):
    # Build a malicious tarball by hand.
    arch_dir = tmp_path / "data" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    mal = arch_dir / "probe_results_evil.tar.gz"
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    safe_payload = b'{"ok": true}'
    with tarfile.open(str(mal), "w:gz") as tf:
        info = tarfile.TarInfo(name="../../evil_outside.json")
        info.size = len(safe_payload)
        import io as _io
        tf.addfile(info, _io.BytesIO(safe_payload))
        info2 = tarfile.TarInfo(name="probe_safe_results.json")
        info2.size = len(safe_payload)
        tf.addfile(info2, _io.BytesIO(safe_payload))
    rr = apr.restore_archive(mal, cache_dir=cache, overwrite=False)
    assert rr["ok"] is True
    # The traversal member must have been skipped.
    assert not (tmp_path.parent / "evil_outside.json").exists()
    assert not (tmp_path / "evil_outside.json").exists()
    assert (cache / "probe_safe_results.json").exists()
    assert rr["n_extracted"] == 1
    assert rr["n_skipped"] >= 1


# ---------------------------------------------------------------------------
# 10. nightly_cleanup integration — 'archive_probes' category present
# ---------------------------------------------------------------------------
def test_nightly_cleanup_runs_archive_probes_category(tmp_path):
    # n_old must exceed DEFAULT_MIN_KEEP (5) for any to be eligible.
    n_old = apr.DEFAULT_MIN_KEEP + 4
    root = _mk_repo(tmp_path, n_old=n_old, n_fresh=0)
    res = nc.run_cleanup(
        root=root, commit=False, include_worktrees=False,
        only_category="archive_probes",
    )
    assert "archive_probes" in res["per_category"]
    info = res["per_category"]["archive_probes"]
    # n_old - min_keep eligible (4).
    assert info["n_eligible"] == 4
    assert info["glob_pattern"] == "data/cache/probe_R*_results.json"


def test_nightly_cleanup_archive_probes_commit_path(tmp_path):
    n_old = apr.DEFAULT_MIN_KEEP + 4
    root = _mk_repo(tmp_path, n_old=n_old, n_fresh=0)
    res = nc.run_cleanup(
        root=root, commit=True, include_worktrees=False,
        only_category="archive_probes",
    )
    info = res["per_category"]["archive_probes"]
    # On commit the archiver returns n_archived; min_keep youngest remain.
    assert info.get("n_archived", 0) == 4
    leftover = list((root / "data" / "cache").glob("probe_R*_results.json"))
    assert len(leftover) == apr.DEFAULT_MIN_KEEP
    # Archive exists.
    arch = list((root / "data" / "archives").glob("probe_results_*.tar.gz"))
    assert len(arch) == 1


# ---------------------------------------------------------------------------
# 11. CLI happy-path via main() — --list returns 0
# ---------------------------------------------------------------------------
def test_cli_list_empty(tmp_path, capsys):
    rc = apr.main(["--list", "--json", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    # No archives yet -> empty list rendered as "[]"
    assert out == "[]"


def test_cli_archive_dry_run(tmp_path, capsys):
    # n_old must exceed DEFAULT_MIN_KEEP (5) for any to be eligible
    # with the CLI's default min_keep.
    n_old = apr.DEFAULT_MIN_KEEP + 3
    root = _mk_repo(tmp_path, n_old=n_old, n_fresh=0)
    rc = apr.main(["--archive", "--root", str(root), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["commit"] is False
    assert payload["n_eligible"] == 3
    # No archive on disk because no --commit.
    assert not (root / "data" / "archives").exists() or not list(
        (root / "data" / "archives").glob("probe_results_*.tar.gz")
    )
