"""scripts.platformkit.improve.checkpoint -- atomic, resumable cursor for the daemon.

A tiny JSON checkpoint that lets the always-on loop resume LOSSLESSLY after a crash
or a clean restart: it records, per artifact name, how far the settled-games cursor
has advanced and the last version that went live, plus a global cycle counter. The
write is temp+fsync+os.replace, so the file is never torn -- a restart sees either the
prior consistent state or the new one, never half.

Default location: data/cache/improve/checkpoint.json (NEVER data/registry/).
stdlib-only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

_REPO = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_CKPT = _REPO / "data" / "cache" / "improve" / "checkpoint.json"


@dataclass
class Checkpoint:
    """Persisted daemon cursor.

    cycle    : monotone count of cycles completed (for observability/backoff).
    cursors  : per-name {name: {"processed": int, "last_version": int|None,
               "last_decision": str|None}} -- `processed` is the count of settled
               games already folded into that name's rolling window.
    """
    cycle: int = 0
    cursors: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def cursor(self, name: str) -> Dict[str, Any]:
        return self.cursors.setdefault(
            name, {"processed": 0, "last_version": None, "last_decision": None})

    def to_dict(self) -> Dict[str, Any]:
        return {"cycle": self.cycle, "cursors": self.cursors}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Checkpoint":
        return cls(
            cycle=int(d.get("cycle", 0) or 0),
            cursors=dict(d.get("cursors") or {}),
        )


def _atomic_write(path: pathlib.Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_checkpoint(path: Optional[str] = None) -> Checkpoint:
    """Load the checkpoint; a missing/torn/garbage file -> a fresh zero cursor."""
    p = pathlib.Path(path) if path else DEFAULT_CKPT
    if not p.exists():
        return Checkpoint()
    try:
        return Checkpoint.from_dict(json.loads(p.read_text(encoding="ascii")))
    except (OSError, ValueError, TypeError):
        return Checkpoint()


def save_checkpoint(ckpt: Checkpoint, path: Optional[str] = None) -> pathlib.Path:
    """Persist the checkpoint atomically (temp+fsync+os.replace -- never torn)."""
    p = pathlib.Path(path) if path else DEFAULT_CKPT
    _atomic_write(p, json.dumps(ckpt.to_dict(), sort_keys=True, indent=2))
    return p


__all__ = ["Checkpoint", "load_checkpoint", "save_checkpoint", "DEFAULT_CKPT"]
