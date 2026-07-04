"""Per-file test for the MLB GUMBO live-state extractor + patch machinery (LANE 2).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        tests/platformkit/ingame/test_ingame_gumbo_mlb.py -q
"""
from __future__ import annotations

import copy

from scripts.platformkit.ingame import ingame_gumbo_mlb as G
from scripts.platformkit.ingame import ingame_gumbo_mlb_patch as P


def _full_doc(inning=7, half="Bottom", outs=1, balls=1, strikes=1,
              on1=None, on2=None, on3=None, use_offense_only=False,
              away_runs=3, home_runs=2, batter_id=677587, pitcher_id=622554,
              pitcher_pitches=12, last_velo=86.9, game_pk=824417, ts="20260704_025709"):
    matchup = {}
    if not use_offense_only:
        matchup = {
            "batter": {"id": batter_id, "fullName": "Batter"},
            "pitcher": {"id": pitcher_id, "fullName": "Pitcher"},
            "postOnFirst": on1, "postOnSecond": on2, "postOnThird": on3,
        }
    else:
        matchup = {"batter": {"id": batter_id}, "pitcher": {"id": pitcher_id}}
    return {
        "gamePk": game_pk,
        "metaData": {"timeStamp": ts, "logicalEvents": []},
        "gameData": {},
        "liveData": {
            "linescore": {
                "currentInning": inning, "inningState": half,
                "outs": outs, "balls": balls, "strikes": strikes,
                "defense": {"first": {"id": 694378, "fullName": "Defender1B"}},
                "offense": {
                    "first": on1 if use_offense_only else None,
                    "second": on2 if use_offense_only else None,
                    "third": on3 if use_offense_only else None,
                },
                "teams": {"away": {"runs": away_runs}, "home": {"runs": home_runs}},
            },
            "plays": {"currentPlay": {
                "matchup": matchup,
                "runners": [],
                "playEvents": [
                    {"isPitch": True, "pitchData": {"startSpeed": 84.1}},
                    {"isPitch": False},
                    {"isPitch": True, "pitchData": {"startSpeed": last_velo}},
                ],
            }},
            "boxscore": {"teams": {"away": {"players": {
                "ID%s" % pitcher_id: {"stats": {"pitching": {"numberOfPitches": pitcher_pitches}}}
            }}, "home": {"players": {}}}},
        },
    }


def test_extract_basic_tick_runner_on_first():
    doc = _full_doc(on1={"id": 656555, "fullName": "Hoskins"}, on2=None, on3=None)
    tick = G.extract_state(doc)
    assert tick["game_pk"] == 824417
    assert tick["inning"] == 7 and tick["half"] == "Bottom" and tick["outs"] == 1
    assert tick["base_state"] == 1 and tick["base_label"] == "1--"
    assert tick["on_first"] is True and tick["on_second"] is False
    assert tick["balls"] == 1 and tick["strikes"] == 1
    assert tick["score_away"] == 3 and tick["score_home"] == 2
    assert tick["batter_id"] == 677587 and tick["pitcher_id"] == 622554
    assert tick["pitcher_pitches"] == 12
    assert tick["pitch_velo_last"] == 86.9


def test_fielding_position_trap_defense_first_never_sets_base_state():
    """defense.first is SET (a fielder) but matchup.postOnFirst/Second/Third are all None
    (bases empty) -- base_state MUST be 0, proving defense.* is never read for occupancy."""
    doc = _full_doc(on1=None, on2=None, on3=None)
    assert doc["liveData"]["linescore"]["defense"]["first"] is not None  # sanity: fielder present
    tick = G.extract_state(doc)
    assert tick["base_state"] == 0 and tick["base_label"] == "---"
    assert tick["on_first"] is False


def test_bases_loaded_via_matchup_postOn():
    doc = _full_doc(on1={"id": 1}, on2={"id": 2}, on3={"id": 3})
    tick = G.extract_state(doc)
    assert tick["base_state"] == 7 and tick["base_label"] == "123"


def test_fallback_to_offense_when_matchup_has_no_postOn_keys():
    doc = _full_doc(use_offense_only=True, on1={"id": 9}, on2=None, on3={"id": 11})
    tick = G.extract_state(doc)
    assert tick["base_state"] == 5 and tick["base_label"] == "1-3"


def test_base_state_from_runners_movement_fixture():
    runners = [
        {"movement": {"end": "2B", "isOut": False}},
        {"movement": {"end": "1B", "isOut": True}},   # out -> not occupying
        {"movement": {"end": None, "isOut": False}},
    ]
    bases = G.base_state_from_runners(runners)
    assert bases["base_state"] == 2 and bases["on_second"] is True
    assert bases["on_first"] is False


def test_extract_state_missing_inning_returns_empty():
    assert G.extract_state({}) == {}
    assert G.extract_state({"liveData": {"linescore": {}}}) == {}
    doc = _full_doc()
    del doc["liveData"]["linescore"]["currentInning"]
    assert G.extract_state(doc) == {}


def test_no_win_probability_field_ever_emitted():
    doc = _full_doc()
    tick = G.extract_state(doc)
    assert "win_prob" not in tick and "winProbability" not in tick


# ---- RFC6902 patch-apply / fullUpdate fallback (sidecar module) ----

def test_is_full_update_true_for_snapshot_and_logical_event():
    assert P.is_full_update({"liveData": {}, "gameData": {}}) is True
    assert P.is_full_update({"metaData": {"logicalEvents": ["fullUpdate"]}}) is True
    assert P.is_full_update({"metaData": {"logicalEvents": ["countChange"]}}) is False
    assert P.is_full_update({}) is False


def test_apply_patch_replace_and_add_and_remove():
    base = {"liveData": {"linescore": {"outs": 0}, "list": [1, 2]}}
    ops = [
        {"op": "replace", "path": "/liveData/linescore/outs", "value": 1},
        {"op": "add", "path": "/liveData/list/-", "value": 3},
        {"op": "remove", "path": "/liveData/list/0"},
    ]
    out = P.apply_patch(base, ops)
    assert out["liveData"]["linescore"]["outs"] == 1
    assert out["liveData"]["list"] == [2, 3]
    # base_state must be untouched (deep copy, not mutated in place)
    assert base["liveData"]["linescore"]["outs"] == 0
    assert base["liveData"]["list"] == [1, 2]


def test_apply_patch_raises_on_bad_op():
    import pytest
    with pytest.raises(ValueError):
        P.apply_patch({"a": 1}, [{"op": "bogus", "path": "/a", "value": 2}])


def test_apply_diffpatch_response_fullupdate_dict_used_directly():
    full = _full_doc()
    out = P.apply_diffpatch_response(None, full)
    assert out is full


def test_apply_diffpatch_response_real_patch_list_applies_against_last_full():
    prior = _full_doc(outs=0)
    ops_doc = {"metaData": {"logicalEvents": ["countChange"]},
               "diff": [{"op": "replace", "path": "/liveData/linescore/outs", "value": 2}]}
    out = P.apply_diffpatch_response(prior, [ops_doc])
    assert out["liveData"]["linescore"]["outs"] == 2
    assert prior["liveData"]["linescore"]["outs"] == 0   # prior untouched


def test_apply_diffpatch_response_fullupdate_logical_event_no_snapshot_forces_refetch():
    doc = {"metaData": {"logicalEvents": ["fullUpdate"]}}   # no liveData -> re-fetch needed
    assert P.apply_diffpatch_response(_full_doc(), [doc]) is None


def test_apply_diffpatch_response_patch_failure_returns_none():
    prior = _full_doc()
    # linescore.outs is an int (scalar) -- attempting to traverse "into" it must fail cleanly.
    bad_ops_doc = {"metaData": {"logicalEvents": []},
                   "diff": [{"op": "replace", "path": "/liveData/linescore/outs/99", "value": 1}]}
    assert P.apply_diffpatch_response(prior, [bad_ops_doc]) is None


def test_apply_diffpatch_response_no_prior_state_and_only_patches_returns_none():
    ops_doc = {"metaData": {"logicalEvents": []},
               "diff": [{"op": "replace", "path": "/x", "value": 1}]}
    assert P.apply_diffpatch_response(None, [ops_doc]) is None


def test_apply_diffpatch_response_empty_list_returns_last_full_unchanged():
    prior = _full_doc()
    assert P.apply_diffpatch_response(prior, []) is prior


# ---- as-of join property (base_out_state joins tick ts <= requested tick ts) ----

def test_asof_join_picks_latest_snapshot_not_exceeding_query_ts():
    """Simulates the WIRE SPEC as-of join: given several extracted ticks with ts strings
    (lexicographically sortable, matching GUMBO's YYYYMMDD_HHMMSS format), the as-of state
    for a query ts is the latest tick with ts <= query_ts, never a future one."""
    docs = [_full_doc(outs=0, ts="20260704_025700"),
            _full_doc(outs=1, ts="20260704_025720"),
            _full_doc(outs=2, ts="20260704_025740")]
    ticks = [G.extract_state(d) for d in docs]

    def asof(query_ts: str):
        candidates = [t for t in ticks if t["ts"] <= query_ts]
        return max(candidates, key=lambda t: t["ts"]) if candidates else None

    assert asof("20260704_025710")["outs"] == 0
    assert asof("20260704_025730")["outs"] == 1
    assert asof("20260704_025900")["outs"] == 2
    assert asof("20260704_025600") is None   # before any snapshot -> honestly no as-of state
