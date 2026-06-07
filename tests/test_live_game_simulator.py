"""Tests for the live event-reactive rest-of-game simulator."""
import numpy as np
import pytest

from src.sim.live_game_simulator import (
    simulate_rest_of_game, _clock_to_sec, _sec_remaining,
)


def _snap(period=3, clock="6:00", hs=58, as_=55, wemby_pf=2):
    return dict(
        home_team="SAS", away_team="NYK", home_score=hs, away_score=as_,
        period=period, clock=clock,
        players=[
            dict(player_id=1, name="Wemby", team="SAS", pts=18, reb=9, ast=3, fg3m=1,
                 stl=1, blk=3, tov=2, min=24, pf=wemby_pf, oncourt=1, is_starter=True,
                 l10_min=34, season_pts_per_min=0.74),
            dict(player_id=2, name="Fox", team="SAS", pts=15, reb=2, ast=6, fg3m=2,
                 stl=1, blk=0, tov=2, min=25, pf=3, oncourt=1, is_starter=True,
                 l10_min=33, season_pts_per_min=0.72),
            dict(player_id=3, name="Vassell", team="SAS", pts=9, reb=3, ast=2, fg3m=2,
                 stl=0, blk=0, tov=1, min=21, pf=1, oncourt=1, is_starter=True,
                 l10_min=29, season_pts_per_min=0.50),
            dict(player_id=11, name="Brunson", team="NYK", pts=21, reb=2, ast=5, fg3m=2,
                 stl=1, blk=0, tov=3, min=26, pf=2, oncourt=1, is_starter=True,
                 l10_min=36, season_pts_per_min=0.78),
            dict(player_id=12, name="KAT", team="NYK", pts=14, reb=8, ast=2, fg3m=1,
                 stl=0, blk=1, tov=2, min=25, pf=2, oncourt=1, is_starter=True,
                 l10_min=34, season_pts_per_min=0.62),
        ],
    )


def test_clock_and_remaining():
    assert _clock_to_sec("6:00") == 360.0
    assert _clock_to_sec(312) == 312.0
    assert _clock_to_sec(None) == 0.0
    # Q3 with 6:00 left -> (4-3)*720 + 360 = 1080
    assert _sec_remaining(3, 360.0) == 1080.0
    # Q4 0:00 -> 0
    assert _sec_remaining(4, 0.0) == 0.0


def test_basic_run_is_coherent():
    r = simulate_rest_of_game(_snap(), n_sims=600, seed=1)
    assert r.n_sims == 600
    assert 0.0 <= r.home_win_prob <= 1.0
    # every player's projection >= their current box (can only accumulate)
    for p in r.players:
        for s in ("pts", "reb", "ast"):
            assert p.proj_final[s] >= p.current[s] - 1e-6
    # team score samples present + final > current
    assert r.proj_home_score >= _snap()["home_score"] - 1e-6


def test_foul_out_zeros_remaining_minutes():
    r = simulate_rest_of_game(_snap(wemby_pf=6), n_sims=400, seed=1)
    wemby = r.player(1)
    assert wemby.exp_remaining_min == pytest.approx(0.0, abs=1e-6)
    assert "foul_trouble" in r.dynamics


def test_reactivity_fifth_foul_drops_star_and_shifts_winprob():
    base = simulate_rest_of_game(_snap(wemby_pf=2), n_sims=3000, seed=7)
    fouled = simulate_rest_of_game(_snap(wemby_pf=5), n_sims=3000, seed=7)
    # star projection drops, remaining minutes drop
    assert fouled.player(1).proj_final["pts"] < base.player(1).proj_final["pts"]
    assert fouled.player(1).exp_remaining_min < base.player(1).exp_remaining_min
    # availability flows through to the team win prob (the bottom-up coupling)
    assert fouled.home_win_prob < base.home_win_prob
    # a teammate absorbs the vacated minutes
    assert fouled.player(2).exp_remaining_min > base.player(2).exp_remaining_min


def test_blowout_pulls_starters():
    r = simulate_rest_of_game(
        _snap(period=4, clock="3:00", hs=110, as_=82), n_sims=400, seed=1)
    assert "blowout" in r.dynamics
    # SAS heavily favored
    assert r.home_win_prob > 0.95


def test_anchored_mode_is_accuracy_neutral():
    """With anchor_final supplied, non-pts point estimates == current+remaining
    (i.e. the anchor), so the coherent layer adds no point error on those stats."""
    snap = _snap()
    anchor = {1: dict(pts=30, reb=12, ast=5, fg3m=2, stl=2, blk=4, tov=3)}
    r = simulate_rest_of_game(snap, n_sims=500, seed=1, anchor_final=anchor)
    wemby = r.player(1)
    # reb/ast/etc proj == anchor exactly (non-pts anchored to the point estimate)
    assert wemby.proj_final["reb"] == pytest.approx(12.0, abs=1e-6)
    assert wemby.proj_final["ast"] == pytest.approx(5.0, abs=1e-6)
    assert wemby.proj_final["blk"] == pytest.approx(4.0, abs=1e-6)


def test_importing_does_not_touch_serve_path():
    """The module is pure + standalone; importing/using it has no global effect."""
    import src.sim.live_game_simulator as m
    assert hasattr(m, "simulate_rest_of_game")
    # deterministic given a seed
    a = simulate_rest_of_game(_snap(), n_sims=300, seed=5)
    b = simulate_rest_of_game(_snap(), n_sims=300, seed=5)
    assert a.home_win_prob == b.home_win_prob


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
