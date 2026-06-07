"""Unit tests for src.loop.orchestrator (mocked sibling modules).

The orchestrator sequences both arms over the shared store. All heavy/skeleton
collaborators (gate, error_miner, wiring, ledger, intel_validator, bridge,
memory_writer) are monkeypatched so the test exercises the SEQUENCING +
checkpoint/budget/never-raise contracts in isolation. No GPU, no real data.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loop import orchestrator as orch  # noqa: E402
from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot  # noqa: E402
from src.loop.signal import GateResult, Hypothesis, Signal, Verdict  # noqa: E402
from src.loop.store import PointInTimeStore  # noqa: E402


# ---- fakes ------------------------------------------------------------------
class _FakeSignal(Signal):
    name = "fake_sig"
    target = "pts"
    scope = "pregame"

    def build(self, ctx):
        return 0.0

    def hypothesis(self):
        return Hypothesis(name=self.name, target=self.target,
                          scope=self.scope, statement="fake")


class _FakeSection(AtlasSection):
    name = "fake_atlas"
    entity = "player"
    source_name = "test.parquet"
    entity_ids = [101]

    def build(self, entity_id, as_of):
        return AtlasArtifact(section=self.name, entity=self.entity,
                             entity_id=entity_id, sub_fields={"rim_freq": 0.4},
                             confidence="high", as_of="2026-05-01")

    def validate(self, artifact):
        return True

    def cv_fields(self):
        return {"defender_distance_dist": CVSlot("defender_distance_dist", "dist")}


@pytest.fixture()
def store(tmp_path):
    return PointInTimeStore(store_dir=tmp_path / "store", autoload=False)


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    """Point the checkpoint at tmp and stub the collaborators with sane defaults."""
    monkeypatch.setattr(orch, "_CHECKPOINT_PATH", tmp_path / "ckpt.json")

    calls = {"ship": [], "variance": [], "record_signal": [],
             "record_atlas": [], "register": [], "memory": [], "fdr": 0}

    monkeypatch.setattr(orch._ledger, "already_tested", lambda *a, **k: False)
    monkeypatch.setattr(orch._ledger, "record_signal",
                        lambda gr, **k: calls["record_signal"].append(gr.signal_name) or "id")
    monkeypatch.setattr(orch._ledger, "record_atlas",
                        lambda art, **k: calls["record_atlas"].append(k.get("verdict")) or "id")

    def _fdr(*a, **k):
        calls["fdr"] += 1
        return {}
    monkeypatch.setattr(orch._ledger, "apply_fdr", _fdr)

    monkeypatch.setattr(orch._intel_validator, "validate",
                        lambda s, a, **k: type("VR", (), {"ok": True, "downgraded_confidence": None})())
    monkeypatch.setattr(orch._bridge, "register_section",
                        lambda s, arts, **k: calls["register"].append(s.name) or {"section": s.name})
    monkeypatch.setattr(orch._memory_writer, "write_finding",
                        lambda **k: calls["memory"].append(k["slug"]) or Path("note.md"))

    def _ship(sig, gr, **k):
        calls["ship"].append(sig.name)
        return type("WR", (), {"ok": True})()
    monkeypatch.setattr(orch._wiring, "ship_signal", _ship)
    monkeypatch.setattr(orch._wiring, "wire_variance_signal",
                        lambda sig, gr, **k: calls["variance"].append(sig.name) or type("WR", (), {"ok": True})())
    return calls


def _gate_returning(verdict):
    def _ev(signal, **k):
        return GateResult(signal_name=signal.name, verdict=verdict)
    return _ev


def _mine_one(monkeypatch):
    h = Hypothesis(name="fake_sig", target="pts", scope="pregame", statement="x")
    monkeypatch.setattr(orch._error_miner, "mine", lambda **k: [h])
    monkeypatch.setattr(orch.Orchestrator, "_discover_signals",
                        lambda self, result: {"fake_sig": _FakeSignal})


# ---- tests ------------------------------------------------------------------
def test_signal_ship_flows_to_wiring_and_ledger(monkeypatch, patched, store):
    _mine_one(monkeypatch)
    monkeypatch.setattr(orch._gate, "evaluate", _gate_returning(Verdict.SHIP))
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])

    o = orch.Orchestrator(store=store, device="cpu")
    res = o.run_iteration(arm="signals")

    assert res.verdicts["fake_sig"] == Verdict.SHIP
    assert "fake_sig" in res.shipped
    assert patched["ship"] == ["fake_sig"]
    assert patched["record_signal"] == ["fake_sig"]
    assert patched["fdr"] == 1  # multiple-comparisons recompute ran


def test_variance_only_routes_to_variance_path(monkeypatch, patched, store):
    _mine_one(monkeypatch)
    monkeypatch.setattr(orch._gate, "evaluate", _gate_returning(Verdict.VARIANCE_ONLY))
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])
    o = orch.Orchestrator(store=store, device="cpu")
    res = o.run_iteration(arm="signals")
    assert res.verdicts["fake_sig"] == Verdict.VARIANCE_ONLY
    assert patched["variance"] == ["fake_sig"]
    assert patched["ship"] == []


def test_defer_is_not_ledgered_and_backs_off(monkeypatch, patched, store):
    _mine_one(monkeypatch)
    monkeypatch.setattr(orch._gate, "evaluate", _gate_returning(Verdict.DEFER))
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])
    o = orch.Orchestrator(store=store, device="cpu")
    res = o.run_iteration(arm="signals")
    assert res.verdicts["fake_sig"] == Verdict.DEFER
    assert patched["record_signal"] == []  # DEFER not consumed
    assert o._ckpt["defer_attempts"]["fake_sig"] == 1


def test_gate_exception_never_raises(monkeypatch, patched, store):
    _mine_one(monkeypatch)

    def _boom(signal, **k):
        raise RuntimeError("gpu oom")
    monkeypatch.setattr(orch._gate, "evaluate", _boom)
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])
    o = orch.Orchestrator(store=store, device="cpu")
    res = o.run_iteration(arm="signals")
    assert res.verdicts["fake_sig"] == Verdict.DEFER
    assert any("gate fake_sig" in e for e in res.errors)


def test_intel_arm_builds_validates_persists(monkeypatch, patched, store):
    monkeypatch.setattr(orch._error_miner, "mine", lambda **k: [])
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections",
                        lambda self, r: [_FakeSection()])
    o = orch.Orchestrator(store=store, device="cpu")
    res = o.run_iteration(arm="intel")
    assert "fake_atlas" in res.atlas_built
    assert patched["register"] == ["fake_atlas"]
    assert patched["memory"] == ["atlas_player_fake_atlas"]
    assert patched["record_atlas"] == [Verdict.SHIP.value]


def test_held_out_budget_spent_exactly_once(monkeypatch, patched, store):
    captured = {"held_out": []}

    def _ev(signal, **k):
        captured["held_out"].append(k.get("held_out_once"))
        return GateResult(signal_name=signal.name, verdict=Verdict.REJECT)
    monkeypatch.setattr(orch._gate, "evaluate", _ev)
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])
    monkeypatch.setattr(orch.Orchestrator, "_discover_signals",
                        lambda self, r: {"fake_sig": _FakeSignal})
    monkeypatch.setattr(orch._error_miner, "mine",
                        lambda **k: [Hypothesis(name="fake_sig", target="pts",
                                                scope="pregame", statement="x")])
    o = orch.Orchestrator(store=store, device="cpu")
    o.run_iteration(arm="signals")
    o._ckpt["defer_attempts"] = {}  # allow re-test next iter
    monkeypatch.setattr(orch._ledger, "already_tested", lambda *a, **k: False)
    o.run_iteration(arm="signals")
    # first call claims the one-time held-out touch; second must not
    assert captured["held_out"][0] is True
    assert all(v is False for v in captured["held_out"][1:])


def test_dry_run_never_spends_held_out_or_checkpoints(monkeypatch, patched, store, tmp_path):
    _mine_one(monkeypatch)
    captured = {}

    def _ev(signal, **k):
        captured["held_out"] = k.get("held_out_once")
        return GateResult(signal_name=signal.name, verdict=Verdict.SHIP)
    monkeypatch.setattr(orch._gate, "evaluate", _ev)
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])
    o = orch.Orchestrator(store=store, device="cpu", dry_run=True)
    o.run_iteration(arm="signals")
    assert captured["held_out"] is False
    assert not (tmp_path / "ckpt.json").exists()  # dry_run writes no checkpoint


def test_run_max_iters_and_checkpoint_increment(monkeypatch, patched, store):
    monkeypatch.setattr(orch._error_miner, "mine", lambda **k: [])
    monkeypatch.setattr(orch.Orchestrator, "_discover_sections", lambda self, r: [])
    # Isolate the SEQUENCING/checkpoint logic: stub signal discovery so the
    # iteration does not instantiate + gate the 20 real signals/*.py modules
    # (the empty mine() + empty registry leaves the signals arm a clean no-op).
    monkeypatch.setattr(orch.Orchestrator, "_discover_signals", lambda self, r: {})
    o = orch.Orchestrator(store=store, device="cpu")
    results = o.run(arm="signals", max_iters=3)
    assert len(results) == 3
    assert o._ckpt["iterations"] == 3


def test_discovery_resilient_to_empty_or_missing(monkeypatch, store):
    """Empty signals/ + intel/ packages must yield empty registries, not crash."""
    o = orch.Orchestrator(store=store, device="cpu")
    res = orch.IterationResult()
    assert o._discover("definitely_not_a_pkg_xyz", Signal, res) == {}
    assert isinstance(o._discover_signals(res), dict)
