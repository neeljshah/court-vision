"""Per-file tests for pitch_engine.pa_chain -- count-state absorption is correct."""
import numpy as np

from domains.mlb.pitch_engine.corpus import OUTCOMES, PA_EVENTS
from domains.mlb.pitch_engine.pa_chain import pa_event_dist, _PA_IX
from domains.mlb.pitch_engine.outcome import _OUT_IX


def _omat(outcome_name):
    """[12,10] that emits `outcome_name` with prob 1 in every count."""
    m = np.zeros((12, 10))
    m[:, _OUT_IX[outcome_name]] = 1.0
    return m


def test_pure_called_strike_is_strikeout():
    pa = pa_event_dist(_omat("called_strike"))
    assert abs(pa.sum() - 1.0) < 1e-9
    assert pa[_PA_IX["K"]] > 0.999


def test_pure_ball_is_walk():
    pa = pa_event_dist(_omat("ball"))
    assert pa[_PA_IX["BB"]] > 0.999


def test_pure_in_play_out_is_out():
    pa = pa_event_dist(_omat("in_play_out"))
    assert pa[_PA_IX["OUT"]] > 0.999


def test_foul_at_two_strikes_does_not_terminate_alone():
    # 50% foul, 50% called strike each pitch -> must still absorb to K (fouls at 2
    # strikes self-loop but the strike escapes), not blow up.
    m = np.zeros((12, 10))
    m[:, _OUT_IX["foul"]] = 0.5
    m[:, _OUT_IX["called_strike"]] = 0.5
    pa = pa_event_dist(m)
    assert abs(pa.sum() - 1.0) < 1e-6
    assert pa[_PA_IX["K"]] > 0.999


def test_mixed_outcomes_normalized():
    m = np.zeros((12, 10))
    m[:, _OUT_IX["ball"]] = 0.4
    m[:, _OUT_IX["called_strike"]] = 0.3
    m[:, _OUT_IX["in_play_out"]] = 0.2
    m[:, _OUT_IX["single"]] = 0.1
    pa = pa_event_dist(m)
    assert abs(pa.sum() - 1.0) < 1e-6
    assert (pa >= 0).all()
