"""predict_service.store -- the atomic canonical store for snapshot envelopes.

ONE writer, many readers. The predict service computes a sport's SnapshotEnvelope
once and saves it here; CourtVision and the paper-trading engine both READ it.

Two artifacts per sport under data/frontend/predict_service/<sport>/:
  * latest.json  -- the current snapshot, written ATOMICALLY (tmp + os.replace) so
                    a concurrent reader sees either the OLD file or the COMPLETE new
                    one, never a half-written (torn) file.
  * history.jsonl -- append-only: every save appends one line via a true O(1)
                    ``open(..., "ab")`` write (never a full-file read+rewrite);
                    a crash mid-append can leave a torn trailing line, tolerated
                    by read_history()'s per-line try/except (skipped, never a
                    crash). Nothing existing is ever overwritten. The honest,
                    immutable record of what we predicted.

read_latest(sport) NEVER raises and NEVER returns a partial object: a missing,
empty, or corrupt latest.json degrades to a status='unavailable' sentinel
envelope. data/ is gitignored -- correct; this is a local cache, never committed.

ENVELOPE STALE-NEVER-GREEN: read_latest also demotes an 'ok' snapshot whose games
are ALL past-tipoff/final to status=STALE_STATUS, so an already-on-disk finished
game (e.g. a day-old latest.json the scheduler has not yet overwritten) is never
served to a consumer as a fresh 'ok' prediction. A snapshot with any upcoming/live
game stays 'ok'. This complements stale_drop, which drops stale RECORDS at PRODUCE
time; this is the status guard for ON-DISK reads.

HONESTY: no $ edge is stored or implied (see predict_service.contracts).

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from predict_service.contracts import SnapshotEnvelope

logger = logging.getLogger(__name__)

# Envelope status an all-past-tipoff/finished snapshot is demoted to. It is NOT
# 'ok' (so a consumer of read_latest never serves a finished game as a live
# prediction) and NOT 'unavailable' (the snapshot exists + is structurally valid;
# it is just settled). Stale-never-green at the ENVELOPE level.
STALE_STATUS = "stale"

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


# os.replace retry: on Windows, os.replace(tmp, path) raises PermissionError when
# another process/handle has *path* open for read (no POSIX-style atomic rename-
# over-an-open-file) -- reproduced 200/200 against a concurrent reader. A short
# retry lets the reader's transient handle close before we give up for real.
_REPLACE_RETRY_ATTEMPTS = 3
_REPLACE_RETRY_MIN_SEC = 0.05
_REPLACE_RETRY_MAX_SEC = 0.15


def _replace_with_retry(tmp: Path, path: Path,
                        sleep_fn: Any = time.sleep) -> None:
    """os.replace(tmp, path) with a small retry on Windows PermissionError.

    Retries up to _REPLACE_RETRY_ATTEMPTS times with a short jittered backoff
    between attempts; re-raises the final PermissionError so the caller's
    existing except-and-log (status=error) path still fires. A non-Permission
    error is never retried -- it surfaces immediately, as before.
    """
    for attempt in range(1, _REPLACE_RETRY_ATTEMPTS + 1):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt >= _REPLACE_RETRY_ATTEMPTS:
                raise
            sleep_fn(random.uniform(_REPLACE_RETRY_MIN_SEC, _REPLACE_RETRY_MAX_SEC))


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically (tmp file + os.replace).

    The tmp file is flushed + fsynced before the rename so the bytes are on disk
    before latest.json points at them. os.replace is atomic on the same filesystem;
    on Windows a reader holding *path* open can make the rename raise
    PermissionError transiently -- _replace_with_retry absorbs that.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, ensure_ascii=True)
        fh.flush()
        os.fsync(fh.fileno())
    _replace_with_retry(tmp, path)


def _append_jsonl_line(path: Path, line: str) -> None:
    """Append *line* (no trailing newline) to *path* as a true O(1) append.

    A bare ``open(path, "ab")`` write + fsync -- no read-whole-file-then-rewrite,
    so a large history.jsonl appends in constant time regardless of its size.
    Torn-tail risk from a crash mid-write is already tolerated by
    read_history()'s per-line try/except (a partial last line is skipped, never
    crashes the reader). The only cheap (O(1), last-byte) check kept from the
    old read+rewrite path: if a PRE-EXISTING torn tail (no trailing newline) is
    on disk, a leading newline is written first so the new line never glues onto
    it -- checked via a single seek-to-end + 1-byte read, not a full-file read.
    """
    needs_leading_newline = False
    if path.is_file():
        size = path.stat().st_size
        if size > 0:
            with path.open("rb") as fh:
                fh.seek(-1, os.SEEK_END)
                needs_leading_newline = fh.read(1) != b"\n"
    with path.open("ab") as fh:
        if needs_leading_newline:
            fh.write(b"\n")
        fh.write(line.encode("utf-8") + b"\n")
        fh.flush()
        os.fsync(fh.fileno())


def append_history(envelope: EnvelopeLike,
                   out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Append one envelope as a JSON line to <sport>/history.jsonl (append-only).

    Never overwrites an existing line. The append is O(1) (open(...,"ab")); a
    crash mid-append can leave a torn trailing line, tolerated by
    read_history()'s per-line try/except. Returns the history path. Raises only
    on a genuine I/O failure (callers that must not raise should use save()).
    """
    env = _as_envelope(envelope)
    path = history_path(env.sport, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(env.to_dict(), default=str, ensure_ascii=True)
    _append_jsonl_line(path, line)
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


def _demote_if_all_past(env: SnapshotEnvelope,
                        now: Optional[datetime] = None) -> SnapshotEnvelope:
    """Demote an 'ok' envelope to STALE_STATUS when EVERY game is past-tipoff/final.

    The ENVELOPE-LEVEL stale-never-green guard, complementing stale_drop (which
    drops stale RECORDS at PRODUCE time). This catches an already-on-disk / echoed
    latest.json whose games have all aged out since it was written: a consumer of
    read_latest must never see a finished game carrying status='ok'.

    Only fires when status=='ok' AND there is at least one prediction AND every
    prediction is stale (post, or tipoff older than the grace window). A snapshot
    with ANY upcoming/live game keeps status='ok' so the live slate is unaffected.
    An empty-predictions envelope is left untouched (its own status governs).
    Never raises -- on any error the envelope is returned unchanged.
    """
    try:
        if env.status != "ok" or not env.predictions:
            return env
        # Reuse the validated per-record staleness check (post OR past-grace).
        from predict_service.stale_drop import is_stale_record  # noqa: PLC0415
        if now is None:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if all(is_stale_record(p, now) for p in env.predictions):
            env.status = STALE_STATUS
            if not env.note:
                env.note = "all games past tipoff/final; demoted ok->stale"
    except Exception as exc:  # noqa: BLE001 -- a guard must never break a read
        logger.warning("read_latest demote check failed for %s: %s",
                       getattr(env, "sport", "?"), exc)
    return env


def read_latest(sport: str,
                out_dir: Optional[Union[str, Path]] = None,
                now: Optional[datetime] = None) -> SnapshotEnvelope:
    """Load <sport>/latest.json -> SnapshotEnvelope. NEVER raises, NEVER torn.

    A missing, empty, or corrupt/partial file degrades to the status='unavailable'
    sentinel envelope -- a reader can always trust the returned object is either a
    COMPLETE 'ok' snapshot or an explicit 'unavailable' one, never a partial read.

    ENVELOPE STALE-NEVER-GREEN: a structurally-valid 'ok' snapshot whose games are
    ALL past-tipoff/final is demoted to status=STALE_STATUS so an already-on-disk
    finished game is never served as a fresh 'ok' prediction. A snapshot with any
    upcoming/live game keeps 'ok'. *now* is injectable (UTC) for deterministic
    tests; defaults to the wall clock.
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
        env = SnapshotEnvelope.from_dict(data)
    except Exception as exc:  # noqa: BLE001 -- a malformed shape is still a miss
        logger.warning("read_latest decode failed for %s: %s", sport, exc)
        return SnapshotEnvelope.unavailable(
            sport, reason="malformed snapshot (%s)" % type(exc).__name__)
    return _demote_if_all_past(env, now=now)


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
    "STALE_STATUS",
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
