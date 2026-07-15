"""Per-file tests for scripts.platformkit.execution.sizing.

LEVER 2 (tier-based sizing, team markets only, pre-registered 2026-07-15):
team/moneyline tiers A=2.0/B=1.5/C=1.0 units; props (or any non-team
market_type) always flat 1.0 regardless of tier; unknown tier -> 1.0.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/execution/test_sizing.py -q
"""
from __future__ import annotations

from scripts.platformkit.execution import sizing as X


def test_team_market_tiers_scale():
    assert X.stake_for("A", "moneyline") == 2.0
    assert X.stake_for("B", "moneyline") == 1.5
    assert X.stake_for("C", "moneyline") == 1.0
    assert X.stake_for("a", "team") == 2.0  # case-insensitive tier


def test_prop_market_always_flat_regardless_of_tier():
    assert X.stake_for("A", "prop") == 1.0
    assert X.stake_for("B", "prop") == 1.0
    assert X.stake_for("C", "prop") == 1.0
    assert X.stake_for(None, "prop") == 1.0


def test_unknown_market_type_defaults_flat():
    assert X.stake_for("A", "arb") == 1.0
    assert X.stake_for("A", "unrecognized") == 1.0


def test_unknown_or_missing_tier_on_team_market_defaults_flat():
    assert X.stake_for(None, "moneyline") == 1.0
    assert X.stake_for("Z", "moneyline") == 1.0
    assert X.stake_for("", "moneyline") == 1.0


def test_tier_sizing_env_toggle_default_on():
    import os
    os.environ.pop("CV_TIER_SIZING", None)
    assert X.tier_sizing_enabled() is True


def test_tier_sizing_env_toggle_off(monkeypatch):
    monkeypatch.setenv("CV_TIER_SIZING", "0")
    assert X.tier_sizing_enabled() is False


def test_tier_sizing_env_toggle_explicit_on(monkeypatch):
    monkeypatch.setenv("CV_TIER_SIZING", "1")
    assert X.tier_sizing_enabled() is True


if __name__ == "__main__":
    test_team_market_tiers_scale()
    test_prop_market_always_flat_regardless_of_tier()
    test_unknown_market_type_defaults_flat()
    test_unknown_or_missing_tier_on_team_market_defaults_flat()
    test_tier_sizing_env_toggle_default_on()
    print("test_sizing self-checks OK")
