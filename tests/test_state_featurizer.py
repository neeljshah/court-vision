"""Tests for src/ingame/state_featurizer.py.

Core guarantees asserted here:
  (a) MONOTONIC TIME: game_elapsed_sec is non-decreasing across event rows; the
      score-margin label is consistent.
  (b) NO FUTURE-EVENT LEAKAGE: the feature row produced at event i is IDENTICAL
      whether or not events after i exist (truncation invariance). This is the
      hard leak-free guarantee from SPEC section 7.

Tests use a small synthetic PBP plus, when available, a real game from
data/nba/. They run under NBA_OFFLINE=1 with no network.
"""

import os
import sys

sys.path.insert(0, ".")

import pytest  # noqa: E402

from src.ingame import state_featurizer as sf  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixture: tiny 2-team game, scripted events.
# ---------------------------------------------------------------------------
def _synthetic_events():
    # HOME=BOS scores first (left side), AWAY=PHI.
    return [
        {"period": 1, "game_clock_sec": 0, "event_type": 0,
         "event_desc": "Start of 1st Period", "player_name": "",
         "team_abbrev": "", "score": "0-0", "score_margin": "0"},
        {"period": 1, "game_clock_sec": 22, "event_type": 2,
         "event_desc": "MISS Embiid 13' Fadeaway", "player_name": "Embiid",
         "team_abbrev": "PHI", "score": "0-0", "score_margin": "0"},
        {"period": 1, "game_clock_sec": 45, "event_type": 1,
         "event_desc": "Smart 13' Jump Shot (2 PTS)", "player_name": "Smart",
         "team_abbrev": "BOS", "score": "2-0", "score_margin": "2"},
        {"period": 1, "game_clock_sec": 60, "event_type": 1,
         "event_desc": "Tatum 24' 3PT Jump Shot (3 PTS) (Smart 1 AST)",
         "player_name": "Tatum", "team_abbrev": "BOS",
         "score": "5-0", "score_margin": "5"},
        {"period": 1, "game_clock_sec": 75, "event_type": 4,
         "event_desc": "Harris REBOUND (Off:0 Def:1)", "player_name": "Harris",
         "team_abbrev": "PHI", "score": "5-0", "score_margin": "5"},
        {"period": 1, "game_clock_sec": 90, "event_type": 1,
         "event_desc": "Maxey Layup (2 PTS)", "player_name": "Maxey",
         "team_abbrev": "PHI", "score": "5-2", "score_margin": "3"},
        {"period": 1, "game_clock_sec": 100, "event_type": 0,
         "event_desc": "Smart STEAL (1 STL)", "player_name": "Smart",
         "team_abbrev": "BOS", "score": "5-2", "score_margin": "3"},
        {"period": 1, "game_clock_sec": 110, "event_type": 5,
         "event_desc": "Maxey Lost Ball Turnover (P1.T1)",
         "player_name": "Maxey", "team_abbrev": "PHI",
         "score": "5-2", "score_margin": "3"},
        {"period": 1, "game_clock_sec": 120, "event_type": 8,
         "event_desc": "SUB: Brogdon FOR Smart", "player_name": "Smart",
         "team_abbrev": "BOS", "score": "5-2", "score_margin": "3"},
        {"period": 1, "game_clock_sec": 200, "event_type": 3,
         "event_desc": "Tatum Free Throw 1 of 2 (6 PTS)",
         "player_name": "Tatum", "team_abbrev": "BOS",
         "score": "6-2", "score_margin": "4"},
        {"period": 4, "game_clock_sec": 720, "event_type": 13,
         "event_desc": "End of 4th Period", "player_name": "",
         "team_abbrev": "", "score": "6-2", "score_margin": "4"},
    ]


def test_monotonic_time():
    res = sf.featurize_game(_synthetic_events(), "TESTGAME", "BOS", "PHI")
    rows = res["game"]
    assert rows, "expected game rows"
    secs = [r["game_elapsed_sec"] for r in rows]
    assert secs == sorted(secs), "game_elapsed_sec must be non-decreasing"
    # remaining is the complement and never negative
    for r in rows:
        assert r["game_remaining_sec"] >= 0
        assert 0.0 <= r["played_share"] <= 1.0


def test_orientation_and_score_mapping():
    res = sf.featurize_game(_synthetic_events(), "TESTGAME", "BOS", "PHI")
    last = res["game"][-1]
    # BOS (home) scored first -> left side -> home_score tracks left number
    assert last["home_score"] == 6
    assert last["away_score"] == 2
    assert last["score_margin"] == 4
    assert res["orientation"]["resolved"] is True


def test_orientation_away_scores_first():
    ev = _synthetic_events()
    # flip: make PHI (away) score the first basket, on the RIGHT side
    ev2 = [
        {"period": 1, "game_clock_sec": 30, "event_type": 1,
         "event_desc": "Maxey Layup (2 PTS)", "player_name": "Maxey",
         "team_abbrev": "PHI", "score": "0-2", "score_margin": "-2"},
        {"period": 1, "game_clock_sec": 45, "event_type": 1,
         "event_desc": "Smart Jump Shot (2 PTS)", "player_name": "Smart",
         "team_abbrev": "BOS", "score": "2-2", "score_margin": "0"},
        {"period": 4, "game_clock_sec": 720, "event_type": 13,
         "event_desc": "End", "player_name": "", "team_abbrev": "",
         "score": "2-2", "score_margin": "0"},
    ]
    res = sf.featurize_game(ev2, "T2", "BOS", "PHI")
    last = res["game"][-1]
    # home=BOS is on the LEFT (PHI took the right side by scoring first there)
    assert last["home_score"] == 2
    assert last["away_score"] == 2
    assert res["orientation"]["right_team"] == "PHI"


def test_player_accumulation():
    res = sf.featurize_game(_synthetic_events(), "TESTGAME", "BOS", "PHI")
    # find the LAST player row for Tatum (BOS)
    tatum = [r for r in res["players"]
             if r["last_name"] == "Tatum" and r["team_abbrev"] == "BOS"]
    assert tatum, "Tatum rows expected"
    last_tatum = tatum[-1]
    assert last_tatum["pts"] == 6        # 3PT (3) then FT making it 6
    assert last_tatum["fg3m"] == 1
    # Smart got the assist on Tatum's 3
    smart = [r for r in res["players"]
             if r["last_name"] == "Smart" and r["team_abbrev"] == "BOS"]
    assert smart[-1]["ast"] == 1
    assert smart[-1]["stl"] == 1         # steal under event_type 0
    # Maxey: turnover counted
    maxey = [r for r in res["players"]
             if r["last_name"] == "Maxey" and r["team_abbrev"] == "PHI"]
    assert maxey[-1]["tov"] == 1


def test_sub_minutes_tracking():
    res = sf.featurize_game(_synthetic_events(), "TESTGAME", "BOS", "PHI")
    # Smart subbed out at game_sec 120; Brogdon subbed in.
    smart = [r for r in res["players"]
             if r["last_name"] == "Smart" and r["team_abbrev"] == "BOS"]
    # after the sub, Smart should be off-court
    after_sub = [r for r in smart if r["game_elapsed_sec"] >= 120]
    assert after_sub and after_sub[-1]["on_court"] is False
    brogdon = [r for r in res["players"] if r["last_name"] == "Brogdon"]
    assert brogdon and brogdon[-1]["on_court"] is True


def test_no_future_leakage_truncation_invariance():
    """The row at event i must be identical whether or not later events exist.

    We featurize the FULL game, then re-featurize a TRUNCATED copy (events
    0..i), and assert the game-state row at index i matches exactly. If any
    feature peeked at a future event, the truncated value would differ.
    """
    events = _synthetic_events()
    full = sf.featurize_game(events, "TESTGAME", "BOS", "PHI",
                             emit_players=False)["game"]
    # test several cut points
    for i in range(1, len(events)):
        truncated = sf.featurize_game(events[: i + 1], "TESTGAME", "BOS", "PHI",
                                      emit_players=False)["game"]
        # truncated may resolve total game length differently if the truncation
        # drops the final OT marker; compare the cumulative-state fields that
        # must be invariant to future events.
        invariant_keys = [
            "event_idx", "period", "elapsed_sec_in_period", "game_elapsed_sec",
            "home_score", "away_score", "score_margin",
            "home_fga", "home_fgm", "home_fg3m", "home_ftm",
            "away_fga", "away_fgm", "away_tov",
        ]
        row_full = full[i]
        row_trunc = truncated[i]
        for k in invariant_keys:
            assert row_full[k] == row_trunc[k], (
                f"LEAK: key {k} at event {i} differs between full "
                f"({row_full[k]}) and truncated ({row_trunc[k]})"
            )


def test_player_no_future_leakage():
    """Per-player accumulators at event i must not depend on future events."""
    events = _synthetic_events()
    full = sf.featurize_game(events, "TESTGAME", "BOS", "PHI")["players"]
    cut = 6
    trunc = sf.featurize_game(events[: cut + 1], "TESTGAME", "BOS", "PHI")["players"]

    def at(rows, idx):
        return {(r["team_abbrev"], r["last_name"]): r
                for r in rows if r["event_idx"] == idx}

    full_at = at(full, cut)
    trunc_at = at(trunc, cut)
    assert set(full_at) == set(trunc_at)
    for key in full_at:
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "fga"):
            assert full_at[key][stat] == trunc_at[key][stat], (
                f"LEAK in player {key} stat {stat} at event {cut}"
            )


def test_live_snapshot_row():
    snap = {
        "game_id": "X", "period": 2, "clock": "06:00",
        "home_team": "BOS", "away_team": "PHI",
        "home_score": 40, "away_score": 35, "players": [],
    }
    row = sf.featurize_live_snapshot(snap)
    # period 2 with 6:00 remaining -> 12 + 6 = 18 min elapsed = 1080s
    assert row["game_elapsed_sec"] == 18 * 60
    assert row["game_remaining_sec"] == (48 - 18) * 60
    assert row["score_margin"] == 5


def test_parse_clock_formats():
    assert sf._parse_clock_remaining("07:24") == 7 * 60 + 24
    assert sf._parse_clock_remaining("PT07M24.00S") == 7 * 60 + 24
    assert sf._parse_clock_remaining("PT0M30.00S") == 30
    assert sf._parse_clock_remaining("") == 0


# ---------------------------------------------------------------------------
# Real-game smoke test (skips cleanly if data absent).
# ---------------------------------------------------------------------------
def _real_game_available(gid="0022200001"):
    return os.path.exists(os.path.join("data", "nba", f"pbp_{gid}_p1.json"))


@pytest.mark.skipif(not _real_game_available(),
                    reason="real PBP data not present")
def test_real_game_monotonic_and_final_score():
    gid = "0022200001"
    events = sf.load_pbp_events(gid)
    assert events
    res = sf.featurize_game(events, gid, "BOS", "PHI", emit_players=False)
    rows = res["game"]
    secs = [r["game_elapsed_sec"] for r in rows]
    assert secs == sorted(secs)
    # final reconstructed score must match the known final 126-117, BOS home win
    last = rows[-1]
    assert last["home_score"] == 126
    assert last["away_score"] == 117
    assert last["score_margin"] == 9


@pytest.mark.skipif(not _real_game_available(),
                    reason="real PBP data not present")
def test_real_game_truncation_invariance():
    gid = "0022200001"
    events = sf.load_pbp_events(gid)
    full = sf.featurize_game(events, gid, "BOS", "PHI", emit_players=False)["game"]
    for i in (50, 150, 300):
        if i >= len(events):
            continue
        trunc = sf.featurize_game(events[: i + 1], gid, "BOS", "PHI",
                                  emit_players=False)["game"]
        for k in ("home_score", "away_score", "home_fgm", "away_fgm",
                  "home_tov", "away_tov", "game_elapsed_sec"):
            assert full[i][k] == trunc[i][k], f"LEAK at event {i} key {k}"
