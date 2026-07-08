"""Per-file test for tools_payton_clean pure quarantine/repair logic.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_tools_payton_clean.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.tools_payton_clean import (
    BAD_ID,
    PLACEHOLDER,
    flagged_box_ids,
    repair_box,
    scrub_actions,
)


def _box() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": "2024-25", "player_id": BAD_ID, "player_name": "Elfrid Payton"},
        {"season": "2024-25", "player_id": 1626157, "player_name": "KAT"},
        {"season": "2025-26", "player_id": 1626157, "player_name": "KAT"},
    ])


def test_flagged_ids_catches_bad_id_and_reports_zero_guard_on_shallow_parquet():
    box = _box()
    activity = {int(pid): {int(str(s)[:4])} for pid, s in zip(box["player_id"], box["season"])}
    ids, n_guard = flagged_box_ids(box, activity)
    assert ids == {BAD_ID}
    assert n_guard == 0  # 2-season parquet: guard has no prior history to fire


def test_repair_box_reassigns_only_that_season_and_id():
    out = repair_box(_box(), {BAD_ID})
    payton = out[out["player_name"] == "Elfrid Payton"]
    assert (payton["player_id"] == PLACEHOLDER).all() and PLACEHOLDER < 0
    # untouched: the real player rows keep their id in both seasons
    assert set(out[out["player_name"] == "KAT"]["player_id"]) == {1626157}
    # 203901 is gone entirely
    assert (out["player_id"] == BAD_ID).sum() == 0


def test_scrub_actions_replaces_personid_in_place():
    actions = [
        {"actionType": "other", "personId": BAD_ID},
        {"actionType": "substitution", "subType": "in", "personId": BAD_ID},
        {"actionType": "2pt", "personId": 1626157},
    ]
    n = scrub_actions(actions)
    assert n == 2
    assert [a["personId"] for a in actions] == [PLACEHOLDER, PLACEHOLDER, 1626157]
    assert all(a["personId"] != BAD_ID for a in actions)
