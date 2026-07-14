"""tests.platformkit.claims.test_condition_tagger -- tag() determinism + leak-freeness."""
from __future__ import annotations

import pytest

from scripts.platformkit.claims import card_registry as reg
from scripts.platformkit.claims import condition_tagger as ct

TS = "2026-07-14T00:00:00Z"


@pytest.fixture(autouse=True)
def _isolated_cards_path(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "CARDS_PATH", tmp_path / "cards.jsonl")
    yield


def _register(trigger, scope="ingame"):
    cond = {"scope": scope, "window": "w", "trigger": trigger, "entity": "game"}
    res = reg.register(claim="c", condition=cond, mechanism="m",
                       expected_sign="+", expected_magnitude="small",
                       source="test", ts=TS)
    assert res["ok"] is True, res
    return res["card_id"]


def test_determinism_same_state_same_tags():
    cid = _register("quarter == 1 and clock_seconds_elapsed >= 360")
    state = {"quarter": 1, "clock_seconds_elapsed": 400}
    assert ct.tag(state, "ingame") == ct.tag(state, "ingame")


def test_trigger_fires_on_matching_state():
    cid = _register("quarter == 1 and clock_seconds_elapsed >= 360")
    state = {"quarter": 1, "clock_seconds_elapsed": 400}
    assert ct.tag(state, "ingame")[cid] is True


def test_trigger_does_not_fire_on_non_matching_state():
    cid = _register("quarter == 1 and clock_seconds_elapsed >= 360")
    state = {"quarter": 2, "clock_seconds_elapsed": 400}
    assert ct.tag(state, "ingame")[cid] is False


def test_missing_field_never_fires_never_raises():
    cid = _register("quarter == 1 and clock_seconds_elapsed >= 360")
    state = {"quarter": 1}  # clock_seconds_elapsed absent
    assert ct.tag(state, "ingame")[cid] is False


def test_leak_free_truncating_future_fields_cannot_change_tags_from_false():
    cid = _register("quarter == 1 and clock_seconds_elapsed >= 360")
    full_state = {"quarter": 1, "clock_seconds_elapsed": 400, "future_only_field": 999}
    truncated = {"quarter": 1, "clock_seconds_elapsed": 400}
    # dropping an irrelevant future field never changes an existing tag
    assert ct.tag(full_state, "ingame") == ct.tag(truncated, "ingame")
    # dropping a field the trigger DOES need can only flip True->False, never invent a True
    truncated_needed = {"quarter": 1}
    assert ct.tag(truncated_needed, "ingame")[cid] is False


def test_scope_filters_pregame_vs_ingame():
    cid_in = _register("quarter == 1", scope="ingame")
    cid_pre = _register("expected_pace_pregame > 0", scope="pregame")
    tags_ingame = ct.tag({"quarter": 1}, "ingame")
    tags_pregame = ct.tag({"expected_pace_pregame": 1.0}, "pregame")
    assert cid_in in tags_ingame and cid_pre not in tags_ingame
    assert cid_pre in tags_pregame and cid_in not in tags_pregame
