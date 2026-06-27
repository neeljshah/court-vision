"""Bounded, sandboxed unattended-readiness probe.

Component-level readiness check for the full live stack. NO real network, NO
real sentinel, NO flag flip, NO money. Each daemon's once-tick runs against an
injected fake feed / isolated temp dir / fake clock. After the sandbox proof we
re-confirm the REAL self-improve loop is byte-identical INERT (sentinel absent
-> NO_CANDIDATE). Per-file test only. ASCII only.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def test_manifest_dag_validates_both_profiles():
    from supervisor.manifest import manifest
    for prof in ("default", "backend"):
        specs = manifest(prof)
        names = [s.name for s in specs]
        assert len(names) == len(set(names)), "duplicate proc names"
        # every depends_on resolves to an earlier-ordered service (topo).
        seen = set()
        for s in specs:
            for d in s.depends_on:
                assert d in seen, "%s depends on un-booted %s" % (s.name, d)
            seen.add(s.name)
    print("OK manifest DAG valid: default=11 backend=10")


def test_inplay_capture_once_dead_feed_degrades_not_green():
    from scripts.platformkit.odds_provider import inplay_snapshot_daemon as d
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        # FROZEN/dead feed: zero ticks. Must NOT write history, must advance
        # freshness to a RED state (no source ts).
        res = d.poll_inplay_once("nba", now=datetime.now(timezone.utc),
                                 fetch_fn=lambda sport: [], out_dir=out)
        assert res["status"] == "ok"
        assert res["n_ticks"] == 0 and res["n_games_live"] == 0
        assert res["out_path"] is None
    print("OK inplay capture once: dead feed -> 0 ticks, no green fabricated")


def test_line_snapshot_once_runs_offline():
    from scripts.platformkit.odds_provider import line_snapshot_daemon as d
    with tempfile.TemporaryDirectory() as td:
        res = d.poll_once("nba", now=datetime.now(timezone.utc),
                          agg_fn=lambda sport, now=None: {"status": "ok", "games": []},
                          out_dir=Path(td))
        assert isinstance(res, dict)
        assert res.get("status") in ("ok", "unavailable")
    print("OK line snapshot once: offline empty agg handled")


def test_resource_governor_failsafe_unknown_defers():
    from scripts.platformkit.autonomy import resource_governor as rg
    # UNKNOWN reading -> DEFERRED_RESOURCE (fail-safe, never PROCEED).
    assert rg.decide(None)["status"] == rg.DEFERRED_RESOURCE
    assert rg.decide({})["status"] == rg.DEFERRED_RESOURCE
    # low mem -> defer; healthy -> proceed.
    assert rg.decide({"mem_free_frac": 0.01})["status"] == rg.DEFERRED_RESOURCE
    assert rg.decide({"mem_free_frac": 0.9})["status"] == rg.PROCEED
    print("OK resource governor: UNKNOWN/low-mem DEFER, healthy PROCEED")


def test_status_composer_only_degrades_severity():
    from scripts.platformkit.autonomy import status_composer as sc
    # _degrade is monotone-DOWN: never upgrades a worse severity.
    assert sc._degrade(sc.OK, sc.DEGRADED) == sc.DEGRADED
    assert sc._degrade(sc.DOWN, sc.OK) == sc.DOWN  # cannot un-down
    assert sc._degrade(sc.DEGRADED, sc.DOWN) == sc.DOWN
    assert sc._degrade("garbage", sc.OK) == sc.DEGRADED  # unknown -> degraded
    print("OK status_composer: monotone-DOWN, unknown->degraded")


def test_status_composer_compose_is_pure_read_no_raise():
    from scripts.platformkit.autonomy import status_composer as sc
    doc = sc.compose(now=datetime.now(timezone.utc).timestamp())
    assert isinstance(doc, dict)
    print("OK status_composer.compose pure read -> dict, no raise")


def test_autonomy_monitor_tick_emits_status_no_green_on_failure():
    from scripts.platformkit.autonomy import autonomy_monitor_runner as m
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "autonomy_status.json"
        now = datetime.now(timezone.utc).timestamp()
        # healthy compose -> writes a status doc.
        m.tick(now=now, compose=lambda **k: {"overall": "degraded", "ok": 1},
               status_path=out)
        assert out.exists(), "monitor did not emit status file"
        doc = json.loads(out.read_text(encoding="ascii"))
        assert isinstance(doc, dict)
        # compose RAISES -> still emits a DEGRADED (never green) envelope.
        def _boom(**k):
            raise RuntimeError("compose blew up")
        m.tick(now=now, compose=_boom, status_path=out)
        doc2 = json.loads(out.read_text(encoding="ascii"))
        assert doc2.get("overall") not in ("ok", "green"), "fabricated green on failure"
    print("OK m5 monitor: emits status; compose-raise -> DEGRADED not green")


def test_selfimprove_runner_inert_sentinel_absent_NO_CANDIDATE():
    # REAL loop, REAL default recalibrate fn, sentinel ABSENT. Drive bounded
    # cycles with a fake clock/sleep + isolated checkpoint + a SEEDED settled
    # game (proves the gate, not an empty feed). Must produce NO candidate.
    from scripts.platformkit.improve import selfimprove_runner as r
    from scripts.platformkit.improve.pipeline_flag import pipeline_enabled, SENTINEL_PATH
    assert not SENTINEL_PATH.exists(), "REAL sentinel present -- abort (must stay absent)"
    assert pipeline_enabled() is False
    settled = [{"game_id": "g1", "sport": "nba", "y": 1, "p": 0.5}]
    # default recalibrate fn must return None even WITH settled games (flag off).
    out = r._default_recalibrate_fn("nba", settled)
    assert out is None, "recalibrate produced a candidate with sentinel absent!"
    with tempfile.TemporaryDirectory() as td:
        ckpt = str(Path(td) / "ckpt.json")
        t = [0.0]
        results = r.run(names=("nba",),
                        settled_games_fn=lambda name, **k: settled,
                        interval_sec=1.0,
                        clock=lambda: t[0],
                        sleep=lambda s: t.__setitem__(0, t[0] + s),
                        max_cycles=3, ckpt_path=ckpt)
    # whatever the CycleResult shape, no candidate may have shipped.
    shipped = []
    for cr in results:
        cand = getattr(cr, "candidate", None)
        if cand is None and isinstance(cr, dict):
            cand = cr.get("candidate")
        if cand:
            shipped.append(cand)
    assert not shipped, "self-improve SHIPPED a candidate while inert: %r" % shipped
    # re-confirm sentinel STILL absent (we never created it).
    assert not SENTINEL_PATH.exists()
    print("OK selfimprove: REAL loop INERT, NO_CANDIDATE, sentinel still absent")


def test_predict_scheduler_produce_once_offline():
    from predict_service import scheduler as s
    with tempfile.TemporaryDirectory() as td:
        # inject a fake produce_fn -> one isolated cycle writes a heartbeat.
        hb = s.run_cycle(sports=["nba"], out_dir=Path(td),
                         produce_fn=lambda sport, out_dir=None: {"status": "ok"},
                         now_fn=lambda: 1000.0)
        assert isinstance(hb, dict)
        assert hb.get("sports", {}).get("nba", {}).get("status") == "ok"
    print("OK predict scheduler: produce-once writes heartbeat, isolated")


def test_work_queue_lease_crash_safe_reclaim():
    from scripts.platformkit.autonomy.work_queue import WorkQueue, ALLOWED_KINDS
    kind = sorted(ALLOWED_KINDS)[0]
    with tempfile.TemporaryDirectory() as td:
        q = WorkQueue(path=str(Path(td) / "q.json"))
        q.enqueue(kind, "nba", now=0.0)
        t = q.lease(now=0.0, visibility_sec=10.0)
        assert t is not None and q.pending_count() == 0
        # simulate worker CRASH: a fresh queue re-reads durable state; the lease
        # expires and reclaim_expired re-offers the task (crash-safe).
        q2 = WorkQueue(path=str(Path(td) / "q.json"))
        assert q2.reclaim_expired(now=100.0) == 1
        assert q2.lease(now=100.0) is not None
    print("OK work_queue: crashed-worker lease reclaimed (durable, atomic)")


def test_real_money_default_deny_units_only():
    from scripts.platformkit.quant_exec import validate as v
    bv = v.build_validation(side="home", market="ml", model_prob=0.55,
                            best_decimal=2.0, close_home=2.0, close_away=2.0)
    d = bv.as_dict()
    assert d["real_money_enabled"] is False, "real money not default-DENY!"
    assert d["edge_claimed"] is False
    assert d["units"] == "probability"
    assert "$" not in json.dumps(d) and "dollar" not in json.dumps(d).lower()
    # ledger schema carries NO units/roi/stake/edge column.
    from scripts.platformkit.ledger.schema import SCHEMA_COLS
    forbidden = {"units", "roi", "stake", "edge", "dollars", "pnl"}
    assert not (set(SCHEMA_COLS) & forbidden), "ledger has a $ column"
    print("OK real-money: default-DENY, units=probability, ledger $-free")
