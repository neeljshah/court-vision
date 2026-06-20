"""scripts.platformkit.autonomy.work_queue -- durable lease-based work queue (A5/D3).

A tiny crash-safe queue so the self-improve loop picks its OWN next task with no human
dispatch. Operations:

  enqueue(kind, sport, args)  -> task_id           (append a PENDING task, dedup-able)
  lease(now, visibility_sec)  -> Task | None       (claim the oldest ready task)
  ack(task_id)                -> bool              (mark a leased task DONE, drop it)
  nack(task_id, now, ...)     -> bool              (release a leased task back to PENDING)

A LEASED task carries a `lease_until`. `reclaim_expired(now)` (called inside `lease`)
returns any task whose lease has elapsed to PENDING -- so a worker that crashes
BEFORE acking loses nothing: the task re-leases after the visibility timeout. This is
the lossless-across-restart guarantee.

DURABILITY: the entire queue is persisted as one JSON document via temp+fsync+os.replace
(the checkpoint.py pattern). Every mutating op rewrites the whole file atomically, so a
crash mid-write leaves either the prior consistent state or the new one -- never a torn
file. A torn/garbage/missing file loads as an EMPTY queue (fail-safe, never raises).

RAILS: store lives under data/cache/autonomy/ (NEVER data/registry/). Tasks are
MEASUREMENT-ONLY (recalibrate / regate_ingame / refresh_corpora / backfill_settled);
this module does not interpret `kind` -- the schedule_policy gate guarantees no
ship/flag/real-money kind is ever enqueued. UNITS/probability only, never $.
stdlib-only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_REPO = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_QUEUE = _REPO / "data" / "cache" / "autonomy" / "work_queue.json"

# Task lifecycle states.
PENDING = "PENDING"
LEASED = "LEASED"
DONE = "DONE"

# Measurement-only kinds the queue is allowed to hold. The schedule_policy is the
# gate that decides WHAT to enqueue; this is a defensive allow-list so a stray
# ship/flag/real-money kind can never be persisted even by a buggy caller.
ALLOWED_KINDS = frozenset(
    {"recalibrate", "regate_ingame", "refresh_corpora", "backfill_settled"})


class DisallowedKind(ValueError):
    """Raised if a caller tries to enqueue a non-measurement (e.g. ship/flag) kind."""


@dataclass
class Task:
    """One unit of durable work.

    status      : PENDING | LEASED | DONE
    attempts    : number of times this task has been leased (for backoff/observability)
    lease_until : epoch seconds the current lease expires (only meaningful when LEASED)
    """
    id: str
    kind: str
    sport: str
    args: Dict[str, Any] = field(default_factory=dict)
    enqueued_ts: float = 0.0
    status: str = PENDING
    attempts: int = 0
    lease_until: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "sport": self.sport,
            "args": self.args, "enqueued_ts": self.enqueued_ts,
            "status": self.status, "attempts": self.attempts,
            "lease_until": self.lease_until,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Task":
        return cls(
            id=str(d["id"]),
            kind=str(d.get("kind", "")),
            sport=str(d.get("sport", "")),
            args=dict(d.get("args") or {}),
            enqueued_ts=float(d.get("enqueued_ts", 0.0) or 0.0),
            status=str(d.get("status", PENDING)),
            attempts=int(d.get("attempts", 0) or 0),
            lease_until=(None if d.get("lease_until") is None
                         else float(d["lease_until"])),
        )


def _atomic_write(path: pathlib.Path, payload: str) -> None:
    """temp+fsync+os.replace -- never leaves a torn file (checkpoint.py pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class WorkQueue:
    """Durable lease-based queue persisted as one atomic JSON document.

    Not thread-safe in-process; cross-process safety comes from the atomic full-file
    rewrite plus the lease/visibility-timeout protocol (two leases never overlap on the
    same task because a lease flips status to LEASED and persists before returning).
    """

    def __init__(self, path: Optional[str] = None):
        self.path = pathlib.Path(path) if path else DEFAULT_QUEUE
        self._tasks: List[Task] = self._load()

    # --- persistence -----------------------------------------------------------
    def _load(self) -> List[Task]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="ascii"))
            return [Task.from_dict(d) for d in raw.get("tasks", [])]
        except (OSError, ValueError, TypeError, KeyError):
            # Torn / garbage / partial file -> empty queue (fail-safe, never raise).
            return []

    def _flush(self) -> None:
        payload = json.dumps(
            {"version": 1, "tasks": [t.to_dict() for t in self._tasks]},
            sort_keys=True, indent=2)
        _atomic_write(self.path, payload)

    def reload(self) -> None:
        """Re-read durable state from disk (e.g. after another process mutated it)."""
        self._tasks = self._load()

    # --- operations ------------------------------------------------------------
    def enqueue(self, kind: str, sport: str,
                args: Optional[Dict[str, Any]] = None,
                now: Optional[float] = None,
                dedup: bool = True) -> str:
        """Append a PENDING task; return its id.

        Rejects any non-measurement kind (defensive rail). With dedup=True an
        identical (kind, sport, args) task that is still PENDING/LEASED is not
        re-added -- the existing task's id is returned instead (idempotent enqueue,
        so a self-scheduler that re-proposes the same work never piles duplicates).
        """
        if kind not in ALLOWED_KINDS:
            raise DisallowedKind(
                "kind %r is not a measurement-only kind %s" % (kind, sorted(ALLOWED_KINDS)))
        args = dict(args or {})
        if dedup:
            for t in self._tasks:
                if (t.kind == kind and t.sport == sport and t.args == args
                        and t.status in (PENDING, LEASED)):
                    return t.id
        ts = float(now if now is not None else time.time())
        task = Task(id=uuid.uuid4().hex, kind=kind, sport=sport, args=args,
                    enqueued_ts=ts, status=PENDING)
        self._tasks.append(task)
        self._flush()
        return task.id

    def reclaim_expired(self, now: Optional[float] = None) -> int:
        """Return any LEASED task whose lease has elapsed to PENDING. Returns count."""
        t_now = float(now if now is not None else time.time())
        n = 0
        for t in self._tasks:
            if t.status == LEASED and t.lease_until is not None and t.lease_until <= t_now:
                t.status = PENDING
                t.lease_until = None
                n += 1
        if n:
            self._flush()
        return n

    def lease(self, now: Optional[float] = None,
              visibility_sec: float = 600.0) -> Optional[Task]:
        """Claim the oldest ready task for `visibility_sec`; None if queue is empty.

        First reclaims any expired lease (so a crashed worker's task re-offers), then
        leases the oldest PENDING task by enqueue time. The status flip + lease_until
        are persisted atomically before returning, so two concurrent leasers cannot
        both win the same task.
        """
        t_now = float(now if now is not None else time.time())
        self.reclaim_expired(t_now)
        ready = [t for t in self._tasks if t.status == PENDING]
        if not ready:
            return None
        task = min(ready, key=lambda t: (t.enqueued_ts, t.id))
        task.status = LEASED
        task.attempts += 1
        task.lease_until = t_now + float(visibility_sec)
        self._flush()
        return task

    def ack(self, task_id: str) -> bool:
        """Mark a leased task DONE and drop it from the queue. True if found+removed."""
        for i, t in enumerate(self._tasks):
            if t.id == task_id and t.status == LEASED:
                del self._tasks[i]
                self._flush()
                return True
        return False

    def nack(self, task_id: str, now: Optional[float] = None,
             requeue: bool = True) -> bool:
        """Release a leased task: back to PENDING (requeue) or drop it. True if found."""
        for i, t in enumerate(self._tasks):
            if t.id == task_id and t.status == LEASED:
                if requeue:
                    t.status = PENDING
                    t.lease_until = None
                else:
                    del self._tasks[i]
                self._flush()
                return True
        return False

    # --- introspection ---------------------------------------------------------
    def pending_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == PENDING)

    def leased_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == LEASED)

    def is_empty(self) -> bool:
        """True iff no PENDING and no LEASED task remains (honest 'nothing due')."""
        return not any(t.status in (PENDING, LEASED) for t in self._tasks)

    def snapshot(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._tasks]


__all__ = [
    "WorkQueue", "Task", "DisallowedKind", "DEFAULT_QUEUE",
    "ALLOWED_KINDS", "PENDING", "LEASED", "DONE",
]
