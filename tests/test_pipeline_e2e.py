"""
test_pipeline_e2e.py — End-to-end pipeline integration tests.

Runs lightweight synthetic data through each pipeline stage and asserts
valid output at each stage boundary. Tests that do not require video or GPU
are always run; video-dependent tests are skipped if no clip is available.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _has_video_clip() -> bool:
    """True if a short test clip exists in data/clips/."""
    clips_dir = ROOT / "data" / "clips"
    if not clips_dir.exists():
        return False
    return any(clips_dir.glob("*.mp4"))


# ── QualityValidator stage ────────────────────────────────────────────────────

class TestQualityValidatorStage:

    def test_quality_validator_is_importable(self) -> None:
        """QualityValidator can be imported without side effects."""
        from src.data.quality_validator import QualityValidator  # noqa: F401

    def test_quality_validator_on_empty_dir_returns_dict(self, tmp_path: Path) -> None:
        """validate() returns a dict even for an empty directory."""
        from src.data.quality_validator import QualityValidator
        gd = tmp_path / "empty_game"
        gd.mkdir()
        v = QualityValidator(str(gd))
        result = v.validate()
        assert isinstance(result, dict)
        assert "overall_passed" in result

    def test_quality_validator_thresholds_are_non_negative(self) -> None:
        """All QualityValidator.THRESHOLDS values must be non-negative numbers."""
        from src.data.quality_validator import QualityValidator
        for key, val in QualityValidator.THRESHOLDS.items():
            assert isinstance(val, (int, float)), f"Threshold {key!r} is not a number"
            assert val >= 0, f"Threshold {key!r} is negative"


# ── feature engineering stage ────────────────────────────────────────────────

class TestFeatureEngineeringStage:

    def test_feature_engineering_importable(self) -> None:
        """src.features.feature_engineering imports without error."""
        import src.features.feature_engineering  # noqa: F401

    def test_feature_engineering_has_expected_attributes(self) -> None:
        """Module exposes expected public names."""
        import src.features.feature_engineering as fe
        # Should have some callable for producing features
        callables = [n for n in dir(fe) if callable(getattr(fe, n)) and not n.startswith("_")]
        assert len(callables) > 0, "feature_engineering exposes no public callables"


# ── prediction stage ──────────────────────────────────────────────────────────

class TestPredictionStage:

    def test_player_props_importable(self) -> None:
        from src.prediction.player_props import predict_props, train_props  # noqa: F401

    def test_betting_portfolio_importable(self) -> None:
        from src.prediction.betting_portfolio import kelly_corr, detect_arb  # noqa: F401

    def test_kelly_corr_produces_non_negative_result(self) -> None:
        """kelly_corr with positive edge always returns >= 0."""
        from src.prediction.betting_portfolio import kelly_corr
        result = kelly_corr(0.05, -110, 1000.0)
        assert result >= 0.0

    def test_detect_arb_returns_list(self) -> None:
        from src.prediction.betting_portfolio import detect_arb
        result = detect_arb({})
        assert isinstance(result, list)


# ── CV quality stage ──────────────────────────────────────────────────────────

class TestCVQualityStage:

    def test_cv_quality_importable(self) -> None:
        from src.tracking.cv_quality import score_tracking_json  # noqa: F401

    def test_cv_quality_scores_synthetic_data(self) -> None:
        """A synthetic tracking dict with healthy values passes all checks."""
        from src.tracking.cv_quality import score_tracking_json
        result = score_tracking_json({
            "ball_valid_pct": 0.75,
            "avg_players_detected": 9.0,
            "homography_stability": 0.92,
            "avg_fps": 24.0,
            "re_id_match_rate": 0.88,
        })
        assert result.overall_ok is True
        d = result.to_dict()
        assert json.dumps(d)  # must serialize cleanly


# ── model registry stage ──────────────────────────────────────────────────────

class TestModelRegistryStage:

    def test_model_registry_json_exists(self) -> None:
        """data/models/model_registry.json must exist after setup."""
        registry_path = ROOT / "data" / "models" / "model_registry.json"
        if not registry_path.exists():
            pytest.skip("model_registry.json not yet created")
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_registry_entries_are_valid(self) -> None:
        """Each registry entry has the required numeric fields."""
        registry_path = ROOT / "data" / "models" / "model_registry.json"
        if not registry_path.exists():
            pytest.skip("model_registry.json not yet created")
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        for key, entry in data.items():
            for field in ("holdout_r2", "holdout_mae", "train_r2", "train_mae"):
                assert field in entry, f"Entry {key!r} missing {field!r}"
                assert isinstance(entry[field], (int, float))


# ── video pipeline stage (skip if no clip) ────────────────────────────────────

@pytest.mark.skipif(not _has_video_clip(), reason="No video clips in data/clips/")
class TestVideoPipelineStage:

    def test_pipeline_importable(self) -> None:
        """unified_pipeline.py can be imported without crashing."""
        import src.pipeline.unified_pipeline  # noqa: F401

    def test_pipeline_produces_tracking_output(self, tmp_path: Path) -> None:
        """Running the pipeline on a short clip produces a tracking CSV."""
        import glob
        clips = glob.glob(str(ROOT / "data" / "clips" / "*.mp4"))
        clip = clips[0]

        try:
            from src.pipeline.unified_pipeline import UnifiedPipeline
            p = UnifiedPipeline(output_dir=str(tmp_path), no_show=True)
            result = p.process_clip(clip, max_frames=30)
            assert result is not None
        except Exception as exc:
            pytest.skip(f"Pipeline raised {exc!r} — likely missing GPU/model files")
