"""P-loop — the orchestrator's discovery arm (_run_discovery_arm), the closed-loop integration.

Proves the additive wiring: OFF by default (CV_LOOP_DISCOVERY unset -> pure no-op, loop unchanged); ON ->
every discovered verdict is recorded to the discovered-signals ledger, every NON-DEFER verdict is ledgered
(FDR bookkeeping), and a SHIP is tracked. Monkeypatched discover() -> no GPU / no 101K build.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from src.loop.orchestrator import Orchestrator, IterationResult  # noqa: E402
from src.loop import discovery as _discovery  # noqa: E402
import src.loop.orchestrator as _orch_mod  # noqa: E402
from src.loop.signal import Verdict  # noqa: E402


class _Spec:
    def __init__(self, name):
        self.name = name; self.kind = "interact"; self.cols = ("a", "b")

    def family_key(self):
        return "fk_" + self.name


class _Gate:
    def __init__(self, v):
        self.verdict = v; self.metrics = {"null_z": 2.0}; self.wf_all_improve = False
        self.signal_name = "x"


class _DR:
    def __init__(self, name, v):
        self.spec = _Spec(name); self.target = "pts"; self.screen_score = 0.5; self.gate = _Gate(v)


def _orch():
    return Orchestrator(store=object(), device="cpu", dry_run=True)


def test_discovery_arm_off_by_default(monkeypatch):
    monkeypatch.delenv("CV_LOOP_DISCOVERY", raising=False)
    called = []
    monkeypatch.setattr(_discovery, "discover", lambda *a, **k: called.append(1) or [])
    o = _orch(); r = IterationResult(arm="signals")
    o._run_discovery_arm(r)
    assert not called and not r.verdicts          # flag OFF -> never imports/calls discover, no-op


def test_discovery_arm_on_records_ledgers_and_ships(monkeypatch):
    monkeypatch.setenv("CV_LOOP_DISCOVERY", "1")
    monkeypatch.setenv("CV_LOOP_DISCOVERY_TARGETS", "pts")
    drs = [_DR("disc_a", Verdict.REJECT), _DR("disc_b", Verdict.SHIP), _DR("disc_c", Verdict.DEFER)]
    monkeypatch.setattr(_discovery, "discover", lambda tgt, **k: drs)
    monkeypatch.setattr(_discovery, "load_discovered_families", lambda *a, **k: set())
    rec = []
    monkeypatch.setattr(_discovery, "record_discovered", lambda dr, **k: rec.append(dr.spec.name))
    led = []
    monkeypatch.setattr(_orch_mod._ledger, "record_signal", lambda gr, **k: led.append(gr.verdict))

    o = _orch(); r = IterationResult(arm="signals")
    o._run_discovery_arm(r)

    assert set(r.verdicts) == {"disc_a", "disc_b", "disc_c"}     # every candidate got a verdict
    assert set(rec) == {"disc_a", "disc_b", "disc_c"}            # every verdict -> discovered ledger
    assert len(led) == 2                                          # only non-DEFER -> main ledger (REJECT+SHIP)
    assert "disc_b" in r.shipped                                 # the SHIP is tracked


def test_discovery_arm_never_raises_on_discover_error(monkeypatch):
    monkeypatch.setenv("CV_LOOP_DISCOVERY", "1")
    monkeypatch.setattr(_discovery, "load_discovered_families", lambda *a, **k: set())

    def _boom(*a, **k):
        raise RuntimeError("gpu exploded")
    monkeypatch.setattr(_discovery, "discover", _boom)
    o = _orch(); r = IterationResult(arm="signals")
    o._run_discovery_arm(r)                                      # must capture, not raise
    assert any("discover" in e for e in r.errors)
