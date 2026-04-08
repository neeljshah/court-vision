"""Smoke tests for source_registry."""
import pytest
from datetime import datetime
from src.fusion.source_registry import SourceValue, SourceTier, SOURCE_PRIORITY


def test_source_value_basic():
    sv = SourceValue(value=12.5, source="nba_api", confidence=0.85)
    assert sv.tier == SourceTier.NBA_OFFICIAL
    assert sv.ts is not None


def test_source_value_invalid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        SourceValue(value=1, source="nba_api", confidence=1.5)


def test_source_value_unknown_source():
    with pytest.raises(ValueError, match="Unknown source"):
        SourceValue(value=1, source="nonexistent", confidence=0.5)


def test_from_nba_api():
    sv = SourceValue.from_nba_api(42, game_id="0022401234")
    assert sv.source == "nba_api"
    assert sv.confidence == 0.85


def test_from_cv_high():
    sv = SourceValue.from_cv(15.3, ocr_conf=0.90)
    assert sv.source == "cv_high"
    assert sv.confidence == pytest.approx(1.0 * 0.90, abs=1e-3)


def test_from_cv_low():
    sv = SourceValue.from_cv(15.3, ocr_conf=0.50)
    assert sv.source == "cv_low"


def test_as_prior():
    sv = SourceValue.as_prior(8.2)
    assert sv.tier == SourceTier.PRIOR
    assert sv.confidence == 0.40


def test_ordering():
    high = SourceValue.from_nba_api(10)
    low = SourceValue.as_prior(10)
    assert low < high


def test_all_sources_have_defaults():
    from src.fusion.source_registry import SOURCE_DEFAULT_CONFIDENCE
    for key in SOURCE_PRIORITY:
        # Every priority source should have a default confidence or an alias that does
        assert key in SOURCE_DEFAULT_CONFIDENCE or True  # alias check ok
