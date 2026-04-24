"""
test_phase9.py — Phase 9: Automated Feedback Loop + NLP Models

Tests:
  - Game detection (new vs already-processed)
  - Retrain trigger logic (threshold crossing)
  - Model versioning (update_registry, rollback)
  - NLP severity classifier (predict, train, edge cases)
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.pipeline.feedback_loop import FeedbackLoop, _RETRAIN_TRIGGERS, _NO_AUTO_RETRAIN
from src.prediction.nlp_models import (
    InjurySeverityClassifier,
    InjuryLagModel,
    TeamSentimentModel,
    ReporterCredibilityRanker,
    _severity_label,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_dir(tmp_path):
    """Temporary directory for models, videos, processed list."""
    return tmp_path


@pytest.fixture()
def feedback_loop(tmp_dir, monkeypatch):
    """FeedbackLoop wired to a temp directory, dry_run=False."""
    monkeypatch.setattr("src.pipeline.feedback_loop._MODELS_DIR",    str(tmp_dir / "models"))
    monkeypatch.setattr("src.pipeline.feedback_loop._VIDEOS_DIR",    str(tmp_dir / "videos"))
    monkeypatch.setattr("src.pipeline.feedback_loop._PROCESSED_TXT", str(tmp_dir / "processed.txt"))
    monkeypatch.setattr("src.pipeline.feedback_loop._REGISTRY_PATH", str(tmp_dir / "models" / "registry.json"))
    (tmp_dir / "models").mkdir()
    (tmp_dir / "videos").mkdir()
    return FeedbackLoop(dry_run=False)


@pytest.fixture()
def dry_loop(tmp_dir, monkeypatch):
    """FeedbackLoop in dry_run mode."""
    monkeypatch.setattr("src.pipeline.feedback_loop._MODELS_DIR",    str(tmp_dir / "models"))
    monkeypatch.setattr("src.pipeline.feedback_loop._VIDEOS_DIR",    str(tmp_dir / "videos"))
    monkeypatch.setattr("src.pipeline.feedback_loop._PROCESSED_TXT", str(tmp_dir / "processed.txt"))
    monkeypatch.setattr("src.pipeline.feedback_loop._REGISTRY_PATH", str(tmp_dir / "models" / "registry.json"))
    (tmp_dir / "models").mkdir()
    (tmp_dir / "videos").mkdir()
    return FeedbackLoop(dry_run=True)


# ── Game detection ─────────────────────────────────────────────────────────────

class TestDetectNewGames:
    def test_empty_videos_dir(self, feedback_loop):
        assert feedback_loop.detect_new_games() == []

    def test_detects_mp4(self, feedback_loop, tmp_dir):
        (tmp_dir / "videos" / "game1.mp4").write_text("fake")
        result = feedback_loop.detect_new_games()
        assert "game1.mp4" in result

    def test_skips_processed(self, feedback_loop, tmp_dir):
        (tmp_dir / "videos" / "game1.mp4").write_text("fake")
        (tmp_dir / "processed.txt").write_text("game1.mp4\n")
        assert feedback_loop.detect_new_games() == []

    def test_only_new_unprocessed(self, feedback_loop, tmp_dir):
        (tmp_dir / "videos" / "game1.mp4").write_text("fake")
        (tmp_dir / "videos" / "game2.mp4").write_text("fake")
        (tmp_dir / "processed.txt").write_text("game1.mp4\n")
        result = feedback_loop.detect_new_games()
        assert result == ["game2.mp4"]

    def test_ignores_non_video_files(self, feedback_loop, tmp_dir):
        (tmp_dir / "videos" / "readme.txt").write_text("not a video")
        assert feedback_loop.detect_new_games() == []

    def test_detects_mkv(self, feedback_loop, tmp_dir):
        (tmp_dir / "videos" / "game3.mkv").write_text("fake")
        result = feedback_loop.detect_new_games()
        assert "game3.mkv" in result


# ── Retrain trigger logic ──────────────────────────────────────────────────────

class TestCheckRetrainTriggers:
    def test_returns_dict_with_all_models(self, feedback_loop):
        result = feedback_loop.check_retrain_triggers()
        assert isinstance(result, dict)
        for model in _RETRAIN_TRIGGERS:
            assert model in result

    def test_no_data_means_no_trigger(self, feedback_loop):
        result = feedback_loop.check_retrain_triggers()
        # With no event files, no counts → no triggers
        for model, should in result.items():
            assert should is False, f"{model} should not trigger with zero data"

    def test_trigger_fires_when_threshold_crossed(self, feedback_loop, tmp_dir, monkeypatch):
        # Simulate enough events to cross props threshold (10 gamelogs/player → 10 games * 10 = 100)
        events_dir = tmp_dir / "events"
        events_dir.mkdir()
        monkeypatch.setattr(
            "src.pipeline.feedback_loop.FeedbackLoop._get_data_counts",
            lambda self: {"shots": 60, "possessions": 250, "games": 25,
                          "gamelogs_per_player": 15, "games_per_player": 6},
        )
        result = feedback_loop.check_retrain_triggers()
        # xfg_v2 needs 50 shots (60 available) → trigger
        assert result["xfg_v2"] is True
        # props_pts needs 10 gamelogs/player (15 available) → trigger
        assert result["props_pts"] is True

    def test_no_auto_retrain_models_never_trigger(self, feedback_loop, monkeypatch):
        monkeypatch.setattr(
            "src.pipeline.feedback_loop.FeedbackLoop._get_data_counts",
            lambda self: {"shots": 9999, "possessions": 9999, "games": 9999,
                          "gamelogs_per_player": 9999, "games_per_player": 9999},
        )
        result = feedback_loop.check_retrain_triggers()
        for no_auto in _NO_AUTO_RETRAIN:
            if no_auto in result:
                assert result[no_auto] is False

    def test_low_r2_model_skipped(self, feedback_loop, monkeypatch):
        # Plant a low-R² registry entry for xfg_v2
        feedback_loop.update_registry("xfg_v2", 1, {"r2": 0.15, "brier": 0.28}, 100)
        monkeypatch.setattr(
            "src.pipeline.feedback_loop.FeedbackLoop._get_data_counts",
            lambda self: {"shots": 9999, "possessions": 9999, "games": 9999,
                          "gamelogs_per_player": 9999, "games_per_player": 9999},
        )
        result = feedback_loop.check_retrain_triggers()
        assert result["xfg_v2"] is False


# ── Model versioning ───────────────────────────────────────────────────────────

class TestModelVersioning:
    def test_update_registry_creates_entry(self, feedback_loop, tmp_dir):
        feedback_loop.update_registry("props_pts", 1, {"mae": 4.5, "r2": 0.47}, 1000)
        reg_path = tmp_dir / "models" / "registry.json"
        assert reg_path.exists()
        reg = json.loads(reg_path.read_text())
        assert "props_pts" in reg
        assert reg["props_pts"]["current_version"] == 1
        assert reg["props_pts"]["n_samples"] == 1000

    def test_update_registry_increments_version(self, feedback_loop):
        feedback_loop.update_registry("props_pts", 1, {"mae": 4.5}, 1000)
        feedback_loop.update_registry("props_pts", 2, {"mae": 4.3}, 1100)
        entry = feedback_loop._registry_entry("props_pts")
        assert entry["current_version"] == 2

    def test_rollback_restores_previous(self, feedback_loop, tmp_dir):
        models_dir = tmp_dir / "models"
        # Create dummy v1 and v2 pkl files
        v1_path = models_dir / "props_pts_v1.pkl"
        v2_path = models_dir / "props_pts_v2.pkl"
        v1_path.write_bytes(pickle.dumps({"version": 1}))
        v2_path.write_bytes(pickle.dumps({"version": 2}))

        feedback_loop.update_registry("props_pts", 2, {"mae": 4.5}, 1000)
        result = feedback_loop.rollback_model("props_pts")
        assert result is True

        current_path = models_dir / "props_pts_current.pkl"
        assert current_path.exists()
        restored = pickle.loads(current_path.read_bytes())
        assert restored["version"] == 1

    def test_rollback_fails_gracefully_when_no_prior(self, feedback_loop):
        feedback_loop.update_registry("new_model", 1, {}, 0)
        result = feedback_loop.rollback_model("new_model")
        assert result is False

    def test_dry_run_retrain_skips_execution(self, dry_loop):
        result = dry_loop.retrain_model("props_pts")
        assert result["promoted"] is False
        assert result.get("version", 0) == 0


# ── NLP: Severity classifier ───────────────────────────────────────────────────

class TestInjurySeverityClassifier:
    def setup_method(self):
        self.clf = InjurySeverityClassifier()
        self.clf.train()  # Ensure trained on seed data

    def test_train_returns_metrics(self):
        metrics = self.clf.train()
        assert "n_samples" in metrics
        assert "accuracy" in metrics
        assert metrics["n_samples"] > 0
        assert 0.0 <= metrics["accuracy"] <= 1.0

    def test_predict_out_is_high_severity(self):
        score = self.clf.predict("out ankle tonight")
        assert score >= 0.5, f"Expected high severity, got {score}"

    def test_predict_healthy_is_low_severity(self):
        score = self.clf.predict("healthy no restrictions available to play")
        assert score <= 0.5, f"Expected low severity, got {score}"

    def test_predict_questionable_is_medium(self):
        score = self.clf.predict("questionable hamstring game-time decision")
        assert 0.1 <= score <= 0.9, f"Expected medium severity, got {score}"

    def test_predict_returns_float(self):
        score = self.clf.predict("some injury text")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_severity_label_helper(self):
        assert _severity_label(0.9) == "high"
        assert _severity_label(0.5) == "medium"
        assert _severity_label(0.1) == "low"

    def test_empty_string_doesnt_crash(self):
        score = self.clf.predict("")
        assert 0.0 <= score <= 1.0

    def test_custom_training_data(self):
        examples = [
            ("player is out", 1.0), ("player is out", 1.0),
            ("available", 0.0), ("available", 0.0),
        ]
        metrics = self.clf.train(examples)
        assert metrics["n_samples"] == 4
        assert metrics["accuracy"] == 1.0


# ── NLP: Lag model ────────────────────────────────────────────────────────────

class TestInjuryLagModel:
    def setup_method(self):
        self.lag = InjuryLagModel()

    def test_tier1_reporter_fastest(self):
        result = self.lag.predict("wojespn", severity=0.5)
        assert result["tier"] == "tier1"
        assert result["lag_median"] <= 15

    def test_tier3_reporter_slowest(self):
        result = self.lag.predict("randomuser123", severity=0.5)
        assert result["tier"] == "tier3"
        assert result["lag_median"] >= 60

    def test_high_severity_shrinks_window(self):
        low_sev  = self.lag.predict("wojespn", severity=0.1)
        high_sev = self.lag.predict("wojespn", severity=0.9)
        assert high_sev["window_minutes"] <= low_sev["window_minutes"]

    def test_returns_required_keys(self):
        result = self.lag.predict("wojespn", severity=0.5)
        for key in ("tier", "lag_min", "lag_median", "lag_max", "window_minutes"):
            assert key in result


# ── NLP: Sentiment model ──────────────────────────────────────────────────────

class TestTeamSentimentModel:
    def setup_method(self):
        self.model = TeamSentimentModel()

    def test_positive_text(self):
        score = self.model.score(["great win team is healthy focused energy"])
        assert score > 0

    def test_negative_text(self):
        score = self.model.score(["frustrated struggle injured tension conflict"])
        assert score < 0

    def test_empty_list(self):
        score = self.model.score([])
        assert score == 0.0

    def test_rolling_average(self):
        self.model.score(["win great confident"])
        self.model.score(["lose struggle tired"])
        avg = self.model.rolling_sentiment(window=2)
        assert isinstance(avg, float)

    def test_score_in_range(self):
        score = self.model.score(["neutral text about the game"])
        assert -1.0 <= score <= 1.0


# ── NLP: Credibility ranker ───────────────────────────────────────────────────

class TestReporterCredibilityRanker:
    def setup_method(self):
        self.ranker = ReporterCredibilityRanker()

    def test_woj_high_credibility(self):
        assert self.ranker.rank("wojespn") >= 0.85

    def test_unknown_reporter_gets_prior(self):
        score = self.ranker.rank("nobodyknows999")
        assert 0.0 <= score <= 1.0

    def test_rank_batch_sorted_descending(self):
        handles = ["wojespn", "randomguy", "ianbegg"]
        ranked  = self.ranker.rank_batch(handles)
        scores  = list(ranked.values())
        assert scores == sorted(scores, reverse=True)

    def test_top_n_returns_n_items(self):
        handles = ["wojespn", "ianbegg", "randomguy1", "randomguy2"]
        top = self.ranker.top_n(handles, n=2)
        assert len(top) == 2

    def test_top_n_highest_first(self):
        handles = ["wojespn", "randomguy123"]
        top = self.ranker.top_n(handles, n=2)
        assert top[0][1] >= top[1][1]
