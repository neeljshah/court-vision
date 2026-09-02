"""scripts.platformkit.data_frontier._politeness -- tiny shared helpers so the 4
frontier pullers don't each reinvent atomic-write / rate-limited GET / ASCII log.

ponytail: this is the whole helper -- no retry backoff curves, no session pool,
no config object. Add those when a puller actually needs them, not before.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def polite_sleep(min_interval: float, last_call: Optional[float]) -> float:
    """Sleep just enough to keep calls >= min_interval apart. Returns the new
    'last call' monotonic timestamp (caller stores it and passes it back)."""
    now = time.monotonic()
    if last_call is not None:
        wait = min_interval - (now - last_call)
        if wait > 0:
            time.sleep(wait)
    return time.monotonic()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def log_line(log_path: Path, msg: str) -> None:
    """Append one ASCII line, timestamped, to a log file (creates dirs)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    line = f"{ts} {msg}\n".encode("ascii", errors="replace").decode("ascii")
    with open(log_path, "a", encoding="ascii", errors="replace") as f:
        f.write(line)


__all__ = ["polite_sleep", "atomic_write_bytes", "atomic_write_text", "log_line"]
