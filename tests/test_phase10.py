"""test_phase10.py — Phase 10: Tier 4-5 ML Models.

Tests:
- Each model instantiates without error.
- Untrained models return safe, valid-range defaults.
- Trained models (on synthetic data) save and reload correctly.
- sim_models.FatigueModel still returns valid multiplier.
"""
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

# ── synthetic training data ───────────────────────────────────────────────────

N = 80  # enough to exceed _MIN=20


def _synthetic_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "frame":                  np.arange(N),
        "player_id":              np.tile(["p1", "p2", "p3", "p4"], N // 4 + 1)[:N],
        "_game":                  np.repeat(["g1", "g2"], N // 2),
        "velocity":               rng.uniform(0, 5, N),
        "vel_toward_basket":      rng.uniform(-1, 3, N),
        "distance_to_ball":       rng.uniform(0, 20, N),
        "distance_to_basket":     rng.uniform(1, 30, N),
        "nearest_opponent":       rng.uniform(0.5, 10, N),
        "nearest_teammate":       rng.uniform(0.5, 10, N),
        "team_spacing":           rng.uniform(50, 400, N),
        "paint_count_own":        rng.integers(0, 4, N),
        "paint_count_opp":        rng.integers(0, 4, N),
        "court_zone":             rng.choice(["paint", "mid_range", "3pt_arc"], N),
        "drive_flag":             rng.integers(0, 2, N),
        "fast_break_flag":        rng.integers(0, 2, N),
        "possession_duration_sec": rng.uniform(2, 24, N),
        "possession_duration":    rng.uniform(60, 720, N),
        "scoreboard_period":      rng.choice([1, 2, 3, 4], N),
        "scoreboard_score_diff":  rng.uniform(-20, 20, N),
        "shot_clock_est":         rng.uniform(0, 24, N),
        "handler_isolation":      rng.uniform(0.5, 8, N),
        "event":                  rng.choice(["none", "shot", "pass", "turnover"], N),
        "team":                   rng.choice(["home", "away"], N),
        "play_type":              rng.choice(["drive", "catch_shoot", "post"], N),
    })


# ── Tier 4 ────────────────────────────────────────────────────────────────────

class TestReboundPositioningModel:
    def test_instantiate(self):
        from src.prediction.tier4_models import ReboundPositioningModel
        m = ReboundPositioningModel()
        assert hasattr(m, "_trained")

    def test_default_predict(self):
        from src.prediction.tier4_models import ReboundPositioningModel
        m = ReboundPositioningModel()
        m._trained = False
        result = m.predict()
        assert 0.0 <= result <= 1.0

    def test_train_and_predict(self):
        from src.prediction.tier4_models import ReboundPositioningModel
        m = ReboundPositioningModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(vel_toward_basket=1.5, distance_to_ball=3.0)
        assert 0.0 <= result <= 1.0

    def test_save_load(self, tmp_path, monkeypatch):
        from src.prediction import tier4_models
        monkeypatch.setattr(tier4_models, "_MDIR", str(tmp_path))
        from src.prediction.tier4_models import ReboundPositioningModel
        m = ReboundPositioningModel()
        m.train(_synthetic_df())
        assert m._trained
        m2 = ReboundPositioningModel()
        assert m2._trained


class TestFatigueCurveModel:
    def test_instantiate(self):
        from src.prediction.tier4_models import FatigueCurveModel
        m = FatigueCurveModel()
        assert hasattr(m, "_trained")

    def test_default_heuristic(self):
        from src.prediction.tier4_models import FatigueCurveModel
        m = FatigueCurveModel()
        m._trained = False
        # heavy schedule → below 1.0 multiplier
        result = m.predict(dist_per100=6.0, minutes=36.0, games_in_last_14=10)
        assert 0.85 <= result <= 1.05

    def test_train_and_predict(self):
        from src.prediction.tier4_models import FatigueCurveModel
        m = FatigueCurveModel()
        m.train(_synthetic_df())
        result = m.predict(dist_per100=5.0, minutes=30.0, games_in_last_14=8)
        assert 0.85 <= result <= 1.05


class TestLateGameEfficiencyModel:
    def test_instantiate_and_default(self):
        from src.prediction.tier4_models import LateGameEfficiencyModel
        m = LateGameEfficiencyModel()
        m._trained = False
        assert m.predict(period=4) == 0.50

    def test_train_valid_probability(self):
        from src.prediction.tier4_models import LateGameEfficiencyModel
        m = LateGameEfficiencyModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(period=4, score_diff=-5.0, minutes_played=35.0)
        assert 0.0 <= result <= 1.0


class TestCloseoutQualityModel:
    def test_default(self):
        from src.prediction.tier4_models import CloseoutQualityModel
        m = CloseoutQualityModel()
        m._trained = False
        assert m.predict() == 0.0

    def test_train_range(self):
        from src.prediction.tier4_models import CloseoutQualityModel
        m = CloseoutQualityModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(closeout_speed=4.0, shot_clock=5.0)
        assert -0.10 <= result <= 0.10


class TestHelpDefenseModel:
    def test_default(self):
        from src.prediction.tier4_models import HelpDefenseModel
        m = HelpDefenseModel()
        m._trained = False
        assert m.predict() == 0.30

    def test_train_probability(self):
        from src.prediction.tier4_models import HelpDefenseModel
        m = HelpDefenseModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(avg_defensive_pressure=2.0, spacing=150.0)
        assert 0.0 <= result <= 1.0


class TestBallStagnationModel:
    def test_default_range(self):
        from src.prediction.tier4_models import BallStagnationModel
        m = BallStagnationModel()
        m._trained = False
        result = m.predict(pass_count=8.0, drive_count=0.0, screen_count=2.0)
        assert 0.0 <= result <= 1.0

    def test_train(self):
        from src.prediction.tier4_models import BallStagnationModel
        m = BallStagnationModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(pass_count=6.0, drive_count=1.0, screen_count=2.0)
        assert 0.0 <= result <= 1.0


class TestScreenEffectivenessModel:
    def test_default(self):
        from src.prediction.tier4_models import ScreenEffectivenessModel
        m = ScreenEffectivenessModel()
        m._trained = False
        assert m.predict() == 0.15

    def test_train_range(self):
        from src.prediction.tier4_models import ScreenEffectivenessModel
        m = ScreenEffectivenessModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(screen_count=2.0, spacing=250.0)
        assert 0.0 <= result <= 1.0


class TestTurnoverPressureModel:
    def test_default(self):
        from src.prediction.tier4_models import TurnoverPressureModel
        m = TurnoverPressureModel()
        m._trained = False
        assert m.predict() == 0.12

    def test_train_probability(self):
        from src.prediction.tier4_models import TurnoverPressureModel
        m = TurnoverPressureModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(avg_pressure_score=2.0, play_type="drive")
        assert 0.0 <= result <= 1.0


# ── Tier 5 ────────────────────────────────────────────────────────────────────

class TestLineupChemistryModel:
    def test_stub_returns_zero(self):
        from src.prediction.tier5_models import LineupChemistryModel
        m = LineupChemistryModel()
        assert m.predict() == 0.0
        assert not m._trained

    def test_train_is_noop(self):
        from src.prediction.tier5_models import LineupChemistryModel
        m = LineupChemistryModel()
        m.train(_synthetic_df())  # should not raise
        assert not m._trained


class TestDefensiveMatchupMatrix:
    def test_instantiate_no_error(self):
        from src.prediction.tier5_models import DefensiveMatchupMatrix
        m = DefensiveMatchupMatrix()
        assert hasattr(m, "_data")

    def test_fallback_league_avg(self):
        from src.prediction.tier5_models import DefensiveMatchupMatrix
        m = DefensiveMatchupMatrix()
        result = m.predict(player_a="unknown_player", player_b="unknown_defender")
        assert result == 112.0


class TestSubstitutionTimingModel:
    def test_inherits_base_logic(self):
        from src.prediction.tier5_models import SubstitutionTimingModel
        m = SubstitutionTimingModel()
        # 5 fouls → always sub (base logic)
        assert m.should_sub(5, 30.0, 0.0, 4)

    def test_train_and_predict(self):
        from src.prediction.tier5_models import SubstitutionTimingModel
        m = SubstitutionTimingModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.should_sub(2, 20.0, 15.0, 4)
        assert isinstance(result, bool)


class TestMomentumModel:
    def test_default_range(self):
        from src.prediction.tier5_models import MomentumModel
        m = MomentumModel()
        m._trained = False
        result = m.predict(run_length=3)
        assert 0.0 <= result <= 1.0

    def test_train(self):
        from src.prediction.tier5_models import MomentumModel
        m = MomentumModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(run_length=2, score_diff=5.0, fast_break=True)
        assert 0.0 <= result <= 1.0


class TestFoulDrawingModel:
    def test_default_fta_tendency(self):
        from src.prediction.tier5_models import FoulDrawingModel
        m = FoulDrawingModel()
        m._trained = False
        assert m.predict(fta_tendency=0.20) == 0.20

    def test_train(self):
        from src.prediction.tier5_models import FoulDrawingModel
        m = FoulDrawingModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(drives_per_36=8.0, fta_tendency=0.20, play_type="drive")
        assert 0.0 <= result <= 1.0


class TestSecondChanceModel:
    def test_default_formula(self):
        from src.prediction.tier5_models import SecondChanceModel
        m = SecondChanceModel()
        m._trained = False
        result = m.predict(oreb_rate=0.25)
        assert abs(result - 0.25 * 2.0 * 0.58) < 1e-6

    def test_train_range(self):
        from src.prediction.tier5_models import SecondChanceModel
        m = SecondChanceModel()
        m.train(_synthetic_df())
        assert m._trained
        result = m.predict(oreb_rate=0.30, proximity=3.0)
        assert 0.0 <= result <= 2.0


class TestPacePerLineupModel:
    def test_stub_default(self):
        from src.prediction.tier5_models import PacePerLineupModel
        m = PacePerLineupModel()
        assert m.predict(team="UNKNOWN") == 14.0

    def test_train_returns_team_avg(self):
        from src.prediction.tier5_models import PacePerLineupModel
        df = _synthetic_df()
        m = PacePerLineupModel()
        m.train(df)
        result = m.predict(team="home")
        assert result > 0.0


# ── FatigueModel wiring ───────────────────────────────────────────────────────

class TestFatigueModelWiring:
    def test_predict_valid_range(self):
        from src.prediction.sim_models import FatigueModel
        m = FatigueModel()
        result = m.predict(dist_per100=5.0, minutes=36.0, games_in_last_14=9)
        assert 0.85 <= result <= 1.05

    def test_batch_predict_shape(self):
        from src.prediction.sim_models import FatigueModel
        m = FatigueModel()
        arr = m.batch_predict(10)
        assert arr.shape == (10,)
        assert np.all(arr == 1.0)


# ── train_all convenience ─────────────────────────────────────────────────────

def test_train_all_tier4():
    from src.prediction.tier4_models import train_all_tier4
    results = train_all_tier4(_synthetic_df())
    assert isinstance(results, dict)
    assert len(results) == 8


def test_train_all_tier5():
    from src.prediction.tier5_models import train_all_tier5
    results = train_all_tier5(_synthetic_df())
    assert isinstance(results, dict)
    assert len(results) == 7
