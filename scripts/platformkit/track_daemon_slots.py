"""Which daemon jobs count against ``--workers``.

`track_daemon.tick` hands a worker slot to the next clip the moment a job
leaves tracking and enters adjudication, even though adjudication is a
threaded pandas pass that keeps burning CPU inside the daemon process. The
count the daemon prints (``len(active)``) therefore stands above ``--workers``
whenever an adjudication is in flight, and the container can be over-committed
against its cgroup quota while it happens.

The cap here is OPT-IN and OFF by default. With ``adjudication_holds_slot``
false this returns exactly the expression the daemon has always used, so
behaviour, flag defaults, ledger fields, statuses and printed lines are
unchanged. Nothing here caps anything unless a caller asks for it.
"""
from __future__ import annotations


def slots_in_use(active: dict, adjudication_holds_slot: bool = False) -> int:
    """Return the number of jobs counted against ``--workers``.

    Default (uncapped, today's behaviour): only jobs that have not yet entered
    adjudication count, so an adjudicating job releases its slot immediately
    and the next clip is claimed on top of it.

    With ``adjudication_holds_slot`` set, a job keeps holding its slot from
    launch until its ledger row is written, adjudication included, so the
    active count cannot exceed ``--workers``.
    """
    if adjudication_holds_slot:
        return len(active)
    return sum(1 for job in active.values() if "adjudication" not in job)
