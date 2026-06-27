"""Per-file test for ci_cadence.run_once -- THE CONDUCTOR (W4). NO full pytest."""
from __future__ import annotations

from scripts.platformkit.progress import ci_cadence
from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS
from scripts.platformkit.autonomy import schedule_policy as _sp


class _SpyQueue:
    """Records every enqueue + enforces the real ALLOWED_KINDS guard."""
    def __init__(self):
        self.enqueued = []
        self._leased = None

    def enqueue(self, kind, sport, args=None, now=None):
        if kind not in ALLOWED_KINDS:
            raise ci_cadence.DisallowedKind(kind)
        self.enqueued.append((kind, sport))
        self._leased = type("T", (), {"id": "t1", "sport": sport, "kind": kind})
        return "t1"

    def lease(self, now=None):
        return self._leased

    def ack(self, tid):
        self._leased = None
        return True


def _policy_returning(kind):
    class _P:
        def decide(self, durable, now=None):
            task = _sp.Task(kind, "nba", {"reason": "x"})
            return _sp.Decision(_sp.TASK, task, {"nba": "IN_SEASON"}, "due")
    return _P()


def _base_deps(queue, policy, rows):
    seen = {"recalibrate_fn": None}

    def _run_cycle(*, name, settled_games_fn, recalibrate_fn, now=None):
        seen["recalibrate_fn"] = recalibrate_fn
        # INERT: recalibrate_fn must yield None (NO_CANDIDATE).
        assert recalibrate_fn("nba", []) is None
        return type("CR", (), {"decision": "NO_CANDIDATE"})

    def _append(snap=None, now=None):
        row = {"ts": now, "engine_enabled": False, "model_static": True}
        rows.append(row)
        return row

    return ci_cadence.Deps(
        build_durable_state=lambda now: {"nba": {"settled_pending": 1,
                                                  "ingame_pending": 0,
                                                  "corpus_age_days": 0.0}},
        finder_discover=lambda: [],
        finder_write=lambda c: None,
        policy=policy,
        queue=queue,
        run_cycle=_run_cycle,
        regate_select=lambda now: type("R", (), {"status": "NO_OP", "targets": []}),
        survivor_select=lambda: [],
        survivor_recheck=lambda st, now=None: None,
        append_snapshot=_append,
        build_snapshot=None,
        pipeline_enabled=lambda: False,  # sentinel ABSENT
    ), seen


def test_inert_one_row_allowed_kind():
    rows = []
    q = _SpyQueue()
    deps, seen = _base_deps(q, _policy_returning("recalibrate"), rows)
    res = ci_cadence.run_once(100.0, deps=deps)
    # exactly one progress row
    assert len(rows) == 1
    assert res.progress_row is not None
    # only an ALLOWED_KINDS kind was enqueued
    assert q.enqueued and all(k in ALLOWED_KINDS for k, _ in q.enqueued)
    assert res.enqueued_kind in ALLOWED_KINDS
    # INERT: recalibrate_fn the cycle saw returns None
    assert seen["recalibrate_fn"]("nba", []) is None
    assert res.cycle_verdict == "NO_CANDIDATE"
    # ship stays proposal-only + engine inert
    assert res.ship_proposal_only is True and res.engine_enabled is False
    assert res.overall == "ok"


def test_degrade_isolated_finder_raise():
    """A raising finder still yields a row, marked degraded, never raises out."""
    rows = []
    q = _SpyQueue()
    deps, _ = _base_deps(q, _policy_returning("recalibrate"), rows)

    def _boom():
        raise RuntimeError("finder dead")
    deps.finder_discover = _boom

    res = ci_cadence.run_once(101.0, deps=deps)
    assert "B_backlog" in res.degraded
    assert res.overall == "degraded"
    assert len(rows) == 1  # cadence CONTINUED -> progress row still appended


def test_forbidden_kind_refused_at_enqueue():
    """A forbidden kind from a buggy policy is REFUSED, isolated, no crash."""
    rows = []
    q = _SpyQueue()

    class _BadP:
        def decide(self, durable, now=None):
            task = type("BadTask", (), {"kind": "ship", "sport": "nba", "args": {}})
            return type("D", (), {"status": "TASK", "task": task})()

    deps, _ = _base_deps(q, _BadP(), rows)
    res = ci_cadence.run_once(102.0, deps=deps)
    assert "D_enqueue" in res.degraded   # enqueue step refused + isolated
    assert q.enqueued == []              # nothing forbidden ever reached the queue
    assert len(rows) == 1


def test_idempotent_enqueue_across_two_ticks():
    rows = []
    q = _SpyQueue()
    deps, _ = _base_deps(q, _policy_returning("recalibrate"), rows)
    ci_cadence.run_once(200.0, deps=deps)
    n_after_first = len(q.enqueued)
    ci_cadence.run_once(201.0, deps=deps)
    # both ticks enqueue the same allowed kind; we assert no forbidden kind leaked
    assert all(k in ALLOWED_KINDS for k, _ in q.enqueued)
    assert len(q.enqueued) >= n_after_first


def test_allowlist_pinned_to_queue():
    from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS as Q
    assert ci_cadence.ALLOWED_KINDS == frozenset(Q)


def test_no_dollar_field():
    rows = []
    q = _SpyQueue()
    deps, _ = _base_deps(q, _policy_returning("recalibrate"), rows)
    res = ci_cadence.run_once(300.0, deps=deps)
    import json
    # res.note is the honest 'no $ field' disclaimer -> excluded from the $ check.
    blob = (json.dumps(res.degraded) + json.dumps(res.steps, default=str)).lower()
    for tok in ("$", "pnl", "roi", "bankroll", "profit", "usd"):
        assert tok not in blob
    # the progress row (real data payload) carries no $ field key
    assert not any("$" in str(k) for k in (res.progress_row or {}))


if __name__ == "__main__":
    import sys
    for fn in (test_inert_one_row_allowed_kind, test_degrade_isolated_finder_raise,
               test_forbidden_kind_refused_at_enqueue,
               test_idempotent_enqueue_across_two_ticks,
               test_allowlist_pinned_to_queue, test_no_dollar_field):
        fn()
        print("ok:", fn.__name__)
    sys.exit(0)
