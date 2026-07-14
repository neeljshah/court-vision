"""tests.platformkit.claims.test_card_registry -- pre-registration lock rules."""
from __future__ import annotations

import pytest

from scripts.platformkit.claims import card_registry as reg

TS = "2026-07-14T00:00:00Z"


@pytest.fixture(autouse=True)
def _isolated_cards_path(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "CARDS_PATH", tmp_path / "cards.jsonl")
    yield


def _valid_condition(trigger="quarter == 1 and clock_seconds_elapsed >= 360"):
    return {"scope": "ingame", "window": "midQ1_to_endQ1", "trigger": trigger, "entity": "game"}


def _register(i=0, trigger=None):
    cond = _valid_condition(trigger) if trigger else _valid_condition()
    return reg.register(
        claim=f"claim {i}",
        condition=cond,
        mechanism="because reasons",
        expected_sign="+",
        expected_magnitude="small",
        source="test",
        ts=TS,
    )


def test_register_valid_card_is_open():
    res = _register()
    assert res["ok"] is True
    assert res["status"] == "OPEN"
    open_cards = reg.get_open()
    assert len(open_cards) == 1
    assert open_cards[0]["mechanism"] == "because reasons"


def test_register_rejects_missing_mechanism():
    res = reg.register(
        claim="x", condition=_valid_condition(), mechanism="  ",
        expected_sign="+", expected_magnitude="small", source="t", ts=TS,
    )
    assert res["ok"] is False
    assert "mechanism" in res["reason"]
    assert reg.get_open() == []


def test_register_rejects_forbidden_trigger_field():
    res = _register(trigger="season_final_ppg > 100")
    assert res["ok"] is False
    assert "season_final_ppg" in res["reason"]
    assert reg.get_open() == []


def test_register_rejects_postgame_leak_field():
    res = _register(trigger="box_score_final_margin > 10")
    assert res["ok"] is False
    assert reg.get_all_latest() == {}


def test_ten_cap_new_card_queues():
    for i in range(10):
        res = _register(i)
        assert res["status"] == "OPEN"
    eleventh = _register(10)
    assert eleventh["ok"] is True
    assert eleventh["status"] == "QUEUED"
    assert len(reg.get_open()) == 10


def test_promote_queued_fills_freed_slot():
    ids = [_register(i)["card_id"] for i in range(10)]
    queued = _register(10)
    assert queued["status"] == "QUEUED"
    reg.close_card(ids[0], "REJECTED", "manual test close", TS)
    assert len(reg.get_open()) == 9
    promoted = reg.promote_queued(TS)
    assert promoted == [queued["card_id"]]
    assert len(reg.get_open()) == 10


def test_can_edit_false_after_peek():
    card_id = _register()["card_id"]
    assert reg.can_edit(card_id) is True
    reg.mark_peeked(card_id, TS)
    assert reg.can_edit(card_id) is False
    assert reg.get_all_latest()[card_id]["outcomes_peeked"] is True


def test_edit_after_peek_auto_rejects_old_card_not_mutate():
    card_id = _register()["card_id"]
    reg.mark_peeked(card_id, TS)
    res = reg.update_card(card_id, {"claim": "sneaky post-hoc rewrite"}, TS)
    assert res["ok"] is False
    assert res["reason"] == "post-hoc modification"
    latest = reg.get_all_latest()[card_id]
    assert latest["status"] == "REJECTED"
    assert latest["reason"] == "post-hoc modification"
    assert latest["claim"] == "claim 0"  # original claim untouched, not overwritten


def test_close_card_allowed_even_after_peek():
    card_id = _register()["card_id"]
    reg.mark_peeked(card_id, TS)
    res = reg.close_card(card_id, "GRADED_TRUE", "graded outcome", TS)
    assert res["ok"] is True
    assert reg.get_all_latest()[card_id]["status"] == "GRADED_TRUE"


def test_validate_trigger_allows_only_allowlisted_fields():
    ok, _ = reg.validate_trigger("scheme_tag_overlap")
    assert ok is True
    ok, reason = reg.validate_trigger("some_unknown_field > 1")
    assert ok is False
    assert "some_unknown_field" in reason
