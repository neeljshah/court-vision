"""Per-file test for the in-game-prop CLV suppress-only guard.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/improve/test_ingame_prop_clv_guard.py -q
"""
from __future__ import annotations

from scripts.platformkit.improve import ingame_prop_clv_guard as G


def test_default_on_suppresses(monkeypatch):
    monkeypatch.delenv(G.ENV, raising=False)
    assert G.is_enabled() is True
    gate = G.clv_guard(None)
    assert gate is not None
    # any in-game prop row is suppressed (gate returns False = do-not-place)
    assert gate({"edge": 0.42, "channel": "paper_ingame_prop"}) is False
    assert gate({"edge": 0.07}) is False


def test_env_off_restores_prior(monkeypatch):
    monkeypatch.setenv(G.ENV, "0")
    assert G.is_enabled() is False
    # OFF -> returns extra unchanged (None == place as before)
    assert G.clv_guard(None) is None
    sentinel = lambda row: True
    assert G.clv_guard(sentinel) is sentinel


def test_composes_over_stricter_gate(monkeypatch):
    monkeypatch.setenv(G.ENV, "1")
    # a stricter upstream gate that would already reject -> still rejected (never loosened)
    strict_reject = lambda row: False
    gate = G.clv_guard(strict_reject)
    assert gate({"edge": 0.9}) is False
    # and even an upstream ACCEPT is still suppressed (channel is adverse)
    strict_accept = lambda row: True
    gate2 = G.clv_guard(strict_accept)
    assert gate2({"edge": 0.9}) is False


def test_no_real_money_or_edge_claim():
    txt = open(G.__file__, encoding="ascii").read().lower()
    assert "suppress-only" in txt
    assert "not an edge claim" in txt or "claims no edge" in txt or "anti-edge" in txt
