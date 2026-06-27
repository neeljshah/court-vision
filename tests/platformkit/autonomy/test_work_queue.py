"""Per-file tests for the durable lease-based work queue (A5/D3).

Asserts: enqueue/lease/ack round-trip; crash-before-ack re-leases after the visibility
timeout (lossless across restart); atomic persistence survives a simulated mid-write;
empty queue -> honest is_empty; never writes outside data/cache/autonomy/; a non-
measurement kind is rejected (rail).

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
     tests/platformkit/autonomy/test_work_queue.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.autonomy import work_queue as wq
from scripts.platformkit.autonomy.work_queue import (
    DisallowedKind, LEASED, PENDING, WorkQueue)


def _qpath(tmp_path):
    return str(tmp_path / "wq.json")


def test_enqueue_lease_ack_roundtrip(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    assert q.is_empty()
    tid = q.enqueue("recalibrate", "nba", {"k": 1}, now=100.0)
    assert q.pending_count() == 1
    assert not q.is_empty()

    t = q.lease(now=101.0, visibility_sec=600.0)
    assert t is not None and t.id == tid
    assert t.status == LEASED and t.attempts == 1
    assert q.leased_count() == 1 and q.pending_count() == 0

    assert q.ack(tid) is True
    assert q.is_empty()
    # acking a non-leased / unknown id is a no-op false.
    assert q.ack(tid) is False


def test_crash_before_ack_releases_after_timeout(tmp_path):
    path = _qpath(tmp_path)
    q = WorkQueue(path)
    tid = q.enqueue("regate_ingame", "mlb", now=0.0)
    leased = q.lease(now=0.0, visibility_sec=300.0)
    assert leased is not None and leased.lease_until == 300.0

    # Simulate a crash: a brand-new process loads durable state, never acked.
    q2 = WorkQueue(path)
    assert q2.leased_count() == 1
    # Before the lease expires, nothing is leasable.
    assert q2.lease(now=299.0, visibility_sec=300.0) is None
    # After the visibility timeout the task re-offers losslessly.
    re = q2.lease(now=301.0, visibility_sec=300.0)
    assert re is not None and re.id == tid
    assert re.attempts == 2  # attempt count carried across the restart


def test_reclaim_expired_counts(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    q.enqueue("recalibrate", "nba", now=0.0)
    q.lease(now=0.0, visibility_sec=10.0)
    assert q.reclaim_expired(now=5.0) == 0   # not yet expired
    assert q.reclaim_expired(now=11.0) == 1   # expired -> back to PENDING
    assert q.pending_count() == 1


def test_nack_requeue_and_drop(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    tid = q.enqueue("refresh_corpora", "soccer", now=0.0)
    q.lease(now=0.0)
    assert q.nack(tid, now=1.0, requeue=True) is True
    assert q.pending_count() == 1
    q.lease(now=2.0)
    assert q.nack(tid, now=3.0, requeue=False) is True
    assert q.is_empty()


def test_atomic_persistence_survives_simulated_midwrite(tmp_path, monkeypatch):
    path = _qpath(tmp_path)
    q = WorkQueue(path)
    q.enqueue("recalibrate", "nba", {"v": 1}, now=0.0)  # establishes prior good state

    # Force the NEXT atomic write to crash AFTER the tmp file is written but BEFORE
    # os.replace swaps it in -- i.e. a torn write. The live file must be untouched.
    real_replace = wq.os.replace

    def boom(src, dst):
        raise OSError("simulated power loss during replace")

    monkeypatch.setattr(wq.os, "replace", boom)
    with pytest.raises(OSError):
        q.enqueue("regate_ingame", "mlb", now=1.0)
    monkeypatch.setattr(wq.os, "replace", real_replace)

    # A fresh load sees the PRIOR consistent state, never a half-written file.
    q2 = WorkQueue(path)
    snap = q2.snapshot()
    assert len(snap) == 1 and snap[0]["kind"] == "recalibrate"
    # The file on disk is valid JSON (the prior good document).
    json.loads(open(path, encoding="ascii").read())


def test_torn_or_garbage_file_loads_empty(tmp_path):
    path = _qpath(tmp_path)
    with open(path, "w", encoding="ascii") as fh:
        fh.write('{"tasks": [ {"id": "x"  ')  # truncated garbage
    q = WorkQueue(path)
    assert q.is_empty()  # fail-safe: never raises, starts clean


def test_empty_queue_is_honest_idle(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    assert q.is_empty()
    assert q.lease(now=0.0) is None  # nothing to hand out
    assert q.pending_count() == 0 and q.leased_count() == 0


def test_dedup_idempotent_enqueue(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    a = q.enqueue("recalibrate", "nba", {"x": 1}, now=0.0)
    b = q.enqueue("recalibrate", "nba", {"x": 1}, now=1.0)
    assert a == b and q.pending_count() == 1
    c = q.enqueue("recalibrate", "nba", {"x": 2}, now=2.0)  # different args
    assert c != a and q.pending_count() == 2


def test_disallowed_kind_rejected(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    for bad in ("ship", "flag_on", "place_bet", "promote"):
        with pytest.raises(DisallowedKind):
            q.enqueue(bad, "nba", now=0.0)
    assert q.is_empty()


def test_lease_picks_oldest_first(tmp_path):
    q = WorkQueue(_qpath(tmp_path))
    q.enqueue("recalibrate", "nba", {"n": 1}, now=10.0)
    second = q.enqueue("recalibrate", "mlb", {"n": 2}, now=5.0)  # older ts
    t = q.lease(now=20.0)
    assert t is not None and t.id == second  # oldest enqueued_ts wins


def test_default_store_under_cache_autonomy():
    # Rail: durable state defaults under data/cache/autonomy/, never data/registry/.
    p = str(wq.DEFAULT_QUEUE).replace("\\", "/")
    assert "/data/cache/autonomy/" in p
    assert "/data/registry/" not in p
