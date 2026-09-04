"""Focused contract tests for the S230 interaction screen."""
from __future__ import annotations

import math

from scripts.platformkit.s230_pregame_scheme_interaction import OffsetInteractionPredictor, TERMS


def _state(p_base: float, outcome: int) -> dict:
    names = tuple("%s_x_%s" % term for term in TERMS)
    features = {"p_base": p_base}
    features.update({name: 0.0 for name in names})
    return {"features": features, "outcome": outcome}


def test_interaction_list_is_frozen_and_offset_is_exact() -> None:
    assert TERMS == (
        ("off_tempo_z", "def_pace_imposed_z"),
        ("off_spacing_z", "def_defender_distance_z"),
        ("off_tempo_spacing_z", "def_pace_imposed_z"),
        ("off_paint_dwell_z", "def_paint_dwell_allowed_z"),
        ("off_transition_share_z", "def_intensity_z"),
        ("off_avg_spacing_z", "def_catch_shoot_allowed_z"),
    )
    train = [_state(0.5, i % 2) for i in range(30)]
    test = _state(0.73, 1)
    predicted = OffsetInteractionPredictor()(train, test, select_inside=True)
    assert math.isclose(predicted, 0.73, rel_tol=0.0, abs_tol=1e-12)
