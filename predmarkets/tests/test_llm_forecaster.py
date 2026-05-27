"""Unit tests for LLMForecaster — no network, fake Anthropic client."""

from __future__ import annotations

from unittest import mock

import pytest

from predmarkets.forecasters.llm_forecaster import (
    LLMForecaster,
    _confidence_score,
    _parse_response,
)


def test_parse_response_bare_json() -> None:
    out = _parse_response('{"prob_yes": 0.42, "reasoning": "x", "confidence": "med"}')
    assert out is not None
    assert out["prob_yes"] == pytest.approx(0.42)
    assert out["reasoning"] == "x"
    assert out["confidence_label"] == "med"


def test_parse_response_strips_code_fence() -> None:
    raw = '```json\n{"prob_yes": 0.1, "reasoning": "", "confidence": "low"}\n```'
    out = _parse_response(raw)
    assert out is not None
    assert out["prob_yes"] == pytest.approx(0.1)


def test_parse_response_finds_embedded_json() -> None:
    raw = 'Here is my answer: {"prob_yes": 0.7, "reasoning": "polls", "confidence": "high"} ok?'
    out = _parse_response(raw)
    assert out is not None
    assert out["prob_yes"] == pytest.approx(0.7)


def test_parse_response_rejects_out_of_range() -> None:
    assert _parse_response('{"prob_yes": 1.5, "reasoning": "x", "confidence": "med"}') is None


def test_parse_response_rejects_garbage() -> None:
    assert _parse_response("absolutely not parseable") is None


def test_confidence_score_mapping() -> None:
    assert _confidence_score("low") == 0.15
    assert _confidence_score("med") == 0.30
    assert _confidence_score("high") == 0.45
    assert _confidence_score("???") == 0.25


def test_applies_to_rejects_crypto() -> None:
    fc = LLMForecaster(client=object())  # bypass real client init
    fc._client_ok = True
    market = {"category": "Crypto", "question_or_title": "x", "volume_24h": 1e6, "status": "open"}
    assert fc.applies_to(market) is False


def test_applies_to_rejects_low_volume() -> None:
    fc = LLMForecaster(client=object(), min_volume_24h=5000)
    fc._client_ok = True
    market = {"category": "Politics", "question_or_title": "x", "volume_24h": 100, "status": "open"}
    assert fc.applies_to(market) is False


def test_applies_to_rejects_closed_market() -> None:
    fc = LLMForecaster(client=object())
    fc._client_ok = True
    market = {"category": "Politics", "question_or_title": "x",
              "volume_24h": 100000, "status": "resolved"}
    assert fc.applies_to(market) is False


def test_applies_to_accepts_politics_when_client_ok() -> None:
    fc = LLMForecaster(client=object(), min_volume_24h=5000)
    fc._client_ok = True
    market = {"category": "Politics", "question_or_title": "Will Trump...",
              "volume_24h": 10000, "status": "open"}
    assert fc.applies_to(market) is True


def test_applies_to_rejects_without_client() -> None:
    fc = LLMForecaster()
    fc._client_ok = False
    market = {"category": "Politics", "question_or_title": "x",
              "volume_24h": 100000, "status": "open"}
    assert fc.applies_to(market) is False


def test_forecast_uses_cached_response(tmp_path, monkeypatch) -> None:
    # Patch cache dir to a temp location
    import predmarkets.forecasters.llm_forecaster as mod
    monkeypatch.setattr(mod, "_CACHE_DIR", str(tmp_path))

    # Pre-write a cache entry
    import json, os
    from datetime import datetime, timezone
    cache_path = os.path.join(
        str(tmp_path),
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}__TEST123.json",
    )
    with open(cache_path, "w") as fh:
        json.dump({"prob_yes": 0.65, "reasoning": "cached", "confidence_label": "high"}, fh)

    fc = LLMForecaster(client=object(), min_volume_24h=0)
    fc._client_ok = True
    forecast = fc.forecast({
        "market_id": "TEST123",
        "category": "Politics",
        "question_or_title": "Test",
        "volume_24h": 100000,
        "status": "open",
    })
    assert forecast is not None
    assert forecast.prob_yes == pytest.approx(0.65)
    assert forecast.confidence == pytest.approx(0.45)
    assert "cached" in forecast.reasoning


def test_forecast_skips_cached_errors(tmp_path, monkeypatch) -> None:
    import predmarkets.forecasters.llm_forecaster as mod
    monkeypatch.setattr(mod, "_CACHE_DIR", str(tmp_path))
    import json, os
    from datetime import datetime, timezone
    cache_path = os.path.join(
        str(tmp_path),
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}__TEST_ERR.json",
    )
    with open(cache_path, "w") as fh:
        json.dump({"error": "rate limited"}, fh)

    fc = LLMForecaster(client=object(), min_volume_24h=0)
    fc._client_ok = True
    forecast = fc.forecast({
        "market_id": "TEST_ERR",
        "category": "Politics",
        "question_or_title": "x",
        "volume_24h": 100000,
        "status": "open",
    })
    assert forecast is None
