"""S150 construct tests for runner claim recovery, all against temporary SQLite."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts.platformkit import foundry_runner as runner
from scripts.platformkit.foundry import results_db
from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.runner_leases import claimer_for_pid


def _seed(db, count=1):
    hashes = [db.upsert_hypothesis(Hypothesis(
        "nba", "s150_%d" % index, "raw", (), frozenset(), "pregame", "ml"))
        for index in range(count)]
    db.enqueue(hashes, "T0")
    return hashes


def _child(db_path: Path, mode: str) -> subprocess.Popen:
    code = """
import os, signal, sys
from scripts.platformkit.foundry.results_db import ResultsDB
from scripts.platformkit.foundry.runner_leases import claim_lifecycle
from scripts.platformkit.foundry.grammar import Hypothesis
path, mode = sys.argv[1:]
with ResultsDB(path) as db:
    digest = db.upsert_hypothesis(Hypothesis('nba', 's150_child', 'raw', (), frozenset(), 'pregame', 'ml'))
    db.enqueue([digest], 'T0')
    with claim_lifecycle(db) as claimer:
        assert len(db.claim(1, tier='T0', owner=claimer)) == 1
        print('claimed', flush=True)
        if mode == 'signal':
            signal.raise_signal(signal.SIGTERM)
"""
    return subprocess.Popen([sys.executable, "-c", code, str(db_path), mode], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def test_s150_releases_claims_on_normal_exit_and_sigterm(tmp_path):
    normal = _child(tmp_path / "normal.sqlite", "normal")
    assert normal.stdout.readline().strip() == "claimed"
    assert normal.wait(timeout=10) == 0, normal.stderr.read()
    with results_db.ResultsDB(tmp_path / "normal.sqlite") as db:
        assert len(db.claim(1, tier="T0")) == 1

    terminated = _child(tmp_path / "term.sqlite", "signal")
    assert terminated.stdout.readline().strip() == "claimed"
    assert terminated.wait(timeout=10) == 128 + signal.SIGTERM, terminated.stderr.read()
    with results_db.ResultsDB(tmp_path / "term.sqlite") as db:
        assert len(db.claim(1, tier="T0")) == 1

def test_s150_reaps_a_real_dead_same_host_pid(tmp_path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    assert dead.wait(timeout=10) == 0
    with results_db.ResultsDB(tmp_path / "dead.sqlite") as db:
        _seed(db, 2)
        assert len(db.claim(2, tier="T0", owner=claimer_for_pid(dead_pid))) == 2
        other = db._c.execute("SELECT hash FROM queue ORDER BY hash LIMIT 1").fetchone()[0]
        db._c.execute("UPDATE queue SET claimer='other-host:999999' WHERE hash=?", (other,))
        assert db.reap_expired(owner=claimer_for_pid()) == 1
        assert db._c.execute("SELECT COUNT(*) FROM queue WHERE claimer='other-host:999999'").fetchone()[0] == 1


def test_s150_default_lease_is_capped_at_five_intervals(tmp_path):
    with results_db.ResultsDB(tmp_path / "lease.sqlite") as db:
        _seed(db, 50)
        assert len(db.claim(50, tier="T0")) == 50
        row = db._c.execute("SELECT lease_until, claimed_at FROM queue LIMIT 1").fetchone()
        assert int((datetime.fromisoformat(row["lease_until"]) -
                    datetime.fromisoformat(row["claimed_at"])).total_seconds()) == 4500


def test_s150_claimer_release_keeps_a_scored_tier(tmp_path):
    with results_db.ResultsDB(tmp_path / "scored.sqlite") as db:
        digest = _seed(db)[0]
        owner = claimer_for_pid()
        assert len(db.claim(1, tier="T0", owner=owner)) == 1
        db.record(results_db.TierResult(
            hash=digest, tier="T0", corpus="construct", corpus_unit="one", corpus_sha="s150",
            n=1, n_eff=1.0, brier_model=0.2, brier_close=0.2, dm_stat=0.0, raw_p=1.0,
            k_family=None, k_global=0, deflated_p=1.0, pbo=None, verdict="COVERED",
            artifact_path="construct.json"))
        assert db.release(claimer=owner) == 0


def test_s150_renews_every_hypothesis_screen(tmp_path, monkeypatch):
    calls = []
    class FakeDB:
        def claim(self, *_args, **_kwargs):
            return [Hypothesis("nba", "a", "raw", (), frozenset(), "pregame", "ml"),
                    Hypothesis("nba", "b", "raw", (), frozenset(), "pregame", "ml")]
        def renew(self, hashes):
            calls.append(tuple(hashes))
            return len(hashes)
    queue = type("Queue", (), {"db": FakeDB(), "family": "s150", "poll_seconds": 0.0,
                                 "claimer": None})()
    monkeypatch.setattr(runner, "_screen_one", lambda *_args: None)
    monkeypatch.setattr(runner, "_promotions", lambda *_args: (0, 0))
    monkeypatch.setattr(runner, "_finish", lambda *_args: {})
    runner.run_pass(0, queue, batch=2)
    assert len(calls) == 2 and all(len(hashes) == 2 for hashes in calls)
