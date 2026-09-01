from scripts.platformkit.ingame.arm_registry import ArmSpec, run_shadow, verdict


def _n(rows):
    return len(rows)


def test_registry_fails_closed_without_effective_n_or_manifest():
    spec = ArmSpec("blend", lambda row: .6, _n)
    assert run_shadow(spec, {"schedule_context": 1}, [{"game": "g"}]).prediction is None
    row = {"schedule_context": 1, "market_micro": 1, "market_coherence": 1}
    assert run_shadow(spec, row, []).prediction is None


def test_registry_never_promotes_and_gate_has_exact_verdicts():
    spec = ArmSpec("blend", lambda row: .6, _n, enabled=True)
    row = {"schedule_context": 1, "market_micro": 1, "market_coherence": 1}
    assert run_shadow(spec, row, [{}]).prediction is None
    assert verdict(-.030, 268, 2, .0, True) == "SHIP_TO_SHADOW"
    assert verdict(-.034, 268, 2, .0, True) == "BEHIND"
    assert verdict(-.039, 268, 2, .0, True) == "BEHIND"
    assert verdict(None, None, 0, None, False) == "INSUFFICIENT"
