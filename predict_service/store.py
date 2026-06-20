"""predict_service.store -- the atomic canonical store for snapshot envelopes.

ONE writer, many readers. The predict service computes a sport's SnapshotEnvelope
once and saves it here; CourtVision and the paper-trading engine both READ it.

Two artifacts per sport under data/frontend/predict_service/<sport>/:
  * latest.json  -- the current snapshot, written ATOMICALLY (tmp + os.replace) so
                    a concurrent reader sees either the OLD file or the COMPLETE new
                    one, never a half-written (torn) file.
  * history.jsonl -- append-only: every save appends one line; nothing is ever
                    overwritten. The honest, immutable record of what we predicted.

read_latest(sport) NEVER raises and NEVER returns a partial object: a missing,
empty, or corrupt latest.json degrades to a status='unavailable' sentinel
envelope. data/ is gitignored -- correct; this is a local cache, never committed.

HONESTY: no $ edge is stored or implied (see predict_service.contracts).

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from predict_service.contracts import SnapshotEnvelope

logger = logging.getLogger(__name__)

# __file__ = predict_service/store.py -> parents[1] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DIR = _REPO_ROOT / "data" / "frontend" / "predict_service"

_LATEST_NAME = "latest.json"
_HISTORY_NAME = "history.jsonl"

EnvelopeLike = Union[SnapshotEnvelope, Dict[str, Any]]


def base_dir(out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Resolve the store base dir (override with *out_dir* in tests)."""
    return Path(out_dir) if out_dir is not None else DEFAULT_BASE_DIR


def sport_dir(sport: str, out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Directory holding one sport's latest.json + history.jsonl."""
    return base_dir(out_dir) / str(sport).lower()


def latest_path(sport: str, out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Path to <sport>/latest.json."""
    return sport_dir(sport, out_dir) / _LATEST_NAME


def history_path(sport: str, out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Path to <sport>/history.jsonl (append-only)."""
    return sport_dir(sport, out_dir) / _HISTORY_NAME


def _as_envelope(envelope: EnvelopeLike) -> SnapshotEnvelope:
    """Coerce a dict OR a SnapshotEnvelope to a SnapshotEnvelope (round-trip safe)."""
    if isinstance(envelope, SnapshotEnvelope):
        return envelope
    if isinstance(envelope, dict):
        return SnapshotEnvelope.from_dict(envelope)
    raise TypeError("envelope must be SnapshotEnvelope or dict, got %r"
                    % (type(envelope).__name__,))


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically (tmp file + os.replace).

    The tmp file is flushed + fsynced before the rename so the bytes are on disk
    before latest.json points at them. os.replace is atomic on the same filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, ensure_ascii=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def append_history(envelope: EnvelopeLike,
                   out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Append one envelope as a JSON line to <sport>/history.jsonl (append-only).

    Never overwrites an existing line. Returns the history path. Raises only on a
    genuine I/O failure (callers that must not raise should use save()).
    """
    env = _as_envelope(envelope)
    path = history_path(env.sport, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(env.to_dict(), default=str, ensure_ascii=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


def save(envelope: EnvelopeLike,
         out_dir: Optional[Union[str, Path]] = None,
         append: bool = True) -> Path:
    """Atomically write *envelope* to <sport>/latest.json AND append to history.

    Returns the latest.json path. The atomic write happens FIRST (readers care
    most about a clean latest.json); the history append is best-effort and a
    failure there is logged, not raised, so a full-disk history never blocks the
    canonical latest. Set append=False to skip the history append.
    """
    env = _as_envelope(envelope)
    payload = env.to_dict()
    target = latest_path(env.sport, out_dir)
    _atomic_write_json(target, payload)
    if append:
        try:
            append_history(env, out_dir)
        except Exception as exc:  # noqa: BLE001 -- history must not sink the save
            logger.warning("history append failed for %s: %s", env.sport, exc)
    return target


# Alias: some callers prefer write(); identical to save().
write = save


def read_latest(sport: str,
                out_dir: Optional[Union[str, Path]] = None) -> SnapshotEnvelope:
    """Load <sport>/latest.json -> SnapshotEnvelope. NEVER raises, NEVER torn.

    A missing, empty, or corrupt/partial file degrades to the status='unavailable'
    sentinel envelope -- a reader can always trust the returned object is either a
    COMPLETE 'ok' snapshot or an explicit 'unavailable' one, never a partial read.
    """
    path = latest_path(sport, out_dir)
    if not path.exists():
        return SnapshotEnvelope.unavailable(sport, reason="latest.json missing")
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 -- an unreadable file is a cache miss
        logger.warning("read_latest read failed for %s: %s", sport, exc)
        return SnapshotEnvelope.unavailable(
            sport, reason="read error (%s)" % type(exc).__name__)
    if not raw.strip():
        return SnapshotEnvelope.unavailable(sport, reason="latest.json empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        # A partial / torn / truncated file lands here -> sentinel, not a crash.
        logger.warning("read_latest parse failed for %s: %s", sport, exc)
        return SnapshotEnvelope.unavailable(
            sport, reason="partial or corrupt latest.json")
    if not isinstance(data, dict):
        return SnapshotEnvelope.unavailable(
            sport, reason="latest.json is not an object")
    try:
        return SnapshotEnvelope.from_dict(data)
    except Exception as exc:  # noqa: BLE001 -- a malformed shape is still a miss
        logger.warning("read_latest decode failed for %s: %s", sport, exc)
        return SnapshotEnvelope.unavailable(
            sport, reason="malformed snapshot (%s)" % type(exc).__name__)


def read_history(sport: str,
                 out_dir: Optional[Union[str, Path]] = None
                 ) -> List[SnapshotEnvelope]:
    """Read every line of <sport>/history.jsonl -> list of envelopes.

    Missing file -> empty list. A corrupt trailing line is tolerated and skipped
    (never crashes the reader). Returns envelopes in append (chronological) order.
    """
    path = history_path(sport, out_dir)
    if not path.exists():
        return []
    out: List[SnapshotEnvelope] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(SnapshotEnvelope.from_dict(json.loads(line)))
                except Exception:  # noqa: BLE001 -- tolerate a partial last write
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("read_history failed for %s: %s", sport, exc)
    return out


__all__ = [
    "DEFAULT_BASE_DIR",
    "base_dir",
    "sport_dir",
    "latest_path",
    "history_path",
    "append_history",
    "save",
    "write",
    "read_latest",
    "read_history",
]
