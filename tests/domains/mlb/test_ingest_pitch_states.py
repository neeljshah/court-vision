"""Per-file test for domains.mlb.ingest_pitch_states (PER-PITCH as-of state layer).

No network -- a synthetic ESPN-summary plays[] payload mimicking the PROBED real schema
(pitch plays carry pitchCount {balls,strikes} as the PRE-pitch count, resultCount as the
post-pitch count, pitchType.abbreviation, pitchVelocity, pitchCoordinate, atBatPitchNumber;
start-batterpitcher / end-inning sentinels exist and must NOT become pitch ticks).

Covers the INCREMENT-3 gate contract:
  * SCHEMA: frozen base cols present + additive per-pitch as-of cols present.
  * tick count == number of pitch plays (sentinels excluded).
  * VARYING pre-pitch count is captured from pitchCount, NOT resultCount (the new lever
    the at-bat grid CONSTANT-0'd) -- proving leak-free pre-pitch read.
  * LEAK-FREE: state_diff at pitch k uses only scores AS-OF k; the fatigue summary
    (sp_pitch_count_prior, velo_decline_vs_early) uses ONLY prior-N pitches (shift1),
    never the current or any future pitch; no *_final merged onto a tick.
  * AS-OF MONOTONIC: sp_pitch_count_prior is non-decreasing per pitching side and the
    first pitch of a side has prior-count 0 and NaN fatigue (no prior baseline).
  * PARITY: the same builder (parse -> fetch) produces identical detail values whether
    called for "train" or "inference" -- there is one builder, deterministic, so a
    feature reads identically in both paths (no silent 0.0).
  * base_run_value is a PURE STATIC RE24 lookup; estimation seasons disjoint from gate.
  * ties dropped (not fabricated); outcome assigned when decided.
"""
from __future__ import annotations

import math

from domains.mlb.ingest_pitch_states import (
    fetch_game_pitch_states,
    parse_pitch_states,
    _is_pitch_play,
    _pre_pitch_count,
    _runners_bitmask,
    _pitch_side,
)
from domains.mlb.re24_table import RE24, RE24_ESTIMATION_SEASONS, base_run_value


# --------------------------------------------------------------------------- payload
def _pitch(ptype, pnum, h, a, outs, balls, strikes, ab_pn, velo,
           rtype="ball", on1=False, on2=False, on3=False, px=120.0, py=150.0):
    """One PITCH play. pitchCount = PRE-pitch count (the as-of feature); resultCount =
    POST-pitch count (an OUTCOME -> must never be read as a feature)."""
    res_b, res_s = balls, strikes
    if rtype == "ball":
        res_b = balls + 1
    else:
        res_s = min(strikes + 1, 3)
    p = {
        "type": {"type": rtype},
        "period": {"type": ptype, "number": pnum},
        "homeScore": h, "awayScore": a, "outs": outs,
        "pitchCount": {"balls": balls, "strikes": strikes},
        "resultCount": {"balls": res_b, "strikes": res_s},
        "pitchType": {"abbreviation": "FF"},
        "pitchVelocity": velo,
        "pitchCoordinate": {"x": px, "y": py},
        "atBatPitchNumber": ab_pn,
    }
    if on1:
        p["onFirst"] = {"id": "1"}
    if on2:
        p["onSecond"] = {"id": "2"}
    if on3:
        p["onThird"] = {"id": "3"}
    return p


def _start(ptype, pnum, h, a, outs):
    return {"type": {"type": "start-batterpitcher"},
            "period": {"type": ptype, "number": pnum},
            "homeScore": h, "awayScore": a, "outs": outs}


def _end_inning(pnum, ptype, h, a):
    return {"type": {"type": "end-inning"},
            "period": {"type": ptype, "number": pnum},
            "homeScore": h, "awayScore": a, "outs": 0}


def _payload():
    """A tiny game. HOME pitches in Top halves (away bats); AWAY pitches in Bottom.
    Home starter velocity DECLINES across the Top 1 + Top 2 (95 -> 94 -> 93 -> 90 -> 88)
    so the fatigue lever is non-trivial. Score: home leads 1-0 entering Top 2.
    Ends home 1, away 0 -> home wins (no tie -> not dropped)."""
    plays = [
        # Top 1: home pitcher faces away batters (home is the pitching side).
        _start("Top", 1, 0, 0, 0),
        _pitch("Top", 1, 0, 0, 0, 0, 0, 1, 95.0),            # 0-0 -> ball
        _pitch("Top", 1, 0, 0, 0, 1, 0, 2, 94.0, rtype="strike-looking"),  # 1-0
        _pitch("Top", 1, 0, 0, 0, 1, 1, 3, 93.0),            # 1-1 -> ball
        _end_inning(1, "Mid", 0, 0),
        # Bottom 1: AWAY pitcher faces home batters (away is the pitching side).
        _start("Bottom", 1, 0, 0, 0),
        _pitch("Bottom", 1, 0, 0, 0, 0, 0, 1, 88.0),         # away pitcher's first pitch
        _pitch("Bottom", 1, 0, 0, 0, 0, 1, 2, 87.0, rtype="strike-swinging",
               on1=True),                                    # runner on 1B as-of
        _end_inning(1, "End", 1, 0),                         # home scored 1 (1-0)
        # Top 2: home pitcher again; velo drops further (fatigue).
        _start("Top", 2, 1, 0, 0),
        _pitch("Top", 2, 1, 0, 0, 0, 0, 1, 90.0),            # home leads 1-0 as-of
        _pitch("Top", 2, 1, 0, 0, 1, 0, 2, 88.0, rtype="strike-looking"),
        _end_inning(2, "Mid", 1, 0),
    ]
    return {"plays": plays}


def _train_inference_payload():
    """The base payload + a final home pitch so the game is decided home 1, away 0."""
    p = _payload()
    p["plays"].append(_start("Bottom", 2, 1, 0, 0))
    p["plays"].append(_end_inning(2, "End", 1, 0))
    return p


# --------------------------------------------------------------------------- SCHEMA
def test_frozen_base_and_additive_cols_present():
    meta = {"game_id": "G1", "p0": 0.55, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    rows = fetch_game_pitch_states("eid", meta, lambda u: _train_inference_payload())
    assert rows, "decided game must produce pitch ticks"
    frozen = {"sport", "game_id", "asof_idx", "state_diff", "frac_elapsed", "p0", "outcome"}
    additive = {"count_balls", "count_strikes", "runners", "outs", "atbat_pitch_number",
                "pitch_type", "pitch_velocity", "pitch_loc_x", "pitch_loc_y",
                "sp_pitch_count_prior", "velo_decline_vs_early",
                "base_run_value", "leverage_bucket"}
    meta_cols = {"home_team", "away_team", "date", "season", "half_inning_label"}
    assert frozen.issubset(rows[0].keys())
    assert additive.issubset(rows[0].keys())
    assert meta_cols.issubset(rows[0].keys())


def test_tick_count_equals_pitch_plays_only():
    rows = parse_pitch_states(_payload())
    # 3 (Top1) + 2 (Bottom1) + 2 (Top2) = 7 pitch plays; sentinels excluded.
    assert len(rows) == 7
    assert [r["asof_idx"] for r in rows] == list(range(7))
    # sentinels are not pitch plays
    assert not _is_pitch_play(_start("Top", 1, 0, 0, 0))
    assert not _is_pitch_play(_end_inning(1, "Mid", 0, 0))
    assert _is_pitch_play(_pitch("Top", 1, 0, 0, 0, 1, 1, 3, 93.0))


# --------------------------------------------------------------------------- LEAK-FREE
def test_count_is_prepitch_varying_not_resultcount():
    # THE NEW LEVER: count VARIES across pitches and is read from pitchCount (pre-pitch),
    # NOT resultCount (post-pitch outcome). Top1: (0,0),(1,0),(1,1).
    rows = parse_pitch_states(_payload())
    top1 = [(r["count_balls"], r["count_strikes"]) for r in rows[:3]]
    assert top1 == [(0, 0), (1, 0), (1, 1)]
    # not constant 0 like the at-bat grid was
    assert any((r["count_balls"], r["count_strikes"]) != (0, 0) for r in rows)
    # pre-pitch count never equals the post-pitch resultCount for our ball/strike plays
    # (we proved we read pitchCount): pitch idx1 pre=(1,0); its resultCount was (2,0).
    assert rows[1]["count_balls"] == 1 and rows[1]["count_strikes"] == 0


def test_state_diff_is_asof_leakfree():
    rows = parse_pitch_states(_payload())
    sds = [r["state_diff"] for r in rows]
    # Top1 (0-3): 0-0 ; Bottom1 (4-5): 0-0 ; Top2 (6-7): home leads 1-0 -> +1.
    assert sds == [0, 0, 0, 0, 0, 1, 1]
    # the +1 appears ONLY at/after the run scored, never on an earlier tick (no leak)
    assert all(s == 0 for s in sds[:5])
    assert sds[5] == 1 and sds[6] == 1


def test_no_season_final_merged_on_tick():
    # The detail cols are per-pitch as-of only; there is no *_final / game-total column.
    meta = {"game_id": "G1", "p0": 0.5, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    rows = fetch_game_pitch_states("eid", meta, lambda u: _train_inference_payload())
    banned = [c for c in rows[0].keys()
              if c.endswith("_final") or c.endswith("_total") or c == "final_score"]
    assert banned == []


# --------------------------------------------------------------------------- AS-OF MONOTONIC
def test_fatigue_summary_uses_prior_pitches_only():
    rows = parse_pitch_states(_payload())
    # sp_pitch_count_prior counts PRIOR pitches per pitching SIDE (shift1, prior-N only).
    # Home pitch ticks (Top halves): idx 0,1,2 (Top1) and idx 5,6 (Top2) -> 0,1,2,3,4.
    home_priors = [rows[i]["sp_pitch_count_prior"] for i in (0, 1, 2, 5, 6)]
    assert home_priors == [0, 1, 2, 3, 4]            # non-decreasing, prior-N only
    # Away pitch ticks (Bottom1): idx 3,4 -> independent per-side counter from 0.
    away_priors = [rows[i]["sp_pitch_count_prior"] for i in (3, 4)]
    assert away_priors == [0, 1]


def test_first_pitch_of_side_has_nan_fatigue():
    rows = parse_pitch_states(_payload())
    # First home pitch (idx0) and first away pitch (idx3) have NO prior baseline -> NaN.
    assert math.isnan(rows[0]["velo_decline_vs_early"])
    assert math.isnan(rows[3]["velo_decline_vs_early"])
    # A later home pitch DOES have a decline value, and it is computed from PRIOR velos
    # only: at idx2 (3rd home pitch, velo 93) baseline = mean(95,94)=94.5 -> decline 1.5.
    assert abs(rows[2]["velo_decline_vs_early"] - (94.5 - 93.0)) < 1e-9
    # at Top2 idx5 (velo 90), baseline = mean of FIRST-N prior home velos (95,94,93)=94.0
    assert abs(rows[5]["velo_decline_vs_early"] - (94.0 - 90.0)) < 1e-9


def test_velo_decline_excludes_current_and_future():
    # Hard no-leak check: the decline at pitch k must NOT change if we alter the velocity
    # of pitch k itself only through its OWN velo (it does, by definition it subtracts the
    # current velo) BUT must be invariant to FUTURE pitches. Truncating the payload after
    # pitch k must leave decline[k] identical -> proves no future read.
    full = parse_pitch_states(_payload())
    # Build a truncated payload that stops right after home pitch idx2 (Top1 done).
    trunc_plays = _payload()["plays"][:5]   # start + 3 pitches + end-inning(Mid1)
    trunc = parse_pitch_states({"plays": trunc_plays})
    assert len(trunc) == 3
    for k in range(3):
        a = full[k]["velo_decline_vs_early"]
        b = trunc[k]["velo_decline_vs_early"]
        assert (math.isnan(a) and math.isnan(b)) or abs(a - b) < 1e-9


# --------------------------------------------------------------------------- PARITY
def test_train_inference_parity_identical_builder():
    # One deterministic builder feeds both "train" and "inference"; the same payload must
    # yield byte-identical detail columns in both calls (no feature silently reading 0.0).
    meta = {"game_id": "G1", "p0": 0.55, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    train = fetch_game_pitch_states("eid", meta, lambda u: _train_inference_payload())
    infer = fetch_game_pitch_states("eid", meta, lambda u: _train_inference_payload())
    assert len(train) == len(infer) and train  # non-empty
    keys = ["count_balls", "count_strikes", "runners", "outs", "atbat_pitch_number",
            "pitch_type", "pitch_velocity", "sp_pitch_count_prior",
            "velo_decline_vs_early", "base_run_value", "leverage_bucket"]
    for tr, inf in zip(train, infer):
        for k in keys:
            tv, iv = tr[k], inf[k]
            if isinstance(tv, float) and math.isnan(tv):
                assert math.isnan(iv)
            else:
                assert tv == iv


# --------------------------------------------------------------------------- STATIC RE24
def test_base_run_value_is_static_table_lookup():
    rows = parse_pitch_states(_payload())
    # Bottom1 idx4: runner on 1B (bitmask 4), outs 0 -> RE24[(4,0)] exactly.
    assert rows[4]["runners"] == 4
    assert rows[4]["base_run_value"] == RE24[(4, 0)]
    assert rows[4]["base_run_value"] == base_run_value(4, 0)
    # bases empty 0 outs
    assert rows[0]["base_run_value"] == RE24[(0, 0)]


def test_re24_estimation_seasons_disjoint_from_gate():
    gate_seasons = {2022, 2023}
    assert set(RE24_ESTIMATION_SEASONS).isdisjoint(gate_seasons)
    assert max(RE24_ESTIMATION_SEASONS) < 2022


# --------------------------------------------------------------------------- HONESTY
def test_tie_game_is_dropped_not_fabricated():
    meta = {"game_id": "G1", "p0": 0.5, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    # base payload ends 1-0 actually decided; build a real tie to confirm drop.
    tie = _payload()
    tie["plays"].append(_end_inning(2, "End", 1, 1))   # last score 1-1 -> tie
    rows = fetch_game_pitch_states("eid", meta, lambda u: tie)
    assert rows == []


def test_outcome_assigned_when_decided():
    meta = {"game_id": "G2", "p0": 0.5, "home_team": "NYY", "away_team": "BOS",
            "date": "2023-07-15", "season": 2023}
    rows = fetch_game_pitch_states("eid", meta, lambda u: _train_inference_payload())
    assert rows and all(r["outcome"] == 1 for r in rows)   # home won 1-0
    assert rows[0]["sport"] == "mlb" and rows[0]["game_id"] == "G2"


# --------------------------------------------------------------------------- unit helpers
def test_helpers():
    assert _runners_bitmask({"onFirst": {"id": "x"}}) == 4
    assert _runners_bitmask({"onSecond": 1, "onThird": 1}) == 3
    assert _runners_bitmask({}) == 0
    assert _pitch_side({"period": {"type": "Top", "number": 1}}) == "home"
    assert _pitch_side({"period": {"type": "Bottom", "number": 1}}) == "away"
    assert _pre_pitch_count({"pitchCount": {"balls": 2, "strikes": 1}}) == (2, 1)
    assert _pre_pitch_count({}) is None
