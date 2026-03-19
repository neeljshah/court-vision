"""
Tests for src/prediction/game_prediction.py.

All tests mock network/NBA API calls so no external access is needed.
"""

from __future__ import annotations

import os
import sys
import json
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_mock_wp_model(home_prob: float = 0.65):
    """Return a mock win probability model object."""

    class _MockWPModel:
        def predict(self, home, away, season=None, game_date=None):
            return {
                "home_win_prob":    home_prob,
                "away_win_prob":    round(1.0 - home_prob, 4),
                "predicted_winner": home if home_prob >= 0.5 else away,
                "margin_est":       3.5,
                "injury_warnings":  {},
                "features":         {"home_net_rtg": 4.5, "away_net_rtg": -1.2},
            }

    return _MockWPModel()


# ── predict_game() ─────────────────────────────────────────────────────────────

class TestPredictGame:

    def test_returns_required_keys(self, monkeypatch):
        """predict_game() result has all required keys."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)

        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.65))

        result = gp.predict_game("GSW", "BOS")
        required = {
            "home_team", "away_team", "home_win_prob", "away_win_prob",
            "predicted_winner", "spread_est", "total_est", "confidence", "features"
        }
        assert required <= set(result.keys())

    def test_probs_sum_to_one(self, monkeypatch):
        """home_win_prob + away_win_prob == 1.0."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.62))

        result = gp.predict_game("GSW", "BOS")
        assert abs(result["home_win_prob"] + result["away_win_prob"] - 1.0) < 1e-4

    def test_confidence_high_when_large_edge(self, monkeypatch):
        """confidence='high' when |prob - 0.5| > 0.15."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.70))

        result = gp.predict_game("GSW", "BOS")
        assert result["confidence"] == "high"

    def test_confidence_medium(self, monkeypatch):
        """confidence='medium' when 0.08 < |prob - 0.5| <= 0.15."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.60))

        result = gp.predict_game("GSW", "BOS")
        assert result["confidence"] == "medium"

    def test_confidence_low_when_near_even(self, monkeypatch):
        """confidence='low' when |prob - 0.5| <= 0.08."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.54))

        result = gp.predict_game("GSW", "BOS")
        assert result["confidence"] == "low"

    def test_spread_positive_when_home_favoured(self, monkeypatch):
        """spread_est > 0 when home_win_prob > 0.5."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.65))

        result = gp.predict_game("GSW", "BOS")
        assert result["spread_est"] > 0

    def test_spread_negative_when_away_favoured(self, monkeypatch):
        """spread_est < 0 when home_win_prob < 0.5."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.35))

        result = gp.predict_game("GSW", "BOS")
        assert result["spread_est"] < 0

    def test_total_est_from_estimate_total(self, monkeypatch):
        """total_est is the value returned by _estimate_total."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 231.5)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.60))

        result = gp.predict_game("GSW", "BOS")
        assert result["total_est"] == 231.5

    def test_predicted_winner_is_home_when_prob_above_half(self, monkeypatch):
        """predicted_winner matches the home team when prob > 0.5."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.70))

        result = gp.predict_game("LAL", "MIA")
        assert result["predicted_winner"] == "LAL"

    def test_team_names_pass_through(self, monkeypatch):
        """home_team and away_team in result match inputs."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_estimate_total", lambda *a, **kw: 224.0)
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.55))

        result = gp.predict_game("DEN", "PHX")
        assert result["home_team"] == "DEN"
        assert result["away_team"] == "PHX"


# ── _estimate_total() ─────────────────────────────────────────────────────────

class TestEstimateTotal:

    def test_returns_league_average_when_no_cache(self, tmp_path, monkeypatch):
        """Returns 224.0 when team_stats cache file does not exist."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))

        total = gp._estimate_total("GSW", "BOS", "2024-25")
        assert total == 224.0

    def test_returns_computed_total_when_cache_exists(self, tmp_path, monkeypatch):
        """Returns formula-based total when team stats cache exists."""
        import src.prediction.game_prediction as gp

        # Build a minimal team_stats cache
        from nba_api.stats.static import teams as nba_teams_static
        all_teams = {t["abbreviation"]: t["id"] for t in nba_teams_static.get_teams()}
        gsw_id = str(all_teams["GSW"])
        bos_id = str(all_teams["BOS"])

        cache = {
            gsw_id: {"pace": 100.0, "off_rtg": 115.0, "def_rtg": 110.0, "net_rtg": 5.0},
            bos_id: {"pace": 96.0, "off_rtg": 118.0, "def_rtg": 108.0, "net_rtg": 10.0},
        }
        cache_path = tmp_path / "team_stats_2024-25.json"
        cache_path.write_text(json.dumps(cache))
        monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))

        total = gp._estimate_total("GSW", "BOS", "2024-25")
        # Expected: avg_pace=(100+96)/2=98; total=98*(115+118)/100=98*2.33=228.34
        expected = round(98.0 * (115.0 + 118.0) / 100.0, 1)
        assert total == expected

    def test_returns_league_average_for_unknown_teams(self, tmp_path, monkeypatch):
        """Returns 224.0 when team not found in cache."""
        import src.prediction.game_prediction as gp
        cache = {"99999": {"pace": 100.0, "off_rtg": 115.0}}
        cache_path = tmp_path / "team_stats_2024-25.json"
        cache_path.write_text(json.dumps(cache))
        monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))

        total = gp._estimate_total("XYZ", "ABC", "2024-25")
        assert total == 224.0


# ── predict_today() ───────────────────────────────────────────────────────────

class TestPredictToday:

    def test_empty_schedule_returns_empty_list(self, monkeypatch):
        """predict_today() returns [] when no games scheduled."""
        import src.prediction.game_prediction as gp
        monkeypatch.setattr(gp, "_fetch_today_games", lambda *a, **kw: [])

        result = gp.predict_today()
        assert result == []

    def test_results_sorted_by_confidence_desc(self, monkeypatch):
        """predict_today() returns games sorted by |home_win_prob - 0.5| descending."""
        import src.prediction.game_prediction as gp

        fake_games = [
            {"home_abbrev": "GSW", "away_abbrev": "BOS", "game_id": "g1", "game_date": "2026-03-17"},
            {"home_abbrev": "LAL", "away_abbrev": "MIA", "game_id": "g2", "game_date": "2026-03-17"},
        ]
        monkeypatch.setattr(gp, "_fetch_today_games", lambda *a, **kw: fake_games)

        probs = {"GSW": 0.72, "LAL": 0.55}

        def _mock_predict_game(home_team, away_team, season="2024-25", game_date=None):
            p = probs[home_team]
            return {
                "home_team": home_team, "away_team": away_team,
                "home_win_prob": p, "away_win_prob": round(1 - p, 4),
                "predicted_winner": home_team, "spread_est": (p - 0.5) * 30,
                "total_est": 224.0, "confidence": "high" if abs(p - 0.5) > 0.15 else "medium",
                "features": {},
            }

        monkeypatch.setattr(gp, "predict_game", _mock_predict_game)

        result = gp.predict_today()
        assert len(result) == 2
        edges = [abs(r["home_win_prob"] - 0.5) for r in result]
        assert edges[0] >= edges[1]

    def test_failed_game_skipped_not_raised(self, monkeypatch):
        """predict_today() swallows per-game errors and skips that game."""
        import src.prediction.game_prediction as gp

        fake_games = [
            {"home_abbrev": "GSW", "away_abbrev": "BOS", "game_id": "g1", "game_date": "2026-03-17"},
        ]
        monkeypatch.setattr(gp, "_fetch_today_games", lambda *a, **kw: fake_games)

        def _fail(*a, **kw):
            raise RuntimeError("model not trained")

        monkeypatch.setattr(gp, "predict_game", _fail)

        result = gp.predict_today()
        assert result == []

    def test_game_id_and_date_added(self, monkeypatch):
        """game_id and game_date are added to each prediction dict."""
        import src.prediction.game_prediction as gp

        fake_games = [
            {"home_abbrev": "DEN", "away_abbrev": "OKC",
             "game_id": "0022401234", "game_date": "2026-03-17"},
        ]
        monkeypatch.setattr(gp, "_fetch_today_games", lambda *a, **kw: fake_games)

        def _mock_predict_game(home_team, away_team, season="2024-25", game_date=None):
            return {
                "home_team": home_team, "away_team": away_team,
                "home_win_prob": 0.60, "away_win_prob": 0.40,
                "predicted_winner": home_team, "spread_est": 3.0,
                "total_est": 224.0, "confidence": "medium",
                "features": {},
            }

        monkeypatch.setattr(gp, "predict_game", _mock_predict_game)

        result = gp.predict_today()
        assert len(result) == 1
        assert result[0]["game_id"] == "0022401234"
        assert result[0]["game_date"] == "2026-03-17"


# ── _team_id_to_abbrev() ──────────────────────────────────────────────────────

class TestTeamIdToAbbrev:

    def test_known_team_id_returns_abbreviation(self):
        """Valid NBA team ID returns its abbreviation."""
        from src.prediction.game_prediction import _team_id_to_abbrev
        from nba_api.stats.static import teams as nba_teams_static
        gsw_id = next(t["id"] for t in nba_teams_static.get_teams() if t["abbreviation"] == "GSW")
        assert _team_id_to_abbrev(gsw_id) == "GSW"

    def test_unknown_team_id_returns_empty_string(self):
        """Unknown team ID returns empty string (not exception)."""
        from src.prediction.game_prediction import _team_id_to_abbrev
        assert _team_id_to_abbrev(0) == ""


# ── predict_spread() ──────────────────────────────────────────────────────────

class TestPredictSpread:

    def test_returns_required_keys(self, monkeypatch):
        """predict_spread() has home_team, away_team, spread_est, home_win_prob, confidence."""
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.65))

        from src.prediction.game_prediction import predict_spread
        result = predict_spread("GSW", "BOS")
        for key in ("home_team", "away_team", "spread_est", "home_win_prob", "confidence"):
            assert key in result

    def test_spread_positive_for_home_favourite(self, monkeypatch):
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.65))

        from src.prediction.game_prediction import predict_spread
        result = predict_spread("GSW", "BOS")
        assert result["spread_est"] > 0

    def test_spread_negative_for_away_favourite(self, monkeypatch):
        import src.prediction.win_probability as wp_mod
        monkeypatch.setattr(wp_mod, "load", lambda *a, **kw: _make_mock_wp_model(0.35))

        from src.prediction.game_prediction import predict_spread
        result = predict_spread("GSW", "BOS")
        assert result["spread_est"] < 0

    def test_confidence_labels(self, monkeypatch):
        import src.prediction.win_probability as wp_mod

        for prob, expected in [(0.70, "high"), (0.60, "medium"), (0.54, "low")]:
            monkeypatch.setattr(wp_mod, "load", lambda *a, p=prob, **kw: _make_mock_wp_model(p))
            from src.prediction.game_prediction import predict_spread
            result = predict_spread("GSW", "BOS")
            assert result["confidence"] == expected


# ── predict_total() ───────────────────────────────────────────────────────────

class TestPredictTotal:

    def test_returns_required_keys(self):
        """predict_total() has home_team, away_team, total_est, over_prob, features_used."""
        from src.prediction.game_prediction import predict_total
        result = predict_total("GSW", "BOS")
        for key in ("home_team", "away_team", "total_est", "over_prob", "features_used"):
            assert key in result

    def test_total_est_is_positive(self):
        """total_est should always be > 0."""
        from src.prediction.game_prediction import predict_total
        result = predict_total("GSW", "BOS")
        assert result["total_est"] > 0

    def test_over_prob_stub(self):
        """over_prob stub is 0.51."""
        from src.prediction.game_prediction import predict_total
        result = predict_total("GSW", "BOS")
        assert result["over_prob"] == 0.51

    def test_features_used_has_expected_keys(self):
        """features_used contains pace_diff, off_rtg_sum, def_rtg_sum, ref_over_rate."""
        from src.prediction.game_prediction import predict_total
        result = predict_total("GSW", "BOS")
        for key in ("pace_diff", "off_rtg_sum", "def_rtg_sum", "ref_over_rate"):
            assert key in result["features_used"]

    def test_total_from_cache(self, tmp_path, monkeypatch):
        """When team stats cache exists, total is computed from data."""
        import src.prediction.game_prediction as gp
        from nba_api.stats.static import teams as nba_teams_static
        all_teams = {t["abbreviation"]: t["id"] for t in nba_teams_static.get_teams()}
        gsw_id = str(all_teams["GSW"])
        bos_id = str(all_teams["BOS"])

        cache = {
            gsw_id: {"pace": 100.0, "off_rtg": 115.0, "def_rtg": 110.0, "net_rtg": 5.0},
            bos_id: {"pace": 96.0,  "off_rtg": 118.0, "def_rtg": 108.0, "net_rtg": 10.0},
        }
        cache_path = tmp_path / "team_stats_2024-25.json"
        cache_path.write_text(json.dumps(cache))
        monkeypatch.setattr(gp, "_NBA_CACHE", str(tmp_path))

        result = gp.predict_total("GSW", "BOS")
        assert result["total_est"] != 224.0   # should be data-driven


# ── predict_today() enhanced ──────────────────────────────────────────────────

class TestPredictTodayEnhanced:

    def test_edge_confidence_key_present(self, monkeypatch):
        """Each result has edge_confidence key."""
        import src.prediction.game_prediction as gp

        monkeypatch.setattr(gp, "_fetch_today_games", lambda *a, **kw: [
            {"home_abbrev": "GSW", "away_abbrev": "BOS",
             "game_id": "g1", "game_date": "2026-03-17"},
        ])

        def _mock_predict_game(home_team, away_team, season="2024-25", game_date=None):
            return {
                "home_team": home_team, "away_team": away_team,
                "home_win_prob": 0.65, "away_win_prob": 0.35,
                "predicted_winner": home_team, "spread_est": 4.5,
                "total_est": 224.0, "confidence": "high", "features": {},
            }

        monkeypatch.setattr(gp, "predict_game", _mock_predict_game)
        monkeypatch.setattr(gp, "predict_spread", lambda *a, **kw: {"spread_est": 4.5})
        monkeypatch.setattr(gp, "predict_total", lambda *a, **kw: {"total_est": 224.0, "over_prob": 0.51})

        result = gp.predict_today()
        assert len(result) == 1
        assert "edge_confidence" in result[0]

    def test_sorted_by_edge_confidence(self, monkeypatch):
        """Results sorted by edge_confidence descending."""
        import src.prediction.game_prediction as gp

        monkeypatch.setattr(gp, "_fetch_today_games", lambda *a, **kw: [
            {"home_abbrev": "GSW", "away_abbrev": "BOS", "game_id": "g1", "game_date": "2026-03-17"},
            {"home_abbrev": "LAL", "away_abbrev": "MIA", "game_id": "g2", "game_date": "2026-03-17"},
        ])

        probs = {"GSW": 0.72, "LAL": 0.55}

        def _mock_predict_game(home_team, away_team, season="2024-25", game_date=None):
            p = probs[home_team]
            return {
                "home_team": home_team, "away_team": away_team,
                "home_win_prob": p, "away_win_prob": round(1 - p, 4),
                "predicted_winner": home_team, "spread_est": (p - 0.5) * 30,
                "total_est": 224.0, "confidence": "high" if abs(p - 0.5) > 0.15 else "medium",
                "features": {},
            }

        monkeypatch.setattr(gp, "predict_game", _mock_predict_game)
        monkeypatch.setattr(gp, "predict_spread", lambda *a, **kw: {})
        monkeypatch.setattr(gp, "predict_total", lambda *a, **kw: {})

        result = gp.predict_today()
        assert len(result) == 2
        assert result[0]["edge_confidence"] >= result[1]["edge_confidence"]
