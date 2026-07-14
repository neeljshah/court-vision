"""Tests for scripts.platformkit.claims.card_consumer -- P5, synthetic VALIDATED cards.

Zero real cards are VALIDATED today (10 accruing, n_fired=0), so this exercises the
consumption MECHANISM end-to-end on synthetic cards built directly (never touches the
real registry file -- everything routes through tmp_path).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_card_consumer.py -q
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.platformkit.claims import card_consumer as cc

_TS = "2026-07-14T00:00:00Z"


def _ingame_card(card_id="card_ingame01"):
    return {
        "card_id": card_id, "status": "VALIDATED",
        "condition": {"scope": "ingame", "window": "midQ1_to_endQ1",
                      "trigger": "quarter == 1", "entity": "game"},
        "claim": "test ingame claim", "mechanism": "test mechanism",
        "expected_sign": "+",
    }


def _pregame_card(card_id="card_pregame01"):
    return {
        "card_id": card_id, "status": "VALIDATED",
        "condition": {"scope": "pregame", "trigger": "spacing_pctile_home <= 0.25", "entity": "game"},
        "claim": "test pregame claim", "mechanism": "test mechanism",
        "expected_sign": "-",
    }


class _FakeRegistry:
    """Stands in for card_registry -- get_all_latest() returns a fixed dict."""

    def __init__(self, cards):
        self._cards = {c["card_id"]: c for c in cards}

    def get_all_latest(self):
        return self._cards


def test_env_flag_default_off():
    name = cc.env_flag_name("card_abc")
    assert name == "CV_CLAIMS_CARD_ABC"
    os.environ.pop(name, None)
    assert cc.is_flag_on("card_abc") is False


def test_env_flag_on_when_set(monkeypatch):
    name = cc.env_flag_name("card_xyz")
    monkeypatch.setenv(name, "1")
    assert cc.is_flag_on("card_xyz") is True


def test_route_ingame_writes_shadow_only_default_off(tmp_path: Path):
    routes = tmp_path / "routes.jsonl"
    card = _ingame_card()
    entry = cc.route_ingame(card, _TS, path=routes)
    assert entry["shadow_only"] is True
    assert entry["promoted"] is False
    assert entry["env_flag"] == "CV_CLAIMS_CARD_INGAME01"
    assert entry["env_flag_default"] == "0"
    assert entry["edge_claimed"] is False
    assert routes.is_file()


def test_route_pregame_writes_trust_segment(tmp_path: Path):
    trust = tmp_path / "trust.jsonl"
    card = _pregame_card()
    entry = cc.route_pregame(card, _TS, path=trust)
    assert entry["trust"] == "TRUSTED"
    assert entry["kind"] == "pregame_trust_segment"
    assert trust.is_file()


def test_emit_proven_line_includes_n_and_effect(tmp_path: Path):
    proven = tmp_path / "proven.jsonl"
    card = _ingame_card()
    grade = {"n_fired": 123, "detail": {
        "half_a": {"brier_delta": -0.01}, "half_b": {"brier_delta": -0.02}}}
    line = cc.emit_proven_line(card, grade, _TS, path=proven)
    assert line["n_fired"] == 123
    assert line["effect"]["half_a_brier_delta"] == -0.01
    assert line["edge_claimed"] is False


def test_emit_proven_line_handles_missing_grade(tmp_path: Path):
    proven = tmp_path / "proven.jsonl"
    line = cc.emit_proven_line(_ingame_card(), None, _TS, path=proven)
    assert line["n_fired"] == 0


def test_consume_card_ingame_routes_and_proves(tmp_path: Path):
    routes, trust, proven, consumed = (tmp_path / n for n in
        ("routes.jsonl", "trust.jsonl", "proven.jsonl", "consumed.jsonl"))
    result = cc.consume_card(_ingame_card(), ts=_TS, routes_path=routes,
                             trust_path=trust, proven_path=proven, consumed_path=consumed)
    assert result["scope"] == "ingame"
    assert "route" in result and result["route"]["shadow_only"] is True
    assert "trust_segment" not in result
    assert proven.is_file() and consumed.is_file()


def test_consume_card_pregame_trust_and_proves(tmp_path: Path):
    routes, trust, proven, consumed = (tmp_path / n for n in
        ("routes.jsonl", "trust.jsonl", "proven.jsonl", "consumed.jsonl"))
    result = cc.consume_card(_pregame_card(), ts=_TS, routes_path=routes,
                             trust_path=trust, proven_path=proven, consumed_path=consumed)
    assert result["scope"] == "pregame"
    assert "trust_segment" in result
    assert "route" not in result


def test_consume_all_end_to_end_synthetic_validated_card(tmp_path: Path):
    routes, trust, proven, consumed, ledger = (tmp_path / n for n in
        ("routes.jsonl", "trust.jsonl", "proven.jsonl", "consumed.jsonl", "ledger.jsonl"))
    reg = _FakeRegistry([_ingame_card(), _pregame_card("card_open01")])
    reg._cards["card_open01"]["status"] = "OPEN"  # not validated -> must be skipped
    summary = cc.consume_all(ts=_TS, registry_module=reg, ledger_path=ledger,
                             routes_path=routes, trust_path=trust, proven_path=proven,
                             consumed_path=consumed)
    assert summary["n_validated_total"] == 1
    assert summary["n_newly_consumed"] == 1
    assert summary["edge_claimed"] is False
    assert routes.is_file()
    assert not trust.is_file()  # only the OPEN pregame card existed, never consumed


def test_consume_all_is_idempotent(tmp_path: Path):
    routes, trust, proven, consumed, ledger = (tmp_path / n for n in
        ("routes.jsonl", "trust.jsonl", "proven.jsonl", "consumed.jsonl", "ledger.jsonl"))
    reg = _FakeRegistry([_ingame_card()])
    cc.consume_all(ts=_TS, registry_module=reg, ledger_path=ledger, routes_path=routes,
                   trust_path=trust, proven_path=proven, consumed_path=consumed)
    second = cc.consume_all(ts=_TS, registry_module=reg, ledger_path=ledger, routes_path=routes,
                            trust_path=trust, proven_path=proven, consumed_path=consumed)
    assert second["n_newly_consumed"] == 0
    # routes.jsonl still has exactly one entry (no duplicate route written)
    lines = [l for l in routes.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(lines) == 1


def test_no_cards_validated_today_is_a_noop_not_a_crash(tmp_path: Path):
    """Honest state check: real registry has 0 VALIDATED cards; consume_all must no-op cleanly."""
    from scripts.platformkit.claims import card_registry as real_reg
    routes, trust, proven, consumed, ledger = (tmp_path / n for n in
        ("routes.jsonl", "trust.jsonl", "proven.jsonl", "consumed.jsonl", "ledger.jsonl"))
    summary = cc.consume_all(ts=_TS, registry_module=real_reg, ledger_path=ledger,
                             routes_path=routes, trust_path=trust, proven_path=proven,
                             consumed_path=consumed)
    assert summary["n_newly_consumed"] == 0
    assert not routes.is_file() and not trust.is_file() and not proven.is_file()
