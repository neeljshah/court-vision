"""scripts.platformkit.tip_capture.store -- append-only JSONL store + singleton.

Store: data/cache/tip_capture/<sport>/<date>.jsonl (date = tip date, UTC), one
row per (game, capture_pass). Crash-safe O(1) append (one open('a') write,
never a read+rewrite) -- a crash mid-append can leave a torn tail line,
tolerated by captured_passes_for()'s per-line try/except, same discipline as
predict_service/store.py's history.jsonl.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("tip_capture")

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "cache" / "tip_capture"
DEFAULT_LOCK_PATH = DEFAULT_OUT_DIR / "tip_capture.lock"
HEARTBEAT_COMPONENT = "tip_capture"

_LOCK_HANDLE = None  # module-held so the flock lives for the process


def store_path(sport: str, tip_time_iso: str, *, out_dir: Optional[Path] = None) -> Path:
    base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    return base / sport.lower() / f"{tip_time_iso[:10]}.jsonl"


def captured_passes_for(game_id: str, sport: str, tip_time_iso: str,
                        *, out_dir: Optional[Path] = None) -> set:
    """Which capture_pass names already exist for this game (idempotency)."""
    path = store_path(sport, tip_time_iso, out_dir=out_dir)
    if not path.is_file():
        return set()
    caps: set = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:  # tolerate a torn trailing line
            continue
        if row.get("game_id") == game_id:
            caps.add(row.get("capture_pass"))
    return caps


def append_row(row: Dict[str, Any], *, out_dir: Optional[Path] = None) -> Path:
    """Crash-safe O(1) append: one open('a') write, never a read+rewrite."""
    path = store_path(row["sport"], row["tip_time"], out_dir=out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        fh.flush()
    return path


def acquire_singleton(lock_path: Path = DEFAULT_LOCK_PATH) -> bool:
    """One daemon per lock_path. POSIX flock; no-op guard off-POSIX (Windows
    dev box -- mirrors pod_sprint/driver.py's _acquire_singleton)."""
    global _LOCK_HANDLE
    try:
        import fcntl
    except ImportError:  # ponytail: Windows = dev-only, races not a concern
        return True
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_HANDLE = open(lock_path, "w")
    try:
        fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception:  # noqa: BLE001
        logger.debug("tip_capture heartbeat skipped", exc_info=True)


__all__ = [
    "DEFAULT_OUT_DIR", "DEFAULT_LOCK_PATH", "HEARTBEAT_COMPONENT",
    "store_path", "captured_passes_for", "append_row", "acquire_singleton", "beat",
]
