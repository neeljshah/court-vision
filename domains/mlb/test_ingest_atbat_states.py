"""Per-file test for domains.mlb.ingest_atbat_states + domains.mlb.re24_table.

No network -- a synthetic ESPN-summary plays[] payload mimicking the PROBED real schema
(start-batterpitcher plays carry as-of outs/runners/scores; end-inning sentinels exist).

Covers the INCREMENT-2 gate contract:
  * tick count == number of at-bats (one start-batterpitcher per at-bat),
  * runners bitmask matches onFirst/onSecond/onThird,
  * state_diff at at-bat k uses only scores AS-OF k (leak-free step-fn),
  * base_run_value is a PURE STATIC table lookup (no test-season fit) and the RE24
    estimation seasons are DISJOINT from the gate corpora (2022/2023) -- MUST-FIX #8,
  * count_balls/count_strikes are present but CONSTANT 0 at the at-bat grid (honest
    reclassification, MUST-FIX #6),
  * frozen base schema columns present.
"""
from __future__ import annotations

from domains.mlb import re24_table
from domains.mlb.ingest_atbat_states import (
    fetch_game_atbat_states,
    parse_atbat_states,
    _runners_bitmask,
)
from domains.mlb.re24_table import (
    RE24,
    RE24_ESTIMATION_SEASONS,
    base_run_value,
    leverage_bucket,
)


# --------------------------------------------------------------------------- payload
def _ab(atbat_id, ptype, pnum, h, a, outs, on1=False, on2=False, on3=False):
    """One start-batterpitcher play = the as-of state facing a batter."""
    p = {
        "atBatId": atbat_id,
        "type": {"type": "start-batterpitcher"},
        "period": {"type": ptype, "number": pnum},
        "homeScore": h, "awayScore": a, "outs": outs,
        "pitchCount": {"balls": 0, "strikes": 0},
    }
    if on1:
        p["onFirst"] = {"id": "1"}
    if on2:
        p["onSecond"] = {"id": "2"}
    if on3:
        p["onThird"] = {"id": "3"}
    return p


def _end_inning(pnum, ptype, h, a):
    return {"atBatId": f"ei{pnum}{ptype}", "type": {"type": "end-inning"},
            "period": {"type": ptype, "number": pnum},
            "homeScore": h, "awayScore": a, "outs": 0}


def _payload():
    """A tiny 2-inning game. Away bats top (Top), home bats bottom (Bottom).
    Score climbs: home scores 1 in bottom of the 1st (between AB ticks)."""
    plays = [
        # Top 1: 3 batters, bases empty, score 0-0; outs 0,1,2 facing each batter
        _ab("t101", "Top", 1, 0, 0, 0),
        _ab("t102", "Top", 1, 0, 0, 1),
        _ab("t103", "Top", 1, 0, 0, 2),
        _end_inning(1, "Mid", 0, 0),
        # Bottom 1: batter 1 (0 outs), batter 2 reaches (runner on 1B, 0 outs),
        # batter 3 faces runner-on-1B 1 out, THEN home leads 1-0 for batter 4
        _ab("b101", "Bottom", 1, 0, 0, 0),
        _ab("b102", "Bottom", 1, 0, 0, 0, on1=True),
        _ab("b103", "Bottom", 1, 0, 0, 1, on1=True, on2=True),
        _ab("b104", "Bottom", 1, 1, 0, 2),     # home now leads 1-0 (as-of)
        _end_inning(1, "End", 1, 0),
        # Top 2: away ties it 1-1 by the 2nd batter
        _ab("t201", "Top", 2, 1, 0, 0),
        _ab("t202", "Top", 2, 1, 1, 1),        # away tied it (as-of 1-1)
        _end_inning(2, "Mid", 1, 1),
    ]
    return {"plays": plays}


# --------------------------------------------------------------------------- tests
def test_tick_count_equals_atbats():
    rows = parse_atbat_states(_payload())
    # 3 (Top1) + 4 (Bottom1) + 2 (Top2) = 9 at-bats; end-inning sentinels excluded
    assert len(rows) == 9
    assert [r["asof_idx"] for r in rows] == list(range(9))


def test_runners_bitmask_matches_on_base():
    rows = parse_atbat_states(_payload())
    # b102 has onFirst -> bit2 set -> 4 ; b103 has 1B+2B -> 4|2 = 6
    assert rows[4]["runners"] == 4          # b102
    assert rows[5]["runners"] == 6          # b103
    assert rows[0]["runners"] == 0          # bases empty
    # unit: bitmask helper
    assert _runners_bitmask({"onFirst": {"id": "x"}}) == 4
    assert _runners_bitmask({"onSecond": 1, "onThird": 1}) == 3
    assert _runners_bitmask({}) == 0


def test_state_diff_is_asof_leakfree():
    rows = parse_atbat_states(_payload())
    # state_diff = homeScore - awayScore AS-OF the start of the at-bat (leak-free).
    sds = [r["state_diff"] for r in rows]
    # Top1 (idx0-2): 0-0 -> 0 ; Bottom1 first 3 (idx3-5): still 0-0 -> 0 ;
    # b104 (idx6): home led 1-0 -> +1 ; Top2 t201 (idx7): +1 ; t202 (idx8): 1-1 -> 0
    assert sds == [0, 0, 0, 0, 0, 0, 1, 1, 0]
    # monotone-ish: the +1 only appears AT/AFTER the run scored, never before (no leak)
    assert all(s == 0 for s in sds[:6])
    assert sds[6] == 1


def test_outs_are_asof_facing_batter():
    rows = parse_atbat_states(_payload())
    # Top1 outs 0,1,2 facing the three batters
    assert [rows[i]["outs"] for i in range(3)] == [0, 1, 2]
    # all start-of-AB outs are in {0,1,2}
    assert all(0 <= r["outs"] <= 2 for r in rows)


def test_count_constant_zero_at_atbat_grid():
    # MUST-FIX #6 honest reclassification: start-of-AB count is always 0-0; a varying
    # count is the deferred pitch tier. Present (zero-network) but constant here.
    rows = parse_atbat_states(_payload())
    assert all(r["count_balls"] == 0 and r["count_strikes"] == 0 for r in rows)


def test_base_run_value_is_static_table_lookup():
    rows = parse_atbat_states(_payload())
    # b102 (runners=4=1B, outs=0) -> RE24[(4,0)] exactly (pure lookup, no fit)
    assert rows[4]["base_run_value"] == RE24[(4, 0)]
    assert rows[4]["base_run_value"] == base_run_value(4, 0)
    # b103 (runners=6=1B+2B, outs=1) -> RE24[(6,1)]
    assert rows[5]["base_run_value"] == RE24[(6, 1)]
    # bases empty 0 outs
    assert rows[0]["base_run_value"] == RE24[(0, 0)]


def test_re24_table_is_pinned_static_constant():
    # MUST-FIX #8: 24 base-out states, all floats, NO data-derivation at import/call.
    assert len(RE24) == 24
    assert all(isinstance(v, float) for v in RE24.values())
    # exactly 8 base states x 3 out states
    base_states = {k[0] for k in RE24}
    out_states = {k[1] for k in RE24}
    assert base_states == set(range(8))
    assert out_states == {0, 1, 2}
    # monotone in outs: more outs -> fewer expected runs for the same base state
    for b in range(8):
        assert RE24[(b, 0)] > RE24[(b, 1)] > RE24[(b, 2)]
    # out-of-range -> neutral 0.0 (never fabricated)
    assert base_run_value(0, 3) == 0.0
    assert base_run_value(0, -1) == 0.0


def test_re24_estimation_seasons_disjoint_from_gate_corpora():
    # MUST-FIX #8 hard rail: the RE24 table's estimation seasons must NOT overlap the
    # in-game gate corpora (2022, 2023) -> no future leak from the static table.
    gate_seasons = {2022, 2023}
    assert set(RE24_ESTIMATION_SEASONS).isdisjoint(gate_seasons)
    assert max(RE24_ESTIMATION_SEASONS) < 2022


def test_re24_no_runtime_data_derivation():
    # The table module imports no pandas/numpy and reads no file -- a pure dict literal.
    src = re24_table.__file__
    with open(src, "r", encoding="ascii") as f:
        text = f.read()
    assert "import pandas" not in text and "import numpy" not in text
    assert "read_parquet" not in text and "read_csv" not in text
    assert "open(" not in text  # no file read inside the table module itself


def test_leverage_bucket_static_rule():
    # blowout -> low regardless of base-out
    assert leverage_bucket(9, 6.0, 7, 0) == "low"
    # late + close + runners on -> high
    assert leverage_bucket(8, 1.0, 4, 1) == "high"
    # late + close + bases empty -> mid
    assert leverage_bucket(8, 1.0, 0, 1) == "mid"
    # RISP early, close, <2 outs -> mid
    assert leverage_bucket(3, 2.0, 2, 1) == "mid"
    # quiet early state -> low
    assert leverage_bucket(2, 0.0, 0, 0) == "low"


def _decided_payload():
    """The base 1-1 payload plus a home run so home wins 2-1 (no tie -> not dropped)."""
    p = _payload()
    p["plays"].append({"atBatId": "b201", "type": {"type": "start-batterpitcher"},
                       "period": {"type": "Bottom", "number": 2},
                       "homeScore": 1, "awayScore": 1, "outs": 0,
                       "pitchCount": {"balls": 0, "strikes": 0}})
    p["plays"].append(_end_inning(2, "End", 2, 1))
    return p


def test_fetch_game_atbat_states_frozen_schema():
    meta = {"game_id": "G1", "p0": 0.55, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    rows = fetch_game_atbat_states("eid", meta, lambda u: _decided_payload())
    assert len(rows) == 10   # 9 original at-bats + the appended home-run at-bat
    frozen = {"sport", "game_id", "asof_idx", "state_diff", "frac_elapsed", "p0", "outcome"}
    detail = {"count_balls", "count_strikes", "runners", "outs",
              "base_run_value", "leverage_bucket"}
    extra = {"home_team", "away_team", "date", "season", "half_inning_label"}
    assert frozen.issubset(rows[0].keys())
    assert detail.issubset(rows[0].keys())
    assert extra.issubset(rows[0].keys())


def test_tie_game_is_dropped_not_fabricated():
    meta = {"game_id": "G1", "p0": 0.5, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    # our base payload ends 1-1 -> tie -> dropped honestly
    rows = fetch_game_atbat_states("eid", meta, lambda u: _payload())
    assert rows == []


def test_outcome_assigned_when_decided():
    meta = {"game_id": "G2", "p0": 0.5, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    rows = fetch_game_atbat_states("eid", meta, lambda u: _decided_payload())
    assert rows and all(r["outcome"] == 1 for r in rows)   # home won 2-1
    assert rows[0]["sport"] == "mlb" and rows[0]["game_id"] == "G2"
