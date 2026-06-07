"""tests/test_nba_api_v3_patch.py — Phase A v3 wrapper regression set.

These tests do NOT call the live NBA API. They monkey-patch the
relevant endpoint classes and assert retry / rate-limit / shape
behaviour.
"""
from __future__ import annotations

import time

import pytest

import scripts.nba_api_v3_patch as v3


@pytest.fixture(autouse=True)
def _fast_rate_limit(monkeypatch):
    # Speed up rate-limit sleeps so the suite runs fast.
    monkeypatch.setattr(v3, "RATE_LIMIT_S", 0.01)
    monkeypatch.setattr(v3, "_BACKOFF_SCHEDULE", (0.01, 0.02))
    v3._LAST_CALL_TS = 0.0  # reset module-level state


def test_pbp_v3_returns_list(monkeypatch):
    class FakeEP:
        def __init__(self, **kw):
            pass

        def get_normalized_dict(self):
            return {"PlayByPlay": [{"actionNumber": 1, "description": "JUMP BALL"}]}

    import nba_api.stats.endpoints.playbyplayv3 as _pbp
    monkeypatch.setattr(_pbp, "PlayByPlayV3", FakeEP)

    out = v3.fetch_pbp_v3("0042400315", retries=0)
    assert isinstance(out, list)
    assert out[0]["actionNumber"] == 1


def test_pbp_v3_retries_on_timeout_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    class FlakyEP:
        def __init__(self, **kw):
            attempts["n"] += 1

        def get_normalized_dict(self):
            if attempts["n"] == 1:
                raise TimeoutError("read timed out")
            return {"PlayByPlay": [{"actionNumber": 99}]}

    import nba_api.stats.endpoints.playbyplayv3 as _pbp
    monkeypatch.setattr(_pbp, "PlayByPlayV3", FlakyEP)

    out = v3.fetch_pbp_v3("0042400315", retries=2)
    assert attempts["n"] == 2
    assert out[0]["actionNumber"] == 99


def test_pbp_v3_returns_empty_after_exhausted_retries(monkeypatch):
    class AlwaysFail:
        def __init__(self, **kw):
            pass

        def get_normalized_dict(self):
            raise TimeoutError("read timed out")

    import nba_api.stats.endpoints.playbyplayv3 as _pbp
    monkeypatch.setattr(_pbp, "PlayByPlayV3", AlwaysFail)

    out = v3.fetch_pbp_v3("0042400315", retries=1)
    assert out == []


def test_rate_limit_enforced_between_calls(monkeypatch):
    monkeypatch.setattr(v3, "RATE_LIMIT_S", 0.05)
    v3._LAST_CALL_TS = 0.0

    class FakeEP:
        def __init__(self, **kw):
            pass

        def get_normalized_dict(self):
            return {"PlayByPlay": []}

    import nba_api.stats.endpoints.playbyplayv3 as _pbp
    monkeypatch.setattr(_pbp, "PlayByPlayV3", FakeEP)

    t0 = time.time()
    v3.fetch_pbp_v3("g1", retries=0)
    v3.fetch_pbp_v3("g1", retries=0)
    elapsed = time.time() - t0
    assert elapsed >= 0.05    # second call had to wait for the limit


def test_matchups_v3_filters_by_period(monkeypatch):
    class FakeEP:
        def __init__(self, **kw):
            pass

        def get_normalized_dict(self):
            return {
                "PlayerMatchups": [
                    {"personId": 1, "period": 1},
                    {"personId": 1, "period": 2},
                    {"personId": 2, "period": 1},
                ]
            }

    import nba_api.stats.endpoints.boxscorematchupsv3 as _bm
    monkeypatch.setattr(_bm, "BoxScoreMatchupsV3", FakeEP)

    all_rows = v3.fetch_matchups_v3("g", retries=0)
    assert len(all_rows) == 3
    period1 = v3.fetch_matchups_v3("g", period=1, retries=0)
    assert len(period1) == 2


def test_box_v3_merges_traditional_and_advanced(monkeypatch):
    class TradEP:
        def __init__(self, **kw):
            pass

        def get_normalized_dict(self):
            return {"PlayerStats": [{"personId": 1, "pts": 30}]}

    class AdvEP:
        def __init__(self, **kw):
            pass

        def get_normalized_dict(self):
            return {"PlayerStats": [{"personId": 1, "usagePct": 0.31}]}

    import nba_api.stats.endpoints.boxscoretraditionalv3 as _bt
    import nba_api.stats.endpoints.boxscoreadvancedv3 as _ba
    monkeypatch.setattr(_bt, "BoxScoreTraditionalV3", TradEP)
    monkeypatch.setattr(_ba, "BoxScoreAdvancedV3", AdvEP)

    out = v3.fetch_box_v3("g", retries=0)
    assert out["traditional"][0]["pts"] == 30
    assert out["advanced"][0]["usagePct"] == 0.31


def test_is_retryable_classification():
    assert v3._is_retryable(TimeoutError("read timed out")) is True
    assert v3._is_retryable(RuntimeError("HTTP 429 Too Many Requests")) is True
    assert v3._is_retryable(RuntimeError("HTTP 403 Forbidden")) is True
    assert v3._is_retryable(RuntimeError("invalid game id")) is False
