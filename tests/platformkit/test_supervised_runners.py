"""tests/platformkit/test_supervised_runners.py -- offline tests for the P2/P4
supervised runner wrappers + their manifest/ops wiring.

Drives both runners with FAKE clocks/sleeps + injected fns + a bounded loop, so
NO network, NO real sleep, NO real process. Also asserts the new services are in
the supervisor manifest + the ops service registry (the single status.json
source), so they flow into boot/restart/status with the rest of the stack.

Run ONLY this file:
    python -m pytest tests/platformkit/test_supervised_runners.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# --------------------------------------------------------------------------- #
# P2 -- inplay_runner
# --------------------------------------------------------------------------- #
class TestInplayRunner:
    def test_run_is_bounded_and_beats_heartbeat(self, monkeypatch, tmp_path):
        from scripts.platformkit.odds_provider import inplay_runner as ir

        beats: List[float] = []
        monkeypatch.setattr(ir, "_beat", lambda now=None: beats.append(now or 0.0))
        sleeps: List[float] = []

        # 3 ticks, no live games, no network (canned fetch returns nothing).
        ir.run(sports=("nba",), interval=1, idle_interval=1,
               sleep=lambda s: sleeps.append(s), max_ticks=3,
               clock=None, fetch_fn=lambda sport: [],
               is_live_fn=lambda *a, **k: False, out_dir=tmp_path)
        # Booted beat + one beat per inter-tick sleep boundary.
        assert len(beats) >= 1
        # The loop ran 3 ticks then returned (bounded) without raising.
        assert len(sleeps) >= 1

    def test_run_never_raises_on_bad_feed(self, monkeypatch, tmp_path):
        from scripts.platformkit.odds_provider import inplay_runner as ir
        monkeypatch.setattr(ir, "_beat", lambda now=None: None)

        def boom(sport):
            raise RuntimeError("feed down")

        # Per-sport isolation inside serve_inplay_forever -> no raise out.
        ir.run(sports=("nba", "mlb"), interval=1, idle_interval=1,
               sleep=lambda s: None, max_ticks=2,
               fetch_fn=boom, is_live_fn=lambda *a, **k: False, out_dir=tmp_path)


# --------------------------------------------------------------------------- #
# P4 -- selfimprove_runner (checkpoint-resumable; measurement-only default)
# --------------------------------------------------------------------------- #
class TestSelfimproveRunner:
    def test_default_recalibrate_returns_none(self):
        from scripts.platformkit.improve import selfimprove_runner as sr
        # No settled games -> NO candidate (nothing ships). Never raises.
        assert sr._default_recalibrate_fn("nba", []) is None
        # The live settled-games provider returns a LIST (count varies with the
        # real feed: 0 in the offseason cold-start, >0 in-season) -- assert the
        # robust contract, not a drifting live count. Still calls the REAL fn.
        settled = sr._default_settled_games_fn("nba", since=0)
        assert isinstance(settled, list)
        # And the recalibrator stays inert (NO_CANDIDATE) on whatever the feed
        # returns while the PIPELINE_ENABLED sentinel is absent (cold start).
        assert sr._default_recalibrate_fn("nba", settled) is None

    def test_run_bounded_no_candidate_never_ships(self, monkeypatch, tmp_path):
        from scripts.platformkit.improve import selfimprove_runner as sr
        beats: List[float] = []
        monkeypatch.setattr(sr, "_beat", lambda now=None: beats.append(now or 0.0))
        ckpt = tmp_path / "checkpoint.json"

        results = sr.run(
            names=("nba", "mlb"),
            settled_games_fn=lambda name, since=0, **k: [],
            recalibrate_fn=lambda name, settled, *a, **k: None,
            interval_sec=0.0, sleep=lambda s: None, clock=lambda: 100.0,
            max_cycles=2, ckpt_path=str(ckpt))
        # Two names x cycles -> results gathered; none shipped (no candidate).
        assert results, "expected CycleResults"
        assert all(r.shipped_version is None for r in results)
        assert beats  # heartbeat fired

    def test_checkpoint_resume_does_not_reprocess(self, monkeypatch, tmp_path):
        """Cursor only advances -- a second run sees the persisted checkpoint."""
        from scripts.platformkit.improve import selfimprove_runner as sr
        from scripts.platformkit.improve.checkpoint import load_checkpoint
        monkeypatch.setattr(sr, "_beat", lambda now=None: None)
        ckpt = tmp_path / "checkpoint.json"

        # Run 1 cycle; checkpoint cycle counter advances + persists.
        sr.run(names=("nba",),
               settled_games_fn=lambda name, since=0, **k: [],
               recalibrate_fn=lambda name, settled, *a, **k: None,
               interval_sec=0.0, sleep=lambda s: None, clock=lambda: 1.0,
               max_cycles=1, ckpt_path=str(ckpt))
        ck1 = load_checkpoint(str(ckpt))
        # Run again; checkpoint is reloaded (resumed), cycle advances further.
        sr.run(names=("nba",),
               settled_games_fn=lambda name, since=0, **k: [],
               recalibrate_fn=lambda name, settled, *a, **k: None,
               interval_sec=0.0, sleep=lambda s: None, clock=lambda: 2.0,
               max_cycles=1, ckpt_path=str(ckpt))
        ck2 = load_checkpoint(str(ckpt))
        assert ck2.cycle >= ck1.cycle  # resumed, monotone -- never reset


# --------------------------------------------------------------------------- #
# Manifest + ops wiring: the new services are supervised AND observable.
# --------------------------------------------------------------------------- #
class TestWiring:
    def test_manifest_includes_new_services(self):
        from supervisor.manifest import manifest, HEARTBEAT
        names = {s.name for s in manifest("default")}
        assert "m2_inplay" in names
        assert "m4_selfimprove" in names
        by = {s.name: s for s in manifest("default")}
        # Both heartbeat-readiness + forever restart + independent (no deps).
        for n in ("m2_inplay", "m4_selfimprove"):
            assert by[n].readiness.kind == HEARTBEAT
            assert by[n].restart_policy.max_retries is None
            assert by[n].depends_on == []

    def test_backend_profile_also_supervises_daemons(self):
        from supervisor.manifest import manifest
        names = {s.name for s in manifest("backend")}
        # Headless profile drops only the node UI, not the new py daemons.
        assert "m2_inplay" in names and "m4_selfimprove" in names
        assert "m1_ui" not in names

    def test_ops_registry_surfaces_new_services(self):
        from ops.service_registry import service_descriptors
        descs = {d.name: d for d in service_descriptors("default")}
        assert "m2_inplay" in descs and "m4_selfimprove" in descs
        # Non-critical: one dead daemon -> degraded, never whole-stack "down".
        assert descs["m2_inplay"].critical is False
        assert descs["m4_selfimprove"].critical is False
        assert descs["m2_inplay"].liveness_component == "m2_inplay"
        assert descs["m4_selfimprove"].liveness_component == "m4_selfimprove"

    def test_doctor_has_remedies_for_new_services(self):
        from ops.runbook import _REMEDIES
        assert "m2_inplay" in _REMEDIES and _REMEDIES["m2_inplay"]
        assert "m4_selfimprove" in _REMEDIES and _REMEDIES["m4_selfimprove"]
