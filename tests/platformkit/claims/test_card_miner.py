"""tests.platformkit.claims.test_card_miner -- seeded card content + registration."""
from __future__ import annotations

import pytest

from scripts.platformkit.claims import card_miner
from scripts.platformkit.claims import card_registry as reg

TS = "2026-07-14T00:00:00Z"


@pytest.fixture(autouse=True)
def _isolated_cards_path(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "CARDS_PATH", tmp_path / "cards.jsonl")
    yield


def test_source1_reported_empty():
    assert "EMPTY" in card_miner.SOURCE1_STATUS


def test_ten_seed_cards_no_more():
    cards = card_miner.all_seed_cards()
    assert len(cards) == 10


def test_every_card_has_a_written_mechanism():
    for card in card_miner.all_seed_cards():
        assert card["mechanism"].strip()
        assert len(card["mechanism"]) > 20  # not a stub


def test_card_one_is_the_preregistered_ingame_experiment():
    card = card_miner.all_seed_cards()[0]
    assert card["condition"]["scope"] == "ingame"
    assert card["condition"]["window"] == "midQ1_to_endQ1"
    assert "matchup" in card["mechanism"].lower()


def test_every_trigger_passes_the_registry_allowlist():
    for card in card_miner.all_seed_cards():
        ok, reason = reg.validate_trigger(card["condition"]["trigger"])
        assert ok, f"{card['claim'][:40]!r} trigger rejected: {reason}"


def test_seed_registers_all_ten_open_no_queue():
    results = card_miner.seed(reg, TS)
    assert len(results) == 10
    assert all(r["ok"] for r in results)
    assert len(reg.get_open()) == 10
    assert all(r["status"] == "OPEN" for r in results)
