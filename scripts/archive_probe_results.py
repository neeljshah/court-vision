"""archive_probe_results.py — R31_X4 probe-results archiver.

Bundles old ``data/cache/probe_R*_results.json`` files into a single
``data/archives/probe_results_<YYYY-MM-DD>.tar.gz`` with an adjacent
``.sha256`` sidecar. Each file's historical value is preserved while the
active ``data/cache/`` directory stays scannable.

Modes
-----
* ``--archive``            : gather files older than ``--keep`` days (default
  7), tar.gz them, write sha256 sidecar, atomic rename. Dry-run unless
  ``--commit`` is set (commit deletes originals only after the archive
  re-verifies).
* ``--list``               : enumerate existing archives (date, n_files, MB).
* ``--restore <archive>``  : extract a single archive back into
  ``data/cache/``.
* ``--verify [archive]``   : re-hash + compare against sidecar.

Hard rules
----------
* Never auto-deletes without ``--commit``.
* Never touches files younger than ``--keep`` days.
* Always preserves the youngest ``--min-keep`` files regardless of age.
* Concurrency-safe: a ``.lock`` sentinel beside the archive path prevents
  two ``--archive`` runs from racing.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

PROBE_GLOB = "probe_R*_results.json"
DEFAULT_CACHE_DIR = "data/cache"
DEFAULT_ARCHIVE_DIR = "data/archives"
DEFAULT_KEEP_DAYS = 7
DEFAULT_MIN_KEEP = 5
SHA_BUF = 1024 * 1024  # 1 MiB streaming hash


# ---------------------------------------------------------------------------
# hashing + atomic write helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """Streaming sha256 hex digest of `path`."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(SHA_BUF)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def write_sidecar(archive: Path, digest: str, n_files: int) -> Path:
    """Write ``<archive>.sha256`` with digest + metadata. Returns sidecar path."""
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    payload = (
        f"{digest}  {archive.name}\n"
        f"# n_files: {n_files}\n"
        f"# created: {datetime.now(timezone.utc).isoformat()}\n"
    )
    tmp = sidecar.with_suffix(sidecar.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, sidecar)
    return sidecar


def read_sidecar_digest(sidecar: Path) -> Optional[str]:
    """Parse first sha256 from a sidecar; None on parse error."""
    try:
        first = sidecar.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    tok = first.split()
    if not tok or len(tok[0]) != 64:
        return None
    return tok[0]


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------
@dataclass
class FileRec:
    path:     Path
    age_days: float
    size:     int


def _age_days(path: Path, now: float) -> float:
    try:
        return (now - path.stat().st_mtime) / 86400.0
    except OSError:
        return -1.0


def discover(
    cache_dir: Path, *, keep_days: int, min_keep: int, now: Optional[float] = None,
) -> Tuple[List[FileRec], List[FileRec]]:
    """Split probe files into (eligible, preserved).

    `eligible` = age > keep_days AND not in youngest `min_keep`.
    """
    now = time.time() if now is None else now
    raw: List[FileRec] = []
    for p in cache_dir.glob(PROBE_GLOB):
        try:
            if not p.is_file() or p.is_symlink():
                continue
            raw.append(FileRec(path=p, age_days=_age_days(p, now),
                               size=p.stat().st_size))
        except OSError:
            continue
    # Sort youngest -> oldest; reserve youngest `min_keep`.
    raw.sort(key=lambda r: r.age_days)
    preserved = raw[: max(0, int(min_keep))]
    candidates = raw[max(0, int(min_keep)):]
    eligible = [r for r in candidates if r.age_days > float(keep_days)]
    not_old_enough = [r for r in candidates if r.age_days <= float(keep_days)]
    return eligible, preserved + not_old_enough


# ---------------------------------------------------------------------------
# archive create
# ---------------------------------------------------------------------------
def _acquire_lock(lock: Path) -> bool:
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError:
        return False
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
    finally:
        os.close(fd)
    return True


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except OSError:
        pass


def build_archive(
    files: List[FileRec], archive: Path, *, cache_dir: Path,
) -> Tuple[Path, str, int]:
    """Tar+gz `files` to `archive.tmp`, then atomic rename. Returns
    (final_path, sha256, n_files). Caller must hold a lock."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    tmp = archive.with_suffix(archive.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    n = 0
    with tarfile.open(str(tmp), "w:gz") as tf:
        for rec in files:
            try:
                arc_name = rec.path.relative_to(cache_dir).as_posix()
            except ValueError:
                arc_name = rec.path.name
            tf.add(str(rec.path), arcname=arc_name, recursive=False)
            n += 1
    digest = sha256_file(tmp)
    os.replace(tmp, archive)
    return archive, digest, n


def archive_probes(
    *, root: Path, keep_days: int = DEFAULT_KEEP_DAYS,
    min_keep: int = DEFAULT_MIN_KEEP, commit: bool = False,
    archive_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Top-level archive workflow. Dry-run by default."""
    cache_dir = root / DEFAULT_CACHE_DIR
    arch_dir = root / DEFAULT_ARCHIVE_DIR
    out: Dict[str, Any] = {
        "commit":     bool(commit),
        "cache_dir":  str(cache_dir),
        "archive_dir": str(arch_dir),
        "keep_days":  int(keep_days),
        "min_keep":   int(min_keep),
        "warnings":   [],
    }
    if not cache_dir.is_dir():
        out["n_eligible"] = 0
        out["size_mb_estimate"] = 0.0
        out["warnings"].append(f"cache_dir missing: {cache_dir}")
        return out

    eligible, _ = discover(cache_dir, keep_days=keep_days, min_keep=min_keep)
    out["n_eligible"] = len(eligible)
    out["size_mb_estimate"] = round(
        sum(r.size for r in eligible) / 1024.0 / 1024.0, 4
    )
    if not eligible:
        out["archive"] = None
        return out

    stamp = archive_name or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_path = arch_dir / f"probe_results_{stamp}.tar.gz"
    # If a same-day archive already exists, suffix with a counter to avoid
    # silent overwrite.
    counter = 1
    while archive_path.exists():
        archive_path = arch_dir / f"probe_results_{stamp}_{counter:02d}.tar.gz"
        counter += 1
    out["archive"] = str(archive_path)

    if not commit:
        return out

    arch_dir.mkdir(parents=True, exist_ok=True)
    lock = archive_path.with_suffix(archive_path.suffix + ".lock")
    if not _acquire_lock(lock):
        out["warnings"].append(f"locked: another archive in flight ({lock})")
        out["n_archived"] = 0
        out["n_deleted"] = 0
        return out
    try:
        final, digest, n = build_archive(eligible, archive_path, cache_dir=cache_dir)
        out["archive"] = str(final)
        out["sha256"] = digest
        out["n_archived"] = n
        # Re-verify the on-disk archive (defence vs torn writes).
        verify_digest = sha256_file(final)
        if verify_digest != digest:
            out["warnings"].append("post-write verify mismatch — aborting delete")
            out["n_deleted"] = 0
            return out
        write_sidecar(final, digest, n)
        # Now safe to delete originals.
        n_del = 0
        for rec in eligible:
            try:
                rec.path.unlink()
                n_del += 1
            except OSError as exc:
                out["warnings"].append(f"unlink failed: {rec.path} — {exc!r}")
        out["n_deleted"] = n_del
        out["size_mb_archive"] = round(final.stat().st_size / 1024.0 / 1024.0, 4)
    finally:
        _release_lock(lock)
    return out


# ---------------------------------------------------------------------------
# list / verify / restore
# ---------------------------------------------------------------------------
def _archive_meta(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": str(path), "name": path.name}
    try:
        st = path.stat()
        info["size_mb"] = round(st.st_size / 1024.0 / 1024.0, 4)
        info["mtime"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        info["size_mb"] = 0.0
    sidecar = path.with_suffix(path.suffix + ".sha256")
    info["sidecar"] = str(sidecar) if sidecar.exists() else None
    info["sha256"] = read_sidecar_digest(sidecar) if sidecar.exists() else None
    n_files = 0
    try:
        with tarfile.open(str(path), "r:gz") as tf:
            for _ in tf:
                n_files += 1
    except (tarfile.TarError, OSError) as exc:
        info["error"] = repr(exc)
    info["n_files"] = n_files
    return info


def list_archives(root: Path) -> List[Dict[str, Any]]:
    arch_dir = root / DEFAULT_ARCHIVE_DIR
    if not arch_dir.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(arch_dir.glob("probe_results_*.tar.gz")):
        out.append(_archive_meta(p))
    return out


def verify_archive(path: Path) -> Dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file():
        return {"path": str(path), "ok": False, "reason": "missing"}
    if not sidecar.is_file():
        return {"path": str(path), "ok": False, "reason": "no_sidecar"}
    expected = read_sidecar_digest(sidecar)
    if expected is None:
        return {"path": str(path), "ok": False, "reason": "bad_sidecar"}
    actual = sha256_file(path)
    return {
        "path":     str(path),
        "ok":       actual == expected,
        "expected": expected,
        "actual":   actual,
        "reason":   "match" if actual == expected else "mismatch",
    }


def verify_all(root: Path) -> List[Dict[str, Any]]:
    return [
        verify_archive(Path(a["path"])) for a in list_archives(root)
    ]


def restore_archive(
    archive: Path, *, cache_dir: Path, overwrite: bool = False,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"archive": str(archive), "cache_dir": str(cache_dir)}
    if not archive.is_file():
        out["ok"] = False
        out["reason"] = "archive_missing"
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    n_extracted = 0
    n_skipped = 0
    try:
        with tarfile.open(str(archive), "r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                # Defence vs path traversal.
                target = (cache_dir / member.name).resolve()
                try:
                    target.relative_to(cache_dir.resolve())
                except ValueError:
                    n_skipped += 1
                    continue
                if target.exists() and not overwrite:
                    n_skipped += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                if src is None:
                    n_skipped += 1
                    continue
                with open(target, "wb") as dst:
                    dst.write(src.read())
                n_extracted += 1
    except (tarfile.TarError, OSError) as exc:
        out["ok"] = False
        out["reason"] = repr(exc)
        out["n_extracted"] = n_extracted
        return out
    out["ok"] = True
    out["n_extracted"] = n_extracted
    out["n_skipped"] = n_skipped
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="R31_X4 probe-results archiver (dry-run by default)."
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--archive", action="store_true",
                      help="archive eligible probe files")
    mode.add_argument("--list", action="store_true",
                      help="list existing archives")
    mode.add_argument("--verify", nargs="?", const="", default=None,
                      help="verify a single archive (or all if no arg)")
    mode.add_argument("--restore", type=str, default=None,
                      help="restore an archive back into data/cache/")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP_DAYS,
                    help="archive files older than N days (default 7)")
    ap.add_argument("--min-keep", type=int, default=DEFAULT_MIN_KEEP,
                    help="preserve youngest N files regardless of age")
    ap.add_argument("--commit", action="store_true",
                    help="actually create archive + delete originals")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite existing files on restore")
    ap.add_argument("--root", type=str, default=_ROOT)
    ap.add_argument("--json", action="store_true")
    return ap.parse_args(argv)


def _print(result: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return
    if isinstance(result, list):
        for r in result:
            print(json.dumps(r, default=str))
        return
    print(json.dumps(result, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    root = Path(args.root)
    if args.archive:
        res = archive_probes(
            root=root, keep_days=int(args.keep),
            min_keep=int(args.min_keep), commit=bool(args.commit),
        )
        _print(res, args.json)
        return 0
    if args.list:
        _print(list_archives(root), args.json)
        return 0
    if args.verify is not None:
        if args.verify == "":
            _print(verify_all(root), args.json)
        else:
            _print(verify_archive(Path(args.verify)), args.json)
        return 0
    if args.restore:
        res = restore_archive(
            Path(args.restore),
            cache_dir=root / DEFAULT_CACHE_DIR,
            overwrite=bool(args.overwrite),
        )
        _print(res, args.json)
        return 0 if res.get("ok") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
