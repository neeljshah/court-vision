"""P1.1 — entity-agent build.py: field-mirror fidelity + seed-locked byte-identity vs TeamModel.

Gates (D01 §9, RED-C5):
  1. validate(agent) passes (structural contract).
  2. Every SimAgent required-float field mirrors TeamModel.rate[pid] EXACTLY (no clone drift).
  3. A seed-locked sim on to_legacy_team_model(agent) is byte-identical to a fresh
     TeamModel.from_cache — the Stage-2 cutover path predict_ensemble16 will use.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from sim.agent import build  # noqa: E402
from sim.agent.schema import _REQUIRED_FLOAT_FIELDS, validate, SimAgent, TeamAgent  # noqa: E402


@pytest.fixture(scope="module")
def agent():
    return build.build_team_agent("NYK")


def test_validate_passes(agent):
    validate(agent)  # raises on any structural violation
    assert isinstance(agent, TeamAgent)
    assert len(agent.agents) >= 8
    assert all(isinstance(a, SimAgent) for a in agent.agents.values())


def test_to_legacy_returns_teammodel(agent):
    from sim.basketball_sim import TeamModel
    legacy = build.to_legacy_team_model(agent)
    assert isinstance(legacy, TeamModel)
    assert legacy.tri == agent.tri == "NYK"


def test_field_mirror_exact(agent):
    """Each SimAgent required-float field equals the wrapped TeamModel.rate value EXACTLY."""
    legacy = build.to_legacy_team_model(agent)
    for pid, ag in agent.agents.items():
        r = legacy.rate[pid]
        for f in _REQUIRED_FLOAT_FIELDS:
            av, bv = getattr(ag, f), r[f]
            # NaN-safe: a faithfully-mirrored NaN equals the source NaN (nan == nan is False in Python)
            assert av == bv or (av != av and bv != bv), \
                f"pid={pid} field={f}: agent={av} != rate={bv}"
        # defense ratings the kernel actually reads
        assert ag.int_d == r["int_d"] and ag.perim_d == r["perim_d"]


def test_tier_is_full_pbp_for_finals_team(agent):
    # NYK has recency_rates -> FULL_PBP tier
    tiers = {p.tier for p in agent.provenance.values()}
    assert "FULL_PBP" in tiers


def test_byte_identical_sim_cpu():
    """Seed-locked CPU sim on to_legacy_team_model(agent) == fresh from_cache (cutover transparency)."""
    from sim.basketball_sim import TeamModel
    from sim.fast_sim import simulate_game_fast

    away = TeamModel.from_cache("SAS")
    legacy = build.to_legacy_team_model(build.build_team_agent("NYK"))
    fresh = TeamModel.from_cache("NYK")

    kw = dict(n_sims=1500, seed=7, anchor=True, defense=True, dispersion=True, dev="cpu")
    r_agent = simulate_game_fast(legacy, away, **kw)
    r_fresh = simulate_game_fast(fresh, away, **kw)

    assert np.array_equal(np.asarray(r_agent.home_total), np.asarray(r_fresh.home_total)), "home_total drift"
    assert np.array_equal(np.asarray(r_agent.away_total), np.asarray(r_fresh.away_total)), "away_total drift"
