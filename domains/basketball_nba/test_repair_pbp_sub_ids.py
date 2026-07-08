"""Per-file test for repair_pbp_sub_ids -- pure repair_actions logic, no disk.

Run: python -m pytest domains/basketball_nba/test_repair_pbp_sub_ids.py -q
"""
from __future__ import annotations

from domains.basketball_nba.repair_pbp_sub_ids import repair_actions, synthetic_id


def _sub(sub_type: str, desc: str, pid=None) -> dict:
    return {"actionType": "substitution", "subType": sub_type, "personId": pid,
            "description": desc}


def test_fills_in_and_out_from_description():
    desc = "Alpha Man enters the game for Beta Guy"
    actions = [_sub("out", desc), _sub("in", desc)]
    n = repair_actions(actions, player_map={})
    assert n == 2
    assert actions[0]["personId"] == synthetic_id("Beta Guy")   # out = the replaced player
    assert actions[1]["personId"] == synthetic_id("Alpha Man")  # in = the entering player
    assert actions[0]["personId"] < 0 and actions[1]["personId"] < 0
    assert actions[0]["personId"] != actions[1]["personId"]


def test_prefers_real_id_when_map_knows_the_name():
    desc = "Alpha Man enters the game for Beta Guy"
    actions = [_sub("in", desc)]
    repair_actions(actions, player_map={"alpha man": 12345})
    assert actions[0]["personId"] == 12345


def test_leaves_mapped_and_non_sub_actions_alone():
    actions = [_sub("in", "Alpha Man enters the game for Beta Guy", pid=99),
               {"actionType": "2pt", "personId": None, "description": "missed shot"}]
    n = repair_actions(actions, player_map={})
    assert n == 0
    assert actions[0]["personId"] == 99
    assert actions[1]["personId"] is None


def test_synthetic_id_is_deterministic():
    assert synthetic_id("Some Name") == synthetic_id("Some Name")


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
