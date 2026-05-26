"""ledger_insurance.py — R27_T7 daily atomic backup for data/pnl_ledger.csv.

The pnl ledger is months of real-money tracking (335k+ rows). A bad
migration, disk error, or typo would be catastrophic. This script gives
us four operations to make that loss impossible:

    --backup [--keep N]     gzip + sha256 snapshot, atomic via tmp+rename.
                             Rotates oldest off (default keep=30).
    --restore <date>        DRY-RUN by default. --commit to actually
                             swap the live file. Always saves the
                             current live file to
                             ``pnl_ledger.csv.pre_restore_<ts>`` first
                             and uses os.replace for atomicity.
    --verify [--date D]     SHA256-validate one backup (or all) vs sidecar.
    --list                  Show available backups: date, rows, size.

CLI examples
------------
    python scripts/ledger_insurance.py --backup
    python scripts/ledger_insurance.py --backup --keep 60
    python scripts/ledger_insurance.py --list
    python scripts/ledger_insurance.py --verify
    python scripts/ledger_insurance.py --verify --date 2026-05-26
    python scripts/ledger_insurance.py --restore 2026-05-26          # dry-run
    python scripts/ledger_insurance.py --restore 2026-05-26 --commit # real

Backups live in ``data/backups/`` with file pattern
``pnl_ledger.csv.<ISO_DATE>.gz``. Each backup ships a
``pnl_ledger.csv.<ISO_DATE>.gz.sha256`` sidecar that pins the SHA256
of the **uncompressed** original — that's what --verify and --restore
re-check.

Idempotence
-----------
    --backup twice on the same day OVERWRITES the existing backup
    (and refreshes its sha256 sidecar). This matches the intent —
    "snapshot the current ledger" — and keeps rotation deterministic.
    The write is still atomic (tmp + os.replace), so a crashed second
    run never leaves a half-written .gz.

Hard rules
----------
    * NEVER places real bets.
    * NEVER mutates ``data/pnl_ledger.csv`` except during --restore
      --commit (and even then via os.replace, with the pre-restore copy
      preserved).
    * Default --restore is dry-run; --commit is required to write.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from datetime import date as _date_cls
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Process-wide lock so multiple threads in the same daemon serialise their
# backups instead of racing each other through os.replace + rotation.
# Cross-process safety is guaranteed by the atomic os.replace itself.
_BACKUP_LOCK = threading.Lock()

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = PROJECT_DIR / "data" / "pnl_ledger.csv"
DEFAULT_BACKUP_DIR = PROJECT_DIR / "data" / "backups"
DEFAULT_KEEP = 30

# pnl_ledger.csv.<YYYY-MM-DD>.gz
_BACKUP_RE = re.compile(
    r"^pnl_ledger\.csv\.(?P<date>\d{4}-\d{2}-\d{2})\.gz$"
)
_CHUNK = 1 << 20  # 1 MiB streaming chunk for sha + gzip


# ============================================================================ #
# Tiny helpers                                                                  #
# ============================================================================ #
def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return _date_cls.today().isoformat()


def _ts_compact() -> str:
    """Compact filesafe timestamp for pre-restore snapshots."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_of_gzip_contents(path: Path) -> str:
    """Hash the UNCOMPRESSED contents of a gzip file (matches sidecar)."""
    h = hashlib.sha256()
    with gzip.open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _gzip_row_count(path: Path) -> int:
    """Count newlines in a gzip backup. Cheap-ish, single pass."""
    n = 0
    try:
        with gzip.open(path, "rb") as fh:
            while True:
                chunk = fh.read(_CHUNK)
                if not chunk:
                    break
                n += chunk.count(b"\n")
    except Exception:  # noqa: BLE001
        return -1
    return n


def _replace_with_retry(src: str, dst: Path, attempts: int = 8) -> None:
    """``os.replace`` with a short retry loop.

    On Windows, two concurrent ``os.replace(*, dst)`` calls can briefly
    surface ``PermissionError`` ("file in use by another process") even
    though replace itself is supposed to be atomic. A handful of short
    retries makes concurrent backups safe without changing the on-disk
    contract.
    """
    delay = 0.005
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.1)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomic single-blob write via temp + os.replace (with retry)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        _replace_with_retry(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_gzip_from_file(src: Path, dst: Path) -> None:
    """Stream-gzip src → unique tmp, then os.replace(tmp, dst). Atomic.

    The tmp filename includes pid + a per-process monotonic ns counter so
    concurrent backups never collide on the same tmp file.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_suffix = f".tmp.{os.getpid()}.{time.monotonic_ns()}"
    tmp = dst.with_suffix(dst.suffix + tmp_suffix)
    try:
        with open(src, "rb") as fin, gzip.open(tmp, "wb",
                                                compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout, length=_CHUNK)
        _replace_with_retry(str(tmp), dst)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_backup_date(name: str) -> Optional[str]:
    m = _BACKUP_RE.match(name)
    return m.group("date") if m else None


# ============================================================================ #
# Public ops                                                                   #
# ============================================================================ #
def list_backups(backup_dir: Path = DEFAULT_BACKUP_DIR) -> List[Dict[str, Any]]:
    """Return a list of backup descriptors, oldest-first.

    Each entry: {date, gz_path, sidecar_path, size_bytes, row_count,
                 has_sidecar, sha256_short}.
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    entries: List[Dict[str, Any]] = []
    try:
        candidates = sorted(backup_dir.iterdir())
    except OSError:
        return []
    for p in candidates:
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        date_str = _parse_backup_date(p.name)
        if date_str is None:
            continue
        sidecar = p.with_suffix(p.suffix + ".sha256")
        sha256_short = ""
        try:
            if sidecar.exists():
                sha256_short = sidecar.read_text(
                    encoding="utf-8"
                ).strip().split()[0][:16]
        except Exception:  # noqa: BLE001
            sha256_short = ""
        try:
            size_bytes = p.stat().st_size
        except OSError:
            # File deleted between iterdir() and stat() (rotation race).
            continue
        entries.append({
            "date":          date_str,
            "gz_path":       str(p),
            "sidecar_path":  str(sidecar),
            "size_bytes":    size_bytes,
            "row_count":     _gzip_row_count(p),
            "has_sidecar":   sidecar.exists(),
            "sha256_short":  sha256_short,
        })
    entries.sort(key=lambda e: e["date"])
    return entries


def backup(
    *,
    ledger_path: Path = DEFAULT_LEDGER,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    keep: int = DEFAULT_KEEP,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """Snapshot ledger → ``<backup_dir>/pnl_ledger.csv.<date>.gz`` + sidecar.

    Rotation: after writing the new backup, oldest entries beyond ``keep``
    (sorted by date) are deleted.

    Returns
    -------
    dict
        ``{"ok": bool, "date", "gz_path", "sha256", "size_bytes",
           "rotated": [paths], "reason"}``.
    """
    ledger_path = Path(ledger_path)
    backup_dir  = Path(backup_dir)
    date_str    = today or _today_iso()

    if not ledger_path.exists():
        return {
            "ok":      False,
            "reason":  f"ledger missing: {ledger_path}",
            "date":    date_str,
        }

    # Serialise in-process so concurrent threads can't race each other
    # through the rotation + post-write verification. Cross-process
    # safety is still guaranteed by os.replace being atomic on Win/POSIX.
    with _BACKUP_LOCK:
        # 1. Hash the source first — pin what we're snapshotting.
        src_sha = _sha256_of_file(ledger_path)

        # 2. Atomic gzip.
        gz_path = backup_dir / f"pnl_ledger.csv.{date_str}.gz"
        _atomic_gzip_from_file(ledger_path, gz_path)

        # 3. Atomic sidecar.
        sidecar = gz_path.with_suffix(gz_path.suffix + ".sha256")
        payload = f"{src_sha}  pnl_ledger.csv.{date_str}\n".encode("utf-8")
        _atomic_write_bytes(sidecar, payload)

        # 4. Sanity-check the new backup decompresses to the same hash.
        try:
            check_sha = _sha256_of_gzip_contents(gz_path)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok":     False,
                "reason": f"post-write decompress failed: {exc!r}",
                "date":   date_str,
                "gz_path": str(gz_path),
                "sha256": src_sha,
            }
        if check_sha != src_sha:
            return {
                "ok":      False,
                "reason":  "post-write hash mismatch — abort",
                "date":    date_str,
                "gz_path": str(gz_path),
                "sha256":  src_sha,
                "sha256_seen": check_sha,
            }

        # 5. Rotate.
        rotated: List[str] = []
        all_backups = list_backups(backup_dir)
        if keep is not None and keep >= 0 and len(all_backups) > keep:
            n_to_drop = len(all_backups) - keep
            for entry in all_backups[:n_to_drop]:
                try:
                    os.unlink(entry["gz_path"])
                    rotated.append(entry["gz_path"])
                except OSError:
                    pass
                try:
                    if entry["has_sidecar"]:
                        os.unlink(entry["sidecar_path"])
                except OSError:
                    pass

        try:
            size_bytes = gz_path.stat().st_size
        except OSError:
            size_bytes = 0

        return {
            "ok":         True,
            "date":       date_str,
            "gz_path":    str(gz_path),
            "sha256":     src_sha,
            "size_bytes": size_bytes,
            "rotated":    rotated,
        }


def verify(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Re-hash each backup vs its sidecar. Returns per-backup pass/fail."""
    backup_dir = Path(backup_dir)
    entries = list_backups(backup_dir)
    if date_str is not None:
        entries = [e for e in entries if e["date"] == date_str]
    results: List[Dict[str, Any]] = []
    n_ok = 0
    n_fail = 0
    for e in entries:
        gz   = Path(e["gz_path"])
        side = Path(e["sidecar_path"])
        if not side.exists():
            results.append({
                "date":   e["date"],
                "ok":     False,
                "reason": "sidecar missing",
            })
            n_fail += 1
            continue
        try:
            expected = side.read_text(encoding="utf-8").strip().split()[0]
        except Exception as exc:  # noqa: BLE001
            results.append({
                "date":   e["date"],
                "ok":     False,
                "reason": f"sidecar unreadable: {exc!r}",
            })
            n_fail += 1
            continue
        try:
            actual = _sha256_of_gzip_contents(gz)
        except Exception as exc:  # noqa: BLE001
            results.append({
                "date":   e["date"],
                "ok":     False,
                "reason": f"decompress failed: {exc!r}",
            })
            n_fail += 1
            continue
        match = (actual == expected)
        if match:
            n_ok += 1
        else:
            n_fail += 1
        results.append({
            "date":     e["date"],
            "ok":       match,
            "expected": expected[:16],
            "actual":   actual[:16],
            "reason":   "" if match else "sha256 mismatch — backup is rotting",
        })
    return {
        "ok":      n_fail == 0 and (n_ok > 0 or date_str is None),
        "n_ok":    n_ok,
        "n_fail":  n_fail,
        "n_total": len(entries),
        "results": results,
    }


def restore(
    *,
    date_str: str,
    ledger_path: Path = DEFAULT_LEDGER,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    commit: bool = False,
) -> Dict[str, Any]:
    """Restore a backup to ``ledger_path``.

    Procedure:
        1. Locate gz + sidecar for ``date_str``.
        2. Verify gz sha256 matches sidecar. Refuse if mismatch.
        3. If ``commit=False``: return plan, no writes.
        4. Snapshot the current ledger to
           ``<ledger_path>.pre_restore_<ts>`` (still gzip+sidecar).
        5. Decompress backup → temp file in ledger's parent dir.
        6. os.replace(temp, ledger_path). Atomic.
    """
    ledger_path = Path(ledger_path)
    backup_dir  = Path(backup_dir)

    gz   = backup_dir / f"pnl_ledger.csv.{date_str}.gz"
    side = gz.with_suffix(gz.suffix + ".sha256")

    plan: Dict[str, Any] = {
        "ok":          False,
        "date":        date_str,
        "gz_path":     str(gz),
        "ledger_path": str(ledger_path),
        "commit":      bool(commit),
        "dry_run":     not bool(commit),
    }

    if not gz.exists():
        plan["reason"] = f"backup missing: {gz}"
        return plan
    if not side.exists():
        plan["reason"] = f"sidecar missing: {side}"
        return plan

    try:
        expected = side.read_text(encoding="utf-8").strip().split()[0]
    except Exception as exc:  # noqa: BLE001
        plan["reason"] = f"sidecar unreadable: {exc!r}"
        return plan

    try:
        actual = _sha256_of_gzip_contents(gz)
    except Exception as exc:  # noqa: BLE001
        plan["reason"] = f"decompress failed: {exc!r}"
        return plan

    plan["expected_sha256"] = expected[:16]
    plan["actual_sha256"]   = actual[:16]

    if actual != expected:
        plan["reason"] = "sha256 mismatch — REFUSING to restore corrupted backup"
        return plan

    if not commit:
        plan["ok"] = True
        plan["reason"] = "dry-run — pass --commit to actually restore"
        return plan

    # ---- commit path ----
    pre_restore_path: Optional[Path] = None
    if ledger_path.exists():
        pre_restore_path = ledger_path.with_name(
            ledger_path.name + f".pre_restore_{_ts_compact()}"
        )
        # Plain copy (no gzip) so a human can grep it immediately.
        shutil.copy2(ledger_path, pre_restore_path)

    # Decompress backup to a temp file in the same directory as ledger.
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=ledger_path.name + ".restore.",
        suffix=".tmp",
        dir=str(ledger_path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as fout, gzip.open(gz, "rb") as fin:
            shutil.copyfileobj(fin, fout, length=_CHUNK)
        os.replace(tmp, ledger_path)
    except Exception as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        plan["reason"] = f"restore write failed: {exc!r}"
        return plan

    plan["ok"] = True
    plan["reason"] = "restored"
    plan["pre_restore_path"] = (
        str(pre_restore_path) if pre_restore_path is not None else ""
    )
    return plan


# ============================================================================ #
# CLI                                                                          #
# ============================================================================ #
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="R27_T7 — ledger insurance (backup / verify / restore).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--backup", action="store_true",
                    help="Snapshot data/pnl_ledger.csv to data/backups/.")
    g.add_argument("--restore", type=str, metavar="DATE",
                    help="Restore from data/backups/pnl_ledger.csv.<DATE>.gz "
                         "(dry-run by default; pass --commit).")
    g.add_argument("--verify", action="store_true",
                    help="SHA256-validate all backups vs sidecars.")
    g.add_argument("--list", action="store_true",
                    help="List available backups.")
    ap.add_argument("--commit", action="store_true",
                    help="Required with --restore to actually replace the ledger.")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                    help=f"--backup rotation count (default {DEFAULT_KEEP}).")
    ap.add_argument("--date", type=str, default=None,
                    help="--verify: limit to one date.")
    ap.add_argument("--today", type=str, default=None,
                    help="--backup: override snapshot date (YYYY-MM-DD).")
    ap.add_argument("--ledger-path", type=str, default=str(DEFAULT_LEDGER))
    ap.add_argument("--backup-dir", type=str, default=str(DEFAULT_BACKUP_DIR))
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of human text.")
    return ap.parse_args(argv)


def _print_list(entries: List[Dict[str, Any]]) -> None:
    if not entries:
        print("(no backups)")
        return
    print(f"{'date':<12} {'size_mb':>9} {'rows':>10} {'sha':<18} path")
    for e in entries:
        size_mb = e["size_bytes"] / 1024.0 / 1024.0
        print(
            f"{e['date']:<12} {size_mb:>9.2f} {e['row_count']:>10} "
            f"{e['sha256_short']:<18} {e['gz_path']}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    ledger = Path(args.ledger_path)
    bdir   = Path(args.backup_dir)

    if args.list:
        out = list_backups(backup_dir=bdir)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            _print_list(out)
        return 0

    if args.backup:
        res = backup(
            ledger_path=ledger, backup_dir=bdir,
            keep=int(args.keep), today=args.today,
        )
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            if res.get("ok"):
                size_mb = res["size_bytes"] / 1024.0 / 1024.0
                print(f"OK  backup={res['gz_path']}  "
                      f"size={size_mb:.2f}MB  "
                      f"sha256={res['sha256'][:16]}  "
                      f"rotated={len(res.get('rotated', []))}")
            else:
                print(f"FAIL  reason={res.get('reason')}")
        return 0 if res.get("ok") else 1

    if args.verify:
        res = verify(backup_dir=bdir, date_str=args.date)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print(f"verify: n_ok={res['n_ok']} n_fail={res['n_fail']} "
                  f"n_total={res['n_total']}")
            for r in res["results"]:
                tag = "OK  " if r["ok"] else "FAIL"
                print(f"  [{tag}] {r['date']}  {r.get('reason','')}")
        return 0 if res["ok"] else 1

    if args.restore:
        res = restore(
            date_str=args.restore, ledger_path=ledger,
            backup_dir=bdir, commit=bool(args.commit),
        )
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            tag = "OK  " if res["ok"] else "FAIL"
            print(f"[{tag}] restore date={res['date']} "
                  f"commit={res.get('commit')} "
                  f"reason={res.get('reason','')}")
            if res.get("pre_restore_path"):
                print(f"  pre_restore_path={res['pre_restore_path']}")
        return 0 if res.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
