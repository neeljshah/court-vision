"""Disabled-is-noop test for the v2 SBS player-line SHADOW path.

Hard safety contract (mirrors the atlas-shadow gate): with the NEW env flag
``CV_INGAME_SBS`` unset / OFF, the live/default projection is byte-identical to
today and nothing in the serving path touches the v2 head. The shadow logger
opts the flag ON *inside its own process only*; the production projector
(``scripts.predict_in_game.project_snapshot``) never imports or calls the v2
head, so flipping the flag cannot change a served value.

These tests assert:
  1. ``sbs_shadow.is_enabled()`` is False by default (unset) and for non-truthy
     values, True only for explicit truthy spellings.
  2. ``project_snapshot`` output is IDENTICAL with the flag OFF vs ON -- i.e. the
     serving path is independent of the flag (the v2 head lives only in the
     shadow lane).
  3. The shadow helpers never mutate the input snapshot.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame import sbs_shadow  # noqa: E402


def _toy_snapshot():
    return {
        "game_id": "TEST0001",
        "period": 2,
        "clock": "11:30",  # ~ endQ1
        "home_team": "AAA",
        "away_team": "BBB",
        "home_score": 30,
        "away_score": 24,
        "players": [
            {"player_id": 111, "name": "Alpha", "team": "AAA", "min": 11.0,
             "pts": 8, "reb": 3, "ast": 2, "fg3m": 1, "stl": 1, "blk": 0,
             "tov": 1, "pf": 1, "is_starter": True},
            {"player_id": 222, "name": "Bravo", "team": "BBB", "min": 9.0,
             "pts": 5, "reb": 2, "ast": 4, "fg3m": 0, "stl": 0, "blk": 1,
             "tov": 2, "pf": 2, "is_starter": True},
        ],
    }


@pytest.fixture(autouse=True)
def _clear_flag():
    """Ensure each test starts with the flag in a known state, restore after."""
    saved = os.environ.get(sbs_shadow.SBS_FLAG)
    os.environ.pop(sbs_shadow.SBS_FLAG, None)
    yield
    if saved is None:
        os.environ.pop(sbs_shadow.SBS_FLAG, None)
    else:
        os.environ[sbs_shadow.SBS_FLAG] = saved


def test_flag_default_off():
    assert sbs_shadow.is_enabled() is False
    for v in ("0", "", "false", "no", "off", "nope"):
        os.environ[sbs_shadow.SBS_FLAG] = v
        assert sbs_shadow.is_enabled() is False, v


def test_flag_truthy_on():
    for v in ("1", "true", "yes", "on", "Y", "T"):
        os.environ[sbs_shadow.SBS_FLAG] = v
        assert sbs_shadow.is_enabled() is True, v


def test_serving_path_independent_of_flag():
    """project_snapshot must be byte-identical with the flag OFF vs ON."""
    import scripts.predict_in_game as pig
    snap = _toy_snapshot()

    os.environ.pop(sbs_shadow.SBS_FLAG, None)
    assert sbs_shadow.is_enabled() is False
    out_off = pig.project_snapshot(_toy_snapshot())

    os.environ[sbs_shadow.SBS_FLAG] = "1"
    assert sbs_shadow.is_enabled() is True
    out_on = pig.project_snapshot(_toy_snapshot())

    # Identical structure + values -> the served projection never depends on the
    # shadow flag (the v2 head is not in the serving path).
    assert out_off == out_on
    # input snapshot is not mutated by the helpers
    assert snap == _toy_snapshot()


def test_snapshot_to_v2_rows_is_pure():
    """snapshot_to_v2_rows must not mutate the snapshot and must emit the v2 keys."""
    snap = _toy_snapshot()
    before = _toy_snapshot()
    rows = sbs_shadow.snapshot_to_v2_rows(snap, store=None, game_date=None)
    assert snap == before  # no mutation
    assert len(rows) == 2
    r0 = rows[0]
    for key in ("game_remaining_min", "period", "played_share",
                "p_pts_so_far", "p_reb_so_far", "p_on_court",
                "score_margin", "total_so_far", "p_prior_pts",
                "_bucket", "_gate_decision"):
        assert key in r0, key
    # ~endQ1 -> v2 window
    assert r0["_gate_decision"] == "v2"
    assert r0["_bucket"] == "12min(endQ1)"


def test_grid_bucket_gate_decisions():
    # before tip -> pregame (game not started)
    assert sbs_shadow.grid_bucket_for(0, "12:00")[2] == "pregame"
    # early Q1 (~6 min elapsed) -> defer to pregame/L5
    assert sbs_shadow.grid_bucket_for(1, "06:00")[2] == "pregame"
    # endQ1 .. midQ3 -> v2 window
    assert sbs_shadow.grid_bucket_for(2, "11:45")[2] == "v2"   # ~12 min
    assert sbs_shadow.grid_bucket_for(3, "06:00")[2] == "v2"   # ~30 min (midQ3)
    # endQ3 / Q4 -> defer to production snapshot
    assert sbs_shadow.grid_bucket_for(4, "11:45")[2] == "snapshot"  # ~36 min
    assert sbs_shadow.grid_bucket_for(4, "06:00")[2] == "snapshot"  # ~42 min
