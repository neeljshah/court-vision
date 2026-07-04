"""Per-file tests for domains.basketball_wnba.atlas_extract_pbp.

Fixture actions mirror the REAL playbyplay schema (verified this wave against
gameId 1012600001): actionType in {2pt,3pt,freethrow}, area/shotDistance/x/y
on shot actions, scoreHome/scoreAway cumulative on every action.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_pbp.py -q
"""
from __future__ import annotations

import json

import domains.basketball_wnba.atlas_extract_common as common
from domains.basketball_wnba.atlas_extract_pbp import (
    CLUTCH_CLOCK_SEC_MAX, CLUTCH_MARGIN_MAX, CLUTCH_PERIOD,
    build_clutch_margin_frame, build_player_clutch_margin_atlas,
    build_player_shot_zones_atlas, build_shot_zone_frame, run_extract_pbp_atlas,
)

HOME_ID, AWAY_ID = 1611661313, 1611661325


def _shot_action(pid, name, team_id, area, made, cum_points_total, score_home, score_away,
                  action_type="2pt", period=1, clock="PT05M00.00S", shot_distance=10.0):
    """*cum_points_total* mirrors the REAL raw CDN schema: pointsTotal is the
    SCORING PLAYER'S CUMULATIVE in-game point total (verified against the real
    corpus, game 1012600001: player Clark's makes show pointsTotal 2, 5, 6, 7
    -- monotonic running sum), NOT this action's own points. The extraction
    code must derive per-action points from actionType (_ACTION_POINTS), never
    from this field -- fixtures deliberately set a cumulative (not per-action)
    value here so a regression back to reading pointsTotal directly would fail
    these tests."""
    return {
        "actionType": action_type, "personId": pid, "playerName": name,
        "teamId": team_id, "area": area, "shotDistance": shot_distance,
        "shotResult": "Made" if made else "Missed",
        "pointsTotal": cum_points_total if made else 0,
        "scoreHome": str(score_home), "scoreAway": str(score_away),
        "period": period, "clock": clock, "x": 25.0, "y": 40.0,
    }


def _write_game(tmp_path, gid, box_game, actions):
    d = tmp_path / gid
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": box_game}), encoding="utf-8")
    (d / "playbyplay.json").write_text(json.dumps({"game": {"actions": actions}}), encoding="utf-8")


def _box_game():
    return {"homeTeam": {"teamId": HOME_ID, "teamTricode": "NYL"},
            "awayTeam": {"teamId": AWAY_ID, "teamTricode": "IND"}}


# ---------------------------------------------------------------------------
# build_shot_zone_frame / build_player_shot_zones_atlas
# ---------------------------------------------------------------------------

def test_shot_zone_frame_only_2pt_3pt(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    actions = [
        _shot_action(1, "A", HOME_ID, "Mid-Range", True, 2, 2, 0),
        _shot_action(1, "A", HOME_ID, "Mid-Range", False, 0, 2, 0),
        {"actionType": "rebound", "personId": 1},  # must be excluded
    ]
    _write_game(tmp_path, "g1", _box_game(), actions)
    shots = build_shot_zone_frame()
    assert len(shots) == 2


def test_shot_zone_atlas_computes_zone_fg_pct(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    actions = [
        _shot_action(1, "A", HOME_ID, "Mid-Range", True, 2, 2, 0),
        _shot_action(1, "A", HOME_ID, "Mid-Range", False, 0, 2, 0),
        _shot_action(1, "A", HOME_ID, "Restricted Area", True, 2, 4, 0),
    ]
    _write_game(tmp_path, "g1", _box_game(), actions)
    shots = build_shot_zone_frame()
    atlas = build_player_shot_zones_atlas(shots)
    row = atlas[atlas["player_id"] == "1"].iloc[0]
    assert row["n_shots_total"] == 3
    assert row["fg_pct_overall"] == round(2 / 3, 4)
    assert row["zone_mid_range_fg_pct"] == 0.5
    assert row["zone_restricted_area_fg_pct"] == 1.0


def test_shot_zone_atlas_empty_input():
    import pandas as pd
    assert build_player_shot_zones_atlas(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_clutch_margin_frame -- pre-shot margin, clutch window
# ---------------------------------------------------------------------------

def test_clutch_flag_true_in_window(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    # Q4, 2 min left, home makes a shot to go up 2-0 (pre-shot margin=0, in
    # window). cum_points_total=40 is a DISTRACTOR (the player's running game
    # total, e.g. their 20th made 2pt of the night) deliberately far from the
    # true per-action value (2) -- if the code ever reads pointsTotal again
    # instead of deriving from actionType, pre_shot_margin_abs would come out
    # as |2 - 40| = 38 instead of 0 and this assertion would fail.
    actions = [_shot_action(1, "A", HOME_ID, "Mid-Range", True, 40, 2, 0,
                             period=CLUTCH_PERIOD, clock="PT02M00.00S")]
    _write_game(tmp_path, "g1", _box_game(), actions)
    cm = build_clutch_margin_frame()
    row = cm.iloc[0]
    assert bool(row["is_clutch"]) is True
    assert row["pre_shot_margin_abs"] == 0
    assert row["points"] == 2  # derived from actionType, not the distractor pointsTotal


def test_clutch_flag_false_outside_period(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    # Q1 shot -- never clutch regardless of clock/margin
    actions = [_shot_action(1, "A", HOME_ID, "Mid-Range", True, 40, 2, 0,
                             period=1, clock="PT02M00.00S")]
    _write_game(tmp_path, "g1", _box_game(), actions)
    cm = build_clutch_margin_frame()
    assert bool(cm.iloc[0]["is_clutch"]) is False


def test_clutch_flag_false_when_margin_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    # Q4, 2 min left, home makes shot but was ALREADY up by 20 before it
    # (blowout). cum_points_total=40 is again a distractor far from the true
    # per-action value (2): if pointsTotal were read directly, pre_shot_margin
    # would corrupt to |22-40|=18 (still <=5 false, but for the wrong reason);
    # asserting the exact value (20) pins the correct actionType-derived math.
    actions = [_shot_action(1, "A", HOME_ID, "Mid-Range", True, 40, 22, 0,
                             period=CLUTCH_PERIOD, clock="PT02M00.00S")]
    _write_game(tmp_path, "g1", _box_game(), actions)
    cm = build_clutch_margin_frame()
    assert cm.iloc[0]["pre_shot_margin_abs"] == 20
    assert bool(cm.iloc[0]["is_clutch"]) is False


def test_clutch_margin_away_team_shot_uses_away_side(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    # away team scores: post margin = home(0) - away(2) = -2; pre-shot margin
    # should back out the 2 pts (derived from actionType, not the distractor
    # cum_points_total=40) from away's side -> pre = 0 - 0 = 0
    actions = [_shot_action(9, "AwayScorer", AWAY_ID, "Mid-Range", True, 40, 0, 2,
                             period=CLUTCH_PERIOD, clock="PT01M00.00S")]
    _write_game(tmp_path, "g1", _box_game(), actions)
    cm = build_clutch_margin_frame()
    assert cm.iloc[0]["pre_shot_margin_abs"] == 0
    assert bool(cm.iloc[0]["is_clutch"]) is True


def test_missed_shots_excluded_from_clutch_margin(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    actions = [_shot_action(1, "A", HOME_ID, "Mid-Range", False, 0, 0, 0)]
    _write_game(tmp_path, "g1", _box_game(), actions)
    cm = build_clutch_margin_frame()
    assert cm.empty


# ---------------------------------------------------------------------------
# build_player_clutch_margin_atlas
# ---------------------------------------------------------------------------

def test_clutch_margin_atlas_share_computation(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    # cum_points_total values (2, then 5) mirror the REAL corpus's monotonic
    # running-total schema (verified game 1012600001, player Clark: 2, 5, 6, 7)
    # -- true per-action points are 2 (2pt) then 3 (3pt), summing to 5. A code
    # regression to reading pointsTotal directly would instead sum 2+5=7.
    actions = [
        _shot_action(1, "A", HOME_ID, "Mid-Range", True, 2, 2, 0, period=1, clock="PT05M00.00S"),
        _shot_action(1, "A", HOME_ID, "Mid-Range", True, 5, 5, 0,
                     action_type="3pt", period=CLUTCH_PERIOD, clock="PT01M00.00S"),
    ]
    _write_game(tmp_path, "g1", _box_game(), actions)
    cm = build_clutch_margin_frame()
    atlas = build_player_clutch_margin_atlas(cm)
    row = atlas[atlas["player_id"] == "1"].iloc[0]
    assert row["total_points_from_scoring_actions"] == 5
    assert row["clutch_points"] == 3
    assert row["clutch_points_share"] == 0.6


def test_clutch_margin_atlas_empty_input():
    import pandas as pd
    assert build_player_clutch_margin_atlas(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# run_extract_pbp_atlas -- disk round-trip
# ---------------------------------------------------------------------------

def test_run_extract_pbp_atlas_writes_parquets(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setattr(common, "ATLAS_OUT_DIR", out_dir)
    actions = [_shot_action(1, "A", HOME_ID, "Mid-Range", True, 2, 2, 0)]
    _write_game(tmp_path, "g1", _box_game(), actions)

    summary = run_extract_pbp_atlas()
    assert summary["player_shot_zones"] == 1
    assert summary["player_clutch_margin"] == 1
    assert (out_dir / "atlas_wnba_player_shot_zones.parquet").exists()
    assert (out_dir / "atlas_wnba_player_clutch_margin.parquet").exists()
