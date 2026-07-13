"""Tests for scripts.platformkit.omni.leak_canary -- P1 acceptance canary.

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_leak_canary.py -q
"""
from __future__ import annotations

import uuid

import pytest

from scripts.platformkit.omni import feature_store as fs
from scripts.platformkit.omni import leak_canary as lc


@pytest.fixture()
def sport(monkeypatch, tmp_path):
    """Isolate each test to its own tmp store root + a unique sport name (mirrors
    test_omni_feature_store.py's fixture)."""
    monkeypatch.setattr(fs, "_STORE_ROOT", tmp_path)
    return f"testsport_{uuid.uuid4().hex[:8]}"


def _games():
    # Realized outcomes deliberately varied (not all-1s) so a real correlation
    # check has something to bite on, not a degenerate constant.
    return [
        {"entity": "g1", "game_ts": "2026-04-01T00:00:00Z", "realized": 1.0},
        {"entity": "g2", "game_ts": "2026-04-02T00:00:00Z", "realized": 0.0},
        {"entity": "g3", "game_ts": "2026-04-03T00:00:00Z", "realized": 1.0},
        {"entity": "g4", "game_ts": "2026-04-04T00:00:00Z", "realized": 0.0},
        {"entity": "g5", "game_ts": "2026-04-05T00:00:00Z", "realized": 1.0},
    ]


def test_honest_future_stamp_excluded_pregame(sport):
    games = _games()
    lc.plant_canary(sport, games)
    visible = lc.fetch_pregame(sport, games, lc.HONEST_KEY)
    assert visible.empty  # as-of guard correctly hides the future-knowable row


def test_dishonest_stamp_slips_past_get_asof(sport):
    """Documents the threat model: as-of filtering trusts the stamp, so a lied
    knowable_at DOES come back pregame -- this is exactly why a separate audit
    is needed, not a bug in get_asof()."""
    games = _games()
    lc.plant_canary(sport, games)
    visible = lc.fetch_pregame(sport, games, lc.DISHONEST_KEY)
    assert len(visible) == len(games)
    for g in games:
        row = visible.loc[visible["entity"] == g["entity"]].iloc[0]
        assert row["value"] == g["realized"]


def test_audit_catches_dishonest_canary(sport):
    games = _games()
    lc.plant_canary(sport, games)

    honest_verdict = lc.audit_canary(sport, games, lc.HONEST_KEY)
    assert honest_verdict["verdict"] == "NOT_FOUND"  # nothing pregame-visible to audit

    dishonest_verdict = lc.audit_canary(sport, games, lc.DISHONEST_KEY)
    assert dishonest_verdict["verdict"] == "CAUGHT"
    assert dishonest_verdict["feature_key"] == lc.DISHONEST_KEY
