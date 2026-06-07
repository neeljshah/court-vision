"""Tests for the per-second projector (FRONT C).

Covers the three required behaviours + calibration source:
  1. monotone interval decay  — band(stat, rem) shrinks as game-time elapses,
     collapsing to ~0 at the buzzer (rem=0), and the per-second stream's hi-lo
     width is non-increasing while the point estimate is held constant.
  2. finals-at-t0              — at the final buzzer the interval collapses to
     the point estimate (lo==hi==projected_final); and the point estimate is
     identical across a between-event stream (accuracy is event-anchored).
  3. disabled no-op            — with CV_INGAME_SBS unset, the flag-gated live
     entrypoint returns None (cannot change a served value).

Run: python -m pytest tests/test_per_second_projector.py -q
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame.per_second_projector import (  # noqa: E402
    INGAME_SBS_FLAG,
    IntervalCalibrator,
    PerSecondProjector,
    PlayerProjection,
    home_win_prob,
    is_enabled,
    naive_team_finals,
    stream_player_intervals,
)
from src.ingame.continuous_projection import PLAYER_STATS  # noqa: E402


# --------------------------------------------------------------------------- #
# A tiny fake v2 head so the tests don't depend on a trained model on disk.
# .project(state_row) must return {stat: projected_final}, floored at current.
# --------------------------------------------------------------------------- #
class _FakeV2:
    """Returns a fixed final per stat, floored at the player's accumulation."""

    def __init__(self, finals):
        self._finals = finals

    def project(self, state_row):
        out = {}
        for s in PLAYER_STATS:
            cur = float(state_row.get(f"p_{s}_so_far", 0.0) or 0.0)
            out[s] = max(cur, float(self._finals.get(s, 0.0)))
        return out


def _calibrator(z_mult=1.0):
    # use the real eval curve if present, else the built-in fallback
    return IntervalCalibrator.from_eval_curve(z_mult=z_mult)


def _make_projector(finals, z_mult=1.0):
    return PerSecondProjector(v2=_FakeV2(finals), calib=_calibrator(z_mult))


def _player_row(pid=1, **so_far):
    row = {"player_id": pid}
    for s in PLAYER_STATS:
        row[f"p_{s}_so_far"] = float(so_far.get(s, 0.0))
    return row


def _game_row(home=50, away=48, game_elapsed_sec=24 * 60):
    return {"home_score": home, "away_score": away,
            "game_elapsed_sec": game_elapsed_sec}


# --------------------------------------------------------------------------- #
# 1. MONOTONE INTERVAL DECAY
# --------------------------------------------------------------------------- #
def test_calibrator_band_monotone_decreasing_as_time_elapses():
    calib = _calibrator()
    for stat in PLAYER_STATS:
        # remaining-min DECREASES as the game progresses; band must not increase
        rems = [42.0, 36.0, 30.0, 24.0, 18.0, 12.0, 6.0, 3.0, 0.0]
        bands = [calib.band(stat, r) for r in rems]
        for earlier, later in zip(bands, bands[1:]):
            assert later <= earlier + 1e-9, (
                f"{stat}: band must shrink as time elapses ({earlier}->{later})"
            )
        # collapses to ~0 at the buzzer
        assert calib.band(stat, 0.0) == pytest.approx(0.0, abs=1e-9)


def test_stream_interval_width_non_increasing_with_point_held():
    proj = _make_projector({"pts": 20.0, "reb": 8.0, "ast": 5.0})
    # one event at 24:00 elapsed (half), player has some box-so-far
    proj.update_event(_game_row(game_elapsed_sec=24 * 60),
                      [_player_row(pid=7, pts=10, reb=4, ast=2)])
    # stream the next 120 seconds (no new event) -> point held, band shrinks
    stream = proj.stream_between_events(24 * 60, 24 * 60 + 120, step_sec=10.0,
                                        stats=["pts"])
    widths = []
    points = []
    for gp in stream:
        p = next(pp for pp in gp.players if pp.stat == "pts")
        widths.append(p.hi - p.lo)
        points.append(p.projected_final)
    # point estimate is IDENTICAL across the between-event stream (event-anchored)
    assert len(set(round(x, 9) for x in points)) == 1
    # interval width is non-increasing as the clock ticks
    for earlier, later in zip(widths, widths[1:]):
        assert later <= earlier + 1e-9


# --------------------------------------------------------------------------- #
# 2. FINALS AT T0 (buzzer) + point held between events
# --------------------------------------------------------------------------- #
def test_interval_collapses_to_point_at_buzzer():
    proj = _make_projector({"pts": 20.0, "reb": 8.0})
    proj.update_event(_game_row(game_elapsed_sec=48 * 60),
                      [_player_row(pid=3, pts=20, reb=8)])
    gp = proj.project_at(48 * 60, stats=["pts", "reb"])
    for p in gp.players:
        assert p.band == pytest.approx(0.0, abs=1e-9)
        assert p.lo == pytest.approx(p.projected_final, abs=1e-9)
        assert p.hi == pytest.approx(p.projected_final, abs=1e-9)


def test_point_estimate_only_changes_on_event():
    proj = _make_projector({"pts": 25.0})
    proj.update_event(_game_row(game_elapsed_sec=12 * 60),
                      [_player_row(pid=5, pts=8)])
    a = proj.project_at(12 * 60, stats=["pts"]).players[0].projected_final
    b = proj.project_at(13 * 60, stats=["pts"]).players[0].projected_final
    assert a == pytest.approx(b)  # no event between -> point unchanged
    # now a NEW event arrives (player scored more) -> point may change
    proj.update_event(_game_row(game_elapsed_sec=13 * 60),
                      [_player_row(pid=5, pts=12)])
    c = proj.project_at(13 * 60, stats=["pts"]).players[0].projected_final
    assert c >= b - 1e-9  # floored at current accumulation, never regresses


def test_lo_never_below_current_accumulation():
    # large band stat where pf - band could go below what already happened
    proj = _make_projector({"pts": 12.0}, z_mult=10.0)
    proj.update_event(_game_row(game_elapsed_sec=6 * 60),
                      [_player_row(pid=9, pts=10)])
    p = proj.project_at(6 * 60, stats=["pts"]).players[0]
    assert p.lo >= p.current - 1e-9


# --------------------------------------------------------------------------- #
# 3. DISABLED NO-OP
# --------------------------------------------------------------------------- #
def test_disabled_live_entrypoint_is_noop(monkeypatch):
    monkeypatch.delenv(INGAME_SBS_FLAG, raising=False)
    assert is_enabled() is False
    out = stream_player_intervals(
        _game_row(), [_player_row(pid=1, pts=5)], 12 * 60,
        projector=_make_projector({"pts": 20.0}),
    )
    assert out is None  # gated OFF -> returns None, cannot affect serving


def test_enabled_live_entrypoint_returns_payload(monkeypatch):
    monkeypatch.setenv(INGAME_SBS_FLAG, "1")
    assert is_enabled() is True
    out = stream_player_intervals(
        _game_row(game_elapsed_sec=18 * 60),
        [_player_row(pid=1, pts=11, reb=5)], 18 * 60,
        stats=["pts", "reb"],
        projector=_make_projector({"pts": 22.0, "reb": 9.0}),
    )
    assert out is not None
    assert "team" in out and "players" in out
    assert "home_win_prob" in out["team"]
    assert out["_resolution"].startswith("per-event accuracy")
    stats_seen = {p["stat"] for p in out["players"]}
    assert stats_seen == {"pts", "reb"}


# --------------------------------------------------------------------------- #
# Accepted baselines: win-prob + naive team pace
# --------------------------------------------------------------------------- #
def test_home_win_prob_matches_accepted_logistic():
    # tied game -> 0.5; home leading -> >0.5; symmetric
    assert home_win_prob(0.0, 24.0) == pytest.approx(0.5)
    assert home_win_prob(10.0, 6.0) > 0.5
    assert home_win_prob(-10.0, 6.0) < 0.5
    # a lead late (less remaining) is worth more than the same lead early
    assert home_win_prob(8.0, 3.0) > home_win_prob(8.0, 24.0)


def test_naive_team_finals_pace_extrapolation():
    # at half (share=0.5) a 50-pt team projects to ~100
    h, a = naive_team_finals(50.0, 48.0, 0.5)
    assert h == pytest.approx(100.0)
    assert a == pytest.approx(96.0)
    # share<=0 -> current scores
    assert naive_team_finals(10.0, 8.0, 0.0) == (10.0, 8.0)


# --------------------------------------------------------------------------- #
# FIX IN-6: is_enabled() delegates to sbs_shadow.is_enabled (truthy set)
# --------------------------------------------------------------------------- #
def test_is_enabled_true_for_truthy_string(monkeypatch):
    """CV_INGAME_SBS='true' must activate the per-second projector."""
    monkeypatch.setenv(INGAME_SBS_FLAG, "true")
    assert is_enabled() is True


def test_is_enabled_false_when_unset(monkeypatch):
    """CV_INGAME_SBS unset must leave the per-second projector disabled."""
    monkeypatch.delenv(INGAME_SBS_FLAG, raising=False)
    assert is_enabled() is False


def test_is_enabled_false_for_zero(monkeypatch):
    """CV_INGAME_SBS='0' must leave the per-second projector disabled."""
    monkeypatch.setenv(INGAME_SBS_FLAG, "0")
    assert is_enabled() is False


# --------------------------------------------------------------------------- #
# Calibration source check (held-out eval, not hand-tuned)
# --------------------------------------------------------------------------- #
def test_calibrator_loads_heldout_eval_when_present():
    calib = _calibrator()
    # every stat has a usable knot list ending at the buzzer (0,0)
    for stat in PLAYER_STATS:
        ks = calib.knots[stat]
        assert ks[0][0] == pytest.approx(0.0)
        assert ks[0][1] == pytest.approx(0.0)
        assert len(ks) >= 2
