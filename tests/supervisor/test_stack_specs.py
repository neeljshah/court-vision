"""Per-file tests for supervisor.stack_specs (W12-shell additions).

Covers the 4 new measurement-only daemon ProcSpecs added by W12:
  m10_best_bets_compute, m11_ingame_pred_tick, m12_pm_paper_tick,
  m13_props_pred_tick.

Verifies (NO real process, socket, port, or file I/O):
  - All 4 specs are present in base_specs() with correct names / modules.
  - Heartbeat paths are under data/cache/daemon_heartbeats/ (correct sub-dir).
  - fresh_sec > 0 for each (stale-never-green).
  - NO depends_on on any of the 4 new specs (independent branch invariant).
  - All 4 are HEARTBEAT readiness kind (not NONE / TCP / HTTP).
  - No $ field, no registry write, no flag flip -- validated via module paths
    (all must be under scripts.platformkit.*, never src.* or kernel.*).
  - The full base_specs() list remains acyclic (topo_order succeeds).

Also covers FIX 1 (the m1_producer early-warning band): the CRITICAL producer now
carries a HEARTBEAT ReadinessSpec(fresh_sec=1500) so the health_aggregator
stale-never-green DEGRADED arm fires in the 1500-2700s silent gap. Verified through
the REAL aggregator with an injected liveness snapshot: healthy beat -> OK,
silent 1500-2700s -> DEGRADED, silent >2700s -> DOWN.

Run ONLY this file:
  python -m pytest tests/supervisor/test_stack_specs.py -q
"""
from __future__ import annotations

import pytest

from supervisor.manifest import HEARTBEAT, topo_order
from supervisor.stack_specs import base_specs

from ops import health_aggregator as agg
from ops import service_registry as sr

# --------------------------------------------------------------------------- #
# New spec names and their expected properties
# --------------------------------------------------------------------------- #
_NEW_NAMES = {
    "m10_best_bets_compute",
    "m11_ingame_pred_tick",
    "m12_pm_paper_tick",
    "m13_props_pred_tick",
}

_EXPECTED_MODULES = {
    "m10_best_bets_compute": "scripts.platformkit.bestbets.bestbets_compute_runner",
    "m11_ingame_pred_tick":  "scripts.platformkit.ingame.ingame_pred_tick_runner",
    "m12_pm_paper_tick":     "scripts.platformkit.pm_trading.pm_paper_tick_runner",
    "m13_props_pred_tick":   "scripts.platformkit.props.props_pred_tick_runner",
}

_HB_DIR = "data/cache/daemon_heartbeats/"


def _new_specs():
    """Return only the 4 new W12 ProcSpecs from base_specs()."""
    return [s for s in base_specs() if s.name in _NEW_NAMES]


# --------------------------------------------------------------------------- #
# Presence + completeness
# --------------------------------------------------------------------------- #

def test_all_four_new_specs_present():
    names = {s.name for s in base_specs()}
    assert _NEW_NAMES.issubset(names), (
        "Missing from base_specs(): %s" % (_NEW_NAMES - names)
    )


def test_no_duplicate_new_names():
    all_names = [s.name for s in base_specs()]
    for name in _NEW_NAMES:
        assert all_names.count(name) == 1, "Duplicate spec name: %s" % name


# --------------------------------------------------------------------------- #
# Module paths (must be platformkit -- never src/kernel/human-gated)
# --------------------------------------------------------------------------- #

def test_new_specs_module_paths():
    for spec in _new_specs():
        assert spec.module == _EXPECTED_MODULES[spec.name], (
            "%s module mismatch: got %r" % (spec.name, spec.module)
        )
        assert spec.module.startswith("scripts.platformkit."), (
            "%s must be under scripts.platformkit.* (human-gated src/kernel off-limits): %r"
            % (spec.name, spec.module)
        )


# --------------------------------------------------------------------------- #
# Readiness: must be HEARTBEAT (stale-never-green invariant)
# --------------------------------------------------------------------------- #

def test_new_specs_readiness_is_heartbeat():
    for spec in _new_specs():
        assert spec.readiness.kind == HEARTBEAT, (
            "%s readiness kind must be HEARTBEAT, got %r"
            % (spec.name, spec.readiness.kind)
        )


def test_new_specs_heartbeat_paths_in_correct_dir():
    for spec in _new_specs():
        hb = spec.readiness.heartbeat_path or ""
        assert hb.startswith(_HB_DIR), (
            "%s heartbeat_path must start with %r, got %r"
            % (spec.name, _HB_DIR, hb)
        )
        # Filename stem should match the spec name for liveness auto-derive.
        stem = hb[len(_HB_DIR):].removesuffix(".txt")
        assert stem == spec.name, (
            "%s heartbeat stem must equal spec name, got %r" % (spec.name, stem)
        )


def test_new_specs_fresh_sec_positive():
    for spec in _new_specs():
        fresh = spec.readiness.fresh_sec
        assert fresh is not None and fresh > 0, (
            "%s fresh_sec must be positive, got %r" % (spec.name, fresh)
        )


# --------------------------------------------------------------------------- #
# No depends_on (independent branch invariant: one dead = one red, no cascade)
# --------------------------------------------------------------------------- #

def test_new_specs_have_no_depends_on():
    for spec in _new_specs():
        assert not spec.depends_on, (
            "%s must have no depends_on (independent branch), got %r"
            % (spec.name, spec.depends_on)
        )


# --------------------------------------------------------------------------- #
# Kind must be "py" (not node, not shell)
# --------------------------------------------------------------------------- #

def test_new_specs_kind_is_py():
    for spec in _new_specs():
        assert spec.kind == "py", (
            "%s kind must be 'py', got %r" % (spec.name, spec.kind)
        )


# --------------------------------------------------------------------------- #
# Cadence plausibility: fresh_sec >= 2x expected cadence
# --------------------------------------------------------------------------- #

_MIN_FRESH = {
    "m10_best_bets_compute": 240.0,   # 2x 120s cadence
    "m11_ingame_pred_tick":  240.0,   # 2x idle (120s)
    "m12_pm_paper_tick":     120.0,   # 2x 60s cadence
    "m13_props_pred_tick":   600.0,   # 2x 300s cadence
}


def test_fresh_sec_at_least_2x_cadence():
    for spec in _new_specs():
        min_expected = _MIN_FRESH[spec.name]
        fresh = spec.readiness.fresh_sec
        assert fresh >= min_expected, (
            "%s fresh_sec %r < 2x cadence floor %r (stale-never-green requires margin)"
            % (spec.name, fresh, min_expected)
        )


# --------------------------------------------------------------------------- #
# Full base_specs() list remains acyclic after additions
# --------------------------------------------------------------------------- #

def test_full_base_specs_acyclic():
    specs = base_specs()
    ordered = topo_order(specs)   # raises CycleError if cyclic
    assert len(ordered) == len(specs), (
        "topo_order dropped specs: expected %d, got %d" % (len(specs), len(ordered))
    )


# --------------------------------------------------------------------------- #
# FIX 1 -- m1_producer (the CRITICAL forecasting producer) early-warning band.
#
# It must now carry a HEARTBEAT ReadinessSpec(fresh_sec=1500) against _PRED_HB so
# the health_aggregator stale-never-green DEGRADED arm (which requires fresh_sec is
# not None) can fire in the 1500-2700s silent gap -- the early warning that a
# default NONE readiness (fresh_sec=None) silently masked. The 2700s liveness wall
# is UNCHANGED, so genuine death still reads DOWN; 1500 sits ABOVE the slowest
# healthy beat (soccer ~1200s) with margin so a healthy idle producer never
# false-REDs. Verified end-to-end through the REAL aggregator with an injected
# liveness snapshot (no process, no port, no file I/O).
# --------------------------------------------------------------------------- #

def _producer_spec():
    return next(s for s in base_specs() if s.name == "m1_producer")


def test_producer_has_heartbeat_readiness_with_early_warning_window():
    spec = _producer_spec()
    assert spec.readiness.kind == HEARTBEAT, (
        "m1_producer readiness must be HEARTBEAT so the DEGRADED early-warning arm "
        "can fire, got %r" % spec.readiness.kind
    )
    assert spec.readiness.heartbeat_path == \
        "data/frontend/predict_service/_heartbeat.json", (
        "m1_producer must beat _PRED_HB, got %r" % spec.readiness.heartbeat_path)
    # 1500 must sit ABOVE the slowest healthy beat (soccer ~1200s) with margin so a
    # healthy idle producer never false-REDs, and BELOW the 2700s liveness/data wall
    # so the gap fires DEGRADED rather than staying GREEN.
    assert spec.readiness.fresh_sec == 1500.0, (
        "m1_producer fresh_sec must be 1500 (above 1200s slowest beat, below 2700s "
        "wall), got %r" % spec.readiness.fresh_sec)
    assert 1200.0 < spec.readiness.fresh_sec < 2700.0


def test_producer_descriptor_carries_fresh_sec():
    """The descriptor the aggregator iterates must now carry fresh_sec (was None).
    Without this the stale-never-green DEGRADED arm can never fire for m1_producer."""
    desc = next(d for d in sr.service_descriptors("default") if d.name == "m1_producer")
    assert desc.fresh_sec == 1500.0
    # liveness component + freshness source are UNCHANGED (override map still wins).
    assert desc.liveness_component == "predict_service_scheduler"
    assert desc.freshness_source == "predict_service"
    assert desc.critical is True


def _aggregate_with_producer_age(monkeypatch, producer_age):
    """Run the REAL aggregator with every other heartbeat fresh and the producer
    at *producer_age* seconds. Returns (overall, producer_row)."""
    snap = {
        "predict_service_scheduler": {"live": producer_age < 2700.0,
                                      "age_sec": producer_age, "path": "/fake/p"},
        "ingame_live_loop": {"live": True, "age_sec": 10.0, "path": "/fake/i"},
        "line_daemon": {"live": True, "age_sec": 12.0, "path": "/fake/l"},
        "paper_loop": {"live": True, "age_sec": 20.0, "path": "/fake/pa"},
    }
    monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
    status = agg.aggregate(now=1_000_000.0)
    row = next(s for s in status["services"] if s["name"] == "m1_producer")
    return status["overall"], row


def test_producer_healthy_beat_reads_ok(monkeypatch):
    """A producer beating well within cadence (600s NBA / 1200s soccer) -> OK."""
    for age in (5.0, 600.0, 1200.0, 1499.0):
        overall, row = _aggregate_with_producer_age(monkeypatch, age)
        assert overall == "ok", "age=%s should be OK, got overall=%s" % (age, overall)
        assert agg._row_severity(row) == agg.OK, "age=%s row not OK" % age


def test_producer_silent_1500_to_2700_reads_degraded(monkeypatch):
    """The restored early-warning band: silent 1500-2700s -> DEGRADED, not GREEN."""
    for age in (1500.0, 2000.0, 2699.0):
        overall, row = _aggregate_with_producer_age(monkeypatch, age)
        assert agg._row_severity(row) == agg.DEGRADED, (
            "age=%s should be DEGRADED (early warning), got %s"
            % (age, agg._row_severity(row)))
        # A CRITICAL service that is DEGRADED (not DOWN) rolls the stack to degraded.
        assert overall == "degraded", "age=%s overall=%s" % (age, overall)
        assert row["live"] is True  # still live -- not yet dead, just warning


def test_producer_silent_past_2700_reads_down(monkeypatch):
    """Past the 2700s liveness wall the CRITICAL producer is DOWN (death not masked)."""
    for age in (2701.0, 5000.0):
        overall, row = _aggregate_with_producer_age(monkeypatch, age)
        assert row["live"] is False, "age=%s should be not-live" % age
        assert agg._row_severity(row) == agg.DOWN, "age=%s row not DOWN" % age
        assert overall == "down", "age=%s critical-down should be overall=down" % age


# --------------------------------------------------------------------------- #
# S66 -- the two factory ProcSpecs, registered but NOT armed
# --------------------------------------------------------------------------- #
_S66_NAMES = ("m50_foundry_runner", "m51_artifact_refresh")


def _s66_specs():
    return {s.name: s for s in base_specs() if s.name in _S66_NAMES}


def test_s66_specs_present_and_shaped():
    specs = _s66_specs()
    assert sorted(specs) == sorted(_S66_NAMES)
    assert specs["m50_foundry_runner"].module == "scripts.platformkit.foundry_runner"
    assert (specs["m51_artifact_refresh"].module
            == "scripts.platformkit.mcp_server.artifact_refresh")
    for spec in specs.values():
        assert spec.kind == "py" and not spec.depends_on and spec.port is None
        assert spec.readiness.kind == HEARTBEAT and spec.readiness.fresh_sec > 0
        assert spec.restart_policy.max_retries is None      # restart forever


def test_m50_can_never_charge_the_fwer_ledger():
    """THE REFUSAL: --allow-charge is absent BY CONSTRUCTION from the supervised argv."""
    argv = _s66_specs()["m50_foundry_runner"].argv
    assert "--allow-charge" not in argv
    assert argv == ["--db", "data/cache/eval_gate/hypotheses.sqlite",
                    "--batch", "50", "--poll-seconds", "30"]


def test_m50_and_m51_argv_are_flags_the_module_really_accepts():
    """A ProcSpec whose argv argparse would reject is an unbootable spec."""
    import importlib

    for name, spec in _s66_specs().items():
        module = importlib.import_module(spec.module)
        parser = _parser_of(module)
        parser.parse_args(spec.argv)          # raises SystemExit on an unknown flag


def _parser_of(module):
    """The module's own ArgumentParser, captured without running anything."""
    import argparse
    import unittest.mock as mock

    captured = []

    def spy(self, *args, **kwargs):
        captured.append(self)
        raise _Stop()

    with mock.patch.object(argparse.ArgumentParser, "parse_args", autospec=True,
                           side_effect=spy):
        try:
            module.main([]) if module.__name__.endswith("artifact_refresh") else module.main()
        except _Stop:
            pass
    assert captured, "no ArgumentParser built by %s.main" % module.__name__
    return captured[0]


class _Stop(Exception):
    """Raised in place of parse_args so main() stops at the parser."""


def test_s66_specs_are_not_armed_in_the_paper_profile():
    """Registered != running. Arming is a config/boot/paper.json change the
    ORCHESTRATOR makes, plus a supervisor restart -- never this lane."""
    import json
    from pathlib import Path

    from supervisor.manifest import manifest

    services = json.loads(
        Path("config/boot/paper.json").read_text(encoding="utf-8"))["services"]
    assert not set(_S66_NAMES) & set(services)

    booted = {s.name for s in manifest("paper", services=services)}
    assert not set(_S66_NAMES) & booted
    # ... and a scratch profile that DOES include them validates (no unknown name,
    # no dangling depends_on, no cycle).
    scratch = {s.name for s in manifest("paper", services=services + list(_S66_NAMES))}
    assert set(_S66_NAMES) <= scratch
    assert len(scratch) == len(booted) + 2
