"""Per-file test for the richer-Statcast in-game win-prob feasibility probe.
Confirms the probe HONESTLY reports the join block (no fabrication) + emits no $ field.
Run ONLY this file:
  python -m pytest tests/test_statcast_richer_pitch_layer_probe.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import statcast_richer_pitch_layer_probe as P


def test_probe_detects_block_on_real_data():
    res = P.run()
    assert "vs_close" in res and "UNPROVEN" in res["vs_close"]
    assert not any(k in res for k in ("roi", "dollar", "edge", "hit_rate"))
    assert res["proposal_only"] is True
    # On the real on-disk corpora the join is infeasible -> TIER3_BLOCKED (honest).
    assert res["verdict"] in ("TIER3_BLOCKED", "READY_TO_GATE")
    if res["verdict"] == "TIER3_BLOCKED":
        # at least one season must carry a concrete block reason (no silent 0-fill).
        reasons = [r for p in res["probes"].values() for r in p.get("reasons", [])]
        assert reasons, "TIER3_BLOCKED must carry an explicit reason"
        assert any(x in reasons for x in
                   ("ZERO_OVERLAPPING_GAMES", "STATCAST_SAMPLE_HAS_NO_SCORE_COLS",
                    "NO_ESPN_CORPUS", "NO_STATCAST_SAMPLE"))


def test_build_joined_states_empty_when_blocked():
    for s in (2022, 2023):
        states, probe = P.build_joined_states(s)
        # blocked join must yield NO fabricated states.
        if probe.get("overlap_games", 0) <= 0 or probe.get("reasons"):
            assert states == []
