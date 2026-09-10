"""Immutable claim-time source identity sidecars for the proposed G372 overlay."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UNKNOWN = "UNKNOWN"
SIDE_FIELDS = (
    "source_path", "source_sha256", "source_bytes", "ffprobe", "crop_rule",
    "route_digest", "weight_digest", "deploy_manifest_sha256", "claim_utc",
    "daemon_pid", "terminal_diagnostic",
)


def sha256_stream(handle) -> str:
    """Digest an ALREADY-OPEN handle, so the descriptor pins the bytes being read.

    The daemon hook opens the staged source the instant it reserves the claim;
    the pod volume guard can unlink that path a moment later and this digest
    still reads the reserved bytes.
    """
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1 << 20), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    """Return a streamed SHA-256 digest without loading a video into memory."""
    with path.open("rb") as handle:
        return sha256_stream(handle)


def digest_paths(paths: list[Path]) -> dict[str, str]:
    """Digest named route or weight files; unreadable files remain explicit."""
    result = {}
    for path in sorted(paths, key=lambda item: str(item)):
        try:
            result[str(path)] = sha256_file(path)
        except OSError:
            result[str(path)] = UNKNOWN
    return result


def utc_now() -> str:
    """Produce the stable UTC format used by sidecars and claim journals."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ffprobe(payload: str) -> dict[str, Any]:
    """Parse bounded ffprobe output and label stream-start fallback as ESTIMATE."""
    try:
        parsed = json.loads(payload)
    except ValueError:
        return {"status": "ERROR", "first_pts": UNKNOWN, "start_time_kind": "UNKNOWN"}
    stream = (parsed.get("streams") or [{}])[0]
    frames = parsed.get("frames") or []
    stamps = []
    for frame in frames:
        try:
            stamp = float(frame["pts_time"])
        except (KeyError, TypeError, ValueError):
            continue
        if stamp >= 0:
            stamps.append(stamp)
    result = {"status": "OK", "width": stream.get("width", UNKNOWN),
              "height": stream.get("height", UNKNOWN),
              "fps": stream.get("avg_frame_rate", UNKNOWN),
              "codec": stream.get("codec_name", UNKNOWN),
              "nb_frames": stream.get("nb_frames", UNKNOWN)}
    if stamps:
        result.update(first_pts=stamps[0], start_time_kind="DECODED_PTS")
    else:
        result.update(first_pts=stream.get("start_time", UNKNOWN), start_time_kind="ESTIMATE")
    return result


def bounded_ffprobe(path: Path, timeout_s: float = 5.0) -> dict[str, Any]:
    """Run a short metadata probe, never a decode or unbounded probe."""
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals",
               "%+5.0", "-show_entries",
               "stream=codec_name,width,height,avg_frame_rate,nb_frames,start_time:frame=pts_time",
               "-of", "json", str(path)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s)
    except (OSError, subprocess.SubprocessError):
        return {"status": "ERROR", "first_pts": UNKNOWN, "start_time_kind": "UNKNOWN"}
    return parse_ffprobe(done.stdout if done.returncode == 0 else "")


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def write_sidecar(path: Path, payload: dict[str, Any]) -> Path:
    """Commit an immutable, canonical sidecar once; a rewrite is an error."""
    missing = set(SIDE_FIELDS) - set(payload)
    if missing:
        raise ValueError("missing sidecar fields: " + ",".join(sorted(missing)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_canonical_bytes({key: payload[key] for key in SIDE_FIELDS}))
        handle.flush()
        os.fsync(handle.fileno())
    return path


def append_claim(journal: Path, entry: dict[str, Any]) -> None:
    """Append every reservation or terminal diagnostic without a rewrite path."""
    required = {"game_id", "claim_utc", "state", "source_identity_path", "diagnostic"}
    missing = required - set(entry)
    if missing:
        raise ValueError("missing claim fields: " + ",".join(sorted(missing)))
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("ab") as handle:
        handle.write(_canonical_bytes(entry))
        handle.flush()
        os.fsync(handle.fileno())


def reservation(game_id: str, sidecar: Path, diagnostic: str = "") -> dict[str, str]:
    """Create the journal row written before bounded identity work starts."""
    return {"game_id": game_id, "claim_utc": utc_now(), "state": "RESERVED",
            "source_identity_path": str(sidecar), "diagnostic": diagnostic}


def terminal_failure(game_id: str, sidecar: Path, diagnostic: str) -> dict[str, str]:
    """Create a non-reclaiming terminal diagnostic that still passes tracking through."""
    return {"game_id": game_id, "claim_utc": utc_now(), "state": "TERMINAL_ERROR",
            "source_identity_path": str(sidecar), "diagnostic": diagnostic}


def completion_field(sidecar: Path | None) -> dict[str, str | None]:
    """Provide the sole additive field proposed for completion-ledger entries."""
    return {"source_identity_path": str(sidecar) if sidecar else None}
