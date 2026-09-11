"""G386 CPU-only one-pass source pin, bounded capture, and receiver receipt.

The live command is intentionally not run by this prepare-only lane.  It opens
each selected source once and derives identity from that handle, never by
hashing and reopening a pathname that may have rotated.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

MAX_SCRATCH_BYTES = 2 * 1024 * 1024 * 1024
MAX_BATCH_BYTES = int(1.5 * 1024 * 1024 * 1024)
CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CaptureReceipt:
    """The receiver's independent readback acknowledgement for one version."""

    version_id: str
    receiver_sha256: str
    receiver_bytes: int
    pixel_opened: bool
    acknowledged: bool


@dataclass(frozen=True)
class CaptureRecord:
    """Immutable-at-return accounting record for a single sealed attempt."""

    attempt_id: str
    source_path: str
    status: str
    source_sha256: str
    source_bytes: int
    source_device: int
    source_inode: int
    ffprobe_stream: str
    ledger_snapshot_line: str
    staged_path: str
    receipt: CaptureReceipt | None


Probe = Callable[[Path], str]
Hook = Callable[[], None]
ReceiverDecoder = Callable[[Path], bool]


def ffprobe_stream(path: Path) -> str:
    """Return the captured copy's ffprobe stream JSON, without opening source again."""
    command = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        return "FFPROBE_ERROR:" + completed.stderr.strip().replace("\n", " ")[:200]
    return completed.stdout.replace("\r\n", "\n").strip()


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(block)
            total += len(block)
    return digest.hexdigest(), total


def _empty(source: Path, status: str, attempt_id: str, ledger_line: str) -> CaptureRecord:
    return CaptureRecord(attempt_id, str(source), status, "", 0, 0, 0, "", ledger_line, "", None)


def _receiver_readback(staged: Path, receiver_root: Path, corrupt: Hook | None,
                       receiver_decode: ReceiverDecoder) -> CaptureReceipt:
    receiver_root.mkdir(parents=True, exist_ok=True)
    version = "%s-%s" % (hashlib.sha256(staged.read_bytes()).hexdigest()[:16], uuid.uuid4().hex[:12])
    temporary = receiver_root / (version + ".tmp")
    final = receiver_root / (version + ".bin")
    shutil.copyfile(staged, temporary)
    if corrupt:
        corrupt()
    os.replace(temporary, final)
    digest, size = _digest(final)
    try:
        pixel_opened = receiver_decode(final)
    except (OSError, subprocess.SubprocessError):
        pixel_opened = False
    return CaptureReceipt(version, digest, size, pixel_opened, pixel_opened)


def pin_copy_one_pass(source: Path, scratch_root: Path, receiver_root: Path,
                      ledger_snapshot_line: str, attempt_id: str,
                      probe: Probe = ffprobe_stream, after_pin: Hook | None = None,
                      before_copy: Hook | None = None,
                      receiver_corrupt: Hook | None = None,
                      receiver_decode: ReceiverDecoder | None = None) -> CaptureRecord:
    """Pin one pathname, stream its opened handle once, and require receiver readback.

    Hooks exist solely for the scratch-only constructed controls and test fixture.
    They are not used by the live capture invocation.
    """
    try:
        path_stat = source.stat()
    except FileNotFoundError:
        return _empty(source, "LOST", attempt_id, ledger_snapshot_line)
    if after_pin:
        after_pin()
    try:
        handle = source.open("rb")
    except FileNotFoundError:
        return _empty(source, "LOST", attempt_id, ledger_snapshot_line)
    with handle:
        before = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino) != (path_stat.st_dev, path_stat.st_ino):
            return _empty(source, "CHANGED", attempt_id, ledger_snapshot_line)
        if before_copy:
            before_copy()
        scratch_root.mkdir(parents=True, exist_ok=True)
        staged = scratch_root / (attempt_id + ".part")
        digest = hashlib.sha256()
        copied = 0
        with staged.open("wb") as output:
            for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
                copied += len(block)
                if copied > MAX_BATCH_BYTES or copied > MAX_SCRATCH_BYTES:
                    output.close()
                    staged.unlink(missing_ok=True)
                    return _empty(source, "TOO_LARGE", attempt_id, ledger_snapshot_line)
                digest.update(block)
                output.write(block)
        after = os.fstat(handle.fileno())
    if copied != before.st_size:
        staged.unlink(missing_ok=True)
        return _empty(source, "SHORT_READ", attempt_id, ledger_snapshot_line)
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        staged.unlink(missing_ok=True)
        return _empty(source, "CHANGED", attempt_id, ledger_snapshot_line)
    staged = staged.with_suffix(".bin")
    (scratch_root / (attempt_id + ".part")).replace(staged)
    source_digest = digest.hexdigest()
    if receiver_decode is None:
        raise ValueError("receiver_decode is required before acknowledgement")
    receipt = _receiver_readback(staged, receiver_root, receiver_corrupt, receiver_decode)
    if receipt.receiver_sha256 != source_digest or receipt.receiver_bytes != copied:
        status = "RECEIVER_MISMATCH"
    elif not receipt.pixel_opened or not receipt.acknowledged:
        status = "COPY_UNDECODABLE"
    else:
        status = "CAPTURED"
    return CaptureRecord(attempt_id, str(source), status, source_digest, copied,
                         before.st_dev, before.st_ino, probe(staged), ledger_snapshot_line,
                         str(staged), receipt)


def write_record(record: CaptureRecord, path: Path) -> None:
    """Write a stable JSON manifest row after the receipt has been returned."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(record), sort_keys=True) + "\n", encoding="ascii")


def release_staging(record: CaptureRecord) -> bool:
    """Release only a receiver-acknowledged staged object after its receipt exists."""
    if record.status != "CAPTURED" or record.receipt is None or not record.receipt.acknowledged:
        return False
    Path(record.staged_path).unlink(missing_ok=True)
    return True
