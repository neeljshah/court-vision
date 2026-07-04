"""Per-file tests for domains.basketball_wnba.cdn_states_extract.

Fixture scores mirror the REAL ground-truthed payload this wave (gameId
1022600149 CHI@LV, went to OT): end_q1 22-19, half 49-37, end_q3 70-64,
final 98-90. No network; tmp_path for all disk I/O.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_cdn_states_extract.py -q
"""
from __future__ import annotations

import json

import domains.basketball_wnba.cdn_backfill as backfill_mod
from domains.basketball_wnba.cdn_states_extract import (
    BONUS_FOUL_THRESHOLD, extract_and_append, extract_checkpoint_states,
    load_backfilled_pair, run_extract_all,
)

HOME_ID, AWAY_ID = 1611661319, 1611661329  # LVA, CHI (real team ids this wave)


def _period_action(period, clock, sh, sa):
    return {"actionType": "period", "subType": "end", "period": period, "clock": clock,
            "scoreHome": sh, "scoreAway": sa}


def _foul_action(period, team_id, sub="personal"):
    return {"actionType": "foul", "subType": sub, "period": period, "teamId": team_id,
            "clock": "PT05M00.00S"}


def _sub_action(period, team_id, person_id, sub, clock="PT05M00.00S"):
    return {"actionType": "substitution", "subType": sub, "period": period,
            "teamId": team_id, "personId": person_id, "clock": clock}


def _player(pid, starter):
    return {"personId": pid, "starter": "1" if starter else "0"}


def _box_game(home_starters=("h1", "h2", "h3", "h4", "h5"),
              away_starters=("a1", "a2", "a3", "a4", "a5")):
    return {
        "homeTeam": {"teamId": HOME_ID, "players": [_player(p, True) for p in home_starters]},
        "awayTeam": {"teamId": AWAY_ID, "players": [_player(p, True) for p in away_starters]},
    }


def _pbp_game(actions):
    return {"actions": actions}


# ---------------------------------------------------------------------------
# load_backfilled_pair -- resumable-file discovery, honest-None on gaps
# ---------------------------------------------------------------------------

def test_load_backfilled_pair_missing_dir_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_mod, "BACKFILL_DIR", tmp_path)
    assert load_backfilled_pair("nope") == None


def test_load_backfilled_pair_partial_files_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_mod, "BACKFILL_DIR", tmp_path)
    d = tmp_path / "g1"
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": {}}), encoding="utf-8")
    assert load_backfilled_pair("g1") is None  # playbyplay.json absent


def test_load_backfilled_pair_happy_path(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_mod, "BACKFILL_DIR", tmp_path)
    d = tmp_path / "g1"
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": {"a": 1}}), encoding="utf-8")
    (d / "playbyplay.json").write_text(json.dumps({"game": {"b": 2}}), encoding="utf-8")
    pair = load_backfilled_pair("g1")
    assert pair["boxscore"] == {"a": 1}
    assert pair["playbyplay"] == {"b": 2}


# ---------------------------------------------------------------------------
# extract_checkpoint_states -- ground-truthed real scores
# ---------------------------------------------------------------------------

def test_checkpoint_scores_match_ground_truth():
    actions = [
        _period_action(1, "PT00M00.00S", "22", "19"),
        _period_action(2, "PT00M00.00S", "49", "37"),
        _period_action(3, "PT00M00.00S", "70", "64"),
    ]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    by_cp = {r["checkpoint"]: r for r in rows}
    assert by_cp["end_q1"]["score_home"] == 22.0 and by_cp["end_q1"]["score_away"] == 19.0
    assert by_cp["half"]["score_home"] == 49.0 and by_cp["half"]["score_away"] == 37.0
    assert by_cp["end_q3"]["score_home"] == 70.0 and by_cp["end_q3"]["score_away"] == 64.0
    for r in rows:
        assert r["provenance"] == "cdn_backfill"
        assert r["foul_trouble_flags"] is None  # honest gap, never fabricated


def test_checkpoint_skipped_when_period_never_reached():
    # game only has period-1 data (e.g. truncated/malformed feed) -- half and
    # end_q3 must be skipped, not fabricated as 0-0.
    actions = [_period_action(1, "PT00M00.00S", "10", "8")]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    assert [r["checkpoint"] for r in rows] == ["end_q1"]


# ---------------------------------------------------------------------------
# team-foul / bonus proxy
# ---------------------------------------------------------------------------

def test_bonus_proxy_triggers_at_threshold():
    actions = [_period_action(1, "PT00M00.00S", "10", "8")]
    actions += [_foul_action(1, HOME_ID) for _ in range(BONUS_FOUL_THRESHOLD)]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    row = rows[0]
    assert row["team_fouls_home"] == BONUS_FOUL_THRESHOLD
    assert row["in_bonus_home"] is True
    assert row["in_bonus_away"] is False


def test_bonus_proxy_not_triggered_below_threshold():
    actions = [_period_action(1, "PT00M00.00S", "10", "8")]
    actions += [_foul_action(1, HOME_ID) for _ in range(BONUS_FOUL_THRESHOLD - 1)]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    assert rows[0]["in_bonus_home"] is False


def test_fouls_reset_each_period():
    actions = [
        _foul_action(1, HOME_ID), _foul_action(1, HOME_ID), _foul_action(1, HOME_ID),
        _period_action(1, "PT00M00.00S", "10", "8"),
        _period_action(2, "PT00M00.00S", "20", "18"),
    ]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    by_cp = {r["checkpoint"]: r for r in rows}
    assert by_cp["end_q1"]["team_fouls_home"] == 3
    assert by_cp["half"]["team_fouls_home"] == 0  # period-2 has zero foul actions


# ---------------------------------------------------------------------------
# lineup reconstruction (starters + substitution replay)
# ---------------------------------------------------------------------------

def test_lineup_is_starters_when_no_subs():
    actions = [_period_action(1, "PT00M00.00S", "10", "8")]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    assert rows[0]["lineup_home"] == ["h1", "h2", "h3", "h4", "h5"]


def test_lineup_replays_substitution_before_checkpoint():
    actions = [
        _sub_action(1, HOME_ID, "h1", "out"),
        _sub_action(1, HOME_ID, "h6", "in"),
        _period_action(1, "PT00M00.00S", "10", "8"),
    ]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    assert rows[0]["lineup_home"] == ["h2", "h3", "h4", "h5", "h6"]


def test_lineup_honest_none_when_not_exactly_five():
    actions = [
        _sub_action(1, HOME_ID, "h6", "in"),  # sub-in with no matching sub-out -> 6 oncourt
        _period_action(1, "PT00M00.00S", "10", "8"),
    ]
    rows = extract_checkpoint_states("g1", _box_game(), _pbp_game(actions))
    assert rows[0]["lineup_home"] is None


def test_lineup_not_exactly_five_starters_is_honest_none():
    box = _box_game(home_starters=("h1", "h2", "h3", "h4"))  # only 4 starters flagged
    actions = [_period_action(1, "PT00M00.00S", "10", "8")]
    rows = extract_checkpoint_states("g1", box, _pbp_game(actions))
    assert rows[0]["lineup_home"] is None


# ---------------------------------------------------------------------------
# extract_and_append / run_extract_all -- disk round-trip, resumable batch
# ---------------------------------------------------------------------------

def test_extract_and_append_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_mod, "BACKFILL_DIR", tmp_path)
    d = tmp_path / "g1"
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": _box_game()}), encoding="utf-8")
    actions = [_period_action(1, "PT00M00.00S", "10", "8")]
    (d / "playbyplay.json").write_text(json.dumps({"game": _pbp_game(actions)}), encoding="utf-8")

    out = tmp_path / "states.jsonl"
    n = extract_and_append("g1", out_path=out)
    assert n == 1
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["game_id"] == "g1"


def test_extract_and_append_missing_game_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_mod, "BACKFILL_DIR", tmp_path)
    out = tmp_path / "states.jsonl"
    assert extract_and_append("nope", out_path=out) == 0
    assert not out.exists()


def test_run_extract_all_walks_every_backfilled_game(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_mod, "BACKFILL_DIR", tmp_path)
    for gid in ("g1", "g2"):
        d = tmp_path / gid
        d.mkdir()
        (d / "boxscore.json").write_text(json.dumps({"game": _box_game()}), encoding="utf-8")
        actions = [_period_action(1, "PT00M00.00S", "10", "8")]
        (d / "playbyplay.json").write_text(json.dumps({"game": _pbp_game(actions)}), encoding="utf-8")

    out = tmp_path / "states.jsonl"
    summary = run_extract_all(out_path=out)
    assert summary == {"n_games": 2, "n_rows": 2}
